"""
Xero -> ZuZan migration wizard (routes mounted under /xero).

Every step is a thin ADAPTER: it reads the Xero export (CSV or Excel), renames/reshapes the columns, and hands the
result to the importers in csv_import.py - the same, tested code the Import screens use. That keeps the rules the same
everywhere: duplicate invoices are refused, foreign currency needs a rate, opening balances post to the real ledger and
can be re-run safely, imported invoices/expenses are posted to the journal, and so on.

POST /xero/accounts           Chart of accounts (Xero "Chart of Accounts" export)
POST /xero/opening-balances   Trial balance (Xero "Trial Balance" export)         ?as_at=YYYY-MM-DD&replace=false
POST /xero/contacts           Customers and suppliers (Xero contacts export)
POST /xero/invoices           Sales invoices (ACCREC) and supplier bills (ACCPAY -> expenses)
POST /xero/employees          Employees

All steps return { imported, skipped, errors: [str], warnings: [str] } plus a few step-specific counts.
"""
import csv, io, re
from collections import OrderedDict
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from database import get_db, Account, AccountType
from auth import require_role
import csv_import as CI

router = APIRouter()

MAX_UPLOAD_BYTES = 10 * 1024 * 1024        # 10 MB is far more than any real export
MAX_ROWS = 50000
_ROLES = ("owner", "admin", "accountant")


# ── shared helpers (also used by quickbooks_migrate) ─────────────────────────

def key(h) -> str:
    """Header -> lookup key: '*ContactName' / 'Contact Name' / 'contact_name' all become 'contactname'."""
    return re.sub(r"[^a-z0-9]+", "", str(h or "").lower())


async def read_table(file: UploadFile) -> list[dict]:
    """The upload as a list of {header-key: value} rows (CSV or Excel). Rejects empty, huge or unreadable files."""
    content = await file.read()
    if not content or not content.strip():
        raise HTTPException(400, "The file is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "The file is too large (limit 10 MB). Export a smaller date range or split it.")
    try:
        headers, rows = CI._read_csv(content)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "Could not read this file. Export it again as CSV or Excel (.xlsx).")
    if not headers or not rows:
        raise HTTPException(400, "The file has no data rows.")
    if len(rows) > MAX_ROWS:
        raise HTTPException(413, f"Too many rows ({len(rows):,}); the limit is {MAX_ROWS:,} per file.")
    keys = [key(h) for h in headers]
    return [{k: (str(v).strip() if v is not None else "") for k, v in zip(keys, r)} for r in rows]


def pick(row: dict, *names) -> str:
    for n in names:
        v = row.get(key(n))
        if v:
            return v
    return ""


def pick_containing(row: dict, must: tuple, prefer: tuple = ()) -> str:
    """First non-empty column whose key contains every word in `must` (columns with a `prefer` word first)."""
    cols = [k for k in row if all(w in k for w in must)]
    cols.sort(key=lambda k: 0 if any(p in k for p in prefer) else 1)
    for k in cols:
        if row[k]:
            return row[k]
    return ""


def make_upload(fieldnames: list[str], rows: list[dict], filename="import.csv") -> UploadFile:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return UploadFile(file=io.BytesIO(buf.getvalue().encode("utf-8")), filename=filename)


def money(v) -> float:
    return CI._parse_float(v)


def truthy(v: str) -> bool:
    return str(v or "").strip().lower() in ("true", "yes", "y", "1")


def falsy(v: str) -> bool:
    return str(v or "").strip().lower() in ("false", "no", "n", "0")


def fmt_errors(errs) -> list[str]:
    out = []
    for e in errs or []:
        if isinstance(e, dict):
            where = f"Row {e['row']}: " if e.get("row") else ""
            out.append(where + str(e.get("message") or e.get("reason") or e))
        else:
            out.append(str(e))
    return out


def result(res: dict, warnings=None, **extra) -> dict:
    """Normalise a csv_import result (or a merged one) to the wizard's shape."""
    warns = list(warnings or [])
    if res.get("warning"):
        warns.append(res["warning"])
    out = {"imported": int(res.get("imported", 0) or 0), "skipped": int(res.get("skipped", 0) or 0),
           "errors": fmt_errors(res.get("errors")), "warnings": warns}
    out.update(extra)
    return out


def merge(*parts: dict) -> dict:
    out = {"imported": 0, "skipped": 0, "errors": [], "warnings": []}
    for p in parts:
        out["imported"] += p["imported"]; out["skipped"] += p["skipped"]
        out["errors"] += p["errors"]; out["warnings"] += p["warnings"]
    return out


def classify_account_type(type_text: str, code: str):
    """AccountType for an exported account type ('Current Asset', 'Direct Costs', 'Accounts Receivable (A/R)' ...)."""
    t = key(type_text)
    table = (
        (("prepay", "inventor", "bank", "fixedasset", "currentasset", "noncurrentasset", "otherasset", "undepositedfunds",
          "accountsreceivable", "receivable"), AccountType.asset),
        (("liabilit", "payable", "creditcard", "currliab", "termliab"), AccountType.liability),
        (("equity", "retained"), AccountType.equity),
        (("revenue", "sales", "income"), AccountType.revenue),
        (("directcost", "costofgoods", "costofsales", "cogs", "overhead", "expense", "depreciat", "cost"), AccountType.expense),
    )
    for words, typ in table:
        if any(w in t for w in words):
            return typ
    return CI._resolve_type(type_text, code)


def import_chart(db: Session, cu, rows: list[dict], code_cols, name_cols, type_cols) -> dict:
    """Create ledger accounts from an exported chart of accounts. Accounts that already exist (same code, or same
    name and kind) are left alone and counted as skipped."""
    cid = cu.company_id
    existing_ids = {r[0] for r in db.query(Account.id).filter(Account.company_id == cid).all()}
    imported = skipped = 0
    errors, warnings = [], []
    for i, row in enumerate(rows, start=2):
        code = pick(row, *code_cols)
        name = pick(row, *name_cols)
        if not name:
            continue
        atype = classify_account_type(pick(row, *type_cols), code)
        if atype is None:
            errors.append(f"Row {i}: account '{name}' - cannot tell what kind of account it is (no recognisable Type); not imported.")
            continue
        acct = CI._find_or_create_account(db, cid, code, name, atype)
        if acct.id in existing_ids:
            skipped += 1
        else:
            existing_ids.add(acct.id)
            imported += 1
    db.commit()
    return {"imported": imported, "skipped": skipped, "errors": errors, "warnings": warnings}


def invoice_total_lines(group: list[dict], qty_cols, price_cols, disc_cols, tax_cols, amount_cols=()) -> tuple[float, float]:
    """(net, vat) of one invoice from its line rows."""
    net = vat = 0.0
    for ln in group:
        qty = money(pick(ln, *qty_cols)) if pick(ln, *qty_cols) else 1.0
        price = money(pick(ln, *price_cols))
        disc = money(pick(ln, *disc_cols)) / 100.0 if disc_cols and pick(ln, *disc_cols) else 0.0
        line = round(qty * price * (1 - disc), 2) if price_cols and pick(ln, *price_cols) else money(pick(ln, *amount_cols))
        net += line
        vat += money(pick(ln, *tax_cols))
    return round(net, 2), round(vat, 2)


# ── 1. Chart of accounts ─────────────────────────────────────────────────────

@router.post("/accounts")
async def import_xero_accounts(file: UploadFile = File(...), current_user=Depends(require_role(*_ROLES)),
                               db: Session = Depends(get_db)):
    """Xero Chart of Accounts export: Code, Name, Type (Tax Code / Description are ignored)."""
    rows = await read_table(file)
    if not any(pick(r, "name", "account name") for r in rows):
        raise HTTPException(400, "No 'Name' column found. Use Accounting > Chart of Accounts > Export in Xero.")
    return result(import_chart(db, current_user, rows, ("code", "account code"), ("name", "account name"), ("type", "account type")))


# ── 2. Opening balances (trial balance) ──────────────────────────────────────

@router.post("/opening-balances")
async def import_xero_opening_balances(file: UploadFile = File(...), as_at: Optional[str] = None, replace: bool = False,
                                       current_user=Depends(require_role(*_ROLES)), db: Session = Depends(get_db)):
    """Xero Trial Balance export. Posted as ONE opening-balance entry to the real ledger (dated `as_at`, default today);
    any difference goes to Opening Balance Equity. Sending the same kind of file twice is refused unless replace=true."""
    rows = await read_table(file)
    out = []
    for r in rows:
        name = pick(r, "account", "account name", "name")
        if not name or key(name) in ("total", "totals", "grandtotal"):
            continue                                        # skip the report's total line
        debit = pick_containing(r, ("debit",), prefer=("ytd", "yeartodate"))
        credit = pick_containing(r, ("credit",), prefer=("ytd", "yeartodate"))
        out.append({"code": pick(r, "account code", "code"), "name": name, "type": pick(r, "account type", "type"),
                    "debit": debit, "credit": credit, "balance": "" if (debit or credit) else pick(r, "balance", "closing balance", "net")})
    if not out:
        raise HTTPException(400, "No account lines found. Export the Trial Balance from Xero (Accounting > Reports > Trial Balance).")
    up = make_upload(["code", "name", "type", "debit", "credit", "balance"], out)
    return result(await CI.import_trial_balance(file=up, as_at=as_at, replace=replace, db=db, cu=current_user))


# ── 3. Contacts ──────────────────────────────────────────────────────────────

def contact_rows(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """(customers, suppliers) in csv_import's column names. IsSupplier=TRUE -> supplier; IsCustomer=TRUE (or no flag at all)
    -> customer; both flags -> both."""
    customers, suppliers = [], []
    for r in rows:
        name = pick(r, "contactname", "name", "contact name", "displayname")
        if not name:
            continue
        addr = " ".join(x for x in (pick(r, "poaddressline1", "postaladdressline1", "saaddressline1", "address", "street"),
                                    pick(r, "pocity", "postalcity", "sacity", "city"),
                                    pick(r, "poregion", "postalregion", "saregion", "region"),
                                    pick(r, "popostalcode", "postalpostalcode", "sapostalcode", "postalcode")) if x)
        rec = {"name": name, "email": pick(r, "emailaddress", "email"), "phone": pick(r, "phonenumber", "phone", "mobile", "telephone"),
               "address": addr, "vat_number": pick(r, "taxnumber", "vatnumber", "vat number")}
        is_sup, is_cust = truthy(pick(r, "issupplier")), truthy(pick(r, "iscustomer"))
        if not is_sup and not is_cust and not falsy(pick(r, "iscustomer")):
            is_cust = True
        if is_cust:
            customers.append(rec)
        if is_sup:
            suppliers.append(rec)
    return customers, suppliers


async def run_contacts(rows, current_user, db) -> dict:
    customers, suppliers = contact_rows(rows)
    if not customers and not suppliers:
        raise HTTPException(400, "No contacts found (a 'ContactName' / 'Name' column is needed).")
    fields = ["name", "email", "phone", "address", "vat_number"]
    parts, warnings = [], []
    if customers:
        res = result(await CI.import_customers(file=make_upload(fields, customers), db=db, cu=current_user))
        warnings.append(f"Customers: {res['imported']} imported, {res['skipped']} skipped")
        parts.append(res)
    if suppliers:
        res = result(await CI.import_suppliers(file=make_upload(fields, suppliers), db=db, cu=current_user))
        warnings.append(f"Suppliers: {res['imported']} imported, {res['skipped']} skipped")
        parts.append(res)
    out = merge(*parts)
    out["warnings"] = warnings + out["warnings"]
    return out


@router.post("/contacts")
async def import_xero_contacts(file: UploadFile = File(...), current_user=Depends(require_role(*_ROLES)),
                               db: Session = Depends(get_db)):
    return await run_contacts(await read_table(file), current_user, db)


# ── 4. Invoices and bills ────────────────────────────────────────────────────

def group_documents(rows: list[dict], number_cols) -> "OrderedDict[str, list[dict]]":
    """Xero/QBO exports one row per invoice LINE: gather the lines of each document (rows with no number stand alone)."""
    groups: "OrderedDict[str, list[dict]]" = OrderedDict()
    for n, r in enumerate(rows):
        num = pick(r, *number_cols)
        groups.setdefault(num or f"\0row{n}", []).append(r)
    return groups


async def run_documents(rows, current_user, db, *, number_cols, party_cols, date_cols, due_cols, status_cols, type_cols, desc_cols,
                        qty_cols, price_cols, disc_cols, tax_cols, amount_cols, total_cols, currency_cols, rate_cols,
                        bill_values, void_values, skip_status_note: str, gross_split: bool = False) -> dict:
    from journal import company_vat_registered
    vat_reg = company_vat_registered(db, current_user.company_id) if gross_split else False
    sales, bills, warnings = [], [], []
    voided = 0
    for num, grp in group_documents(rows, number_cols).items():
        first = grp[0]
        party = pick(first, *party_cols)
        status = pick(first, *status_cols)
        if key(status) in void_values:
            voided += 1                                      # a voided/deleted document never happened: don't book it
            continue
        net, vat = invoice_total_lines(grp, qty_cols, price_cols, disc_cols, tax_cols, amount_cols)
        if gross_split and not vat:   # export gives one VAT-inclusive total: split it at the standard 15% (or none if not a VAT vendor)
            if vat_reg:
                gross = net
                net = round(gross / 1.15, 2); vat = round(gross - net, 2)
        total = money(pick(first, *total_cols)) if total_cols and pick(first, *total_cols) else 0.0
        if not net and total:
            net = round(total - vat, 2)
        desc = next((pick(g, *desc_cols) for g in grp if pick(g, *desc_cols)), "")
        rec = {"invoice_number": "" if num.startswith("\0row") else num, "client_name": party, "description": desc,
               "amount": f"{net:.2f}", "vat_amount": f"{vat:.2f}", "total_amount": f"{round(net + vat, 2):.2f}",
               "currency": pick(first, *currency_cols), "exchange_rate": pick(first, *rate_cols),
               "issue_date": pick(first, *date_cols), "due_date": pick(first, *due_cols), "status": status}
        (bills if key(pick(first, *type_cols)) in bill_values else sales).append(rec)
    if voided:
        warnings.append(f"{voided} voided/deleted document(s) were ignored.")
    parts = []
    if sales:
        fields = ["invoice_number", "client_name", "description", "amount", "vat_amount", "total_amount", "currency",
                  "exchange_rate", "issue_date", "due_date", "status"]
        res = result(await CI.import_invoices(file=make_upload(fields, sales), db=db, cu=current_user))
        warnings.append(f"Sales invoices: {res['imported']} imported")
        parts.append(res)
    if bills:
        exp = [{"vendor": b["client_name"], "description": b["description"] or f"Bill {b['invoice_number']}".strip(),
                "amount": b["amount"], "vat_amount": b["vat_amount"], "expense_date": b["issue_date"],
                "category": ""} for b in bills]
        res = result(await CI.import_expenses(file=make_upload(["vendor", "description", "amount", "vat_amount", "expense_date", "category"], exp),
                                              db=db, cu=current_user))
        warnings.append(f"Supplier bills imported as expenses: {res['imported']}")
        parts.append(res)
    if not parts:
        raise HTTPException(400, "Nothing to import: no usable invoice or bill rows were found." + skip_status_note)
    out = merge(*parts)
    out["warnings"] = warnings + out["warnings"]
    return out


@router.post("/invoices")
async def import_xero_invoices(file: UploadFile = File(...), current_user=Depends(require_role(*_ROLES)),
                               db: Session = Depends(get_db)):
    """Xero invoice export (one row per invoice line is fine). Type ACCREC (or no Type) = sales invoice, ACCPAY = supplier
    bill, imported as an expense. Voided/deleted documents are ignored. Invoices already in ZuZan are not imported twice."""
    rows = await read_table(file)
    return await run_documents(
        rows, current_user, db,
        number_cols=("invoicenumber", "invoice number", "invoiceno", "number"),
        party_cols=("contactname", "contact name", "customer", "supplier", "name"),
        date_cols=("invoicedate", "invoice date", "date"), due_cols=("duedate", "due date"),
        status_cols=("status", "invoicestatus"), type_cols=("type", "invoicetype"),
        desc_cols=("description", "itemdescription"),
        qty_cols=("quantity", "qty"), price_cols=("unitamount", "unit amount", "unitprice"), disc_cols=("discount", "discountrate"),
        tax_cols=("taxamount", "totaltax", "vatamount"), amount_cols=("subtotal", "amount", "linetotal"),
        total_cols=(), currency_cols=("currency", "currencycode"), rate_cols=("currencyrate", "exchangerate"),
        bill_values=("accpay", "bill", "supplierbill"), void_values=("voided", "void", "deleted"),
        skip_status_note="")


# ── 5. Employees ─────────────────────────────────────────────────────────────

def employee_rows(rows: list[dict], first_cols, last_cols, name_cols, extra: dict) -> list[dict]:
    out = []
    for r in rows:
        first, last = pick(r, *first_cols), pick(r, *last_cols)
        if not first and not last:
            full = pick(r, *name_cols)
            parts = full.split(" ", 1)
            first, last = parts[0], (parts[1] if len(parts) > 1 else "")
        if not first or not last:
            continue
        rec = {"first_name": first, "last_name": last}
        for field, cols in extra.items():
            rec[field] = pick(r, *cols)
        out.append(rec)
    return out


@router.post("/employees")
async def import_xero_employees(file: UploadFile = File(...), current_user=Depends(require_role(*_ROLES)),
                                db: Session = Depends(get_db)):
    """Employee export: First Name, Last Name, ID/Tax number, Date of Birth, Start Date, Job Title, Department, Pay Rate.
    Pay Rate is read as the MONTHLY gross salary - check it before running payroll."""
    rows = await read_table(file)
    fields = ["first_name", "last_name", "id_number", "tax_number", "date_of_birth", "start_date", "position", "department",
              "gross_salary", "email"]
    recs = employee_rows(rows, ("firstname", "first name", "givenname"), ("lastname", "last name", "surname", "familyname"),
                         ("name", "employeename", "fullname"),
                         {"id_number": ("idnumber", "nationalid", "id number"), "tax_number": ("taxnumber", "incometaxnumber", "taxfilenumber"),
                          "date_of_birth": ("dateofbirth", "dob", "birthdate"), "start_date": ("startdate", "employmentstartdate", "hiredate", "dateofhire"),
                          "position": ("jobtitle", "classification", "position", "title", "role"), "department": ("department", "costcentre"),
                          "gross_salary": ("payrate", "salary", "basicsalary", "monthlysalary", "annualsalary"), "email": ("email", "emailaddress")})
    if not recs:
        raise HTTPException(400, "No employees found (First Name and Last Name columns are needed).")
    res = result(await CI.import_employees(file=make_upload(fields, recs), db=db, cu=current_user),
                 warnings=["Pay Rate was read as the monthly gross salary. Check each employee's salary before running payroll."])
    return res
