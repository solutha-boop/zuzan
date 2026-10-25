"""
QuickBooks Online -> ZuZan migration wizard (routes mounted under /qbo).

Thin adapters over the same importers the Import screens use (see xero_migrate.py for the shared helpers).

POST /qbo/accounts           Chart of accounts (QBO "Account List" export)
POST /qbo/opening-balances   Trial balance                                  ?as_at=YYYY-MM-DD&replace=false
POST /qbo/customers          Customer contact list
POST /qbo/vendors            Vendor contact list
POST /qbo/invoices           Invoice list (QBO exports one total per invoice, so VAT is not split - see warning)
POST /qbo/employees          Employees
"""
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
