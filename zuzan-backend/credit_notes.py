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
import logging

logger = logging.getLogger("zuzan.creditnotes")
credit_notes_router = APIRouter()


class CreditNoteCreate(BaseModel):
    invoice_id:   Optional[int] = None   # link to original invoice (optional)
    client_name:  str
    description:  Optional[str] = None
    amount:       float                  # excl. VAT
    vat_rate:     Optional[float] = 0.15
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
    return [_cn_dict(r) for r in rows]


# ── POST /credit-notes ────────────────────────────────────────────────────────
@credit_notes_router.post("")
async def create_credit_note(
    body: CreditNoteCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from database import CreditNote

    # Determine client name from linked invoice if not provided
    client_name = body.client_name
    if body.invoice_id and not client_name:
        inv = db.query(Invoice).filter(
            Invoice.id == body.invoice_id,
            Invoice.company_id == current_user.company_id,
        ).first()
        if inv:
            client_name = inv.client_name

    # Compute amounts
    vat_rate   = body.vat_rate if body.vat_rate is not None else 0.15
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
        description=body.description,
        amount=body.amount,
        vat_amount=vat_amount,
        total_amount=total,
        currency=body.currency or "ZAR",
        issue_date=issue_date,
        notes=body.notes,
    )
    db.add(cn)
    db.flush()  # get cn.id

    # Post journal entry: DR Revenue, DR VAT Output (if VAT), CR Accounts Receivable
    try:
        je_id = _post_credit_note_journal(cn, current_user.company_id, db)
        cn.journal_entry_id = je_id
    except Exception as e:
        logger.warning(f"Credit note journal post failed: {e}")

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
    db.delete(cn)
    db.commit()
    return {"ok": True}


# ── Journal posting for credit note ──────────────────────────────────────────
def _post_credit_note_journal(cn, company_id: int, db: Session) -> Optional[int]:
    """
    Double-entry for a credit note:
      DR Revenue (4000)          — amount excl. VAT
      DR VAT Output (2200)       — VAT amount (if any)
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
    vat_acc = _get_account("2200")

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
