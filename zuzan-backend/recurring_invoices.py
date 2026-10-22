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
from journal import company_vat_registered as _vatreg
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
    supply_type:    Optional[str]  = None   # "standard" | "zero_rated" | "exempt"
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
    supply_type:    Optional[str]  = None
    currency:       Optional[str]  = None
    frequency:      Optional[str]  = None
    is_active:      Optional[bool] = None


_FREQUENCIES = ("weekly", "monthly", "quarterly", "annually")


def _check_frequency(freq):
    if (freq or "").strip().lower() not in _FREQUENCIES:
        raise HTTPException(status_code=400, detail="frequency must be weekly, monthly, quarterly or annually")
    return freq.strip().lower()


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
        "supply_type":        getattr(ri, "supply_type", None),
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
    freq = _check_frequency(body.frequency)
    if not body.amount or body.amount <= 0:
        raise HTTPException(status_code=400, detail="The amount must be greater than zero.")
    if not (body.client_name or "").strip():
        raise HTTPException(status_code=400, detail="client_name is required.")
    try:
        start = datetime.fromisoformat(body.start_date)
    except Exception:
        raise HTTPException(status_code=400, detail="start_date must be an ISO date, e.g. 2026-11-01.")
    ri = RecurringInvoice(
        company_id=current_user.company_id,
        client_name=body.client_name,
        client_email=body.client_email,
        description=body.description,
        amount=body.amount,
        vat_applicable=body.vat_applicable if body.vat_applicable is not None else True,
        supply_type=(body.supply_type if body.supply_type in ("standard", "zero_rated", "exempt") else None),
        currency=body.currency or "ZAR",
        frequency=freq,
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
    changes = body.dict(exclude_unset=True)
    if "frequency" in changes:
        changes["frequency"] = _check_frequency(changes["frequency"])
    if "amount" in changes and (changes["amount"] is None or changes["amount"] <= 0):
        raise HTTPException(status_code=400, detail="The amount must be greater than zero.")
    for field, value in changes.items():
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
    inv = _generate_invoice_from_template(ri, db, advance=False)   # a manual run must not move the schedule
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


def _generate_invoice_from_template(ri, db: Session, advance: bool = True) -> Invoice:
    """Create an Invoice from a RecurringInvoice template and (by default) advance next_run_date."""
    now = datetime.utcnow()

    # Compute next invoice number for this company
    from companies import next_invoice_number
    inv_number = next_invoice_number(ri.company_id, db)

    _st = getattr(ri, "supply_type", None)
    vat_rate = 0.15 if (ri.vat_applicable and _st not in ("zero_rated", "exempt") and _vatreg(db, ri.company_id)) else 0.0
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
        supply_type=_st,
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
        je.post_invoice_raised(inv, db)
    except Exception as e:
        # Loud on purpose: repair_unposted_invoices() posts it on the next start-up, but someone should see this.
        logger.error(f"Journal post failed for recurring invoice {inv.invoice_number}: {e}")

    ri.last_run_date = now
    ri.invoices_generated = (ri.invoices_generated or 0) + 1
    if advance:
        # Step from the SCHEDULED date (not from "now") so a 31st/1st/etc. cycle does not drift; if the job was
        # down for several periods, skip the missed ones rather than flooding the client with back-to-back invoices.
        nxt = _next_run(ri.frequency, ri.next_run_date or now)
        while nxt <= now:
            nxt = _next_run(ri.frequency, nxt)
        ri.next_run_date = nxt

    db.commit()
    db.refresh(inv)
    return inv


def repair_unposted_invoices() -> int:
    """One-off safety net run at start-up: issued invoices (sent / overdue / paid) that have no active raised
    ledger entry get one. Before 2026-10 recurring invoices called a journal function that did not exist, so they
    never reached the ledger. Idempotent - invoices that already have their entries are never touched."""
    from database import JournalEntry
    db = SessionLocal()
    fixed = 0
    try:
        import journal as je
        reversed_ids = {r[0] for r in db.query(JournalEntry.is_reversal_of).filter(JournalEntry.is_reversal_of.isnot(None)).all()}
        raised = {(e.company_id, e.source_id) for e in db.query(JournalEntry.id, JournalEntry.company_id, JournalEntry.source_id)
                  .filter(JournalEntry.source == "invoice").all() if e.id not in reversed_ids}
        paid_posted = {(e.company_id, e.source_id) for e in db.query(JournalEntry.company_id, JournalEntry.source_id)
                       .filter(JournalEntry.source == "invoice_payment").all()}
        for inv in db.query(Invoice).filter(Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue, InvoiceStatus.partial, InvoiceStatus.paid])).all():
            try:
                changed = False
                if (inv.company_id, inv.id) not in raised:
                    je.init_accounts(inv.company_id, db)
                    je.post_invoice_raised(inv, db); changed = True
                if inv.status in (InvoiceStatus.paid, InvoiceStatus.partial) and (inv.company_id, inv.id) not in paid_posted:
                    je.post_invoice_paid(inv, db); changed = True
                if changed:
                    db.commit(); fixed += 1
            except Exception as e:
                db.rollback()
                logger.warning(f"Could not repair postings for invoice {inv.id}: {e}")
        if fixed:
            logger.warning(f"Repaired missing ledger postings for {fixed} invoice(s)")
    except Exception as e:
        logger.error(f"Invoice posting repair failed: {e}")
    finally:
        db.close()
    return fixed
