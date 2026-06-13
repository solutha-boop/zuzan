from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from database import get_db, Budget, Expense, Invoice
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


def _upsert(db: Session, company_id: int, entry: BudgetUpsert) -> Budget:
    """Insert or update a single budget entry."""
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

    # Actual expenses grouped by category + month
    expense_rows = (
        db.query(
            Expense.category,
            extract("month", Expense.expense_date).label("month"),
            func.sum(Expense.amount).label("total"),
        )
        .filter(
            Expense.company_id == current_user.company_id,
            extract("year", Expense.expense_date) == year,
        )
        .group_by(Expense.category, extract("month", Expense.expense_date))
        .all()
    )

    # Actual revenue (paid invoices) grouped by month
    invoice_rows = (
        db.query(
            extract("month", Invoice.paid_date).label("month"),
            func.sum(Invoice.amount).label("total"),
        )
        .filter(
            Invoice.company_id == current_user.company_id,
            Invoice.status == "paid",
            extract("year", Invoice.paid_date) == year,
        )
        .group_by(extract("month", Invoice.paid_date))
        .all()
    )

    actuals = []
    for row in expense_rows:
        actuals.append({
            "type":     "expense",
            "category": row.category or "Other",
            "month":    int(row.month),
            "actual":   round(float(row.total), 2),
        })
    for row in invoice_rows:
        actuals.append({
            "type":     "income",
            "category": "Revenue",
            "month":    int(row.month),
            "actual":   round(float(row.total), 2),
        })

    return actuals


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
