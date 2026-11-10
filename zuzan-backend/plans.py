"""Plan levels, limits and server-side enforcement.

The screens hide locked features, but hiding is not enforcement: anything a plan does not include is
also refused by the server, so a client cannot reach it by calling the API directly.
"""
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

PLAN_LEVEL = {"starter": 1, "professional": 2, "business": 3}
PLAN_LABEL = {"starter": "Starter", "professional": "Professional", "business": "Business"}
INVOICE_LIMIT = {"starter": 20, "professional": 80, "business": 999999}
USER_LIMIT = {"starter": 2, "professional": 5, "business": 20}


def _company(db: Session, company_id: int):
    from database import Company
    return db.query(Company).filter(Company.id == company_id).first()


def plan_of(company) -> str:
    p = getattr(company, "plan", None)
    p = getattr(p, "value", p) or "starter"
    return str(p).lower() if str(p).lower() in PLAN_LEVEL else "starter"


def has_plan(company, required: str) -> bool:
    """Partner companies (billing_exempt) are not held to plan locks, matching the invoice limit behaviour."""
    if company is None:
        return False
    if getattr(company, "billing_exempt", False):
        return True
    return PLAN_LEVEL[plan_of(company)] >= PLAN_LEVEL[required]


def plan_error(required: str, what: str = "This feature") -> HTTPException:
    return HTTPException(status_code=403, detail=f"{what} is available on the {PLAN_LABEL[required]} plan. Upgrade your plan to use it.")


def require_plan(required: str, what: str = "This feature"):
    """Router/endpoint dependency: 403 unless the signed-in user's company is on `required` or higher."""
    from auth import get_current_user
    from database import get_db

    def _dep(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
        if not has_plan(_company(db, current_user.company_id), required):
            raise plan_error(required, what)
        return current_user
    return _dep


def check_invoice_limit(company_id: int, db: Session):
    """Raise 403 when the company has used up this month's invoice allowance."""
    from database import Invoice
    company = _company(db, company_id)
    if company is None or getattr(company, "billing_exempt", False):
        return
    limit = INVOICE_LIMIT.get(plan_of(company), 20)
    now = datetime.utcnow()
    used = db.query(Invoice).filter(Invoice.company_id == company_id,
                                    Invoice.created_at >= datetime(now.year, now.month, 1)).count()
    if used >= limit:
        raise HTTPException(status_code=403, detail=f"Monthly invoice limit ({limit}) reached. Upgrade your plan.")


def check_user_limit(company_id: int, db: Session, adding: int = 1):
    """Raise 403 when active users + open invitations would exceed the plan's user allowance."""
    from database import User, InviteToken
    company = _company(db, company_id)
    if company is None or getattr(company, "billing_exempt", False):
        return
    limit = USER_LIMIT.get(plan_of(company), 2)
    active = db.query(User).filter(User.company_id == company_id, User.is_active == True).count()
    pending = db.query(InviteToken).filter(InviteToken.company_id == company_id, InviteToken.used_at == None,
                                           InviteToken.expires_at > datetime.utcnow()).count()
    if active + pending + adding > limit:
        raise HTTPException(status_code=403, detail=f"Your {PLAN_LABEL[plan_of(company)]} plan includes {limit} users. Upgrade your plan to add more.")
