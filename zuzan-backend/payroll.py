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


# ── PAYFAST PAYMENT GATEWAY ───────────────────────────────────────────────────
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
        payment.status    = "completed"
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
    company    = db.query(Company).filter(Company.id == current_user.company_id).first()
    plan_str   = str(company.plan).split(".")[-1]
    billing_str = str(company.billing_cycle).split(".")[-1]
    plan_price = PLAN_PRICES.get(plan_str, {}).get(billing_str, 299)
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
