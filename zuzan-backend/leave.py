"""
ZuZan Leave Management
BCEA-compliant leave tracking: submission, approval, balance maintenance, monthly accrual.
Auto-approves pending requests after 48 hours if no manager action.
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta, date as date_type

from database import get_db, Employee, LeaveRequest, LeaveBalance
from auth import get_current_user, User
import logging

logger = logging.getLogger("zuzan.leave")
router = APIRouter()

# ── BCEA constants ────────────────────────────────────────────────────────────
ANNUAL_ACCRUAL_PER_MONTH = 1.25   # 15 working days / 12 months
ANNUAL_MAX_CARRY         = 30.0   # cap on accumulated annual balance
AUTO_APPROVE_HOURS       = 48     # auto-approve after 2 days of no manager action
LEAVE_TYPES              = {"annual", "sick", "family", "maternity", "unpaid"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def count_working_days(start: date_type, end: date_type) -> float:
    """Count Monday–Friday days between start and end (inclusive)."""
    if end < start:
        return 0.0
    days, current = 0, start
    while current <= end:
        if current.weekday() < 5:   # 0=Mon … 4=Fri
            days += 1
        current += timedelta(days=1)
    return float(days)


def get_or_create_balance(employee_id: int, company_id: int, db: Session) -> LeaveBalance:
    bal = db.query(LeaveBalance).filter(LeaveBalance.employee_id == employee_id).first()
    if not bal:
        bal = LeaveBalance(company_id=company_id, employee_id=employee_id)
        db.add(bal)
        db.flush()
    return bal


def _deduct(bal: LeaveBalance, leave_type: str, days: float):
    if leave_type == "annual":
        bal.annual_balance   = max(0.0, bal.annual_balance - days)
        bal.annual_taken_ytd += days
    elif leave_type == "sick":
        bal.sick_balance   = max(0.0, bal.sick_balance - days)
        bal.sick_taken_ytd += days
    elif leave_type == "family":
        bal.family_balance   = max(0.0, bal.family_balance - days)
        bal.family_taken_ytd += days
    # maternity and unpaid: no balance deduction


def _restore(bal: LeaveBalance, leave_type: str, days: float):
    if leave_type == "annual":
        bal.annual_balance   += days
        bal.annual_taken_ytd  = max(0.0, bal.annual_taken_ytd - days)
    elif leave_type == "sick":
        bal.sick_balance   += days
        bal.sick_taken_ytd  = max(0.0, bal.sick_taken_ytd - days)
    elif leave_type == "family":
        bal.family_balance   += days
        bal.family_taken_ytd  = max(0.0, bal.family_taken_ytd - days)


def _auto_approve_stale(db: Session, company_id: int):
    """Auto-approve any pending requests that have been waiting > 48 hours."""
    cutoff = datetime.utcnow() - timedelta(hours=AUTO_APPROVE_HOURS)
    stale = db.query(LeaveRequest).filter(
        LeaveRequest.company_id == company_id,
        LeaveRequest.status     == "pending",
        LeaveRequest.submitted_at <= cutoff,
    ).all()
    for req in stale:
        req.status       = "approved"
        req.auto_approved = True
        req.reviewed_at  = datetime.utcnow()
        req.reviewed_by  = "auto (48h)"
        bal = get_or_create_balance(req.employee_id, req.company_id, db)
        _deduct(bal, req.leave_type, req.days_requested)
    if stale:
        db.commit()
        logger.info(f"Auto-approved {len(stale)} leave request(s) for company {company_id}")


def _to_dict(r: LeaveRequest, emp_name: str) -> dict:
    return {
        "id":             r.id,
        "employee_id":    r.employee_id,
        "employee_name":  emp_name,
        "leave_type":     r.leave_type,
        "start_date":     r.start_date.strftime("%Y-%m-%d"),
        "end_date":       r.end_date.strftime("%Y-%m-%d"),
        "days_requested": r.days_requested,
        "status":         r.status,
        "reason":         r.reason,
        "submitted_at":   r.submitted_at.isoformat(),
        "reviewed_at":    r.reviewed_at.isoformat() if r.reviewed_at else None,
        "reviewed_by":    r.reviewed_by,
        "auto_approved":  r.auto_approved,
    }


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class LeaveRequestCreate(BaseModel):
    employee_id: int
    leave_type:  str           # annual / sick / family / maternity / unpaid
    start_date:  str           # YYYY-MM-DD
    end_date:    str           # YYYY-MM-DD
    reason:      Optional[str] = None

class LeaveRequestReview(BaseModel):
    status: str                # approved / rejected / cancelled


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/requests")
async def list_requests(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return all leave requests for the company (triggers auto-approve check first)."""
    cid = current_user.company_id
    _auto_approve_stale(db, cid)
    reqs = (
        db.query(LeaveRequest)
        .filter(LeaveRequest.company_id == cid)
        .order_by(LeaveRequest.submitted_at.desc())
        .all()
    )
    emp_names = {
        e.id: f"{e.first_name} {e.last_name}"
        for e in db.query(Employee).filter(Employee.company_id == cid).all()
    }
    return [_to_dict(r, emp_names.get(r.employee_id, "Unknown")) for r in reqs]


@router.post("/requests")
async def submit_request(
    data: LeaveRequestCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit a leave request on behalf of (or as) an employee."""
    cid = current_user.company_id
    emp = db.query(Employee).filter(
        Employee.id == data.employee_id,
        Employee.company_id == cid,
    ).first()
    if not emp:
        raise HTTPException(404, "Employee not found")
    if data.leave_type not in LEAVE_TYPES:
        raise HTTPException(400, f"Invalid leave type. Valid: {', '.join(sorted(LEAVE_TYPES))}")

    start = datetime.strptime(data.start_date, "%Y-%m-%d").date()
    end   = datetime.strptime(data.end_date,   "%Y-%m-%d").date()
    days  = count_working_days(start, end)
    if days <= 0:
        raise HTTPException(400, "No working days in the selected date range")

    # Balance check for leave types that draw from a pool
    if data.leave_type in ("annual", "sick", "family"):
        bal = get_or_create_balance(data.employee_id, cid, db)
        available = {
            "annual": bal.annual_balance,
            "sick":   bal.sick_balance,
            "family": bal.family_balance,
        }[data.leave_type]
        if days > available:
            raise HTTPException(
                400,
                f"Insufficient {data.leave_type} leave. "
                f"Available: {available:.1f} days, Requested: {days:.0f} days.",
            )

    req = LeaveRequest(
        company_id    = cid,
        employee_id   = data.employee_id,
        leave_type    = data.leave_type,
        start_date    = datetime.strptime(data.start_date, "%Y-%m-%d"),
        end_date      = datetime.strptime(data.end_date,   "%Y-%m-%d"),
        days_requested = days,
        reason        = data.reason,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return {
        "id":             req.id,
        "days_requested": req.days_requested,
        "status":         req.status,
        "message":        f"{days:.0f} working day(s) submitted. Pending manager approval (auto-approved after 48h).",
    }


@router.put("/requests/{req_id}")
async def review_request(
    req_id: int,
    data:   LeaveRequestReview,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Approve, reject, or cancel a leave request."""
    req = db.query(LeaveRequest).filter(
        LeaveRequest.id         == req_id,
        LeaveRequest.company_id == current_user.company_id,
    ).first()
    if not req:
        raise HTTPException(404, "Leave request not found")
    if req.status != "pending":
        raise HTTPException(400, f"Request is already '{req.status}' and cannot be changed")
    if data.status not in ("approved", "rejected", "cancelled"):
        raise HTTPException(400, "status must be 'approved', 'rejected', or 'cancelled'")

    req.status      = data.status
    req.reviewed_at = datetime.utcnow()
    req.reviewed_by = f"{current_user.first_name} {current_user.last_name}"

    if data.status == "approved":
        bal = get_or_create_balance(req.employee_id, req.company_id, db)
        _deduct(bal, req.leave_type, req.days_requested)

    db.commit()
    return {"id": req.id, "status": req.status}


@router.get("/balances")
async def list_balances(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return leave balances for all active employees, creating default records as needed."""
    cid = current_user.company_id
    employees = (
        db.query(Employee)
        .filter(Employee.company_id == cid, Employee.is_active == True)
        .all()
    )
    result = []
    for emp in employees:
        bal = get_or_create_balance(emp.id, cid, db)
        result.append({
            "employee_id":       emp.id,
            "employee_name":     f"{emp.first_name} {emp.last_name}",
            "position":          emp.position or "",
            "annual_balance":    round(bal.annual_balance, 2),
            "annual_accrued_ytd": round(bal.annual_accrued_ytd, 2),
            "annual_taken_ytd":  round(bal.annual_taken_ytd, 2),
            "sick_balance":      round(bal.sick_balance, 2),
            "sick_taken_ytd":    round(bal.sick_taken_ytd, 2),
            "family_balance":    round(bal.family_balance, 2),
            "family_taken_ytd":  round(bal.family_taken_ytd, 2),
            "last_accrual_date": bal.last_accrual_date.strftime("%Y-%m-%d") if bal.last_accrual_date else None,
        })
    db.commit()   # persist any newly created balance rows
    return result


@router.post("/accrue")
async def run_accrual(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Manually trigger monthly leave accrual (annual leave +1.25 days per employee)."""
    n = _run_accrual_internal(current_user.company_id, db)
    return {
        "accrued_for":  n,
        "days_added":   ANNUAL_ACCRUAL_PER_MONTH,
        "message":      f"Annual leave accrued for {n} employee(s) (+{ANNUAL_ACCRUAL_PER_MONTH} days each).",
    }


# ── Internal helper called by payroll engine ──────────────────────────────────

def _run_accrual_internal(company_id: int, db: Session) -> int:
    """
    Add ANNUAL_ACCRUAL_PER_MONTH days of annual leave to every active employee.
    Idempotent within the same calendar month — will not double-accrue.
    Returns the number of employees accrued for.
    """
    now = datetime.utcnow()
    employees = (
        db.query(Employee)
        .filter(Employee.company_id == company_id, Employee.is_active == True)
        .all()
    )
    accrued = 0
    for emp in employees:
        bal = get_or_create_balance(emp.id, company_id, db)
        # Skip if already accrued this calendar month
        if (
            bal.last_accrual_date
            and bal.last_accrual_date.month == now.month
            and bal.last_accrual_date.year  == now.year
        ):
            continue
        bal.annual_balance     = min(ANNUAL_MAX_CARRY, bal.annual_balance + ANNUAL_ACCRUAL_PER_MONTH)
        bal.annual_accrued_ytd += ANNUAL_ACCRUAL_PER_MONTH
        bal.last_accrual_date  = now
        accrued += 1
    db.commit()
    return accrued
