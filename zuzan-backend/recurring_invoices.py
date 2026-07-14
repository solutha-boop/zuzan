"""
ZuZan Recurring Invoices — templates that auto-generate invoices on a schedule.
Mounted at /recurring-invoices.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
from database import (
    get_db, Company, Invoice, InvoiceStatus, SessionLocal
)
from auth import get_current_user, User
import logging, uuid

logger = logging.getLogger("zuzan.recurring")
recurring_router = APIRouter()

# ── Pydantic schemas ──────────────────────────────────────────────────────────
class RecurringInvoiceCreate(BaseModel):
    client_name:    str
    client_email:   Optional[str] = None
    description:    Optional[str] = None
    amount:         float
    vat_applicable: Optional[bool] = True
    currency:       Optional[str] = "ZAR"
    frequency:      str   # weekly | monthly | quarterly | annually
    start_date:     str   # ISO date YYYY-MM-DD
    is_active:      Optional[bool] = True

class RecurringInvoiceUpdate(BaseModel):
    client_name:    Optional[str]  = None
    client_email:   Optional[str]  = None
    description:    Optional[str]  = None
    amount:         Optional[float]= None
    vat_applicable: Optional[bool] = None
    currency:       Optional[str]  = None
    frequency:      Optional[str]  = None
    is_active:      Optional[bool] = None


def _next_run(frequency: str, from_date: datetime) -> datetime:
    """Calculate next run date based on frequency."""
    freq = frequency.lower()
    if freq == "weekly":
        return from_date + timedelta(weeks=1)
    elif freq == "monthly":
        # Add one month
        month = from_date.month + 1
        year  = from_date.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        day   = min(from_date.day, [31,28,31,30,31,30,31,31,30,31,30,31][month-1])
        return from_date.replace(year=year, month=month, day=day)
    elif freq == "quarterly":
        return _next_run("monthly", _next_run("monthly", _next_run("monthly", from_date)))
    elif freq == "annually":
        return from_date.replace(year=from_date.year + 1)
    return from_date + timedelta(days=30)


def _ri_dict(ri) -> dict:
    return {
        "id":                 ri.id,
        "client_name":        ri.client_name,
        "client_email":       ri.client_email,
        "description":        ri.description,
        "amount":             ri.amount,
        "vat_applicable":     ri.vat_applicable,
        "currency":           ri.currency or "ZAR",
        "frequency":          ri.frequency,
        "start_date":         ri.start_date.isoformat()    if ri.start_date    else None,
        "next_run_date":      ri.next_run_date.isoformat() if ri.next_run_date else None,
        "last_run_date":      ri.last_run_date.isoformat() if ri.last_run_date else None,
        "is_active":          ri.is_active,
        "invoices_generated": ri.invoices_generated or 0,
        "created_at":         ri.created_at.isoformat()    if ri.created_at    else None,
    }


# ── GET /recurring-invoices ───────────────────────────────────────────────────
@recurring_router.get("")
async def list_recurring(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from database import RecurringInvoice
    rows = (
        db.query(RecurringInvoice)
        .filter(RecurringInvoice.company_id == current_user.company_id)
        .order_by(RecurringInvoice.created_at.desc())
        .all()
    )
    return [_ri_dict(r) for r in rows]


# ── POST /recurring-invoices ──────────────────────────────────────────────────
@recurring_router.post("")
async def create_recurring(
    body: RecurringInvoiceCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from database import RecurringInvoice
    start = datetime.fromisoformat(body.start_date)
    ri = RecurringInvoice(
        company_id=current_user.company_id,
        client_name=body.client_name,
        client_email=body.client_email,
        description=body.description,
        amount=body.amount,
        vat_applicable=body.vat_applicable if body.vat_applicable is not None else True,
        currency=body.currency or "ZAR",
        frequency=body.frequency,
        start_date=start,
        next_run_date=start,
        is_active=body.is_active if body.is_active is not None else True,
        invoices_generated=0,
    )
    db.add(ri)
    db.commit()
    db.refresh(ri)
    return _ri_dict(ri)


# ── PUT /recurring-invoices/{id} ──────────────────────────────────────────────
@recurring_router.put("/{ri_id}")
async def update_recurring(
    ri_id: int,
    body: RecurringInvoiceUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from database import RecurringInvoice
    ri = db.query(RecurringInvoice).filter(
        RecurringInvoice.id == ri_id,
        RecurringInvoice.company_id == current_user.company_id,
    ).first()
    if not ri:
        raise HTTPException(status_code=404, detail="Recurring invoice not found")
    for field, value in body.dict(exclude_unset=True).items():
        setattr(ri, field, value)
    db.commit()
    db.refresh(ri)
    return _ri_dict(ri)


# ── DELETE /recurring-invoices/{id} ──────────────────────────────────────────
@recurring_router.delete("/{ri_id}")
async def delete_recurring(
    ri_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from database import RecurringInvoice
    ri = db.query(RecurringInvoice).filter(
        RecurringInvoice.id == ri_id,
        RecurringInvoice.company_id == current_user.company_id,
    ).first()
    if not ri:
        raise HTTPException(status_code=404, detail="Recurring invoice not found")
    db.delete(ri)
    db.commit()
    return {"ok": True}


# ── POST /recurring-invoices/{id}/run — manual trigger ───────────────────────
@recurring_router.post("/{ri_id}/run")
async def run_recurring(
    ri_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from database import RecurringInvoice
    ri = db.query(RecurringInvoice).filter(
        RecurringInvoice.id == ri_id,
        RecurringInvoice.company_id == current_user.company_id,
    ).first()
    if not ri:
        raise HTTPException(status_code=404, detail="Recurring invoice not found")
    inv = _generate_invoice_from_template(ri, db)
    return {"ok": True, "invoice_id": inv.id, "invoice_number": inv.invoice_number}


# ── Background: generate due recurring invoices ───────────────────────────────
def generate_due_recurring_invoices():
    """Called on startup and should be run daily."""
    db = SessionLocal()
    try:
        from database import RecurringInvoice
        now = datetime.utcnow()
        due = db.query(RecurringInvoice).filter(
            RecurringInvoice.is_active == True,
            RecurringInvoice.next_run_date <= now,
        ).all()

        generated = 0
        for ri in due:
            try:
                _generate_invoice_from_template(ri, db)
                generated += 1
            except Exception as e:
                logger.warning(f"Failed to generate recurring invoice {ri.id}: {e}")

        if generated:
            logger.info(f"Recurring invoices: generated {generated}")
    except Exception as e:
        logger.error(f"Recurring invoice job failed: {e}")
    finally:
        db.close()


def _generate_invoice_from_template(ri, db: Session) -> Invoice:
    """Create an Invoice from a RecurringInvoice template and advance next_run_date."""
    now = datetime.utcnow()

    # Compute next invoice number for this company
    last = (
        db.query(Invoice)
        .filter(Invoice.company_id == ri.company_id)
        .order_by(Invoice.id.desc())
        .first()
    )
    try:
        last_num = int(last.invoice_number.split("-")[-1]) if last else 0
    except Exception:
        last_num = 0
    inv_number = f"INV-{last_num + 1:04d}"

    vat_rate = 0.15 if ri.vat_applicable else 0.0
    vat_amount = round(ri.amount * vat_rate, 2)
    total_amount = round(ri.amount + vat_amount, 2)

    inv = Invoice(
        company_id=ri.company_id,
        invoice_number=inv_number,
        client_name=ri.client_name,
        client_email=ri.client_email,
        description=ri.description or f"Recurring invoice — {ri.frequency}",
        amount=ri.amount,
        vat_amount=vat_amount,
        total_amount=total_amount,
        currency=ri.currency or "ZAR",
        exchange_rate=1.0,
        status=InvoiceStatus.sent,
        issue_date=now,
        due_date=now + timedelta(days=30),
        portal_token=str(uuid.uuid4()).replace("-", ""),
        portal_token_created_at=now,
    )
    db.add(inv)

    # Post journal entry
    try:
        import journal as je
        db.flush()  # get inv.id
        je.post_invoice(inv.id, db)
    except Exception as e:
        logger.warning(f"Journal post failed for recurring inv: {e}")

    # Advance next run date
    ri.last_run_date = now
    ri.next_run_date = _next_run(ri.frequency, now)
    ri.invoices_generated = (ri.invoices_generated or 0) + 1

    db.commit()
    db.refresh(inv)
    return inv
