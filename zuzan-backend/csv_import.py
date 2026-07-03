"""
CSV Import — migrate data from Xero / QuickBooks / generic CSV files into ZuZan.

Supported entity types:
  POST /import/customers  — contact/customer list
  POST /import/suppliers  — vendor/supplier list
  POST /import/invoices   — invoice history
  POST /import/expenses   — expense / bill history

Column detection is case-insensitive and recognises common Xero and
QuickBooks export column names automatically.  Unknown column names are
ignored rather than rejected, so partial CSVs work.

Date formats accepted: YYYY-MM-DD, DD/MM/YYYY, MM/DD/YYYY, DD-MM-YYYY,
                       DD Mon YYYY, DD Month YYYY, YYYY/MM/DD.

Currency values may include R, $, £ and thousands commas — all stripped.
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
import csv, io
from datetime import datetime

from database import (
    get_db, Customer, Supplier, Invoice, Expense, InvoiceStatus,
)
from auth import require_role

router = APIRouter()


# ── Column alias maps ─────────────────────────────────────────────────────────
# Each field maps to every recognised column header (lowercased, spaces→_).

def _norm(s: str) -> str:
    return s.strip().lower().replace(" ", "_").replace("-", "_").replace("/", "_")


CUSTOMER_ALIASES: dict[str, list[str]] = {
    "name":          ["name", "contact_name", "contactname", "customer", "company",
                      "company_name", "client", "client_name", "account_name",
                      "full_name", "display_name"],
    "email":         ["email", "email_address", "emailaddress", "contact_email",
                      "e_mail", "e-mail"],
    "phone":         ["phone", "phone_number", "phonenumber", "telephone",
                      "mobile", "cell", "work_phone", "home_phone"],
    "address":       ["address", "postal_address", "postaladdress", "billing_address",
                      "billingaddress", "street_address", "postal_address_1",
                      "billing_street", "mailing_address"],
    "vat_number":    ["vat_number", "vat", "tax_number", "taxnumber", "tax_id",
                      "taxid", "vat_reg", "vat_registration"],
    "payment_terms": ["payment_terms", "paymentterms", "terms", "credit_terms",
                      "days", "net_days"],
    "notes":         ["notes", "memo", "comments", "remarks"],
}

SUPPLIER_ALIASES: dict[str, list[str]] = {
    "name":          ["name", "supplier", "vendor", "contact_name", "contactname",
                      "company", "company_name", "payee", "account_name"],
    "email":         ["email", "email_address", "emailaddress", "contact_email"],
    "phone":         ["phone", "phone_number", "telephone", "mobile"],
    "address":       ["address", "postal_address", "billing_address",
                      "postal_address_1", "street_address"],
    "vat_number":    ["vat_number", "vat", "tax_number", "tax_id", "taxid"],
    "bank_name":     ["bank_name", "bank", "bank_institution", "financial_institution"],
    "account_number":["account_number", "account_no", "acc_number", "bank_account",
                      "account"],
    "branch_code":   ["branch_code", "branch", "sort_code", "routing_number",
                      "bsb", "bsb_number"],
    "account_type":  ["account_type", "acc_type", "account_kind"],
    "payment_terms": ["payment_terms", "paymentterms", "terms", "credit_terms",
                      "days", "net_days"],
    "notes":         ["notes", "memo", "comments"],
}

INVOICE_ALIASES: dict[str, list[str]] = {
    "invoice_number": ["invoice_number", "invoiceno", "invoice_no", "invoicenumber",
                       "number", "ref", "reference", "num", "doc_number",
                       "document_number", "transaction_number"],
    "client_name":    ["client_name", "contact_name", "contactname", "customer",
                       "client", "company", "bill_to", "billed_to",
                       "customer_name"],
    "client_email":   ["client_email", "email", "contact_email", "customer_email"],
    "description":    ["description", "memo", "notes", "line_description",
                       "item_description", "details", "particulars"],
    "amount":         ["amount", "subtotal", "net_amount", "excl_vat", "excl",
                       "net", "line_amount", "subtotal_amount"],
    "vat_amount":     ["vat_amount", "vat", "tax", "tax_amount", "totaltax",
                       "total_tax", "gst", "gst_amount"],
    "total_amount":   ["total_amount", "total", "gross", "incl_vat", "amount_due",
                       "grand_total", "invoice_total", "balance_due"],
    "currency":       ["currency", "currency_code", "currencycode"],
    "issue_date":     ["issue_date", "issuedate", "date", "invoice_date",
                       "invoicedate", "created_date", "sent_date", "transaction_date"],
    "due_date":       ["due_date", "duedate", "payment_due", "due",
                       "due_by", "payment_date"],
    "status":         ["status", "invoice_status", "invoicestatus", "state"],
}

EXPENSE_ALIASES: dict[str, list[str]] = {
    "vendor":        ["vendor", "supplier", "payee", "contact_name", "contactname",
                      "merchant", "paid_to", "from", "account"],
    "description":   ["description", "memo", "notes", "details",
                      "line_description", "narration", "particulars"],
    "amount":        ["amount", "subtotal", "net_amount", "excl_vat", "net",
                      "excl", "line_amount"],
    "vat_amount":    ["vat_amount", "vat", "tax", "tax_amount", "totaltax",
                      "total_tax", "gst"],
    "category":      ["category", "account", "account_name", "expense_type",
                      "type", "expense_category", "chart_of_account"],
    "expense_date":  ["expense_date", "date", "transaction_date",
                      "created_date", "invoice_date", "bill_date"],
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _map_headers(headers: list[str], aliases: dict) -> dict[str, int]:
    """Return {field: column_index} for every field we can match in headers."""
    normed = [_norm(h) for h in headers]
    mapping: dict[str, int] = {}
    for field, alts in aliases.items():
        for i, h in enumerate(normed):
            if h in alts:
                mapping[field] = i
                break
    return mapping


def _get(row: list[str], mapping: dict, field: str, default: str = "") -> str:
    idx = mapping.get(field)
    if idx is None or idx >= len(row):
        return default
    return row[idx].strip()


def _parse_date(s: str) -> Optional[datetime]:
    if not s or not s.strip():
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y",
                "%d %b %Y", "%d %B %Y", "%Y/%m/%d", "%d %b %Y",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


def _parse_float(s: str) -> float:
    if not s or not s.strip():
        return 0.0
    cleaned = (
        s.strip()
        .replace(",", "")
        .replace("R", "").replace("r", "")
        .replace("$", "").replace("£", "").replace("€", "")
        .replace(" ", "")
        .strip()
    )
    try:
        return round(float(cleaned), 2)
    except ValueError:
        return 0.0


def _parse_status(s: str) -> InvoiceStatus:
    v = s.strip().lower() if s else ""
    if v in ("paid", "payment received", "closed"):
        return InvoiceStatus.paid
    if v in ("overdue", "past due", "late"):
        return InvoiceStatus.overdue
    if v in ("draft", "open", "voided", "void", "deleted"):
        return InvoiceStatus.draft
    # Xero uses "AUTHORISED" for sent-but-unpaid
    if v in ("authorised", "authorized", "approved", "sent",
             "submitted", "pending", "outstanding", "awaiting_payment",
             "awaiting payment"):
        return InvoiceStatus.sent
    return InvoiceStatus.sent


def _read_csv(file_bytes: bytes) -> tuple[list[str], list[list[str]]]:
    # utf-8-sig handles Excel BOM; fall back to latin-1 for Windows exports
    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = file_bytes.decode("latin-1")

    dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    reader  = csv.reader(io.StringIO(text), dialect)
    rows    = [r for r in reader if any(c.strip() for c in r)]

    if not rows:
        raise HTTPException(400, "CSV file is empty or unreadable")
    return rows[0], rows[1:]


# ── CUSTOMERS ─────────────────────────────────────────────────────────────────

@router.post("/customers")
async def import_customers(
    file: UploadFile = File(...),
    db:   Session    = Depends(get_db),
    cu               = Depends(require_role("owner", "admin", "accountant")),
):
    cid             = cu.company_id
    headers, rows   = _read_csv(await file.read())
    m               = _map_headers(headers, CUSTOMER_ALIASES)

    if "name" not in m:
        raise HTTPException(
            400,
            f"No name column found. Detected columns: {headers}. "
            "Expected one of: Name, Contact Name, Customer, Company."
        )

    imported, skipped, errors = 0, 0, []

    for i, row in enumerate(rows, start=2):
        try:
            name = _get(row, m, "name")
            if not name:
                continue

            # Skip duplicates
            if db.query(Customer).filter(
                Customer.company_id == cid, Customer.name == name
            ).first():
                skipped += 1
                errors.append({"row": i, "message": f"'{name}' already exists — skipped"})
                continue

            terms_str = _get(row, m, "payment_terms", "30")
            try:
                terms = int(float(terms_str)) if terms_str else 30
            except (ValueError, TypeError):
                terms = 30

            db.add(Customer(
                company_id    = cid,
                name          = name,
                email         = _get(row, m, "email"),
                phone         = _get(row, m, "phone"),
                address       = _get(row, m, "address"),
                vat_number    = _get(row, m, "vat_number"),
                payment_terms = terms,
                notes         = _get(row, m, "notes"),
                is_active     = True,
            ))
            imported += 1
        except Exception as e:
            errors.append({"row": i, "message": str(e)})

    db.commit()
    return {
        "entity":     "customers",
        "total_rows": len(rows),
        "imported":   imported,
        "skipped":    skipped,
        "errors":     errors,
    }


# ── SUPPLIERS ─────────────────────────────────────────────────────────────────

@router.post("/suppliers")
async def import_suppliers(
    file: UploadFile = File(...),
    db:   Session    = Depends(get_db),
    cu               = Depends(require_role("owner", "admin", "accountant")),
):
    cid           = cu.company_id
    headers, rows = _read_csv(await file.read())
    m             = _map_headers(headers, SUPPLIER_ALIASES)

    if "name" not in m:
        raise HTTPException(
            400,
            f"No name column found. Detected columns: {headers}. "
            "Expected one of: Name, Supplier, Vendor, Contact Name."
        )

    imported, skipped, errors = 0, 0, []

    for i, row in enumerate(rows, start=2):
        try:
            name = _get(row, m, "name")
            if not name:
                continue

            if db.query(Supplier).filter(
                Supplier.company_id == cid, Supplier.name == name
            ).first():
                skipped += 1
                errors.append({"row": i, "message": f"'{name}' already exists — skipped"})
                continue

            terms_str = _get(row, m, "payment_terms", "30")
            try:
                terms = int(float(terms_str)) if terms_str else 30
            except (ValueError, TypeError):
                terms = 30

            db.add(Supplier(
                company_id     = cid,
                name           = name,
                email          = _get(row, m, "email"),
                phone          = _get(row, m, "phone"),
                address        = _get(row, m, "address"),
                vat_number     = _get(row, m, "vat_number"),
                bank_name      = _get(row, m, "bank_name"),
                account_number = _get(row, m, "account_number"),
                branch_code    = _get(row, m, "branch_code"),
                account_type   = _get(row, m, "account_type"),
                payment_terms  = terms,
                notes          = _get(row, m, "notes"),
                is_active      = True,
            ))
            imported += 1
        except Exception as e:
            errors.append({"row": i, "message": str(e)})

    db.commit()
    return {
        "entity":     "suppliers",
        "total_rows": len(rows),
        "imported":   imported,
        "skipped":    skipped,
        "errors":     errors,
    }


# ── INVOICES ──────────────────────────────────────────────────────────────────

@router.post("/invoices")
async def import_invoices(
    file: UploadFile = File(...),
    db:   Session    = Depends(get_db),
    cu               = Depends(require_role("owner", "admin", "accountant")),
):
    cid           = cu.company_id
    headers, rows = _read_csv(await file.read())
    m             = _map_headers(headers, INVOICE_ALIASES)

    if "client_name" not in m:
        raise HTTPException(
            400,
            f"No client/customer column found. Detected columns: {headers}. "
            "Expected one of: Client Name, Contact Name, Customer."
        )

    # Sequence seed — find highest existing imported invoice number
    last_num = db.query(func.max(Invoice.id)).filter(Invoice.company_id == cid).scalar() or 0

    imported, errors = 0, []

    for i, row in enumerate(rows, start=2):
        try:
            client_name = _get(row, m, "client_name")
            if not client_name:
                continue

            amount     = _parse_float(_get(row, m, "amount"))
            vat_amount = _parse_float(_get(row, m, "vat_amount"))
            total_raw  = _parse_float(_get(row, m, "total_amount"))
            total      = total_raw if total_raw else round(amount + vat_amount, 2)

            inv_no = _get(row, m, "invoice_number")
            if not inv_no:
                last_num += 1
                inv_no = f"IMP-{last_num:04d}"

            issue_date = _parse_date(_get(row, m, "issue_date")) or datetime.utcnow()
            due_date   = _parse_date(_get(row, m, "due_date"))
            currency   = _get(row, m, "currency", "ZAR") or "ZAR"
            status     = _parse_status(_get(row, m, "status"))

            db.add(Invoice(
                company_id      = cid,
                invoice_number  = inv_no,
                client_name     = client_name,
                client_email    = _get(row, m, "client_email"),
                description     = _get(row, m, "description"),
                amount          = amount,
                vat_amount      = vat_amount,
                total_amount    = total,
                currency        = currency,
                exchange_rate   = 1.0,
                status          = status,
                issue_date      = issue_date,
                due_date        = due_date,
                paid_date       = issue_date if status == InvoiceStatus.paid else None,
                paid_amount_zar = total      if status == InvoiceStatus.paid else None,
            ))
            imported += 1
        except Exception as e:
            errors.append({"row": i, "message": str(e)})

    db.commit()
    return {
        "entity":     "invoices",
        "total_rows": len(rows),
        "imported":   imported,
        "skipped":    0,
        "errors":     errors,
    }


# ── EXPENSES ──────────────────────────────────────────────────────────────────

@router.post("/expenses")
async def import_expenses(
    file: UploadFile = File(...),
    db:   Session    = Depends(get_db),
    cu               = Depends(require_role("owner", "admin", "accountant")),
):
    cid           = cu.company_id
    headers, rows = _read_csv(await file.read())
    m             = _map_headers(headers, EXPENSE_ALIASES)

    if "vendor" not in m and "description" not in m and "amount" not in m:
        raise HTTPException(
            400,
            f"Could not detect any recognisable columns. Detected: {headers}. "
            "Expected at least: Vendor (or Description) and Amount."
        )

    imported, errors = 0, []

    for i, row in enumerate(rows, start=2):
        try:
            vendor = (
                _get(row, m, "vendor")
                or _get(row, m, "description")
                or "Imported"
            )
            amount = _parse_float(_get(row, m, "amount"))
            if amount == 0.0:
                errors.append({"row": i, "message": "Skipped — amount is zero or missing"})
                continue

            db.add(Expense(
                company_id   = cid,
                vendor       = vendor,
                description  = _get(row, m, "description"),
                amount       = amount,
                vat_amount   = _parse_float(_get(row, m, "vat_amount")),
                category     = _get(row, m, "category") or "Imported",
                expense_date = _parse_date(_get(row, m, "expense_date")) or datetime.utcnow(),
            ))
            imported += 1
        except Exception as e:
            errors.append({"row": i, "message": str(e)})

    db.commit()
    return {
        "entity":     "expenses",
        "total_rows": len(rows),
        "imported":   imported,
        "skipped":    0,
        "errors":     errors,
    }
