"""
Employer Benefit Schemes
========================
Company-level scheme templates + per-employee enrollment.

Endpoints (prefix /benefits)
-----------------------------
POST   /benefits/schemes              — create scheme
GET    /benefits/schemes              — list all schemes for the company
PUT    /benefits/schemes/{id}         — update scheme
DELETE /benefits/schemes/{id}         — deactivate scheme

POST   /benefits/enroll               — enroll employee in a scheme
GET    /benefits/employee/{emp_id}    — list employee's active enrollments
DELETE /benefits/enrollment/{id}      — unenroll employee from a scheme
GET    /benefits/summary              — total employer cost across all active employees
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from database import get_db, BenefitScheme, EmployeeBenefit, Employee
from auth import require_role

router = APIRouter()

BENEFIT_TYPES = {"pension", "medical", "group_life", "other"}
BENEFIT_LABELS = {
    "pension":    "Pension / Provident Fund",
    "medical":    "Medical Aid",
    "group_life": "Group Life / Risk Cover",
    "other":      "Other",
}
BENEFIT_ICONS = {
    "pension":    "🏦",
    "medical":    "🏥",
    "group_life": "🛡️",
    "other":      "⚙️",
}


# ── Pydantic models ──────────────────────────────────────────────────────────

class SchemeCreate(BaseModel):
    name: str
    benefit_type: str
    description: Optional[str] = None
    employer_pct: float = 0.0   # percentage of gross, e.g. 5.0 = 5%
    employee_pct: float = 0.0

class SchemeUpdate(BaseModel):
    name: Optional[str] = None
    benefit_type: Optional[str] = None
    description: Optional[str] = None
    employer_pct: Optional[float] = None
    employee_pct: Optional[float] = None
    is_active: Optional[bool] = None

class EnrollRequest(BaseModel):
    employee_id: int
    scheme_id: int
    employer_pct_override: Optional[float] = None  # None = use scheme default
    employee_pct_override: Optional[float] = None


def _scheme_dict(s: BenefitScheme) -> dict:
    return {
        "id":           s.id,
        "name":         s.name,
        "benefit_type": s.benefit_type,
        "label":        BENEFIT_LABELS.get(s.benefit_type, s.benefit_type),
        "icon":         BENEFIT_ICONS.get(s.benefit_type, "⚙️"),
        "description":  s.description,
        "employer_pct": s.employer_pct,
        "employee_pct": s.employee_pct,
        "is_active":    s.is_active,
        "created_at":   s.created_at.isoformat() if s.created_at else None,
        "enrollment_count": len([e for e in (s.enrollments or []) if e.is_active]),
    }

def _enrollment_dict(e: EmployeeBenefit) -> dict:
    emp = e.employee
    sch = e.scheme
    eff_emp_pct = e.employer_pct_override if e.employer_pct_override is not None else sch.employer_pct
    eff_ee_pct  = e.employee_pct_override  if e.employee_pct_override  is not None else sch.employee_pct
    gross = emp.gross_salary or 0.0
    return {
        "id":                   e.id,
        "employee_id":          e.employee_id,
        "employee_name":        f"{emp.first_name} {emp.last_name}",
        "employee_number":      emp.employee_number,
        "gross_salary":         gross,
        "scheme_id":            e.scheme_id,
        "scheme_name":          sch.name,
        "benefit_type":         sch.benefit_type,
        "icon":                 BENEFIT_ICONS.get(sch.benefit_type, "⚙️"),
        "employer_pct":         eff_emp_pct,
        "employee_pct":         eff_ee_pct,
        "employer_pct_override": e.employer_pct_override,
        "employee_pct_override": e.employee_pct_override,
        "employer_monthly":     round(gross * eff_emp_pct / 100, 2),
        "employee_monthly":     round(gross * eff_ee_pct  / 100, 2),
        "is_active":            e.is_active,
        "enrolled_at":          e.enrolled_at.isoformat() if e.enrolled_at else None,
    }


# ── Scheme endpoints ─────────────────────────────────────────────────────────

@router.post("/schemes")
def create_scheme(
    body: SchemeCreate,
    current_user=Depends(require_role(["owner", "admin", "accountant"])),
    db: Session = Depends(get_db),
):
    if body.benefit_type not in BENEFIT_TYPES:
        raise HTTPException(400, f"benefit_type must be one of: {', '.join(BENEFIT_TYPES)}")
    if body.employer_pct < 0 or body.employer_pct > 100:
        raise HTTPException(400, "employer_pct must be between 0 and 100")
    if body.employee_pct < 0 or body.employee_pct > 100:
        raise HTTPException(400, "employee_pct must be between 0 and 100")

    scheme = BenefitScheme(
        company_id   = current_user.company_id,
        name         = body.name.strip(),
        benefit_type = body.benefit_type,
        description  = body.description,
        employer_pct = body.employer_pct,
        employee_pct = body.employee_pct,
    )
    db.add(scheme)
    db.commit()
    db.refresh(scheme)
    return _scheme_dict(scheme)


@router.get("/schemes")
def list_schemes(
    include_inactive: bool = False,
    current_user=Depends(require_role(["owner", "admin", "accountant", "viewer"])),
    db: Session = Depends(get_db),
):
    q = db.query(BenefitScheme).filter(BenefitScheme.company_id == current_user.company_id)
    if not include_inactive:
        q = q.filter(BenefitScheme.is_active == True)
    schemes = q.order_by(BenefitScheme.benefit_type, BenefitScheme.name).all()
    return [_scheme_dict(s) for s in schemes]


@router.put("/schemes/{scheme_id}")
def update_scheme(
    scheme_id: int,
    body: SchemeUpdate,
    current_user=Depends(require_role(["owner", "admin", "accountant"])),
    db: Session = Depends(get_db),
):
    scheme = db.query(BenefitScheme).filter(
        BenefitScheme.id == scheme_id,
        BenefitScheme.company_id == current_user.company_id,
    ).first()
    if not scheme:
        raise HTTPException(404, "Scheme not found")

    if body.name is not None:         scheme.name         = body.name.strip()
    if body.benefit_type is not None:
        if body.benefit_type not in BENEFIT_TYPES:
            raise HTTPException(400, f"benefit_type must be one of: {', '.join(BENEFIT_TYPES)}")
        scheme.benefit_type = body.benefit_type
    if body.description is not None:  scheme.description  = body.description
    if body.employer_pct is not None: scheme.employer_pct = body.employer_pct
    if body.employee_pct is not None: scheme.employee_pct = body.employee_pct
    if body.is_active is not None:    scheme.is_active    = body.is_active

    db.commit()
    db.refresh(scheme)
    return _scheme_dict(scheme)


@router.delete("/schemes/{scheme_id}")
def deactivate_scheme(
    scheme_id: int,
    current_user=Depends(require_role(["owner", "admin"])),
    db: Session = Depends(get_db),
):
    scheme = db.query(BenefitScheme).filter(
        BenefitScheme.id == scheme_id,
        BenefitScheme.company_id == current_user.company_id,
    ).first()
    if not scheme:
        raise HTTPException(404, "Scheme not found")
    scheme.is_active = False
    db.commit()
    return {"status": "deactivated"}


# ── Enrollment endpoints ──────────────────────────────────────────────────────

@router.post("/enroll")
def enroll_employee(
    body: EnrollRequest,
    current_user=Depends(require_role(["owner", "admin", "accountant"])),
    db: Session = Depends(get_db),
):
    # Validate employee belongs to this company
    emp = db.query(Employee).filter(
        Employee.id == body.employee_id,
        Employee.company_id == current_user.company_id,
    ).first()
    if not emp:
        raise HTTPException(404, "Employee not found")

    # Validate scheme belongs to this company
    scheme = db.query(BenefitScheme).filter(
        BenefitScheme.id == body.scheme_id,
        BenefitScheme.company_id == current_user.company_id,
        BenefitScheme.is_active == True,
    ).first()
    if not scheme:
        raise HTTPException(404, "Benefit scheme not found or inactive")

    # Check for existing enrollment
    existing = db.query(EmployeeBenefit).filter(
        EmployeeBenefit.employee_id == body.employee_id,
        EmployeeBenefit.scheme_id == body.scheme_id,
    ).first()

    if existing:
        # Re-activate if inactive, update overrides
        existing.is_active = True
        existing.employer_pct_override = body.employer_pct_override
        existing.employee_pct_override = body.employee_pct_override
        existing.enrolled_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return _enrollment_dict(existing)

    enrollment = EmployeeBenefit(
        employee_id           = body.employee_id,
        scheme_id             = body.scheme_id,
        employer_pct_override = body.employer_pct_override,
        employee_pct_override = body.employee_pct_override,
    )
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)
    return _enrollment_dict(enrollment)


@router.get("/employee/{employee_id}")
def get_employee_benefits(
    employee_id: int,
    current_user=Depends(require_role(["owner", "admin", "accountant", "viewer"])),
    db: Session = Depends(get_db),
):
    emp = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.company_id == current_user.company_id,
    ).first()
    if not emp:
        raise HTTPException(404, "Employee not found")

    enrollments = db.query(EmployeeBenefit).filter(
        EmployeeBenefit.employee_id == employee_id,
        EmployeeBenefit.is_active == True,
    ).all()
    return [_enrollment_dict(e) for e in enrollments]


@router.delete("/enrollment/{enrollment_id}")
def unenroll_employee(
    enrollment_id: int,
    current_user=Depends(require_role(["owner", "admin", "accountant"])),
    db: Session = Depends(get_db),
):
    enrollment = db.query(EmployeeBenefit).filter(
        EmployeeBenefit.id == enrollment_id,
    ).first()
    if not enrollment:
        raise HTTPException(404, "Enrollment not found")

    # Security check: make sure the employee belongs to this company
    emp = db.query(Employee).filter(
        Employee.id == enrollment.employee_id,
        Employee.company_id == current_user.company_id,
    ).first()
    if not emp:
        raise HTTPException(403, "Not authorised")

    enrollment.is_active = False
    db.commit()
    return {"status": "unenrolled"}


@router.get("/summary")
def benefits_summary(
    current_user=Depends(require_role(["owner", "admin", "accountant"])),
    db: Session = Depends(get_db),
):
    """
    Total monthly employer benefit cost and employee deductions
    across all active employees and active enrollments.
    """
    enrollments = (
        db.query(EmployeeBenefit)
        .join(Employee, EmployeeBenefit.employee_id == Employee.id)
        .join(BenefitScheme, EmployeeBenefit.scheme_id == BenefitScheme.id)
        .filter(
            Employee.company_id == current_user.company_id,
            Employee.is_active == True,
            EmployeeBenefit.is_active == True,
            BenefitScheme.is_active == True,
        )
        .all()
    )

    total_employer = 0.0
    total_employee = 0.0
    by_type: dict = {}

    for e in enrollments:
        gross = e.employee.gross_salary or 0.0
        emp_pct = e.employer_pct_override if e.employer_pct_override is not None else e.scheme.employer_pct
        ee_pct  = e.employee_pct_override  if e.employee_pct_override  is not None else e.scheme.employee_pct
        emp_cost = round(gross * emp_pct / 100, 2)
        ee_ded   = round(gross * ee_pct  / 100, 2)
        total_employer += emp_cost
        total_employee += ee_ded
        t = e.scheme.benefit_type
        if t not in by_type:
            by_type[t] = {"label": BENEFIT_LABELS.get(t, t), "icon": BENEFIT_ICONS.get(t, "⚙️"),
                          "employer_cost": 0.0, "employee_deductions": 0.0}
        by_type[t]["employer_cost"]       += emp_cost
        by_type[t]["employee_deductions"] += ee_ded

    return {
        "total_employer_monthly": round(total_employer, 2),
        "total_employee_monthly": round(total_employee, 2),
        "by_type": list(by_type.values()),
        "enrollment_count": len(enrollments),
    }
