"""
QuickBooks Online -> ZuZan migration wizard (routes mounted under /qbo).

Thin adapters over the same importers the Import screens use (see xero_migrate.py for the shared helpers).

POST /qbo/accounts           Chart of accounts (QBO "Account List" export)
POST /qbo/opening-balances   Trial balance                                  ?as_at=YYYY-MM-DD&replace=false
POST /qbo/general-ledger     General Ledger report (QBO multi-level format)
POST /qbo/customers          Customer contact list
POST /qbo/vendors            Vendor contact list
POST /qbo/invoices           Invoice list (QBO exports one total per invoice, so VAT is not split - see warning)
POST /qbo/employees          Employees
"""
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from database import get_db
from auth import require_role
import csv_import as CI
from xero_migrate import (read_table, pick, pick_containing, make_upload, result, merge, import_chart, run_documents,
                          employee_rows, _ROLES, key)

router = APIRouter()

_CONTACT_FIELDS = ["name", "email", "phone", "address", "vat_number"]


def _contacts(rows):
    out = []
    for r in rows:
        name = pick(r, "displayname", "customer", "vendor", "company", "companyname", "name", "fullname")
        if not name:
            first, last = pick(r, "firstname", "givenname"), pick(r, "lastname", "familyname")
            name = f"{first} {last}".strip()
        if not name:
            continue
        addr = pick(r, "billingaddress", "billaddress", "address", "streetaddress")
        if not addr:
            addr = " ".join(x for x in (pick(r, "billingstreet", "billaddressstreet"), pick(r, "billingcity", "billaddresscity"),
                                        pick(r, "billingpostalcode", "billaddresspostalcode", "billingzip")) if x)
        out.append({"name": name, "email": pick(r, "email", "emails", "emailaddress"),
                    "phone": pick(r, "phone", "phonenumbers", "phonenumber", "mobile"), "address": addr,
                    "vat_number": pick(r, "taxnumber", "vatnumber", "taxregno", "taxid")})
    return out


@router.post("/accounts")
async def import_qbo_accounts(file: UploadFile = File(...), current_user=Depends(require_role(*_ROLES)),
                              db: Session = Depends(get_db)):
    rows = await read_table(file)
    if not any(pick(r, "name", "account name", "account", "fullname") for r in rows):
        raise HTTPException(400, "No account name column found. Use Accounting > Chart of accounts > Export in QuickBooks.")
    for r in rows:                                       # QBO calls the name column "Name", "Account name" or "Full name"
        if not r.get("name"):
            r["name"] = pick(r, "accountname", "fullname", "account")
    return result(import_chart(db, current_user, rows, ("number", "accountnumber", "code"), ("name",), ("type", "accounttype")))


@router.post("/opening-balances")
async def import_qbo_opening_balances(file: UploadFile = File(...), as_at: Optional[str] = None, replace: bool = False,
                                      current_user=Depends(require_role(*_ROLES)), db: Session = Depends(get_db)):
    rows = await read_table(file)
    out = []
    for r in rows:
        name = pick(r, "account", "accountname", "name", "fullname")
        if not name or key(name) in ("total", "totals", "grandtotal"):
            continue
        debit, credit = pick_containing(r, ("debit",)), pick_containing(r, ("credit",))
        out.append({"code": pick(r, "number", "accountnumber", "code"), "name": name, "type": pick(r, "type", "accounttype"),
                    "debit": debit, "credit": credit, "balance": "" if (debit or credit) else pick(r, "balance", "amount")})
    if not out:
        raise HTTPException(400, "No account lines found. Export the Trial Balance from QuickBooks (Reports > Trial Balance).")
    up = make_upload(["code", "name", "type", "debit", "credit", "balance"], out)
    return result(await CI.import_trial_balance(file=up, as_at=as_at, replace=replace, db=db, cu=current_user))


@router.post("/general-ledger")
async def import_qbo_general_ledger(file: UploadFile = File(...), current_user=Depends(require_role(*_ROLES)),
                                    db: Session = Depends(get_db)):
    """
    QuickBooks Online General Ledger export.

    QBO's GL has a multi-level structure:
      • Several report-header rows at the top (company name, date range, report title) — no data
      • One row of column headers somewhere in the middle
      • Account-name rows: first column has the account name, all other columns are blank
      • Transaction rows: first column blank, then Date / Transaction Type / Num / Name / Memo / Split / Amount / Balance
      • Sub-total rows starting with "Total" — skipped
      • Blank rows — skipped

    Amount sign convention in QBO: positive = increases the account's natural balance.
    ZuZan's import_general_ledger expects: positive = debit, negative = credit.
    So for credit-normal accounts (liability / equity / revenue) we negate the amount.

    The endpoint normalises the multi-level data into flat rows and passes them to
    CI.import_general_ledger which handles duplicate detection and journal posting.
    """
    content = await file.read()
    if not content or not content.strip():
        raise HTTPException(400, "The file is empty.")

    # ── Parse raw CSV ──────────────────────────────────────────────────────
    try:
        raw_headers, raw_rows = CI._read_csv(content)
    except Exception:
        raise HTTPException(400, "Could not read this file. Export the General Ledger as CSV from QuickBooks.")

    if not raw_headers or not raw_rows:
        raise HTTPException(400, "The file has no data rows.")

    # ── Locate the column-header row ───────────────────────────────────────
    # QBO inserts report-title rows before the real header.  The real header
    # contains "Date" and either "Amount" or "Debit".
    _hkey = lambda h: re.sub(r"[^a-z0-9]+", "", str(h or "").lower())

    def _is_data_header(row):
        ks = [_hkey(c) for c in row]
        return "date" in ks and ("amount" in ks or "debit" in ks)

    data_start = None
    col_headers = raw_headers
    all_rows = [raw_headers] + raw_rows   # check headers row too

    for i, row in enumerate(all_rows):
        if _is_data_header(row):
            col_headers = row
            data_start = i + 1
            break

    if data_start is None:
        raise HTTPException(400, "Could not find a data-header row (expected columns: Date, Amount). "
                                 "Export the General Ledger report from QuickBooks (Reports → General Ledger).")

    actual_rows = all_rows[data_start:]
    hkeys = [_hkey(h) for h in col_headers]

    def _col(row, *names):
        for n in names:
            k = _hkey(n)
            if k in hkeys:
                v = row[hkeys.index(k)] if hkeys.index(k) < len(row) else ""
                if v and str(v).strip():
                    return str(v).strip()
        return ""

    # ── Walk rows, tracking current account name ───────────────────────────
    # Credit-normal account types that need amount sign flip
    _CREDIT_NORMAL_TYPES = {"accounts payable (a/p)", "accounts payable", "credit card",
                            "other current liabilities", "long-term liabilities", "equity",
                            "income", "other income", "sales"}

    current_account_name = ""
    current_account_type = ""  # QB's "type" is embedded in the account-name row for some exports
    out_rows = []

    for row in actual_rows:
        # Extend short rows
        while len(row) < len(hkeys):
            row = list(row) + [""]

        first = str(row[0]).strip() if row else ""
        date_val = _col(row, "date")

        # Skip blank rows
        if not any(str(c).strip() for c in row):
            continue

        # Skip total/subtotal rows
        if re.match(r"^total\b", first, re.I):
            continue

        # Account-name row: first column has content, date column is blank
        if first and not date_val:
            # QBO sometimes includes the account code in the name: "1000 Checking" or "Checking"
            current_account_name = first
            current_account_type = _col(row, "type", "accounttype")
            continue

        # Transaction row: must have a date
        if not date_val:
            continue

        amount_str = _col(row, "amount")
        if not amount_str:
            continue

        try:
            amount = float(str(amount_str).replace(",", "").replace(" ", ""))
        except ValueError:
            continue

        # Determine if this account is credit-normal so we can flip the sign
        acct_type_key = current_account_type.strip().lower()
        is_credit_normal = (
            acct_type_key in _CREDIT_NORMAL_TYPES
            or any(w in acct_type_key for w in ("liabilit", "equity", "income", "revenue", "sales", "credit card"))
        )
        # If the account name starts with a 4xxx / 2xxx / 3xxx code that's credit-normal by GAAP prefix:
        m = re.match(r"^(\d)", current_account_name)
        if m and not acct_type_key:
            prefix = int(m.group(1))
            is_credit_normal = prefix in (2, 3, 4)   # liability, equity, revenue

        # QBO positive = increases account; ZuZan positive = debit
        # For debit-normal (asset/expense): no change.  For credit-normal: negate.
        zuzan_net = -amount if is_credit_normal else amount

        out_rows.append({
            "date":         date_val,
            "reference":    _col(row, "num", "no", "transactiontype", "type") or _col(row, "transactiontype"),
            "description":  _col(row, "memo", "memoodescription", "description", "name"),
            "account_name": current_account_name,
            "account_code": "",        # QBO GL has no code column; _find_or_create_account matches by name
            "net_amount":   str(zuzan_net),
        })

    if not out_rows:
        raise HTTPException(400, "No transaction rows found. Make sure you exported the General Ledger "
                                 "(not the Transaction List) from QuickBooks.")

    up = make_upload(["date", "reference", "description", "account_name", "account_code", "net_amount"], out_rows)
    res = await CI.import_general_ledger(file=up, db=db, cu=current_user)
    warns = []
    if not any(pick(r, "type", "accounttype") for r in actual_rows[:20]):
        warns.append("No account-type column detected in this GL. Account types were inferred from account names and "
                     "code prefixes. Use 'Fix Account Types' in Import Data → Accounts after importing if any accounts "
                     "appear under the wrong section of the balance sheet.")
    return result(res, warnings=warns)


@router.post("/customers")
async def import_qbo_customers(file: UploadFile = File(...), current_user=Depends(require_role(*_ROLES)),
                               db: Session = Depends(get_db)):
    recs = _contacts(await read_table(file))
    if not recs:
        raise HTTPException(400, "No customers found (a 'Customer' / 'Display name' column is needed).")
    return result(await CI.import_customers(file=make_upload(_CONTACT_FIELDS, recs), db=db, cu=current_user))


@router.post("/vendors")
async def import_qbo_vendors(file: UploadFile = File(...), current_user=Depends(require_role(*_ROLES)),
                             db: Session = Depends(get_db)):
    recs = _contacts(await read_table(file))
    if not recs:
        raise HTTPException(400, "No vendors found (a 'Vendor' / 'Display name' column is needed).")
    return result(await CI.import_suppliers(file=make_upload(_CONTACT_FIELDS, recs), db=db, cu=current_user))


@router.post("/invoices")
async def import_qbo_invoices(file: UploadFile = File(...), current_user=Depends(require_role(*_ROLES)),
                              db: Session = Depends(get_db)):
    """QBO invoice list: Date, No., Customer, Due date, Amount (or Total), Status. Voided invoices are ignored. The export has
    one total per invoice with no VAT split, so the total is treated as VAT-inclusive and split at 15% unless a Tax column is present."""
    rows = await read_table(file)
    res = await run_documents(
        rows, current_user, db,
        number_cols=("num", "no", "invoiceno", "number", "invoicenumber"),
        party_cols=("customer", "customerdisplayname", "name"),
        date_cols=("invoicedate", "date", "transactiondate"), due_cols=("duedate", "due"),
        status_cols=("status",), type_cols=("transactiontype", "type"),
        desc_cols=("memo", "description", "productservicedescription"),
        qty_cols=("qty", "quantity"), price_cols=("rate", "unitprice"), disc_cols=(),
        tax_cols=("tax", "taxamount", "salestax", "vat"), amount_cols=("amount", "total", "lineamount"),
        total_cols=(), currency_cols=("currency",), rate_cols=("exchangerate",),
        bill_values=("bill", "vendorbill"), void_values=("voided", "void", "deleted"), skip_status_note="", gross_split=True)
    if not any(pick(r, "tax", "taxamount", "salestax", "vat") for r in rows):
        res["warnings"].append("QuickBooks exports one VAT-inclusive total per invoice, so each was split at 15% VAT "
                               "(no VAT if your company is not VAT-registered). Zero-rated or exempt invoices will need correcting.")
    return res


@router.post("/employees")
async def import_qbo_employees(file: UploadFile = File(...), current_user=Depends(require_role(*_ROLES)),
                               db: Session = Depends(get_db)):
    rows = await read_table(file)
    fields = ["first_name", "last_name", "id_number", "tax_number", "date_of_birth", "start_date", "position", "department",
              "gross_salary", "email"]
    recs = employee_rows(rows, ("firstname", "first name", "givenname"), ("lastname", "last name", "surname", "familyname"),
                         ("name", "employee", "employeename", "displayname"),
                         {"id_number": ("idnumber", "ssn", "nationalid"), "tax_number": ("taxnumber", "taxid"),
                          "date_of_birth": ("dateofbirth", "dob", "birthdate"), "start_date": ("hiredate", "startdate", "dateofhire"),
                          "position": ("jobtitle", "title", "position"), "department": ("department", "class"),
                          "gross_salary": ("salary", "payrate", "monthlysalary", "basicsalary"), "email": ("email", "emailaddress")})
    if not recs:
        raise HTTPException(400, "No employees found (First Name and Last Name columns are needed).")
    return result(await CI.import_employees(file=make_upload(fields, recs), db=db, cu=current_user),
                  warnings=["Salary / Pay rate was read as the monthly gross salary. Check each employee before running payroll."])
