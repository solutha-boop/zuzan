from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from pydantic import BaseModel
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
import secrets
from typing import Optional
from database import get_db, User, Company, Payment, PlanType, BillingCycle, SubscriptionStatus

SECRET_KEY = "zuzan-secret-key-2025"
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()
router = APIRouter()

PLAN_PRICES = {
    "starter":      {"monthly": 299,  "annual": 2990},
    "professional": {"monthly": 699,  "annual": 6990},
    "business":     {"monthly": 1299, "annual": 12990},
}


class RegisterRequest(BaseModel):
    company_name:    str
    reg_number:      Optional[str] = None
    industry:        Optional[str] = None
    first_name:      str
    last_name:       str
    email:           str
    phone:           Optional[str] = None
    password:        str
    plan:            str = "starter"
    billing_cycle:   str = "monthly"
    payroll_enabled: bool = False
    employee_count:  int = 0


class LoginRequest(BaseModel):
    email:    str
    password: str


def make_safe_password(password: str) -> str:
    """Truncate password to 50 chars to stay within bcrypt 72-byte limit."""
    if not password:
        return "Zuzan2025"
    return password[:50]


def hash_password(password: str) -> str:
    return pwd_context.hash(make_safe_password(password))


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(make_safe_password(plain), hashed)


def create_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    try:
        payload = jwt.decode(
            credentials.credentials,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@router.post("/register")
async def register(data: RegisterRequest, db: Session = Depends(get_db)):
    # Check email not already registered
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Create company
    company = Company(
        name=data.company_name,
        reg_number=data.reg_number,
        industry=data.industry,
        plan=PlanType(data.plan),
        billing_cycle=BillingCycle(data.billing_cycle),
        subscription_status=SubscriptionStatus.trial,
        trial_ends=datetime.utcnow() + timedelta(days=14),
        payroll_enabled=data.payroll_enabled,
        payroll_employees=data.employee_count,
    )
    db.add(company)
    db.flush()

    # Create user
    user = User(
        company_id=company.id,
        first_name=data.first_name,
        last_name=data.last_name,
        email=data.email,
        phone=data.phone,
        hashed_password=hash_password(data.password),
        role="owner",
    )
    db.add(user)
    db.flush()

    # Create payment record
    plan_price = PLAN_PRICES.get(data.plan, {}).get(data.billing_cycle, 299)
    payroll_cost = max(99, data.employee_count * 17.50) if data.payroll_enabled else 0
    payment = Payment(
        company_id=company.id,
        amount=plan_price + payroll_cost,
        plan=data.plan,
        billing_cycle=data.billing_cycle,
        status="trial",
    )
    db.add(payment)
    db.commit()

    token = create_token({"user_id": user.id, "company_id": company.id})

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id":         user.id,
            "first_name": user.first_name,
            "last_name":  user.last_name,
            "email":      user.email,
            "role":       user.role,
        },
        "company": {
            "id":                  company.id,
            "name":                company.name,
            "plan":                str(company.plan.value),
            "subscription_status": str(company.subscription_status.value),
            "trial_ends":          company.trial_ends.isoformat(),
            "payroll_enabled":     company.payroll_enabled,
        },
    }


@router.post("/login")
async def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    company = db.query(Company).filter(Company.id == user.company_id).first()
    token = create_token({"user_id": user.id, "company_id": company.id})

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id":         user.id,
            "first_name": user.first_name,
            "last_name":  user.last_name,
            "email":      user.email,
            "role":       user.role,
        },
        "company": {
            "id":                  company.id,
            "name":                company.name,
            "plan":                str(company.plan.value),
            "subscription_status": str(company.subscription_status.value),
            "trial_ends":          company.trial_ends.isoformat() if company.trial_ends else None,
            "payroll_enabled":     company.payroll_enabled,
        },
    }


@router.get("/me")
async def get_me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    return {
        "user": {
            "id":         current_user.id,
            "first_name": current_user.first_name,
            "last_name":  current_user.last_name,
            "email":      current_user.email,
            "role":       current_user.role,
        },
        "company": {
            "id":                  company.id,
            "name":                company.name,
            "plan":                str(company.plan.value),
            "subscription_status": str(company.subscription_status.value),
            "payroll_enabled":     company.payroll_enabled,
            "payroll_employees":   company.payroll_employees,
        },
    }

# In-memory reset tokens {token: {email, expires}}
_reset_tokens: dict = {}


class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token:        str
    new_password: str


@router.post("/forgot-password")
async def forgot_password(data: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email.lower().strip()).first()
    if not user:
        # Don't reveal whether email exists
        return {"message": "If that email is registered, a reset code has been generated.", "reset_code": None}

    token = secrets.token_hex(4).upper()  # 8-char code e.g. A3F9B21C
    _reset_tokens[token] = {
        "email":   data.email.lower().strip(),
        "expires": datetime.utcnow() + timedelta(minutes=30),
    }

    return {
        "message":    "Reset code generated. In production this will be emailed. For now use the code below.",
        "reset_code": token,
        "expires_in": "30 minutes",
    }


@router.post("/reset-password")
async def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    entry = _reset_tokens.get(data.token.upper().strip())
    if not entry:
        raise HTTPException(status_code=400, detail="Invalid reset code.")
    if datetime.utcnow() > entry["expires"]:
        del _reset_tokens[data.token.upper().strip()]
        raise HTTPException(status_code=400, detail="Reset code has expired. Please request a new one.")
    if len(data.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")

    user = db.query(User).filter(User.email == entry["email"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    user.hashed_password = pwd_context.hash(data.new_password)
    db.commit()
    del _reset_tokens[data.token.upper().strip()]

    return {"message": "Password updated successfully. You can now sign in."}
