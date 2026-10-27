import io, types, asyncio, datetime as dt
from fastapi import UploadFile
from tests.helpers import *
from database import Invoice, InvoiceStatus
import journal as J, financial_statements as FS, csv_import as CI, companies as CO


def _up(t): return UploadFile(filename="x.csv", file=io.BytesIO(t.encode()))


def _afs(co, year):
    return FS.annual_financial_statements(year=year, db=db, current_user=types.SimpleNamespace(company_id=co.id, id=1, role="owner"))


def test_empty_company_produces_balanced_empty_statements():
    co = company("afsEmpty", "general")
    r = _afs(co, 2026)
    assert r["balance_sheet"]["balanced"] and r["cash_flow"]["reconciles_to_ledger"]
    assert r["changes_in_equity"]["net_profit"] == 0


def test_imported_opening_balances_dated_before_the_year_roll_into_opening_equity_and_balance():
    co = company("afsOB", "general"); cu = types.SimpleNamespace(company_id=co.id, id=1, role="owner")
    asyncio.run(CI.import_trial_balance(file=_up("Code,Account Name,Type,Debit,Credit\n1000,Bank,Asset,8000,\n2000,Accounts Payable,Liability,,3000\n"),
                                        as_at="2025-02-28", replace=False, db=db, cu=cu))
    r = _afs(co, 2026)                              # FY2026 starts 1 Mar 2025, so the TB is opening
    assert r["balance_sheet"]["balanced"], (r["balance_sheet"]["total_assets"], r["balance_sheet"]["total_equity_and_liabilities"])
    assert r["changes_in_equity"]["opening_total"] == 5000
    assert r["cash_flow"]["reconciles_to_ledger"]


def test_foreign_currency_and_part_paid_invoices_keep_the_statements_balanced_and_ageing_on_balances():
    co = company("afsFX", "general"); cid = co.id
    user = types.SimpleNamespace(company_id=cid, id=1, role="owner", first_name="B", last_name="B")
    J.init_accounts(cid, db)
    d = dt.datetime(2025, 9, 1)
    fx = Invoice(company_id=cid, invoice_number="F1", client_name="US", amount=100, vat_amount=0, total_amount=100, currency="USD",
                 exchange_rate=18.0, status=InvoiceStatus.sent, issue_date=d, due_date=d)
    db.add(fx); db.commit(); db.refresh(fx); J.post_invoice_raised(fx, db); db.commit()
    asyncio.run(CO.update_invoice(fx.id, CO.InvoiceUpdate(status="paid", paid_date="2025-10-01", paid_amount_zar=900, final_payment=False), current_user=user, db=db))
    r = _afs(co, 2026)
    assert r["balance_sheet"]["balanced"]
    assert r["cash_flow"]["reconciles_to_ledger"]
    ag = next(v for v in r.values() if isinstance(v, dict) and "receivables_aging" in v)["receivables_aging"]
    assert ag["total"] == 900                       # R1,800 carried less R900 received
