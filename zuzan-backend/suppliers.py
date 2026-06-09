from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from database import get_db, Supplier
from auth import get_current_user, User

router = APIRouter()

class SupplierCreate(BaseModel):
    name:            str
    contact_person:  Optional[str] = None
    email:           Optional[str] = None
    phone:           Optional[str] = None
    address:         Optional[str] = None
    vat_number:      Optional[str] = None
    bank_name:       Optional[str] = None
    account_number:  Optional[str] = None
    branch_code:     Optional[str] = None
    account_type:    Optional[str] = None
    payment_terms:   int = 30
    notes:           Optional[str] = None

class SupplierUpdate(BaseModel):
    name:            Optional[str] = None
    contact_person:  Optional[str] = None
    email:           Optional[str] = None
    phone:           Optional[str] = None
    address:         Optional[str] = None
    vat_number:      Optional[str] = None
    bank_name:       Optional[str] = None
    account_number:  Optional[str] = None
    branch_code:     Optional[str] = None
    account_type:    Optional[str] = None
    payment_terms:   Optional[int] = None
    notes:           Optional[str] = None

def to_dict(s):
    return {
        "id": s.id, "name": s.name, "contact_person": s.contact_person,
        "email": s.email, "phone": s.phone, "address": s.address,
        "vat_number": s.vat_number, "bank_name": s.bank_name,
        "account_number": s.account_number, "branch_code": s.branch_code,
        "account_type": s.account_type, "payment_terms": s.payment_terms,
        "notes": s.notes, "created_at": s.created_at.isoformat(),
    }

@router.get("/")
async def list_suppliers(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(Supplier).filter(Supplier.company_id == current_user.company_id, Supplier.is_active == True).order_by(Supplier.name).all()
    return [to_dict(s) for s in items]

@router.post("/")
async def create_supplier(data: SupplierCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = Supplier(company_id=current_user.company_id, **data.dict())
    db.add(s); db.commit(); db.refresh(s)
    return to_dict(s)

@router.put("/{sid}")
async def update_supplier(sid: int, data: SupplierUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.query(Supplier).filter(Supplier.id == sid, Supplier.company_id == current_user.company_id).first()
    if not s: raise HTTPException(404, "Supplier not found")
    for k, v in data.dict(exclude_none=True).items(): setattr(s, k, v)
    db.commit(); db.refresh(s)
    return to_dict(s)

@router.delete("/{sid}")
async def delete_supplier(sid: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.query(Supplier).filter(Supplier.id == sid, Supplier.company_id == current_user.company_id).first()
    if not s: raise HTTPException(404, "Supplier not found")
    s.is_active = False; db.commit()
    return {"message": "Supplier deleted"}
