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
from email_service import send_verification_email, send_welcome_email, send_password_reset_email, send_admin_signup_notification, send_invite_email
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

import os
try:
    from config import PLAN_PRICES, PAYROLL_PER_EMP
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
    payroll_cost = max(99, data.employee_count * PAYROLL_PER_EMP) if data.payroll_enabled else 0
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
            "afs_enabled":         company.afs_enabled,
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
            "afs_enabled":         company.afs_enabled,
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
            "afs_enabled":         company.afs_enabled,
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


# ─────────────────────────────────────────────────────────────────────────────
# Role-based access control
# ─────────────────────────────────────────────────────────────────────────────

ROLE_HIERARCHY = ["owner", "admin", "accountant", "employee"]

def require_role(*allowed_roles):
    """
    Dependency factory.  Usage:
        Depends(require_role("owner", "admin"))
    Returns the current user if their role is in allowed_roles, else 403.
    """
    def _check(current_user: User = Depends(get_current_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. Requires one of: {', '.join(allowed_roles)}"
            )
        return current_user
    return _check


def log_action(db, company_id: int, user, action: str, target_type: str = None, target_id: int = None, detail: str = None):
    """Write a row to audit_log. Non-fatal — never raises."""
    try:
        from database import AuditLog
        entry = AuditLog(
            company_id=company_id,
            user_id=user.id if user else None,
            user_email=user.email if user else None,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=detail,
        )
        db.add(entry)
        db.commit()
    except Exception:
        db.rollback()


# ─────────────────────────────────────────────────────────────────────────────
# Team management request models
# ─────────────────────────────────────────────────────────────────────────────

class InviteRequest(BaseModel):
    email: str
    role:  str = "accountant"   # admin | accountant | employee

class UpdateRoleRequest(BaseModel):
    role: str


# ─────────────────────────────────────────────────────────────────────────────
# Team endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/team")
async def list_team(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all users in the current company."""
    members = db.query(User).filter(
        User.company_id == current_user.company_id,
        User.is_active == True,
    ).all()
    return [
        {
            "id":         m.id,
            "first_name": m.first_name,
            "last_name":  m.last_name,
            "email":      m.email,
            "role":       m.role,
            "created_at": m.created_at.isoformat() if m.created_at else None,
            "is_self":    m.id == current_user.id,
        }
        for m in members
    ]


@router.get("/team/invites")
async def list_invites(
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db),
):
    """List pending (unused, unexpired) invitations."""
    from database import InviteToken
    now = datetime.utcnow()
    invites = db.query(InviteToken).filter(
        InviteToken.company_id == current_user.company_id,
        InviteToken.used_at == None,
        InviteToken.expires_at > now,
    ).all()
    return [
        {
            "id":         inv.id,
            "email":      inv.email,
            "role":       inv.role,
            "expires_at": inv.expires_at.isoformat(),
            "created_at": inv.created_at.isoformat() if inv.created_at else None,
        }
        for inv in invites
    ]


@router.post("/team/invite")
async def invite_member(
    data: InviteRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db),
):
    """Send an email invitation to join the company."""
    from database import InviteToken, Company
    import secrets as _secrets

    # Validate role
    valid_roles = ["admin", "accountant", "payroll", "employee"]
    if data.role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Role must be one of: {', '.join(valid_roles)}")

    email = data.email.lower().strip()

    # Check if email already in this company
    existing = db.query(User).filter(
        User.email == email,
        User.company_id == current_user.company_id,
        User.is_active == True,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="This email is already a member of your company.")

    # Invalidate any prior pending invite for same email+company
    prior = db.query(InviteToken).filter(
        InviteToken.company_id == current_user.company_id,
        InviteToken.email == email,
        InviteToken.used_at == None,
    ).all()
    for p in prior:
        db.delete(p)
    db.flush()

    token_str = _secrets.token_urlsafe(32)
    invite = InviteToken(
        company_id=current_user.company_id,
        email=email,
        role=data.role,
        token=token_str,
        invited_by=current_user.id,
        expires_at=datetime.utcnow() + timedelta(hours=48),
    )
    db.add(invite)
    db.commit()

    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    inviter_name = f"{current_user.first_name} {current_user.last_name}"
    background_tasks.add_task(
        send_invite_email,
        email, company.name, inviter_name, data.role, token_str
    )

    log_action(db, current_user.company_id, current_user, "team.invite_sent",
               detail=f"Invited {email} as {data.role}")

    return {"message": f"Invitation sent to {email}", "role": data.role}


@router.get("/invite/{token}")
async def get_invite_info(token: str, db: Session = Depends(get_db)):
    """Public endpoint — return invite metadata so the accept page can show company + role."""
    from database import InviteToken, Company
    now = datetime.utcnow()
    invite = db.query(InviteToken).filter(InviteToken.token == token).first()
    if not invite:
        raise HTTPException(status_code=404, detail="Invite link not found.")
    if invite.used_at:
        raise HTTPException(status_code=400, detail="This invite has already been used.")
    if invite.expires_at < now:
        raise HTTPException(status_code=400, detail="This invite link has expired.")
    company = db.query(Company).filter(Company.id == invite.company_id).first()
    return {
        "email":        invite.email,
        "role":         invite.role,
        "company_name": company.name if company else "Unknown",
        "expires_at":   invite.expires_at.isoformat(),
    }


class AcceptInviteRequest(BaseModel):
    token:      str
    first_name: str
    last_name:  str
    password:   str


@router.post("/accept-invite")
async def accept_invite(
    data: AcceptInviteRequest,
    db: Session = Depends(get_db),
):
    """Accept an invitation — create a new user account linked to the inviting company."""
    from database import InviteToken, Company
    now = datetime.utcnow()
    invite = db.query(InviteToken).filter(InviteToken.token == data.token).first()
    if not invite:
        raise HTTPException(status_code=404, detail="Invite link not found.")
    if invite.used_at:
        raise HTTPException(status_code=400, detail="This invite has already been used.")
    if invite.expires_at < now:
        raise HTTPException(status_code=400, detail="This invite link has expired.")

    # Check if email already has an account
    existing = db.query(User).filter(User.email == invite.email).first()
    if existing:
        # If they already belong to this company, just mark the invite used
        if existing.company_id == invite.company_id:
            invite.used_at = now
            db.commit()
            raise HTTPException(status_code=400, detail="You already have an account in this company.")
        raise HTTPException(
            status_code=400,
            detail="An account with this email already exists. "
                   "Contact support to move your account to this company."
        )

    if len(data.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")

    # Create user
    user = User(
        company_id=invite.company_id,
        first_name=data.first_name.strip(),
        last_name=data.last_name.strip(),
        email=invite.email,
        hashed_password=hash_password(data.password),
        role=invite.role,
        is_active=True,
        email_verified=True,   # verified implicitly — they clicked the invite link
    )
    db.add(user)
    invite.used_at = now
    db.flush()

    company = db.query(Company).filter(Company.id == invite.company_id).first()
    db.commit()

    log_action(db, invite.company_id, user, "team.invite_accepted",
               detail=f"{invite.email} joined as {invite.role}")

    token_str = create_token({"user_id": user.id, "company_id": invite.company_id})
    return {
        "access_token": token_str,
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
            "afs_enabled":         company.afs_enabled,
        },
    }


@router.patch("/team/{user_id}")
async def update_team_member(
    user_id: int,
    data: UpdateRoleRequest,
    current_user: User = Depends(require_role("owner")),
    db: Session = Depends(get_db),
):
    """Change a team member's role (owner only)."""
    valid_roles = ["admin", "accountant", "payroll", "employee"]
    if data.role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Role must be one of: {', '.join(valid_roles)}")

    member = db.query(User).filter(
        User.id == user_id,
        User.company_id == current_user.company_id,
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Team member not found.")
    if member.role == "owner":
        raise HTTPException(status_code=400, detail="Cannot change the owner's role.")
    if member.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot change your own role.")

    old_role = member.role
    member.role = data.role
    db.commit()

    log_action(db, current_user.company_id, current_user, "team.role_changed",
               target_type="user", target_id=user_id,
               detail=f"{member.email}: {old_role} → {data.role}")

    return {"message": f"Role updated to {data.role}", "user_id": user_id}


@router.delete("/team/{user_id}")
async def remove_team_member(
    user_id: int,
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db),
):
    """Remove a team member (deactivate their account). Owner cannot be removed."""
    member = db.query(User).filter(
        User.id == user_id,
        User.company_id == current_user.company_id,
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Team member not found.")
    if member.role == "owner":
        raise HTTPException(status_code=400, detail="Cannot remove the company owner.")
    if member.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot remove yourself.")

    member.is_active = False
    db.commit()

    log_action(db, current_user.company_id, current_user, "team.member_removed",
               target_type="user", target_id=user_id,
               detail=f"Removed {member.email} ({member.role})")

    return {"message": f"Member {member.email} removed."}


@router.delete("/team/invites/{invite_id}")
async def cancel_invite(
    invite_id: int,
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db),
):
    """Cancel a pending invitation."""
    from database import InviteToken
    invite = db.query(InviteToken).filter(
        InviteToken.id == invite_id,
        InviteToken.company_id == current_user.company_id,
    ).first()
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found.")
    db.delete(invite)
    db.commit()
    return {"message": "Invitation cancelled."}


@router.get("/audit-log")
async def get_audit_log(
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
):
    """Return recent audit log entries for this company."""
    from database import AuditLog
    entries = db.query(AuditLog).filter(
        AuditLog.company_id == current_user.company_id,
    ).order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()
    return [
        {
            "id":          e.id,
            "user_email":  e.user_email,
            "action":      e.action,
            "target_type": e.target_type,
            "target_id":   e.target_id,
            "detail":      e.detail,
            "created_at":  e.created_at.isoformat() if e.created_at else None,
        }
        for e in entries
    ]
