"""
Salt Edge Account Information API v5 integration.
Provides bank feeds via Salt Edge's hosted Connect Widget.

Env vars required:
  SALTEDGE_APP_ID      — from Salt Edge dashboard
  SALTEDGE_SECRET      — from Salt Edge dashboard
  SALTEDGE_REDIRECT_URI — e.g. https://zuzan-app.onrender.com (frontend URL, no path needed)
  FRONTEND_URL         — e.g. https://zuzan-app.onrender.com

Flow:
  1. POST /banking/saltedge/connect  → create customer + connect session → return {connect_url}
  2. Frontend redirects user to connect_url (Salt Edge hosted widget)
  3. User selects bank and logs in on Salt Edge
  4. Salt Edge redirects user to SALTEDGE_REDIRECT_URI?connection_id=XXX#bankfeeds
  5. Frontend hits GET /banking/saltedge/callback?connection_id=XXX
  6. Backend stores connection, syncs accounts + transactions
"""

import os, logging, requests
from datetime import datetime, date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import (
    get_db, User, Invoice, Expense, InvoiceStatus,
    SaltEdgeConnection, SaltEdgeBankAccount, SaltEdgeTransaction,
)
from auth import get_current_user

logger = logging.getLogger("zuzan.saltedge")

SALTEDGE_APP_ID    = os.environ.get("SALTEDGE_APP_ID", "")
SALTEDGE_SECRET    = os.environ.get("SALTEDGE_SECRET", "")
SALTEDGE_BASE_URL  = "https://www.saltedge.com/api/v5"
FRONTEND_URL       = os.environ.get("FRONTEND_URL", "https://zuzan-app.onrender.com")

saltedge_router = APIRouter()

# ── Helpers ──────────────────────────────────────────────────────────────────

def _headers():
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "App-id": SALTEDGE_APP_ID,
        "Secret": SALTEDGE_SECRET,
    }

def _se_get(path: str, params: dict = None):
    r = requests.get(f"{SALTEDGE_BASE_URL}{path}", headers=_headers(), params=params, timeout=30)
    if not r.ok:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json().get("data")

def _se_post(path: str, payload: dict):
    r = requests.post(f"{SALTEDGE_BASE_URL}{path}", headers=_headers(), json=payload, timeout=30)
    if not r.ok:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json().get("data")

def _se_delete(path: str):
    r = requests.delete(f"{SALTEDGE_BASE_URL}{path}", headers=_headers(), timeout=30)
    if not r.ok:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json().get("data")

def _ensure_customer(company_id: int, db: Session) -> str:
    """Get or create a Salt Edge customer for this company. Returns saltedge_customer_id."""
    conn_rec = db.query(SaltEdgeConnection).filter_by(company_id=company_id).first()
    if conn_rec and conn_rec.saltedge_customer_id:
        return conn_rec.saltedge_customer_id

    # Create customer on Salt Edge
    data = _se_post("/customers", {"data": {"identifier": f"zuzan_company_{company_id}"}})
    customer_id = str(data["id"])

    if not conn_rec:
        conn_rec = SaltEdgeConnection(company_id=company_id)
        db.add(conn_rec)
    conn_rec.saltedge_customer_id = customer_id
    db.commit()
    return customer_id

def _to_zar(inv) -> float:
    if inv.currency and inv.currency != "ZAR":
        return (inv.total_amount or 0) * (inv.exchange_rate or 1)
    return inv.total_amount or 0

def _auto_match(company_id: int, db: Session):
    """Auto-match unmatched transactions against open invoices and expenses."""
    txns = db.query(SaltEdgeTransaction).filter_by(
        company_id=company_id, match_status="unmatched"
    ).all()

    open_invoices = db.query(Invoice).filter(
        Invoice.company_id == company_id,
        Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue]),
    ).all()

    open_expenses = db.query(Expense).filter_by(company_id=company_id).all()

    for txn in txns:
        txn_date = txn.made_on.date() if isinstance(txn.made_on, datetime) else txn.made_on

        if txn.amount > 0:
            # Credit → try to match to an invoice
            best_inv, best_conf = None, 0.0
            for inv in open_invoices:
                inv_zar = _to_zar(inv)
                if inv_zar <= 0:
                    continue
                if abs(txn.amount - inv_zar) / inv_zar > 0.01:
                    continue
                # Date proximity score
                inv_date = inv.due_date or inv.invoice_date
                if inv_date:
                    if isinstance(inv_date, datetime):
                        inv_date = inv_date.date()
                    days = abs((txn_date - inv_date).days) if inv_date else 999
                    conf = 0.95 if days <= 1 else 0.85 if days <= 7 else 0.75 if days <= 30 else 0.65
                else:
                    conf = 0.65
                if conf > best_conf:
                    best_conf, best_inv = conf, inv
            if best_inv and best_conf >= 0.65:
                txn.match_status       = "matched"
                txn.matched_invoice_id = best_inv.id
                txn.match_confidence   = best_conf
                txn.matched_at         = datetime.utcnow()

        elif txn.amount < 0:
            # Debit → try to match to an expense
            abs_amt = abs(txn.amount)
            best_exp, best_conf = None, 0.0
            for exp in open_expenses:
                exp_amt = exp.amount or 0
                if exp_amt <= 0:
                    continue
                if abs(abs_amt - exp_amt) / exp_amt > 0.01:
                    continue
                exp_date = exp.expense_date
                if exp_date:
                    if isinstance(exp_date, datetime):
                        exp_date = exp_date.date()
                    days = abs((txn_date - exp_date).days)
                    conf = 0.90 if days <= 1 else 0.75 if days <= 7 else 0.55
                else:
                    conf = 0.55
                if conf > best_conf:
                    best_conf, best_exp = conf, exp
            if best_exp and best_conf >= 0.55:
                txn.match_status      = "matched"
                txn.matched_expense_id = best_exp.id
                txn.match_confidence   = best_conf
                txn.matched_at         = datetime.utcnow()

    db.commit()

def _sync_accounts_and_txns(connection_id_str: str, company_id: int, conn_rec: SaltEdgeConnection, db: Session):
    """Sync accounts and transactions for a Salt Edge connection."""
    # Sync accounts
    accounts_data = _se_get("/accounts", {"connection_id": connection_id_str})
    if not accounts_data:
        return 0, 0

    acct_map = {}
    for a in accounts_data:
        sid = str(a["id"])
        acct = db.query(SaltEdgeBankAccount).filter_by(saltedge_account_id=sid).first()
        if not acct:
            acct = SaltEdgeBankAccount(
                company_id=company_id,
                connection_id=conn_rec.id,
                saltedge_account_id=sid,
            )
            db.add(acct)
        acct.name          = a.get("name")
        acct.nature        = a.get("nature")
        acct.balance       = a.get("balance")
        acct.currency_code = a.get("currency_code", "ZAR")
        acct.last_synced   = datetime.utcnow()
        db.flush()
        acct_map[sid] = acct

    db.commit()

    # Sync transactions — up to 6 pages × 50 per account
    new_count = 0
    for sid, acct in acct_map.items():
        next_id = None
        for _ in range(6):
            params = {"connection_id": connection_id_str, "account_id": sid, "per_page": 50}
            if next_id:
                params["from_id"] = next_id
            txns_data = _se_get("/transactions", params)
            if not txns_data:
                break
            for t in txns_data:
                tid = str(t["id"])
                if db.query(SaltEdgeTransaction).filter_by(saltedge_txn_id=tid).first():
                    continue
                made_on = datetime.strptime(t["made_on"], "%Y-%m-%d") if isinstance(t.get("made_on"), str) else datetime.utcnow()
                txn = SaltEdgeTransaction(
                    company_id=company_id,
                    bank_account_id=acct.id,
                    saltedge_txn_id=tid,
                    amount=t.get("amount", 0),
                    description=t.get("description"),
                    made_on=made_on,
                    status=t.get("status"),
                )
                db.add(txn)
                new_count += 1
            if len(txns_data) < 50:
                break
            next_id = txns_data[-1]["id"]

    db.commit()
    conn_rec.last_synced = datetime.utcnow()
    db.commit()

    _auto_match(company_id, db)
    return len(acct_map), new_count

# ── Endpoints ─────────────────────────────────────────────────────────────────

@saltedge_router.get("/connect")
async def connect(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Step 1: create a connect session and return the Salt Edge Connect Widget URL."""
    if not SALTEDGE_APP_ID or not SALTEDGE_SECRET:
        raise HTTPException(status_code=503, detail="Salt Edge credentials not configured")

    cid = current_user.company_id
    customer_id = _ensure_customer(cid, db)
    return_to = f"{FRONTEND_URL}?saltedge=callback#bankfeeds"

    data = _se_post("/connect_sessions/create", {
        "data": {
            "customer_id": customer_id,
            "consent": {
                "scopes": ["account_details", "transactions_details"],
                "from_date": "2024-01-01",
            },
            "attempt": {
                "return_to": return_to,
                "fetch_scopes": ["accounts", "transactions"],
                "store_credentials": True,
            },
        }
    })
    return {"connect_url": data["connect_url"]}


@saltedge_router.get("/callback")
async def callback(
    connection_id: str = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Step 2: called after user completes Salt Edge Connect. Stores connection and syncs."""
    cid = current_user.company_id
    conn_rec = db.query(SaltEdgeConnection).filter_by(company_id=cid).first()
    if not conn_rec:
        raise HTTPException(status_code=400, detail="No Salt Edge customer found. Please reconnect.")

    # If connection_id wasn't passed, look it up via API
    if not connection_id:
        connections = _se_get("/connections", {"customer_id": conn_rec.saltedge_customer_id})
        if not connections:
            raise HTTPException(status_code=400, detail="No connection found. Please complete the bank connection.")
        connection_id = str(connections[0]["id"])
        provider_name = connections[0].get("provider_name", "")
    else:
        # Look up provider name
        try:
            conn_data = _se_get(f"/connections/{connection_id}")
            provider_name = conn_data.get("provider_name", "")
        except Exception:
            provider_name = ""

    conn_rec.saltedge_connection_id = str(connection_id)
    conn_rec.provider_name = provider_name
    conn_rec.status = "active"
    conn_rec.connected_at = datetime.utcnow()
    db.commit()

    accts, txns = _sync_accounts_and_txns(str(connection_id), cid, conn_rec, db)
    return {"connected": True, "accounts_synced": accts, "transactions_imported": txns}


@saltedge_router.get("/status")
async def status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conn_rec = db.query(SaltEdgeConnection).filter_by(company_id=current_user.company_id).first()
    if not conn_rec or not conn_rec.saltedge_connection_id:
        return {"connected": False, "provider": "saltedge"}

    accts = db.query(SaltEdgeBankAccount).filter_by(company_id=current_user.company_id, is_active=True).all()
    return {
        "connected": True,
        "provider": "saltedge",
        "provider_name": conn_rec.provider_name,
        "accounts_count": len(accts),
        "last_synced": conn_rec.last_synced.isoformat() if conn_rec.last_synced else None,
    }


@saltedge_router.get("/accounts")
async def accounts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    accts = db.query(SaltEdgeBankAccount).filter_by(
        company_id=current_user.company_id, is_active=True
    ).all()
    return [
        {
            "id": a.id,
            "name": a.name,
            "nature": a.nature,
            "balance": a.balance,
            "currency_code": a.currency_code,
            "last_synced": a.last_synced.isoformat() if a.last_synced else None,
        }
        for a in accts
    ]


@saltedge_router.post("/sync")
async def sync(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cid = current_user.company_id
    conn_rec = db.query(SaltEdgeConnection).filter_by(company_id=cid).first()
    if not conn_rec or not conn_rec.saltedge_connection_id:
        raise HTTPException(status_code=400, detail="No Salt Edge connection found.")

    accts, txns = _sync_accounts_and_txns(conn_rec.saltedge_connection_id, cid, conn_rec, db)
    return {"accounts_synced": accts, "transactions_new": txns}


@saltedge_router.get("/transactions")
async def transactions(
    match_status: str = "unmatched",
    limit: int = 200,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(SaltEdgeTransaction).filter_by(company_id=current_user.company_id)
    if match_status != "all":
        q = q.filter(SaltEdgeTransaction.match_status == match_status)
    txns = q.order_by(SaltEdgeTransaction.made_on.desc()).limit(limit).all()

    result = []
    for t in txns:
        acct = db.query(SaltEdgeBankAccount).filter_by(id=t.bank_account_id).first()
        inv  = db.query(Invoice).filter_by(id=t.matched_invoice_id).first() if t.matched_invoice_id else None
        exp  = db.query(Expense).filter_by(id=t.matched_expense_id).first() if t.matched_expense_id else None
        result.append({
            "id": t.id,
            "amount": t.amount,
            "description": t.description,
            "made_on": t.made_on.isoformat() if t.made_on else None,
            "status": t.status,
            "match_status": t.match_status,
            "match_confidence": t.match_confidence,
            "account_name": acct.name if acct else None,
            "matched_invoice": {"id": inv.id, "invoice_number": inv.invoice_number, "total_amount": inv.total_amount} if inv else None,
            "matched_expense": {"id": exp.id, "description": exp.description, "amount": exp.amount} if exp else None,
        })
    return result


@saltedge_router.post("/transactions/{txn_id}/match")
async def match_txn(
    txn_id: int,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    txn = db.query(SaltEdgeTransaction).filter_by(id=txn_id, company_id=current_user.company_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    txn.match_status       = "matched"
    txn.matched_invoice_id = body.get("invoice_id")
    txn.matched_expense_id = body.get("expense_id")
    txn.match_confidence   = 1.0
    txn.matched_at         = datetime.utcnow()
    db.commit()
    return {"ok": True}


@saltedge_router.post("/transactions/{txn_id}/exclude")
async def exclude_txn(
    txn_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    txn = db.query(SaltEdgeTransaction).filter_by(id=txn_id, company_id=current_user.company_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    txn.match_status = "excluded"
    db.commit()
    return {"ok": True}


@saltedge_router.post("/transactions/{txn_id}/unmatch")
async def unmatch_txn(
    txn_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    txn = db.query(SaltEdgeTransaction).filter_by(id=txn_id, company_id=current_user.company_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    txn.match_status       = "unmatched"
    txn.matched_invoice_id = None
    txn.matched_expense_id = None
    txn.match_confidence   = None
    txn.matched_at         = None
    db.commit()
    return {"ok": True}


@saltedge_router.delete("/disconnect")
async def disconnect(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cid = current_user.company_id
    conn_rec = db.query(SaltEdgeConnection).filter_by(company_id=cid).first()
    if not conn_rec:
        raise HTTPException(status_code=404, detail="No connection found")

    # Delete connection on Salt Edge
    if conn_rec.saltedge_connection_id:
        try:
            _se_delete(f"/connections/{conn_rec.saltedge_connection_id}")
        except Exception as e:
            logger.warning(f"Salt Edge disconnect API error: {e}")

    # Keep transaction history, just clear the connection
    conn_rec.saltedge_connection_id = None
    conn_rec.provider_name = None
    conn_rec.status = "inactive"
    db.commit()
    return {"disconnected": True}
