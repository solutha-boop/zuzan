"""
ZuZan Client Portal — public invoice view + PayFast payment + IPN webhook
Routes are mounted at /portal (no auth required for GET/pay/notify)
"""

from fastapi import APIRouter, HTTPException, Request, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from datetime import datetime
import os, hashlib, uuid, logging

from database import get_db, Invoice, InvoiceStatus, Company, SessionLocal

logger = logging.getLogger("zuzan.portal")

portal_router = APIRouter()

# ── PayFast config (shared with payroll.py subscription payments) ─────────────
PAYFAST_MERCHANT_ID  = os.environ.get("PAYFAST_MERCHANT_ID",  "10000100")
PAYFAST_MERCHANT_KEY = os.environ.get("PAYFAST_MERCHANT_KEY", "46f0cd694581a")
PAYFAST_PASSPHRASE   = os.environ.get("PAYFAST_PASSPHRASE",   "")
PAYFAST_SANDBOX      = os.environ.get("PAYFAST_SANDBOX", "true").lower() == "true"
PAYFAST_URL          = "https://sandbox.payfast.co.za/eng/process" if PAYFAST_SANDBOX else "https://www.payfast.co.za/eng/process"
BACKEND_URL          = os.environ.get("BACKEND_URL",   "https://zuzan-backend.onrender.com")
FRONTEND_URL         = os.environ.get("FRONTEND_URL",  "https://zuzan-app.onrender.com")


def _pf_signature(data: dict, passphrase: str = "") -> str:
    params = {k: v for k, v in data.items() if v != ""}
    param_string = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    if passphrase:
        param_string += f"&passphrase={passphrase}"
    return hashlib.md5(param_string.encode()).hexdigest()


def _get_invoice_by_token(token: str, db: Session) -> Invoice:
    inv = db.query(Invoice).filter(Invoice.portal_token == token).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    return inv


# ── GET /portal/invoice/{token} — public ─────────────────────────────────────
@portal_router.get("/invoice/{token}")
async def get_portal_invoice(token: str, db: Session = Depends(get_db)):
    """Return safe public fields for the invoice. No auth required."""
    inv = _get_invoice_by_token(token, db)
    company = db.query(Company).filter(Company.id == inv.company_id).first()

    # ZAR equivalent for foreign-currency invoices
    zar_total = round(
        inv.paid_amount_zar if inv.status == InvoiceStatus.paid and inv.paid_amount_zar
        else (inv.total_amount or 0) * (inv.exchange_rate or 1),
        2
    )

    return {
        "token":          token,
        "invoice_number": inv.invoice_number,
        "client_name":    inv.client_name,
        "description":    inv.description or "",
        "currency":       inv.currency or "ZAR",
        "amount":         inv.amount,          # excl. VAT
        "vat_amount":     inv.vat_amount or 0,
        "total_amount":   inv.total_amount,    # incl. VAT, original currency
        "zar_total":      zar_total,           # always ZAR — used for PayFast
        "exchange_rate":  inv.exchange_rate or 1,
        "issue_date":     inv.issue_date.isoformat() if inv.issue_date else None,
        "due_date":       inv.due_date.isoformat()   if inv.due_date   else None,
        "status":         inv.status.value,
        "paid_date":      inv.paid_date.isoformat()  if inv.paid_date  else None,
        "notes":          inv.notes or "",
        "company_name":   company.name        if company else "",
        "company_email":  company.email       if company else "",
        "company_phone":  company.phone       if company else "",
        "company_address":company.address     if company else "",
        "company_logo":   company.logo_url    if company else "",
        "vat_number":     company.vat_number  if company else "",
    }


# ── POST /portal/invoice/{token}/pay — public ────────────────────────────────
@portal_router.post("/invoice/{token}/pay")
async def initiate_portal_payment(token: str, db: Session = Depends(get_db)):
    """Build PayFast redirect params for invoice payment."""
    inv = _get_invoice_by_token(token, db)

    if inv.status == InvoiceStatus.paid:
        raise HTTPException(status_code=400, detail="This invoice has already been paid.")
    if inv.status == InvoiceStatus.draft:
        raise HTTPException(status_code=400, detail="This invoice is still a draft.")

    company = db.query(Company).filter(Company.id == inv.company_id).first()

    # Always charge in ZAR
    zar_total = round(
        (inv.total_amount or 0) * (inv.exchange_rate or 1), 2
    )
    if zar_total <= 0:
        raise HTTPException(status_code=400, detail="Invoice amount must be greater than zero.")

    pf_data = {
        "merchant_id":   PAYFAST_MERCHANT_ID,
        "merchant_key":  PAYFAST_MERCHANT_KEY,
        "return_url":    f"{FRONTEND_URL}/portal/{token}?paid=1",
        "cancel_url":    f"{FRONTEND_URL}/portal/{token}?cancelled=1",
        "notify_url":    f"{BACKEND_URL}/portal/notify",
        "name_first":    inv.client_name.split()[0][:50] if inv.client_name else "Client",
        "name_last":     " ".join(inv.client_name.split()[1:])[:50] if inv.client_name and len(inv.client_name.split()) > 1 else "-",
        "email_address": "",   # client email not stored on invoice
        "m_payment_id":  token,           # unique — used to find invoice on IPN
        "amount":        f"{zar_total:.2f}",
        "item_name":     f"Invoice {inv.invoice_number}"[:100],
        "item_description": (inv.description or "")[:255],
        "custom_str1":   str(inv.id),
        "custom_str2":   str(inv.company_id),
    }
    pf_data["signature"] = _pf_signature(pf_data, PAYFAST_PASSPHRASE)

    return {
        "payfast_url":  PAYFAST_URL,
        "payfast_data": pf_data,
        "zar_total":    zar_total,
        "sandbox":      PAYFAST_SANDBOX,
    }


# ── POST /portal/notify — PayFast IPN ────────────────────────────────────────
@portal_router.post("/notify")
async def portal_payfast_notify(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    PayFast IPN handler for invoice payments.
    PayFast posts to this URL after a successful payment.
    m_payment_id == portal_token of the invoice.
    """
    try:
        form  = await request.form()
        data  = dict(form)
    except Exception:
        return JSONResponse(content={"status": "error", "detail": "Bad request"}, status_code=400)

    token  = data.get("m_payment_id", "")
    status = data.get("payment_status", "")

    if not token:
        return JSONResponse(content={"status": "error", "detail": "Missing m_payment_id"}, status_code=400)

    # Signature verification (skip in sandbox mode for easier testing)
    if not PAYFAST_SANDBOX:
        sig_data     = {k: v for k, v in data.items() if k != "signature"}
        expected_sig = _pf_signature(sig_data, PAYFAST_PASSPHRASE)
        received_sig = data.get("signature", "")
        if received_sig != expected_sig:
            logger.warning(f"Portal IPN: signature mismatch for token {token[:8]}...")
            return JSONResponse(content={"status": "error", "detail": "Invalid signature"}, status_code=400)

    if status != "COMPLETE":
        logger.info(f"Portal IPN: ignoring status={status} for token {token[:8]}...")
        return JSONResponse(content={"status": "ok", "detail": f"Status {status} — no action"})

    # Find invoice
    inv = db.query(Invoice).filter(Invoice.portal_token == token).first()
    if not inv:
        logger.error(f"Portal IPN: invoice not found for token {token[:8]}...")
        return JSONResponse(content={"status": "error", "detail": "Invoice not found"}, status_code=404)

    if inv.status == InvoiceStatus.paid:
        logger.info(f"Portal IPN: invoice {inv.invoice_number} already paid — ignoring duplicate")
        return JSONResponse(content={"status": "ok", "detail": "Already paid"})

    # Mark paid
    amount_gross = float(data.get("amount_gross", 0) or 0)
    inv.status          = InvoiceStatus.paid
    inv.paid_date       = datetime.utcnow()
    inv.paid_amount_zar = amount_gross if amount_gross > 0 else round(
        (inv.total_amount or 0) * (inv.exchange_rate or 1), 2
    )
    db.commit()

    # Post journal entry for payment received (non-fatal)
    try:
        import journal as journal_engine
        db2 = SessionLocal()
        journal_engine.post_invoice_payment(inv.id, db2)
        db2.close()
    except Exception as e:
        logger.warning(f"Portal IPN: journal post failed (non-fatal): {e}")

    logger.info(f"Portal IPN: invoice {inv.invoice_number} marked paid — R{inv.paid_amount_zar:.2f}")
    return JSONResponse(content={"status": "ok"})
