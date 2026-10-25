"""
Xero → ZuZan Migration Router
==============================
Provides guided import endpoints for each step of the Xero migration wizard.

Endpoints
---------
POST /xero/accounts           — Chart of Accounts (Xero CoA CSV export)
POST /xero/opening-balances   — Opening balances (Xero Trial Balance CSV export)
POST /xero/contacts           — Customers & Suppliers (Xero Contacts CSV export)
POST /xero/invoices           — Invoices (Xero Invoice CSV export, ACCREC + ACCPAY)
POST /xero/employees          — Employees (Xero Payroll Employee CSV export)

Contacts and invoices reuse csv_import.py logic internally; these endpoints
add Xero-specific column normalisation on top.

All endpoints return:
  { imported: int, skipped: int, errors: [str], warnings: [str] }
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import func
import csv, io, re
from datetime import datetime, date
from typing import Optional

from database import (
    get_db, CompanyAccount, Customer, Supplier, Invoice, InvoiceStatus,
    Employee, Account, AccountType, JournalEntry, JournalLine,
)
from auth import require_role

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    return s.strip().lower().replace(" ", "_").replace("-", "_").replace("/", "_")

def _parse_date(val: str) -> Optional[datetime]:
    if not val or not val.strip():
        return None
    val = val.strip()
    fmts = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y",
            "%d %b %Y", "%d %B %Y", "%Y/%m/%d", "%d %b %y"]
    for f in fmts:
        try:
            return datetime.strptime(val, f)
        except ValueError:
            pass
    return None

def _parse_money(val: str) -> float:
    if not val or not val.strip():
        return 0.0
    cleaned = re.sub(r"[R$£€,\s]", "", val.strip())
    try:
        return float(cleaned)
    except ValueError:
        return 0.0

def _parse_csv(content: bytes) -> list[dict]:
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for row in reader:
        rows.append({_norm(k): (v.strip() if v else "") for k, v in row.items()})
    return rows

def _get_col(row: dict, *aliases) -> str:
    for a in aliases:
        v = row.get(_norm(a), "")
        if v:
            return v
    return ""

# Xero account type → ZuZan group + normal side
XERO_TYPE_MAP = {
    "bank":        ("Assets",        "Debit"),
    "current":     ("Assets",        "Debit"),
    "fixed":       ("Assets",        "Debit"),
    "otherasset":  ("Assets",        "Debit"),
    "prepayment":  ("Assets",        "Debit"),
    "inventory":   ("Assets",        "Debit"),
    "liability":   ("Liabilities",   "Credit"),
    "currliab":    ("Liabilities",   "Credit"),
    "termliab":    ("Liabilities",   "Credit"),
    "otherliaility":("Liabilities",  "Credit"),
    "equity":      ("Equity",        "Credit"),
    "revenue":     ("Income",        "Credit"),
    "sales":       ("Income",        "Credit"),
    "otherincome": ("Income",        "Credit"),
    "directcosts": ("Cost of Sales", "Debit"),
    "overheads":   ("Expenses",      "Debit"),
    "expense":     ("Expenses",      "Debit"),
    "depreciatn":  ("Expenses",      "Debit"),
    "otherexpense":("Expenses",      "Debit"),
}


# ─────────────────────────────────────────────────────────────────────────────
# 1. Chart of Accounts
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/xero/accounts")
async def import_xero_accounts(
    file: UploadFile = File(...),
    current_user=Depends(require_role(["owner","admin","accountant"])),
    db: Session = Depends(get_db),
):
    """
    Accepts Xero's Chart of Accounts CSV export.
    Expected columns: Code, Name, Type, Tax Code, Description
    """
    content = await file.read()
    rows = _parse_csv(content)
    if not rows:
        raise HTTPException(400, "Empty or unreadable CSV file.")

    company_id = current_user.company_id
    imported = skipped = 0
    errors = []
    warnings = []

    # Load existing codes to avoid duplicates
    existing_codes = {
        r.code for r in db.query(CompanyAccount.code)
        .filter(CompanyAccount.company_id == company_id, CompanyAccount.is_deleted == False)
    }

    for i, row in enumerate(rows, 1):
        code = _get_col(row, "code", "account_code", "account code")
        name = _get_col(row, "name", "account_name", "account name", "description")
        xtype = _get_col(row, "type", "account_type", "account type").lower().replace(" ", "").replace("_", "")
        desc  = _get_col(row, "description", "notes")

        if not code or not name:
            skipped += 1
            continue

        if code in existing_codes:
            warnings.append(f"Row {i}: account code {code} already exists — skipped.")
            skipped += 1
            continue

        group, normal = XERO_TYPE_MAP.get(xtype, ("Expenses", "Debit"))

        db.add(CompanyAccount(
            company_id  = company_id,
            code        = code,
            name        = name,
            type        = "Detail",
            group       = group,
            normal      = normal,
            description = desc,
        ))
        existing_codes.add(code)
        imported += 1

    db.commit()
    return {"imported": imported, "skipped": skipped, "errors": errors, "warnings": warnings}


# ─────────────────────────────────────────────────────────────────────────────
# 2. Opening Balances (Trial Balance)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/xero/opening-balances")
async def import_xero_opening_balances(
    file: UploadFile = File(...),
    current_user=Depends(require_role(["owner","admin","accountant"])),
    db: Session = Depends(get_db),
):
    """
    Accepts Xero's Trial Balance CSV export.
    Expected columns: Account Code, Account Name, YTD Debit, YTD Credit  (or Debit/Credit)

    Posts a single opening-balance journal entry dated today.
    Accounts are identified by code; if a matching CompanyAccount exists its
    normal-side is used, otherwise Assets/Expenses are DR, everything else CR.
    """
    content = await file.read()
    rows = _parse_csv(content)
    if not rows:
        raise HTTPException(400, "Empty or unreadable CSV file.")

    company_id = current_user.company_id

    # Build code → group lookup from CompanyAccount
    coa = {r.code: r for r in
           db.query(CompanyAccount)
           .filter(CompanyAccount.company_id == company_id, CompanyAccount.is_deleted == False)}

    lines_data = []   # (account_code, account_name, amount, side)
    errors   = []
    warnings = []

    for i, row in enumerate(rows, 1):
        code  = _get_col(row, "account_code", "code", "account code")
        name  = _get_col(row, "account_name", "name", "account", "account name")
        ytd_dr = _parse_money(_get_col(row, "ytd_debit",  "debit",  "dr", "balance_debit"))
        ytd_cr = _parse_money(_get_col(row, "ytd_credit", "credit", "cr", "balance_credit"))
        net    = _parse_money(_get_col(row, "net_movement", "net", "balance", "closing_balance", "closing balance"))

        if not name and not code:
            skipped_row = True
            continue

        # Determine net amount and natural side
        if ytd_dr or ytd_cr:
            amount = ytd_dr - ytd_cr   # positive = net debit
        elif net:
            amount = net
        else:
            continue

        if abs(amount) < 0.01:
            continue

        if amount > 0:
            side = "DR"
        else:
            side = "CR"
            amount = abs(amount)

        lines_data.append((code or name, name or code, amount, side))

    if not lines_data:
        return {"imported": 0, "skipped": 0, "errors": ["No non-zero balance lines found."], "warnings": warnings}

    # Create the opening-balance journal entry
    je = JournalEntry(
        company_id  = company_id,
        entry_date  = datetime.utcnow(),
        description = "Opening balances — migrated from Xero",
        reference   = "XERO-OB",
        source      = "xero_migration",
    )
    db.add(je)
    db.flush()

    # Fetch the suspense / retained earnings account code (3000)
    total_dr = sum(a for _, _, a, s in lines_data if s == "DR")
    total_cr = sum(a for _, _, a, s in lines_data if s == "CR")
    diff = round(total_dr - total_cr, 2)

    for code, name, amount, side in lines_data:
        db.add(JournalLine(
            journal_entry_id = je.id,
            account_code     = code,
            account_name     = name,
            debit            = amount if side == "DR" else 0,
            credit           = amount if side == "CR" else 0,
            description      = "Opening balance",
        ))

    # Balance the entry via retained earnings / equity if it doesn't balance
    if abs(diff) > 0.01:
        warnings.append(
            f"Trial balance is out by R{diff:,.2f} — difference posted to account 3000 (Retained Earnings)."
        )
        db.add(JournalLine(
            journal_entry_id = je.id,
            account_code     = "3000",
            account_name     = "Retained Earnings",
            debit            = -diff if diff < 0 else 0,
            credit           = diff  if diff > 0 else 0,
            description      = "Opening balance plug",
        ))

    db.commit()
    return {
        "imported": len(lines_data),
        "skipped":  0,
        "errors":   errors,
        "warnings": warnings,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. Contacts  (Customers + Suppliers)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/xero/contacts")
async def import_xero_contacts(
    file: UploadFile = File(...),
    current_user=Depends(require_role(["owner","admin","accountant"])),
    db: Session = Depends(get_db),
):
    """
    Accepts Xero's Contacts CSV export.
    Contacts with IsSupplier=TRUE → Supplier, others → Customer.
    If both flags are true the contact is imported as both.
    """
    content = await file.read()
    rows = _parse_csv(content)
    if not rows:
        raise HTTPException(400, "Empty or unreadable CSV file.")

    company_id = current_user.company_id
    cust_imported = cust_skipped = sup_imported = sup_skipped = 0
    errors = []

    existing_cust_names = {
        r.name.lower() for r in
        db.query(Customer.name).filter(Customer.company_id == company_id)
    }
    existing_sup_names = {
        r.name.lower() for r in
        db.query(Supplier.name).filter(Supplier.company_id == company_id)
    }

    for i, row in enumerate(rows, 1):
        name    = _get_col(row, "name", "contact_name", "contactname", "company_name", "display_name")
        email   = _get_col(row, "email_address", "email", "emailaddress")
        phone   = _get_col(row, "phone", "phone_number", "phonenumber", "telephone")
        contact = _get_col(row, "first_name", "firstname") + " " + _get_col(row, "last_name", "lastname")
        contact = contact.strip()
        address = " ".join(filter(None, [
            _get_col(row, "postal_address_line_1", "poaddressline1", "street", "address_line_1"),
            _get_col(row, "postal_city", "city"),
            _get_col(row, "postal_region", "region", "province"),
            _get_col(row, "postal_postal_code", "postal_code", "postalcode", "zip"),
        ]))
        vat     = _get_col(row, "tax_number", "vat_number", "vatnumber", "tax_number")
        is_cust = _get_col(row, "is_customer", "iscustomer", "customer").lower() not in ("false","no","0","")
        is_sup  = _get_col(row, "is_supplier", "issupplier", "supplier").lower() in ("true","yes","1")

        # If neither flag set, default to customer
        if not is_sup and not is_cust:
            is_cust = True

        if not name:
            errors.append(f"Row {i}: no name — skipped.")
            continue

        # Customer
        if is_cust:
            if name.lower() in existing_cust_names:
                cust_skipped += 1
            else:
                db.add(Customer(
                    company_id     = company_id,
                    name           = name,
                    email          = email,
                    phone          = phone,
                    contact_person = contact or None,
                    address        = address or None,
                    vat_number     = vat or None,
                ))
                existing_cust_names.add(name.lower())
                cust_imported += 1

        # Supplier
        if is_sup:
            if name.lower() in existing_sup_names:
                sup_skipped += 1
            else:
                db.add(Supplier(
                    company_id     = company_id,
                    name           = name,
                    email          = email,
                    phone          = phone,
                    contact_person = contact or None,
                    address        = address or None,
                    vat_number     = vat or None,
                ))
                existing_sup_names.add(name.lower())
                sup_imported += 1

    db.commit()
    return {
        "imported": cust_imported + sup_imported,
        "skipped":  cust_skipped  + sup_skipped,
        "errors":   errors,
        "warnings": [
            f"Customers imported: {cust_imported} (skipped: {cust_skipped})",
            f"Suppliers imported: {sup_imported} (skipped: {sup_skipped})",
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. Invoices  (ACCREC = sales invoices, ACCPAY = bills → expenses)
# ─────────────────────────────────────────────────────────────────────────────

def _next_inv_number(db: Session, company_id: int) -> str:
    from sqlalchemy import func as sf
    row = db.query(sf.max(Invoice.invoice_number)).filter(
        Invoice.company_id == company_id
    ).scalar()
    if not row:
        return "INV-0001"
    m = re.search(r"(\d+)$", str(row))
    n = (int(m.group(1)) + 1) if m else 1
    return f"INV-{n:04d}"

@router.post("/xero/invoices")
async def import_xero_invoices(
    file: UploadFile = File(...),
    current_user=Depends(require_role(["owner","admin","accountant"])),
    db: Session = Depends(get_db),
):
    """
    Accepts Xero's Invoice CSV export.
    Key columns: ContactName, InvoiceNumber, InvoiceDate, DueDate,
                 Description, Quantity, UnitAmount, TaxType, TaxAmount,
                 Currency, Type (ACCREC|ACCPAY), Status
    ACCREC → Invoice (sales), ACCPAY → Expense (creditor bill).
    """
    content = await file.read()
    rows = _parse_csv(content)
    if not rows:
        raise HTTPException(400, "Empty or unreadable CSV file.")

    company_id = current_user.company_id
    inv_counter = _next_inv_number(db, company_id)
    imported = skipped = 0
    errors = []
    warnings = []

    # Group rows by InvoiceNumber (multi-line items)
    grouped: dict[str, list] = {}
    ungrouped = []
    for row in rows:
        inv_no = _get_col(row, "invoice_number", "invoicenumber", "reference", "invoice_no")
        if inv_no:
            grouped.setdefault(inv_no, []).append(row)
        else:
            ungrouped.append(row)

    # Also treat ungrouped as individual single-line invoices
    all_groups = list(grouped.values()) + [[r] for r in ungrouped]

    for group in all_groups:
        first = group[0]
        client  = _get_col(first, "contact_name", "contactname", "customer", "supplier", "name")
        inv_no  = _get_col(first, "invoice_number", "invoicenumber", "reference", "invoice_no")
        itype   = _get_col(first, "type", "invoice_type", "invoicetype").upper()
        status  = _get_col(first, "status", "invoice_status").lower()
        idate   = _parse_date(_get_col(first, "invoice_date", "invoicedate", "date", "issue_date"))
        ddate   = _parse_date(_get_col(first, "due_date", "duedate", "due"))
        pdate   = _parse_date(_get_col(first, "fully_paid_on_date", "paid_date", "payment_date"))
        currency= _get_col(first, "currency", "currencycode") or "ZAR"
        ex_rate = float(_get_col(first, "currency_rate", "exchange_rate") or 1) or 1

        if not client:
            skipped += 1
            continue

        # Aggregate line amounts
        subtotal = 0.0
        vat_total = 0.0
        items = []
        for line in group:
            qty   = float(_get_col(line, "quantity", "qty") or 1)
            price = _parse_money(_get_col(line, "unit_amount", "unitamount", "unit_price", "price", "amount"))
            disc  = float(_get_col(line, "discount", "discount_rate") or 0) / 100
            tax   = _parse_money(_get_col(line, "tax_amount", "taxamount", "vat_amount"))
            desc  = _get_col(line, "description", "item_description", "line_description")
            line_total = qty * price * (1 - disc)
            subtotal  += line_total
            vat_total += tax
            if desc or price:
                items.append({
                    "description": desc,
                    "quantity":    qty,
                    "unit_price":  price,
                    "vat_amount":  tax,
                    "total":       line_total + tax,
                })

        total = round(subtotal + vat_total, 2)
        if total == 0:
            skipped += 1
            continue

        # Map status
        if status in ("paid", "authorised") and pdate:
            zstatus = InvoiceStatus.paid
        elif status in ("voided", "void"):
            zstatus = InvoiceStatus.written_off
        elif status in ("draft", "submitted"):
            zstatus = InvoiceStatus.draft
        else:
            zstatus = InvoiceStatus.sent

        # Use existing inv number or generate
        used_no = inv_no or inv_counter
        if not inv_no:
            m = re.search(r"(\d+)$", inv_counter)
            n = int(m.group(1)) + 1 if m else 1
            inv_counter = f"INV-{n:04d}"

        import json as _json
        db.add(Invoice(
            company_id     = company_id,
            invoice_number = used_no,
            client_name    = client,
            description    = items[0]["description"] if items else "",
            amount         = round(subtotal, 2),
            vat_amount     = round(vat_total, 2),
            total_amount   = total,
            currency       = currency,
            exchange_rate  = ex_rate,
            status         = zstatus,
            issue_date     = idate or datetime.utcnow(),
            due_date       = ddate,
            paid_date      = pdate if zstatus == InvoiceStatus.paid else None,
            paid_amount_zar= total if zstatus == InvoiceStatus.paid else None,
            items_json     = _json.dumps(items) if len(items) > 1 else None,
        ))
        imported += 1

    db.commit()
    return {"imported": imported, "skipped": skipped, "errors": errors, "warnings": warnings}


# ─────────────────────────────────────────────────────────────────────────────
# 5. Employees
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/xero/employees")
async def import_xero_employees(
    file: UploadFile = File(...),
    current_user=Depends(require_role(["owner","admin","accountant"])),
    db: Session = Depends(get_db),
):
    """
    Accepts Xero Payroll Employee export CSV.
    Key columns: First Name, Last Name, Date of Birth, Email,
                 Phone, Start Date, Pay Rate, Job Title/Classification.
    """
    content = await file.read()
    rows = _parse_csv(content)
    if not rows:
        raise HTTPException(400, "Empty or unreadable CSV file.")

    company_id = current_user.company_id
    imported = skipped = 0
    errors = []

    # Build set of existing employee names
    existing = {
        f"{r.first_name} {r.last_name}".lower()
        for r in db.query(Employee.first_name, Employee.last_name)
        .filter(Employee.company_id == company_id)
    }

    # Get next employee number
    max_no = db.query(func.max(Employee.employee_number)).filter(
        Employee.company_id == company_id
    ).scalar()
    try:
        next_no = int(re.sub(r"\D", "", str(max_no or "0"))) + 1
    except:
        next_no = 1

    for i, row in enumerate(rows, 1):
        first = _get_col(row, "first_name", "firstname", "given_name")
        last  = _get_col(row, "last_name", "lastname", "surname", "family_name")
        if not first and not last:
            full = _get_col(row, "name", "employee_name", "full_name")
            parts = full.split(" ", 1)
            first = parts[0]
            last  = parts[1] if len(parts) > 1 else ""

        if not first:
            errors.append(f"Row {i}: no name — skipped.")
            skipped += 1
            continue

        key = f"{first} {last}".lower()
        if key in existing:
            skipped += 1
            continue

        dob   = _parse_date(_get_col(row, "date_of_birth", "dateofbirth", "dob", "birth_date"))
        email = _get_col(row, "email", "email_address", "emailaddress")
        phone = _get_col(row, "phone", "phone_number", "mobile")
        addr  = _get_col(row, "address", "street_address", "home_address",
                         "address_line_1", "addressline1")
        city  = _get_col(row, "city", "suburb", "town")
        start = _parse_date(_get_col(row, "start_date", "startdate", "employment_start_date"))
        pos   = _get_col(row, "job_title", "jobtitle", "classification", "position",
                         "title", "role", "occupation")
        dept  = _get_col(row, "department", "dept", "cost_centre")
        tax_no= _get_col(row, "tax_number", "taxnumber", "income_tax_number", "tax_file_number")
        id_no = _get_col(row, "id_number", "idnumber", "national_id", "national_insurance_number")
        salary_str = _get_col(row, "pay_rate", "payrate", "salary", "annual_salary",
                               "hourly_rate", "basic_salary")
        salary = _parse_money(salary_str)

        db.add(Employee(
            company_id        = company_id,
            employee_number   = f"EMP{next_no:04d}",
            first_name        = first,
            last_name         = last,
            id_number         = id_no or None,
            tax_number        = tax_no or None,
            date_of_birth     = dob,
            appointment_date  = start,
            address           = " ".join(filter(None, [addr, city])) or None,
            position          = pos or None,
            department        = dept or None,
            basic_salary      = salary or 0,
            employment_type   = "permanent",
        ))
        existing.add(key)
        next_no += 1
        imported += 1

    db.commit()
    return {"imported": imported, "skipped": skipped, "errors": errors, "warnings": []}
