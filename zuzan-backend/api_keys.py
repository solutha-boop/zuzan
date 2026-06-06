from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import secrets, hashlib

from database import get_db, APIKey, Company, User
from auth import get_current_user

router = APIRouter()

RATE_LIMIT_PER_DAY = 1000  # requests per API key per day
SCOPES = ["read", "write", "payroll", "reports"]

# ── HELPERS ───────────────────────────────────────────────────────────────────
def generate_api_key() -> tuple[str, str, str]:
    """Returns (raw_key, key_hash, key_prefix)"""
    raw = "zuzan_" + secrets.token_urlsafe(32)
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    prefix = raw[:12]
    return raw, hashed, prefix

def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()

def get_company_from_api_key(api_key_raw: str, db: Session) -> Optional[tuple]:
    """Validate an API key and return (company, api_key_record) or None"""
    hashed = hash_key(api_key_raw)
    key_record = db.query(APIKey).filter(
        APIKey.key_hash == hashed,
        APIKey.is_active == True
    ).first()
    if not key_record:
        return None, None
    # Rate limiting
    if key_record.requests_today >= RATE_LIMIT_PER_DAY:
        return None, None
    company = db.query(Company).filter(Company.id == key_record.company_id).first()
    # Update last_used and request count
    key_record.last_used = datetime.utcnow()
    key_record.requests_today = (key_record.requests_today or 0) + 1
    db.commit()
    return company, key_record

# ── MODELS ────────────────────────────────────────────────────────────────────
class CreateKeyRequest(BaseModel):
    name: str
    scopes: List[str] = ["read"]

class APIKeyResponse(BaseModel):
    id: int
    name: str
    key_prefix: str
    scopes: str
    is_active: bool
    last_used: Optional[datetime]
    requests_today: int
    created_at: datetime

# ── ROUTES ────────────────────────────────────────────────────────────────────
@router.get("/")
async def list_keys(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    keys = db.query(APIKey).filter(
        APIKey.company_id == current_user.company_id,
        APIKey.is_active == True
    ).all()
    return [{
        "id":            k.id,
        "name":          k.name,
        "key_prefix":    k.key_prefix,
        "scopes":        k.scopes,
        "is_active":     k.is_active,
        "last_used":     k.last_used.isoformat() if k.last_used else None,
        "requests_today":k.requests_today or 0,
        "created_at":    k.created_at.isoformat(),
    } for k in keys]


@router.post("/")
async def create_key(data: CreateKeyRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Limit to 10 active keys per company
    existing = db.query(APIKey).filter(APIKey.company_id == current_user.company_id, APIKey.is_active == True).count()
    if existing >= 10:
        raise HTTPException(status_code=400, detail="Maximum 10 active API keys allowed.")

    valid_scopes = [s for s in data.scopes if s in SCOPES]
    if not valid_scopes:
        valid_scopes = ["read"]

    raw_key, hashed, prefix = generate_api_key()

    key = APIKey(
        company_id=current_user.company_id,
        name=data.name,
        key_hash=hashed,
        key_prefix=prefix,
        scopes=",".join(valid_scopes),
    )
    db.add(key)
    db.commit()
    db.refresh(key)

    return {
        "id":         key.id,
        "name":       key.name,
        "key":        raw_key,   # Only returned ONCE on creation
        "key_prefix": key.key_prefix,
        "scopes":     key.scopes,
        "created_at": key.created_at.isoformat(),
        "message":    "Copy this key now — it will not be shown again.",
    }


@router.delete("/{key_id}")
async def revoke_key(key_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    key = db.query(APIKey).filter(
        APIKey.id == key_id,
        APIKey.company_id == current_user.company_id
    ).first()
    if not key:
        raise HTTPException(status_code=404, detail="API key not found.")
    key.is_active = False
    db.commit()
    return {"message": "API key revoked."}


@router.get("/usage")
async def get_usage(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    keys = db.query(APIKey).filter(APIKey.company_id == current_user.company_id).all()
    total_today = sum(k.requests_today or 0 for k in keys if k.is_active)
    return {
        "total_requests_today": total_today,
        "rate_limit_per_key":   RATE_LIMIT_PER_DAY,
        "active_keys":          sum(1 for k in keys if k.is_active),
    }
