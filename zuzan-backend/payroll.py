"""
ZuZan - Payroll Engine, Reports and PayFast Payment Gateway
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
from database import get_db, Employee, Payslip, Invoice, Expense, Company, Payment, InvoiceStatus, InventoryItem, PurchaseOrder, DepreciationEntry, Account, AccountType, JournalEntry, JournalLine
from auth import get_current_user, User
import hashlib
import logging

def _to_zar(inv) -> float:
    """Convert an invoice's total to ZAR, applying exchange_rate for foreign currencies.
    For paid invoices, uses paid_amount_zar (actual cash received) when available."""
    if inv.currency and inv.currency != "ZAR":
        if getattr(inv, "paid_amount_zar", None):
            return inv.paid_amount_zar
        return (inv.total_amount or 0) * (inv.exchange_rate or 1.0)
    return inv.total_amount or 0


def _po_delivered_net(po) -> float:
    """Ex-VAT value of goods actually delivered on a purchase order.

    Full subtotal for received POs. For partial AND paid POs, sums per-item
    quantity_received × unit_price so the P&L matches the incremental journal
    postings (audit fixes 2026-07-02 / 2026-07-03). "paid" is included because
    pay_po accepts partially delivered POs: paying one flips its status to
    "paid" and would otherwise revert its COGS to the full subtotal while the
    journal carries only the delivered amount. Legacy POs with no receipt
    tracking (all quantity_received = 0) fall back to the full subtotal —
    consistent with the full-amount journal entry their backfill posted.
    (Fully received/paid POs are unaffected: their delivered sum equals the
    subtotal, and the migration backfilled their quantity_received in full.)"""
    net_full = (po.total_amount or 0) - (po.vat_amount or 0)
    if po.status not in ("partial", "paid"):
        return round(net_full, 2)
    delivered = sum((i.quantity_received or 0) * (i.unit_price or 0) for i in po.items)
    if delivered > 0:
        return round(delivered, 2)
    return round(net_full, 2)  # legacy PO — no tracking data


def _po_delivered_total(po) -> float:
    """VAT-inclusive value of goods actually delivered (net + proportional VAT)."""
    net = _po_delivered_net(po)
    vat_rate = (po.vat_amount / po.subtotal) if (po.subtotal and po.vat_amount) else 0.0
    return round(net * (1 + vat_rate), 2)


logger = logging.getLogger("zuzan.payroll")


def _bank_import_income(db: Session, company_id: int, date_from=None, date_to=None) -> float:
    """
    Sum net revenue credits from bank-import journal entries (source == 'bank_import_income').
    Uses three simple queries instead of a multi-table JOIN to avoid SQLAlchemy ambiguity.

    This is intentionally separate from invoice-based revenue to avoid double-counting.
    Invoice revenue is read from the Invoice table; bank import income is read from here.
    """
    # 1. Revenue account IDs for this company
    rev_ids = [
        a.id for a in db.query(Account).filter(
            Account.company_id == company_id,
            Account.type == AccountType.revenue,
        ).all()
    ]
    if not rev_ids:
        return 0.0

    # 2. Bank-import journal entry IDs, filtered by company and optional date range
    eq = db.query(JournalEntry.id).filter(
        JournalEntry.company_id == company_id,
        JournalEntry.source == "bank_import_income",
    )
    if date_from:
        eq = eq.filter(JournalEntry.date >= date_from)
    if date_to:
        eq = eq.filter(JournalEntry.date < date_to)
    entry_ids = [r[0] for r in eq.all()]
    if not entry_ids:
        return 0.0

    # 3. Sum credit − debit for revenue lines in those entries
    total = db.query(
        func.coalesce(func.sum(JournalLine.credit - JournalLine.debit), 0)
    ).filter(
        JournalLine.entry_id.in_(entry_ids),
        JournalLine.account_id.in_(rev_ids),
    ).scalar()
    return float(total or 0)

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

# ── BCEA (Basic Conditions of Employment Act) overtime constants ──────────────
# Reference: BCEA No. 75 of 1997 as amended
BCEA_WEEKLY_HOURS    = 45       # normal maximum working hours per week (s9)
BCEA_WEEKS_PER_MONTH = 52 / 12  # 4.3333 weeks/month — used to derive hourly rate
BCEA_OT_RATE_WEEKDAY = 1.5      # weekday & Saturday overtime multiplier (s10)
BCEA_OT_RATE_SUNDAY  = 2.0      # Sunday work multiplier (s16)
BCEA_OT_RATE_PH      = 2.0      # public holiday work multiplier (s18)
BCEA_MAX_OT_WEEKLY   = 10       # max overtime hours per week (s10)


def bcea_hourly_rate(gross_monthly: float, explicit_hourly_rate: float = None) -> float:
    """
    Return the hourly rate used for BCEA overtime calculations.
    Explicit hourly_rate takes priority (hourly employees).
    Otherwise derived from gross monthly ÷ (45 h/week × 52/12 weeks).
    """
    if explicit_hourly_rate:
        return explicit_hourly_rate
    return gross_monthly / (BCEA_WEEKLY_HOURS * BCEA_WEEKS_PER_MONTH)


def calc_overtime(
    gross_monthly: float,
    overtime_hours: float = 0,
    sunday_hours: float = 0,
    ph_hours: float = 0,
    explicit_hourly_rate: float = None,
) -> dict:
    """
    Calculate BCEA overtime amounts for a single employee in a pay period.
    - overtime_hours : weekday / Saturday OT (1.5x)
    - sunday_hours   : Sunday hours worked  (2x)
    - ph_hours       : public holiday hours (2x)
    Returns per-category hours, rand amounts, and combined total.
    """
    hr = bcea_hourly_rate(gross_monthly, explicit_hourly_rate)
    ot_amount  = round(overtime_hours * hr * BCEA_OT_RATE_WEEKDAY, 2)
    sun_amount = round(sunday_hours   * hr * BCEA_OT_RATE_SUNDAY,  2)
    ph_amount_ = round(ph_hours       * hr * BCEA_OT_RATE_PH,      2)
    total_ot   = round(ot_amount + sun_amount + ph_amount_, 2)
    return {
        "hourly_rate":     round(hr, 4),
        "overtime_hours":  overtime_hours,
        "overtime_amount": ot_amount,
        "sunday_hours":    sunday_hours,
        "sunday_amount":   sun_amount,
        "ph_hours":        ph_hours,
        "ph_amount":       ph_amount_,
        "total_overtime":  total_ot,
    }


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


def calc_payroll(
    gross_monthly: float,
    tax_year: str = None,
    annual_payroll_total: float = None,
    overtime_hours: float = 0,
    sunday_hours: float = 0,
    ph_hours: float = 0,
    explicit_hourly_rate: float = None,
) -> dict:
    """
    Compute monthly payroll including BCEA overtime.

    annual_payroll_total: sum of ALL employees' gross monthly salary * 12.
    SDL only applies if annual_payroll_total >= 500_000 (SA law).
    Pass None to always apply SDL (conservative default for single-employee calculations).

    overtime_hours : weekday/Saturday OT hours (BCEA s10 — 1.5x)
    sunday_hours   : Sunday hours worked        (BCEA s16 — 2.0x)
    ph_hours       : public holiday hours       (BCEA s18 — 2.0x)
    explicit_hourly_rate: set for hourly employees; salaried employees derive
                          hourly rate from gross_monthly / (45h × 4.333 weeks).
    """
    yr = TAX_YEARS.get(tax_year or CURRENT_TAX_YEAR, TAX_YEARS[CURRENT_TAX_YEAR])

    # ── Overtime ──────────────────────────────────────────────────────────────
    ot = calc_overtime(gross_monthly, overtime_hours, sunday_hours, ph_hours, explicit_hourly_rate)
    total_overtime = ot["total_overtime"]

    # ── Taxable gross = base salary + overtime ────────────────────────────────
    taxable_gross = gross_monthly + total_overtime

    # ── PAYE on taxable gross (annualised) ────────────────────────────────────
    annual_paye  = calc_paye(taxable_gross * 12, tax_year)
    monthly_paye = annual_paye / 12

    # ── UIF on base salary only (overtime is excluded from UIF per SARS) ─────
    uif_base     = min(gross_monthly, yr["uif_ceil"])
    uif_employee = uif_base * UIF_RATE
    uif_employer = uif_base * UIF_RATE

    # ── SDL on taxable gross ──────────────────────────────────────────────────
    SDL_THRESHOLD  = 500_000
    sdl_applicable = annual_payroll_total is None or annual_payroll_total >= SDL_THRESHOLD
    sdl = taxable_gross * SDL_RATE if sdl_applicable else 0

    net_pay    = taxable_gross - monthly_paye - uif_employee
    total_cost = taxable_gross + uif_employer + sdl

    return {
        "gross":           round(gross_monthly, 2),
        "overtime":        ot,                           # full BCEA breakdown
        "taxable_gross":   round(taxable_gross, 2),
        "paye":            round(monthly_paye, 2),
        "uif_employee":    round(uif_employee, 2),
        "uif_employer":    round(uif_employer, 2),
        "sdl":             round(sdl, 2),
        "net_pay":         round(net_pay, 2),
        "total_cost":      round(total_cost, 2),
        "tax_year":        tax_year or CURRENT_TAX_YEAR,
    }


# PAYROLL ROUTER
payroll_router = APIRouter()


class OvertimeEntry(BaseModel):
    employee_id:    int
    overtime_hours: float = 0   # weekday/Saturday OT (BCEA s10 — 1.5x)
    sunday_hours:   float = 0   # Sunday hours         (BCEA s16 — 2.0x)
    ph_hours:       float = 0   # public holiday hours (BCEA s18 — 2.0x)


class RunPayrollRequest(BaseModel):
    overtime: list[OvertimeEntry] = []


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
        "gross": 0, "taxable_gross": 0, "paye": 0, "uif_employee": 0,
        "uif_employer": 0, "sdl": 0, "net_pay": 0, "total_cost": 0
    }

    annual_payroll_total = sum(e.gross_salary for e in employees) * 12

    for emp in employees:
        c = calc_payroll(emp.gross_salary, annual_payroll_total=annual_payroll_total,
                         explicit_hourly_rate=emp.hourly_rate)
        c["employee_id"]      = emp.id
        c["employee_name"]    = f"{emp.first_name} {emp.last_name}"
        c["employee_number"]  = emp.employee_number
        c["position"]         = emp.position
        c["department"]       = emp.department
        c["grade"]            = emp.grade
        c["employment_type"]  = emp.employment_type or "salaried"
        c["hourly_rate_bcea"] = round(bcea_hourly_rate(emp.gross_salary, emp.hourly_rate), 4)
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
        "bcea": {
            "normal_weekly_hours": BCEA_WEEKLY_HOURS,
            "max_ot_weekly":       BCEA_MAX_OT_WEEKLY,
            "ot_rate_weekday":     BCEA_OT_RATE_WEEKDAY,
            "ot_rate_sunday":      BCEA_OT_RATE_SUNDAY,
            "ot_rate_ph":          BCEA_OT_RATE_PH,
        },
    }


@payroll_router.post("/run")
async def run_payroll(
    data: RunPayrollRequest = RunPayrollRequest(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    employees = db.query(Employee).filter(
        Employee.company_id == current_user.company_id,
        Employee.is_active == True
    ).all()

    if not employees:
        raise HTTPException(status_code=400, detail="No active employees found")

    # Build overtime lookup keyed by employee_id
    ot_map = {entry.employee_id: entry for entry in (data.overtime or [])}

    period = datetime.utcnow().strftime("%Y-%m")
    created = []
    annual_payroll_total = sum(e.gross_salary for e in employees) * 12

    for emp in employees:
        existing = db.query(Payslip).filter(
            Payslip.employee_id == emp.id,
            Payslip.period == period
        ).first()
        if existing:
            continue
        ot_entry = ot_map.get(emp.id, OvertimeEntry(employee_id=emp.id))
        c = calc_payroll(
            emp.gross_salary,
            annual_payroll_total=annual_payroll_total,
            overtime_hours=ot_entry.overtime_hours,
            sunday_hours=ot_entry.sunday_hours,
            ph_hours=ot_entry.ph_hours,
            explicit_hourly_rate=emp.hourly_rate,
        )
        ot = c["overtime"]
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
            overtime_hours=ot["overtime_hours"],
            overtime_amount=ot["overtime_amount"],
            sunday_hours=ot["sunday_hours"],
            sunday_amount=ot["sunday_amount"],
            ph_hours=ot["ph_hours"],
            ph_amount=ot["ph_amount"],
        )
        db.add(payslip)
        db.flush()   # get payslip.id before journal post
        created.append(emp.id)
        try:
            import journal as journal_engine
            journal_engine.init_accounts(emp.company_id, db)
            journal_engine.post_payroll(payslip, emp, db)
        except Exception as e:
            logger.error(f"Journal post failed for payslip {payslip.id}: {e}")
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Payroll processed but journal entry failed for {emp.first_name} {emp.last_name}: {e}. Payroll has been rolled back — please retry.",
            )

    db.commit()

    # Trigger monthly leave accrual alongside payroll run (idempotent within same month)
    try:
        from leave import _run_accrual_internal
        accrued = _run_accrual_internal(current_user.company_id, db)
        logger.info(f"Leave accrual: {accrued} employee(s) accrued for company {current_user.company_id}")
    except Exception as e:
        logger.warning(f"Leave accrual failed (non-fatal): {e}")

    # NOTE: Fixed asset depreciation is no longer triggered by payroll.
    # Use the "Run Depreciation" button in the Fixed Assets module.

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


def _cipc_status(company, now: datetime) -> dict:
    """
    Compute days until CIPC Annual Return is due.
    AR must be filed within 30 business days after the company's registration anniversary.
    We warn 60 days before the due date (= ~30 days before anniversary) so there's
    time to prepare and file.
    Returns a dict with: due_date, days_until_due, warning (bool), overdue (bool), message.
    """
    # Use cipc_registration_date if set; fall back to company created_at
    reg_date = getattr(company, "cipc_registration_date", None) or company.created_at
    if not reg_date:
        return {"due_date": None, "days_until_due": None, "warning": False, "overdue": False,
                "message": "Set your company registration date in Settings to enable CIPC AR reminders."}

    # This year's anniversary
    try:
        anniversary = reg_date.replace(year=now.year)
    except ValueError:
        # Handles 29 Feb on non-leap years
        anniversary = reg_date.replace(year=now.year, day=28)

    # AR due date = anniversary + 30 business days (approx as 42 calendar days)
    due_date = anniversary + timedelta(days=42)

    # If the due date has already passed this year, look at next year's
    if due_date < now:
        try:
            anniversary = reg_date.replace(year=now.year + 1)
        except ValueError:
            anniversary = reg_date.replace(year=now.year + 1, day=28)
        due_date = anniversary + timedelta(days=42)

    days_until = (due_date - now).days
    warning  = days_until <= 60
    overdue  = days_until < 0

    if overdue:
        msg = f"⚠️ CIPC Annual Return is OVERDUE by {abs(days_until)} days. File immediately at cipc.co.za to avoid penalties."
    elif warning:
        msg = f"📋 CIPC Annual Return due in {days_until} days ({due_date.strftime('%d %b %Y')}). File at cipc.co.za."
    else:
        msg = f"CIPC Annual Return due {due_date.strftime('%d %b %Y')} ({days_until} days)."

    return {
        "due_date":      due_date.strftime("%Y-%m-%d"),
        "days_until_due": days_until,
        "warning":        warning,
        "overdue":        overdue,
        "message":        msg,
    }


@reports_router.get("/dashboard")
async def dashboard(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    cid = current_user.company_id
    now = datetime.utcnow()

    # All-time paid invoices — matches the Invoices tab "Paid" KPI exactly
    paid_invoices = db.query(Invoice).filter(
        Invoice.company_id == cid,
        Invoice.status == InvoiceStatus.paid,
    ).all()
    total_revenue = sum(_to_zar(i) for i in paid_invoices)
    # Add bank-import income (posted as journal entries, not invoices)
    total_revenue += _bank_import_income(db, cid)

    outstanding_invoices = db.query(Invoice).filter(
        Invoice.company_id == cid,
        Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])
    ).all()
    total_outstanding = sum(_to_zar(i) for i in outstanding_invoices)

    # All-time expenses ex-VAT — P&L should show the net expense, not the VAT-inclusive amount
    expenses = db.query(Expense).filter(
        Expense.company_id == cid,
    ).all()
    total_expenses = sum(e.amount - (e.vat_amount or 0) for e in expenses)

    # Include PO COGS: all received purchase orders — ex-VAT to match expense treatment.
    # Delivered value only (audit fix 2026-07-02): partial POs count what was actually
    # received, matching the incremental journal postings.
    po_cogs = sum(
        _po_delivered_net(po)
        for po in db.query(PurchaseOrder).filter(
            PurchaseOrder.company_id == cid,
            PurchaseOrder.status.in_(["received", "partial", "paid"]),
        ).all()
    )
    total_expenses = total_expenses + po_cogs

    # Include all-time depreciation from fixed assets (IAS 16 — posted to journal acct 5800)
    total_depreciation = db.query(func.sum(DepreciationEntry.amount)).filter(
        DepreciationEntry.company_id == cid
    ).scalar() or 0
    total_expenses = total_expenses + total_depreciation

    employees = db.query(Employee).filter(
        Employee.company_id == cid,
        Employee.is_active == True
    ).all()
    # Sum ALL payslips for the company (including terminated employees) so that historical
    # payroll cost is never understated when headcount has changed.
    actual_payslips_total = (
        db.query(func.sum(Payslip.total_cost))
        .join(Employee, Payslip.employee_id == Employee.id)
        .filter(Employee.company_id == cid)
        .scalar()
    )
    if actual_payslips_total:
        total_payroll = actual_payslips_total
    else:
        # No payslips yet — estimate from currently active employees only
        total_payroll = sum(calc_payroll(e.gross_salary)["total_cost"] for e in employees)

    gross_profit = total_revenue - total_expenses
    net_profit   = gross_profit - total_payroll
    tax_provision = max(0, net_profit * 0.27)

    # VAT position — all-time output vs input VAT.
    # Exclude draft invoices: VAT liability only arises on issued (sent/overdue/paid) invoices.
    all_invoices_vat = db.query(Invoice).filter(
        Invoice.company_id == cid,
        Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue, InvoiceStatus.paid]),
    ).all()
    output_vat = round(sum(i.vat_amount or 0 for i in all_invoices_vat), 2)
    input_vat  = round(sum(e.vat_amount or 0 for e in expenses), 2)
    net_vat_payable = round(output_vat - input_vat, 2)

    # PO double-count warning: structural check — find expenses whose (supplier, month, net amount)
    # closely match a received PO, which would indicate the same cost recorded twice.
    # Uses ±5% amount tolerance and same calendar month to avoid false positives.
    received_pos = db.query(PurchaseOrder).filter(
        PurchaseOrder.company_id == cid,
        PurchaseOrder.status.in_(["received", "partial", "paid"]),
    ).all()
    duplicate_expense_warning = None
    for po in received_pos:
        po_date = po.received_date or po.order_date or po.created_at
        if not po_date:
            continue
        po_net = (po.total_amount or 0) - (po.vat_amount or 0)
        if po_net <= 0:
            continue
        po_sup = (po.supplier_name or "").strip().lower()
        for exp in expenses:
            if not exp.expense_date:
                continue
            # Must be in the same calendar month
            if exp.expense_date.year != po_date.year or exp.expense_date.month != po_date.month:
                continue
            # Supplier name must overlap (one contains the other, case-insensitive)
            exp_sup = (exp.vendor or "").strip().lower()
            if not po_sup or not exp_sup:
                continue
            if po_sup not in exp_sup and exp_sup not in po_sup:
                continue
            # Amount must be within 5%
            exp_net = (exp.amount or 0) - (exp.vat_amount or 0)
            if abs(exp_net - po_net) / po_net > 0.05:
                continue
            duplicate_expense_warning = (
                f"Possible double-count: Expense '{exp.vendor}' "
                f"({exp.expense_date.strftime('%b %Y')}, R{exp_net:,.2f} excl. VAT) "
                f"matches received PO {po.po_number} "
                f"({po_date.strftime('%b %Y')}, R{po_net:,.2f} excl. VAT). "
                f"Verify this expense does not duplicate the PO cost."
            )
            break
        if duplicate_expense_warning:
            break

    # CIPC Annual Return reminder
    company = db.query(Company).filter(Company.id == cid).first()
    cipc = _cipc_status(company, now) if company else None

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
        "output_vat":        output_vat,
        "input_vat":         input_vat,
        "net_vat_payable":   net_vat_payable,
        "cipc":              cipc,
        "po_duplicate_warning": duplicate_expense_warning,
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
            _to_zar(inv) for inv in db.query(Invoice).filter(
                Invoice.company_id == cid,
                Invoice.status == InvoiceStatus.paid,
                Invoice.paid_date >= start,
                Invoice.paid_date < end
            ).all()
        )
        # Add bank-import income for this month
        revenue += _bank_import_income(db, cid, start, end)
        # Expenses ex-VAT for P&L
        expenses = sum(
            (exp.amount - (exp.vat_amount or 0)) for exp in db.query(Expense).filter(
                Expense.company_id == cid,
                Expense.expense_date >= start,
                Expense.expense_date < end
            ).all()
        )
        # Add PO COGS for POs received/partial/paid in this month — ex-VAT,
        # delivered value only for partial POs (audit fix 2026-07-02)
        po_cogs = sum(
            _po_delivered_net(po)
            for po in db.query(PurchaseOrder).filter(
                PurchaseOrder.company_id == cid,
                PurchaseOrder.status.in_(["received", "partial", "paid"]),
                PurchaseOrder.received_date >= start,
                PurchaseOrder.received_date < end,
            ).all()
        )
        expenses = expenses + po_cogs

        # Add depreciation charged in this period (DepreciationEntry.period = "YYYY-MM")
        period_str = start.strftime("%Y-%m")
        depreciation = db.query(func.sum(DepreciationEntry.amount)).filter(
            DepreciationEntry.company_id == cid,
            DepreciationEntry.period == period_str,
        ).scalar() or 0
        expenses = expenses + depreciation

        months.append({
            "month":        start.strftime("%b"),
            "revenue":      round(revenue, 2),
            "expenses":     round(expenses, 2),
            "gross_profit": round(revenue - expenses, 2),
            # Legacy alias kept for any existing consumers
            "profit":       round(revenue - expenses, 2),
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
    # Fixed assets (IAS 16) — cost less accumulated depreciation
    fixed_assets_cost     = bal("1500")
    accum_depreciation    = bal("1510")   # contra-asset: journal stores as negative (credit normal)
    fixed_assets_net      = round(fixed_assets_cost + accum_depreciation, 2)  # cost - accum (accum is negative)
    total_assets = round(cash_and_equivalents + trade_receivables + inventory_at_cost + vat_input_recoverable + fixed_assets_net, 2)

    # ── LIABILITIES ───────────────────────────────────────────────────────────
    accounts_payable    = bal("2000")
    vat_payable         = bal("2100")
    paye_payable        = bal("2200")
    uif_payable         = bal("2210")
    sdl_payable         = bal("2220")
    income_tax_payable  = bal("2126")   # Corporate income tax due to SARS
    prov_tax_payable    = bal("2127")   # Provisional tax (IRP6) due to SARS
    total_liabilities = round(
        accounts_payable + vat_payable + paye_payable + uif_payable + sdl_payable
        + income_tax_payable + prov_tax_payable,
        2,
    )

    # ── EQUITY ────────────────────────────────────────────────────────────────
    # ZuZan does not post year-end closing entries, so account 3000 stays at zero
    # unless the owner manually journals equity (e.g. share capital, drawings).
    # Retained income = explicit equity balance (3000) + cumulative P&L derived
    # from all revenue and expense journal accounts — identical approach to AFS.
    rev_accounts = db.query(Account).filter(Account.company_id==cid, Account.type==AccountType.revenue).all()
    exp_accounts = db.query(Account).filter(Account.company_id==cid, Account.type==AccountType.expense).all()
    cum_revenue  = sum(journal_engine.account_balance(a, db) for a in rev_accounts)
    cum_expenses = sum(journal_engine.account_balance(a, db) for a in exp_accounts)
    retained_income = round(bal("3000") + cum_revenue - cum_expenses, 2)
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
            "fixed_assets_cost":     fixed_assets_cost,
            "accum_depreciation":    accum_depreciation,
            "fixed_assets_net":      fixed_assets_net,
            "total":                 total_assets,
        },
        "liabilities": {
            "accounts_payable":   accounts_payable,
            "vat_payable":        vat_payable,
            "paye_payable":       paye_payable,
            "uif_payable":        uif_payable,
            "sdl_payable":        sdl_payable,
            "income_tax_payable": income_tax_payable,
            "prov_tax_payable":   prov_tax_payable,
            "total":              total_liabilities,
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
        Invoice.due_date <= cutoff_90
    ).all()
    amount_90 = round(sum(_to_zar(i) for i in overdue_90), 2)
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
                       "days": (now - i.due_date).days} for i in overdue_90]})

    # ── RULE 3: VAT control reconciliation ────────────────────────────────────
    # Exclude draft invoices from output VAT — consistent with /reports/dashboard fix.
    all_invoices = db.query(Invoice).filter(
        Invoice.company_id==cid,
        Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue, InvoiceStatus.paid]),
    ).all()
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
    # Delivered value only for partial POs (audit fix 2026-07-02)
    open_pos = db.query(PurchaseOrder).filter(
        PurchaseOrder.company_id==cid,
        PurchaseOrder.status.in_(["received","partial"])
    ).all()
    ap_total = round(sum(_po_delivered_total(po) for po in open_pos), 2)
    if not open_pos:
        checks.append({"rule": "Accounts Payable", "status": "pass",
            "detail": "No received purchase orders awaiting payment.", "amount": None, "items": []})
    else:
        checks.append({"rule": "Accounts Payable", "status": "warn",
            "detail": f"{len(open_pos)} received PO(s) totalling R {ap_total:,.2f} recorded as accounts payable.",
            "amount": ap_total,
            "items": [{"id": po.po_number, "supplier": po.supplier_name,
                       "amount": _po_delivered_total(po), "status": po.status} for po in open_pos]})

    # ── RULE 6: AR control account — journal 1100 vs outstanding invoices ────
    from database import Account, JournalLine
    import journal as journal_engine
    journal_engine.init_accounts(cid, db)
    ar_acct = db.query(Account).filter(Account.company_id == cid, Account.code == "1100").first()
    if ar_acct:
        ar_journal_bal = journal_engine.account_balance(ar_acct, db)
        outstanding_invs = db.query(Invoice).filter(
            Invoice.company_id == cid,
            Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])
        ).all()
        ar_raw_total = round(sum(_to_zar(i) for i in outstanding_invs), 2)
        ar_diff = round(ar_journal_bal - ar_raw_total, 2)
        if abs(ar_diff) < 1.0:
            checks.append({"rule": "AR Control Account (1100)", "status": "pass",
                "detail": f"Journal AR balance R {ar_journal_bal:,.2f} reconciles with outstanding invoices R {ar_raw_total:,.2f} ✓",
                "amount": ar_journal_bal})
        else:
            checks.append({"rule": "AR Control Account (1100)", "status": "fail",
                "detail": f"AR journal balance R {ar_journal_bal:,.2f} differs from outstanding invoice total R {ar_raw_total:,.2f} by R {ar_diff:,.2f}. Likely caused by a missed journal posting. Run /journal/backfill to repair.",
                "amount": ar_diff})

    # ── RULE 7: AP control account — journal 2000 vs open POs + unpaid credit expenses ──
    ap_acct = db.query(Account).filter(Account.company_id == cid, Account.code == "2000").first()
    if ap_acct:
        from database import Expense as _ExpenseModel, JournalEntry as _JE
        ap_journal_bal = journal_engine.account_balance(ap_acct, db)
        open_po_list = db.query(PurchaseOrder).filter(
            PurchaseOrder.company_id == cid,
            PurchaseOrder.status.in_(["received", "partial"])
        ).all()
        # Per-PO expected AP = sum of AP credits posted by each delivery (audit fix
        # 2026-07-02) — same lookup as /reports/creditors-aging. Using po.total_amount
        # here false-failed this check whenever a partially delivered PO existed,
        # because the journal correctly carries only the delivered amount.
        # Fallback to po.total_amount when no journal entry exists yet.
        po_ap_credit_map: dict = {}
        if open_po_list:
            _rows = (
                db.query(_JE.source_id, func.sum(JournalLine.credit))
                .join(JournalLine, JournalLine.entry_id == _JE.id)
                .filter(
                    _JE.company_id == cid,
                    _JE.source == "purchase_order",
                    _JE.source_id.in_([po.id for po in open_po_list]),
                    JournalLine.account_id == ap_acct.id,
                )
                .group_by(_JE.source_id)
                .all()
            )
            for _po_id, _credit in _rows:
                po_ap_credit_map[_po_id] = round(_credit or 0, 2)
        open_po_total = round(sum(
            po_ap_credit_map.get(po.id, round(po.total_amount or 0, 2))
            for po in open_po_list
        ), 2)
        # Unpaid on-credit expenses also sit in AP (2000) until POST /expenses/{id}/pay is called.
        credit_exp_total = round(
            sum(
                (exp.amount or 0)
                for exp in db.query(_ExpenseModel).filter(
                    _ExpenseModel.company_id == cid,
                    _ExpenseModel.is_on_credit == True,
                    _ExpenseModel.paid_at == None,  # noqa: E711
                ).all()
            ),
            2,
        )
        ap_raw_total = round(open_po_total + credit_exp_total, 2)
        ap_diff = round(ap_journal_bal - ap_raw_total, 2)
        detail_breakdown = f"Open POs R {open_po_total:,.2f}"
        if credit_exp_total:
            detail_breakdown += f" + unpaid credit expenses R {credit_exp_total:,.2f}"
        if abs(ap_diff) < 1.0:
            checks.append({"rule": "AP Control Account (2000)", "status": "pass",
                "detail": f"Journal AP balance R {ap_journal_bal:,.2f} reconciles with {detail_breakdown} = R {ap_raw_total:,.2f} ✓",
                "amount": ap_journal_bal})
        else:
            checks.append({"rule": "AP Control Account (2000)", "status": "fail",
                "detail": f"AP journal balance R {ap_journal_bal:,.2f} differs from {detail_breakdown} = R {ap_raw_total:,.2f} by R {ap_diff:,.2f}. Likely caused by a missed journal posting. Run /journal/backfill to repair.",
                "amount": ap_diff})

    # ── RULE 8: Inventory valuation ───────────────────────────────────────────
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

    # ── RULE 8: Unmatched revenue — paid invoices with no expense offset ───────
    # Simple check: gross margin — warn if expenses are >90% of revenue
    total_rev = round(sum(_to_zar(i) for i in db.query(Invoice).filter(Invoice.company_id==cid, Invoice.status==InvoiceStatus.paid).all()), 2)
    total_exp = round(sum(e.amount - (e.vat_amount or 0) for e in all_expenses), 2)
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
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    cid = current_user.company_id
    now = datetime.utcnow()

    # Resolve date range — honour the caller's date_from/date_to; default to current month.
    if date_from:
        period_start = datetime.strptime(date_from, "%Y-%m-%d")
    else:
        period_start = datetime(now.year, now.month, 1)

    if date_to:
        # date_to is inclusive (e.g. "2026-06-30"); add 1 day for open-ended DB filter
        period_end = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
    else:
        period_end = None   # no upper bound

    # Human-readable period label
    end_label = (period_end - timedelta(days=1)).strftime("%d %b %Y") if period_end else "present"
    period_label = f"{period_start.strftime('%d %b %Y')} – {end_label}"

    # ── Receipts ──────────────────────────────────────────────────────────────
    inv_q = db.query(Invoice).filter(
        Invoice.company_id == cid,
        Invoice.status == InvoiceStatus.paid,
        Invoice.paid_date >= period_start,
    )
    if period_end:
        inv_q = inv_q.filter(Invoice.paid_date < period_end)
    paid_in_period = inv_q.all()
    cash_receipts  = round(sum(_to_zar(i) for i in paid_in_period), 2)
    # Add bank-import income (posted as journal entries, not invoices)
    cash_receipts  = round(cash_receipts + _bank_import_income(db, cid, period_start, period_end), 2)

    # ── Payments ──────────────────────────────────────────────────────────────
    exp_q = db.query(Expense).filter(
        Expense.company_id == cid,
        Expense.expense_date >= period_start,
    )
    if period_end:
        exp_q = exp_q.filter(Expense.expense_date < period_end)
    expenses_in_period = exp_q.all()
    cash_payments = round(sum(e.amount for e in expenses_in_period), 2)

    # ── Payroll ───────────────────────────────────────────────────────────────
    pay_q = db.query(Payslip).join(Employee).filter(
        Employee.company_id == cid,
        Payslip.generated_at >= period_start,
    )
    if period_end:
        pay_q = pay_q.filter(Payslip.generated_at < period_end)
    payslips_in_period = pay_q.all()
    payroll_disbursed  = round(sum(p.net_pay for p in payslips_in_period), 2)
    sars_payments      = round(sum(p.paye + p.uif_employee + p.uif_employer + p.sdl for p in payslips_in_period), 2)

    # ── VAT net-to-SARS ──────────────────────────────────────────────────────
    # Output VAT collected on paid invoices minus input VAT on expenses.
    output_vat = round(sum(i.vat_amount or 0 for i in paid_in_period), 2)
    input_vat  = round(sum(e.vat_amount or 0 for e in expenses_in_period), 2)
    net_vat_to_sars = round(output_vat - input_vat, 2)

    net_operating = round(
        cash_receipts - cash_payments - payroll_disbursed - sars_payments - net_vat_to_sars,
        2,
    )

    return {
        "period": period_label,
        "operating": {
            "cash_receipts_from_customers": cash_receipts,
            "cash_paid_to_suppliers":       -cash_payments,
            "payroll_net_pay":              -payroll_disbursed,
            "sars_paye_uif_sdl":            -sars_payments,
            "sars_vat_net":                 -net_vat_to_sars,
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
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    cid = current_user.company_id
    now = datetime.utcnow()

    # Parse date range; default to current month if not provided
    if date_from and date_to:
        try:
            period_start = datetime.strptime(date_from, "%Y-%m-%d")
            period_end   = datetime.strptime(date_to,   "%Y-%m-%d") + timedelta(days=1)
        except ValueError:
            period_start = datetime(now.year, now.month, 1)
            period_end   = now + timedelta(days=1)
    else:
        period_start = datetime(now.year, now.month, 1)
        period_end   = now + timedelta(days=1)

    from_period = period_start.strftime("%Y-%m")
    to_period   = (period_end - timedelta(days=1)).strftime("%Y-%m")
    period_label = (
        f"{period_start.strftime('%d %b %Y')} – {(period_end - timedelta(days=1)).strftime('%d %b %Y')}"
        if date_from and date_to else now.strftime("%B %Y")
    )

    paid_invoices = db.query(Invoice).filter(
        Invoice.company_id == cid,
        Invoice.status == InvoiceStatus.paid,
        Invoice.paid_date >= period_start,
        Invoice.paid_date < period_end,
    ).all()
    revenue = round(sum(_to_zar(i) for i in paid_invoices), 2)
    # Add bank-import income in the same date range
    revenue = round(revenue + _bank_import_income(db, cid, period_start, period_end), 2)

    expenses = db.query(Expense).filter(
        Expense.company_id == cid,
        Expense.expense_date >= period_start,
        Expense.expense_date < period_end,
    ).all()
    # Ex-VAT expenses for P&L — consistent with dashboard and monthly-trend endpoints
    total_expenses = round(sum(e.amount - (e.vat_amount or 0) for e in expenses), 2)

    expense_by_cat: dict = {}
    for e in expenses:
        key = e.category or "Other"
        expense_by_cat[key] = round(expense_by_cat.get(key, 0) + (e.amount - (e.vat_amount or 0)), 2)

    # Include PO COGS: received purchase orders in range — ex-VAT
    po_cogs_items = db.query(PurchaseOrder).filter(
        PurchaseOrder.company_id == cid,
        PurchaseOrder.status.in_(["received", "partial", "paid"]),
        PurchaseOrder.received_date >= period_start,
        PurchaseOrder.received_date < period_end,
    ).all()
    # Delivered value only for partial POs (audit fix 2026-07-02)
    po_cogs = round(sum(_po_delivered_net(po) for po in po_cogs_items), 2)
    if po_cogs:
        total_expenses = round(total_expenses + po_cogs, 2)
        expense_by_cat["Cost of Sales (POs)"] = round(
            expense_by_cat.get("Cost of Sales (POs)", 0) + po_cogs, 2
        )

    # Include depreciation across all periods in range (IAS 16 — DepreciationEntry.period = "YYYY-MM")
    period_depreciation = db.query(func.sum(DepreciationEntry.amount)).filter(
        DepreciationEntry.company_id == cid,
        DepreciationEntry.period >= from_period,
        DepreciationEntry.period <= to_period,
    ).scalar() or 0
    if period_depreciation:
        total_expenses = round(total_expenses + period_depreciation, 2)
        expense_by_cat["Depreciation"] = round(period_depreciation, 2)

    active_employees = db.query(Employee).filter(
        Employee.company_id == cid,
        Employee.is_active == True
    ).all()
    # Sum payslips for ALL employees (including terminated) so that periods where headcount
    # changed are not understated. Active employees are still used for the fallback estimate.
    period_payslips_total = (
        db.query(func.sum(Payslip.total_cost))
        .join(Employee, Payslip.employee_id == Employee.id)
        .filter(
            Employee.company_id == cid,
            Payslip.period >= from_period,
            Payslip.period <= to_period,
        )
        .scalar()
    )
    if period_payslips_total:
        total_payroll_cost = round(period_payslips_total, 2)
    else:
        # No payslips in range — estimate from currently active employees
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
    total_outstanding = round(sum(_to_zar(i) for i in outstanding), 2)
    overdue_count     = sum(1 for i in outstanding if i.status == InvoiceStatus.overdue)

    # Anchor the 6-month window to period_end so that when the user filters to a
    # historical range (e.g. FY2026), the trend bars cover that actual period
    # rather than always ending at today.
    trend_anchor = min(period_end, now + timedelta(days=1))
    trend = []
    for i in range(5, -1, -1):
        m = trend_anchor.month - i
        y = trend_anchor.year
        while m <= 0:
            m += 12
            y -= 1
        start = datetime(y, m, 1)
        end_m, end_y = (m + 1, y) if m < 12 else (1, y + 1)
        end = datetime(end_y, end_m, 1)
        rev = round(sum(_to_zar(inv) for inv in db.query(Invoice).filter(
            Invoice.company_id == cid, Invoice.status == InvoiceStatus.paid,
            Invoice.paid_date >= start, Invoice.paid_date < end).all()), 2)
        # Bank-import income + any non-invoice revenue for this month
        rev = round(rev + _bank_import_income(db, cid, start, end), 2)
        exp_rows = db.query(Expense).filter(
            Expense.company_id == cid,
            Expense.expense_date >= start, Expense.expense_date < end).all()
        exp = round(sum(ex.amount - (ex.vat_amount or 0) for ex in exp_rows), 2)
        po_c = round(sum(_po_delivered_net(po) for po in db.query(PurchaseOrder).filter(
            PurchaseOrder.company_id == cid,
            PurchaseOrder.status.in_(["received", "partial", "paid"]),
            PurchaseOrder.received_date >= start,
            PurchaseOrder.received_date < end,
        ).all()), 2)
        exp = round(exp + po_c, 2)
        # Add depreciation for this period
        trend_period = start.strftime("%Y-%m")
        trend_depr = db.query(func.sum(DepreciationEntry.amount)).filter(
            DepreciationEntry.company_id == cid,
            DepreciationEntry.period == trend_period,
        ).scalar() or 0
        exp = round(exp + trend_depr, 2)
        trend.append({"month": start.strftime("%b"), "revenue": rev, "expenses": exp, "gross_profit": round(rev - exp, 2), "profit": round(rev - exp, 2)})

    return {
        "period":       period_label,
        "generated_at": now.isoformat(),
        "pl": {
            "revenue":              revenue,
            "po_cogs":              po_cogs,
            "depreciation_amount":  round(period_depreciation, 2),
            "total_expenses":       total_expenses,
            "expense_breakdown":    expense_by_cat,
            "gross_profit":         gross_profit,
            "payroll_cost":         total_payroll_cost,
            "ebit":                 ebit,
            "tax_provision":        tax_provision,
            "net_profit":           net_profit,
            "gross_margin_pct":     gross_margin,
            "net_margin_pct":       net_margin,
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
        Invoice.paid_date >= year_start
    ).all()
    ytd_revenue = round(sum(_to_zar(i) for i in paid_invoices), 2)
    # Add bank-import income (journal entries, not invoices) — avoids double-counting
    ytd_revenue = round(ytd_revenue + _bank_import_income(db, cid, year_start), 2)

    expenses = db.query(Expense).filter(
        Expense.company_id == cid,
        Expense.expense_date >= year_start
    ).all()
    # Ex-VAT expenses — consistent with dashboard/management endpoints
    ytd_expenses = round(sum(e.amount - (e.vat_amount or 0) for e in expenses), 2)

    # Add PO COGS (received/partial/paid POs) — ex-VAT, consistent with dashboard
    po_cogs_ytd = sum(
        (po.total_amount or 0) - (po.vat_amount or 0)
        for po in db.query(PurchaseOrder).filter(
            PurchaseOrder.company_id == cid,
            PurchaseOrder.status.in_(["received", "partial", "paid"]),
            PurchaseOrder.received_date >= year_start,
        ).all()
    )
    ytd_expenses = round(ytd_expenses + po_cogs_ytd, 2)

    # Add YTD depreciation (DepreciationEntry records for periods in this year)
    year_start_period = f"{now.year}-01"
    year_end_period   = f"{now.year}-12"
    ytd_depreciation = db.query(func.sum(DepreciationEntry.amount)).filter(
        DepreciationEntry.company_id == cid,
        DepreciationEntry.period >= year_start_period,
        DepreciationEntry.period <= year_end_period,
    ).scalar() or 0
    ytd_expenses = round(ytd_expenses + ytd_depreciation, 2)

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
        # Only age from due_date — invoices without a due_date go into not_due to avoid
        # falsely overstating overdue balances (audit fix: removed issue_date/created_at fallback)
        due = inv.due_date
        entry = {
            "id":             inv.invoice_number,
            "client":         inv.client_name,
            "amount":         round(_to_zar(inv), 2),
            "due_date":       due.strftime("%Y-%m-%d") if due else None,
            "days_overdue":   0,
            "status":         str(inv.status).split(".")[-1],
        }
        if due is None:
            # No due date — treat as not yet due
            buckets["not_due"].append(entry)
        else:
            days_overdue = (now - due).days
            entry["days_overdue"] = max(0, days_overdue)
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
    """
    Creditors book with aging — outstanding purchase orders (received/partial) and
    unpaid on-credit expenses, grouped by vendor/supplier, aged from due date.
    Fully paid POs and paid credit expenses are excluded.
    """
    from database import Supplier as SupplierModel, Expense as ExpenseModel, Account as _Account, JournalEntry as _JE, JournalLine as _JL
    from crypto import decrypt_field
    cid = current_user.company_id
    now = datetime.utcnow()

    # Outstanding POs: received but not yet paid
    open_pos = db.query(PurchaseOrder).filter(
        PurchaseOrder.company_id == cid,
        PurchaseOrder.status.in_(["received", "partial"]),
    ).order_by(PurchaseOrder.received_date.desc()).all()

    # For partial POs, the true AP balance is the sum of AP credits posted to account 2000
    # by each individual delivery (post_po_received), not po.total_amount.
    # We pre-build this lookup so the per-PO loop is O(1).
    ap_acct = db.query(_Account).filter(_Account.company_id == cid, _Account.code == "2000").first()
    po_ap_amounts: dict = {}  # po.id -> actual AP credits outstanding (excl. any partial payment)
    if ap_acct and open_pos:
        po_ids = [po.id for po in open_pos]
        rows = (
            db.query(_JE.source_id, func.sum(_JL.credit))
            .join(_JL, _JL.entry_id == _JE.id)
            .filter(
                _JE.company_id == cid,
                _JE.source == "purchase_order",
                _JE.source_id.in_(po_ids),
                _JL.account_id == ap_acct.id,
            )
            .group_by(_JE.source_id)
            .all()
        )
        for po_id, total_credit in rows:
            po_ap_amounts[po_id] = round(total_credit or 0, 2)

    # Build a supplier lookup for payment terms and bank details
    supplier_cache: dict = {}
    def _get_supplier(supplier_id):
        if supplier_id is None:
            return None
        if supplier_id not in supplier_cache:
            supplier_cache[supplier_id] = db.query(SupplierModel).filter(
                SupplierModel.id == supplier_id
            ).first()
        return supplier_cache[supplier_id]

    vendor_map: dict = {}
    for po in open_pos:
        sup = _get_supplier(po.supplier_id)
        payment_terms = (sup.payment_terms if sup else 30) or 30
        vendor_name = po.supplier_name or (sup.name if sup else "Unknown")

        # Age from due date: delivery_date + payment_terms days
        base_date = po.received_date or po.order_date or po.created_at
        due_date = base_date + timedelta(days=payment_terms) if base_date else None
        days_overdue = (now - due_date).days if due_date else 0
        bucket = (
            "not_due" if days_overdue < 0
            else "current" if days_overdue <= 30
            else "31_60"   if days_overdue <= 60
            else "61_90"   if days_overdue <= 90
            else "over_90"
        )

        if vendor_name not in vendor_map:
            vendor_map[vendor_name] = {
                "vendor":        vendor_name,
                "supplier_id":   po.supplier_id,
                "bank_name":     decrypt_field(sup.bank_name)      if sup else None,
                "account_number":decrypt_field(sup.account_number) if sup else None,
                "branch_code":   decrypt_field(sup.branch_code)    if sup else None,
                "account_type":  sup.account_type                  if sup else None,
                "invoices": [],
                "total": 0,
            }

        # Use the journal AP balance for this PO as the creditor amount.
        # For partial POs this reflects only what was actually delivered; for full
        # receipts it equals po.total_amount.  Fall back to po.total_amount when
        # no journal entry exists yet (e.g. immediately after a failed journal post).
        po_amount = po_ap_amounts.get(po.id, round(po.total_amount or 0, 2))

        entry = {
            "id":           po.po_number,
            "description":  po.notes or f"Purchase order {po.po_number}",
            "status":       po.status,
            "amount":       po_amount,
            "received_date":base_date.strftime("%Y-%m-%d") if base_date else None,
            "due_date":     due_date.strftime("%Y-%m-%d") if due_date else None,
            "days_overdue": max(0, days_overdue),
            "days_until_due": max(0, -days_overdue) if days_overdue < 0 else 0,
            "bucket":       bucket,
        }
        vendor_map[vendor_name]["invoices"].append(entry)
        vendor_map[vendor_name]["total"] = round(
            vendor_map[vendor_name]["total"] + po_amount, 2
        )

    # On-credit expenses not yet paid — these create an AP liability identical to POs.
    # Aged from expense_date + 30 days (expenses have no per-supplier payment_terms).
    credit_expenses = db.query(ExpenseModel).filter(
        ExpenseModel.company_id == cid,
        ExpenseModel.is_on_credit == True,
        ExpenseModel.paid_at == None,  # noqa: E711
    ).all()

    for exp in credit_expenses:
        vendor_name = exp.vendor or "Unknown"
        base_date = exp.expense_date or exp.created_at
        exp_payment_terms = 30  # default — expenses don't have a supplier-level payment_terms
        due_date = base_date + timedelta(days=exp_payment_terms) if base_date else None
        days_overdue = (now - due_date).days if due_date else 0
        bucket = (
            "not_due" if days_overdue < 0
            else "current" if days_overdue <= 30
            else "31_60"   if days_overdue <= 60
            else "61_90"   if days_overdue <= 90
            else "over_90"
        )

        if vendor_name not in vendor_map:
            vendor_map[vendor_name] = {
                "vendor":        vendor_name,
                "supplier_id":   None,
                "bank_name":     None,
                "account_number":None,
                "branch_code":   None,
                "account_type":  None,
                "invoices": [],
                "total": 0,
            }

        entry = {
            "id":            f"EXP-{exp.id}",
            "description":   exp.description or f"Expense — {exp.vendor}",
            "status":        "on_credit",
            "amount":        round(exp.amount or 0, 2),
            "received_date": base_date.strftime("%Y-%m-%d") if base_date else None,
            "due_date":      due_date.strftime("%Y-%m-%d") if due_date else None,
            "days_overdue":  max(0, days_overdue),
            "days_until_due":max(0, -days_overdue) if days_overdue < 0 else 0,
            "bucket":        bucket,
        }
        vendor_map[vendor_name]["invoices"].append(entry)
        vendor_map[vendor_name]["total"] = round(
            vendor_map[vendor_name]["total"] + (exp.amount or 0), 2
        )

    vendors = sorted(vendor_map.values(), key=lambda x: x["total"], reverse=True)

    all_entries = [e for v in vendors for e in v["invoices"]]
    def btotal(bucket): return round(sum(e["amount"] for e in all_entries if e["bucket"] == bucket), 2)

    return {
        "as_at":   now.strftime("%d %B %Y"),
        "vendors": vendors,
        "totals": {
            "not_due": btotal("not_due"),
            "current": btotal("current"),
            "31_60":   btotal("31_60"),
            "61_90":   btotal("61_90"),
            "over_90": btotal("over_90"),
            "grand":   round(sum(e["amount"] for e in all_entries), 2),
        },
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
    # All invoices issued in the period (tax point = invoice issue_date, not created_at).
    # Using issue_date ensures backdated invoices and bulk-imported invoices land in the
    # correct VAT period, consistent with SARS requirements.
    all_invoices = db.query(Invoice).filter(
        Invoice.company_id == cid,
        Invoice.issue_date >= start,
        Invoice.issue_date < end,
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

import os as _os
PAYFAST_MERCHANT_ID  = _os.environ.get("PAYFAST_MERCHANT_ID",  "10000100")
PAYFAST_MERCHANT_KEY = _os.environ.get("PAYFAST_MERCHANT_KEY", "46f0cd694581a")
PAYFAST_PASSPHRASE   = _os.environ.get("PAYFAST_PASSPHRASE",   "")
PAYFAST_SANDBOX      = _os.environ.get("PAYFAST_SANDBOX", "true").lower() == "true"
PAYFAST_URL          = "https://sandbox.payfast.co.za/eng/process" if PAYFAST_SANDBOX else "https://www.payfast.co.za/eng/process"
BACKEND_URL          = _os.environ.get("BACKEND_URL", "https://zuzan-backend.onrender.com")
FRONTEND_URL         = _os.environ.get("FRONTEND_URL", "https://zuzan-app.onrender.com")

try:
    from config import PLAN_PRICES  # single source of truth — see config.py
except ImportError:
    PLAN_PRICES = {
        "starter":      {"monthly": 399,  "annual": 3990},
        "professional": {"monthly": 899,  "annual": 8990},
        "business":     {"monthly": 1499, "annual": 14990},
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
        "return_url":       f"{FRONTEND_URL}/payment/success",
        "cancel_url":       f"{FRONTEND_URL}/payment/cancel",
        "notify_url":       f"{BACKEND_URL}/payments/notify",
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

    # Signature verification
    sig_data = {k: v for k, v in data.items() if k != "signature"}
    expected_sig = pf_signature(sig_data, PAYFAST_PASSPHRASE)
    received_sig = data.get("signature", "")
    if not PAYFAST_SANDBOX and received_sig != expected_sig:
        logger.warning(f"PayFast notify: signature mismatch (expected {expected_sig}, got {received_sig})")
        return JSONResponse(content={"status": "error", "detail": "Invalid signature"}, status_code=400)

    payment = db.query(Payment).filter(Payment.id == int(pf_id)).first()
    if not payment:
        return JSONResponse(content={"status": "error"}, status_code=404)

    if status == "COMPLETE":
        payment.status     = "completed"
        payment.payfast_id = data.get("pf_payment_id")
        company = db.query(Company).filter(Company.id == int(data.get("custom_str1", 0))).first()
        if company:
            from database import SubscriptionStatus, PlanType, BillingCycle, SubscriptionPayment
            company.subscription_status = SubscriptionStatus.active
            plan_val      = data.get("custom_str2", "starter")
            cycle_val     = data.get("custom_str3", "monthly")
            company.plan          = PlanType(plan_val)
            company.billing_cycle = BillingCycle(cycle_val)

            # ── Log to ZuZan's own revenue ledger ──────────────────────────
            amount_paid = float(data.get("amount_gross", payment.amount or 0))
            now = datetime.utcnow()
            from dateutil.relativedelta import relativedelta
            period_end = now + (relativedelta(years=1) if cycle_val == "annual" else relativedelta(months=1))
            owner = company.users[0] if company.users else None
            sub_pay = SubscriptionPayment(
                company_id          = company.id,
                company_name        = company.name,
                owner_email         = owner.email if owner else None,
                plan                = plan_val,
                billing_cycle       = cycle_val,
                amount              = amount_paid,
                payfast_payment_id  = data.get("pf_payment_id"),
                internal_payment_id = payment.id,
                status              = "success",
                payment_date        = now,
                period_start        = now,
                period_end          = period_end,
            )
            db.add(sub_pay)
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
