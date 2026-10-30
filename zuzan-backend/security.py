"""
ZuZan security helpers (kept in one place so they can be reviewed in one go).

* client_ip()          the real caller IP behind Render's proxy (rate limits used to see ONE shared proxy address)
* Throttle             small in-memory sliding-window counter (per process; fine for a single Render instance)
* SecurityMiddleware   security headers, request-size cap and a global per-IP request ceiling
* check_password()     password policy
"""
import os, time, threading, hashlib
from collections import deque

ON_RENDER = bool(os.environ.get("RENDER"))


def client_ip(request) -> str:
    """Render's edge appends the real client address as the LAST X-Forwarded-For entry; earlier entries can be forged by the caller."""
    if ON_RENDER:
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            last = xff.split(",")[-1].strip()
            if last:
                return last
    return request.client.host if request.client else "unknown"


class Throttle:
    """allow(key) -> True while fewer than `limit` hits were recorded for `key` in the last `window` seconds."""
    def __init__(self, limit: int, window: int):
        self.limit, self.window = limit, window
        self._hits: dict[str, deque] = {}
        self._lock = threading.Lock()

    def _trim(self, q, now):
        while q and q[0] <= now - self.window:
            q.popleft()

    def hit(self, key: str) -> bool:
        """Record one hit; False when over the limit (the hit still counts, so hammering never resets the clock)."""
        now = time.monotonic()
        with self._lock:
            q = self._hits.setdefault(key, deque())
            self._trim(q, now)
            q.append(now)
            if len(self._hits) > 20000:                       # housekeeping: forget idle keys
                for k in [k for k, v in self._hits.items() if not v or v[-1] <= now - self.window][:5000]:
                    self._hits.pop(k, None)
            return len(q) <= self.limit

    def count(self, key: str) -> int:
        now = time.monotonic()
        with self._lock:
            q = self._hits.get(key)
            if not q:
                return 0
            self._trim(q, now)
            return len(q)

    def blocked(self, key: str) -> bool:
        return self.count(key) >= self.limit

    def clear(self, key: str):
        with self._lock:
            self._hits.pop(key, None)


# ── password policy ───────────────────────────────────────────────────────────
_COMMON = {
    "password", "password1", "password123", "password1!", "passw0rd", "qwerty123", "qwertyuiop", "12345678", "123456789",
    "1234567890", "11111111", "00000000", "iloveyou", "welcome1", "welcome123", "admin123", "letmein1", "zuzan2025",
    "zuzan123", "zuzan2026", "abc12345", "monkey123", "dragon123", "football1", "sunshine1", "princess1", "changeme",
    "test1234", "testing123", "qazwsx123", "1q2w3e4r", "asdfghjkl", "johannesburg", "capetown123", "southafrica",
}


def check_password(pw: str, *hints: str) -> str | None:
    """Return a message when the password is not acceptable, else None."""
    pw = pw or ""
    if len(pw) < 8:
        return "Password must be at least 8 characters."
    if len(pw) > 128:
        return "Password must be 128 characters or fewer."
    low = pw.lower()
    if low in _COMMON or len(set(low)) < 4:
        return "That password is too easy to guess. Choose something less common."
    for h in hints:
        h = (h or "").strip().lower()
        if len(h) >= 4 and (low == h or low == h.split("@")[0]):
            return "Your password must not be your email address or name."
    return None


def derived_secret() -> str:
    """Stable, non-public fallback signing key used ONLY when SECRET_KEY was never set on Render: it is derived from
    the database URL (which contains the DB password), so it cannot be guessed from this source code."""
    seed = os.environ.get("DATABASE_URL", "") or "no-database-url"
    return hashlib.sha256(("zuzan|jwt|" + seed).encode()).hexdigest()


# ── ASGI middleware ───────────────────────────────────────────────────────────
MAX_BODY = 25 * 1024 * 1024                    # largest legitimate request is a 10 MB document/CSV (+ multipart overhead)
_global = Throttle(limit=900, window=60)       # per IP, all endpoints together (a busy accountant uses well under this)
_SENSITIVE = (
    ("/clocking/clock-kiosk", Throttle(30, 60)),
    ("/clocking/kiosk-info", Throttle(30, 60)),
    ("/clocking/today-kiosk", Throttle(60, 60)),
    ("/portal/", Throttle(60, 60)),
    ("/auth/accept-invite", Throttle(10, 60)),
    ("/auth/invite/", Throttle(30, 60)),
    ("/auth/verify-email/", Throttle(20, 60)),
    ("/companies/verify-payroll-pin", Throttle(10, 300)),
    ("/ai/", Throttle(40, 60)),
    ("/expenses/scan-receipt", Throttle(20, 60)),
    ("/integrations/", Throttle(120, 60)),
    ("/v1/", Throttle(120, 60)),
    ("/track", Throttle(30, 60)),
    ("/admin/api/", Throttle(30, 60)),
    ("/billing/payfast-notify", Throttle(120, 60)),
    ("/billing/afs-notify", Throttle(120, 60)),
)

_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
    (b"cross-origin-opener-policy", b"same-origin"),
    (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
]


class SecurityMiddleware:
    def __init__(self, app):
        self.app = app

    async def _reply(self, send, status, text, extra=()):
        body = ('{"detail":"%s"}' % text).encode()
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()), *extra]})
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        hdrs = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        path = scope.get("path", "")
        method = scope.get("method", "GET")
        if method != "OPTIONS":
            # ip for throttling
            xff = hdrs.get("x-forwarded-for", "")
            ip = (xff.split(",")[-1].strip() if (ON_RENDER and xff) else (scope.get("client") or ("unknown",))[0]) or "unknown"
            # 1. body size
            try:
                clen = int(hdrs.get("content-length", "0") or 0)
            except ValueError:
                clen = 0
            if clen > MAX_BODY:
                return await self._reply(send, 413, "Request is too large.")
            # 2. throttles
            if path not in ("/health", "/") and os.environ.get("ZUZAN_DISABLE_THROTTLE") != "1":
                if not _global.hit(ip):
                    return await self._reply(send, 429, "Too many requests. Please slow down.", [(b"retry-after", b"60")])
                for prefix, thr in _SENSITIVE:
                    if path.startswith(prefix):
                        if not thr.hit(ip + "|" + prefix):
                            return await self._reply(send, 429, "Too many requests. Please try again shortly.", [(b"retry-after", b"60")])
                        break

        async def send_wrapped(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {k.lower() for k, _ in headers}
                for k, v in _HEADERS:
                    if k not in present:
                        headers.append((k, v))
                if b"cache-control" not in present and not path.startswith(("/docs", "/redoc", "/openapi.json")):
                    headers.append((b"cache-control", b"no-store"))        # financial data must never sit in a shared/browser cache
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapped)
