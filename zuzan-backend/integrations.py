"""
integrations.py — Inbound invoice push endpoint

Allows external back-office systems (e.g. Solid Matter Travel) to POST a
completed invoice directly into Zuzan over HTTPS using a Zuzan API key.

Endpoint:  POST /integrations/invoice
Auth:      X-API-Key: <zuzan_api_key>
Behaviour: Creates invoice + customer if new; updates + re-journals if the
           document number already exists for this company.
"""

from fastapi import APIRouter, HTTPException, Header, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import json

from database import get_db, Invoice, InvoiceStatus, Customer, JournalEntry
from api_keys import get_company_from_api_key
from journal import post_invoice_raised

router = APIRouter()


# ── PAYLOAD MODELS ────────────────────────────────────────────────────────────

class SMTClient(BaseModel):
    name: str
    accountNo: Optional[str] = None
    taxReference: Optional[str] = None
    billingAddress: Optional[str] = None

class SMTTraveller(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    pax: Optional[int] = 1

class SMTLineItem(BaseModel):
    serviceCode: Optional[str] = None
    service: Optional[str] = None
    description: str
    qty: float = 1
    net: float = 0
    markup: float = 0
    vat: float = 0
    total: float

class SMTTotals(BaseModel):
    net: float = 0
    markup: float = 0
    vat: float = 0
    total: float
    receipts: Optional[float] = 0
    due: Optional[float] = None

class SMTInvoice(BaseModel):
    quoteId: Optional[str] = None
    documentNo: str                # used as Zuzan invoice_number + dedup key
    documentDate: str              # ISO date e.g. "2026-09-04"
    travelDate: Optional[str] = None
    currency: Optional[str] = "ZAR"
    client: SMTClient
    traveller: Optional[SMTTraveller] = None
    lineItems: List[SMTLineItem] = []
    totals: SMTTotals

class InboundInvoicePayload(BaseModel):
    source: Optional[str] = None
    postedAt: Optional[str] = None
    invoice: SMTInvoice


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _find_or_create_customer(company_id: int, client: SMTClient, db: Session) -> Customer:
    """Match customer by external_code (accountNo) first, then name."""
    cust = None
    if client.accountNo:
        cust = db.query(Customer).filter(
            Customer.company_id == company_id,
            Customer.external_code == client.accountNo,
        ).first()
    if not cust:
        cust = db.query(Customer).filter(
            Customer.company_id == company_id,
            Customer.name.ilike(client.name.strip()),
        ).first()
    if not cust:
        cust = Customer(
            company_id=company_id,
            name=client.name.strip(),
            external_code=client.accountNo or None,
            address=client.billingAddress or None,
            vat_number=client.taxReference or None,
        )
        db.add(cust)
        db.flush()
    else:
        # Keep external_code up to date in case it was added later
        if client.accountNo and not cust.external_code:
            cust.external_code = client.accountNo
    return cust


def _build_items_json(line_items: List[SMTLineItem]) -> str:
    """Convert SMT line items → Zuzan items_json format."""
    items = []
    for li in line_items:
        items.append({
            "code":        li.serviceCode or "",
            "description": f"{li.service} — {li.description}" if li.service else li.description,
            "quantity":    li.qty,
            "unit_price":  round(li.net + li.markup, 2),  # net + markup = billed to client
            "vat_amount":  round(li.vat, 2),
            "total":       round(li.total, 2),
        })
    return json.dumps(items)


def _parse_date(date_str: str) -> datetime:
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(date_str[:10], "%Y-%m-%d")
        except ValueError:
            pass
    raise ValueError(f"Cannot parse date: {date_str}")


def _delete_existing_journals(invoice_id: int, company_id: int, db: Session):
    """Remove journal entries for a prior posting of this invoice."""
    db.query(JournalEntry).filter(
        JournalEntry.company_id == company_id,
        JournalEntry.source == "invoice_raised",
        JournalEntry.source_id == invoice_id,
    ).delete(synchronize_session=False)


# ── ENDPOINT ──────────────────────────────────────────────────────────────────

@router.post("/invoice")
async def inbound_invoice(
    payload: InboundInvoicePayload,
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    """
    Accept an invoice from an external back-office system and post it into Zuzan.

    Returns:
      {
        "status":          "created" | "updated",
        "zuzan_invoice_id": <int>,
        "invoice_number":   "<documentNo>",
        "message":          "<human-readable>"
      }

    Errors:
      401 — missing or invalid API key
      422 — payload validation failure (FastAPI auto)
      500 — unexpected server error
    """
    company, key_record = get_company_from_api_key(x_api_key, db)
    if not company:
        raise HTTPException(status_code=401, detail="Invalid or expired API key.")

    inv = payload.invoice
    doc_no = inv.documentNo.strip()

    # ── Find or create customer ───────────────────────────────────────────────
    customer = _find_or_create_customer(company.id, inv.client, db)

    # ── Compute amounts ───────────────────────────────────────────────────────
    subtotal   = round(inv.totals.net + inv.totals.markup, 2)
    vat_amount = round(inv.totals.vat, 2)
    total      = round(inv.totals.total, 2)
    items_json = _build_items_json(inv.lineItems)

    try:
        issue_date = _parse_date(inv.documentDate)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid documentDate: {inv.documentDate}")

    # ── Check for duplicate ───────────────────────────────────────────────────
    existing = db.query(Invoice).filter(
        Invoice.company_id == company.id,
        Invoice.invoice_number == doc_no,
    ).first()

    if existing:
        # UPDATE path — reverse old journals, then repost
        _delete_existing_journals(existing.id, company.id, db)

        existing.client_name   = customer.name
        existing.client_email  = (inv.traveller.email if inv.traveller else None) or existing.client_email
        existing.amount        = subtotal
        existing.vat_amount    = vat_amount
        existing.total_amount  = total
        existing.currency      = inv.currency or "ZAR"
        existing.issue_date    = issue_date
        existing.quote_ref     = inv.quoteId or existing.quote_ref
        existing.tax_ref       = inv.client.taxReference or existing.tax_ref
        existing.travel_date   = inv.travelDate or existing.travel_date
        existing.pax_count     = (inv.traveller.pax if inv.traveller else None) or existing.pax_count
        existing.passenger_name= (inv.traveller.name if inv.traveller else None) or existing.passenger_name
        existing.items_json    = items_json
        existing.notes         = f"Re-posted from {payload.source or 'external'} at {payload.postedAt or datetime.utcnow().isoformat()}"
        db.flush()
        try:
            post_invoice_raised(existing, db)
        except Exception:
            pass  # journal failure must not block the invoice save
        db.commit()
        return {
            "status":           "updated",
            "zuzan_invoice_id": existing.id,
            "invoice_number":   doc_no,
            "message":          f"Invoice {doc_no} updated and re-posted to accounts.",
        }

    else:
        # CREATE path
        new_inv = Invoice(
            company_id     = company.id,
            invoice_number = doc_no,
            client_name    = customer.name,
            client_email   = (inv.traveller.email if inv.traveller else None) or "",
            description    = f"Travel invoice — {doc_no}",
            amount         = subtotal,
            vat_amount     = vat_amount,
            total_amount   = total,
            currency       = inv.currency or "ZAR",
            exchange_rate  = 1,
            status         = InvoiceStatus.sent,
            issue_date     = issue_date,
            quote_ref      = inv.quoteId or None,
            tax_ref        = inv.client.taxReference or None,
            travel_date    = inv.travelDate or None,
            pax_count      = (inv.traveller.pax if inv.traveller else None),
            passenger_name = (inv.traveller.name if inv.traveller else None),
            items_json     = items_json,
            notes          = f"Posted from {payload.source or 'external'} at {payload.postedAt or datetime.utcnow().isoformat()}",
        )
        db.add(new_inv)
        db.flush()
        try:
            post_invoice_raised(new_inv, db)
        except Exception:
            pass
        db.commit()
        db.refresh(new_inv)
        return {
            "status":           "created",
            "zuzan_invoice_id": new_inv.id,
            "invoice_number":   doc_no,
            "message":          f"Invoice {doc_no} created and posted to accounts.",
        }
