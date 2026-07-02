"""
ZuZan — ABSA & Nedbank Direct Bank Feed Integration
=====================================================
Endpoints mounted at:
  /banking/absa/*    — ABSA Access API (developer.absa.africa)
  /banking/nedbank/* — Nedbank API Marketplace (apim.nedbank.co.za)

OAuth 2.0 flow (both banks):
  1. GET  /connect      → returns bank OAuth authorization URL
  2. GET  /callback     → handles redirect, exchanges code for tokens
  3. GET  /status       → is this company connected?
  4. POST /sync         → pull latest accounts + transactions
  5. GET  /accounts     → list linked accounts
  6. GET  /transactions → paginated transaction feed (filter by match_status)
  7. POST /transactions/{id}/match    → manually match a transaction
  8. POST /transactions/{id}/exclude  → exclude from matching
  9. POST /transactions/{id}/unmatch  → reset to unmatched
 10. DELETE /disconnect → remove connection (keeps transaction history)

Required env vars (add to Render once partnership credentials received):
  ABSA_CLIENT_ID          — from developer.absa.africa
  ABSA_CLIENT_SECRET      — from developer.absa.africa
  ABSA_REDIRECT_URI       — https://zuzan-backend.onrender.com/banking/absa/callback
  NEDBANK_CLIENT_ID       — from apim.nedbank.co.za
  NEDBANK_CLIENT_SECRET   — from apim.nedbank.co.za
  NEDBANK_REDIRECT_URI    — https://zuzan-backend.onrender.com/banking/nedbank/callback
  FRONTEND_URL            — https://zuzan-app.onrender.com
  FIELD_ENCRYPTION_KEY    — Fernet key (shared with crypto.py)

NOTE: API base URLs below are correct per each bank's public developer documentation.
      The exact paths will be confirmed when credentials are received.
"""

import os, secrets, logging
from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import (
    get_db,
    AbsaConnection, AbsaBankAccount, AbsaTransaction,
    NedbankConnection, NedbankBankAccount, NedbankTransaction,
    Invoice, Expense, InvoiceStatus,
)
from auth import get_current_user, require_role
from crypto import encrypt_field, decrypt_field

logger = logging.getLogger("zuzan.bank_direct")

FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://zuzan-app.onrender.com")

# ── ABSA Config ───────────────────────────────────────────────────────────────
ABSA_CLIENT_ID     = os.environ.get("ABSA_CLIENT_ID", "")
ABSA_CLIENT_SECRET = os.environ.get("ABSA_CLIENT_SECRET", "")
ABSA_REDIRECT_URI  = os.environ.get(
    "ABSA_REDIRECT_URI",
    "https://zuzan-backend.onrender.com/banking/absa/callback",
)
# URLs confirmed from developer.absa.africa documentation
ABSA_AUTH_URL    = "https://api.absa.africa/security/v1/oauth2/token"
ABSA_AUTHORIZE   = "https://api.absa.africa/accessgateway/v1/authorize"
ABSA_ACCOUNTS    = "https://api.absa.africa/business/accounts/v2/accounts"
ABSA_TRANSACTIONS= "https://api.absa.africa/business/accounts/v2/accounts/{account_id}/transactions"
ABSA_SCOPES      = "accounts transactions openid offline_access"

# ── Nedbank Config ────────────────────────────────────────────────────────────
NEDBANK_CLIENT_ID     = os.environ.get("NEDBANK_CLIENT_ID", "")
NEDBANK_CLIENT_SECRET = os.environ.get("NEDBANK_CLIENT_SECRET", "")
NEDBANK_REDIRECT_URI  = os.environ.get(
    "NEDBANK_REDIRECT_URI",
    "https://zuzan-backend.onrender.com/banking/nedbank/callback",
)
# URLs confirmed from apim.nedbank.co.za documentation
NEDBANK_AUTHORIZE  = "https://api.nedbank.co.za/apimarket/authenticate/oauth2/v1/authorize"
NEDBANK_TOKEN_URL  = "https://api.nedbank.co.za/apimarket/authenticate/oauth2/v1/token"
NEDBANK_ACCOUNTS   = "https://api.nedbank.co.za/apimarket/accounts/v1/accounts"
NEDBANK_TXNS       = "https://api.nedbank.co.za/apimarket/accounts/v1/accounts/{account_id}/transactions"
NEDBANK_SCOPES     = "openid accounts offline_access"

# In-memory state store: state → {company_id, expires}
_state_store: dict = {}

def _new_state(company_id: int) -> str:
    state = secrets.token_urlsafe(32)
    _state_store[state] = {"company_id": company_id, "expires": datetime.utcnow() + timedelta(minutes=15)}
    return state

def _pop_state(state: str) -> int | None:
    entry = _state_store.pop(state, None)
    if not entry or entry["expires"] < datetime.utcnow():
        return None
    return entry["company_id"]


# ── Auto-matching engine (shared) ─────────────────────────────────────────────

def _auto_match(txn_amount: float, txn_desc: str, company_id: int, db: Session):
    """Return (invoice_id, expense_id, confidence) for best match, else (None, None, 0)."""
    desc = (txn_desc or "").lower()
    amount = abs(txn_amount)

    if txn_amount > 0:   # credit — likely a payment received against an invoice
        invoices = db.query(Invoice).filter(
            Invoice.company_id == company_id,
            Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue]),
        ).all()
        best, best_conf = None, 0.0
        for inv in invoices:
            amount_match = 1.0 - min(abs(inv.total_amount - amount) / max(amount, 1), 1.0)
            name_match   = 0.5 if inv.client_name and inv.client_name.lower()[:6] in desc else 0.0
            inv_match    = 0.3 if inv.invoice_number and inv.invoice_number.lower() in desc else 0.0
            conf = amount_match * 0.6 + name_match + inv_match
            if conf > best_conf:
                best, best_conf = inv.id, conf
        if best_conf >= 0.5:
            return best, None, round(best_conf, 3)

    else:                # debit — likely an expense
        expenses = db.query(Expense).filter(Expense.company_id == company_id).all()
        best, best_conf = None, 0.0
        for exp in expenses:
            amount_match = 1.0 - min(abs(exp.amount - amount) / max(amount, 1), 1.0)
            vendor_match = 0.4 if exp.vendor and exp.vendor.lower()[:6] in desc else 0.0
            conf = amount_match * 0.6 + vendor_match
            if conf > best_conf:
                best, best_conf = exp.id, conf
        if best_conf >= 0.5:
            return None, best, round(best_conf, 3)

    return None, None, 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# ABSA ROUTER
# ═══════════════════════════════════════════════════════════════════════════════

absa_router = APIRouter()


@absa_router.get("/connect")
def absa_connect(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if not ABSA_CLIENT_ID:
        raise HTTPException(503, "ABSA integration not yet configured. Partnership credentials pending.")
    state = _new_state(current_user.company_id)
    params = {
        "response_type": "code",
        "client_id":     ABSA_CLIENT_ID,
        "redirect_uri":  ABSA_REDIRECT_URI,
        "scope":         ABSA_SCOPES,
        "state":         state,
    }
    return {"connect_url": f"{ABSA_AUTHORIZE}?{urlencode(params)}"}


@absa_router.get("/callback")
def absa_callback(
    code: str = Query(None), state: str = Query(None), error: str = Query(None),
    db: Session = Depends(get_db),
):
    redirect_base = f"{FRONTEND_URL}?absa=callback"
    if error or not code or not state:
        return RedirectResponse(f"{redirect_base}&error={error or 'missing_params'}")

    company_id = _pop_state(state)
    if not company_id:
        return RedirectResponse(f"{redirect_base}&error=invalid_state")

    try:
        resp = httpx.post(ABSA_AUTH_URL, data={
            "grant_type":    "authorization_code",
            "code":          code,
            "redirect_uri":  ABSA_REDIRECT_URI,
            "client_id":     ABSA_CLIENT_ID,
            "client_secret": ABSA_CLIENT_SECRET,
        }, timeout=30)
        resp.raise_for_status()
        tok = resp.json()
    except Exception as e:
        logger.error(f"ABSA token exchange failed: {e}")
        return RedirectResponse(f"{redirect_base}&error=token_exchange_failed")

    conn = db.query(AbsaConnection).filter(AbsaConnection.company_id == company_id).first()
    if not conn:
        conn = AbsaConnection(company_id=company_id)
        db.add(conn)

    conn.access_token  = encrypt_field(tok["access_token"])
    conn.refresh_token = encrypt_field(tok.get("refresh_token", ""))
    conn.token_expiry  = datetime.utcnow() + timedelta(seconds=tok.get("expires_in", 3600))
    conn.scopes        = tok.get("scope", "")
    conn.connected_at  = datetime.utcnow()
    db.commit()

    _absa_sync_accounts(company_id, db)
    return RedirectResponse(f"{redirect_base}&success=1")


def _absa_get_token(conn: AbsaConnection, db: Session) -> str:
    if conn.token_expiry and conn.token_expiry > datetime.utcnow() + timedelta(minutes=2):
        return decrypt_field(conn.access_token)
    # Refresh
    try:
        resp = httpx.post(ABSA_AUTH_URL, data={
            "grant_type":    "refresh_token",
            "refresh_token": decrypt_field(conn.refresh_token),
            "client_id":     ABSA_CLIENT_ID,
            "client_secret": ABSA_CLIENT_SECRET,
        }, timeout=30)
        resp.raise_for_status()
        tok = resp.json()
        conn.access_token  = encrypt_field(tok["access_token"])
        conn.refresh_token = encrypt_field(tok.get("refresh_token", decrypt_field(conn.refresh_token)))
        conn.token_expiry  = datetime.utcnow() + timedelta(seconds=tok.get("expires_in", 3600))
        db.commit()
        return tok["access_token"]
    except Exception as e:
        raise HTTPException(502, f"ABSA token refresh failed: {e}")


def _absa_sync_accounts(company_id: int, db: Session):
    conn = db.query(AbsaConnection).filter(AbsaConnection.company_id == company_id).first()
    if not conn:
        return
    token = _absa_get_token(conn, db)
    try:
        resp = httpx.get(ABSA_ACCOUNTS, headers={"Authorization": f"Bearer {token}"}, timeout=30)
        resp.raise_for_status()
        accounts = resp.json().get("accounts", [])
    except Exception as e:
        logger.error(f"ABSA accounts fetch failed: {e}")
        return

    for acct in accounts:
        acct_id = acct.get("accountId") or acct.get("id")
        existing = db.query(AbsaBankAccount).filter(AbsaBankAccount.absa_account_id == acct_id).first()
        if not existing:
            existing = AbsaBankAccount(company_id=company_id, absa_account_id=acct_id)
            db.add(existing)
        existing.account_name    = acct.get("accountName") or acct.get("name")
        existing.account_type    = acct.get("accountType") or acct.get("type")
        existing.current_balance = acct.get("currentBalance") or acct.get("balance", {}).get("current")
        existing.account_number  = encrypt_field(acct.get("accountNumber", "")) if acct.get("accountNumber") else None
        existing.last_synced     = datetime.utcnow()
    conn.last_synced = datetime.utcnow()
    db.commit()


def _absa_sync_transactions(company_id: int, db: Session) -> int:
    conn = db.query(AbsaConnection).filter(AbsaConnection.company_id == company_id).first()
    if not conn:
        return 0
    token = _absa_get_token(conn, db)
    accounts = db.query(AbsaBankAccount).filter(AbsaBankAccount.company_id == company_id, AbsaBankAccount.is_active == True).all()
    new_count = 0

    for acct in accounts:
        try:
            url = ABSA_TRANSACTIONS.format(account_id=acct.absa_account_id)
            resp = httpx.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
            resp.raise_for_status()
            txns = resp.json().get("transactions", [])
        except Exception as e:
            logger.error(f"ABSA transactions fetch failed for account {acct.absa_account_id}: {e}")
            continue

        for t in txns:
            txn_id = t.get("transactionId") or t.get("id")
            if db.query(AbsaTransaction).filter(AbsaTransaction.absa_txn_id == txn_id).first():
                continue
            amount = float(t.get("amount", 0))
            desc   = t.get("description") or t.get("transactionDescription", "")
            date_str = t.get("transactionDate") or t.get("valueDate", "")
            try:
                txn_date = datetime.fromisoformat(date_str[:10])
            except Exception:
                txn_date = datetime.utcnow()

            inv_id, exp_id, conf = _auto_match(amount, desc, company_id, db)
            txn = AbsaTransaction(
                company_id         = company_id,
                bank_account_id    = acct.id,
                absa_txn_id        = txn_id,
                amount             = amount,
                description        = desc,
                reference          = t.get("reference"),
                txn_date           = txn_date,
                running_balance    = t.get("runningBalance"),
                match_status       = "matched" if inv_id or exp_id else "unmatched",
                matched_invoice_id = inv_id,
                matched_expense_id = exp_id,
                match_confidence   = conf if (inv_id or exp_id) else None,
                matched_at         = datetime.utcnow() if (inv_id or exp_id) else None,
            )
            db.add(txn)
            new_count += 1
        acct.last_synced = datetime.utcnow()

    db.commit()
    return new_count


@absa_router.get("/status")
def absa_status(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    conn = db.query(AbsaConnection).filter(AbsaConnection.company_id == current_user.company_id).first()
    if not conn:
        return {"connected": False, "configured": bool(ABSA_CLIENT_ID)}
    accts = db.query(AbsaBankAccount).filter(AbsaBankAccount.company_id == current_user.company_id, AbsaBankAccount.is_active == True).count()
    return {
        "connected":    True,
        "configured":   bool(ABSA_CLIENT_ID),
        "connected_at": conn.connected_at.isoformat() if conn.connected_at else None,
        "last_synced":  conn.last_synced.isoformat() if conn.last_synced else None,
        "account_count": accts,
    }


@absa_router.post("/sync")
def absa_sync(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    cid = current_user.company_id
    conn = db.query(AbsaConnection).filter(AbsaConnection.company_id == cid).first()
    if not conn:
        raise HTTPException(400, "ABSA not connected")
    _absa_sync_accounts(cid, db)
    new_txns = _absa_sync_transactions(cid, db)
    accts = db.query(AbsaBankAccount).filter(AbsaBankAccount.company_id == cid, AbsaBankAccount.is_active == True).count()
    return {"accounts_synced": accts, "transactions_new": new_txns}


@absa_router.get("/accounts")
def absa_accounts(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    accts = db.query(AbsaBankAccount).filter(
        AbsaBankAccount.company_id == current_user.company_id,
        AbsaBankAccount.is_active == True,
    ).all()
    return [{"id": a.id, "name": a.account_name, "type": a.account_type, "balance": a.current_balance, "currency": a.currency, "last_synced": a.last_synced.isoformat() if a.last_synced else None} for a in accts]


@absa_router.get("/transactions")
def absa_transactions(
    match_status: str = Query("unmatched"),
    limit: int = Query(200),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    q = db.query(AbsaTransaction).filter(AbsaTransaction.company_id == current_user.company_id)
    if match_status != "all":
        q = q.filter(AbsaTransaction.match_status == match_status)
    txns = q.order_by(AbsaTransaction.txn_date.desc()).limit(limit).all()
    return [{"id": t.id, "amount": t.amount, "description": t.description, "reference": t.reference,
             "txn_date": t.txn_date.isoformat()[:10], "match_status": t.match_status,
             "matched_invoice_id": t.matched_invoice_id, "matched_expense_id": t.matched_expense_id,
             "match_confidence": t.match_confidence} for t in txns]


class MatchPayload(BaseModel):
    invoice_id: int | None = None
    expense_id: int | None = None


@absa_router.post("/transactions/{txn_id}/match")
def absa_match(txn_id: int, payload: MatchPayload, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    txn = db.query(AbsaTransaction).filter(AbsaTransaction.id == txn_id, AbsaTransaction.company_id == current_user.company_id).first()
    if not txn: raise HTTPException(404, "Transaction not found")
    txn.match_status = "matched"; txn.matched_invoice_id = payload.invoice_id; txn.matched_expense_id = payload.expense_id
    txn.match_confidence = 1.0; txn.matched_at = datetime.utcnow()
    db.commit()
    return {"status": "matched"}


@absa_router.post("/transactions/{txn_id}/exclude")
def absa_exclude(txn_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    txn = db.query(AbsaTransaction).filter(AbsaTransaction.id == txn_id, AbsaTransaction.company_id == current_user.company_id).first()
    if not txn: raise HTTPException(404, "Transaction not found")
    txn.match_status = "excluded"; db.commit(); return {"status": "excluded"}


@absa_router.post("/transactions/{txn_id}/unmatch")
def absa_unmatch(txn_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    txn = db.query(AbsaTransaction).filter(AbsaTransaction.id == txn_id, AbsaTransaction.company_id == current_user.company_id).first()
    if not txn: raise HTTPException(404, "Transaction not found")
    txn.match_status = "unmatched"; txn.matched_invoice_id = None; txn.matched_expense_id = None
    txn.match_confidence = None; txn.matched_at = None
    db.commit(); return {"status": "unmatched"}


@absa_router.delete("/disconnect")
def absa_disconnect(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    conn = db.query(AbsaConnection).filter(AbsaConnection.company_id == current_user.company_id).first()
    if conn: db.delete(conn); db.commit()
    return {"status": "disconnected"}


# ═══════════════════════════════════════════════════════════════════════════════
# NEDBANK ROUTER
# ═══════════════════════════════════════════════════════════════════════════════

nedbank_router = APIRouter()


@nedbank_router.get("/connect")
def nedbank_connect(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if not NEDBANK_CLIENT_ID:
        raise HTTPException(503, "Nedbank integration not yet configured. Partnership credentials pending.")
    state = _new_state(current_user.company_id)
    params = {
        "response_type": "code",
        "client_id":     NEDBANK_CLIENT_ID,
        "redirect_uri":  NEDBANK_REDIRECT_URI,
        "scope":         NEDBANK_SCOPES,
        "state":         state,
    }
    return {"connect_url": f"{NEDBANK_AUTHORIZE}?{urlencode(params)}"}


@nedbank_router.get("/callback")
def nedbank_callback(
    code: str = Query(None), state: str = Query(None), error: str = Query(None),
    db: Session = Depends(get_db),
):
    redirect_base = f"{FRONTEND_URL}?nedbank=callback"
    if error or not code or not state:
        return RedirectResponse(f"{redirect_base}&error={error or 'missing_params'}")

    company_id = _pop_state(state)
    if not company_id:
        return RedirectResponse(f"{redirect_base}&error=invalid_state")

    try:
        resp = httpx.post(NEDBANK_TOKEN_URL, data={
            "grant_type":    "authorization_code",
            "code":          code,
            "redirect_uri":  NEDBANK_REDIRECT_URI,
            "client_id":     NEDBANK_CLIENT_ID,
            "client_secret": NEDBANK_CLIENT_SECRET,
        }, timeout=30)
        resp.raise_for_status()
        tok = resp.json()
    except Exception as e:
        logger.error(f"Nedbank token exchange failed: {e}")
        return RedirectResponse(f"{redirect_base}&error=token_exchange_failed")

    conn = db.query(NedbankConnection).filter(NedbankConnection.company_id == company_id).first()
    if not conn:
        conn = NedbankConnection(company_id=company_id)
        db.add(conn)

    conn.access_token  = encrypt_field(tok["access_token"])
    conn.refresh_token = encrypt_field(tok.get("refresh_token", ""))
    conn.token_expiry  = datetime.utcnow() + timedelta(seconds=tok.get("expires_in", 3600))
    conn.scopes        = tok.get("scope", "")
    conn.connected_at  = datetime.utcnow()
    db.commit()

    _nedbank_sync_accounts(company_id, db)
    return RedirectResponse(f"{redirect_base}&success=1")


def _nedbank_get_token(conn: NedbankConnection, db: Session) -> str:
    if conn.token_expiry and conn.token_expiry > datetime.utcnow() + timedelta(minutes=2):
        return decrypt_field(conn.access_token)
    try:
        resp = httpx.post(NEDBANK_TOKEN_URL, data={
            "grant_type":    "refresh_token",
            "refresh_token": decrypt_field(conn.refresh_token),
            "client_id":     NEDBANK_CLIENT_ID,
            "client_secret": NEDBANK_CLIENT_SECRET,
        }, timeout=30)
        resp.raise_for_status()
        tok = resp.json()
        conn.access_token  = encrypt_field(tok["access_token"])
        conn.refresh_token = encrypt_field(tok.get("refresh_token", decrypt_field(conn.refresh_token)))
        conn.token_expiry  = datetime.utcnow() + timedelta(seconds=tok.get("expires_in", 3600))
        db.commit()
        return tok["access_token"]
    except Exception as e:
        raise HTTPException(502, f"Nedbank token refresh failed: {e}")


def _nedbank_sync_accounts(company_id: int, db: Session):
    conn = db.query(NedbankConnection).filter(NedbankConnection.company_id == company_id).first()
    if not conn: return
    token = _nedbank_get_token(conn, db)
    try:
        resp = httpx.get(NEDBANK_ACCOUNTS, headers={"Authorization": f"Bearer {token}"}, timeout=30)
        resp.raise_for_status()
        accounts = resp.json().get("accounts", [])
    except Exception as e:
        logger.error(f"Nedbank accounts fetch failed: {e}"); return

    for acct in accounts:
        acct_id = acct.get("accountId") or acct.get("id")
        existing = db.query(NedbankBankAccount).filter(NedbankBankAccount.nedbank_account_id == acct_id).first()
        if not existing:
            existing = NedbankBankAccount(company_id=company_id, nedbank_account_id=acct_id)
            db.add(existing)
        existing.account_name    = acct.get("accountName") or acct.get("name")
        existing.account_type    = acct.get("accountType") or acct.get("type")
        existing.current_balance = acct.get("currentBalance") or acct.get("balance", {}).get("current")
        existing.account_number  = encrypt_field(acct.get("accountNumber", "")) if acct.get("accountNumber") else None
        existing.last_synced     = datetime.utcnow()
    conn.last_synced = datetime.utcnow()
    db.commit()


def _nedbank_sync_transactions(company_id: int, db: Session) -> int:
    conn = db.query(NedbankConnection).filter(NedbankConnection.company_id == company_id).first()
    if not conn: return 0
    token = _nedbank_get_token(conn, db)
    accounts = db.query(NedbankBankAccount).filter(NedbankBankAccount.company_id == company_id, NedbankBankAccount.is_active == True).all()
    new_count = 0

    for acct in accounts:
        try:
            url = NEDBANK_TXNS.format(account_id=acct.nedbank_account_id)
            resp = httpx.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
            resp.raise_for_status()
            txns = resp.json().get("transactions", [])
        except Exception as e:
            logger.error(f"Nedbank transactions fetch failed for account {acct.nedbank_account_id}: {e}"); continue

        for t in txns:
            txn_id = t.get("transactionId") or t.get("id")
            if db.query(NedbankTransaction).filter(NedbankTransaction.nedbank_txn_id == txn_id).first():
                continue
            amount = float(t.get("amount", 0))
            desc   = t.get("description") or t.get("transactionDescription", "")
            date_str = t.get("transactionDate") or t.get("postingDate", "")
            try:
                txn_date = datetime.fromisoformat(date_str[:10])
            except Exception:
                txn_date = datetime.utcnow()

            inv_id, exp_id, conf = _auto_match(amount, desc, company_id, db)
            txn = NedbankTransaction(
                company_id         = company_id,
                bank_account_id    = acct.id,
                nedbank_txn_id     = txn_id,
                amount             = amount,
                description        = desc,
                reference          = t.get("reference"),
                txn_date           = txn_date,
                running_balance    = t.get("runningBalance"),
                match_status       = "matched" if inv_id or exp_id else "unmatched",
                matched_invoice_id = inv_id,
                matched_expense_id = exp_id,
                match_confidence   = conf if (inv_id or exp_id) else None,
                matched_at         = datetime.utcnow() if (inv_id or exp_id) else None,
            )
            db.add(txn)
            new_count += 1
        acct.last_synced = datetime.utcnow()

    db.commit()
    return new_count


@nedbank_router.get("/status")
def nedbank_status(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    conn = db.query(NedbankConnection).filter(NedbankConnection.company_id == current_user.company_id).first()
    if not conn:
        return {"connected": False, "configured": bool(NEDBANK_CLIENT_ID)}
    accts = db.query(NedbankBankAccount).filter(NedbankBankAccount.company_id == current_user.company_id, NedbankBankAccount.is_active == True).count()
    return {
        "connected":     True,
        "configured":    bool(NEDBANK_CLIENT_ID),
        "connected_at":  conn.connected_at.isoformat() if conn.connected_at else None,
        "last_synced":   conn.last_synced.isoformat() if conn.last_synced else None,
        "account_count": accts,
    }


@nedbank_router.post("/sync")
def nedbank_sync(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    cid = current_user.company_id
    conn = db.query(NedbankConnection).filter(NedbankConnection.company_id == cid).first()
    if not conn: raise HTTPException(400, "Nedbank not connected")
    _nedbank_sync_accounts(cid, db)
    new_txns = _nedbank_sync_transactions(cid, db)
    accts = db.query(NedbankBankAccount).filter(NedbankBankAccount.company_id == cid, NedbankBankAccount.is_active == True).count()
    return {"accounts_synced": accts, "transactions_new": new_txns}


@nedbank_router.get("/accounts")
def nedbank_accounts(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    accts = db.query(NedbankBankAccount).filter(
        NedbankBankAccount.company_id == current_user.company_id,
        NedbankBankAccount.is_active == True,
    ).all()
    return [{"id": a.id, "name": a.account_name, "type": a.account_type, "balance": a.current_balance, "currency": a.currency, "last_synced": a.last_synced.isoformat() if a.last_synced else None} for a in accts]


@nedbank_router.get("/transactions")
def nedbank_transactions(
    match_status: str = Query("unmatched"),
    limit: int = Query(200),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    q = db.query(NedbankTransaction).filter(NedbankTransaction.company_id == current_user.company_id)
    if match_status != "all":
        q = q.filter(NedbankTransaction.match_status == match_status)
    txns = q.order_by(NedbankTransaction.txn_date.desc()).limit(limit).all()
    return [{"id": t.id, "amount": t.amount, "description": t.description, "reference": t.reference,
             "txn_date": t.txn_date.isoformat()[:10], "match_status": t.match_status,
             "matched_invoice_id": t.matched_invoice_id, "matched_expense_id": t.matched_expense_id,
             "match_confidence": t.match_confidence} for t in txns]


@nedbank_router.post("/transactions/{txn_id}/match")
def nedbank_match(txn_id: int, payload: MatchPayload, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    txn = db.query(NedbankTransaction).filter(NedbankTransaction.id == txn_id, NedbankTransaction.company_id == current_user.company_id).first()
    if not txn: raise HTTPException(404, "Transaction not found")
    txn.match_status = "matched"; txn.matched_invoice_id = payload.invoice_id; txn.matched_expense_id = payload.expense_id
    txn.match_confidence = 1.0; txn.matched_at = datetime.utcnow()
    db.commit(); return {"status": "matched"}


@nedbank_router.post("/transactions/{txn_id}/exclude")
def nedbank_exclude(txn_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    txn = db.query(NedbankTransaction).filter(NedbankTransaction.id == txn_id, NedbankTransaction.company_id == current_user.company_id).first()
    if not txn: raise HTTPException(404, "Transaction not found")
    txn.match_status = "excluded"; db.commit(); return {"status": "excluded"}


@nedbank_router.post("/transactions/{txn_id}/unmatch")
def nedbank_unmatch(txn_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    txn = db.query(NedbankTransaction).filter(NedbankTransaction.id == txn_id, NedbankTransaction.company_id == current_user.company_id).first()
    if not txn: raise HTTPException(404, "Transaction not found")
    txn.match_status = "unmatched"; txn.matched_invoice_id = None; txn.matched_expense_id = None
    txn.match_confidence = None; txn.matched_at = None
    db.commit(); return {"status": "unmatched"}


@nedbank_router.delete("/disconnect")
def nedbank_disconnect(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    conn = db.query(NedbankConnection).filter(NedbankConnection.company_id == current_user.company_id).first()
    if conn: db.delete(conn); db.commit()
    return {"status": "disconnected"}
