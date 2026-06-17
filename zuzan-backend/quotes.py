from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from database import get_db, Quote
from auth import get_current_user, User

def clean(value, max_len=500):
    if value is None: return value
    return str(value).strip()[:max_len]

router = APIRouter()

VAT_RATE = 0.15

class QuoteCreate(BaseModel):
    client_name:         str
    client_email:        Optional[str] = None
    description:         str
    amount:              float
    vat_applicable:      bool = True
    currency:            str = "ZAR"
    exchange_rate:       float = 1
    valid_until:         Optional[str] = None
    notes:               Optional[str] = None
    vat_amount_override: Optional[float] = None  # Manual VAT for non-ZAR quotes
    status:              str = "draft"            # "draft" or "sent"

class QuoteUpdate(BaseModel):
    client_name:         Optional[str] = None
    client_email:        Optional[str] = None
    description:         Optional[str] = None
    amount:              Optional[float] = None
    vat_applicable:      Optional[bool] = None
    vat_amount_override: Optional[float] = None  # Manual VAT override for non-ZAR quotes
    currency:            Optional[str] = None
    exchange_rate:       Optional[float] = None
    status:              Optional[str] = None
    valid_until:         Optional[str] = None
    notes:               Optional[str] = None

def next_quote_number(db, company_id):
    from sqlalchemy import func as _func
    last = db.query(_func.max(Quote.id)).filter(Quote.company_id == company_id).scalar() or 0
    existing_numbers = {
        row[0] for row in
        db.query(Quote.quote_number).filter(Quote.company_id == company_id).all()
    }
    n = last + 1
    candidate = f"QTE-{str(n).zfill(4)}"
    while candidate in existing_numbers:
        n += 1
        candidate = f"QTE-{str(n).zfill(4)}"
    return candidate

def to_dict(q):
    return {
        "id":           q.id,
        "quote_number": q.quote_number,
        "client_name":  q.client_name,
        "client_email": q.client_email,
        "description":  q.description,
        "amount":       q.amount,
        "vat_applicable": q.vat_applicable,
        "vat_amount":   q.vat_amount,
        "total_amount": q.total_amount,
        "currency":     q.currency,
        "exchange_rate": q.exchange_rate,
        "status":       q.status,
        "valid_until":  q.valid_until.strftime("%Y-%m-%d") if q.valid_until else None,
        "notes":        q.notes,
        "created_at":   q.created_at.isoformat(),
    }

@router.get("/")
async def list_quotes(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(Quote).filter(Quote.company_id == current_user.company_id).order_by(Quote.created_at.desc()).all()
    return [to_dict(q) for q in items]

@router.post("/")
async def create_quote(data: QuoteCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if data.currency != "ZAR" and data.vat_amount_override is not None:
        vat = round(data.vat_amount_override, 2)   # User-specified VAT for foreign currency
    else:
        vat = round(data.amount * VAT_RATE, 2) if data.vat_applicable else 0
    total = round(data.amount + vat, 2)
    valid = datetime.strptime(data.valid_until, "%Y-%m-%d") if data.valid_until else None
    q = Quote(
        company_id=current_user.company_id,
        quote_number=next_quote_number(db, current_user.company_id),
        client_name=clean(data.client_name, 200),
        client_email=clean(data.client_email, 200),
        description=clean(data.description, 1000),
        amount=data.amount,
        vat_applicable=data.vat_applicable,
        vat_amount=vat,
        total_amount=total,
        currency=data.currency,
        exchange_rate=data.exchange_rate,
        valid_until=valid,
        notes=clean(data.notes, 2000),
        status=data.status if data.status in ("draft", "sent") else "draft",
    )
    db.add(q); db.commit(); db.refresh(q)
    return to_dict(q)

@router.put("/{qid}")
async def update_quote(qid: int, data: QuoteUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(Quote).filter(Quote.id == qid, Quote.company_id == current_user.company_id).first()
    if not q: raise HTTPException(404, "Quote not found")
    if data.client_name  is not None: q.client_name  = data.client_name
    if data.client_email is not None: q.client_email = data.client_email
    if data.description  is not None: q.description  = data.description
    if data.status       is not None: q.status        = data.status
    if data.currency     is not None: q.currency      = data.currency
    if data.exchange_rate is not None: q.exchange_rate = data.exchange_rate
    if data.notes        is not None: q.notes         = data.notes
    if data.valid_until  is not None:
        q.valid_until = datetime.strptime(data.valid_until, "%Y-%m-%d")
    if data.amount is not None or data.vat_applicable is not None or data.vat_amount_override is not None:
        amt = data.amount if data.amount is not None else q.amount
        vat_on = data.vat_applicable if data.vat_applicable is not None else q.vat_applicable
        q.amount = amt
        q.vat_applicable = vat_on
        if data.vat_amount_override is not None:
            # Non-ZAR quotes: use the caller-supplied VAT amount
            q.vat_amount = round(data.vat_amount_override, 2)
        else:
            q.vat_amount = round(amt * VAT_RATE, 2) if vat_on else 0
        q.total_amount = round(amt + q.vat_amount, 2)
    db.commit(); db.refresh(q)
    return to_dict(q)

@router.delete("/{qid}")
async def delete_quote(qid: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(Quote).filter(Quote.id == qid, Quote.company_id == current_user.company_id).first()
    if not q: raise HTTPException(404, "Quote not found")
    db.delete(q); db.commit()
    return {"message": "Quote deleted"}
