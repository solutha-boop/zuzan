"""
ZuZan - Payroll Engine, Reports and PayFast Payment Gateway
Fixed clean version - no compact syntax
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from database import get_db, Employee, Payslip, Invoice, Expense, Company, Payment, InvoiceStatus
from auth import get_current_user, User
import hashlib
import logging

logger = logging.getLogger("zuzan.payroll")

# ── SA TAX TABLES 2025/2026 ───────────────────────────────────────────────────
PAYE_BRACKETS = [
    {"min": 0,       "max": 237100,  "rate": 0.18, "base": 0},
    {"min": 237101,  "max": 370500,  "rate": 0.26, "base": 42678},
    {"min": 370501,  "max": 512800,  "rate": 0.31, "base": 77362},
    {"min": 512801,  "max": 673000,  "rate": 0.36, "base": 121475},
    {"min": 673001,  "max": 857900,  "rate": 0.39, "base": 179147},
    {"min": 857901,  "max": 1817000, "rate": 0.41, "base": 251258},
    {"min": 1817001, "max": 9999999, "rate": 0.45, "base": 644489},
]

PRIMARY_REBATE  = 17235
UIF_RATE        = 0.01
UIF_CEIL        = 17712
SDL_RATE        = 0.01
PAYROLL_PER_EMP = 17.50
PAYROLL_MIN     = 99.00


def calc_paye(annual_income: float) -> float:
    bracket = None
    for b in PAYE_BRACKETS:
        if b["min"] <= annual_income <= b["max"]:
            bracket = b
            break
    if not bracket:
        return 0
    tax = bracket["base"] + (annual_income - bracket["min"]) * bracket["rate"] - PRIMARY_REBATE
    return max(0, tax)


def calc_payroll(gross_monthly: float) -> dict:
    annual_paye = calc_paye(gross_monthly * 12)
    monthly_paye = annual_paye / 12
    uif_base = min(gross_monthly, UIF_CEIL)
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
    }


# ── PAYROLL ROUTER ────────────────────────────────────────────────────────────
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
        created.append(emp.id)

    db.commit()
    return {
        "status":           "processed",
        "period":           period,
        "payslips_created": len(created),
        "message":          f"Payroll processed for {len(created)} employees.",
    }


# ── REPORTS ROUTER ────────────────────────────────────────────────────────────
reports_router = APIRouter()


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
        Invoice.created_at >= month_start
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
                Invoice.created_at >= start,
                Invoice.created_at < end
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
    cid = current_user.company_id
    now = datetime.utcnow()

    # Trade receivables = outstanding invoices
    outstanding_invoices = db.query(Invoice).filter(
        Invoice.company_id == cid,
        Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])
    ).all()
    trade_receivables = round(sum(i.total_amount for i in outstanding_invoices), 2)

    # Cash approximation = total revenue collected - total expenses paid
    all_paid = db.query(Invoice).filter(
        Invoice.company_id == cid,
        Invoice.status == InvoiceStatus.paid
    ).all()
    total_revenue_collected = sum(i.total_amount for i in all_paid)

    all_expenses = db.query(Expense).filter(Expense.company_id == cid).all()
    total_expenses_paid = sum(e.amount for e in all_expenses)

    payslips = db.query(Payslip).join(Employee).filter(Employee.company_id == cid).all()
    total_payroll_paid = sum(p.net_pay for p in payslips)

    cash_and_equivalents = round(total_revenue_collected - total_expenses_paid - total_payroll_paid, 2)

    # Liabilities: PAYE + UIF + SDL from last payroll run (current month)
    month_start = datetime(now.year, now.month, 1)
    recent_payslips = db.query(Payslip).join(Employee).filter(
        Employee.company_id == cid,
        Payslip.generated_at >= month_start
    ).all()
    paye_payable = round(sum(p.paye for p in recent_payslips), 2)
    uif_payable  = round(sum(p.uif_employee + p.uif_employer for p in recent_payslips), 2)
    sdl_payable  = round(sum(p.sdl for p in recent_payslips), 2)

    total_assets      = round(cash_and_equivalents + trade_receivables, 2)
    total_liabilities = round(paye_payable + uif_payable + sdl_payable, 2)
    equity            = round(total_assets - total_liabilities, 2)

    return {
        "date": now.strftime("%d %B %Y"),
        "assets": {
            "cash_and_equivalents": cash_and_equivalents,
            "trade_receivables":    trade_receivables,
            "total":                total_assets,
        },
        "liabilities": {
            "paye_payable": paye_payable,
            "uif_payable":  uif_payable,
            "sdl_payable":  sdl_payable,
            "total":        total_liabilities,
        },
        "equity": {
            "retained_income": equity,
            "total":           equity,
        },
        "total_liabilities_and_equity": round(total_liabilities + equity, 2),
    }


@reports_router.get("/cash-flow")
async def cash_flow(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    cid = current_user.company_id
    now = datetime.utcnow()
    month_start = datetime(now.year, now.month, 1)

    # Operating inflows: cash collected from customers this month
    paid_this_month = db.query(Invoice).filter(
        Invoice.company_id == cid,
        Invoice.status == InvoiceStatus.paid,
        Invoice.paid_date >= month_start
    ).all()
    cash_receipts = round(sum(i.total_amount for i in paid_this_month), 2)

    # Operating outflows: expenses this month
    expenses_this_month = db.query(Expense).filter(
        Expense.company_id == cid,
        Expense.expense_date >= month_start
    ).all()
    cash_payments = round(sum(e.amount for e in expenses_this_month), 2)

    # Payroll outflows: net pay disbursed this month
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
    due_date = datetime(now.year, now.month + 1 if now.month < 12 else 1,
                        7, tzinfo=None).strftime("%d %B %Y") if now.month < 12 else \
               datetime(now.year + 1, 1, 7).strftime("%d %B %Y")

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
            "gros