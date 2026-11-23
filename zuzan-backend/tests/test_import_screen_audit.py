"""Import screen audit 2026-11-22: real-world Xero and QuickBooks export layouts on every import type.

Before this audit: Xero's "*ContactName"-style headers were not recognised, multi-line Xero invoices lost every
line after the first, QuickBooks invoice numbers ("No.") were replaced by IMP-numbers, QuickBooks P&L and Balance
Sheet reports could not be imported, a QuickBooks GL on the import screen was rejected line by line, accounts
without a code were all created as assets (Services, Subscriptions...), "Accounts Receivable (A/R)" and
"Opening Balance Equity" were duplicated beside ZuZan's 1100 / 3999, and Xero manual journals (no reference
column) were rejected as one-sided journals."""
import asyncio
import io
import types
from collections import defaultdict

import openpyxl
from fastapi import UploadFile, HTTPException

from tests.helpers import db, company
from database import Account, Customer, Invoice, InvoiceStatus, Expense, JournalEntry
import csv_import as CI
import quickbooks_migrate as QB

_n = [0]


def _co():
    _n[0] += 1
    return company(f"ImpAudit{_n[0]}", "general")


def _cu(co):
    return types.SimpleNamespace(company_id=co.id, id=1, role="owner")


def _up(content, name="x.csv"):
    if isinstance(content, str):
        content = content.encode("utf-8")
    return UploadFile(file=io.BytesIO(content), filename=name)


def _xlsx(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def _run(fn, co, content, name="x.csv", **kw):
    if "current_user" in fn.__code__.co_varnames:
        return asyncio.run(fn(file=_up(content, name), current_user=_cu(co), db=db, **kw))
    return asyncio.run(fn(file=_up(content, name), db=db, cu=_cu(co), **kw))


def _tb(co):
    out = defaultdict(float)
    for je in db.query(JournalEntry).filter_by(company_id=co.id).all():
        tot = 0.0
        for ln in je.lines:
            a = db.get(Account, ln.account_id)
            out[(a.code, a.type.value)] += (ln.debit or 0) - (ln.credit or 0)
            tot += (ln.debit or 0) - (ln.credit or 0)
        assert abs(tot) < 0.005, f"unbalanced journal {je.reference}"
    return {k: round(v, 2) for k, v in out.items() if abs(v) > 0.004}


def _acct(co, name):
    return db.query(Account).filter_by(company_id=co.id, name=name).one()


def test_header_normalisation():
    assert CI._norm("*ContactName") == "contactname"
    assert CI._norm("No.") == "no"
    assert CI._norm("Memo/Description") == "memo_description"
    m = CI._map_headers(["Date", "Name", "Account", "Debit"], CI.GENERAL_LEDGER_ALIASES)
    assert m["account_name"] == 2                       # "Account", never the customer "Name" column


def test_xero_contacts_with_asterisk_headers():
    co = _co()
    r = _run(CI.import_customers, co, "*ContactName,EmailAddress,POAddressLine1,TaxNumber\nAcme Ltd,a@acme.co.za,1 Main Rd,4123456789\n")
    assert r["imported"] == 1
    c = db.query(Customer).filter_by(company_id=co.id).one()
    assert (c.email, c.address, c.vat_number) == ("a@acme.co.za", "1 Main Rd", "4123456789")


def test_xero_multi_line_invoice_is_one_invoice_with_all_lines():
    co = _co()
    csv = ("*ContactName,*InvoiceNumber,*InvoiceDate,*DueDate,Description,LineAmount,TaxAmount,Total\n"
           "Acme,INV-20,01/03/2026,31/03/2026,Line A,100,15,345\n"
           "Acme,INV-20,01/03/2026,31/03/2026,Line B,200,30,345\n")
    r = _run(CI.import_invoices, co, csv)
    assert r["imported"] == 1 and not r["errors"]
    inv = db.query(Invoice).filter_by(company_id=co.id).one()
    assert (inv.invoice_number, inv.amount, inv.vat_amount, inv.total_amount) == ("INV-20", 300, 45, 345)


def test_quickbooks_invoice_list_keeps_numbers_and_open_balance_sets_status():
    co = _co()
    rows = [["Co"], ["Invoice List"], [], [None, "Date", "No.", "Customer", "Due Date", "Amount", "Open Balance"],
            [None, "07/07/2024", "1011", "Dikopo", "06/08/2024", "16100.00", "16100.00"],
            [None, "10/05/2024", "1009", "BP", "09/06/2024", "32000.00", "0.00"]]
    r = _run(CI.import_invoices, co, _xlsx(rows), "i.xlsx")
    assert r["imported"] == 2
    got = {i.invoice_number: i.status for i in db.query(Invoice).filter_by(company_id=co.id)}
    assert got == {"1011": InvoiceStatus.sent, "1009": InvoiceStatus.paid}


def test_xero_bill_to_expense_uses_vat_date_and_account_code():
    co = _co()
    csv = ("*ContactName,*InvoiceNumber,*InvoiceDate,*DueDate,Description,*Quantity,*UnitAmount,*AccountCode,TaxAmount,Total\n"
           "Eskom,B-1,02/03/2026,02/04/2026,Electricity,1,1000,5200,150,1150\n")
    assert _run(CI.import_expenses, co, csv)["imported"] == 1
    e = db.query(Expense).filter_by(company_id=co.id).one()
    assert (e.vendor, e.amount, e.vat_amount, e.category, e.expense_date.strftime("%Y-%m-%d")) == \
           ("Eskom", 1150, 150, "5200 - Utilities", "2026-03-02")


def test_quickbooks_trial_balance_types_and_system_accounts():
    co = _co()
    rows = [["Co"], ["Trial Balance"], ["As of February 28, 2026"], [], [None, "Debit", "Credit"],
            ["Solutha (bank)", 43699.61, None], ["Accounts Receivable (A/R)", 16100, None],
            ["Opening Balance Equity", None, 139480.16], ["Services", None, 100000], ["Subscriptions", 60000, None],
            ["Meals and entertainment", 59680.55, None], ["Mystery account", 60000, None], ["TOTAL", 239480.16, 239480.16]]
    r = _run(CI.import_trial_balance, co, _xlsx(rows), "tb.xlsx", as_at="2026-02-28")
    assert r["imported"] == 7
    tb = _tb(co)
    assert tb[("1100", "asset")] == 16100 and tb[("3999", "equity")] == -139480.16
    assert _acct(co, "Services").type.value == "revenue"
    assert _acct(co, "Subscriptions").type.value == "expense"
    assert _acct(co, "Meals and entertainment").type.value == "expense"
    assert _acct(co, "Solutha (bank)").type.value == "asset"
    assert any("Mystery account" in w for w in r.get("warnings", []))
    assert db.query(Account).filter(Account.company_id == co.id, Account.name.like("Accounts Receivable (%")).count() == 0


def test_xero_trial_balance_year_to_date_columns():
    co = _co()
    csv = ("Trial Balance\nDemo Co\nAs at 28 February 2026\n\n"
           "Account,Account Code,Account Type,Debit - Year to date,Credit - Year to date\n"
           "Business Bank Account (090),090,Bank,5000.00,\nSales (200),200,Revenue,,8000.00\n"
           "Rent (469),469,Expense,3000.00,\nTotal,,,8000.00,8000.00\n")
    r = _run(CI.import_trial_balance, co, csv, as_at="2026-02-28")
    assert r["imported"] == 3
    assert _acct(co, "Sales").type.value == "revenue" and _acct(co, "Business Bank Account").type.value == "asset"


def test_quickbooks_profit_and_loss_report():
    co = _co()
    rows = [["Co"], ["Profit and Loss"], ["March 2025 - February 2026"], [], [None, "Total"], ["Income", None],
            ["   Services", 118493.0], ["Total Income", 118493.0], ["Gross Profit", 118493.0], ["Expenses", None],
            ["   Bank charges", 2111.95], ["   Subscriptions", 38229.75], ["Total Expenses", 40341.70],
            ["Other Expenses", None], ["   General expenses", 22909.44], ["Total Other Expenses", 22909.44],
            ["Net Earnings", 55241.86]]
    r = _run(CI.import_profit_loss, co, _xlsx(rows), "pl.xlsx", as_at="2026-02-28")
    assert r["imported"] == 4 and not r["errors"]
    tb = _tb(co)
    assert tb[("3998", "equity")] == 55241.86                 # net profit offset
    assert _acct(co, "Services").type.value == "revenue" and _acct(co, "Bank charges").type.value == "expense"


def test_quickbooks_balance_sheet_report():
    co = _co()
    rows = [["Co"], ["Balance Sheet"], ["As of February 28, 2026"], [], [None, "Total"],
            ["Assets"], ["   Current Assets"], ["      Bank Accounts"], ["         FNB Cheque", 43699.61],
            ["      Total Bank Accounts", 43699.61], ["      Accounts Receivable"], ["         Accounts Receivable (A/R)", 16100.00],
            ["      Total Accounts Receivable", 16100.00], ["   Total Current Assets", 59799.61], ["Total Assets", 59799.61],
            ["Liabilities and Equity"], ["   Liabilities"], ["      Director loan", 10000.00], ["   Total Liabilities", 10000.00],
            ["   Equity"], ["      Opening Balance Equity", 139480.16], ["      Retained Earnings", -47064.16],
            ["      Net Income", -42616.39], ["   Total Equity", 49799.61], ["Total Liabilities and Equity", 59799.61]]
    r = _run(CI.import_balance_sheet, co, _xlsx(rows), "bs.xlsx", as_at="2026-02-28")
    assert not r["errors"] and r["balancing_to_opening_equity"] == 0
    tb = _tb(co)
    assert tb[("1100", "asset")] == 16100 and tb[("3999", "equity")] == -139480.16
    assert _acct(co, "FNB Cheque").type.value == "asset" and _acct(co, "Director loan").type.value == "liability"
    assert tb[("3000", "equity")] == round(47064.16 + 42616.39, 2)   # retained earnings + net income


def test_quickbooks_general_ledger_on_the_import_screen():
    co = _co()
    rows = [["Solutha"], ["General Ledger"], ["All Dates"], [],
            [None, "Date", "Transaction Type", "No.", "Name", "Memo/Description", "Account", "Debit", "Credit", "Balance"],
            ["Solutha (bank)"], [None, "07/11/2023", "Deposit", None, None, "Opening", "Solutha (bank)", 1000, None, 1000],
            [None, "20/05/2024", "Expense", None, None, "KARRI PAY", "Solutha (bank)", None, 20, 980],
            ["Total for Solutha (bank)", None, None, None, None, None, None, 1000, 20, None],
            ["Accounts Receivable (A/R)"], [None, "10/05/2024", "Invoice", 1009, "BP Drive Inn", None, "Accounts Receivable (A/R)", 800, None, 800],
            ["Opening Balance Equity"], [None, "07/11/2023", "Deposit", None, None, None, "Opening Balance Equity", None, 1000, -1000],
            ["Services"], [None, "10/05/2024", "Invoice", 1009, "BP Drive Inn", "March VAT", "Services", None, 800, -800],
            ["General expenses"], [None, "20/05/2024", "Expense", None, None, "KARRI PAY", "General expenses", 20, None, 20],
            [], ["Sunday, Nov 22, 2026 06:28:27 PM GMT+2 - Accrual Basis"]]
    r = _run(CI.import_general_ledger, co, _xlsx(rows), "gl.xlsx")
    assert r["imported"] == 6 and not r["errors"]
    assert not any("Accrual Basis" in w for w in r["warnings"])
    tb = _tb(co)
    assert tb[("1100", "asset")] == 800 and tb[("3999", "equity")] == -1000 and tb[("5900", "expense")] == 20
    assert _acct(co, "Services").type.value == "revenue"
    assert db.query(Account).filter_by(company_id=co.id, name="BP Drive Inn").count() == 0


def test_xero_general_ledger_account_type_column():
    co = _co()
    csv = ("Date,Source,Description,Reference,Debit,Credit,Account Code,Account,Account Type\n"
           "01 Mar 2026,Manual Journal,Opening,MJ1,5000.00,,090,Business Bank Account,Bank\n"
           "01 Mar 2026,Manual Journal,Opening,MJ1,,5000.00,960,Retained Earnings,Equity\n")
    assert _run(CI.import_general_ledger, co, csv)["imported"] == 2
    assert db.query(Account).filter_by(company_id=co.id, code="960").one().type.value == "equity"


def test_xero_manual_journal_without_reference_column():
    co = _co()
    db.add(Account(company_id=co.id, code="6100", name="Audit Fees", type=CI.AccountType.expense))
    db.add(Account(company_id=co.id, code="800", name="Accounts Payable (Xero)", type=CI.AccountType.liability))
    db.commit()
    csv = ("*Narration,*Date,Description,*AccountCode,*TaxRate,*Amount\n"
           "Accrual,31/03/2026,Audit fee,6100,Tax Exempt,5000\nAccrual,31/03/2026,Audit fee,800,Tax Exempt,-5000\n")
    r = _run(CI.import_journals, co, csv)
    assert r["imported"] == 2 and not r["errors"]
    assert _tb(co) == {("6100", "expense"): 5000, ("800", "liability"): -5000}


def test_journal_line_with_unknown_code_and_no_name_is_rejected_not_invented():
    co = _co()
    csv = "*Narration,*Date,*AccountCode,*Amount\nAccrual,31/03/2026,6100,5000\nAccrual,31/03/2026,800,-5000\n"
    r = _run(CI.import_journals, co, csv)
    assert r["imported"] == 0 and "800" in r["errors"][0]["message"] or "6100" in r["errors"][0]["message"]
    assert db.query(Account).filter_by(company_id=co.id, code="800").count() == 0


def test_quickbooks_account_list_reuses_system_accounts():
    co = _co()
    rows = [["Co"], ["Account List"], [], ["Account", "Type", "Detail Type"],
            ["Accounts Receivable (A/R)", "Accounts receivable (A/R)", "Accounts Receivable (A/R)"],
            ["Opening Balance Equity", "Equity", "Opening Balance Equity"], ["Services", "Income", "Service/Fee Income"]]
    _run(QB.import_qbo_accounts, co, _xlsx(rows), "a.xlsx")
    names = [a.name for a in db.query(Account).filter_by(company_id=co.id)]
    assert "Accounts Receivable (A/R)" not in names and names.count("Opening Balance Equity") == 1


def test_empty_ledger_file_is_reported_not_silently_accepted():
    co = _co()
    try:
        _run(CI.import_general_ledger, co, "Date,Reference,Account Name,Debit,Credit\n2026-03-01,J1,,,\n")
        assert False, "expected an error"
    except HTTPException as e:
        assert e.status_code == 400
