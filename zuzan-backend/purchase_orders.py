from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from database import get_db, PurchaseOrder, PurchaseOrderItem, Supplier, Expense
from auth import get_current_user, User
import logging
import journal as journal_engine
import email_service
logger = logging.getLogger("zuzan.po")

router = APIRouter()

class POItem(BaseModel):
    description: str
    quantity:    float = 1
    unit_price:  float = 0

class POCreate(BaseModel):
    # NOTE: no currency field — POs are ZAR-only by design (see PurchaseOrder model
    # in database.py). Do not add one without exchange-rate handling across the AP chain.
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
    # Max-id seeded with collision check (scale fix 2026-07-03), matching
    # next_invoice_number/next_quote_number: the previous count()+1 scheme
    # produced duplicate numbers after any PO was deleted.
    from sqlalchemy import func as _func
    last = db.query(_func.max(PurchaseOrder.id)).filter(PurchaseOrder.company_id == company_id).scalar() or 0
    existing_numbers = {
        row[0] for row in
        db.query(PurchaseOrder.po_number).filter(PurchaseOrder.company_id == company_id).all()
    }
    n = last + 1
    candidate = f"PO-{str(n).zfill(4)}"
    while candidate in existing_numbers:
        n += 1
        candidate = f"PO-{str(n).zfill(4)}"
    return candidate

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
                   "quantity_received": i.quantity_received or 0,
                   "unit_price": i.unit_price, "total": i.total} for i in po.items],
        "created_at": po.created_at.isoformat(),
    }

@router.get("/")
async def list_pos(
    limit: Optional[int] = None,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Optional pagination (scale fix 2026-07-03) — omitted params return all rows as before.
    try:
        q = (
            db.query(PurchaseOrder)
            .options(joinedload(PurchaseOrder.items))
            .filter(PurchaseOrder.company_id == current_user.company_id)
            .order_by(PurchaseOrder.created_at.desc())
        )
        if offset:
            q = q.offset(offset)
        if limit is not None:
            q = q.limit(limit)
        pos = q.all()
        return [to_dict(p) for p in pos]
    except Exception as e:
        logger.error(f"list_pos error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/")
async def create_po(data: POCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
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
    except Exception as e:
        logger.error(f"create_po error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{po_id}")
async def update_po(po_id: int, data: POUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id, PurchaseOrder.company_id == current_user.company_id).first()
    if not po: raise HTTPException(404, "Purchase order not found")
    if data.supplier_id is not None: po.supplier_id = data.supplier_id
    if data.supplier_name is not None: po.supplier_name = data.supplier_name
    if data.status is not None and data.status != po.status:
        # Whitelist status transitions (audit fix 2026-07-03): financial statuses
        # (received/partial/paid) must be reached via /receive and /pay, which post
        # the required journal entries and receipt tracking. Setting them directly
        # would bypass the journal and misstate COGS and the AP control account.
        ALLOWED_TRANSITIONS = {
            "draft":     {"sent", "cancelled"},
            "sent":      {"draft", "cancelled"},
            "cancelled": {"draft"},
        }
        if data.status not in ALLOWED_TRANSITIONS.get(po.status, set()):
            raise HTTPException(
                400,
                f"Cannot change status from '{po.status}' to '{data.status}' via update. "
                f"Use POST /purchase-orders/{po.id}/receive or /pay so journal entries are posted correctly."
            )
        po.status = data.status
    if data.notes is not None: po.notes = data.notes
    if data.delivery_date is not None:
        po.delivery_date = datetime.strptime(data.delivery_date, "%Y-%m-%d")
    if data.items is not None:
        # Block item edits once goods have been received (audit fix 2026-07-02):
        # replacing items would wipe quantity_received tracking and desync the
        # journal entries already posted for prior deliveries.
        if po.status in ("received", "partial", "paid"):
            raise HTTPException(400, f"Cannot edit items on a PO with status '{po.status}' — journal entries exist for received goods")
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

@router.post("/{po_id}/send")
async def send_po(po_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Email the PO to the supplier and mark it as sent."""
    po = (
        db.query(PurchaseOrder)
        .options(joinedload(PurchaseOrder.items))
        .filter(PurchaseOrder.id == po_id, PurchaseOrder.company_id == current_user.company_id)
        .first()
    )
    if not po:
        raise HTTPException(404, "Purchase order not found")
    if po.status in ("received", "partial", "paid", "cancelled"):
        raise HTTPException(400, f"Cannot send a PO with status '{po.status}'")

    # Resolve supplier email (optional — status updates regardless)
    supplier_email = None
    if po.supplier_id:
        s = db.query(Supplier).filter(Supplier.id == po.supplier_id).first()
        if s:
            supplier_email = s.email

    # Always mark as sent first
    po.status = "sent"
    db.commit()
    db.refresh(po)

    # Attempt email if we have an address
    email_sent = False
    if supplier_email:
        from database import Company
        company = db.query(Company).filter(Company.id == current_user.company_id).first()
        company_display = company.name if company else "Your company"
        po_dict = to_dict(po)
        email_sent = email_service.send_po_email(
            supplier_email=supplier_email,
            supplier_name=po.supplier_name or supplier_email,
            po=po_dict,
            company_name=company_display,
        )

    return {**to_dict(po), "emailed_to": supplier_email if email_sent else None, "email_sent": email_sent}


@router.delete("/{po_id}")
async def delete_po(po_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id, PurchaseOrder.company_id == current_user.company_id).first()
    if not po:
        raise HTTPException(404, "Purchase order not found")
    # Block deletion of POs that have already been received or paid — these have
    # journal entries (DR COGS / CR AP, and DR AP / CR Bank) that must be reversed
    # first, otherwise COGS and the AP control account (2000) become permanently misstated.
    if po.status in ("received", "partial", "paid"):
        # Reverse all journal entries linked to this PO before deleting.
        # Sources: "purchase_order" (received entry) and "po_payment" (payment clearance).
        try:
            journal_engine.init_accounts(current_user.company_id, db)
            reason = f"PO deleted — {po.po_number} ({po.supplier_name or 'Supplier'})"
            for src in ("purchase_order", "po_payment"):
                journal_engine.reverse_journal_entries(
                    current_user.company_id, src, po.id, db, reason=reason
                )
            db.commit()
        except Exception as e:
            logger.error(f"Journal reversal failed for PO {po.po_number}: {e}")
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"PO deletion aborted — journal reversal failed: {e}. Please retry.",
            )
    db.delete(po)
    db.commit()
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
    # "paid" is blocked too (audit fix 2026-07-02): receiving after payment would flip the
    # status back to partial/received, re-opening a settled creditor. Deliveries after
    # payment must be recorded on a new PO.
    if po.status in ("received", "paid", "cancelled"):
        raise HTTPException(400, f"Cannot receive a PO with status '{po.status}'")

    # Map received quantities to items.
    # Cumulative tracking (audit fix 2026-07-02): each item accumulates quantity_received
    # across deliveries, so multi-delivery POs eventually reach "received" and a delivery
    # exceeding the remaining ordered quantity is rejected instead of double-posting.
    received_map = {r.item_id: r.quantity_received for r in data.items}
    received_total = 0.0   # ex-VAT amount received in THIS call
    EPS = 1e-6             # float tolerance for quantity comparisons

    # Validate and compute WITHOUT mutating items yet — mutations are applied
    # after init_accounts below, because init_accounts commits internally and
    # would otherwise persist the new quantities before the journal post
    # (audit fix 2026-07-09).
    new_quantities: dict = {}   # item.id -> new cumulative quantity_received
    for item in po.items:
        qty_recv = received_map.get(item.id, 0)
        if qty_recv < 0:
            raise HTTPException(400, f"Received quantity for '{item.description}' cannot be negative")
        already = item.quantity_received or 0
        remaining = (item.quantity or 0) - already
        if qty_recv > remaining + EPS:
            raise HTTPException(
                400,
                f"Cannot receive {qty_recv:g} of '{item.description}' — "
                f"{already:g} of {item.quantity:g} already received "
                f"(only {max(0, remaining):g} outstanding). "
                f"Enter this delivery's quantity only, not the full order."
            )
        new_quantities[item.id] = round(already + qty_recv, 6)
        received_total += round(qty_recv * item.unit_price, 2)

    all_received = all(
        new_quantities.get(item.id, item.quantity_received or 0) >= (item.quantity or 0) - EPS
        for item in po.items
    )
    received_total = round(received_total, 2)

    # Reject zero-value deliveries (audit fix 2026-07-09): an all-zero receive
    # would flip the PO to "partial" with NO journal entry, so creditors-aging
    # and Rule 7 would fall back to po.total_amount against a zero journal AP
    # balance, and _po_delivered_net's legacy fallback would put the full
    # subtotal into P&L COGS. Nothing was delivered — there is nothing to post.
    if received_total <= 0:
        raise HTTPException(
            400,
            "Nothing received — all delivery quantities are zero. "
            "Enter the quantity actually delivered for at least one line item."
        )

    # Proportional VAT: apply the same VAT rate as the PO (15% if VAT-applicable, 0 otherwise)
    vat_rate = (po.vat_amount / po.subtotal) if (po.subtotal and po.vat_amount) else 0.0
    received_vat   = round(received_total * vat_rate, 2)

    # Ensure the chart of accounts exists BEFORE mutating the PO — init_accounts
    # commits internally, which would otherwise persist the status change early
    # and defeat the single-commit rollback below (audit fix 2026-07-09).
    journal_engine.init_accounts(current_user.company_id, db)

    # Apply the receipt: cumulative item quantities + PO status (deferred from
    # the validation loop above so init_accounts' commit can't persist them early)
    for item in po.items:
        if item.id in new_quantities:
            item.quantity_received = new_quantities[item.id]
    po.status = "received" if all_received else "partial"
    # Keep the FIRST delivery date (audit fix 2026-07-02): overwriting on each partial
    # delivery shifted the PO's COGS into the latest delivery month in trend reports.
    if not po.received_date:
        po.received_date = datetime.utcnow()

    # NOTE: We use the double-entry journal (post_po_received) as the single
    # source of truth — DR Cost of Sales / CR Accounts Payable.
    # Creating a separate Expense record would double-count the cost, so we
    # ignore data.create_expense here; the journal entry IS the cost record.
    expense_id = None

    # Single commit AFTER the journal post succeeds (audit fix 2026-07-09):
    # previously the receipt was committed first, so a journal failure left a
    # received/partial PO with no journal entry while the error message falsely
    # claimed a rollback — and the suggested retry was blocked by the status
    # guard above. Now a journal failure rolls back the receipt too.
    try:
        # Post a journal entry for the amount received in THIS call.
        # Each call (first receive or subsequent partial delivery) posts its own
        # incremental entry, so the AP and COGS accounts accumulate correctly.
        journal_engine.post_po_received(
            po, db,
            received_net=received_total,
            received_vat=received_vat,
        )
        db.commit()
    except Exception as e:
        logger.error(f"Journal post failed for PO {po.po_number}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"PO receipt failed — journal entry could not be posted: {e}. No changes were saved — please retry.",
        )
    db.refresh(po)

    return {
        **to_dict(po),
        "received_total":   round(received_total, 2),
        "expense_id":       expense_id,
        "expense_created":  expense_id is not None,
    }


@router.post("/backfill-received-dates")
async def backfill_received_dates(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Audit fix: set received_date = created_at for any PO in received/partial/paid status
    that is missing a received_date. Safe to run multiple times (idempotent).
    """
    pos = db.query(PurchaseOrder).filter(
        PurchaseOrder.company_id == current_user.company_id,
        PurchaseOrder.status.in_(["received", "partial", "paid"]),
        PurchaseOrder.received_date == None,  # noqa: E711
    ).all()
    updated = 0
    for po in pos:
        po.received_date = po.created_at
        updated += 1
    db.commit()
    return {
        "status":  "ok",
        "updated": updated,
        "message": f"Set received_date on {updated} purchase order(s) using their created_at date.",
    }


@router.post("/{po_id}/pay")
async def pay_po(po_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Mark a purchase order as paid.
    Posts the journal entry: DR Accounts Payable / CR Bank (clears AP).
    Must be called after /receive — goods must already be received.
    """
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id, PurchaseOrder.company_id == current_user.company_id).first()
    if not po:
        raise HTTPException(404, "Purchase order not found")
    if po.status == "paid":
        raise HTTPException(400, "Purchase order has already been paid")
    if po.status not in ("received", "partial"):
        raise HTTPException(400, f"PO must be received before marking as paid. Current status: '{po.status}'")

    # Ensure the chart of accounts exists BEFORE mutating the PO — init_accounts
    # commits internally, which would otherwise persist the status change early
    # and defeat the single-commit rollback below (audit fix 2026-07-09).
    journal_engine.init_accounts(current_user.company_id, db)

    # Determine the actual AP balance to clear.
    # For full receipts this equals po.total_amount.
    # For partial POs the AP balance is the sum of incremental delivery credits
    # posted to account 2000 by each post_po_received call — which may be less
    # than po.total_amount.  Paying po.total_amount would over-debit AP and
    # mis-state the bank balance.
    from database import Account as _Acct, JournalEntry as _JE, JournalLine as _JL
    ap_acct = db.query(_Acct).filter(
        _Acct.company_id == current_user.company_id,
        _Acct.code == "2000",
    ).first()
    ap_balance = None
    if ap_acct:
        # Reversal-aware (audit fix 2026-07-13): net credits minus debits and
        # include "purchase_order_reversal" entries, so paying a PO whose receipt
        # was partially reversed clears only the true remaining AP balance.
        ap_lines = (
            db.query(_JL)
            .join(_JE, _JL.entry_id == _JE.id)
            .filter(
                _JE.company_id == current_user.company_id,
                _JE.source.in_(["purchase_order", "purchase_order_reversal"]),
                _JE.source_id == po.id,
                _JL.account_id == ap_acct.id,
            )
            .all()
        )
        total_ap_credits = sum(l.credit - l.debit for l in ap_lines)
        if total_ap_credits > 0:
            ap_balance = round(total_ap_credits, 2)

    # Single commit AFTER the journal post succeeds (audit fix 2026-07-09):
    # previously status="paid" was committed first, so a journal failure left a
    # paid PO whose AP credit was never cleared — it vanished from the creditors
    # book while account 2000 kept the balance (Rule 7 fail) — and the error
    # message falsely claimed a rollback while the suggested retry was blocked
    # by the "already been paid" guard above. Now the status change and the
    # journal entry commit or roll back together.
    po.status = "paid"
    try:
        journal_engine.post_po_paid(po, db, paid_amount=ap_balance)
        db.commit()
    except Exception as e:
        logger.error(f"Journal post failed for PO payment {po.po_number}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"PO payment failed — journal entry could not be posted: {e}. No changes were saved — please retry.",
        )
    db.refresh(po)

    return {**to_dict(po), "journal": "DR Accounts Payable / CR Bank posted"}
