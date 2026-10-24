"""
ZuZan Credit Notes — issue credit notes against invoices (or standalone).
Mounted at /credit-notes.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from database import get_db, Invoice, InvoiceStatus, Company, SessionLocal
from auth import get_current_user, User
from journal import company_vat_registered as _vatreg
import logging
import json as _json

logger = logging.getLogger("zuzan.creditnotes")
credit_notes_router = APIRouter()


class StockReturn(BaseModel):
    code: str                 # inventory SKU (or name) of an item sold on the linked invoice
    quantity: float           # units coming back


class CreditNoteCreate(BaseModel):
    restock:      Optional[list[StockReturn]] = None   # goods physically returned: put back on the shelf at their original cost
    invoice_id:   Optional[int] = None   # link to original invoice (optional)
    client_name:  str
    description:  Optional[str] = None
    amount:       float                  # excl. VAT
    vat_rate:     Optional[float] = None   # None = follow the linked invoice (0% if it had no VAT, else 15%)
    currency:     Optional[str] = "ZAR"
    notes:        Optional[str] = None
    issue_date:   Optional[str] = None   # ISO date; defaults to today


def _cn_dict(cn) -> dict:
    return {
        "id":               cn.id,
        "credit_note_number": cn.credit_note_number,
        "invoice_id":       cn.invoice_id,
        "client_name":      cn.client_name,
        "description":      cn.description,
        "amount":           cn.amount,
        "vat_amount":       cn.vat_amount,
        "total_amount":     cn.total_amount,
        "currency":         cn.currency or "ZAR",
        "issue_date":       cn.issue_date.isoformat() if cn.issue_date else None,
        "notes":            cn.notes,
        "journal_entry_id": cn.journal_entry_id,
        "created_at":       cn.created_at.isoformat() if cn.created_at else None,
    }


def _plan_stock_return(db, company_id: int, invoice, restock):
    """Check each returned line against what the invoice sold less what earlier credit notes already took back.
    Returns ([{item_id, qty, cost}], total_cost). Cost is the ORIGINAL per-unit cost of the sale."""
    from database import InventoryItem, CreditNote
    try:
        sold = _json.loads(invoice.stock_cogs_json) if invoice.stock_cogs_json else []
    except Exception:
        sold = []
    if not sold:
        raise HTTPException(status_code=400, detail="That invoice did not sell any tracked stock, so there is nothing to put back.")
    sold_q, sold_cost = {}, {}
    for m in sold:
        sold_q[m["item_id"]] = sold_q.get(m["item_id"], 0) + (m.get("qty") or 0)
        sold_cost[m["item_id"]] = sold_cost.get(m["item_id"], 0) + (m.get("cost") or 0)
    back_q = {}
    for c in db.query(CreditNote).filter(CreditNote.company_id == company_id, CreditNote.invoice_id == invoice.id).all():
        for r in (_json.loads(c.stock_returns_json) if c.stock_returns_json else []):
            back_q[r["item_id"]] = back_q.get(r["item_id"], 0) + r["qty"]
    items = db.query(InventoryItem).filter(InventoryItem.company_id == company_id, InventoryItem.is_active == True).all()
    plan, total, seen = [], 0.0, {}
    for ln in restock:
        key = (ln.code or "").strip().lower()
        it = next((i for i in items if (i.sku or "").strip().lower() == key or (i.name or "").strip().lower() == key), None)
        if not it or it.id not in sold_q:
            raise HTTPException(status_code=400, detail=f"'{ln.code}' was not sold on that invoice.")
        if not (ln.quantity or 0) > 0:
            raise HTTPException(status_code=400, detail=f"Returned quantity for '{ln.code}' must be greater than zero.")
        seen[it.id] = seen.get(it.id, 0) + ln.quantity
        left = sold_q[it.id] - back_q.get(it.id, 0)
        if seen[it.id] > left + 1e-6:
            raise HTTPException(status_code=400, detail=f"Cannot take back {seen[it.id]:g} of '{it.name}': {sold_q[it.id]:g} sold, {back_q.get(it.id, 0):g} already returned.")
    for iid, q in seen.items():
        unit = (sold_cost[iid] / sold_q[iid]) if sold_q[iid] else 0
        cost = round(q * unit, 2)
        plan.append({"item_id": iid, "qty": q, "cost": cost}); total += cost
    return plan, round(total, 2)


# ── GET /credit-notes ─────────────────────────────────────────────────────────
@credit_notes_router.get("")
async def list_credit_notes(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from database import CreditNote
    rows = (
        db.query(CreditNote)
        .filter(CreditNote.company_id == current_user.company_id)
        .order_by(CreditNote.created_at.desc())
        .all()
    )
    # enrich for the screen: the invoice number and the names of any goods put back in stock
    from database import InventoryItem
    inv_no = {i.id: i.invoice_number for i in db.query(Invoice).filter(Invoice.company_id == current_user.company_id,
              Invoice.id.in_([r.invoice_id for r in rows if r.invoice_id] or [0])).all()}
    names = {i.id: i.name for i in db.query(InventoryItem).filter(InventoryItem.company_id == current_user.company_id).all()}
    out = []
    for r in rows:
        d = _cn_dict(r)
        d["invoice_number"] = inv_no.get(r.invoice_id)
        try:
            rets = _json.loads(r.stock_returns_json) if r.stock_returns_json else []
        except Exception:
            rets = []
        d["stock_returns"] = [{"name": names.get(x["item_id"], "item"), "qty": x["qty"]} for x in rets]
        out.append(d)
    return out


# ── GET /credit-notes/returnable/{invoice_id} ─────────────────────────────────
@credit_notes_router.get("/returnable/{invoice_id}")
async def returnable_stock(
    invoice_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Stock lines that were sold on this invoice and can still be put back by a credit note."""
    from database import InventoryItem, CreditNote
    inv = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.company_id == current_user.company_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    try:
        sold = _json.loads(inv.stock_cogs_json) if inv.stock_cogs_json else []
    except Exception:
        sold = []
    sold_q = {}
    for m in sold:
        sold_q[m["item_id"]] = sold_q.get(m["item_id"], 0) + (m.get("qty") or 0)
    back_q = {}
    for cn in db.query(CreditNote).filter(CreditNote.company_id == current_user.company_id, CreditNote.invoice_id == inv.id).all():
        for r in (_json.loads(cn.stock_returns_json) if cn.stock_returns_json else []):
            back_q[r["item_id"]] = back_q.get(r["item_id"], 0) + r["qty"]
    out = []
    for it in db.query(InventoryItem).filter(InventoryItem.company_id == current_user.company_id, InventoryItem.id.in_(list(sold_q) or [0])).all():
        left = round(sold_q[it.id] - back_q.get(it.id, 0), 4)
        out.append({"code": it.sku or it.name, "name": it.name, "sold": sold_q[it.id], "returned": back_q.get(it.id, 0), "returnable": max(0, left)})
    return out


# ── POST /credit-notes ────────────────────────────────────────────────────────
@credit_notes_router.post("")
async def create_credit_note(
    body: CreditNoteCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from database import CreditNote

    # --- validation (a credit note must be a positive amount against a real, own invoice) ---
    if not body.amount or body.amount <= 0 or body.amount != body.amount:
        raise HTTPException(status_code=400, detail="The credit note amount must be greater than zero.")
    if body.vat_rate is not None and not (0 <= body.vat_rate <= 1):
        raise HTTPException(status_code=400, detail="vat_rate must be between 0 and 1 (e.g. 0.15).")
    if body.issue_date:
        try:
            datetime.fromisoformat(body.issue_date)
        except Exception:
            raise HTTPException(status_code=400, detail="issue_date must be an ISO date, e.g. 2026-10-31.")
    linked_inv = None
    if body.invoice_id:
        linked_inv = db.query(Invoice).filter(Invoice.id == body.invoice_id, Invoice.company_id == current_user.company_id).first()
        if not linked_inv:
            raise HTTPException(status_code=404, detail="The invoice this credit note is linked to was not found.")

    # The ledger and the VAT201 are in rand. A foreign-currency credit note is converted at the linked invoice's rate.
    cn_currency = (body.currency or "ZAR").upper()
    fx_note = ""
    if cn_currency != "ZAR":
        rate = (linked_inv.exchange_rate if linked_inv is not None and (linked_inv.currency or "ZAR").upper() == cn_currency else None)
        if not rate:
            raise HTTPException(status_code=400, detail=f"A {cn_currency} credit note must be linked to the {cn_currency} invoice it credits, so the exchange rate is known.")
        fx_note = f" [{cn_currency} {body.amount:,.2f} at {rate}]"
        body = body.copy(update={"amount": round(body.amount * rate, 2), "currency": "ZAR"})

    # Never credit more than was invoiced (all credit notes on the invoice together, ex VAT, in rand)
    if linked_inv is not None:
        from database import CreditNote as _CNm
        inv_zar = (linked_inv.amount or 0) * ((linked_inv.exchange_rate or 1.0) if (linked_inv.currency or "ZAR") != "ZAR" else 1.0)
        already = sum((c.amount or 0) for c in db.query(_CNm).filter(_CNm.company_id == current_user.company_id, _CNm.invoice_id == linked_inv.id).all())
        if already + body.amount > inv_zar + 0.01:
            raise HTTPException(status_code=400, detail=f"This would credit more than the invoice: invoice {inv_zar:,.2f} ex VAT, already credited {already:,.2f}.")

    # Determine client name from linked invoice if not provided
    client_name = body.client_name
    if linked_inv is not None and not client_name:
        client_name = linked_inv.client_name

    # Compute amounts
    if body.vat_rate is not None:
        vat_rate = body.vat_rate
    else:
        _linked = None
        if body.invoice_id:
            _linked = db.query(Invoice).filter(Invoice.id == body.invoice_id, Invoice.company_id == current_user.company_id).first()
        # a credit note for an invoice that charged no VAT must not reverse VAT that was never charged
        vat_rate = 0.0 if (not _vatreg(db, current_user.company_id) or (_linked is not None and _linked.vat_amount is not None and (_linked.vat_amount or 0) == 0)) else 0.15
    vat_amount = round(body.amount * vat_rate, 2)
    total      = round(body.amount + vat_amount, 2)
    issue_date = datetime.fromisoformat(body.issue_date) if body.issue_date else datetime.utcnow()

    # Next credit note number
    from database import CreditNote as CN
    last = db.query(CN).filter(CN.company_id == current_user.company_id).order_by(CN.id.desc()).first()
    try:
        last_num = int(last.credit_note_number.split("-")[-1]) if last else 0
    except Exception:
        last_num = 0
    cn_number = f"CN-{last_num + 1:04d}"

    cn = CreditNote(
        company_id=current_user.company_id,
        invoice_id=body.invoice_id,
        credit_note_number=cn_number,
        client_name=client_name,
        description=((body.description or "") + fx_note).strip() or None,
        amount=body.amount,
        vat_amount=vat_amount,
        total_amount=total,
        currency=body.currency or "ZAR",
        issue_date=issue_date,
        notes=body.notes,
    )
    # Goods returned: validate against what the linked invoice actually sold (and earlier returns)
    _returns, _return_cost = [], 0.0
    if body.restock:
        if linked_inv is None:
            raise HTTPException(status_code=400, detail="To put stock back, link the credit note to the invoice that sold it.")
        _returns, _return_cost = _plan_stock_return(db, current_user.company_id, linked_inv, body.restock)
        cn.stock_returns_json = _json.dumps(_returns)
    db.add(cn)
    db.flush()  # get cn.id

    # Post journal entry: DR Revenue, DR VAT Output (if VAT), CR Accounts Receivable
    try:
        je_id = _post_credit_note_journal(cn, current_user.company_id, db)
        cn.journal_entry_id = je_id
        if _returns:
            from database import InventoryItem as _II
            import journal as _jj
            for _r in _returns:
                _it = db.query(_II).filter(_II.id == _r["item_id"], _II.company_id == current_user.company_id).first()
                if _it:
                    _it.quantity_on_hand = round((_it.quantity_on_hand or 0) + _r["qty"], 4)
            if _return_cost > 0:
                _jj.post_credit_note_stock_return(cn, _return_cost, db)
    except Exception as e:
        logger.error(f"Credit note journal post failed: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Credit note NOT saved - the journal entry failed: {e}")

    db.commit()
    db.refresh(cn)
    return _cn_dict(cn)


# ── GET /credit-notes/{id} ────────────────────────────────────────────────────
@credit_notes_router.get("/{cn_id}")
async def get_credit_note(
    cn_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from database import CreditNote
    cn = db.query(CreditNote).filter(
        CreditNote.id == cn_id,
        CreditNote.company_id == current_user.company_id,
    ).first()
    if not cn:
        raise HTTPException(status_code=404, detail="Credit note not found")
    return _cn_dict(cn)


# ── DELETE /credit-notes/{id} ─────────────────────────────────────────────────
@credit_notes_router.delete("/{cn_id}")
async def delete_credit_note(
    cn_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from database import CreditNote
    cn = db.query(CreditNote).filter(
        CreditNote.id == cn_id,
        CreditNote.company_id == current_user.company_id,
    ).first()
    if not cn:
        raise HTTPException(status_code=404, detail="Credit note not found")
    # The ledger entry must go with the document, otherwise revenue/AR stay permanently reduced with nothing to show for it.
    try:
        import journal as _j
        _j.reverse_journal_entries(current_user.company_id, "credit_note", cn.id, db, reason=f"Credit note {cn.credit_note_number} deleted")
        _rets = _json.loads(cn.stock_returns_json) if cn.stock_returns_json else []
        if _rets:
            from database import InventoryItem as _II
            for _r in _rets:
                _it = db.query(_II).filter(_II.id == _r["item_id"], _II.company_id == current_user.company_id).first()
                if _it and (_it.quantity_on_hand or 0) + 1e-6 < _r["qty"]:
                    raise HTTPException(status_code=400, detail=f"Cannot delete {cn.credit_note_number}: the {_r['qty']:g} returned units of '{_it.name}' are no longer on hand.")
            for _r in _rets:
                _it = db.query(_II).filter(_II.id == _r["item_id"], _II.company_id == current_user.company_id).first()
                if _it:
                    _it.quantity_on_hand = round((_it.quantity_on_hand or 0) - _r["qty"], 4)
            _j.reverse_journal_entries(current_user.company_id, "credit_note_stock", cn.id, db, reason=f"Credit note {cn.credit_note_number} deleted")
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        logger.error(f"Credit note reversal failed: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Credit note NOT deleted - its journal reversal failed: {e}")
    db.delete(cn)
    db.commit()
    return {"ok": True}


# ── Journal posting for credit note ──────────────────────────────────────────
def _post_credit_note_journal(cn, company_id: int, db: Session) -> Optional[int]:
    """
    Double-entry for a credit note:
      DR Revenue (4000)          — amount excl. VAT
      DR VAT Output (2100)       — VAT amount (if any)
      CR Accounts Receivable (1100) — total incl. VAT

    This reverses the original invoice's journal.
    """
    from database import Account, JournalEntry, JournalLine
    from sqlalchemy import func

    def _get_account(code: str):
        return db.query(Account).filter(
            Account.company_id == company_id,
            Account.code == code,
        ).first()

    ar_acc  = _get_account("1100")
    rev_acc = _get_account("4000")
    vat_acc = _get_account("2100")   # VAT Output (2200 is PAYE Payable - credit-note VAT was being posted there)

    if not ar_acc or not rev_acc:
        logger.warning("Credit note journal: required accounts not found")
        return None

    entry = JournalEntry(
        company_id=company_id,
        date=cn.issue_date or datetime.utcnow(),
        description=f"Credit note {cn.credit_note_number} — {cn.client_name}",
        reference=cn.credit_note_number,
        source="credit_note",
        source_id=cn.id,
    )
    db.add(entry)
    db.flush()

    lines = []
    # DR Revenue
    lines.append(JournalLine(
        entry_id=entry.id,
        account_id=rev_acc.id,
        debit=cn.amount,
        credit=0,
        description="Revenue reduction — credit note",
    ))
    # DR VAT Output (if VAT charged)
    if cn.vat_amount and cn.vat_amount > 0 and vat_acc:
        lines.append(JournalLine(
            entry_id=entry.id,
            account_id=vat_acc.id,
            debit=cn.vat_amount,
            credit=0,
            description="VAT output reduction — credit note",
        ))
    # CR Accounts Receivable
    lines.append(JournalLine(
        entry_id=entry.id,
        account_id=ar_acc.id,
        debit=0,
        credit=cn.total_amount,
        description="AR reduction — credit note",
    ))

    for line in lines:
        db.add(line)
    db.flush()
    return entry.id
