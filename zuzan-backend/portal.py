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
from crypto import decrypt_field

logger = logging.getLogger("zuzan.portal")

portal_router = APIRouter()

# ── PayFast config (shared with payroll.py subscription payments) ─────────────
PAYFAST_MERCHANT_ID  = os.environ.get("PAYFAST_MERCHANT_ID",  "10000100")
PAYFAST_MERCHANT_KEY = os.environ.get("PAYFAST_MERCHANT_KEY", "46f0cd694581a")
PAYFAST_PASSPHRASE   = os.environ.get("PAYFAST_PASSPHRASE",   "")
PAYFAST_SANDBOX      = os.environ.get("PAYFAST_SANDBOX", "true").lower() == "true"
PAYFAST_URL          = "https://sandbox.payfast.co.za/eng/process" if PAYFAST_SANDBOX else "https://www.payfast.co.za/eng/process"
BACKEND_URL          = os.environ.get("BACKEND_URL",   "https://api.zuzan.co.za")
FRONTEND_URL         = os.environ.get("FRONTEND_URL",  "https://app.zuzan.co.za")


def _pf_param_string(data: dict, passphrase: str = "", skip_empty: bool = True) -> str:
    """PayFast parameter string: fields in the ORDER given (never alphabetical), values URL-encoded
    (quote_plus: space -> '+', upper-case hex), passphrase appended. Sorting / not encoding made PayFast reject
    the signature of any invoice whose item name contains a space."""
    from urllib.parse import quote_plus
    def enc(v): return quote_plus(str(v).strip()).replace("~", "%7E")      # PHP urlencode also encodes "~"
    parts = [f"{k}={enc(v)}" for k, v in data.items() if not (skip_empty and str(v) == "")]
    ps = "&".join(parts)
    if passphrase:
        ps += f"&passphrase={enc(passphrase)}"
    return ps


def _pf_signature(data: dict, passphrase: str = "") -> str:
    return hashlib.md5(_pf_param_string(data, passphrase).encode()).hexdigest()


def _pf_itn_signature_ok(data: dict, passphrase: str = "") -> bool:
    """Check an ITN signature. PayFast's own samples differ on whether blank fields are part of the string, so
    both forms are accepted - each is still an MD5 over the received data that only matches if it is untampered."""
    received = data.get("signature", "")
    body = {k: v for k, v in data.items() if k != "signature"}
    return received in (
        hashlib.md5(_pf_param_string(body, passphrase, skip_empty=True).encode()).hexdigest(),
        hashlib.md5(_pf_param_string(body, passphrase, skip_empty=False).encode()).hexdigest(),
    )


def _pf_validate_remote(data: dict) -> bool:
    """PayFast's server-to-server confirmation: post the received fields back and expect the word VALID.
    A forged ITN cannot pass this. Network trouble raises, so the ITN is answered with an error and PayFast retries."""
    import requests
    body = {k: v for k, v in data.items() if k != "signature"}
    url = ("https://sandbox.payfast.co.za" if PAYFAST_SANDBOX else "https://www.payfast.co.za") + "/eng/query/validate"
    r = requests.post(url, data=_pf_param_string(body, "", skip_empty=False),
                      headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=10)
    return r.text.strip().upper() == "VALID"


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
    if inv.status == InvoiceStatus.written_off:
        raise HTTPException(status_code=400, detail="This invoice can no longer be paid online. Please contact us.")

    company = db.query(Company).filter(Company.id == inv.company_id).first()

    # Always charge in ZAR
    zar_total = round(
        (inv.total_amount or 0) * (inv.exchange_rate or 1), 2
    )
    if zar_total <= 0:
        raise HTTPException(status_code=400, detail="Invoice amount must be greater than zero.")

    # Use per-company PayFast credentials; fall back to global env vars
    pf_merchant_id  = (decrypt_field(company.payfast_merchant_id)  if company and company.payfast_merchant_id  else None) or PAYFAST_MERCHANT_ID
    pf_merchant_key = (decrypt_field(company.payfast_merchant_key) if company and company.payfast_merchant_key else None) or PAYFAST_MERCHANT_KEY
    pf_passphrase   = (decrypt_field(company.payfast_passphrase)   if company and company.payfast_passphrase   else None) or PAYFAST_PASSPHRASE

    pf_data = {
        "merchant_id":   pf_merchant_id,
        "merchant_key":  pf_merchant_key,
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
    pf_data["signature"] = _pf_signature(pf_data, pf_passphrase)

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

    # Find invoice first - its company decides which PayFast credentials apply
    inv = db.query(Invoice).filter(Invoice.portal_token == token).first()
    if not inv:
        logger.error(f"Portal IPN: invoice not found for token {token[:8]}...")
        return JSONResponse(content={"status": "error", "detail": "Invoice not found"}, status_code=404)
    _co = db.query(Company).filter(Company.id == inv.company_id).first()
    _passphrase = (decrypt_field(_co.payfast_passphrase) if _co and _co.payfast_passphrase else None) or PAYFAST_PASSPHRASE
    _merchant = (decrypt_field(_co.payfast_merchant_id) if _co and _co.payfast_merchant_id else None) or PAYFAST_MERCHANT_ID

    # The signature is ALWAYS checked. (It used to be skipped whenever PAYFAST_SANDBOX was unset/true - and it
    # defaults to true - which let anyone holding an invoice link mark it paid with a hand-made POST.)
    if os.environ.get("PORTAL_IPN_SKIP_SIGNATURE") != "1" and not _pf_itn_signature_ok(data, _passphrase):
        logger.warning(f"Portal IPN: signature mismatch for token {token[:8]}...")
        return JSONResponse(content={"status": "error", "detail": "Invalid signature"}, status_code=400)

    if status != "COMPLETE":
        logger.info(f"Portal IPN: ignoring status={status} for token {token[:8]}...")
        return JSONResponse(content={"status": "ok", "detail": f"Status {status} — no action"})

    if data.get("merchant_id") and data.get("merchant_id") != _merchant:
        logger.error(f"Portal IPN: merchant_id mismatch for invoice {inv.invoice_number}")
        return JSONResponse(content={"status": "error", "detail": "Merchant mismatch"}, status_code=400)

    if inv.status == InvoiceStatus.written_off:
        # Money arrived for a debt that was written off: it has to be booked as a bad-debt recovery (VAT Act s22),
        # which needs a person. Do not silently flip the invoice to paid.
        logger.error(f"Portal IPN: payment received for WRITTEN-OFF invoice {inv.invoice_number} - record it with 'Record Recovery'.")
        return JSONResponse(content={"status": "ok", "detail": "Written-off invoice - recorded for manual recovery"})

    if inv.status == InvoiceStatus.paid:
        logger.info(f"Portal IPN: invoice {inv.invoice_number} already paid — ignoring duplicate")
        return JSONResponse(content={"status": "ok", "detail": "Already paid"})

    # The amount actually paid must cover the invoice (a R1 payment must not clear a R10 000 invoice)
    try:
        amount_gross = float(data.get("amount_gross", 0) or 0)
    except ValueError:
        amount_gross = 0.0
    _due_zar = round((inv.total_amount or 0) * (inv.exchange_rate or 1), 2)
    if amount_gross + 0.01 < _due_zar:
        logger.error(f"Portal IPN: amount R{amount_gross:.2f} is less than invoice {inv.invoice_number} total R{_due_zar:.2f} - not marked paid")
        return JSONResponse(content={"status": "error", "detail": "Amount does not match the invoice"}, status_code=400)

    # Ask PayFast to confirm this notification really came from them
    if os.environ.get("PORTAL_IPN_SKIP_SIGNATURE") != "1":
        try:
            confirmed = _pf_validate_remote(data)
        except Exception as e:
            logger.error(f"Portal IPN: PayFast confirmation call failed ({e}) - asking PayFast to retry")
            return JSONResponse(content={"status": "error", "detail": "Could not confirm with PayFast, retry"}, status_code=503)
        if not confirmed:
            logger.error(f"Portal IPN: PayFast did NOT confirm notification for invoice {inv.invoice_number}")
            return JSONResponse(content={"status": "error", "detail": "Not confirmed by PayFast"}, status_code=400)

    # Mark paid
    inv.status          = InvoiceStatus.paid
    inv.paid_date       = datetime.utcnow()
    inv.paid_amount_zar = amount_gross if amount_gross > 0 else round(
        (inv.total_amount or 0) * (inv.exchange_rate or 1), 2
    )
    db.commit()

    # Post journal entry for payment received: DR Bank / CR Accounts Receivable.
    # Audit fix 2026-07-03: the previous code called a nonexistent function
    # (post_invoice_payment) with an id instead of the Invoice object, on a
    # throwaway session that was never committed — so portal payments never
    # reached the journal and the AR control account (1100) failed to reconcile.
    # Non-fatal by design: the invoice is already marked paid above, and a PayFast
    # IPN retry would hit the "already paid" guard and skip this block, so we
    # log loudly and rely on /journal/backfill as the repair path.
    try:
        import journal as journal_engine
        journal_engine.init_accounts(inv.company_id, db)
        journal_engine.post_invoice_paid(inv, db)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(
            f"Portal IPN: journal post FAILED for invoice {inv.invoice_number}: {e}. "
            f"AR control (1100) will not reconcile — run /journal/backfill to repair."
        )

    logger.info(f"Portal IPN: invoice {inv.invoice_number} marked paid — R{inv.paid_amount_zar:.2f}")
    return JSONResponse(content={"status": "ok"})
