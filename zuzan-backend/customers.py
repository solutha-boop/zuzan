from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from database import get_db, Customer
from auth import get_current_user, User

def clean(value, max_len=500):
    if value is None: return value
    return str(value).strip()[:max_len]

router = APIRouter()

class CustomerCreate(BaseModel):
    name:            str
    contact_person:  Optional[str] = None
    email:           Optional[str] = None
    phone:           Optional[str] = None
    address:         Optional[str] = None
    vat_number:      Optional[str] = None
    payment_terms:   int = 30
    notes:           Optional[str] = None

class CustomerUpdate(BaseModel):
    name:            Optional[str] = None
    contact_person:  Optional[str] = None
    email:           Optional[str] = None
    phone:           Optional[str] = None
    address:         Optional[str] = None
    vat_number:      Optional[str] = None
    payment_terms:   Optional[int] = None
    notes:           Optional[str] = None

def to_dict(c):
    return {
        "id": c.id, "name": c.name, "contact_person": c.contact_person,
        "email": c.email, "phone": c.phone, "address": c.address,
        "vat_number": c.vat_number, "payment_terms": c.payment_terms,
        "notes": c.notes, "created_at": c.created_at.isoformat(),
    }

@router.get("/")
async def list_customers(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(Customer).filter(Customer.company_id == current_user.company_id, Customer.is_active == True).order_by(Customer.name).all()
    return [to_dict(c) for c in items]

@router.post("/")
async def create_customer(data: CustomerCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d = data.dict()
    for field in ["name","contact_person","email","phone","address","vat_number","notes"]:
        if d.get(field): d[field] = clean(d[field], 500)
    c = Customer(company_id=current_user.company_id, **d)
    db.add(c); db.commit(); db.refresh(c)
    return to_dict(c)

@router.put("/{cid}")
async def update_customer(cid: int, data: CustomerUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = db.query(Customer).filter(Customer.id == cid, Customer.company_id == current_user.company_id).first()
    if not c: raise HTTPException(404, "Customer not found")
    for k, v in data.dict(exclude_none=True).items(): setattr(c, k, v)
    db.commit(); db.refresh(c)
    return to_dict(c)

@router.delete("/{cid}")
async def delete_customer(cid: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = db.query(Customer).filter(Customer.id == cid, Customer.company_id == current_user.company_id).first()
    if not c: raise HTTPException(404, "Customer not found")
    c.is_active = False; db.commit()
    return {"message": "Customer deleted"}
