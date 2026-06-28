"""
ZuZan — Stitch Money Bank Feed Integration
==========================================
Endpoints mounted at /banking/stitch

OAuth flow (PKCE):
  1. GET  /banking/stitch/connect        → returns Stitch auth URL (requires JWT)
  2. GET  /banking/stitch/callback       → handles Stitch redirect, exchanges code for tokens
  3. GET  /banking/stitch/status         → is this company connected?
  4. POST /banking/stitch/sync           → pull latest transactions from Stitch
  5. GET  /banking/stitch/accounts       → list linked bank accounts
  6. GET  /banking/stitch/transactions   → paginated transaction feed with match status
  7. POST /banking/stitch/transactions/{id}/match    → manually match a transaction
  8. POST /banking/stitch/transactions/{id}/exclude  → exclude a transaction
  9. POST /banking/stitch/transactions/{id}/unmatch  → reset to unmatched
  10. DELETE /banking/stitch/disconnect  → remove connection (keeps transaction history)

Required env vars:
  STITCH_CLIENT_ID      — from Stitch developer portal
  STITCH_CLIENT_SECRET  — from Stitch developer portal
  STITCH_REDIRECT_URI   — e.g. https://zuzan-backend.onrender.com/banking/stitch/callback
  FRONTEND_URL          — e.g. https://zuzan-app.onrender.com
  FIELD_ENCRYPTION_KEY  — Fernet key (shared with crypto.py)
"""

import os, hashlib, base64, secrets, logging
from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import (
    get_db, StitchConnection, StitchBankAccount, StitchTransaction,
    Invoice, Expense, InvoiceStatus,
)
from auth import get_current_user, require_role
from crypto import encrypt_field, decrypt_field

logger = logging.getLogger("zuzan.stitch")
stitch_router = APIRouter()

# ── Config ────────────────────────────────────────────────────────────────────
STITCH_CLIENT_ID     = os.environ.get("STITCH_CLIENT_ID", "")
STITCH_CLIENT_SECRET = os.environ.get("STITCH_CLIENT_SECRET", "")
STITCH_REDIRECT_URI  = os.environ.get(
    "STITCH_REDIRECT_URI",
    "https://zuzan-backend.onrender.com/banking/stitch/callback",
)
FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://zuzan-app.onrender.com")

STITCH_SCOPES        = "openid offline_access transactions accounts balances"
STITCH_AUTHORIZE_URL = "https://secure.stitch.money/connect/authorize"
STITCH_TOKEN_URL     = "https://secure.stitch.money/connect/token"
STITCH_GRAPHQL_URL   = "https://api.stitch.money/graphql"

# In-memory PKCE state store: state → {code_verifier, company_id, nonce, expires}
# Works fine on paid/always-on Render. For free tier, states survive ~seconds of
# inactivity; if the server sleeps between redirect and callback, user retries.
_auth_states: dict = {}


# ── PKCE Helpers ─────────────────────────────────────────────────────────────

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _pkce() -> tuple[str, str, str, str]:
    """Return (code_verifier, code_challenge, state, nonce)."""
    verifier  = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    state     = _b64url(secrets.token_bytes(32))
    nonce     = _b64url(secrets.token_bytes(32))
    return verifier, challenge, state, nonce


# ── Token Helpers ─────────────────────────────────────────────────────────────

async def _graphql(access_token: str, query: str, variables: dict | None = None) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            STITCH_GRAPHQL_URL,
            json={"query": query, "variables": variables or {}},
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def _refresh_token(conn: StitchConnection, db: Session) -> str:
    """Exchange refresh token for a new access token; update DB. Returns raw access_token."""
    rt = decrypt_field(conn.refresh_token)
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            STITCH_TOKEN_URL,
            data={
                "grant_type":    "refresh_token",
                "client_id":     STITCH_CLIENT_ID,
                "client_secret": STITCH_CLIENT_SECRET,
                "refresh_token": rt,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if not resp.is_success:
            raise HTTPException(status_code=502, detail=f"Stitch token refresh failed: {resp.text[:200]}")
        tokens = resp.json()

    conn.access_token  = encrypt_field(tokens["access_token"])
    if "refresh_token" in tokens:
        conn.refresh_token = encrypt_field(tokens["refresh_token"])
    conn.token_expiry = datetime.utcnow() + timedelta(seconds=tokens.get("expires_in", 900) - 60)
    db.commit()
    return tokens["access_token"]


async def _valid_token(conn: StitchConnection, db: Session) -> str:
    """Return a valid (non-expired) access token, refreshing if needed."""
    if datetime.utcnow() >= conn.token_expiry:
        return await _refresh_token(conn, db)
    return decrypt_field(conn.access_token)


# ── OAuth Endpoints ───────────────────────────────────────────────────────────

@stitch_router.get("/connect")
async def connect(current_user=Depends(get_current_user)):
    """Generate Stitch OAuth URL for the current company. Frontend redirects the user there."""
    if not STITCH_CLIENT_ID:
        raise HTTPException(
            status_code=503,
            detail="Stitch is not configured. Add STITCH_CLIENT_ID and STITCH_CLIENT_SECRET to Render environment variables.",
        )
    verifier, challenge, state, nonce = _pkce()
    _auth_states[state] = {
        "code_verifier": verifier,
        "company_id":    current_user.company_id,
        "nonce":         nonce,
        "expires":       datetime.utcnow() + timedelta(minutes=15),
    }
    params = {
        "client_id":             STITCH_CLIENT_ID,
        "scope":                 STITCH_SCOPES,
        "response_type":         "code",
        "redirect_uri":          STITCH_REDIRECT_URI,
        "nonce":                 nonce,
        "state":                 state,
        "code_challenge":        challenge,
        "code_challenge_method": "S256",
    }
    return {"auth_url": f"{STITCH_AUTHORIZE_URL}?{urlencode(params)}"}


@stitch_router.get("/callback")
async def callback(
    code:  str   = Query(...),
    state: str   = Query(...),
    db:    Session = Depends(get_db),
):
    """OAuth callback from Stitch — exchanges auth code for tokens, then redirects to frontend."""
    state_data = _auth_states.pop(state, None)
    if not state_data:
        return RedirectResponse(url=f"{FRONTEND_URL}?stitch=error&reason=invalid_state#bankfeeds")
    if datetime.utcnow() > state_data["expires"]:
        return RedirectResponse(url=f"{FRONTEND_URL}?stitch=error&reason=expired#bankfeeds")

    company_id    = state_data["company_id"]
    code_verifier = state_data["code_verifier"]

    # Exchange code for tokens
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            STITCH_TOKEN_URL,
            data={
                "grant_type":    "authorization_code",
                "client_id":     STITCH_CLIENT_ID,
                "client_secret": STITCH_CLIENT_SECRET,
                "code":          code,
                "redirect_uri":  STITCH_REDIRECT_URI,
                "code_verifier": code_verifier,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if not resp.is_success:
            logger.error(f"Stitch token exchange failed: {resp.text}")
            return RedirectResponse(url=f"{FRONTEND_URL}?stitch=error&reason=token_exchange#bankfeeds")
        tokens = resp.json()

    access_token  = tokens["access_token"]
    refresh_token = tokens.get("refresh_token", "")
    expires_in    = tokens.get("expires_in", 900)

    # Upsert connection
    conn = db.query(StitchConnection).filter(StitchConnection.company_id == company_id).first()
    if not conn:
        conn = StitchConnection(company_id=company_id)
        db.add(conn)
    conn.access_token  = encrypt_field(access_token)
    conn.refresh_token = encrypt_field(refresh_token)
    conn.token_expiry  = datetime.utcnow() + timedelta(seconds=expires_in - 60)
    conn.scopes        = tokens.get("scope", STITCH_SCOPES)
    conn.connected_at  = datetime.utcnow()
    db.commit()
    db.refresh(conn)

    # Initial sync (non-fatal)
    try:
        await _sync_accounts(conn, db)
        await _sync_transactions(conn, db)
        conn.last_synced = datetime.utcnow()
        db.commit()
    except Exception as e:
        logger.warning(f"Initial Stitch sync failed (non-fatal): {e}")

    return RedirectResponse(url=f"{FRONTEND_URL}?stitch=connected#bankfeeds")


# ── Data Endpoints ────────────────────────────────────────────────────────────

@stitch_router.get("/status")
async def status(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    conn = db.query(StitchConnection).filter(
        StitchConnection.company_id == current_user.company_id
    ).first()
    if not conn:
        return {"connected": False}
    accts = db.query(StitchBankAccount).filter(
        StitchBankAccount.company_id == current_user.company_id,
        StitchBankAccount.is_active == True,
    ).count()
    return {
        "connected":      True,
        "connected_at":   conn.connected_at.isoformat() if conn.connected_at else None,
        "last_synced":    conn.last_synced.isoformat()  if conn.last_synced  else None,
        "accounts_count": accts,
    }


@stitch_router.get("/accounts")
async def list_accounts(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    accts = db.query(StitchBankAccount).filter(
        StitchBankAccount.company_id == current_user.company_id,
        StitchBankAccount.is_active  == True,
    ).all()
    return [{
        "id":               a.id,
        "stitch_id":        a.stitch_account_id,
        "bank_id":          a.bank_id,
        "account_name":     a.account_name,
        "account_type":     a.account_type,
        "account_number":   decrypt_field(a.account_number) if a.account_number else None,
        "current_balance":  a.current_balance,
        "available_balance":a.available_balance,
        "currency":         a.currency,
        "last_synced":      a.last_synced.isoformat() if a.last_synced else None,
    } for a in accts]


@stitch_router.post("/sync")
async def sync(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    conn = db.query(StitchConnection).filter(
        StitchConnection.company_id == current_user.company_id
    ).first()
    if not conn:
        raise HTTPException(status_code=404, detail="No Stitch connection. Connect your bank first.")
    accts_synced = await _sync_accounts(conn, db)
    txns_new     = await _sync_transactions(conn, db)
    conn.last_synced = datetime.utcnow()
    db.commit()
    return {
        "accounts_synced":     accts_synced,
        "transactions_new":    txns_new,
        "last_synced":         conn.last_synced.isoformat(),
    }


@stitch_router.get("/transactions")
async def list_transactions(
    match_status: str   = Query(None),   # unmatched | matched | excluded
    account_id:   int   = Query(None),
    limit:        int   = Query(200),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(StitchTransaction).filter(
        StitchTransaction.company_id == current_user.company_id
    )
    if match_status:
        q = q.filter(StitchTransaction.match_status == match_status)
    if account_id:
        q = q.filter(StitchTransaction.bank_account_id == account_id)
    txns = q.order_by(StitchTransaction.txn_date.desc()).limit(limit).all()

    # Look up matched invoice/expense names for display
    inv_map = {}
    exp_map = {}
    inv_ids = [t.matched_invoice_id for t in txns if t.matched_invoice_id]
    exp_ids = [t.matched_expense_id for t in txns if t.matched_expense_id]
    if inv_ids:
        for inv in db.query(Invoice).filter(Invoice.id.in_(inv_ids)).all():
            inv_map[inv.id] = f"INV #{inv.invoice_number} — {inv.client_name}"
    if exp_ids:
        for exp in db.query(Expense).filter(Expense.id.in_(exp_ids)).all():
            exp_map[exp.id] = f"{exp.vendor} ({exp.category})"

    return [{
        "id":                 t.id,
        "bank_account_id":    t.bank_account_id,
        "amount":             t.amount,
        "description":        t.description,
        "reference":          t.reference,
        "date":               t.txn_date.isoformat()[:10],
        "running_balance":    t.running_balance,
        "match_status":       t.match_status,
        "matched_invoice_id": t.matched_invoice_id,
        "matched_expense_id": t.matched_expense_id,
        "matched_label":      inv_map.get(t.matched_invoice_id) or exp_map.get(t.matched_expense_id),
        "match_confidence":   t.match_confidence,
    } for t in txns]


class MatchBody(BaseModel):
    invoice_id: int | None = None
    expense_id: int | None = None


@stitch_router.post("/transactions/{txn_id}/match")
async def match_txn(txn_id: int, body: MatchBody, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    txn = _get_txn(txn_id, current_user.company_id, db)
    txn.match_status       = "matched"
    txn.matched_invoice_id = body.invoice_id
    txn.matched_expense_id = body.expense_id
    txn.match_confidence   = 1.0
    txn.matched_at         = datetime.utcnow()
    db.commit()
    return {"status": "matched"}


@stitch_router.post("/transactions/{txn_id}/exclude")
async def exclude_txn(txn_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    txn = _get_txn(txn_id, current_user.company_id, db)
    txn.match_status = "excluded"
    txn.matched_at   = datetime.utcnow()
    db.commit()
    return {"status": "excluded"}


@stitch_router.post("/transactions/{txn_id}/unmatch")
async def unmatch_txn(txn_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    txn = _get_txn(txn_id, current_user.company_id, db)
    txn.match_status       = "unmatched"
    txn.matched_invoice_id = None
    txn.matched_expense_id = None
    txn.match_confidence   = None
    txn.matched_at         = None
    db.commit()
    return {"status": "unmatched"}


@stitch_router.delete("/disconnect")
async def disconnect(current_user=Depends(require_role("owner", "admin")), db: Session = Depends(get_db)):
    conn = db.query(StitchConnection).filter(
        StitchConnection.company_id == current_user.company_id
    ).first()
    if conn:
        db.delete(conn)
    # Mark accounts inactive (keep transaction history)
    for a in db.query(StitchBankAccount).filter(
        StitchBankAccount.company_id == current_user.company_id
    ).all():
        a.is_active = False
    db.commit()
    return {"status": "disconnected"}


# ── Internal Sync Functions ───────────────────────────────────────────────────

async def _sync_accounts(conn: StitchConnection, db: Session) -> int:
    access_token = await _valid_token(conn, db)
    result = await _graphql(access_token, """
        query GetAccounts {
            user {
                bankAccounts {
                    id
                    accountNumber
                    accountType
                    bankId
                    name
                    currentBalance
                    availableBalance
                }
            }
        }
    """)
    raw = result.get("data", {}).get("user", {}).get("bankAccounts", [])
    count = 0
    for ra in raw:
        acct = db.query(StitchBankAccount).filter(
            StitchBankAccount.stitch_account_id == ra["id"]
        ).first()
        if not acct:
            acct = StitchBankAccount(
                company_id=conn.company_id,
                stitch_account_id=ra["id"],
            )
            db.add(acct)
        acct.bank_id           = ra.get("bankId")
        acct.account_number    = encrypt_field(ra.get("accountNumber"))
        acct.account_name      = ra.get("name")
        acct.account_type      = ra.get("accountType")
        acct.current_balance   = ra.get("currentBalance")
        acct.available_balance = ra.get("availableBalance")
        acct.currency          = "ZAR"
        acct.last_synced       = datetime.utcnow()
        acct.is_active         = True
        count += 1
    db.commit()
    return count


async def _sync_transactions(conn: StitchConnection, db: Session) -> int:
    """Fetch recent transactions for all accounts and auto-match new ones."""
    access_token = await _valid_token(conn, db)
    accounts = db.query(StitchBankAccount).filter(
        StitchBankAccount.company_id == conn.company_id,
        StitchBankAccount.is_active  == True,
    ).all()

    total_new = 0

    for account in accounts:
        cursor = None
        for _page in range(6):   # up to 6 × 50 = 300 transactions per account
            variables: dict = {"accountId": account.stitch_account_id, "first": 50}
            if cursor:
                variables["after"] = cursor

            result = await _graphql(access_token, """
                query TxnsByAccount($accountId: ID!, $first: UInt, $after: Cursor) {
                    node(id: $accountId) {
                        ... on BankAccount {
                            transactions(first: $first, after: $after) {
                                pageInfo { hasNextPage endCursor }
                                edges {
                                    node {
                                        id
                                        amount
                                        reference
                                        description
                                        date
                                        runningBalance
                                    }
                                }
                            }
                        }
                    }
                }
            """, variables)

            node      = result.get("data", {}).get("node", {})
            txn_data  = node.get("transactions", {})
            edges     = txn_data.get("edges", [])
            page_info = txn_data.get("pageInfo", {})

            for edge in edges:
                t = edge["node"]
                if db.query(StitchTransaction).filter(
                    StitchTransaction.stitch_txn_id == t["id"]
                ).first():
                    continue   # already stored

                raw_date = t.get("date", "")
                try:
                    txn_date = datetime.fromisoformat(raw_date.replace("Z", "+00:00")).replace(tzinfo=None)
                except Exception:
                    txn_date = datetime.utcnow()

                new_txn = StitchTransaction(
                    company_id      = conn.company_id,
                    bank_account_id = account.id,
                    stitch_txn_id   = t["id"],
                    amount          = float(t.get("amount", 0)),
                    description     = t.get("description"),
                    reference       = t.get("reference"),
                    txn_date        = txn_date,
                    running_balance = t.get("runningBalance"),
                    match_status    = "unmatched",
                )
                db.add(new_txn)
                db.flush()
                _auto_match(new_txn, conn.company_id, db)
                total_new += 1

            db.commit()

            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")

        account.last_synced = datetime.utcnow()

    db.commit()
    return total_new


def _auto_match(txn: StitchTransaction, company_id: int, db: Session):
    """Best-effort auto-match: credit→invoice, debit→expense."""
    amount = abs(txn.amount)
    if amount < 1:
        return

    if txn.amount > 0:
        # Credit: try to match an outstanding invoice by amount ±1%
        open_invoices = db.query(Invoice).filter(
            Invoice.company_id == company_id,
            Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue]),
        ).all()
        best_conf, best_inv = 0.0, None
        for inv in open_invoices:
            inv_amt = inv.paid_amount_zar or inv.total_amount
            if inv_amt <= 0:
                continue
            pct_diff = abs(amount - inv_amt) / inv_amt
            if pct_diff > 0.01:
                continue
            # Date proximity bonus
            ref_date = inv.due_date or inv.issue_date
            days_diff = abs((txn.txn_date - ref_date).days) if ref_date else 999
            conf = 0.95 if days_diff <= 7 else (0.80 if days_diff <= 30 else 0.65)
            if conf > best_conf:
                best_conf, best_inv = conf, inv
        if best_inv:
            txn.match_status       = "matched"
            txn.matched_invoice_id = best_inv.id
            txn.match_confidence   = best_conf
            txn.matched_at         = datetime.utcnow()

    else:
        # Debit: try to match an expense by amount ±1% within 7 days
        expenses = db.query(Expense).filter(Expense.company_id == company_id).all()
        best_conf, best_exp = 0.0, None
        for exp in expenses:
            if exp.amount <= 0:
                continue
            pct_diff = abs(amount - exp.amount) / exp.amount
            if pct_diff > 0.01:
                continue
            days_diff = abs((txn.txn_date - (exp.expense_date or datetime.utcnow())).days)
            conf = 0.90 if days_diff <= 3 else (0.75 if days_diff <= 7 else 0.55)
            if conf > best_conf:
                best_conf, best_exp = conf, exp
        if best_exp and best_conf >= 0.55:
            txn.match_status       = "matched"
            txn.matched_expense_id = best_exp.id
            txn.match_confidence   = best_conf
            txn.matched_at         = datetime.utcnow()


# ── Helper ────────────────────────────────────────────────────────────────────

def _get_txn(txn_id: int, company_id: int, db: Session) -> StitchTransaction:
    txn = db.query(StitchTransaction).filter(
        StitchTransaction.id         == txn_id,
        StitchTransaction.company_id == company_id,
    ).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    return txn
