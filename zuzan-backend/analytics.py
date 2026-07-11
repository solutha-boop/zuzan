"""
analytics.py — Site visit tracking (engagement + geo).

Public endpoint:  POST /track   — called by the React app on every tab switch.
Admin endpoints are inline in main.py alongside other admin routes.
"""
from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from database import get_db, SiteVisit
import hashlib
import httpx

router = APIRouter()


def _get_client_ip(request: Request) -> str:
    """Return the real client IP, honouring the X-Forwarded-For header set by Render/Nginx."""
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else ""


async def _geo_lookup(ip: str) -> tuple[str | None, str | None]:
    """Return (country, city) for the given IP address using ip-api.com (free tier)."""
    if not ip or ip in ("127.0.0.1", "::1", "localhost", ""):
        return None, None
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(
                f"http://ip-api.com/json/{ip}",
                params={"fields": "status,country,city"},
            )
            data = resp.json()
            if data.get("status") == "success":
                return data.get("country"), data.get("city")
    except Exception:
        pass
    return None, None


@router.post("/track", tags=["Analytics"])
async def track_visit(request: Request, db: Session = Depends(get_db)):
    """Record a page view.  Fire-and-forget from the frontend — always returns 200."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    ip = _get_client_ip(request)
    ip_hash = hashlib.sha256(ip.encode()).hexdigest()[:16] if ip else None
    country, city = await _geo_lookup(ip)

    visit = SiteVisit(
        session_id=(body.get("session_id") or "")[:64] or None,
        page=(body.get("page") or "")[:100] or None,
        referrer=(body.get("referrer") or "")[:500] or None,
        country=country,
        city=city,
        user_agent=(request.headers.get("user-agent") or "")[:300] or None,
        ip_hash=ip_hash,
    )
    db.add(visit)
    try:
        db.commit()
    except Exception:
        db.rollback()

    return {"ok": True}
