"""2026-11-15 (Okwendalo): a replaced opening balance must net out in its own period, the P&L must ignore
reversed imports and split cost of sales from operating expenses, and an accountant can fix an account's
name or type."""
import io, types, asyncio, datetime as dt
import pytest
from fastapi import UploadFile, HTTPException
from tests.helpers import *
from database import Account, AccountType, JournalEntry
import csv_import as CI
import journal as J
import payroll as P

def _up(t): return UploadFile(filename="x.csv", file=io.BytesIO(t.encode()))
def _cu(name, role="owner"):
    co = company(name, "general")
    return co, types.SimpleNamespace(company_id=co.id, id=1, role=role)
def _tb(cu, text, as_at, replace=False):
    return asyncio.run(CI.import_trial_balance(file=_up(text), as_at=as_at, replace=replace, db=db, cu=cu))

TB1 = ("Code,Account Name,Type,Debit,Credit\n1010,Bank,asset,500,\n4000,Fuel Sales,revenue,,1000\n"
       "5010,Purchases - Shop Stock,cogs,400,\n6100,Rent,expense,100,\n")
TB2 = ("Code,Account Name,Type,Debit,Credit\n1010,Bank,asset,300,\n4000,Fuel Sales,revenue,,600\n"
       "5010,Purchases - Shop Stock,cogs,250,\n6100,Rent,expense,50,\n")

def test_replace_reversal_is_dated_like_the_entry_it_reverses():
    co, cu = _cu("rpA")
    _tb(cu, TB1, "2026-02-28")
    _tb(cu, TB2, "2024-02-29", replace=True)
    rev = db.query(JournalEntry).filter_by(company_id=co.id, source="import_reversal").one()
    assert rev.date.strftime("%Y-%m-%d") == "2026-02-28"

def test_pl_ignores_reversed_import_and_splits_cost_of_sales():
    co, cu = _cu("rpB")
    _tb(cu, TB1, "2026-02-28")
    _tb(cu, TB2, "2024-02-29", replace=True)
    fy26 = (dt.datetime(2025, 3, 1), dt.datetime(2026, 3, 1))
    assert P._gl_import_income(db, co.id, *fy26) == 0          # replaced FY: nothing left
    fy24 = (dt.datetime(2023, 3, 1), dt.datetime(2024, 3, 1))
    inc = P._gl_import_income_detail(db, co.id, *fy24)
    assert inc["total"] == 600 and inc["breakdown"] == {"Sales Revenue": 600}   # 4000 is ZuZan's own account: keeps its name
    ex = P._gl_import_expenses(db, co.id, *fy24)
    assert ex["cogs_total"] == 250 and ex["cogs_breakdown"] == {"Purchases - Shop Stock": 250}
    assert ex["breakdown"] == {"Rent": 50} and ex["total"] == 300

def _upd(cu, code, **kw):
    return asyncio.run(J.update_ledger_account(code=code, data=J.LedgerAccountUpdate(**kw), current_user=cu, db=db))

def test_accountant_can_rename_and_retype_an_imported_account():
    co, cu = _cu("rpC", role="accountant")
    _tb(cu, "Code,Account Name,Type,Debit,Credit\n6107,Equipment Rental,asset,100,\n1010,Bank,asset,,100\n", "2024-02-29")
    r = _upd(cu, "6107", name="Equipment rental", type="expense")
    a = db.query(Account).filter_by(company_id=co.id, code="6107").one()
    assert a.type == AccountType.expense and a.name == "Equipment rental" and r["changed"]

def test_system_account_only_moves_between_expense_and_cost_of_sales():
    co, cu = _cu("rpD")
    J.init_accounts(co.id, db)
    a = db.query(Account).filter_by(company_id=co.id, code="5000").one()
    assert a.is_system
    _upd(cu, "5000", type="cogs")
    assert db.query(Account).filter_by(company_id=co.id, code="5000").one().type == AccountType.cogs
    with pytest.raises(HTTPException):
        _upd(cu, "5000", type="asset")
    with pytest.raises(HTTPException):
        _upd(cu, "5000", name="Fuel purchases")
