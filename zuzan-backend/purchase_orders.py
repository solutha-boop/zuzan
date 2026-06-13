from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from database import get_db, PurchaseOrder, PurchaseOrderItem, Supplier, Expense
from auth import get_current_user, User
import logging
import journal as journal_engine
logger = logging.getLogger("zuzan.po")

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
        "received_date": po.received_date.strftime("%Y-%m-%d") if getattr(po, "received_date", None) else None,
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


class ReceivedItem(BaseModel):
    item_id:           int
    quantity_received: float

class POReceive(BaseModel):
    items:            List[ReceivedItem]
    create_expense:   bool = True   # auto-create expense for payment
    expense_category: Optional[str] = "6000 - Cost of Sales"


@router.post("/{po_id}/receive")
async def receive_po(po_id: int, data: POReceive, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id, PurchaseOrder.company_id == current_user.company_id).first()
    if not po: raise HTTPException(404, "Purchase order not found")
    if po.status in ("received", "cancelled"):
        raise HTTPException(400, f"Cannot receive a PO with status '{po.status}'")

    # Map received quantities to items
    received_map = {r.item_id: r.quantity_received for r in data.items}
    received_total = 0.0
    all_received = True

    for item in po.items:
        qty_recv = received_map.get(item.id, 0)
        if qty_recv < item.quantity:
            all_received = False
        received_value = round(qty_recv * item.unit_price, 2)
        received_total += received_value

    # Update PO status
    po.status = "received" if all_received else "partial"
    po.received_date = datetime.utcnow()

    expense_id = None
    if data.create_expense and received_total > 0:
        vat_applicable = po.vat_amount > 0
        vat_on_received = round(received_total * 0.15, 2) if vat_applicable else 0
        expense = Expense(
            company_id=current_user.company_id,
            vendor=po.supplier_name or "Supplier",
            description=f"Goods received — {po.po_number}",
            amount=received_total,
            vat_amount=vat_on_received,
            category=data.expense_category,
            expense_date=datetime.utcnow(),
        )
        db.add(expense)
        db.flush()
        expense_id = expense.id

    db.commit()
    db.refresh(po)

    try:
        journal_engine.init_accounts(current_user.company_id, db)
        journal_engine.post_po_received(po, db)
        db.commit()
    except Exception as e:
        logger.warning(f"Journal post failed for PO {po.po_number}: {e}")

    return {
        **to_dict(po),
        "received_total":   round(received_total, 2),
        "expense_id":       expense_id,
        "expense_created":  expense_id is not None,
    }
