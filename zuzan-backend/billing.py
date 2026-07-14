"""
ZuZan Billing — trial expiry, PayFast subscription flow, overdue invoice reminders.
Mounted at /billing (requires auth except /payfast-notify).
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from database import (
    get_db, Company, Invoice, InvoiceStatus, SubscriptionStatus,
    SubscriptionPayment, User, SessionLocal
)
from auth import get_current_user
from crypto import decrypt_field
from email_service import (
    send_trial_warning_email,
    send_trial_expired_email,
    send_subscription_active_email,
    send_overdue_invoice_reminder,
)
import os, hashlib, logging
from urllib.parse import quote_plus

logger = logging.getLogger("zuzan.billing")

billing_router = APIRouter()

# ── PayFast config ────────────────────────────────────────────────────────────
PAYFAST_MERCHANT_ID  = os.environ.get("PAYFAST_MERCHANT_ID",  "10000100")
PAYFAST_MERCHANT_KEY = os.environ.get("PAYFAST_MERCHANT_KEY", "46f0cd694581a")
PAYFAST_PASSPHRASE   = os.environ.get("PAYFAST_PASSPHRASE",   "")
PAYFAST_SANDBOX      = os.environ.get("PAYFAST_SANDBOX", "true").lower() == "true"
PAYFAST_URL          = "https://sandbox.payfast.co.za/eng/process" if PAYFAST_SANDBOX else "https://www.payfast.co.za/eng/process"
BACKEND_URL          = os.environ.get("BACKEND_URL",  "https://api.zuzan.co.za")
FRONTEND_URL         = os.environ.get("FRONTEND_URL", "https://app.zuzan.co.za")
ADMIN_EMAIL          = os.environ.get("ADMIN_EMAIL",  "dev@solutha.co.za")

PLAN_PRICES = {
    "starter":      {"monthly": 399,  "annual": 3990},
    "professional": {"monthly": 899,  "annual": 8990},
    "business":     {"monthly": 1499, "annual": 14990},
}

PAYROLL_PER_EMP  = 45   # R45/employee/month (matches companies.py)
PAYROLL_MIN_COST = 99   # minimum payroll add-on fee


def _pf_signature(data: dict, passphrase: str = "") -> str:
    """Build PayFast MD5 signature.

    Parameters are included in the ORDER they appear in `data` (insertion order,
    as required by PayFast for both checkout forms and ITN verification).
    Values are URL-encoded (urllib.parse.quote_plus), matching PayFast's PHP SDK.
    Empty-string values are excluded per PayFast spec.
    """
    param_string = "&".join(
        f"{k}={quote_plus(str(v))}"
        for k, v in data.items()
        if str(v) != ""
    )
    if passphrase:
        param_string += f"&passphrase={quote_plus(passphrase)}"
    return hashlib.md5(param_string.encode()).hexdigest()


def _pf_verify_itn(form_data: dict, passphrase: str = "") -> bool:
    """Verify PayFast ITN signature.

    Removes 'signature' from received data, recomputes, and compares.
    Returns True if valid.
    """
    received_sig = form_data.get("signature", "")
    data_without_sig = {k: v for k, v in form_data.items() if k != "signature"}
    computed = _pf_signature(data_without_sig, passphrase)
    return computed == received_sig


# ── GET /billing/status ───────────────────────────────────────────────────────
@billing_router.get("/status")
async def billing_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    co = db.query(Company).filter(Company.id == current_user.company_id).first()
    if not co:
        raise HTTPException(status_code=404, detail="Company not found")

    days_remaining = None
    if co.trial_ends:
        delta = co.trial_ends - datetime.utcnow()
        days_remaining = max(0, delta.days)

    # Recent payments
    payments = (
        db.query(SubscriptionPayment)
        .filter(SubscriptionPayment.company_id == co.id)
        .order_by(SubscriptionPayment.payment_date.desc())
        .limit(10)
        .all()
    )

    return {
        "status":          co.subscription_status.value if co.subscription_status else "trial",
        "plan":            co.plan.value if co.plan else "starter",
        "billing_cycle":   co.billing_cycle.value if co.billing_cycle else "monthly",
        "trial_ends":      co.trial_ends.isoformat() if co.trial_ends else None,
        "days_remaining":  days_remaining,
        "overdue_reminders_enabled": getattr(co, "overdue_reminders_enabled", True),
        "payments": [
            {
                "id":           p.id,
                "amount":       p.amount,
                "plan":         p.plan,
                "status":       p.status,
                "payment_date": p.payment_date.isoformat() if p.payment_date else None,
            }
            for p in payments
        ],
    }


# ── POST /billing/subscribe — build PayFast subscription params ───────────────
@billing_router.post("/subscribe")
async def initiate_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    co = db.query(Company).filter(Company.id == current_user.company_id).first()
    if not co:
        raise HTTPException(status_code=404, detail="Company not found")

    plan  = co.plan.value          if co.plan          else "starter"
    cycle = co.billing_cycle.value if co.billing_cycle else "monthly"

    # Base plan price — use the correct billing cycle
    base_amount = PLAN_PRICES.get(plan, PLAN_PRICES["starter"])[cycle]

    # Payroll add-on cost (same logic as signup)
    payroll_cost = 0
    if getattr(co, "payroll_enabled", False):
        emp_count    = getattr(co, "payroll_employees", 0) or 0
        monthly_cost = max(PAYROLL_MIN_COST, emp_count * PAYROLL_PER_EMP)
        payroll_cost = monthly_cost if cycle == "monthly" else monthly_cost * 12

    amount = base_amount + payroll_cost

    # Per-company credentials (override global if set)
    pf_id  = (decrypt_field(co.payfast_merchant_id)  if co.payfast_merchant_id  else None) or PAYFAST_MERCHANT_ID
    pf_key = (decrypt_field(co.payfast_merchant_key) if co.payfast_merchant_key else None) or PAYFAST_MERCHANT_KEY
    pf_pp  = (decrypt_field(co.payfast_passphrase)   if co.payfast_passphrase   else None) or PAYFAST_PASSPHRASE

    # PayFast frequency: 3 = monthly, 6 = annual
    pf_frequency = "3" if cycle == "monthly" else "6"

    # Billing date = tomorrow (trial is already done; first charge is immediate)
    billing_date = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")

    # Build item description (include payroll add-on if applicable)
    item_desc = f"ZuZan {plan.title()} Plan ({cycle})"
    if payroll_cost:
        item_desc += f" + Payroll add-on"

    pf_data = {
        "merchant_id":      pf_id,
        "merchant_key":     pf_key,
        "return_url":       f"{FRONTEND_URL}/settings?tab=subscription&subscribed=1",
        "cancel_url":       f"{FRONTEND_URL}/settings?tab=subscription",
        "notify_url":       f"{BACKEND_URL}/billing/payfast-notify",
        "name_first":       current_user.first_name or "User",
        "name_last":        current_user.last_name  or "",
        "email_address":    current_user.email,
        "m_payment_id":     f"sub-{co.id}-{int(datetime.utcnow().timestamp())}",
        "amount":           f"{amount:.2f}",
        "item_name":        item_desc,
        "item_description": f"Subscription — {co.name}",
        # PayFast Subscriptions product
        "subscription_type": "1",
        "billing_date":      billing_date,
        "recurring_amount":  f"{amount:.2f}",
        "frequency":         pf_frequency,
        "cycles":            "0",   # 0 = indefinite
    }
    pf_data["signature"] = _pf_signature(pf_data, pf_pp)

    return {"payfast_url": PAYFAST_URL, "payfast_data": pf_data}


# ── POST /billing/payfast-notify — ITN webhook (no auth) ─────────────────────
@billing_router.post("/payfast-notify")
async def payfast_notify(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    data = dict(form)

    # ── Verify PayFast ITN signature ──────────────────────────────────────────
    # Skip signature check only in sandbox mode (for testing without real creds)
    if not PAYFAST_SANDBOX:
        if not _pf_verify_itn(data, PAYFAST_PASSPHRASE):
            logger.warning(
                f"PayFast ITN: signature mismatch — possible spoofed request. "
                f"m_payment_id={data.get('m_payment_id')}"
            )
            return {"ok": True}   # Return 200 so PayFast stops retrying; don't process

    # Extract key fields
    m_payment_id = data.get("m_payment_id", "")  # "sub-{company_id}-{ts}"
    pf_payment_id = data.get("pf_payment_id", "")
    amount_gross = float(data.get("amount_gross", 0))
    payment_status = data.get("payment_status", "")

    if payment_status != "COMPLETE":
        logger.info(f"PayFast notify status={payment_status}, ignoring")
        return {"ok": True}

    # Extract company_id from m_payment_id
    try:
        parts = m_payment_id.split("-")
        company_id = int(parts[1]) if len(parts) >= 2 else None
    except Exception:
        company_id = None

    if not company_id:
        logger.warning(f"PayFast ITN: could not parse company_id from {m_payment_id}")
        return {"ok": True}

    co = db.query(Company).filter(Company.id == company_id).first()
    if not co:
        logger.warning(f"PayFast ITN: company {company_id} not found")
        return {"ok": True}

    # Activate subscription
    co.subscription_status = SubscriptionStatus.active
    db.commit()

    # Log subscription payment
    owner = db.query(User).filter(User.company_id == co.id, User.role == "owner").first()
    sub_pay = SubscriptionPayment(
        company_id=co.id,
        company_name=co.name,
        owner_email=owner.email if owner else None,
        plan=co.plan.value if co.plan else "starter",
        billing_cycle=co.billing_cycle.value if co.billing_cycle else "monthly",
        amount=amount_gross,
        payfast_payment_id=pf_payment_id,
        status="success",
        payment_date=datetime.utcnow(),
        period_start=datetime.utcnow(),
        period_end=datetime.utcnow() + timedelta(days=31),
    )
    db.add(sub_pay)
    db.commit()

    # Send confirmation email
    if owner:
        try:
            send_subscription_active_email(
                first_name=owner.first_name,
                email=owner.email,
                company_name=co.name,
                plan=co.plan.value if co.plan else "starter",
                amount=amount_gross,
            )
        except Exception as e:
            logger.warning(f"Subscription active email failed: {e}")

    logger.info(f"Subscription activated for company {co.id} ({co.name}), amount R{amount_gross}")
    return {"ok": True}


# ── PATCH /billing/overdue-reminders — toggle overdue reminders ───────────────
@billing_router.patch("/overdue-reminders")
async def toggle_overdue_reminders(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    body = await request.json()
    enabled = bool(body.get("enabled", True))
    co = db.query(Company).filter(Company.id == current_user.company_id).first()
    if not co:
        raise HTTPException(status_code=404, detail="Company not found")
    if hasattr(co, "overdue_reminders_enabled"):
        co.overdue_reminders_enabled = enabled
        db.commit()
    return {"overdue_reminders_enabled": enabled}


# ── Background: trial expiry checks ──────────────────────────────────────────
def check_trial_expirations():
    """
    Run daily. Sends warning emails (3 days before) and expiry emails (on expiry day).
    Called from main.py lifespan on startup, and ideally scheduled to run daily.
    """
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        warning_threshold = now + timedelta(days=3)

        companies = db.query(Company).filter(
            Company.subscription_status == SubscriptionStatus.trial
        ).all()

        warned = 0
        expired = 0

        for co in companies:
            if not co.trial_ends:
                continue

            owner = db.query(User).filter(
                User.company_id == co.id,
                User.role == "owner",
            ).first()
            if not owner:
                continue

            subscribe_url = f"{FRONTEND_URL}/settings?tab=subscription"

            # 3-day warning (send once)
            if (
                co.trial_ends > now
                and co.trial_ends <= warning_threshold
                and not getattr(co, "trial_warning_sent_at", None)
            ):
                days_left = (co.trial_ends - now).days + 1
                try:
                    send_trial_warning_email(
                        first_name=owner.first_name,
                        email=owner.email,
                        company_name=co.name,
                        days_left=days_left,
                        subscribe_url=subscribe_url,
                    )
                    if hasattr(co, "trial_warning_sent_at"):
                        co.trial_warning_sent_at = now
                    db.commit()
                    warned += 1
                    logger.info(f"Trial warning sent to {owner.email} ({co.name})")
                except Exception as e:
                    logger.warning(f"Trial warning email failed for {co.id}: {e}")

            # Trial expired (send once, mark as expired)
            if (
                co.trial_ends <= now
                and not getattr(co, "trial_expiry_email_sent_at", None)
            ):
                try:
                    send_trial_expired_email(
                        first_name=owner.first_name,
                        email=owner.email,
                        company_name=co.name,
                        subscribe_url=subscribe_url,
                    )
                    co.subscription_status = SubscriptionStatus.expired
                    if hasattr(co, "trial_expiry_email_sent_at"):
                        co.trial_expiry_email_sent_at = now
                    db.commit()
                    expired += 1
                    logger.info(f"Trial expired email sent to {owner.email} ({co.name})")
                except Exception as e:
                    logger.warning(f"Trial expired email failed for {co.id}: {e}")

        if warned or expired:
            logger.info(f"Trial check: {warned} warning(s), {expired} expiry email(s)")
    except Exception as e:
        logger.error(f"Trial expiry check failed: {e}")
    finally:
        db.close()


# ── Background: overdue invoice reminders ─────────────────────────────────────
def send_overdue_reminders():
    """
    Run daily. Sends reminder emails to clients for overdue invoices.
    Only runs for companies with overdue_reminders_enabled=True.
    Sends on days 7, 14, and 30 past due_date (once per interval per invoice).
    """
    db = SessionLocal()
    try:
        from database import Invoice, InvoiceStatus, Company
        now = datetime.utcnow()
        REMINDER_DAYS = [7, 14, 30]

        companies = db.query(Company).filter(
            Company.subscription_status.in_([
                SubscriptionStatus.trial,
                SubscriptionStatus.active,
            ])
        ).all()

        sent = 0
        for co in companies:
            # Check if overdue reminders enabled (default True)
            if not getattr(co, "overdue_reminders_enabled", True):
                continue

            overdue_invoices = db.query(Invoice).filter(
                Invoice.company_id == co.id,
                Invoice.status == InvoiceStatus.sent,
                Invoice.due_date != None,
                Invoice.due_date < now,
                Invoice.client_email != None,
            ).all()

            for inv in overdue_invoices:
                if not inv.client_email or not inv.due_date:
                    continue
                days_overdue = (now - inv.due_date).days
                # Only send on the specific milestone days (± 1 day tolerance)
                if not any(abs(days_overdue - d) <= 1 for d in REMINDER_DAYS):
                    continue

                portal_url = f"{FRONTEND_URL}/portal/{inv.portal_token}" if inv.portal_token else None

                try:
                    send_overdue_invoice_reminder(
                        client_email=inv.client_email,
                        client_name=inv.client_name,
                        company_name=co.name,
                        invoice_number=inv.invoice_number,
                        amount=inv.total_amount,
                        days_overdue=days_overdue,
                        portal_url=portal_url,
                    )
                    sent += 1
                except Exception as e:
                    logger.warning(f"Overdue reminder failed for inv {inv.id}: {e}")

        if sent:
            logger.info(f"Overdue reminders: {sent} sent")
    except Exception as e:
        logger.error(f"Overdue reminder job failed: {e}")
    finally:
        db.close()
