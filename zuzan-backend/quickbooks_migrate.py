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

from database import get_db, AccountType
from auth import require_role
import csv_import as CI
from xero_migrate import (read_table, pick, pick_containing, make_upload, result, merge, import_chart, run_documents,
                          employee_rows, _ROLES, key, MAX_UPLOAD_BYTES)

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
    """
    QuickBooks Trial Balance export.

    QBO's Trial Balance has no 'Type' column — account type is inferred in this order:
      1. Explicit type column (if present)
      2. Keyword matching on the account name (asset, liability, revenue, expense keywords)
      3. Debit/Credit side: debit-only → 'asset'; credit-only → 'income'
      4. Final fallback: 'asset' (safe default — user can fix with Fix Account Types)

    Special case: "Credit Card" with a debit balance is a bank account (asset), not a liability.
    """
    rows = await read_table(file)
    # QB Trial Balance: the account name column has no header — read_table stores it under key "".
    # Rename it to "name" so the pick() calls below find it.
    for r in rows:
        if "" in r and r[""] and not r.get("name") and not r.get("account"):
            r["name"] = r[""]
    out = []
    warns = []
    fallback_count = 0

    for r in rows:
        name = pick(r, "account", "accountname", "name", "fullname")
        if not name or key(name) in ("total", "totals", "grandtotal"):
            continue

        debit  = pick_containing(r, ("debit",))
        credit = pick_containing(r, ("credit",))

        # 1. Explicit type column
        type_val = pick(r, "type", "accounttype")

        if not type_val:
            # 2. Keyword inference from name
            inferred = CI._guess_account_type(name)

            # Special case: "Credit Card" with a debit balance is a QB bank/asset account
            if key(name) == "creditcard" and debit and not credit:
                inferred = AccountType.asset

            if inferred is not None:
                type_val = inferred.value
            else:
                # 3. Debit/credit side fallback
                if debit and not credit:
                    type_val = "asset"
                    fallback_count += 1
                elif credit and not debit:
                    type_val = "income"
                    fallback_count += 1
                else:
                    type_val = "asset"   # 4. Final safe default
                    fallback_count += 1

        out.append({
            "code":    pick(r, "number", "accountnumber", "code"),
            "name":    name,
            "type":    type_val,
            "debit":   debit,
            "credit":  credit,
            "balance": "" if (debit or credit) else pick(r, "balance", "amount"),
        })

    if not out:
        raise HTTPException(400, "No account lines found. Export the Trial Balance from QuickBooks (Reports → Trial Balance).")

    if fallback_count:
        warns.append(
            f"{fallback_count} account(s) had no recognisable account type and were assigned a default. "
            "Use Import Data → Accounts → Fix Account Types after import to reclassify any that look wrong."
        )

    up = make_upload(["code", "name", "type", "debit", "credit", "balance"], out)
    return result(await CI.import_trial_balance(file=up, as_at=as_at, replace=replace, db=db, cu=current_user),
                  warnings=warns)


@router.post("/general-ledger")
async def import_qbo_general_ledger(file: UploadFile = File(...), current_user=Depends(require_role(*_ROLES)),
                                    db: Session = Depends(get_db)):
    """
    QuickBooks Online General Ledger export.

    QBO's GL has a multi-level structure:
      • Several report-header rows at the top (company name, date range, report title) — no data
      • One row of column headers
      • Account-name rows: first column has the account name, all other columns are blank
      • Transaction rows: first column blank, then Date / Transaction Type / Num / Name / Memo / Split / Amount / Balance
      • Sub-total rows starting with "Total" — skipped
      • Blank rows — skipped

    Amount sign convention in QBO: positive = increases the account's natural balance.
    ZuZan's import_general_ledger expects: positive = debit, negative = credit.
    So for credit-normal accounts (liability / equity / revenue) we negate the amount.
    (If the export has separate Debit / Credit columns they are used as-is, no flipping.)

    Account type (and therefore the sign) is resolved in this order (audit fix 2026-11-11):
      1. the account already in ZuZan's chart (the wizard imports the QBO Account List first) — matched by name,
         and its code is passed through so the GL lines land on THAT account instead of a duplicate;
      2. an account-type column in the export, if present;
      3. the account name ("Accounts Receivable (A/R)", "Sales", "Credit Card"...) via csv_import._guess_account_type;
      4. a leading GAAP-style code in the account name ("4000 Sales").
    Accounts that cannot be classified are reported in the warnings instead of being silently treated as assets.

    Each transaction's lines share Transaction Type + Num (+ date); when Num is blank the journal is keyed on
    Transaction Type + date only, so same-type transactions of one day are posted as one balanced journal.
    """
    from database import Account, AccountType

    content = await file.read()
    if not content or not content.strip():
        raise HTTPException(400, "The file is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "The file is too large (limit 10 MB). Export one financial year at a time.")

    # ── Parse raw CSV ──────────────────────────────────────────────────────
    try:
        raw_headers, raw_rows = CI._read_csv(content)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "Could not read this file. Export the General Ledger as CSV from QuickBooks.")

    if not raw_headers or not raw_rows:
        raise HTTPException(400, "The file has no data rows.")

    # ── Locate the column-header row ───────────────────────────────────────
    _hkey = lambda h: re.sub(r"[^a-z0-9]+", "", str(h or "").lower())

    def _is_data_header(row):
        ks = [_hkey(c) for c in row]
        return "date" in ks and ("amount" in ks or "debit" in ks)

    data_start = None
    col_headers = raw_headers
    all_rows = [list(raw_headers)] + [list(r) for r in raw_rows]   # check the headers row too

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
                idx = hkeys.index(k)
                v = row[idx] if idx < len(row) else ""
                if v and str(v).strip():
                    return str(v).strip()
        return ""

    def _num(s):
        s = str(s or "").replace(",", "").replace(" ", "").replace("R", "")
        neg = s.startswith("(") and s.endswith(")")
        s = s.strip("()")
        if not s:
            return None
        try:
            v = float(s)
        except ValueError:
            return None
        return -v if neg else v

    has_type_col = any(k in hkeys for k in ("accounttype", "type"))
    has_dr_cr    = "debit" in hkeys or "credit" in hkeys
    has_amount   = "amount" in hkeys

    # ── ZuZan chart of accounts, by name (lower/trimmed) ───────────────────
    cid = current_user.company_id
    chart: dict[str, Account] = {}
    for a in db.query(Account).filter(Account.company_id == cid).all():
        k = (a.name or "").strip().lower()
        if k and (k not in chart or (a.is_active and not chart[k].is_active)):
            chart[k] = a

    _DESCRIPTOR = {AccountType.asset: "Current Asset", AccountType.liability: "Current Liability",
                   AccountType.equity: "Equity", AccountType.revenue: "Revenue",
                   AccountType.cogs: "Cost of Sales", AccountType.expense: "Expense"}
    _CREDIT_NORMAL = {AccountType.liability, AccountType.equity, AccountType.revenue}
    # cogs is debit-normal (same as expense) — not in _CREDIT_NORMAL

    def _resolve(acct_name: str, acct_type_text: str):
        """-> (account_code_to_pass, type_descriptor_to_pass, AccountType or None)"""
        nm = (acct_name or "").strip()
        lead = re.match(r"^(\d{3,6})\s+(.+)$", nm)            # "4000 Sales"
        bare = lead.group(2).strip() if lead else nm
        for cand in (nm, bare):
            a = chart.get(cand.lower())
            if a is not None:
                return a.code, "", a.type
        t = None
        if acct_type_text:
            t = CI._type_from_xero_name(acct_type_text) or CI._guess_account_type(acct_type_text)
        if t is None:
            t = CI._guess_account_type(bare)
        if t is None and lead:
            t = CI._infer_type_from_code(lead.group(1))
        return "", (_DESCRIPTOR[t] if t is not None else ""), t

    # ── Walk rows, tracking the current account ────────────────────────────
    current_account_name = ""
    current = ("", "", None)
    unresolved: set[str] = set()
    out_rows = []

    for row in actual_rows:
        while len(row) < len(hkeys):
            row = row + [""]

        if not any(str(c).strip() for c in row):
            continue
        first = str(row[0]).strip() if row else ""
        date_val = _col(row, "date")

        if re.match(r"^total\b", first, re.I):                 # sub-total rows
            continue

        if first and not date_val:                             # account-name row
            current_account_name = first
            current = _resolve(first, _col(row, "accounttype", "type") if has_type_col else "")
            if current[2] is None:
                unresolved.add(first)
            continue

        if not date_val or not current_account_name:
            continue

        code, descriptor, atype = current
        if has_amount and _col(row, "amount"):
            amount = _num(_col(row, "amount"))
            if amount is None:
                continue
            # QBO positive = increases the account; ZuZan positive = debit
            zuzan_net = -amount if atype in _CREDIT_NORMAL else amount
        elif has_dr_cr:
            dr = _num(_col(row, "debit")) or 0.0
            cr = _num(_col(row, "credit")) or 0.0
            zuzan_net = dr - cr
        else:
            continue
        if abs(zuzan_net) < 0.005:
            continue

        ttype = _col(row, "transactiontype")
        num   = _col(row, "num", "no")
        ref   = (f"{ttype} {num}".strip() if num else (ttype or "QBO GL"))[:100]

        out_rows.append({
            "date":         date_val,
            "reference":    ref,
            "description":  _col(row, "memodescription", "memo", "description", "name") or ttype,
            "account_name": current_account_name,
            "account_code": code,
            "name":         descriptor,     # GL 'Name' column = account-type descriptor (sets type on NEW accounts)
            "net_amount":   f"{zuzan_net:.2f}",
        })

    if not out_rows:
        raise HTTPException(400, "No transaction rows found. Make sure you exported the General Ledger "
                                 "(not the Transaction List) from QuickBooks.")

    up = make_upload(["date", "reference", "description", "account_name", "account_code", "name", "net_amount"],
                     out_rows)
    res = await CI.import_general_ledger(file=up, db=db, cu=current_user)

    warns = []
    if unresolved:
        shown = ", ".join(sorted(unresolved)[:10]) + (" …" if len(unresolved) > 10 else "")
        warns.append(f"{len(unresolved)} account(s) could not be classified and were imported as assets: {shown}. "
                     "Import the QuickBooks Account List first (step 1) or fix them with 'Fix Account Types' "
                     "in Import Data → Accounts.")
    if not has_type_col and not unresolved:
        warns.append("No account-type column in this GL: account types were taken from your ZuZan chart of accounts "
                     "and account names. Check the balance sheet after importing.")
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
