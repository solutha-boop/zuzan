from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from database import get_db, Budget, Expense, Invoice, JournalEntry, JournalLine, PurchaseOrder
from auth import get_current_user, User

router = APIRouter()

EXPENSE_CATS = [
    "Cost of Sales","Utilities","Telecoms","Office","Banking","Insurance",
    "Tax","Equipment","Travel","Salaries","Rent","Marketing","Professional Fees","Other"
]

def clean(value, max_len=500):
    if value is None: return value
    return str(value).strip()[:max_len]

class BudgetUpsert(BaseModel):
    year:       int
    month:      int
    category:   str
    amount:     float
    type:       str = "expense"   # "expense" or "income"
    department: Optional[str] = None

class BudgetBulkUpsert(BaseModel):
    entries: List[BudgetUpsert]


def _validate(entry: BudgetUpsert):
    if entry.type not in ("expense", "income"):
        raise HTTPException(400, "type must be 'expense' or 'income'")
    if not (1 <= entry.month <= 12):
        raise HTTPException(400, f"month must be 1-12 (got {entry.month})")
    if not (2000 <= entry.year <= 2100):
        raise HTTPException(400, f"year looks wrong ({entry.year})")
    if entry.amount is None or entry.amount != entry.amount or entry.amount < 0:
        raise HTTPException(400, "amount cannot be negative")
    if not (entry.category or "").strip():
        raise HTTPException(400, "category is required")


def _upsert(db: Session, company_id: int, entry: BudgetUpsert) -> Budget:
    """Insert or update a single budget entry."""
    _validate(entry)
    b = db.query(Budget).filter(
        Budget.company_id == company_id,
        Budget.year       == entry.year,
        Budget.month      == entry.month,
        Budget.category   == clean(entry.category, 200),
        Budget.type       == entry.type,
        Budget.department == (clean(entry.department, 200) if entry.department else None),
    ).first()
    if b:
        b.amount     = entry.amount
        b.updated_at = datetime.utcnow()
    else:
        b = Budget(
            company_id = company_id,
            year       = entry.year,
            month      = entry.month,
            category   = clean(entry.category, 200),
            type       = entry.type,
            department = clean(entry.department, 200) if entry.department else None,
            amount     = entry.amount,
        )
        db.add(b)
    return b


# ── LIST budgets for a year ───────────────────────────────────────────────────
@router.get("/")
async def list_budgets(
    year: int = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    year = year or datetime.utcnow().year
    items = db.query(Budget).filter(
        Budget.company_id == current_user.company_id,
        Budget.year == year,
    ).all()
    return [
        {
            "id": b.id, "year": b.year, "month": b.month,
            "category": b.category, "type": b.type,
            "department": b.department, "amount": b.amount,
        }
        for b in items
    ]


# ── UPSERT single entry ───────────────────────────────────────────────────────
@router.post("/")
async def upsert_budget(
    data: BudgetUpsert,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    b = _upsert(db, current_user.company_id, data)
    db.commit(); db.refresh(b)
    return {"id": b.id, "year": b.year, "month": b.month, "category": b.category, "amount": b.amount}


# ── BULK upsert (annual planning grid saves many cells at once) ───────────────
@router.post("/bulk")
async def bulk_upsert(
    data: BudgetBulkUpsert,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    for entry in data.entries:          # validate everything first: all or nothing
        _validate(entry)
    for entry in data.entries:
        _upsert(db, current_user.company_id, entry)
    db.commit()
    return {"saved": len(data.entries)}


# ── ACTUALS: actual spend/income per category per month for a year ─────────────
@router.get("/actuals")
async def get_actuals(
    year: int = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    year = year or datetime.utcnow().year
    cid  = current_user.company_id

    # Aggregate into a single dict keyed by (type, category, month) so multiple
    # income sources (invoices + bank imports) collapse into one "Revenue" row per month.
    totals: dict = {}

    def add(type_: str, category: str, month: int, amount: float):
        key = (type_, category, int(month))
        totals[key] = totals.get(key, 0.0) + float(amount or 0)

    # 1. Expenses (logged via Expense tab)
    for row in (
        db.query(
            Expense.category,
            extract("month", Expense.expense_date).label("month"),
            func.sum(Expense.amount - func.coalesce(Expense.vat_amount, 0)).label("total"),   # ex VAT, like the P&L
        )
        .filter(
            Expense.company_id == cid,
            extract("year", Expense.expense_date) == year,
        )
        .group_by(Expense.category, extract("month", Expense.expense_date))
        .all()
    ):
        add("expense", row.category or "Other", row.month, row.total)

    # 2. Revenue from paid invoices (ex VAT, converted to rand like the dashboard)
    from payroll import _received_zar
    for inv in db.query(Invoice).filter(Invoice.company_id == cid, Invoice.status.in_(["paid", "partial"]),
                                        Invoice.paid_date.isnot(None),
                                        extract("year", Invoice.paid_date) == year).all():
        total = _received_zar(inv)
        gross = inv.total_amount or 0
        ex_vat = total * ((inv.amount or 0) / gross) if gross else 0.0
        add("income", "Revenue", inv.paid_date.month, ex_vat)

    # 3. Revenue from bank CSV imports (journal entries with source="bank_import_income")
    for row in (
        db.query(
            extract("month", JournalEntry.date).label("month"),
            func.sum(JournalLine.credit).label("total"),
        )
        .join(JournalLine, JournalLine.entry_id == JournalEntry.id)
        .filter(
            JournalEntry.company_id == cid,
            JournalEntry.source == "bank_import_income",
            extract("year", JournalEntry.date) == year,
            JournalLine.credit > 0,
        )
        .group_by(extract("month", JournalEntry.date))
        .all()
    ):
        if row.total:
            add("income", "Revenue", row.month, row.total)

    # 4. Cost of Sales from received purchase orders: delivered value only, and stock bought for resale is an
    #    asset until it is sold (its cost arrives through the ledger's cost-of-sales entries below).
    from payroll import _po_cost_net, _stock_pl_cost
    from datetime import datetime as _dt
    for po in db.query(PurchaseOrder).filter(
            PurchaseOrder.company_id == cid,
            PurchaseOrder.status.in_(["received", "partial", "paid"]),
            PurchaseOrder.received_date.isnot(None),
            extract("year", PurchaseOrder.received_date) == year).all():
        add("expense", "Cost of Sales", po.received_date.month, _po_cost_net(po))
    for m in range(1, 13):
        stock_cost = _stock_pl_cost(db, cid, _dt(year, m, 1), _dt(year + (m == 12), (m % 12) + 1, 1))
        if stock_cost:
            add("expense", "Cost of Sales", m, stock_cost)

    # 5. Payroll cost and depreciation (both are in the dashboard's expenses, so they belong in the budget view too)
    from database import Payslip, Employee, DepreciationEntry
    for ps in (db.query(Payslip).join(Employee, Payslip.employee_id == Employee.id)
               .filter(Employee.company_id == cid, extract("year", Payslip.generated_at) == year).all()):
        add("expense", "Salaries", ps.generated_at.month, ps.total_cost or 0)
    for d in db.query(DepreciationEntry).filter(DepreciationEntry.company_id == cid,
                                                DepreciationEntry.period.like(f"{year}-%")).all():
        try:
            add("expense", "Depreciation", int(str(d.period)[5:7]), d.amount or 0)
        except ValueError:
            pass

    return [
        {"type": k[0], "category": k[1], "month": k[2], "actual": round(v, 2)}
        for k, v in totals.items()
    ]


# ── SUMMARY: budget vs actuals rolled up per month (for cash flow) ────────────
@router.get("/summary")
async def get_summary(
    year: int = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    year = year or datetime.utcnow().year
    budgets  = await list_budgets(year=year, current_user=current_user, db=db)
    actuals  = await get_actuals(year=year, current_user=current_user, db=db)

    months = list(range(1, 13))
    result = []
    for m in months:
        b_income  = sum(b["amount"] for b in budgets  if b["month"]==m and b["type"]=="income")
        b_expense = sum(b["amount"] for b in budgets  if b["month"]==m and b["type"]=="expense")
        a_income  = sum(a["actual"] for a in actuals  if a["month"]==m and a["type"]=="income")
        a_expense = sum(a["actual"] for a in actuals  if a["month"]==m and a["type"]=="expense")
        result.append({
            "month":            m,
            "budgeted_income":  round(b_income, 2),
            "budgeted_expense": round(b_expense, 2),
            "budgeted_net":     round(b_income - b_expense, 2),
            "actual_income":    round(a_income, 2),
            "actual_expense":   round(a_expense, 2),
            "actual_net":       round(a_income - a_expense, 2),
        })
    return result
