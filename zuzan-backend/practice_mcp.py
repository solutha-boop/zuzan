"""
practice_mcp.py - read-only MCP endpoint for the Solutha practice agent.

Lets a Claude custom connector read a practice user's client companies
(the companies the user can switch into) without a browser login.

Endpoint:  POST /mcp   (MCP Streamable HTTP, JSON responses, stateless)
Auth:      Authorization: Bearer <PRACTICE_MCP_TOKEN>
Config:    PRACTICE_MCP_TOKEN       long random secret (32+ chars). Unset = endpoint disabled.
           PRACTICE_MCP_USER_EMAIL  the practice user whose client companies are exposed.

Every tool is READ ONLY. Tools reuse the existing report endpoints so the
figures match what the user sees in the app. Nothing here writes to the DB
(the report functions only read; the session is rolled back and closed).
"""
import hmac
import inspect
import json
import logging
import os
from datetime import datetime, date
from typing import Any, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from database import SessionLocal, User, Company, CompanyMembership, Payslip, Employee

router = APIRouter()
logger = logging.getLogger("zuzan.practice_mcp")

PROTOCOL_VERSIONS = ["2025-06-18", "2025-03-26", "2024-11-05"]
SERVER_INFO = {"name": "zuzan-practice", "version": "1.0.0"}


# ── AUTH ──────────────────────────────────────────────────────────────────────
def _token_ok(request: Request) -> bool:
    expected = os.environ.get("PRACTICE_MCP_TOKEN", "")
    if len(expected) < 32:
        return False
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return False
    return hmac.compare_digest(header[7:].strip().encode(), expected.encode())


def _practice_user(db) -> Optional[User]:
    email = (os.environ.get("PRACTICE_MCP_USER_EMAIL") or "").strip().lower()
    if not email:
        return None
    user = db.query(User).filter(User.email.ilike(email)).first()
    if not user or not getattr(user, "is_active", True):
        return None
    return user


def _clients(db, user: User) -> dict:
    """company_id -> (Company, role) for every company the user can switch into."""
    out = {}
    for m in db.query(CompanyMembership).filter(CompanyMembership.user_id == user.id).all():
        co = db.query(Company).filter(Company.id == m.company_id).first()
        if co:
            out[co.id] = (co, m.role)
    if user.company_id and user.company_id not in out:
        co = db.query(Company).filter(Company.id == user.company_id).first()
        if co:
            out[co.id] = (co, user.role or "owner")
    return out


def _as_company(db, user: User, company_id: int, role: str) -> User:
    """Same in-memory swap get_current_user does after /auth/switch-company - never persisted."""
    db.expunge(user)
    user.company_id = company_id
    user.role = role
    return user


# ── HELPERS ───────────────────────────────────────────────────────────────────
def _jsonable(obj):
    return json.loads(json.dumps(obj, default=lambda o: o.isoformat() if isinstance(o, (datetime, date)) else str(o)))


async def _call(fn, **kwargs):
    res = fn(**kwargs)
    if inspect.isawaitable(res):
        res = await res
    return res


def _prev_month(today: date) -> str:
    y, m = today.year, today.month - 1
    if m == 0:
        y, m = y - 1, 12
    return f"{y:04d}-{m:02d}"


def _period(value: Optional[str], default: str) -> str:
    v = (value or "").strip()
    if not v:
        return default
    datetime.strptime(v, "%Y-%m")       # raises ValueError on a bad period
    return v


# ── TOOLS ─────────────────────────────────────────────────────────────────────
_CID = {"company_id": {"type": "integer", "description": "Client company id from list_clients."}}
_PERIOD = {"period": {"type": "string", "description": "Month as YYYY-MM. Optional."}}

TOOLS = [
    {"name": "list_clients",
     "description": "List the practice's client companies in ZuZan (id, name, VAT registered, the practice's role). Call this first.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "client_snapshot",
     "description": "One-call weekly check for a client: debtors aging, VAT201 for the current and previous month (if VAT registered), EMP201 for last month, payroll status for last month and this month, and the balance-sheet reconciliation checks.",
     "inputSchema": {"type": "object", "properties": dict(_CID), "required": ["company_id"], "additionalProperties": False}},
    {"name": "debtors_aging",
     "description": "Outstanding customer invoices for a client, aged by due date, with per-customer totals.",
     "inputSchema": {"type": "object", "properties": dict(_CID), "required": ["company_id"], "additionalProperties": False}},
    {"name": "vat201",
     "description": "VAT201 figures for a client for one month (months=1) or a two-month period starting at period (months=2). Defaults to the current month.",
     "inputSchema": {"type": "object", "properties": {**_CID, **_PERIOD, "months": {"type": "integer", "enum": [1, 2]}}, "required": ["company_id"], "additionalProperties": False}},
    {"name": "emp201",
     "description": "EMP201 (PAYE, UIF, SDL, ETI) for a client's payroll month. Defaults to last month, which is due by the 7th of this month.",
     "inputSchema": {"type": "object", "properties": {**_CID, **_PERIOD}, "required": ["company_id"], "additionalProperties": False}},
    {"name": "payroll_status",
     "description": "Whether payroll has been run for a client's month: payslip count, active employees and gross/net totals. Defaults to the current month.",
     "inputSchema": {"type": "object", "properties": {**_CID, **_PERIOD}, "required": ["company_id"], "additionalProperties": False}},
    {"name": "reconciliation_checks",
     "description": "Balance-sheet reconciliation checks for a client (pass/warn/fail per rule). Needs the client on the Professional plan.",
     "inputSchema": {"type": "object", "properties": dict(_CID), "required": ["company_id"], "additionalProperties": False}},
]


async def _debtors(db, u):
    import payroll as P
    return await _call(P.debtors_aging, current_user=u, db=db)


async def _vat(db, u, period=None, months=1):
    import payroll as P
    return await _call(P.vat201, current_user=u, db=db, period=period, months=months)


async def _emp(db, u, period):
    import payroll as P
    return await _call(P.emp201, current_user=u, db=db, period=period, date_from=None, date_to=None)


def _payroll_status(db, company_id, period):
    active = db.query(Employee).filter(Employee.company_id == company_id, Employee.is_active == True).count()
    slips = (db.query(Payslip).join(Employee, Payslip.employee_id == Employee.id)
             .filter(Employee.company_id == company_id, Payslip.period == period).all())
    def tot(attr):
        return round(sum((getattr(s, attr, 0) or 0) for s in slips), 2)
    return {"period": period, "payroll_run": bool(slips), "payslips": len(slips), "active_employees": active,
            "gross_total": tot("gross_salary"), "net_total": tot("net_pay"), "paye_total": tot("paye")}


async def _recon(db, u):
    import payroll as P
    return await _call(P.reconciliation, current_user=u, db=db)


async def _safe(coro_or_value):
    try:
        if inspect.isawaitable(coro_or_value):
            return await coro_or_value
        return coro_or_value
    except Exception as e:  # HTTPException or report error: report it, don't fail the snapshot
        detail = getattr(e, "detail", None) or str(e)
        return {"error": str(detail)}


async def _run_tool(name: str, args: dict) -> Any:
    db = SessionLocal()
    try:
        user = _practice_user(db)
        if not user:
            raise ValueError("The practice user is not configured or not active (PRACTICE_MCP_USER_EMAIL).")
        clients = _clients(db, user)
        if name == "list_clients":
            return [{"company_id": cid, "name": co.name, "vat_registered": bool(getattr(co, "vat_registered", True)), "role": role}
                    for cid, (co, role) in sorted(clients.items(), key=lambda kv: kv[1][0].name.lower())]

        try:
            cid = int(args.get("company_id"))
        except (TypeError, ValueError):
            raise ValueError("company_id is required: call list_clients for the ids.")
        if cid not in clients:
            raise ValueError("That company is not one of this practice's clients.")
        co, role = clients[cid]
        u = _as_company(db, user, cid, role)
        today = datetime.utcnow().date()
        this_month = today.strftime("%Y-%m")

        if name == "debtors_aging":
            return await _debtors(db, u)
        if name == "vat201":
            if not getattr(co, "vat_registered", True):
                return {"note": f"{co.name} is not VAT registered in ZuZan."}
            months = int(args.get("months") or 1)
            if months not in (1, 2):
                raise ValueError("months must be 1 or 2.")
            return await _vat(db, u, _period(args.get("period"), this_month), months)
        if name == "emp201":
            return await _emp(db, u, _period(args.get("period"), _prev_month(today)))
        if name == "payroll_status":
            return _payroll_status(db, cid, _period(args.get("period"), this_month))
        if name == "reconciliation_checks":
            return await _recon(db, u)
        if name == "client_snapshot":
            snap = {"company_id": cid, "name": co.name, "as_of": today.isoformat(),
                    "debtors_aging": await _safe(_debtors(db, u)),
                    "emp201_last_month": await _safe(_emp(db, u, _prev_month(today))),
                    "payroll_last_month": _payroll_status(db, cid, _prev_month(today)),
                    "payroll_this_month": _payroll_status(db, cid, this_month),
                    "reconciliation": await _safe(_recon(db, u))}
            if getattr(co, "vat_registered", True):
                snap["vat201_this_month"] = await _safe(_vat(db, u, this_month, 1))
                snap["vat201_last_month"] = await _safe(_vat(db, u, _prev_month(today), 1))
            else:
                snap["vat201"] = "Not VAT registered in ZuZan."
            return snap
        raise LookupError(name)
    finally:
        db.rollback()
        db.close()


# ── JSON-RPC ──────────────────────────────────────────────────────────────────
def _ok(rid, result):
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def _err(rid, code, message):
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


async def _handle(msg: dict) -> Optional[dict]:
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or "method" not in msg:
        return _err(msg.get("id") if isinstance(msg, dict) else None, -32600, "Invalid request")
    rid, method, params = msg.get("id"), msg["method"], msg.get("params") or {}
    if rid is None:                                    # notification (e.g. notifications/initialized)
        return None
    if method == "initialize":
        asked = params.get("protocolVersion")
        return _ok(rid, {"protocolVersion": asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
                         "capabilities": {"tools": {"listChanged": False}},
                         "serverInfo": SERVER_INFO,
                         "instructions": "Read-only access to the Solutha practice's client companies in ZuZan. Call list_clients first, then client_snapshot per client."})
    if method == "ping":
        return _ok(rid, {})
    if method == "tools/list":
        return _ok(rid, {"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name")
        if name not in {t["name"] for t in TOOLS}:
            return _err(rid, -32602, f"Unknown tool: {name}")
        try:
            data = await _run_tool(name, params.get("arguments") or {})
            return _ok(rid, {"content": [{"type": "text", "text": json.dumps(_jsonable(data), ensure_ascii=False)}], "isError": False})
        except (ValueError, LookupError) as e:
            return _ok(rid, {"content": [{"type": "text", "text": str(e)}], "isError": True})
        except Exception:
            logger.exception("practice MCP tool %s failed", name)
            return _ok(rid, {"content": [{"type": "text", "text": "ZuZan could not produce that report. Try again later."}], "isError": True})
    return _err(rid, -32601, f"Method not found: {method}")


@router.post("/mcp")
async def mcp_post(request: Request):
    if len(os.environ.get("PRACTICE_MCP_TOKEN", "")) < 32:
        return JSONResponse({"detail": "Practice connector is not enabled."}, status_code=503)
    if not _token_ok(request):
        return JSONResponse({"detail": "Unauthorized"}, status_code=401, headers={"WWW-Authenticate": "Bearer"})
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(_err(None, -32700, "Parse error"), status_code=400)
    if isinstance(body, list):
        replies = [r for r in [await _handle(m) for m in body] if r is not None]
        return JSONResponse(replies) if replies else Response(status_code=202)
    reply = await _handle(body)
    return JSONResponse(reply) if reply is not None else Response(status_code=202)


@router.get("/mcp")
async def mcp_get():
    return Response(status_code=405, headers={"Allow": "POST"})


@router.delete("/mcp")
async def mcp_delete():
    return Response(status_code=405, headers={"Allow": "POST"})
