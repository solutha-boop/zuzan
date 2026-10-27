import io, types, asyncio, datetime as dt
import pytest
from fastapi import UploadFile, HTTPException
from tests.helpers import *
from database import Account, JournalLine, JournalEntry
import csv_import as CI
import journal as J


def _up(text):
    return UploadFile(filename="x.csv", file=io.BytesIO(text.encode("utf-8")))


def _cu(name):
    co = company(name, "general")
    return co, types.SimpleNamespace(company_id=co.id, id=1, role="owner")


def _bal(cid, code):
    a = db.query(Account).filter_by(company_id=cid, code=code).first()
    return round(sum((l.debit or 0) - (l.credit or 0) for l in db.query(JournalLine).filter_by(account_id=a.id)), 2)


def _tb(cu, text, **kw):
    return asyncio.run(CI.import_trial_balance(file=_up(text), as_at=kw.get("as_at"), replace=kw.get("replace", False), db=db, cu=cu))


def test_trial_balance_signs_types_dates_and_out_of_balance_warning():
    co, cu = _cu("ledA")
    r = _tb(cu, "Code,Account Name,Type,Balance\n"
                "1000,Bank,Asset,10000\n"
                "1500,Accumulated Depreciation,Asset,-2000\n"        # negative asset = credit
                "2000,Creditors,Non-current liabilities,3000\n"      # unrecognised-by-table label, still a liability
                "3000,Owner Equity,Equity,5000\n", as_at="2025-02-28")
    assert r["imported"] == 4 and not r["errors"]
    assert _bal(co.id, "1000") == 10000 and _bal(co.id, "1500") == -2000
    assert _bal(co.id, "2000") == -3000 and _bal(co.id, "3000") == -5000
    assert abs(r["balancing_to_opening_equity"]) == 0 and "warning" not in r      # 10000-2000 = 3000+5000
    e = db.query(JournalEntry).filter_by(company_id=co.id, reference="OB-TB").one()
    assert e.date.strftime("%Y-%m-%d") == "2025-02-28"
    assert unbal(co) == 0


def test_trial_balance_flags_out_of_balance_and_unknown_type():
    co, cu = _cu("ledB")
    r = _tb(cu, "Name,Debit,Credit\nBank,1000,\nMystery account,,\nWidgets,500,\nCapital,,1200\n")
    assert r["imported"] == 3                                                     # zero row skipped
    assert abs(r["balancing_to_opening_equity"]) == 300 and "warning" in r
    co2, cu2 = _cu("ledB2")
    r2 = _tb(cu2, "Account,Type,Balance\nSomething odd,,500\n")                   # no type, no code, only a balance
    assert r2["imported"] == 0 and r2["errors"]


def test_reimport_is_blocked_unless_replace():
    co, cu = _cu("ledC")
    csv = "Code,Account Name,Type,Debit,Credit\n1000,Bank,Asset,500,\n3000,Capital,Equity,,500\n"
    _tb(cu, csv)
    with pytest.raises(HTTPException) as ei:
        _tb(cu, csv)
    assert ei.value.status_code == 409
    assert _bal(co.id, "1000") == 500
    _tb(cu, csv, replace=True)                                                    # earlier one reversed, new one posted
    assert _bal(co.id, "1000") == 500 and unbal(co) == 0


def test_profit_loss_negative_amounts_and_unknown_type():
    co, cu = _cu("ledD")
    csv = ("Type,Code,Account Name,Amount\n"
           "Revenue,4000,Sales,10000\n"
           "Revenue,4010,Sales returns,-500\n"                                    # credit note: debit to income
           "Expense,6000,Hall hire,3000\n"
           "Expense,6010,Hall hire refund,-200\n"
           "Gizmo,,Strange,100\n")
    r = asyncio.run(CI.import_profit_loss(file=_up(csv), as_at="2025-02-28", replace=False, db=db, cu=cu))
    assert r["imported"] == 4 and len(r["errors"]) == 1
    assert _bal(co.id, "4000") == -10000 and _bal(co.id, "4010") == 500
    assert _bal(co.id, "6000") == 3000 and _bal(co.id, "6010") == -200
    assert _bal(co.id, "3998") == 6700          # net profit offset keeps the entry balanced
    assert unbal(co) == 0


def _gl(cu, text):
    return asyncio.run(CI.import_general_ledger(file=_up(text), db=db, cu=cu))


def test_journal_import_same_ref_different_dates_not_merged_and_reimport_skipped():
    co, cu = _cu("ledE")
    csv = ("Date,Reference,Description,Account Code,Account Name,Debit,Credit\n"
           "2025-01-31,J1,Hall hire,6000,Hall hire,100,\n2025-01-31,J1,Hall hire,1000,Bank,,100\n"
           "2025-02-28,J1,Hall hire,6000,Hall hire,120,\n2025-02-28,J1,Hall hire,1000,Bank,,120\n"
           "31-13-2025,J2,Bad date,6000,Hall hire,50,\n31-13-2025,J2,Bad date,1000,Bank,,50\n"
           "2025-03-31,J3,Unbalanced,6000,Hall hire,70,\n2025-03-31,J3,Unbalanced,1000,Bank,,60\n")
    r = _gl(cu, csv)
    assert db.query(JournalEntry).filter_by(company_id=co.id, source="import").count() == 2      # two J1s, kept apart
    msgs = " ".join(e["message"] for e in r["errors"])
    assert "J2" in msgs and "date" in msgs and "J3" in msgs and "unbalanced" in msgs
    assert _bal(co.id, "6000") == 220
    r2 = _gl(cu, csv)                                                              # same file again
    assert db.query(JournalEntry).filter_by(company_id=co.id, source="import").count() == 2
    assert _bal(co.id, "6000") == 220 and unbal(co) == 0


def test_imported_asset_is_not_posted_to_an_expense_account_of_the_same_name():
    co, cu = _cu("ledF")
    J.init_accounts(co.id, db); db.commit()                        # seeded chart has expense 5260 'Equipment'
    csv = ("Date,Reference,Description,Account Code,Account Name,Debit,Credit\n"
           "2025-01-31,E1,Buy,1600,Equipment,500,\n2025-01-31,E1,Buy,1000,Bank,,500\n")
    _gl(cu, csv)
    assert _bal(co.id, "5260") == 0 and _bal(co.id, "1600") == 500
