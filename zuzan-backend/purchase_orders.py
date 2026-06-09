from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from database import get_db, PurchaseOrder, PurchaseOrderItem, Supplier
from auth import get_current_user, User

router = APIRouter()

class POItem(BaseModel):
    description: str
    quantity:    float = 1
    unit_price:  float = 0

class POCreate(BaseModel):
    supplier_id:   Optional[int] = None
    supplier_name: Optional[str] = None
    delivery_date: Optional[str] = None
    vat_applicable: bool = True
    notes:         Optional[str] = None
    items:         List[POItem] = []

class POUpdate(BaseModel):
    supplier_id:   Optional[int] = None
    supplier_name: Optional[str] = None
    status:        Optional[str] = None
    delivery_date: Optional[str] = None
    vat_applicable: Optional[bool] = None
    notes:         Optional[str] = None
    items:         Optional[List[POItem]] = None

def next_po_number(db, company_id):
    count = db.query(PurchaseOrder).filter(PurchaseOrder.company_id == company_id).count()
    return f"PO-{str(count + 1).zfill(4)}"

def calc_totals(items, vat_applicable):
    subtotal = sum(i.quantity * i.unit_price for i in items)
    vat = round(subtotal * 0.15, 2) if vat_applicable else 0
    return round(subtotal, 2), vat, round(subtotal + vat, 2)

def to_dict(po):
    return {
        "id": po.id, "po_number": po.po_number,
        "supplier_id": po.supplier_id, "supplier_name": po.supplier_name,
        "status": po.status,
        "order_date": po.order_date.strftime("%Y-%m-%d") if po.order_date else None,
        "delivery_date": po.delivery_date.strftime("%Y-%m-%d") if po.delivery_date else None,
        "subtotal": po.subtotal, "vat_amount": po.vat_amount, "total_amount": po.total_amount,
        "notes": po.notes,
        "items": [{"id": i.id, "description": i.description, "quantity": i.quantity,
                   "unit_price": i.unit_price, "total": i.total} for i in po.items],
        "created_at": po.created_at.isoformat(),
    }

@router.get("/")
async def list_pos(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(PurchaseOrder).filter(PurchaseOrder.company_id == current_user.company_id).order_by(PurchaseOrder.created_at.desc()).all()
    return [to_dict(p) for p in items]

@router.post("/")
async def create_po(data: POCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    supplier_name = data.supplier_name
    if data.supplier_id and not supplier_name:
        s = db.query(Supplier).filter(Supplier.id == data.supplier_id).first()
        if s: supplier_name = s.name
    subtotal, vat, total = calc_totals(data.items, data.vat_applicable)
    delivery = datetime.strptime(data.delivery_date, "%Y-%m-%d") if data.delivery_date else None
    po = PurchaseOrder(
        company_id=current_user.company_id,
        po_number=next_po_number(db, current_user.company_id),
        supplier_id=data.supplier_id, supplier_name=supplier_name,
        delivery_date=delivery, subtotal=subtotal, vat_amount=vat, total_amount=total,
        notes=data.notes,
    )
    db.add(po); db.flush()
    for item in data.items:
        db.add(PurchaseOrderItem(
            purchase_order_id=po.id, description=item.description,
            quantity=item.quantity, unit_price=item.unit_price,
            total=round(item.quantity * item.unit_price, 2),
        ))
    db.commit(); db.refresh(po)
    return to_dict(po)

@router.put("/{po_id}")
async def update_po(po_id: int, data: POUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id, PurchaseOrder.company_id == current_user.company_id).first()
    if not po: raise HTTPException(404, "Purchase order not found")
    if data.supplier_id is not None: po.supplier_id = data.supplier_id
    if data.supplier_name is not None: po.supplier_name = data.supplier_name
    if data.status is not None: po.status = data.status
    if data.notes is not None: po.notes = data.notes
    if data.delivery_date is not None:
        po.delivery_date = datetime.strptime(data.delivery_date, "%Y-%m-%d")
    if data.items is not None:
        for old in po.items: db.delete(old)
        db.flush()
        vat_applicable = data.vat_applicable if data.vat_applicable is not None else (po.vat_amount > 0)
        subtotal, vat, total = calc_totals(data.items, vat_applicable)
        po.subtotal = subtotal; po.vat_amount = vat; po.total_amount = total
        for item in data.items:
            db.add(PurchaseOrderItem(
                purchase_order_id=po.id, description=item.description,
                quantity=item.quantity, unit_price=item.unit_price,
                total=round(item.quantity * item.unit_price, 2),
            ))
    db.commit(); db.refresh(po)
    return to_dict(po)

@router.delete("/{po_id}")
async def delete_po(po_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id, PurchaseOrder.company_id == current_user.company_id).first()
    if not po: raise HTTPException(404, "Purchase order not found")
    db.delete(po); db.commit()
    return {"message": "Purchase order deleted"}
