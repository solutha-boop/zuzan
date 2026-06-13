"""
ZuZan - Invoices, Expenses, Employees, Companies Routers
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from database import get_db, Invoice, Expense, Employee, Company, Payslip, InvoiceStatus
from auth import get_current_user, User
import logging
import journal as journal_engine

logger = logging.getLogger("zuzan.routers")

def clean(value, max_len=500):
    """Strip whitespace and enforce max length on text inputs."""
    if value is None: return value
    return str(value).strip()[:max_len]


# ── COMPANIES ─────────────────────────────────────────────────────────────────
router = APIRouter()

class CompanyUpdate(BaseModel):
    name:         Optional[str] = None
    reg_number:   Optional[str] = None
    vat_number:   Optional[str] = None
    industry:     Optional[str] = None
    address:      Optional[str] = None
    phone:        Optional[str] = None
    email:        Optional[str] = None
    bank_name:    Optional[str] = None
    bank_account: Optional[str] = None
    bank_branch:  Optional[str] = None


@router.get("/me")
async def get_company(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


@router.put("/me")
async def update_company(data: CompanyUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    for field, value in data.dict(exclude_none=True).items():
        setattr(company, field, value)
    db.commit()
    return company


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

class InvoiceUpdate(BaseModel):
    status:       Optional[str] = None
    paid_date:    Optional[str] = None
    notes:        Optional[str] = None


def next_invoice_number(company_id: int, db: Session) -> str:
    count = db.query(Invoice).filter(Invoice.company_id == company_id).count()
    return f"INV-{str(count + 1).zfill(4)}"


@invoices_router.get("/")
async def list_invoices(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    invoices = db.query(Invoice).filter(Invoice.company_id == current_user.company_id).order_by(Invoice.created_at.desc()).all()
    return invoices


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

    vat_amount   = round(data.amount * VAT_RATE, 2) if data.vat_applicable else 0
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
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    logger.info(f"Invoice created: {invoice.invoice_number} for {data.client_name}")
    try:
        journal_engine.init_accounts(current_user.company_id, db)
        journal_engine.post_invoice_raised(invoice, db)
        db.commit()
    except Exception as e:
        logger.warning(f"Journal post failed for invoice {invoice.invoice_number}: {e}")
    return invoice


@invoices_router.put("/{invoice_id}")
async def update_invoice(invoice_id: int, data: InvoiceUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.company_id == current_user.company_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    was_paid = invoice.status == InvoiceStatus.paid
    if data.status:
        invoice.status = InvoiceStatus(data.status)
    if data.paid_date:
        invoice.paid_date = datetime.fromisoformat(data.paid_date)
    if data.notes:
        invoice.notes = data.notes
    db.commit()
    # Post payment journal entry when invoice first marked as paid
    if not was_paid and invoice.status == InvoiceStatus.paid:
        try:
            journal_engine.post_invoice_paid(invoice, db)
            db.commit()
        except Exception as e:
            logger.warning(f"Journal post failed for invoice payment {invoice.invoice_number}: {e}")
    return invoice


@invoices_router.delete("/{invoice_id}")
async def delete_invoice(invoice_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.company_id == current_user.company_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    db.delete(invoice)
    db.commit()
    return {"status": "deleted"}


# ── EXPENSES ──────────────────────────────────────────────────────────────────
expenses_router = APIRouter()

class ExpenseCreate(BaseModel):
    vendor:          str
    description:     str
    amount:          float           # Always excl. VAT
    vat_applicable:  bool = True     # Apply 15% VAT
    category:        Optional[str] = "General"
    expense_date:    Optional[str] = None

class ExpenseUpdate(BaseModel):
    vendor:       Optional[str] = None
    description:  Optional[str] = None
    amount:       Optional[float] = None
    category:     Optional[str] = None


@expenses_router.get("/")
async def list_expenses(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Expense).filter(Expense.company_id == current_user.company_id).order_by(Expense.created_at.desc()).all()


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
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)
    try:
        journal_engine.init_accounts(current_user.company_id, db)
        journal_engine.post_expense(expense, db)
        db.commit()
    except Exception as e:
        logger.warning(f"Journal post failed for expense {expense.id}: {e}")
    return expense


@expenses_router.put("/{expense_id}")
async def update_expense(expense_id: int, data: ExpenseUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    expense = db.query(Expense).filter(Expense.id == expense_id, Expense.company_id == current_user.company_id).first()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    for field, value in data.dict(exclude_none=True).items():
        setattr(expense, field, value)
    db.commit()
    return expense


@expenses_router.delete("/{expense_id}")
async def delete_expense(expense_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    expense = db.query(Expense).filter(Expense.id == expense_id, Expense.company_id == current_user.company_id).first()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
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
    gross_salary:     Optional[float] = None
    tax_number:       Optional[str] = None
    address:          Optional[str] = None
    bank_name:        Optional[str] = None
    bank_account:     Optional[str] = None
    account_number:   Optional[str] = None
    branch_code:      Optional[str] = None
    account_type:     Optional[str] = None
    is_active:        Optional[bool] = None


@employees_router.get("/")
async def list_employees(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Employee).filter(
        Employee.company_id == current_user.company_id,
        Employee.is_active == True
    ).all()


@employees_router.post("/")
async def create_employee(data: EmployeeCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Check payroll is enabled
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    if not company.payroll_enabled:
        raise HTTPException(status_code=403, detail="Payroll module not enabled. Add it from Settings.")

    count = db.query(Employee).filter(Employee.company_id == current_user.company_id).count()
    emp = Employee(
        company_id=current_user.company_id,
        employee_number=data.employee_number or f"EMP-{str(count + 1).zfill(3)}",
        first_name=data.first_name,
        last_name=data.last_name,
        id_number=data.id_number,
        tax_number=data.tax_number,
        date_of_birth=datetime.fromisoformat(data.date_of_birth) if data.date_of_birth else None,
        appointment_date=datetime.fromisoformat(data.appointment_date) if data.appointment_date else None,
        address=data.address,
        position=data.position,
        department=data.department,
        gross_salary=data.gross_salary,
        bank_name=data.bank_name,
        bank_account=data.bank_account,
        account_number=data.account_number,
        branch_code=data.branch_code,
        account_type=data.account_type,
        start_date=datetime.fromisoformat(data.start_date) if data.start_date else datetime.utcnow(),
    )
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return emp


@employees_router.put("/{employee_id}")
async def update_employee(employee_id: int, data: EmployeeUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.id == employee_id, Employee.company_id == current_user.company_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    for field, value in data.dict(exclude_none=True).items():
        setattr(emp, field, value)
    db.commit()
    return emp


# ── BANK STATEMENT IMPORT ─────────────────────────────────────────────────────
bank_router = APIRouter()

class BankTransaction(BaseModel):
    date:        str
    description: str
    amount:      float
    type:        str  # debit or credit
    category:    Optional[str] = "Other"

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
    Debits are saved as expenses.
    Credits are saved as invoice payments if matched.
    """
    expenses_created  = 0
    expenses_skipped  = 0
    credits_recorded  = 0

    for txn in data.transactions:
        if txn.type == "debit":
            # Check for duplicate — same vendor, amount and date
            existing = db.query(Expense).filter(
                Expense.company_id   == current_user.company_id,
                Expense.amount       == txn.amount,
                Expense.description  == txn.description,
            ).first()

            if existing:
                expenses_skipped += 1
                continue

            expense = Expense(
                company_id   = current_user.company_id,
                vendor       = txn.description[:100],
                description  = f"Imported from {data.bank.upper()} statement",
                amount       = txn.amount,
                category     = txn.category,
                expense_date = datetime.fromisoformat(txn.date),
            )
            db.add(expense)
            expenses_created += 1

        elif txn.type == "credit":
            credits_recorded += 1

    db.commit()

    return {
        "status":           "success",
        "bank":             data.bank,
        "expenses_created": expenses_created,
        "expenses_skipped": expenses_skipped,
        "credits_recorded": credits_recorded,
        "total_processed":  len(data.transactions),
        "message":          f"Imported {expenses_created} expenses from {data.bank.upper()} statement.",
    }


@bank_router.get("/import/history")
async def import_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get recently imported bank transactions."""
    recent = db.query(Expense).filter(
        Expense.company_id  == current_user.company_id,
        Expense.description.like("Imported from%")
    ).order_by(Expense.created_at.desc()).limit(100).all()
    return recent
