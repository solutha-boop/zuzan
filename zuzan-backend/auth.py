from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Request
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from pydantic import BaseModel
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
import secrets
from typing import Optional
from database import get_db, User, Company, Payment, PlanType, BillingCycle, SubscriptionStatus
from email_service import send_verification_email, send_welcome_email, send_password_reset_email, send_admin_signup_notification
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

import os
try:
    from config import PLAN_PRICES
except ImportError:
    PLAN_PRICES = {
        "starter":      {"monthly": 399,  "annual": 3990},
        "professional": {"monthly": 899,  "annual": 8990},
        "business":     {"monthly": 1499, "annual": 14990},
    }

SECRET_KEY = os.environ.get("SECRET_KEY", "zuzan-dev-key-change-in-production")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()
router = APIRouter()


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
@limiter.limit("5/minute")
async def register(request: Request, data: RegisterRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
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
    verify_token = secrets.token_urlsafe(32)
    user = User(
        company_id=company.id,
        first_name=data.first_name,
        last_name=data.last_name,
        email=data.email,
        phone=data.phone,
        hashed_password=hash_password(data.password),
        role="owner",
        email_verified=False,
        email_verify_token=verify_token,
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

    # Send verification email only — welcome email fires after they click the link
    background_tasks.add_task(
        send_verification_email, data.first_name, data.email, verify_token
    )
    admin_email = os.environ.get("ADMIN_EMAIL", "")
    if admin_email:
        background_tasks.add_task(
            send_admin_signup_notification,
            admin_email, data.first_name, data.last_name,
            data.email, data.company_name, data.plan, data.billing_cycle,
        )

    # Initialise chart of accounts for the new company
    try:
        import journal as journal_engine
        journal_engine.init_accounts(company.id, db)
    except Exception:
        pass  # Non-fatal — accounts created on first transaction if missed here

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
            "logo_url":            company.logo_url,
            "plan":                str(company.plan.value),
            "subscription_status": str(company.subscription_status.value),
            "trial_ends":          company.trial_ends.isoformat(),
            "payroll_enabled":     company.payroll_enabled,
        },
    }


@router.post("/login")
@limiter.limit("10/minute")
async def login(request: Request, data: LoginRequest, db: Session = Depends(get_db)):
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
            "logo_url":            company.logo_url,
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
            "logo_url":            company.logo_url,
            "plan":                str(company.plan.value),
            "subscription_status": str(company.subscription_status.value),
            "payroll_enabled":     company.payroll_enabled,
            "payroll_employees":   company.payroll_employees,
        },
    }

@router.get("/verify-email/{token}", response_class=HTMLResponse)
async def verify_email(token: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    from email_service import FRONTEND_URL
    user = db.query(User).filter(User.email_verify_token == token).first()
    if not user:
        html = f"""<html><body style="font-family:Arial;text-align:center;padding:60px;background:#FAF7F2;">
          <h1 style="color:#C8401A;">ZuZan</h1>
          <h2 style="color:#c00;">⚠️ Invalid or expired link</h2>
          <p>This verification link is invalid or has already been used.</p>
          <a href="{FRONTEND_URL}" style="color:#C8401A;">Return to ZuZan</a>
        </body></html>"""
        return HTMLResponse(content=html, status_code=400)

    user.email_verified = True
    user.email_verify_token = None
    db.commit()

    # Send welcome email now that the address is confirmed
    company = db.query(Company).filter(Company.id == user.company_id).first()
    if company:
        trial_ends_fmt = company.trial_ends.strftime("%-d %B %Y") if company.trial_ends else "14 days"
        background_tasks.add_task(
            send_welcome_email,
            user.first_name, user.email, company.name,
            str(company.plan.value), str(company.billing_cycle.value), trial_ends_fmt,
        )

    html = f"""<html><body style="font-family:Arial;text-align:center;padding:60px;background:#FAF7F2;">
      <div style="max-width:480px;margin:0 auto;">
        <h1 style="color:#C8401A;font-size:36px;">ZuZan</h1>
        <div style="font-size:64px;margin:20px 0;">✅</div>
        <h2 style="color:#1a1a1a;">Email Verified!</h2>
        <p style="color:#555;line-height:1.7;">
          Your email address has been confirmed, {user.first_name}.<br>
          Check your inbox — your welcome email is on its way.
        </p>
        <a href="{FRONTEND_URL}" style="display:inline-block;margin-top:24px;background:#C8401A;color:#fff;
           padding:14px 36px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:15px;">
          Open ZuZan
        </a>
      </div>
    </body></html>"""
    return HTMLResponse(content=html)


class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token:        str
    new_password: str


@router.post("/forgot-password")
@limiter.limit("3/minute")
async def forgot_password(request: Request, data: ForgotPasswordRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email.lower().strip()).first()
    if not user:
        return {"message": "If that email is registered, a reset code has been sent."}

    token = secrets.token_hex(4).upper()  # 8-char code e.g. A3F9B21C
    user.reset_token = token
    user.reset_token_expires = datetime.utcnow() + timedelta(minutes=30)
    db.commit()

    background_tasks.add_task(
        send_password_reset_email, user.first_name, user.email, token
    )

    return {
        "message":  "A reset code has been sent to your email address.",
        "expires_in": "30 minutes",
    }


@router.post("/reset-password")
async def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    token = data.token.upper().strip()
    user = db.query(User).filter(User.reset_token == token).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid reset code.")
    if datetime.utcnow() > user.reset_token_expires:
        user.reset_token = None; user.reset_token_expires = None; db.commit()
        raise HTTPException(status_code=400, detail="Reset code has expired. Please request a new one.")
    if len(data.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")

    user.hashed_password = hash_password(data.new_password)
    user.reset_token = None
    user.reset_token_expires = None
    db.commit()

    return {"message": "Password updated successfully. You can now sign in."}
