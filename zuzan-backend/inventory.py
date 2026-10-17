from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import logging

from database import get_db, InventoryItem
from auth import get_current_user, User
import journal as journal_engine

logger = logging.getLogger("zuzan.inventory")

router = APIRouter()

class ItemCreate(BaseModel):
    name:             str
    sku:              Optional[str] = None
    description:      Optional[str] = None
    category:         Optional[str] = None
    unit_cost:        float = 0
    unit_price:       float = 0
    quantity_on_hand: float = 0
    reorder_level:    float = 5
    unit_of_measure:  str = "Unit"

class ItemUpdate(BaseModel):
    name:             Optional[str] = None
    sku:              Optional[str] = None
    description:      Optional[str] = None
    category:         Optional[str] = None
    unit_cost:        Optional[float] = None
    unit_price:       Optional[float] = None
    quantity_on_hand: Optional[float] = None
    reorder_level:    Optional[float] = None
    unit_of_measure:  Optional[str] = None

class StockAdjust(BaseModel):
    quantity: float   # positive = receive, negative = issue
    reason:   Optional[str] = None

def item_to_dict(i):
    return {
        "id":               i.id,
        "sku":              i.sku,
        "name":             i.name,
        "description":      i.description,
        "category":         i.category,
        "unit_cost":        i.unit_cost,
        "unit_price":       i.unit_price,
        "quantity_on_hand": i.quantity_on_hand,
        "reorder_level":    i.reorder_level,
        "unit_of_measure":  i.unit_of_measure,
        "low_stock":        i.quantity_on_hand <= i.reorder_level,
        "stock_value":      round((i.unit_cost or 0) * (i.quantity_on_hand or 0), 2),
        "created_at":       i.created_at.isoformat(),
    }

@router.get("/")
async def list_items(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(InventoryItem).filter(InventoryItem.company_id == current_user.company_id, InventoryItem.is_active == True).all()
    return [item_to_dict(i) for i in items]

def _check_non_negative(d):
    for k in ("unit_cost", "unit_price", "quantity_on_hand", "reorder_level"):
        if d.get(k) is not None and d[k] < 0:
            raise HTTPException(status_code=400, detail=f"{k.replace('_', ' ')} cannot be negative.")


@router.post("/")
async def create_item(data: ItemCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _check_non_negative(data.dict())
    item = InventoryItem(company_id=current_user.company_id, **data.dict())
    db.add(item); db.flush()
    try:
        # Opening stock goes on the ledger too, otherwise Inventory (1200) never matches the stock list
        if (item.quantity_on_hand or 0) > 0 and (item.unit_cost or 0) > 0:
            journal_engine.init_accounts(current_user.company_id, db)
            journal_engine.post_stock_adjustment(item, item.quantity_on_hand, db, reason="Opening stock")
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Journal post failed for new inventory item: {e}")
        raise HTTPException(status_code=500, detail=f"Item not saved - the stock journal failed: {e}")
    db.refresh(item)
    return item_to_dict(item)

@router.put("/{item_id}")
async def update_item(item_id: int, data: ItemUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id, InventoryItem.company_id == current_user.company_id).first()
    if not item: raise HTTPException(status_code=404, detail="Item not found")
    upd = data.dict(exclude_none=True)
    _check_non_negative(upd)
    old_qty, old_cost = (item.quantity_on_hand or 0), (item.unit_cost or 0)
    for k, v in upd.items():
        setattr(item, k, v)
    new_qty, new_cost = (item.quantity_on_hand or 0), (item.unit_cost or 0)
    try:
        # Keep the ledger in step with direct edits to quantity / cost
        if new_qty != old_qty or new_cost != old_cost:
            journal_engine.init_accounts(current_user.company_id, db)
            # revalue the existing stock to the new cost, then book the quantity change at the new cost
            journal_engine.post_stock_revaluation(item, old_qty * (new_cost - old_cost), db)
            if new_qty != old_qty:
                journal_engine.post_stock_adjustment(item, new_qty - old_qty, db, reason="Stock count / edit")
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Journal post failed for inventory edit {item_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Item not saved - the stock journal failed: {e}")
    db.refresh(item)
    return item_to_dict(item)

@router.post("/{item_id}/adjust")
async def adjust_stock(item_id: int, data: StockAdjust, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id, InventoryItem.company_id == current_user.company_id).first()
    if not item: raise HTTPException(status_code=404, detail="Item not found")
    actual_qty = round(data.quantity, 4)
    current_qty = item.quantity_on_hand or 0
    # Clamp negative adjustments so stock can't go below zero; record actual applied qty for journal
    applied_qty = actual_qty if actual_qty >= 0 else max(actual_qty, -current_qty)
    item.quantity_on_hand = round(current_qty + applied_qty, 4)
    # Quantity and journal commit together - never a stock change without its ledger entry
    try:
        journal_engine.init_accounts(current_user.company_id, db)
        journal_engine.post_stock_adjustment(item, applied_qty, db, reason=data.reason)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Journal post failed for stock adjustment on item {item.id}: {e}")
        raise HTTPException(status_code=500, detail=f"Stock adjustment not saved - the journal failed: {e}")
    db.refresh(item)
    return item_to_dict(item)

@router.delete("/{item_id}")
async def delete_item(item_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id, InventoryItem.company_id == current_user.company_id).first()
    if not item: raise HTTPException(status_code=404, detail="Item not found")
    if (item.quantity_on_hand or 0) > 0 and (item.unit_cost or 0) > 0:
        raise HTTPException(status_code=400, detail="This item still has stock on hand. Adjust the quantity to zero (write-off or sale) before deleting it, so the stock value leaves the books.")
    item.is_active = False; db.commit()
    return {"message": "Item deleted"}

@router.get("/summary")
async def inventory_summary(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(InventoryItem).filter(InventoryItem.company_id == current_user.company_id, InventoryItem.is_active == True).all()
    total_value   = sum((i.unit_cost or 0) * (i.quantity_on_hand or 0) for i in items)
    retail_value  = sum((i.unit_price or 0) * (i.quantity_on_hand or 0) for i in items)
    low_stock     = [item_to_dict(i) for i in items if i.quantity_on_hand <= i.reorder_level]
    return {"total_items": len(items), "total_cost_value": round(total_value, 2), "total_retail_value": round(retail_value, 2), "low_stock_count": len(low_stock), "low_stock_items": low_stock}
