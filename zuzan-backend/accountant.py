"""
Zuzan — Accountant / Bookkeeper Practice Router
Endpoints for multi-client management, client onboarding, and cross-company summaries.
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
import secrets
import logging

from database import get_db, Company, User, CompanyMembership, Invoice, InvoiceStatus, InviteToken
from auth import get_current_user, log_action
from email_service import send_email

logger = logging.getLogger("zuzan.accountant")

router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _invoice_summary(company_id: int, db: Session) -> dict:
    """Return unpaid/overdue invoice counts and totals for a company."""
    try:
        now = datetime.utcnow()
        unpaid = db.query(Invoice).filter(
            Invoice.company_id == company_id,
            Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.draft]),
        ).all()
        overdue = [i for i in unpaid if i.due_date and i.due_date < now and i.status == InvoiceStatus.sent]
        unpaid_total = sum(float(i.total_amount or 0) for i in unpaid if i.status == InvoiceStatus.sent)
        return {
            "unpaid_count": len([i for i in unpaid if i.status == InvoiceStatus.sent]),
            "unpaid_total": round(unpaid_total, 2),
            "overdue_count": len(overdue),
            "draft_count":  len([i for i in unpaid if i.status == InvoiceStatus.draft]),
        }
    except Exception as e:
        logger.warning(f"Invoice summary failed for company {company_id}: {e}")
        return {"unpaid_count": 0, "unpaid_total": 0.0, "overdue_count": 0, "draft_count": 0}


def _company_card(company: Company, role: str, db: Session) -> dict:
    sub = company.subscription_status.value if hasattr(company.subscription_status, "value") else str(company.subscription_status or "trial")
    plan = company.plan.value if hasattr(company.plan, "value") else str(company.plan or "starter")
    inv = _invoice_summary(company.id, db)
    return {
        "id":                   company.id,
        "name":                 company.name or "",
        "email":                company.email or "",
        "phone":                company.phone or "",
        "industry":             company.industry or "",
        "plan":                 plan,
        "subscription_status":  sub,
        "billing_exempt":       bool(company.billing_exempt),
        "trial_ends":           company.trial_ends.isoformat() if company.trial_ends else None,
        "role":                 role,
        **inv,
    }


# ── GET /accountant/clients ───────────────────────────────────────────────────

@router.get("/clients")
async def list_clients(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return all companies the current user can access, with invoice summary stats.
    Includes both their home company and any CompanyMembership companies.
    """
    seen = set()
    results = []

    # Always include home company
    home = db.query(Company).filter(Company.id == current_user.company_id).first()
    if home:
        seen.add(home.id)
        results.append(_company_card(home, "owner", db))

    # All membership companies
    memberships = db.query(CompanyMembership).filter(
        CompanyMembership.user_id == current_user.id
    ).all()
    for m in memberships:
        if m.company_id in seen:
            continue
        company = db.query(Company).filter(Company.id == m.company_id).first()
        if company:
            seen.add(company.id)
            results.append(_company_card(company, m.role, db))

    return results


# ── POST /accountant/onboard-client ──────────────────────────────────────────

class OnboardClientIn(BaseModel):
    company_name:  str
    contact_name:  str
    contact_email: str
    contact_phone: Optional[str] = None
    industry:      Optional[str] = None


@router.post("/onboard-client")
async def onboard_client(
    data: OnboardClientIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a new client company, add current user as Accountant member,
    and send the client an invite email to complete their account setup.
    """
    if not data.company_name.strip():
        raise HTTPException(status_code=400, detail="Company name is required.")
    if not data.contact_email.strip():
        raise HTTPException(status_code=400, detail="Contact email is required.")

    # Create the client company
    new_company = Company(
        name=data.company_name.strip(),
        email=data.contact_email.strip(),
        phone=data.contact_phone or "",
        industry=data.industry or "",
    )
    db.add(new_company)
    db.flush()  # get new_company.id

    # Add current user (the accountant) as Accountant member
    membership = CompanyMembership(
        user_id=current_user.id,
        company_id=new_company.id,
        role="accountant",
    )
    db.add(membership)

    # Create an invite token for the client to register as owner
    token = secrets.token_urlsafe(32)
    invite = InviteToken(
        company_id=new_company.id,
        email=data.contact_email.strip(),
        role="owner",
        token=token,
        invited_by=current_user.id,
        expires_at=datetime.utcnow() + timedelta(days=14),
    )
    db.add(invite)
    db.commit()
    db.refresh(new_company)

    # Send invite email to the client
    invite_url = f"https://zuzan.co.za/accept-invite?token={token}"
    accountant_name = f"{current_user.first_name} {current_user.last_name}".strip() or "Your accountant"
    try:
        send_email(
            to=data.contact_email.strip(),
            subject=f"You've been invited to Zuzan by {accountant_name}",
            html=f"""
<div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;color:#222">
  <div style="background:#1a3a5c;padding:24px 32px;border-radius:12px 12px 0 0">
    <h1 style="color:#fff;margin:0;font-size:22px">Welcome to Zuzan</h1>
  </div>
  <div style="background:#fff;padding:28px 32px;border:1px solid #e0e8f0;border-top:none;border-radius:0 0 12px 12px">
    <p>Hi {data.contact_name},</p>
    <p><strong>{accountant_name}</strong> has set up a <strong>Zuzan</strong> account for <strong>{data.company_name}</strong> and invited you to manage your business finances online.</p>
    <p>Zuzan handles your invoicing, expenses, payroll and more — all in one place.</p>
    <div style="text-align:center;margin:28px 0">
      <a href="{invite_url}" style="background:#1a3a5c;color:#fff;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px">Set Up My Account →</a>
    </div>
    <p style="font-size:12px;color:#888">This invitation expires in 14 days. If you weren't expecting this, please ignore it.</p>
  </div>
</div>""",
        )
        email_sent = True
    except Exception as e:
        logger.warning(f"Onboard invite email failed for {data.contact_email}: {e}")
        email_sent = False

    log_action(db, new_company.id, current_user.id, "onboard_client",
               f"Onboarded client company: {data.company_name} ({data.contact_email})")

    return {
        **_company_card(new_company, "accountant", db),
        "invite_token": token,
        "invite_url":   invite_url,
        "email_sent":   email_sent,
    }


# ── DELETE /accountant/clients/{company_id} ───────────────────────────────────

@router.delete("/clients/{company_id}")
async def remove_client(
    company_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove accountant's access to a client company (does not delete the company)."""
    membership = db.query(CompanyMembership).filter(
        CompanyMembership.user_id == current_user.id,
        CompanyMembership.company_id == company_id,
    ).first()
    if not membership:
        raise HTTPException(status_code=404, detail="Client not found in your portfolio.")
    db.delete(membership)
    db.commit()
    return {"status": "ok"}
