"""
ZuZan - Invoices, Expenses, Employees, Companies Routers
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from database import get_db, Invoice, Expense, Employee, Company, Payslip, InvoiceStatus
from auth import get_current_user, require_role, log_action, User
from crypto import encrypt_field, decrypt_field
from passlib.context import CryptContext
import logging
import os
import journal as journal_engine

_pin_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

logger = logging.getLogger("zuzan.routers")

def clean(value, max_len=500):
    """Strip whitespace and enforce max length on text inputs."""
    if value is None: return value
    return str(value).strip()[:max_len]


# ── COMPANIES ─────────────────────────────────────────────────────────────────
router = APIRouter()

class CompanyUpdate(BaseModel):
    name:                   Optional[str] = None
    reg_number:             Optional[str] = None
    vat_number:             Optional[str] = None
    industry:               Optional[str] = None
    address:                Optional[str] = None
    phone:                  Optional[str] = None
    email:                  Optional[str] = None
    bank_name:              Optional[str] = None
    bank_account:           Optional[str] = None
    bank_branch:            Optional[str] = None
    logo_url:               Optional[str] = None
    cipc_registration_date: Optional[str] = None  # ISO date — company incorporation anniversary


def _company_dict(c: Company) -> dict:
    """Return company as dict with bank fields decrypted."""
    return {
        "id": c.id, "name": c.name, "reg_number": c.reg_number,
        "vat_number": c.vat_number, "industry": c.industry,
        "address": c.address, "phone": c.phone, "email": c.email,
        "bank_name":    decrypt_field(c.bank_name),
        "bank_account": decrypt_field(c.bank_account),
        "bank_branch":  decrypt_field(c.bank_branch),
        "logo_url": c.logo_url, "plan": c.plan, "billing_cycle": c.billing_cycle,
        "subscription_status": c.subscription_status,
        "trial_ends": c.trial_ends.isoformat() if c.trial_ends else None,
        "payroll_enabled": c.payroll_enabled, "payroll_employees": c.payroll_employees,
        "cipc_registration_date": c.cipc_registration_date.isoformat() if c.cipc_registration_date else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


@router.get("/me")
async def get_company(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return _company_dict(company)


@router.put("/me")
async def update_company(data: CompanyUpdate, current_user: User = Depends(require_role("owner", "admin")), db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    for field, value in data.dict(exclude_none=True).items():
        if field in ("bank_name", "bank_account", "bank_branch"):
            setattr(company, field, encrypt_field(value))
        elif field == "cipc_registration_date":
            setattr(company, field, datetime.fromisoformat(value) if value else None)
        else:
            setattr(company, field, value)
    db.commit()
    return _company_dict(company)


class PayrollPinSet(BaseModel):
    pin: str  # 4–8 digit PIN

class PayrollPinVerify(BaseModel):
    pin: str

@router.put("/payroll-pin")
async def set_payroll_pin(data: PayrollPinSet, current_user: User = Depends(require_role("owner")), db: Session = Depends(get_db)):
    if not data.pin.isdigit() or not (4 <= len(data.pin) <= 8):
        raise HTTPException(status_code=400, detail="PIN must be 4–8 digits.")
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    company.payroll_pin_hash = _pin_ctx.hash(data.pin)
    db.commit()
    return {"status": "ok", "message": "Payroll PIN updated."}

@router.post("/verify-payroll-pin")
async def verify_payroll_pin(data: PayrollPinVerify, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    if not company.payroll_pin_hash:
        return {"valid": True, "pin_set": False}  # No PIN configured — allow access
    valid = _pin_ctx.verify(data.pin, company.payroll_pin_hash)
    return {"valid": valid, "pin_set": True}

@router.get("/payroll-pin-status")
async def payroll_pin_status(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    return {"pin_set": bool(company.payroll_pin_hash)}


# Keep router as companies_router
companies_router = router


# ── INVOICES ──────────────────────────────────────────────────────────────────
invoices_router = APIRouter()

VAT_RATE = 0.15  # SA standard VAT rate

class InvoiceCreate(BaseModel):
    client_name:     str
    client_email:    Optional[str] = None
    description:     str
    amount:          float           # Always excl. VAT
    vat_applicable:  bool = True     # Apply 15% VAT
    due_date:        Optional[str] = None
    notes:           Optional[str] = None
    currency:            Optional[str] = "ZAR"
    exchange_rate:       Optional[float] = 1.0
    vat_amount_override: Optional[float] = None  # Manual VAT for non-ZAR invoices
    cogs_amount:         Optional[float] = None  # If set, post DR Cost of Sales / CR Inventory for this amount

class InvoiceUpdate(BaseModel):
    client_name:     Optional[str]   = None
    description:     Optional[str]   = None
    amount:          Optional[float] = None   # excl. VAT
    due_date:        Optional[str]   = None
    status:          Optional[str]   = None
    paid_date:       Optional[str]   = None
    notes:           Optional[str]   = None
    paid_amount_zar: Optional[float] = None  # ZAR actually received on payment


def next_invoice_number(company_id: int, db: Session) -> str:
    from sqlalchemy import func as _func
    last = db.query(_func.max(Invoice.id)).filter(Invoice.company_id == company_id).scalar() or 0
    # Use MAX(id) + 1 so deletions don't cause collisions
    existing_numbers = {
        row[0] for row in
        db.query(Invoice.invoice_number).filter(Invoice.company_id == company_id).all()
    }
    n = last + 1
    candidate = f"INV-{str(n).zfill(4)}"
    while candidate in existing_numbers:
        n += 1
        candidate = f"INV-{str(n).zfill(4)}"
    return candidate


@invoices_router.get("/")
async def list_invoices(
    limit: Optional[int] = None,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # limit/offset are optional (scale fix 2026-07-03): omitted = return all rows,
    # exactly as before, so existing frontend calls are unaffected.
    try:
        q = db.query(Invoice).filter(Invoice.company_id == current_user.company_id).order_by(Invoice.created_at.desc())
        if offset:
            q = q.offset(offset)
        if limit is not None:
            q = q.limit(limit)
        return q.all()
    except Exception as e:
        # Fallback: column may not exist yet in production DB — query without new columns
        logger.warning(f"Invoice ORM query failed ({e}), falling back to safe column list")
        db.rollback()
        from sqlalchemy import text as _text
        page_sql = ""
        if limit is not None:
            page_sql = f" LIMIT {int(limit)} OFFSET {int(offset or 0)}"
        rows = db.execute(_text(
            "SELECT id, company_id, invoice_number, client_name, client_email, "
            "description, amount, vat_amount, total_amount, currency, exchange_rate, "
            "paid_amount_zar, due_date, notes, status, issue_date, paid_date, created_at "
            "FROM invoices WHERE company_id = :cid ORDER BY created_at DESC" + page_sql
        ), {"cid": current_user.company_id})
        cols = list(rows.keys())
        return [dict(zip(cols, r)) for r in rows]


@invoices_router.post("/")
async def create_invoice(data: InvoiceCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Check plan invoice limits
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    limits = {"starter": 20, "professional": 50, "business": 999999}
    limit = limits.get(company.plan, 20)

    # Count this month's invoices
    now = datetime.utcnow()
    monthly_count = db.query(Invoice).filter(
        Invoice.company_id == current_user.company_id,
        Invoice.created_at >= datetime(now.year, now.month, 1)
    ).count()

    if monthly_count >= limit:
        raise HTTPException(status_code=403, detail=f"Monthly invoice limit ({limit}) reached. Upgrade your plan.")

    if data.currency and data.currency != "ZAR" and data.vat_amount_override is not None:
        vat_amount = round(data.vat_amount_override, 2)   # User-specified VAT for foreign currency
    else:
        vat_amount = round(data.amount * VAT_RATE, 2) if data.vat_applicable else 0
    total_amount = round(data.amount + vat_amount, 2)

    invoice = Invoice(
        company_id=current_user.company_id,
        invoice_number=next_invoice_number(current_user.company_id, db),
        client_name=clean(data.client_name, 200),
        client_email=clean(data.client_email, 200),
        description=clean(data.description, 1000),
        amount=data.amount,
        vat_amount=vat_amount,
        total_amount=total_amount,
        due_date=datetime.fromisoformat(data.due_date) if data.due_date else None,
        notes=clean(data.notes, 2000),
        status=InvoiceStatus.sent,
        currency=data.currency or "ZAR",
        exchange_rate=data.exchange_rate or 1.0,
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    logger.info(f"Invoice created: {invoice.invoice_number} for {data.client_name}")
    try:
        journal_engine.init_accounts(current_user.company_id, db)
        journal_engine.post_invoice_raised(invoice, db)
        # Optional COGS entry: DR Cost of Sales (5000) / CR Inventory at Cost (1200)
        if data.cogs_amount and data.cogs_amount > 0:
            journal_engine.post_invoice_cogs(invoice, round(data.cogs_amount, 2), db)
        db.commit()
    except Exception as e:
        logger.error(f"Journal post failed for invoice {invoice.invoice_number}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Invoice created but journal entry failed: {e}. Invoice has been rolled back — please retry.",
        )
    return invoice


@invoices_router.put("/{invoice_id}")
async def update_invoice(invoice_id: int, data: InvoiceUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.company_id == current_user.company_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    was_paid = invoice.status == InvoiceStatus.paid
    if data.client_name:
        invoice.client_name = data.client_name
    if data.description:
        invoice.description = data.description
    if data.amount is not None:
        invoice.amount       = data.amount
        invoice.vat_amount   = round(data.amount * 0.15, 2)
        invoice.total_amount = round(data.amount * 1.15, 2)
    if data.due_date is not None:
        invoice.due_date = datetime.fromisoformat(data.due_date) if data.due_date else None
    if data.status:
        invoice.status = InvoiceStatus(data.status)
    if data.paid_date:
        invoice.paid_date = datetime.fromisoformat(data.paid_date)
    # If being marked paid with no paid_date, default to now so date-filtered reports include it
    if not was_paid and invoice.status == InvoiceStatus.paid and not invoice.paid_date:
        invoice.paid_date = datetime.utcnow()
    if data.notes:
        invoice.notes = data.notes
    if data.paid_amount_zar is not None:
        invoice.paid_amount_zar = data.paid_amount_zar
    # Post payment journal entry when invoice first marked as paid.
    # Commit once only AFTER both the status update and the journal entry succeed —
    # this keeps them atomic so a journal failure rolls back the invoice status too.
    if not was_paid and invoice.status == InvoiceStatus.paid:
        try:
            journal_engine.post_invoice_paid(invoice, db)
            db.commit()
        except Exception as e:
            logger.error(f"Journal post failed for invoice payment {invoice.invoice_number}: {e}")
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Payment recording failed — journal entry could not be posted: {e}. Please retry.",
            )
    else:
        db.commit()
    return invoice


@invoices_router.delete("/{invoice_id}")
async def delete_invoice(invoice_id: int, current_user: User = Depends(require_role("owner", "admin")), db: Session = Depends(get_db)):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.company_id == current_user.company_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    # Reverse all journal entries linked to this invoice before deleting, so that
    # AR control account (1100), Sales Revenue (4000), and Bank (1000) remain accurate.
    # Sources to reverse: "invoice" (raised), "invoice_payment" (paid), "invoice_cogs" (COGS).
    try:
        journal_engine.init_accounts(current_user.company_id, db)
        reason = f"Invoice deleted — {invoice.invoice_number} ({invoice.client_name})"
        for src in ("invoice", "invoice_payment", "invoice_cogs"):
            journal_engine.reverse_journal_entries(
                current_user.company_id, src, invoice.id, db, reason=reason
            )
        db.commit()
    except Exception as e:
        logger.error(f"Journal reversal failed for invoice {invoice.invoice_number}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Invoice deletion aborted — journal reversal failed: {e}. Please retry.",
        )
    db.delete(invoice)
    db.commit()
    return {"status": "deleted"}



@invoices_router.post("/{invoice_id}/send")
async def send_invoice(invoice_id: int, current_user: User = Depends(require_role("owner","admin","accountant")), db: Session = Depends(get_db)):
    """Generate portal token (if needed), mark invoice as sent, and email the client."""
    import uuid as _uuid
    from datetime import datetime as _dt
    from email_service import send_invoice_email

    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.company_id == current_user.company_id
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.status == InvoiceStatus.paid:
        raise HTTPException(status_code=400, detail="Invoice is already paid.")

    # Generate portal token if missing
    if not invoice.portal_token:
        invoice.portal_token = _uuid.uuid4().hex
        invoice.portal_token_created_at = _dt.utcnow()

    # Mark as sent
    invoice.status = InvoiceStatus.sent
    db.commit()
    db.refresh(invoice)

    portal_url = f"{os.environ.get('FRONTEND_URL','https://zuzan-app.onrender.com')}/portal/{invoice.portal_token}"

    # Send email if client email is known
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    email_sent = False
    client_email = getattr(invoice, "client_email", None) or ""
    if client_email:
        try:
            send_invoice_email(
                client_email=client_email,
                client_name=invoice.client_name or "Client",
                company_name=company.name if company else "ZuZan",
                invoice_number=invoice.invoice_number,
                description=invoice.description or "",
                total_amount=invoice.total_amount or 0,
                currency=invoice.currency or "ZAR",
                due_date=invoice.due_date.strftime("%d %b %Y") if invoice.due_date else "",
                portal_token=invoice.portal_token,
            )
            email_sent = True
        except Exception as e:
            logger.warning(f"Invoice email failed (non-fatal): {e}")

    return {
        "status":       "sent",
        "portal_token": invoice.portal_token,
        "portal_url":   portal_url,
        "email_sent":   email_sent,
    }


# ── EXPENSES ──────────────────────────────────────────────────────────────────
expenses_router = APIRouter()

class ExpenseCreate(BaseModel):
    vendor:          str
    description:     str
    amount:          float           # Always excl. VAT
    vat_applicable:  bool = True     # Apply 15% VAT
    category:        Optional[str] = "General"
    expense_date:    Optional[str] = None
    is_on_credit:    bool = False    # True = purchased on credit; journals to AP (2000) not Bank (1000)

class ExpenseUpdate(BaseModel):
    vendor:          Optional[str] = None
    description:     Optional[str] = None
    amount:          Optional[float] = None   # excl. VAT — vat_amount is recalculated automatically
    vat_applicable:  Optional[bool] = None    # if omitted, inferred from existing vat_amount
    category:        Optional[str] = None
    is_on_credit:    Optional[bool] = None


@expenses_router.get("/")
async def list_expenses(
    limit: Optional[int] = None,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Optional pagination (scale fix 2026-07-03) — omitted params return all rows as before.
    q = db.query(Expense).filter(Expense.company_id == current_user.company_id).order_by(Expense.created_at.desc())
    if offset:
        q = q.offset(offset)
    if limit is not None:
        q = q.limit(limit)
    return q.all()


@expenses_router.post("/")
async def create_expense(data: ExpenseCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    exp_vat    = round(data.amount * VAT_RATE, 2) if data.vat_applicable else 0
    exp_total  = round(data.amount + exp_vat, 2)

    expense = Expense(
        company_id=current_user.company_id,
        vendor=clean(data.vendor, 200),
        description=clean(data.description, 1000),
        amount=exp_total,
        vat_amount=exp_vat,
        category=clean(data.category, 200),
        expense_date=datetime.fromisoformat(data.expense_date) if data.expense_date else datetime.utcnow(),
        is_on_credit=data.is_on_credit,
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)
    try:
        journal_engine.init_accounts(current_user.company_id, db)
        journal_engine.post_expense(expense, db)
        db.commit()
    except Exception as e:
        logger.error(f"Journal post failed for expense {expense.id}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Expense saved but journal entry failed: {e}. Expense has been rolled back — please retry.",
        )
    return expense


@expenses_router.put("/{expense_id}")
async def update_expense(expense_id: int, data: ExpenseUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    expense = db.query(Expense).filter(Expense.id == expense_id, Expense.company_id == current_user.company_id).first()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    # Apply non-amount fields first
    non_amount_fields = {k: v for k, v in data.dict(exclude_none=True).items()
                         if k not in ("amount", "vat_applicable")}
    for field, value in non_amount_fields.items():
        setattr(expense, field, value)

    # If amount is being updated, recalculate vat_amount to keep it consistent.
    # expense.amount is stored VAT-inclusive; data.amount is excl-VAT (matching create convention).
    if data.amount is not None:
        # Determine whether VAT applies: explicit flag > infer from existing vat_amount
        apply_vat = data.vat_applicable if data.vat_applicable is not None else (
            (expense.vat_amount or 0) > 0
        )
        new_vat = round(data.amount * VAT_RATE, 2) if apply_vat else 0.0
        new_total = round(data.amount + new_vat, 2)

        # Post a correcting journal entry (delta) if the stored amount has changed
        old_total = expense.amount or 0
        old_vat   = expense.vat_amount or 0
        if abs(new_total - old_total) > 0.01:
            try:
                journal_engine.init_accounts(current_user.company_id, db)
                # Build a temporary expense-like object with the delta values
                # Reversing entry: negate old amounts, then post new amounts
                class _Delta:
                    pass
                old_exp = _Delta()
                old_exp.company_id  = expense.company_id
                old_exp.amount      = old_total
                old_exp.vat_amount  = old_vat
                old_exp.vendor      = expense.vendor
                old_exp.description = f"[REVERSAL] {expense.description or ''}"
                old_exp.category    = expense.category
                old_exp.expense_date = expense.expense_date
                old_exp.id          = expense.id
                # Reverse old entry by swapping debits/credits (negate amounts trick:
                # post a negative-amount expense using a manual credit/debit swap)
                from database import Account, JournalEntry, JournalLine, AccountType
                existing_entries = db.query(JournalEntry).filter(
                    JournalEntry.company_id == current_user.company_id,
                    JournalEntry.source == "expense",
                    JournalEntry.source_id == expense.id,
                ).all()
                for entry in existing_entries:
                    rev_entry = JournalEntry(
                        company_id  = current_user.company_id,
                        date        = datetime.utcnow(),
                        description = f"Expense correction (reversal) — {expense.vendor}",
                        reference   = f"REV-EXP-{expense.id}",
                        source      = "expense_reversal",
                        source_id   = expense.id,
                    )
                    db.add(rev_entry)
                    db.flush()
                    for line in entry.lines:
                        db.add(JournalLine(
                            entry_id   = rev_entry.id,
                            account_id = line.account_id,
                            debit      = line.credit,   # swap
                            credit     = line.debit,    # swap
                            description= f"Reversal of line {line.id}",
                        ))
                # Now post the new entry
                # Temporarily set values for post_expense
                expense.amount     = new_total
                expense.vat_amount = new_vat
                journal_engine.post_expense(expense, db)
                db.commit()
            except Exception as e:
                logger.error(f"Journal correction failed for expense {expense.id}: {e}")
                # Non-fatal — still save the field update

        expense.amount     = new_total
        expense.vat_amount = new_vat

    if data.is_on_credit is not None:
        expense.is_on_credit = data.is_on_credit

    db.commit()
    return expense


@expenses_router.post("/{expense_id}/pay")
async def pay_expense(
    expense_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Mark an on-credit expense as paid and clear the Accounts Payable balance.
    Posts journal entry: DR Accounts Payable (2000) / CR Bank / Cash (1000).
    Only valid for expenses recorded with is_on_credit=True that have not yet been paid.
    """
    expense = db.query(Expense).filter(
        Expense.id == expense_id,
        Expense.company_id == current_user.company_id,
    ).first()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    if not expense.is_on_credit:
        raise HTTPException(
            status_code=400,
            detail="This expense was not recorded on credit. Only on-credit expenses can be paid via this endpoint.",
        )
    if expense.paid_at:
        raise HTTPException(status_code=400, detail="Expense has already been marked as paid.")

    expense.paid_at = datetime.utcnow()
    db.commit()
    db.refresh(expense)

    try:
        journal_engine.init_accounts(current_user.company_id, db)
        journal_engine.post_expense_paid(expense, db)
        db.commit()
    except Exception as e:
        logger.error(f"Journal post failed for expense payment {expense.id}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Payment recording failed — journal entry could not be posted: {e}. Please retry.",
        )
    return expense


@expenses_router.delete("/{expense_id}")
async def delete_expense(expense_id: int, current_user: User = Depends(require_role("owner", "admin")), db: Session = Depends(get_db)):
    expense = db.query(Expense).filter(Expense.id == expense_id, Expense.company_id == current_user.company_id).first()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    # Reverse journal entry for this expense before deleting, so that the
    # Expense account, VAT Input (1300), and Bank (1000) remain accurate.
    try:
        journal_engine.init_accounts(current_user.company_id, db)
        journal_engine.reverse_journal_entries(
            current_user.company_id, "expense", expense.id, db,
            reason=f"Expense deleted — {expense.vendor}: {expense.description or ''}",
        )
        db.commit()
    except Exception as e:
        logger.error(f"Journal reversal failed for expense {expense.id}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Expense deletion aborted — journal reversal failed: {e}. Please retry.",
        )
    db.delete(expense)
    db.commit()
    return {"status": "deleted"}


# ── EMPLOYEES ─────────────────────────────────────────────────────────────────
employees_router = APIRouter()

class EmployeeCreate(BaseModel):
    first_name:       str
    last_name:        str
    id_number:        Optional[str] = None
    tax_number:       Optional[str] = None
    date_of_birth:    Optional[str] = None
    appointment_date: Optional[str] = None
    address:          Optional[str] = None
    position:         Optional[str] = None
    department:       Optional[str] = None
    grade:            Optional[str] = None           # e.g. "A", "B2", "Senior"
    employment_type:  Optional[str] = "salaried"    # "salaried" | "hourly"
    hourly_rate:      Optional[float] = None         # explicit rate for hourly employees
    gross_salary:     float
    employee_number:  Optional[str] = None
    bank_name:        Optional[str] = None
    bank_account:     Optional[str] = None
    account_number:   Optional[str] = None
    branch_code:      Optional[str] = None
    account_type:     Optional[str] = None
    start_date:       Optional[str] = None

class EmployeeUpdate(BaseModel):
    position:         Optional[str] = None
    department:       Optional[str] = None
    grade:            Optional[str] = None
    employment_type:  Optional[str] = None
    hourly_rate:      Optional[float] = None
    gross_salary:     Optional[float] = None
    tax_number:       Optional[str] = None
    address:          Optional[str] = None
    bank_name:        Optional[str] = None
    bank_account:     Optional[str] = None
    account_number:   Optional[str] = None
    branch_code:      Optional[str] = None
    account_type:     Optional[str] = None
    is_active:        Optional[bool] = None


def _employee_dict(e: Employee) -> dict:
    """Return employee as dict with bank fields decrypted."""
    from payroll import bcea_hourly_rate
    return {
        "id": e.id, "company_id": e.company_id,
        "employee_number": e.employee_number,
        "first_name": e.first_name, "last_name": e.last_name,
        "id_number": e.id_number, "tax_number": e.tax_number,
        "date_of_birth": e.date_of_birth.isoformat() if e.date_of_birth else None,
        "appointment_date": e.appointment_date.isoformat() if e.appointment_date else None,
        "address": e.address, "position": e.position, "department": e.department,
        "grade": e.grade,
        "employment_type": e.employment_type or "salaried",
        "hourly_rate": e.hourly_rate,
        "hourly_rate_bcea": round(bcea_hourly_rate(e.gross_salary, e.hourly_rate), 4),
        "gross_salary": e.gross_salary,
        "bank_name":      decrypt_field(e.bank_name),
        "bank_account":   decrypt_field(e.bank_account),
        "account_number": decrypt_field(e.account_number),
        "branch_code":    decrypt_field(e.branch_code),
        "account_type": e.account_type,
        "start_date": e.start_date.isoformat() if e.start_date else None,
        "is_active": e.is_active,
    }


@employees_router.get("/")
async def list_employees(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    emps = db.query(Employee).filter(
        Employee.company_id == current_user.company_id,
        Employee.is_active == True
    ).all()
    return [_employee_dict(e) for e in emps]


@employees_router.post("/")
async def create_employee(data: EmployeeCreate, current_user: User = Depends(require_role("owner", "admin")), db: Session = Depends(get_db)):
    # Check payroll is enabled
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    if not company.payroll_enabled:
        raise HTTPException(status_code=403, detail="Payroll module not enabled. Add it from Settings.")

    # Max-id seeded with collision check (scale fix 2026-07-03): count()+1
    # produced duplicate employee numbers after any employee was deleted.
    from sqlalchemy import func as _func
    _last = db.query(_func.max(Employee.id)).filter(Employee.company_id == current_user.company_id).scalar() or 0
    _existing = {
        row[0] for row in
        db.query(Employee.employee_number).filter(Employee.company_id == current_user.company_id).all()
    }
    _n = _last + 1
    _candidate = f"EMP-{str(_n).zfill(3)}"
    while _candidate in _existing:
        _n += 1
        _candidate = f"EMP-{str(_n).zfill(3)}"
    emp = Employee(
        company_id=current_user.company_id,
        employee_number=data.employee_number or _candidate,
        first_name=data.first_name,
        last_name=data.last_name,
        id_number=data.id_number,
        tax_number=data.tax_number,
        date_of_birth=datetime.fromisoformat(data.date_of_birth) if data.date_of_birth else None,
        appointment_date=datetime.fromisoformat(data.appointment_date) if data.appointment_date else None,
        address=data.address,
        position=data.position,
        department=data.department,
        grade=data.grade,
        employment_type=data.employment_type or "salaried",
        hourly_rate=data.hourly_rate,
        gross_salary=data.gross_salary,
        bank_name=encrypt_field(data.bank_name),
        bank_account=encrypt_field(data.bank_account),
        account_number=encrypt_field(data.account_number),
        branch_code=encrypt_field(data.branch_code),
        account_type=data.account_type,
        start_date=datetime.fromisoformat(data.start_date) if data.start_date else datetime.utcnow(),
    )
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return _employee_dict(emp)


_EMPLOYEE_BANK_FIELDS = {"bank_name", "bank_account", "account_number", "branch_code"}

@employees_router.put("/{employee_id}")
async def update_employee(employee_id: int, data: EmployeeUpdate, current_user: User = Depends(require_role("owner", "admin")), db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.id == employee_id, Employee.company_id == current_user.company_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    for field, value in data.dict(exclude_none=True).items():
        setattr(emp, field, encrypt_field(value) if field in _EMPLOYEE_BANK_FIELDS else value)
    db.commit()
    return _employee_dict(emp)


# ── BANK STATEMENT IMPORT ─────────────────────────────────────────────────────
bank_router = APIRouter()

class BankTransaction(BaseModel):
    date:           str
    description:    str
    amount:         float           # VAT-inclusive amount as it appears on the bank statement
    type:           str             # debit or credit
    category:       Optional[str] = "Other"
    vat_applicable: bool  = False   # legacy field — kept for backwards compat
    has_vat:        bool  = False   # set True to split out VAT (15%) on import
    vat_amount:     float = 0.0     # pre-calculated VAT amount from frontend

class BankImportRequest(BaseModel):
    bank:         str
    transactions: list[BankTransaction]

@bank_router.post("/import")
async def import_bank_statement(
    data: BankImportRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Import bank statement transactions into ZuZan.
    Debits  → saved as Expense records + journal entry (DR Expense / CR Bank).
    Credits → journal entry (DR Bank / CR Revenue) so income flows to P&L.
    """
    expenses_created  = 0
    expenses_skipped  = 0
    credits_recorded  = 0
    credits_skipped   = 0

    for txn in data.transactions:
        if txn.type == "debit":
            # Check for duplicate — same vendor, amount and date.
            # Audit fix 2026-07-04: the previous filter compared txn.description against
            # Expense.description, but imported expenses store the bank narrative in
            # `vendor` and a fixed "Imported from ..." string in `description` — so the
            # dedupe never matched and re-importing a statement duplicated every expense.
            existing = db.query(Expense).filter(
                Expense.company_id   == current_user.company_id,
                Expense.vendor       == txn.description[:100],
                Expense.amount       == txn.amount,
                Expense.expense_date == datetime.fromisoformat(txn.date),
            ).first()

            if existing:
                expenses_skipped += 1
                continue

            # Calculate VAT split if applicable (bank amount is VAT-inclusive).
            # Audit fix 2026-07-04: the frontend sends `has_vat` + a precomputed
            # `vat_amount` (never the legacy `vat_applicable`), so checking only
            # vat_applicable dropped the VAT split on every imported expense —
            # overstating P&L expenses and understating input VAT. Mirror the
            # credit branch (journal.post_bank_income): honor either flag, prefer
            # the provided vat_amount, and fall back to 15/115 back-calculation.
            if txn.has_vat or txn.vat_applicable:
                imp_vat   = round(float(txn.vat_amount or 0), 2)
                if imp_vat <= 0:
                    imp_vat = round(txn.amount * 0.15 / 1.15, 2)  # back-calculate from incl-VAT
                imp_total = txn.amount                            # store as-is (VAT-inclusive)
            else:
                imp_vat   = 0.0
                imp_total = txn.amount

            expense = Expense(
                company_id   = current_user.company_id,
                vendor       = txn.description[:100],
                description  = f"Imported from {data.bank.upper()} statement",
                amount       = imp_total,
                vat_amount   = imp_vat,
                category     = txn.category,
                expense_date = datetime.fromisoformat(txn.date),
            )
            db.add(expense)
            db.flush()  # get expense.id before journal post
            try:
                import journal as journal_engine
                journal_engine.init_accounts(current_user.company_id, db)
                journal_engine.post_expense(expense, db)
            except Exception as je:
                logger.warning(f"Journal post failed for bank import expense: {je}")
            expenses_created += 1

        elif txn.type == "credit":
            # Duplicate check (audit fix 2026-07-04): credits previously had NO dedupe,
            # so re-importing a statement re-posted the income journal entry and
            # double-counted revenue in every report. Match on the exact fields
            # post_bank_income writes: source, date, description, and the bank-debit
            # line amount. The query autoflushes entries posted earlier in this same
            # batch, so within-file duplicates are caught too. (Two genuinely identical
            # credits — same day, description and amount — must be imported manually.)
            from database import JournalEntry, JournalLine
            from datetime import date as _date
            dup_q = db.query(JournalEntry.id).join(
                JournalLine, JournalLine.entry_id == JournalEntry.id
            ).filter(
                JournalEntry.company_id  == current_user.company_id,
                JournalEntry.source      == "bank_import_income",
                JournalEntry.description == f"Bank income — {txn.description}",
                JournalLine.debit        == round(float(txn.amount or 0), 2),
            )
            try:
                dup_q = dup_q.filter(JournalEntry.date == _date.fromisoformat(txn.date))
            except Exception:
                pass  # unparseable date — post_bank_income falls back to today; match on description+amount only
            if dup_q.first():
                credits_skipped += 1
                continue

            # Post a journal entry so income flows into P&L and the balance sheet
            try:
                import journal as journal_engine
                journal_engine.init_accounts(current_user.company_id, db)
                journal_engine.post_bank_income(current_user.company_id, txn, db)
                credits_recorded += 1
            except Exception as je:
                logger.warning(f"Journal post failed for bank import income: {je}")
                credits_skipped += 1

    db.commit()

    return {
        "status":           "success",
        "bank":             data.bank,
        "expenses_created": expenses_created,
        "expenses_skipped": expenses_skipped,
        "credits_recorded": credits_recorded,
        "credits_skipped":  credits_skipped,
        "total_processed":  len(data.transactions),
        "message":          f"Imported {expenses_created} expenses and {credits_recorded} income entries from {len(data.transactions)} transactions.",
    }
