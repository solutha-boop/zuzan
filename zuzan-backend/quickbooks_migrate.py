"""
QuickBooks Online → ZuZan Migration Router
==========================================
Accepts QBO CSV / Excel exports and imports them into ZuZan.

Endpoints (prefix /qbo)
-----------------------
POST /qbo/accounts           — Chart of Accounts (QBO CoA CSV export)
POST /qbo/opening-balances   — Opening balances (QBO Trial Balance report CSV)
POST /qbo/customers          — Customers (QBO Customer Contact List CSV)
POST /qbo/vendors            — Vendors / Suppliers (QBO Vendor Contact List CSV)
POST /qbo/invoices           — Invoices & Bills (QBO Invoice / Bill CSV export)
POST /qbo/employees          — Employees (QBO Employee Contact List CSV)

All endpoints return:
  { imported: int, skipped: int, errors: [str], warnings: [str] }
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import func
import csv, io, re, json as _json
from datetime import datetime
from typing import Optional

from database import (
    get_db, CompanyAccount, Customer, Supplier, Invoice, InvoiceStatus,
    Employee, JournalEntry, JournalLine,
)
from auth import require_role

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers (shared with xero_migrate pattern)
# ─────────────────────────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    return s.strip().lower().replace(" ", "_").replace("-", "_").replace("/", "_").replace(".", "")

def _parse_date(val: str) -> Optional[datetime]:
    if not val or not val.strip():
        return None
    val = val.strip()
    for f in ["%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y",
              "%d %b %Y", "%d %B %Y", "%Y/%m/%d", "%m-%d-%Y"]:
        try:
            return datetime.strptime(val, f)
        except ValueError:
            pass
    return None

def _parse_money(val: str) -> float:
    if not val or not val.strip():
        return 0.0
    cleaned = re.sub(r"[R$£€,\s()]", "", val.strip())
    # QBO sometimes wraps negatives in parens: (1234.00)
    negative = val.strip().startswith("(")
    try:
        n = float(cleaned)
        return -n if negative else n
    except ValueError:
        return 0.0

def _parse_csv(content: bytes) -> list[dict]:
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for row in reader:
        rows.append({_norm(k): (v.strip() if v else "") for k, v in row.items()})
    return rows

def _get(row: dict, *aliases) -> str:
    for a in aliases:
        v = row.get(_norm(a), "")
        if v:
            return v
    return ""

# QBO account type → ZuZan group + normal side
QBO_TYPE_MAP = {
    # Balance Sheet — Assets
    "bank":                      ("Assets",        "Debit"),
    "accounts_receivable":       ("Assets",        "Debit"),
    "accounts_receivable_(a_r)": ("Assets",        "Debit"),
    "other_current_assets":      ("Assets",        "Debit"),
    "other_current_asset":       ("Assets",        "Debit"),
    "fixed_asset":               ("Assets",        "Debit"),
    "fixed_assets":              ("Assets",        "Debit"),
    "other_asset":               ("Assets",        "Debit"),
    "other_assets":              ("Assets",        "Debit"),
    # Balance Sheet — Liabilities
    "accounts_payable":          ("Liabilities",   "Credit"),
    "accounts_payable_(a_p)":    ("Liabilities",   "Credit"),
    "credit_card":               ("Liabilities",   "Credit"),
    "other_current_liabilities": ("Liabilities",   "Credit"),
    "other_current_liability":   ("Liabilities",   "Credit"),
    "long_term_liabilities":     ("Liabilities",   "Credit"),
    "long_term_liability":       ("Liabilities",   "Credit"),
    # Equity
    "equity":                    ("Equity",        "Credit"),
    "owners_equity":             ("Equity",        "Credit"),
    # Income
    "income":                    ("Income",        "Credit"),
    "other_income":              ("Income",        "Credit"),
    "sales":                     ("Income",        "Credit"),
    # Cost of Sales
    "cost_of_goods_sold":        ("Cost of Sales", "Debit"),
    "cost_of_sales":             ("Cost of Sales", "Debit"),
    # Expenses
    "expense":                   ("Expenses",      "Debit"),
    "expenses":                  ("Expenses",      "Debit"),
    "other_expense":             ("Expenses",      "Debit"),
    "other_expenses":            ("Expenses",      "Debit"),
}


# ─────────────────────────────────────────────────────────────────────────────
# 1. Chart of Accounts
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/qbo/accounts")
async def import_qbo_accounts(
    file: UploadFile = File(...),
    current_user=Depends(require_role(["owner","admin","accountant"])),
    db: Session = Depends(get_db),
):
    """
    QBO: Accounting → Chart of Accounts → Run Report → Export
    Columns: Account, Type, Detail Type, Description, Balance
    Also accepts: Name, Account Type, Account Number
    """
    content = await file.read()
    rows = _parse_csv(content)
    if not rows:
        raise HTTPException(400, "Empty or unreadable CSV file.")

    company_id = current_user.company_id
    existing_codes = {
        r.code for r in
        db.query(CompanyAccount.code)
        .filter(CompanyAccount.company_id == company_id, CompanyAccount.is_deleted == False)
    }
    existing_names = {
        r.name.lower() for r in
        db.query(CompanyAccount.name)
        .filter(CompanyAccount.company_id == company_id, CompanyAccount.is_deleted == False)
    }

    imported = skipped = 0
    errors = []

    for i, row in enumerate(rows, 1):
        name  = _get(row, "account", "name", "account_name", "accountname")
        code  = _get(row, "number", "account_number", "accountnumber", "code", "account_code")
        atype = _get(row, "type", "account_type", "accounttype").lower().replace(" ", "_").replace("(", "").replace(")", "")
        desc  = _get(row, "description", "detail_type", "detailtype", "notes")

        if not name:
            skipped += 1
            continue

        # Generate a code if missing (use name slug)
        if not code:
            code = re.sub(r"[^A-Za-z0-9]", "", name)[:8].upper()
        if not code:
            skipped += 1
            continue

        if code in existing_codes or name.lower() in existing_names:
            skipped += 1
            continue

        group, normal = QBO_TYPE_MAP.get(atype, ("Expenses", "Debit"))

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
        existing_names.add(name.lower())
        imported += 1

    db.commit()
    return {"imported": imported, "skipped": skipped, "errors": errors, "warnings": []}


# ─────────────────────────────────────────────────────────────────────────────
# 2. Opening Balances (Trial Balance)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/qbo/opening-balances")
async def import_qbo_opening_balances(
    file: UploadFile = File(...),
    current_user=Depends(require_role(["owner","admin","accountant"])),
    db: Session = Depends(get_db),
):
    """
    QBO: Reports → Trial Balance → Export
    Columns: Account, Debit, Credit
    Also handles: Account Name, Account Code, Total
    """
    content = await file.read()
    rows = _parse_csv(content)
    if not rows:
        raise HTTPException(400, "Empty or unreadable CSV file.")

    company_id = current_user.company_id
    lines_data = []
    errors = []
    warnings = []

    for i, row in enumerate(rows, 1):
        name   = _get(row, "account", "account_name", "accountname", "name", "account_title")
        code   = _get(row, "account_code", "accountcode", "number", "code")
        debit  = _parse_money(_get(row, "debit", "dr", "debit_balance"))
        credit = _parse_money(_get(row, "credit", "cr", "credit_balance"))
        total  = _parse_money(_get(row, "total", "balance", "net", "amount"))

        if not name:
            continue

        # Compute net
        if debit or credit:
            amount = debit - credit
        elif total:
            amount = total
        else:
            continue

        if abs(amount) < 0.01:
            continue

        side = "DR" if amount > 0 else "CR"
        lines_data.append((code or name, name, abs(amount), side))

    if not lines_data:
        return {"imported": 0, "skipped": 0, "errors": ["No non-zero balance lines found."], "warnings": warnings}

    je = JournalEntry(
        company_id  = company_id,
        entry_date  = datetime.utcnow(),
        description = "Opening balances — migrated from QuickBooks",
        reference   = "QBO-OB",
        source      = "qbo_migration",
    )
    db.add(je)
    db.flush()

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

    if abs(diff) > 0.01:
        warnings.append(f"Trial balance is out by R{diff:,.2f} — plugged to account 3000 (Retained Earnings).")
        db.add(JournalLine(
            journal_entry_id = je.id,
            account_code     = "3000",
            account_name     = "Retained Earnings",
            debit            = -diff if diff < 0 else 0,
            credit           = diff  if diff > 0 else 0,
            description      = "Opening balance plug",
        ))

    db.commit()
    return {"imported": len(lines_data), "skipped": 0, "errors": errors, "warnings": warnings}


# ─────────────────────────────────────────────────────────────────────────────
# 3. Customers
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/qbo/customers")
async def import_qbo_customers(
    file: UploadFile = File(...),
    current_user=Depends(require_role(["owner","admin","accountant"])),
    db: Session = Depends(get_db),
):
    """
    QBO: Sales → Customers → Export → Customer Contact List
    Columns: Customer, Company, Email, Phone, Mobile, Street, City, State/Province,
             ZIP, Country, Tax Reg. No., Balance, Open Balance
    """
    content = await file.read()
    rows = _parse_csv(content)
    if not rows:
        raise HTTPException(400, "Empty or unreadable CSV file.")

    company_id = current_user.company_id
    existing = {
        r.name.lower() for r in
        db.query(Customer.name).filter(Customer.company_id == company_id)
    }
    imported = skipped = 0
    errors = []

    for i, row in enumerate(rows, 1):
        # QBO has both "Customer" (display name) and "Company"
        display = _get(row, "customer", "display_name", "displayname", "display_name_as", "name", "full_name")
        company = _get(row, "company", "company_name")
        name = display or company
        if not name:
            errors.append(f"Row {i}: no name — skipped.")
            continue

        if name.lower() in existing:
            skipped += 1
            continue

        email   = _get(row, "email", "email_address", "emailaddress", "primary_email_addr")
        phone   = _get(row, "phone", "main_phone", "mainphone", "primary_phone", "mobile")
        contact = display if company else ""
        street  = _get(row, "street", "billing_address_street", "billing_street", "address_line_1")
        city    = _get(row, "city", "billing_address_city", "billing_city")
        state   = _get(row, "state_province", "state", "billing_address_state", "billing_state", "province")
        zcode   = _get(row, "zip_postal_code", "zip", "postal_code", "postalcode")
        country = _get(row, "country", "billing_address_country")
        vat     = _get(row, "tax_reg_no", "taxregno", "vat_number", "vatnumber", "gst_number", "tax_number")
        addr    = ", ".join(filter(None, [street, city, state, zcode, country]))

        db.add(Customer(
            company_id     = company_id,
            name           = name,
            email          = email or None,
            phone          = phone or None,
            contact_person = (contact or None),
            address        = addr or None,
            vat_number     = vat or None,
        ))
        existing.add(name.lower())
        imported += 1

    db.commit()
    return {"imported": imported, "skipped": skipped, "errors": errors, "warnings": []}


# ─────────────────────────────────────────────────────────────────────────────
# 4. Vendors (Suppliers)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/qbo/vendors")
async def import_qbo_vendors(
    file: UploadFile = File(...),
    current_user=Depends(require_role(["owner","admin","accountant"])),
    db: Session = Depends(get_db),
):
    """
    QBO: Expenses → Vendors → Export → Vendor Contact List
    Columns: Vendor, Company, Email, Phone, Street, City, State, ZIP, Country,
             Tax Reg. No., Account No.
    """
    content = await file.read()
    rows = _parse_csv(content)
    if not rows:
        raise HTTPException(400, "Empty or unreadable CSV file.")

    company_id = current_user.company_id
    existing = {
        r.name.lower() for r in
        db.query(Supplier.name).filter(Supplier.company_id == company_id)
    }
    imported = skipped = 0
    errors = []

    for i, row in enumerate(rows, 1):
        display = _get(row, "vendor", "display_name", "displayname", "name", "full_name", "supplier")
        company = _get(row, "company", "company_name")
        name = display or company
        if not name:
            errors.append(f"Row {i}: no name — skipped.")
            continue

        if name.lower() in existing:
            skipped += 1
            continue

        email   = _get(row, "email", "email_address", "primary_email_addr")
        phone   = _get(row, "phone", "main_phone", "primary_phone", "telephone", "mobile")
        street  = _get(row, "street", "billing_address_street", "address_line_1", "address")
        city    = _get(row, "city", "billing_address_city")
        state   = _get(row, "state_province", "state", "province")
        zcode   = _get(row, "zip_postal_code", "zip", "postal_code")
        country = _get(row, "country")
        vat     = _get(row, "tax_reg_no", "taxregno", "vat_number", "tax_number", "gst_number")
        addr    = ", ".join(filter(None, [street, city, state, zcode, country]))

        db.add(Supplier(
            company_id     = company_id,
            name           = name,
            email          = email or None,
            phone          = phone or None,
            contact_person = (display if company else None),
            address        = addr or None,
            vat_number     = vat or None,
        ))
        existing.add(name.lower())
        imported += 1

    db.commit()
    return {"imported": imported, "skipped": skipped, "errors": errors, "warnings": []}


# ─────────────────────────────────────────────────────────────────────────────
# 5. Invoices & Bills
# ─────────────────────────────────────────────────────────────────────────────

def _next_inv_number(db: Session, company_id: int) -> str:
    row = db.query(func.max(Invoice.invoice_number)).filter(
        Invoice.company_id == company_id
    ).scalar()
    if not row:
        return "INV-0001"
    m = re.search(r"(\d+)$", str(row))
    n = (int(m.group(1)) + 1) if m else 1
    return f"INV-{n:04d}"

@router.post("/qbo/invoices")
async def import_qbo_invoices(
    file: UploadFile = File(...),
    current_user=Depends(require_role(["owner","admin","accountant"])),
    db: Session = Depends(get_db),
):
    """
    QBO: Sales → Invoices → Export  (or  Expenses → Bills → Export)
    Invoice columns: Invoice No., Customer, P.O. No., Invoice Date, Due Date,
                     Terms, Status, Amount, Balance Due, Memo
    Bill columns:    Bill No., Vendor, Bill Date, Due Date, Status, Amount, Balance Due

    Invoices (customer-facing) → ZuZan Invoice
    Bills (vendor-facing) → also imported as ZuZan Invoice with client = vendor name
    """
    content = await file.read()
    rows = _parse_csv(content)
    if not rows:
        raise HTTPException(400, "Empty or unreadable CSV file.")

    company_id = current_user.company_id
    inv_counter = _next_inv_number(db, company_id)
    imported = skipped = 0
    errors = []

    # Group multi-line rows by invoice/bill number
    grouped: dict[str, list] = {}
    ungrouped = []
    for row in rows:
        no = _get(row, "invoice_no", "invoiceno", "invoice_number", "num",
                  "bill_no", "billno", "bill_number", "ref_no", "refno", "transaction_no")
        if no:
            grouped.setdefault(no, []).append(row)
        else:
            ungrouped.append(row)

    all_groups = list(grouped.values()) + [[r] for r in ungrouped]

    for group in all_groups:
        first = group[0]
        client = _get(first, "customer", "client", "customer_name",
                      "vendor", "vendor_name", "supplier", "name")
        inv_no  = _get(first, "invoice_no", "invoiceno", "num", "invoice_number",
                       "bill_no", "billno", "bill_number", "ref_no")
        status  = _get(first, "status", "invoice_status", "bill_status").lower()
        idate   = _parse_date(_get(first, "invoice_date", "invoicedate", "date",
                                   "bill_date", "billdate", "txn_date"))
        ddate   = _parse_date(_get(first, "due_date", "duedate", "terms_due_date"))
        pdate   = _parse_date(_get(first, "closed_date", "paid_date", "payment_date"))
        memo    = _get(first, "memo", "description", "message", "notes", "item_description")
        currency = _get(first, "currency", "currency_code") or "ZAR"

        if not client:
            skipped += 1
            continue

        # Aggregate line amounts
        subtotal  = 0.0
        vat_total = 0.0
        items = []
        for line in group:
            # QBO uses "Amount" for line total; tax handled separately
            amount   = _parse_money(_get(line, "amount", "line_amount", "total_amount",
                                         "subtotal", "sales_amount"))
            tax      = _parse_money(_get(line, "tax_amount", "taxamount", "gst_amount",
                                         "vat_amount", "tax"))
            desc     = _get(line, "description", "memo", "product_service",
                            "item_description", "service_description", "line_description")
            qty      = float(_get(line, "qty", "quantity") or 1)
            unit     = _parse_money(_get(line, "rate", "unit_price", "unit_amount", "price"))
            if unit and qty:
                line_sub = unit * qty
            else:
                line_sub = amount - tax
            subtotal  += line_sub
            vat_total += tax
            if desc or amount:
                items.append({
                    "description": desc or memo,
                    "quantity":    qty,
                    "unit_price":  unit or (line_sub / qty if qty else 0),
                    "vat_amount":  tax,
                    "total":       line_sub + tax,
                })

        total = round(subtotal + vat_total, 2)
        if total == 0:
            # Try the "Amount" top-level column as a fallback
            total = _parse_money(_get(first, "amount", "total", "invoice_amount"))
            subtotal = total
        if total == 0:
            skipped += 1
            continue

        # Balance Due: if 0 → paid; if < total → partial; if = total → open
        balance_due = _parse_money(_get(first, "balance_due", "balancedue",
                                        "open_balance", "openbalance", "balance"))
        paid = total - balance_due if balance_due is not None else None

        # Status mapping
        if status in ("paid", "closed"):
            zstatus = InvoiceStatus.paid
        elif status in ("voided", "void", "deleted"):
            zstatus = InvoiceStatus.written_off
        elif status in ("draft", "pending", "not_sent"):
            zstatus = InvoiceStatus.draft
        elif status == "overdue":
            zstatus = InvoiceStatus.overdue
        else:
            zstatus = InvoiceStatus.sent

        # Override via balance
        if balance_due is not None and abs(balance_due) < 0.01 and total > 0:
            zstatus = InvoiceStatus.paid
        elif balance_due is not None and 0 < balance_due < total:
            zstatus = InvoiceStatus.partial

        used_no = inv_no or inv_counter
        if not inv_no:
            m = re.search(r"(\d+)$", inv_counter)
            n = int(m.group(1)) + 1 if m else 1
            inv_counter = f"INV-{n:04d}"

        db.add(Invoice(
            company_id     = company_id,
            invoice_number = used_no,
            client_name    = client,
            description    = (items[0]["description"] if items else memo) or "",
            amount         = round(subtotal, 2),
            vat_amount     = round(vat_total, 2),
            total_amount   = total,
            currency       = currency,
            exchange_rate  = 1.0,
            status         = zstatus,
            issue_date     = idate or datetime.utcnow(),
            due_date       = ddate,
            paid_date      = pdate if zstatus in (InvoiceStatus.paid,) else None,
            paid_amount_zar= paid if zstatus in (InvoiceStatus.paid, InvoiceStatus.partial) else None,
            items_json     = _json.dumps(items) if len(items) > 1 else None,
        ))
        imported += 1

    db.commit()
    return {"imported": imported, "skipped": skipped, "errors": errors, "warnings": []}


# ─────────────────────────────────────────────────────────────────────────────
# 6. Employees
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/qbo/employees")
async def import_qbo_employees(
    file: UploadFile = File(...),
    current_user=Depends(require_role(["owner","admin","accountant"])),
    db: Session = Depends(get_db),
):
    """
    QBO: Payroll → Employees → Export → Employee Contact List
    Columns: Employee, Email, Phone, Mobile, Street, City, State, ZIP, Country,
             Hire Date, Status, Employee Type, Billing Rate
    """
    content = await file.read()
    rows = _parse_csv(content)
    if not rows:
        raise HTTPException(400, "Empty or unreadable CSV file.")

    company_id = current_user.company_id
    existing = {
        f"{r.first_name} {r.last_name}".lower()
        for r in db.query(Employee.first_name, Employee.last_name)
        .filter(Employee.company_id == company_id)
    }
    max_no = db.query(func.max(Employee.employee_number)).filter(
        Employee.company_id == company_id
    ).scalar()
    try:
        next_no = int(re.sub(r"\D", "", str(max_no or "0"))) + 1
    except:
        next_no = 1

    imported = skipped = 0
    errors = []

    for i, row in enumerate(rows, 1):
        full  = _get(row, "employee", "name", "employee_name", "full_name", "display_name")
        first = _get(row, "first_name", "firstname", "given_name")
        last  = _get(row, "last_name",  "lastname",  "surname", "family_name")

        if full and not first:
            parts = full.strip().split(" ", 1)
            first = parts[0]
            last  = parts[1] if len(parts) > 1 else ""

        if not first:
            errors.append(f"Row {i}: no employee name — skipped.")
            skipped += 1
            continue

        key = f"{first} {last}".lower()
        if key in existing:
            skipped += 1
            continue

        email  = _get(row, "email", "email_address", "work_email", "primary_email")
        phone  = _get(row, "phone", "main_phone", "mobile", "work_phone")
        street = _get(row, "street", "address", "home_address_street")
        city   = _get(row, "city", "home_address_city")
        state  = _get(row, "state_province", "state", "home_address_state", "province")
        start  = _parse_date(_get(row, "hire_date", "hiredate", "start_date", "employment_date"))
        pos    = _get(row, "employee_type", "job_title", "jobtitle", "title", "designation",
                      "classification", "occupation")
        dept   = _get(row, "department", "dept", "cost_centre")
        rate   = _parse_money(_get(row, "billing_rate", "billingrate", "hourly_rate",
                                   "salary", "pay_rate", "gross_salary"))
        addr   = ", ".join(filter(None, [street, city, state]))

        db.add(Employee(
            company_id       = company_id,
            employee_number  = f"EMP{next_no:04d}",
            first_name       = first,
            last_name        = last,
            appointment_date = start,
            address          = addr or None,
            position         = pos or None,
            department       = dept or None,
            basic_salary     = rate or 0,
            employment_type  = "salaried" if rate and rate > 500 else "hourly",
        ))
        existing.add(key)
        next_no += 1
        imported += 1

    db.commit()
    return {"imported": imported, "skipped": skipped, "errors": errors, "warnings": []}
