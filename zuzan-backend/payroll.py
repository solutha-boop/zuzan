"""
ZuZan - Payroll Engine, Reports and PayFast Payment Gateway
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from database import get_db, Employee, Payslip, Invoice, Expense, Company, Payment, InvoiceStatus, InventoryItem, PurchaseOrder
from auth import get_current_user, User
import hashlib
import logging

logger = logging.getLogger("zuzan.payroll")

# SA TAX TABLES — Multi-year for audit history
TAX_YEARS = {
    "2024/2025": {
        "brackets": [
            {"min": 0,        "max": 237100,   "rate": 0.18, "base": 0},
            {"min": 237101,   "max": 370500,   "rate": 0.26, "base": 42678},
            {"min": 370501,   "max": 512800,   "rate": 0.31, "base": 77362},
            {"min": 512801,   "max": 673000,   "rate": 0.36, "base": 121475},
            {"min": 673001,   "max": 857900,   "rate": 0.39, "base": 179147},
            {"min": 857901,   "max": 1817000,  "rate": 0.41, "base": 251258},
            {"min": 1817001,  "max": 9999999,  "rate": 0.45, "base": 644489},
        ],
        "primary_rebate": 17235,
        "uif_ceil": 17712,
    },
    "2025/2026": {
        "brackets": [
            {"min": 0,        "max": 237100,   "rate": 0.18, "base": 0},
            {"min": 237101,   "max": 370500,   "rate": 0.26, "base": 42678},
            {"min": 370501,   "max": 512800,   "rate": 0.31, "base": 77362},
            {"min": 512801,   "max": 673000,   "rate": 0.36, "base": 121475},
            {"min": 673001,   "max": 857900,   "rate": 0.39, "base": 179147},
            {"min": 857901,   "max": 1817000,  "rate": 0.41, "base": 251258},
            {"min": 1817001,  "max": 9999999,  "rate": 0.45, "base": 644489},
        ],
        "primary_rebate": 17235,
        "uif_ceil": 17712,
    },
    "2026/2027": {
        "brackets": [
            {"min": 0,        "max": 245100,   "rate": 0.18, "base": 0},
            {"min": 245101,   "max": 383100,   "rate": 0.26, "base": 44118},
            {"min": 383101,   "max": 530200,   "rate": 0.31, "base": 79998},
            {"min": 530201,   "max": 695800,   "rate": 0.36, "base": 125599},
            {"min": 695801,   "max": 887000,   "rate": 0.39, "base": 185215},
            {"min": 887001,   "max": 1878600,  "rate": 0.41, "base": 259783},
            {"min": 1878601,  "max": 9999999,  "rate": 0.45, "base": 666339},
        ],
        "primary_rebate": 17820,
        "uif_ceil": 17712,
    },
}

CURRENT_TAX_YEAR = "2026/2027"

# Active tables (current year)
PAYE_BRACKETS = TAX_YEARS[CURRENT_TAX_YEAR]["brackets"]
PRIMARY_REBATE = TAX_YEARS[CURRENT_TAX_YEAR]["primary_rebate"]
UIF_CEIL       = TAX_YEARS[CURRENT_TAX_YEAR]["uif_ceil"]
UIF_RATE        = 0.01
SDL_RATE        = 0.01
PAYROLL_PER_EMP = 17.50
PAYROLL_MIN     = 99.00


def calc_paye(annual_income: float, tax_year: str = None) -> float:
    yr = TAX_YEARS.get(tax_year or CURRENT_TAX_YEAR, TAX_YEARS[CURRENT_TAX_YEAR])
    bracket = None
    for b in yr["brackets"]:
        if b["min"] <= annual_income <= b["max"]:
            bracket = b
            break
    if not bracket:
        return 0
    tax = bracket["base"] + (annual_income - bracket["min"]) * bracket["rate"] - yr["primary_rebate"]
    return max(0, tax)


def calc_payroll(gross_monthly: float, tax_year: str = None) -> dict:
    yr = TAX_YEARS.get(tax_year or CURRENT_TAX_YEAR, TAX_YEARS[CURRENT_TAX_YEAR])
    annual_paye = calc_paye(gross_monthly * 12, tax_year)
    monthly_paye = annual_paye / 12
    uif_base = min(gross_monthly, yr["uif_ceil"])
    uif_employee = uif_base * UIF_RATE
    uif_employer = uif_base * UIF_RATE
    sdl = gross_monthly * SDL_RATE
    net_pay = gross_monthly - monthly_paye - uif_employee
    total_cost = gross_monthly + uif_employer + sdl
    return {
        "gross":        round(gross_monthly, 2),
        "paye":         round(monthly_paye, 2),
        "uif_employee": round(uif_employee, 2),
        "uif_employer": round(uif_employer, 2),
        "sdl":          round(sdl, 2),
        "net_pay":      round(net_pay, 2),
        "total_cost":   round(total_cost, 2),
        "tax_year":     tax_year or CURRENT_TAX_YEAR,
    }


# PAYROLL ROUTER
payroll_router = APIRouter()


@payroll_router.get("/calculate")
async def calculate_all(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    employees = db.query(Employee).filter(
        Employee.company_id == current_user.company_id,
        Employee.is_active == True
    ).all()

    results = []
    totals = {
        "gross": 0, "paye": 0, "uif_employee": 0,
        "uif_employer": 0, "sdl": 0, "net_pay": 0, "total_cost": 0
    }

    for emp in employees:
        c = calc_payroll(emp.gross_salary)
        c["employee_id"]     = emp.id
        c["employee_name"]   = f"{emp.first_name} {emp.last_name}"
        c["employee_number"] = emp.employee_number
        c["position"]        = emp.position
        c["department"]      = emp.department
        results.append(c)
        for key in totals:
            totals[key] = round(totals[key] + c[key], 2)

    zuzan_fee = max(PAYROLL_MIN, len(employees) * PAYROLL_PER_EMP)

    return {
        "employees":      results,
        "totals":         totals,
        "employee_count": len(employees),
        "zuzan_fee":      round(zuzan_fee, 2),
        "period":         datetime.utcnow().strftime("%B %Y"),
    }


@payroll_router.post("/run")
async def run_payroll(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    employees = db.query(Employee).filter(
        Employee.company_id == current_user.company_id,
        Employee.is_active == True
    ).all()

    if not employees:
        raise HTTPException(status_code=400, detail="No active employees found")

    period = datetime.utcnow().strftime("%Y-%m")
    created = []

    for emp in employees:
        existing = db.query(Payslip).filter(
            Payslip.employee_id == emp.id,
            Payslip.period == period
        ).first()
        if existing:
            continue
        c = calc_payroll(emp.gross_salary)
        payslip = Payslip(
            employee_id=emp.id,
            period=period,
            gross_salary=c["gross"],
            paye=c["paye"],
            uif_employee=c["uif_employee"],
            uif_employer=c["uif_employer"],
            sdl=c["sdl"],
            net_pay=c["net_pay"],
            total_cost=c["total_cost"],
        )
        db.add(payslip)
        db.flush()   # get payslip.id before journal post
        created.append(emp.id)
        try:
            import journal as journal_engine
            journal_engine.init_accounts(emp.company_id, db)
            journal_engine.post_payroll(payslip, emp, db)
        except Exception as e:
            logger.warning(f"Journal post failed for payslip {payslip.id}: {e}")

    db.commit()
    return {
        "status":           "processed",
        "period":           period,
        "payslips_created": len(created),
        "message":          f"Payroll processed for {len(created)} employees.",
    }


# REPORTS ROUTER
reports_router = APIRouter()


@reports_router.get("/tax-years")
async def get_tax_years(current_user: User = Depends(get_current_user)):
    return {
        "current": CURRENT_TAX_YEAR,
        "available": list(TAX_YEARS.keys()),
    }


@reports_router.get("/dashboard")
async def dashboard(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    cid = current_user.company_id
    now = datetime.utcnow()
    month_start = datetime(now.year, now.month, 1)

    paid_invoices = db.query(Invoice).filter(
        Invoice.company_id == cid,
        Invoice.status == InvoiceStatus.paid,
        Invoice.paid_date >= month_start
    ).all()
    total_revenue = sum(i.total_amount for i in paid_invoices)

    outstanding_invoices = db.query(Invoice).filter(
        Invoice.company_id == cid,
        Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])
    ).all()
    total_outstanding = sum(i.total_amount for i in outstanding_invoices)

    expenses = db.query(Expense).filter(
        Expense.company_id == cid,
        Expense.expense_date >= month_start
    ).all()
    total_expenses = sum(e.amount for e in expenses)

    employees = db.query(Employee).filter(
        Employee.company_id == cid,
        Employee.is_active == True
    ).all()
    total_payroll = sum(calc_payroll(e.gross_salary)["total_cost"] for e in employees)

    gross_profit = total_revenue - total_expenses
    net_profit   = gross_profit - total_payroll
    tax_provision = max(0, net_profit * 0.27)

    return {
        "period":            now.strftime("%B %Y"),
        "total_revenue":     round(total_revenue, 2),
        "total_expenses":    round(total_expenses, 2),
        "total_outstanding": round(total_outstanding, 2),
        "total_payroll":     round(total_payroll, 2),
        "gross_profit":      round(gross_profit, 2),
        "net_profit":        round(net_profit, 2),
        "tax_provision":     round(tax_provision, 2),
        "invoice_count":     len(paid_invoices),
        "employee_count":    len(employees),
        "outstanding_count": len(outstanding_invoices),
    }


@reports_router.get("/monthly-trend")
async def monthly_trend(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    cid = current_user.company_id
    now = datetime.utcnow()
    months = []

    for i in range(5, -1, -1):
        month = now.month - i
        year  = now.year
        while month <= 0:
            month += 12
            year  -= 1

        start = datetime(year, month, 1)
        end_month = month + 1
        end_year  = year
        if end_month > 12:
            end_month = 1
            end_year += 1
        end = datetime(end_year, end_month, 1)

        revenue = sum(
            inv.total_amount for inv in db.query(Invoice).filter(
                Invoice.company_id == cid,
                Invoice.status == InvoiceStatus.paid,
                Invoice.paid_date >= start,
                Invoice.paid_date < end
            ).all()
        )
        expenses = sum(
            exp.amount for exp in db.query(Expense).filter(
                Expense.company_id == cid,
                Expense.expense_date >= start,
                Expense.expense_date < end
            ).all()
        )

        months.append({
            "month":    start.strftime("%b"),
            "revenue":  round(revenue, 2),
            "expenses": round(expenses, 2),
            "profit":   round(revenue - expenses, 2),
        })

    return months


@reports_router.get("/balance-sheet")
async def balance_sheet(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Balance sheet derived from the double-entry journal.
    Falls back to estimated values if no journal entries exist yet.
    """
    from database import Account, AccountType, JournalLine
    import journal as journal_engine

    cid = current_user.company_id
    now = datetime.utcnow()

    # Ensure accounts exist
    journal_engine.init_accounts(cid, db)

    def bal(code):
        acct = db.query(Account).filter(Account.company_id==cid, Account.code==code).first()
        if not acct:
            return 0.0
        return journal_engine.account_balance(acct, db)

    # ── ASSETS ────────────────────────────────────────────────────────────────
    cash_and_equivalents  = bal("1000")
    trade_receivables     = bal("1100")
    inventory_at_cost     = bal("1200")
    vat_input_recoverable = bal("1300")
    total_assets = round(cash_and_equivalents + trade_receivables + inventory_at_cost + vat_input_recoverable, 2)

    # ── LIABILITIES ───────────────────────────────────────────────────────────
    accounts_payable = bal("2000")
    vat_payable      = bal("2100")
    paye_payable     = bal("2200")
    uif_payable      = bal("2210")
    sdl_payable      = bal("2220")
    total_liabilities = round(accounts_payable + vat_payable + paye_payable + uif_payable + sdl_payable, 2)

    # ── EQUITY ────────────────────────────────────────────────────────────────
    retained_income = bal("3000")
    # If no explicit equity postings yet, derive from Revenue − Expenses
    if retained_income == 0:
        revenue  = bal("4000")
        expenses = sum(bal(code) for code in ["5000","5100","5110","5200","5210","5220","5230","5240","5250","5260","5270","5280","5290","5300","5900"])
        retained_income = round(revenue - expenses, 2)
    total_equity = retained_income

    # ── BALANCE CHECK ─────────────────────────────────────────────────────────
    total_liabilities_and_equity = round(total_liabilities + total_equity, 2)
    imbalance = round(total_assets - total_liabilities_and_equity, 2)
    balanced  = abs(imbalance) < 1.0

    return {
        "date":      now.strftime("%d %B %Y"),
        "balanced":  balanced,
        "imbalance": imbalance,
        "source":    "journal",
        "assets": {
            "cash_and_equivalents":  cash_and_equivalents,
            "trade_receivables":     trade_receivables,
            "inventory_at_cost":     inventory_at_cost,
            "vat_input_recoverable": vat_input_recoverable,
            "total":                 total_assets,
        },
        "liabilities": {
            "accounts_payable": accounts_payable,
            "vat_payable":      vat_payable,
            "paye_payable":     paye_payable,
            "uif_payable":      uif_payable,
            "sdl_payable":      sdl_payable,
            "total":            total_liabilities,
        },
        "equity": {
            "retained_income": retained_income,
            "total":           total_equity,
        },
        "total_liabilities_and_equity": total_liabilities_and_equity,
    }


@reports_router.get("/reconciliation")
async def reconciliation(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Run all balance sheet reconciliation checks and return pass/warn/fail per rule."""
    from datetime import timedelta
    cid = current_user.company_id
    now = datetime.utcnow()
    VAT_RATE = 0.15

    checks = []

    # ── RULE 1: Balance sheet equation ────────────────────────────────────────
    bs = await balance_sheet(current_user=current_user, db=db)
    if bs["balanced"]:
        checks.append({"rule": "Balance Sheet Equation", "status": "pass",
            "detail": "Assets = Liabilities + Equity ✓",
            "amount": None})
    else:
        checks.append({"rule": "Balance Sheet Equation", "status": "fail",
            "detail": f"Imbalance of R {abs(bs['imbalance']):,.2f} — Assets do not equal Liabilities + Equity.",
            "amount": bs["imbalance"]})

    # ── RULE 2: Debtors ageing — invoices outstanding > 90 days ──────────────
    cutoff_90 = now - timedelta(days=90)
    overdue_90 = db.query(Invoice).filter(
        Invoice.company_id==cid,
        Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue]),
        Invoice.issue_date <= cutoff_90
    ).all()
    amount_90 = round(sum(i.total_amount for i in overdue_90), 2)
    if not overdue_90:
        checks.append({"rule": "Debtors Ageing (>90 days)", "status": "pass",
            "detail": "No invoices outstanding beyond 90 days.", "amount": None,
            "items": []})
    else:
        checks.append({"rule": "Debtors Ageing (>90 days)", "status": "warn",
            "detail": f"{len(overdue_90)} invoice(s) outstanding beyond 90 days totalling R {amount_90:,.2f}. Consider writing off or following up.",
            "amount": amount_90,
            "items": [{"id": i.invoice_number, "client": i.client_name,
                       "amount": i.total_amount,
                       "days": (now - i.issue_date).days} for i in overdue_90]})

    # ── RULE 3: VAT control reconciliation ────────────────────────────────────
    all_invoices = db.query(Invoice).filter(Invoice.company_id==cid).all()
    all_expenses = db.query(Expense).filter(Expense.company_id==cid).all()
    vat_output   = round(sum(i.vat_amount or 0 for i in all_invoices), 2)
    vat_input    = round(sum(e.vat_amount or 0 for e in all_expenses), 2)
    net_vat      = round(vat_output - vat_input, 2)
    vat_status   = "pass" if net_vat >= 0 else "warn"
    vat_detail   = (f"Output VAT R {vat_output:,.2f} − Input VAT R {vat_input:,.2f} = Net payable R {net_vat:,.2f} to SARS."
                    if net_vat >= 0 else
                    f"Input VAT R {vat_input:,.2f} exceeds output VAT R {vat_output:,.2f}. You may have a VAT refund of R {abs(net_vat):,.2f} due from SARS.")
    checks.append({"rule": "VAT Control Account", "status": vat_status,
        "detail": vat_detail, "amount": net_vat})

    # ── RULE 4: Payroll liabilities — PAYE/UIF/SDL current month ─────────────
    month_start     = datetime(now.year, now.month, 1)
    recent_payslips = db.query(Payslip).join(Employee).filter(
        Employee.company_id==cid, Payslip.generated_at>=month_start
    ).all()
    paye = round(sum(p.paye for p in recent_payslips), 2)
    uif  = round(sum(p.uif_employee + p.uif_employer for p in recent_payslips), 2)
    sdl  = round(sum(p.sdl for p in recent_payslips), 2)
    payroll_liab = round(paye + uif + sdl, 2)
    # EMP201 due by 7th of next month
    emp201_due = datetime(now.year + (1 if now.month==12 else 0), (now.month % 12) + 1, 7)
    days_to_emp201 = (emp201_due - now).days
    if not recent_payslips:
        checks.append({"rule": "Payroll Liabilities (EMP201)", "status": "pass",
            "detail": "No payroll run this month.", "amount": None})
    elif days_to_emp201 < 0:
        checks.append({"rule": "Payroll Liabilities (EMP201)", "status": "fail",
            "detail": f"EMP201 payment of R {payroll_liab:,.2f} (PAYE R {paye:,.2f} + UIF R {uif:,.2f} + SDL R {sdl:,.2f}) was due on {emp201_due.strftime('%d %b %Y')} and may be overdue.",
            "amount": payroll_liab})
    elif days_to_emp201 <= 7:
        checks.append({"rule": "Payroll Liabilities (EMP201)", "status": "warn",
            "detail": f"EMP201 of R {payroll_liab:,.2f} due in {days_to_emp201} day(s) on {emp201_due.strftime('%d %b %Y')}. PAYE R {paye:,.2f} | UIF R {uif:,.2f} | SDL R {sdl:,.2f}.",
            "amount": payroll_liab})
    else:
        checks.append({"rule": "Payroll Liabilities (EMP201)", "status": "pass",
            "detail": f"EMP201 of R {payroll_liab:,.2f} due {emp201_due.strftime('%d %b %Y')} ({days_to_emp201} days away). PAYE R {paye:,.2f} | UIF R {uif:,.2f} | SDL R {sdl:,.2f}.",
            "amount": payroll_liab})

    # ── RULE 5: Accounts payable — open POs received but not cleared ──────────
    open_pos = db.query(PurchaseOrder).filter(
        PurchaseOrder.company_id==cid,
        PurchaseOrder.status.in_(["received","partial"])
    ).all()
    ap_total = round(sum(po.total_amount or 0 for po in open_pos), 2)
    if not open_pos:
        checks.append({"rule": "Accounts Payable", "status": "pass",
            "detail": "No received purchase orders awaiting payment.", "amount": None, "items": []})
    else:
        checks.append({"rule": "Accounts Payable", "status": "warn",
            "detail": f"{len(open_pos)} received PO(s) totalling R {ap_total:,.2f} recorded as accounts payable.",
            "amount": ap_total,
            "items": [{"id": po.po_number, "supplier": po.supplier_name,
                       "amount": po.total_amount, "status": po.status} for po in open_pos]})

    # ── RULE 6: Inventory valuation ───────────────────────────────────────────
    inv_items   = db.query(InventoryItem).filter(InventoryItem.company_id==cid, InventoryItem.is_active==True).all()
    below_reorder = [i for i in inv_items if i.quantity_on_hand <= i.reorder_level]
    neg_stock     = [i for i in inv_items if i.quantity_on_hand < 0]
    if neg_stock:
        checks.append({"rule": "Inventory Valuation", "status": "fail",
            "detail": f"{len(neg_stock)} item(s) have negative stock on hand — indicates unrecorded purchases or data entry errors.",
            "amount": None,
            "items": [{"sku": i.sku, "name": i.name, "qty": i.quantity_on_hand} for i in neg_stock]})
    elif below_reorder:
        checks.append({"rule": "Inventory Valuation", "status": "warn",
            "detail": f"{len(below_reorder)} item(s) at or below reorder level. Reorder to avoid stock-outs.",
            "amount": None,
            "items": [{"sku": i.sku, "name": i.name, "qty": i.quantity_on_hand, "reorder": i.reorder_level} for i in below_reorder]})
    else:
        inv_total = round(sum(i.quantity_on_hand * i.unit_cost for i in inv_items), 2)
        checks.append({"rule": "Inventory Valuation", "status": "pass",
            "detail": f"All {len(inv_items)} stock item(s) above reorder level. Total inventory at cost: R {inv_total:,.2f}.",
            "amount": inv_total})

    # ── RULE 7: Unmatched revenue — paid invoices with no expense offset ───────
    # Simple check: gross margin — warn if expenses are >90% of revenue
    total_rev = round(sum(i.amount for i in db.query(Invoice).filter(Invoice.company_id==cid, Invoice.status==InvoiceStatus.paid).all()), 2)
    total_exp = round(sum(e.amount for e in all_expenses), 2)
    if total_rev > 0:
        expense_ratio = total_exp / total_rev
        if expense_ratio > 0.9:
            checks.append({"rule": "Gross Margin Health", "status": "warn",
                "detail": f"Expenses are {expense_ratio*100:.0f}% of revenue. Gross margin is only {(1-expense_ratio)*100:.0f}%. Review cost structure.",
                "amount": round(total_rev - total_exp, 2)})
        else:
            checks.append({"rule": "Gross Margin Health", "status": "pass",
                "detail": f"Gross margin is {(1-expense_ratio)*100:.0f}%. Expenses are {expense_ratio*100:.0f}% of revenue.",
                "amount": round(total_rev - total_exp, 2)})
    else:
        checks.append({"rule": "Gross Margin Health", "status": "pass",
            "detail": "No revenue recorded yet.", "amount": None})

    passed = sum(1 for c in checks if c["status"]=="pass")
    warned = sum(1 for c in checks if c["status"]=="warn")
    failed = sum(1 for c in checks if c["status"]=="fail")

    return {
        "date":    now.strftime("%d %B %Y"),
        "summary": {"total": len(checks), "passed": passed, "warned": warned, "failed": failed},
        "checks":  checks,
        "balance_sheet": bs,
    }


@reports_router.get("/cash-flow")
async def cash_flow(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    cid = current_user.company_id
    now = datetime.utcnow()
    month_start = datetime(now.year, now.month, 1)

    paid_this_month = db.query(Invoice).filter(
        Invoice.company_id == cid,
        Invoice.status == InvoiceStatus.paid,
        Invoice.paid_date >= month_start
    ).all()
    cash_receipts = round(sum(i.total_amount for i in paid_this_month), 2)

    expenses_this_month = db.query(Expense).filter(
        Expense.company_id == cid,
        Expense.expense_date >= month_start
    ).all()
    cash_payments = round(sum(e.amount for e in expenses_this_month), 2)

    payslips_this_month = db.query(Payslip).join(Employee).filter(
        Employee.company_id == cid,
        Payslip.generated_at >= month_start
    ).all()
    payroll_disbursed = round(sum(p.net_pay for p in payslips_this_month), 2)
    sars_payments     = round(sum(p.paye + p.uif_employee + p.uif_employer + p.sdl for p in payslips_this_month), 2)

    net_operating = round(cash_receipts - cash_payments - payroll_disbursed - sars_payments, 2)

    return {
        "period": now.strftime("%B %Y"),
        "operating": {
            "cash_receipts_from_customers": cash_receipts,
            "cash_paid_to_suppliers":       -cash_payments,
            "payroll_net_pay":              -payroll_disbursed,
            "sars_paye_uif_sdl":            -sars_payments,
            "net_cash_from_operations":     net_operating,
        },
        "investing": {
            "net_cash_from_investing": 0,
        },
        "financing": {
            "net_cash_from_financing": 0,
        },
        "net_increase_in_cash": net_operating,
    }


@reports_router.get("/emp201")
async def emp201(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    cid = current_user.company_id
    now = datetime.utcnow()
    period = now.strftime("%Y-%m")

    if now.month < 12:
        due_date = datetime(now.year, now.month + 1, 7).strftime("%d %B %Y")
    else:
        due_date = datetime(now.year + 1, 1, 7).strftime("%d %B %Y")

    payslips = db.query(Payslip).join(Employee).filter(
        Employee.company_id == cid,
        Payslip.period == period
    ).all()

    employees_detail = []
    for ps in payslips:
        emp = db.query(Employee).filter(Employee.id == ps.employee_id).first()
        employees_detail.append({
            "employee_name":   f"{emp.first_name} {emp.last_name}",
            "employee_number": emp.employee_number or f"EMP-{emp.id:03d}",
            "gross_salary":    ps.gross_salary,
            "paye":            ps.paye,
            "uif_employee":    ps.uif_employee,
            "uif_employer":    ps.uif_employer,
            "sdl":             ps.sdl,
            "net_pay":         ps.net_pay,
        })

    total_paye         = round(sum(p.paye for p in payslips), 2)
    total_uif_employee = round(sum(p.uif_employee for p in payslips), 2)
    total_uif_employer = round(sum(p.uif_employer for p in payslips), 2)
    total_sdl          = round(sum(p.sdl for p in payslips), 2)
    total_uif          = round(total_uif_employee + total_uif_employer, 2)
    total_due_sars     = round(total_paye + total_uif + total_sdl, 2)

    return {
        "period":            now.strftime("%B %Y"),
        "due_date":          due_date,
        "employee_count":    len(payslips),
        "employees":         employees_detail,
        "total_paye":        total_paye,
        "total_uif":         total_uif,
        "total_sdl":         total_sdl,
        "total_due_sars":    total_due_sars,
        "efiling_reference": f"EMP201-{period}",
    }


@reports_router.get("/management")
async def management_accounts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    cid = current_user.company_id
    now = datetime.utcnow()
    month_start = datetime(now.year, now.month, 1)

    paid_invoices = db.query(Invoice).filter(
        Invoice.company_id == cid,
        Invoice.status == InvoiceStatus.paid,
        Invoice.created_at >= month_start
    ).all()
    revenue = round(sum(i.total_amount for i in paid_invoices), 2)

    expenses = db.query(Expense).filter(
        Expense.company_id == cid,
        Expense.expense_date >= month_start
    ).all()
    total_expenses = round(sum(e.amount for e in expenses), 2)

    expense_by_cat: dict = {}
    for e in expenses:
        key = e.category or "Other"
        expense_by_cat[key] = round(expense_by_cat.get(key, 0) + e.amount, 2)

    active_employees = db.query(Employee).filter(
        Employee.company_id == cid,
        Employee.is_active == True
    ).all()
    total_payroll_cost = round(sum(calc_payroll(e.gross_salary)["total_cost"] for e in active_employees), 2)

    gross_profit  = round(revenue - total_expenses, 2)
    ebit          = round(gross_profit - total_payroll_cost, 2)
    tax_provision = round(max(0, ebit * 0.27), 2)
    net_profit    = round(ebit - tax_provision, 2)
    gross_margin  = round((gross_profit / revenue * 100) if revenue else 0, 1)
    net_margin    = round((net_profit / revenue * 100) if revenue else 0, 1)

    outstanding = db.query(Invoice).filter(
        Invoice.company_id == cid,
        Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])
    ).all()
    total_outstanding = round(sum(i.total_amount for i in outstanding), 2)
    overdue_count     = sum(1 for i in outstanding if i.status == InvoiceStatus.overdue)

    trend = []
    for i in range(5, -1, -1):
        m = now.month - i
        y = now.year
        while m <= 0:
            m += 12
            y -= 1
        start = datetime(y, m, 1)
        end_m, end_y = (m + 1, y) if m < 12 else (1, y + 1)
        end = datetime(end_y, end_m, 1)
        rev = round(sum(inv.total_amount for inv in db.query(Invoice).filter(
            Invoice.company_id == cid, Invoice.status == InvoiceStatus.paid,
            Invoice.created_at >= start, Invoice.created_at < end).all()), 2)
        exp = round(sum(ex.amount for ex in db.query(Expense).filter(
            Expense.company_id == cid,
            Expense.expense_date >= start, Expense.expense_date < end).all()), 2)
        trend.append({"month": start.strftime("%b"), "revenue": rev, "expenses": exp, "profit": round(rev - exp, 2)})

    return {
        "period":       now.strftime("%B %Y"),
        "generated_at": now.isoformat(),
        "pl": {
            "revenue":           revenue,
            "total_expenses":    total_expenses,
            "expense_breakdown": expense_by_cat,
            "gross_profit":      gross_profit,
            "payroll_cost":      total_payroll_cost,
            "ebit":              ebit,
            "tax_provision":     tax_provision,
            "net_profit":        net_profit,
            "gross_margin_pct":  gross_margin,
            "net_margin_pct":    net_margin,
        },
        "kpis": {
            "revenue":          revenue,
            "net_profit":       net_profit,
            "outstanding":      total_outstanding,
            "overdue_count":    overdue_count,
            "employee_count":   len(active_employees),
            "payroll_cost":     total_payroll_cost,
            "gross_margin_pct": gross_margin,
            "net_margin_pct":   net_margin,
        },
        "trend": trend,
    }



@reports_router.get("/provisional-tax")
async def provisional_tax(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Calculates provisional tax (IRP6) for the company.
    SA corporate tax rate: 27% of taxable income.
    Provisional tax is paid in two installments per tax year.
    First payment: 6 months into the tax year.
    Second payment: last day of the tax year.
    """
    cid = current_user.company_id
    now = datetime.utcnow()
    CORP_TAX_RATE = 0.27

    # Get all revenue and expenses for the current calendar year (YTD)
    year_start = datetime(now.year, 1, 1)

    paid_invoices = db.query(Invoice).filter(
        Invoice.company_id == cid,
        Invoice.status == InvoiceStatus.paid,
        Invoice.created_at >= year_start
    ).all()
    ytd_revenue = round(sum(i.total_amount for i in paid_invoices), 2)

    expenses = db.query(Expense).filter(
        Expense.company_id == cid,
        Expense.expense_date >= year_start
    ).all()
    ytd_expenses = round(sum(e.amount for e in expenses), 2)

    payslips = db.query(Payslip).join(Employee).filter(
        Employee.company_id == cid,
        Payslip.generated_at >= year_start
    ).all()
    ytd_payroll = round(sum(p.total_cost for p in payslips), 2)

    # YTD taxable income
    ytd_taxable_income = round(ytd_revenue - ytd_expenses - ytd_payroll, 2)

    # Annualise based on months elapsed
    months_elapsed = now.month
    annual_taxable_income = round((ytd_taxable_income / months_elapsed * 12) if months_elapsed > 0 else 0, 2)

    # Corporate tax on estimated annual income
    estimated_annual_tax = round(max(0, annual_taxable_income * CORP_TAX_RATE), 2)

    # Provisional tax payments
    # First IRP6: 50% of estimated annual tax — due last day of month 6 of tax year
    # Second IRP6: balance (50%) — due last day of tax year (assume Feb year-end = 28 Feb)
    first_payment  = round(estimated_annual_tax / 2, 2)
    second_payment = round(estimated_annual_tax - first_payment, 2)

    # Due dates (assuming 28 Feb financial year-end — standard for SA companies)
    first_due  = datetime(now.year, 8, 31).strftime("%d %B %Y")   # 31 Aug
    second_due = datetime(now.year + 1, 2, 28).strftime("%d %B %Y")  # 28 Feb next year

    return {
        "tax_year":                 f"{now.year}/{now.year + 1}",
        "corp_tax_rate_pct":        27,
        "months_elapsed":           months_elapsed,
        "ytd": {
            "revenue":              ytd_revenue,
            "expenses":             ytd_expenses,
            "payroll_cost":         ytd_payroll,
            "taxable_income":       ytd_taxable_income,
        },
        "annualised": {
            "taxable_income":       annual_taxable_income,
            "estimated_tax":        estimated_annual_tax,
        },
        "irp6": {
            "first_payment":        first_payment,
            "first_due":            first_due,
            "second_payment":       second_payment,
            "second_due":           second_due,
        },
        "notes": [
            "Based on annualised YTD figures — update when actual year-end figures are known.",
            "Small Business Corporations (SBC) qualify for reduced tax rates — consult your accountant.",
            "Submit IRP6 via SARS eFiling before due dates to avoid penalties.",
            "Turnover tax may apply if annual turnover is below R1,000,000.",
        ]
    }


@reports_router.get("/debtors-aging")
async def debtors_aging(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Debtors book with aging — outstanding invoices owed TO the company."""
    cid = current_user.company_id
    now = datetime.utcnow()

    outstanding = db.query(Invoice).filter(
        Invoice.company_id == cid,
        Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])
    ).all()

    buckets = {"current": [], "31_60": [], "61_90": [], "over_90": [], "not_due": []}

    for inv in outstanding:
        due = inv.due_date or inv.created_at
        days_overdue = (now - due).days if due else 0
        entry = {
            "id":             inv.invoice_number,
            "client":         inv.client_name,
            "amount":         round(inv.total_amount, 2),
            "due_date":       due.strftime("%Y-%m-%d") if due else None,
            "days_overdue":   max(0, days_overdue),
            "status":         str(inv.status).split(".")[-1],
        }
        if days_overdue < 0:
            buckets["not_due"].append(entry)
        elif days_overdue <= 30:
            buckets["current"].append(entry)
        elif days_overdue <= 60:
            buckets["31_60"].append(entry)
        elif days_overdue <= 90:
            buckets["61_90"].append(entry)
        else:
            buckets["over_90"].append(entry)

    def bucket_total(b): return round(sum(i["amount"] for i in b), 2)

    return {
        "as_at":      now.strftime("%d %B %Y"),
        "buckets":    buckets,
        "totals": {
            "not_due":  bucket_total(buckets["not_due"]),
            "current":  bucket_total(buckets["current"]),
            "31_60":    bucket_total(buckets["31_60"]),
            "61_90":    bucket_total(buckets["61_90"]),
            "over_90":  bucket_total(buckets["over_90"]),
            "grand":    bucket_total(buckets["not_due"]) + bucket_total(buckets["current"]) +
                        bucket_total(buckets["31_60"]) + bucket_total(buckets["61_90"]) +
                        bucket_total(buckets["over_90"]),
        }
    }


@reports_router.get("/creditors-aging")
async def creditors_aging(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Creditors book with aging — expenses grouped by vendor."""
    cid = current_user.company_id
    now = datetime.utcnow()

    expenses = db.query(Expense).filter(
        Expense.company_id == cid
    ).order_by(Expense.expense_date.desc()).all()

    # Group by vendor
    vendor_map = {}
    for exp in expenses:
        v = exp.vendor or "Unknown"
        if v not in vendor_map:
            vendor_map[v] = {"vendor": v, "invoices": [], "total": 0}
        exp_date = exp.expense_date or exp.created_at
        days_old = (now - exp_date).days if exp_date else 0
        entry = {
            "id":       f"EXP-{exp.id:03d}",
            "description": exp.description or "",
            "category": exp.category or "Other",
            "amount":   round(exp.amount, 2),
            "date":     exp_date.strftime("%Y-%m-%d") if exp_date else None,
            "days_old": days_old,
            "bucket":   "current" if days_old <= 30 else "31_60" if days_old <= 60 else "61_90" if days_old <= 90 else "over_90",
        }
        vendor_map[v]["invoices"].append(entry)
        vendor_map[v]["total"] = round(vendor_map[v]["total"] + exp.amount, 2)

    vendors = sorted(vendor_map.values(), key=lambda x: x["total"], reverse=True)

    # Bucket totals across all vendors
    all_exp = [e for v in vendors for e in v["invoices"]]
    def btotal(bucket): return round(sum(e["amount"] for e in all_exp if e["bucket"] == bucket), 2)

    return {
        "as_at":   now.strftime("%d %B %Y"),
        "vendors": vendors,
        "totals": {
            "current": btotal("current"),
            "31_60":   btotal("31_60"),
            "61_90":   btotal("61_90"),
            "over_90": btotal("over_90"),
            "grand":   round(sum(e["amount"] for e in all_exp), 2),
        }
    }


@reports_router.get("/vat201")
async def vat201(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    period: Optional[str] = None,
):
    """
    VAT201 return calculation.
    SA VAT rate: 15%. Filed monthly or bi-monthly.
    Output VAT: from invoice vat_amount fields.
    Input VAT: estimated at 15/115 of expenses (VAT-inclusive assumption).
    period: YYYY-MM format, defaults to current month.
    """
    cid = current_user.company_id
    now = datetime.utcnow()
    VAT_RATE = 0.15

    # Determine period
    if period:
        try:
            year, month = int(period.split("-")[0]), int(period.split("-")[1])
        except Exception:
            year, month = now.year, now.month
    else:
        year, month = now.year, now.month

    start = datetime(year, month, 1)
    end_month = month + 1 if month < 12 else 1
    end_year  = year if month < 12 else year + 1
    end = datetime(end_year, end_month, 1)

    period_label = start.strftime("%B %Y")
    due_date = datetime(end_year, end_month + 1 if end_month < 12 else 1, 25).strftime("%d %B %Y") if end_month < 12 else datetime(end_year + 1, 2, 25).strftime("%d %B %Y")

    # ── OUTPUT TAX ─────────────────────────────────────────────────────────────
    # All invoices issued in the period (tax point = invoice date)
    all_invoices = db.query(Invoice).filter(
        Invoice.company_id == cid,
        Invoice.created_at >= start,
        Invoice.created_at < end,
    ).all()

    # Standard rated supplies (excl. VAT)
    standard_supplies_incl = round(sum(i.total_amount for i in all_invoices), 2)
    output_vat_exact        = round(sum(i.vat_amount or 0 for i in all_invoices), 2)
    # If no vat_amount recorded, estimate from total
    output_vat = output_vat_exact if output_vat_exact > 0 else round(standard_supplies_incl * VAT_RATE / (1 + VAT_RATE), 2)
    standard_supplies_excl  = round(standard_supplies_incl - output_vat, 2)

    # ── INPUT TAX ──────────────────────────────────────────────────────────────
    expenses = db.query(Expense).filter(
        Expense.company_id == cid,
        Expense.expense_date >= start,
        Expense.expense_date < end,
    ).all()

    total_expenses_incl = round(sum(e.amount for e in expenses), 2)
    # Use stored vat_amount if available, else estimate at 15/115
    stored_input_vat = round(sum(getattr(e, "vat_amount", 0) or 0 for e in expenses), 2)
    input_vat_estimated = stored_input_vat if stored_input_vat > 0 else round(total_expenses_incl * VAT_RATE / (1 + VAT_RATE), 2)
    vat_is_exact = stored_input_vat > 0
    total_expenses_excl = round(total_expenses_incl - input_vat_estimated, 2)

    # Expense breakdown by category for audit trail
    cat_breakdown: dict = {}
    for e in expenses:
        key = e.category or "Other"
        cat_breakdown[key] = round(cat_breakdown.get(key, 0) + e.amount, 2)

    # ── NET VAT ────────────────────────────────────────────────────────────────
    net_vat = round(output_vat - input_vat_estimated, 2)

    return {
        "period":          period_label,
        "period_code":     start.strftime("%Y-%m"),
        "due_date":        due_date,
        "vat_rate_pct":    15,
        "output": {
            "field_1a_standard_supplies_excl_vat": standard_supplies_excl,
            "field_1b_zero_rated_supplies":         0,
            "field_4a_output_vat":                  output_vat,
            "invoice_count":                         len(all_invoices),
            "total_invoiced_incl_vat":               standard_supplies_incl,
            "vat_recorded_on_invoices":              output_vat_exact,
        },
        "input": {
            "field_14_input_vat":                    input_vat_estimated,
            "total_expenses_incl_vat":               total_expenses_incl,
            "total_expenses_excl_vat":               total_expenses_excl,
            "expense_count":                          len(expenses),
            "expense_breakdown":                      cat_breakdown,
            "note": ("Input VAT from stored expense records." if vat_is_exact else "Input VAT estimated at 15/115 of expenses. Adjust for any zero-rated or exempt purchases."),
            "is_exact": vat_is_exact,
        },
        "net": {
            "field_15_net_vat":  net_vat,
            "status":             "payable" if net_vat >= 0 else "refundable",
            "amount":             abs(net_vat),
        },
    }

# PAYFAST PAYMENT GATEWAY
payments_router = APIRouter()

PAYFAST_MERCHANT_ID  = "10000100"
PAYFAST_MERCHANT_KEY = "46f0cd694581a"
PAYFAST_PASSPHRASE   = ""
PAYFAST_SANDBOX      = True
PAYFAST_URL = "https://sandbox.payfast.co.za/eng/process" if PAYFAST_SANDBOX else "https://www.payfast.co.za/eng/process"

PLAN_PRICES = {
    "starter":      {"monthly": 299,  "annual": 2990},
    "professional": {"monthly": 699,  "annual": 6990},
    "business":     {"monthly": 1299, "annual": 12990},
}


class PaymentInitRequest(BaseModel):
    plan:            str
    billing_cycle:   str = "monthly"
    payroll_enabled: bool = False
    employee_count:  int = 0


def pf_signature(data: dict, passphrase: str = "") -> str:
    params = {k: v for k, v in data.items() if v != ""}
    param_string = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    if passphrase:
        param_string += f"&passphrase={passphrase}"
    return hashlib.md5(param_string.encode()).hexdigest()


@payments_router.post("/initiate")
async def initiate_payment(
    data: PaymentInitRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    plan_price   = PLAN_PRICES.get(data.plan, {}).get(data.billing_cycle, 299)
    payroll_cost = max(99, data.employee_count * 17.50) if data.payroll_enabled else 0
    total        = round(plan_price + payroll_cost, 2)

    payment = Payment(
        company_id=current_user.company_id,
        amount=total,
        plan=data.plan,
        billing_cycle=data.billing_cycle,
        status="pending",
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    pf_data = {
        "merchant_id":      PAYFAST_MERCHANT_ID,
        "merchant_key":     PAYFAST_MERCHANT_KEY,
        "return_url":       "http://localhost:3000/payment/success",
        "cancel_url":       "http://localhost:3000/payment/cancel",
        "notify_url":       "http://localhost:8001/payments/notify",
        "name_first":       current_user.first_name,
        "name_last":        current_user.last_name,
        "email_address":    current_user.email,
        "m_payment_id":     str(payment.id),
        "amount":           f"{total:.2f}",
        "item_name":        f"ZuZan {data.plan.capitalize()} Plan ({data.billing_cycle})",
        "item_description": f"ZuZan subscription{' + Payroll' if data.payroll_enabled else ''}",
        "custom_str1":      str(current_user.company_id),
        "custom_str2":      data.plan,
        "custom_str3":      data.billing_cycle,
        "subscription_type": "1",
        "billing_date":     datetime.utcnow().strftime("%Y-%m-%d"),
        "recurring_amount": f"{plan_price:.2f}",
        "frequency":        "3" if data.billing_cycle == "monthly" else "6",
        "cycles":           "0",
    }
    pf_data["signature"] = pf_signature(pf_data, PAYFAST_PASSPHRASE)

    return {
        "payment_id":   payment.id,
        "payfast_url":  PAYFAST_URL,
        "payfast_data": pf_data,
        "total":        total,
        "sandbox":      PAYFAST_SANDBOX,
    }


@payments_router.post("/notify")
async def payfast_notify(request: Request, db: Session = Depends(get_db)):
    form   = await request.form()
    data   = dict(form)
    pf_id  = data.get("m_payment_id")
    status = data.get("payment_status")

    if not pf_id:
        return JSONResponse(content={"status": "error"}, status_code=400)

    payment = db.query(Payment).filter(Payment.id == int(pf_id)).first()
    if not payment:
        return JSONResponse(content={"status": "error"}, status_code=404)

    if status == "COMPLETE":
        payment.status     = "completed"
        payment.payfast_id = data.get("pf_payment_id")
        company = db.query(Company).filter(Company.id == int(data.get("custom_str1", 0))).first()
        if company:
            from database import SubscriptionStatus, PlanType, BillingCycle
            company.subscription_status = SubscriptionStatus.active
            company.plan          = PlanType(data.get("custom_str2", "starter"))
            company.billing_cycle = BillingCycle(data.get("custom_str3", "monthly"))
    else:
        payment.status = "failed"

    db.commit()
    return JSONResponse(content={"status": "ok"})


@payments_router.get("/subscription")
async def subscription_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    company     = db.query(Company).filter(Company.id == current_user.company_id).first()
    plan_str    = str(company.plan).split(".")[-1]
    billing_str = str(company.billing_cycle).split(".")[-1]
    plan_price  = PLAN_PRICES.get(plan_str, {}).get(billing_str, 299)
    payroll_cost = max(99, company.payroll_employees * 17.50) if company.payroll_enabled else 0

    return {
        "plan":              company.plan,
        "billing_cycle":     company.billing_cycle,
        "status":            company.subscription_status,
        "trial_ends":        company.trial_ends.isoformat() if company.trial_ends else None,
        "plan_price":        plan_price,
        "payroll_cost":      payroll_cost,
        "total_monthly":     plan_price + payroll_cost,
        "payroll_enabled":   company.payroll_enabled,
        "payroll_employees": company.payroll_employees,
    }
