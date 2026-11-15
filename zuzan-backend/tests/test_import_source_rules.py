"""Each import source has its own rules (2026-11-15, Okwendalo QuickBooks migration):
- the trial balance import skips the report's Total line;
- Fix Account Types needs ?source= and applies only that system's rules - Xero's 2xx = revenue never
  touches a 4-digit GAAP / QuickBooks code."""
import io, types, asyncio
import pytest
from fastapi import UploadFile, HTTPException
from tests.helpers import *
from database import Account, AccountType
import csv_import as CI

def _up(text):
    return UploadFile(filename="x.csv", file=io.BytesIO(text.encode("utf-8")))

def _cu(name):
    co = company(name, "general")
    return co, types.SimpleNamespace(company_id=co.id, id=1, role="owner")

def _tb(cu, text):
    return asyncio.run(CI.import_trial_balance(file=_up(text), as_at="2026-10-31", replace=False, db=db, cu=cu))

def _fix(cu, source, dry_run=False):
    return asyncio.run(CI.reclassify_gl_accounts(source=source, dry_run=dry_run, db=db, cu=cu))

def _type(cid, code):
    return db.query(Account).filter_by(company_id=cid, code=code).one().type

# Okwendalo-shaped file: liabilities wrongly typed as revenue, plus the QuickBooks TOTALS line
OKW = ("Code,Account Name,Type,Debit,Credit\n"
       "1010,Bank,asset,1000,\n"
       "2010,Accrued Expenses,revenue,,300\n"
       "2020,VAT Payable,revenue,,200\n"
       "4000,Fuel Sales,revenue,,800\n"
       "5240,Insurance,expense,300,\n"
       "TOTALS,TOTALS,asset,1300,1300\n")

def test_trial_balance_skips_report_total_line_but_keeps_real_total_accounts():
    co, cu = _cu("srcA")
    r = _tb(cu, OKW + "6990,Total Sundry Expenses,expense,0.01,\n")
    assert r["total_lines_skipped"] == 1 and not r["errors"]
    assert db.query(Account).filter_by(company_id=co.id, code="TOTALS").first() is None
    assert db.query(Account).filter_by(company_id=co.id, code="6990").first() is not None   # numeric code: a real account
    assert abs(r["balancing_to_opening_equity"]) < 0.02

def test_reclassify_requires_a_source():
    co, cu = _cu("srcB")
    _tb(cu, OKW)
    with pytest.raises(HTTPException) as e:
        _fix(cu, None)
    assert e.value.status_code == 400

def test_xero_rules_leave_four_digit_codes_alone():
    co, cu = _cu("srcC")
    _tb(cu, OKW)
    r = _fix(cu, "xero")
    assert r["fixed"] == 0
    assert _type(co.id, "2010") == AccountType.revenue      # unchanged: 2010 is not a Xero code

def test_quickbooks_rules_fix_liabilities_typed_as_revenue_but_not_expense_vs_cogs():
    co, cu = _cu("srcD")
    _tb(cu, OKW)
    r = _fix(cu, "quickbooks")
    assert {a["code"] for a in r["accounts"]} == {"2010", "2020"}
    assert _type(co.id, "2010") == AccountType.liability and _type(co.id, "2020") == AccountType.liability
    assert _type(co.id, "5240") == AccountType.expense       # 5xxx is cost of sales in QBO, but not forced
    assert _type(co.id, "4000") == AccountType.revenue

def test_csv_rules_use_zuzan_ranges_and_dry_run_saves_nothing():
    co, cu = _cu("srcE")
    _tb(cu, OKW)
    r = _fix(cu, "csv", dry_run=True)
    assert r["fixed"] == 2 and _type(co.id, "2010") == AccountType.revenue
    _fix(cu, "csv")
    assert _type(co.id, "2010") == AccountType.liability

def test_xero_rules_still_fix_xero_codes():
    co, cu = _cu("srcF")
    _tb(cu, "Code,Account Name,Type,Debit,Credit\n"
            "090,Bank,asset,500,\n"
            "200,Sales,asset,,500\n")                       # 200 wrongly typed: Xero 2xx = revenue
    r = _fix(cu, "xero")
    assert _type(co.id, "200") == AccountType.revenue and r["fixed"] == 1
