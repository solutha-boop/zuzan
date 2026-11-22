"""Reversals land on the original date unless the period is closed (2026-11-22).

Deleting a wrong or test document must take it out of the month it was in. A period is closed
when it is on or before the company's lock date, or (payroll) its EMP201 is marked submitted -
then the reversal posts today so a filed return is never changed silently."""
import io, types, asyncio, datetime as dt
from fastapi import UploadFile
from tests.helpers import *
from database import JournalEntry, Company, Emp201Submission
import csv_import as CI, journal as J, companies as CO

H = "Date,Reference,Description,Account Code,Account Name,Debit,Credit\n"
TODAY = dt.datetime.utcnow().date()


def _co(name, text):
    co = company(name, "general")
    cu = types.SimpleNamespace(company_id=co.id, id=1, role="accountant", first_name="S", last_name="G", email="s@x.com")
    J.init_accounts(co.id, db)
    r = asyncio.run(CI.import_journals(file=UploadFile(filename="j.csv", file=io.BytesIO((H + text).encode())), db=db, cu=cu))
    assert not r["errors"], r["errors"]
    return co, cu


SALE = "2026-10-10,S1,Sale,1000,Bank / Cash,1150,\n2026-10-10,S1,Sale,4000,Sales,,1000\n2026-10-10,S1,Sale,2100,VAT Output (Payable to SARS),,150\n"


def _entry(co, ref): return db.query(JournalEntry).filter_by(company_id=co.id, reference=ref).one()
def _rev(e): return db.query(JournalEntry).filter_by(is_reversal_of=e.id).one()


def test_reversal_uses_the_original_date_when_the_period_is_open():
    co, _ = _co("rd1", SALE)
    e = _entry(co, "S1")
    J._post_reversal_for_entry(e, db); db.commit()
    assert _rev(e).date.date() == dt.date(2026, 10, 10)


def test_reversal_posts_today_when_the_period_is_locked():
    co, _ = _co("rd2", SALE)
    co.lock_date = dt.date(2026, 10, 31); db.commit()
    e = _entry(co, "S1")
    J._post_reversal_for_entry(e, db); db.commit()
    d = _rev(e).date.date()
    assert d == TODAY or d == dt.date(2026, 11, 1)          # today, or the first open day if the lock is in the future


def test_entries_after_the_lock_date_still_reverse_on_their_own_date():
    co, _ = _co("rd3", SALE)
    co.lock_date = dt.date(2026, 9, 30); db.commit()
    e = _entry(co, "S1")
    J._post_reversal_for_entry(e, db); db.commit()
    assert _rev(e).date.date() == dt.date(2026, 10, 10)


def test_payroll_reversal_posts_today_once_the_emp201_is_submitted():
    co, _ = _co("rd4", "2026-10-13,P1,Payroll,5100,Salaries (Gross),1000,\n2026-10-13,P1,Payroll,1000,Bank / Cash,,1000\n")
    e = _entry(co, "P1"); e.source = "payroll"; db.commit()
    assert J.reversal_date(e, db).date() == dt.date(2026, 10, 13)
    db.add(Emp201Submission(company_id=co.id, period="2026-10", reference="X", submitted_at=dt.datetime(2026, 11, 6))); db.commit()
    assert J.reversal_date(e, db).date() == TODAY


def test_manual_reverse_endpoint_defaults_to_original_date_and_can_post_today():
    co, cu = _co("rd5", SALE + "2026-10-11,S2,Sale,1000,Bank / Cash,115,\n2026-10-11,S2,Sale,4000,Sales,,100\n2026-10-11,S2,Sale,2100,VAT Output (Payable to SARS),,15\n")
    u = types.SimpleNamespace(company_id=co.id, id=1, role="owner")
    r1 = asyncio.run(J.reverse_entry_endpoint(_entry(co, "S1").id, current_user=u, db=db))
    r2 = asyncio.run(J.reverse_entry_endpoint(_entry(co, "S2").id, date_mode="today", current_user=u, db=db))
    assert r1["reversal_date"] == "2026-10-10" and r2["reversal_date"] == TODAY.isoformat()


def test_auto_reversal_uses_its_reversal_date():
    co, _ = _co("rd6", SALE)
    e = _entry(co, "S1"); e.auto_reverse = True; e.reversal_date = dt.datetime(2026, 11, 1); db.commit()
    J.process_pending_reversals(co.id, db)
    assert _rev(e).date.date() == dt.date(2026, 11, 1)


def test_redate_repairs_reversals_posted_today_dry_run_first():
    co, cu = _co("rd7", SALE + "2026-10-12,S3,Sale,1000,Bank / Cash,230,\n2026-10-12,S3,Sale,4000,Sales,,230\n")
    a, b = _entry(co, "S1"), _entry(co, "S3")
    for e in (a, b):                                          # the old behaviour: dated the day they were posted
        J._post_reversal_for_entry(e, db, date=dt.datetime.utcnow())
    db.commit()
    assert _rev(a).date.date() == TODAY
    dry = asyncio.run(J.redate_reversals(on=TODAY.isoformat(), current_user=cu, db=db))
    assert dry["moved"] == 2 and not dry["applied"] and _rev(a).date.date() == TODAY
    co.lock_date = dt.date(2026, 10, 10); db.commit()        # S1 is now in a closed period: it stays where it is
    done = asyncio.run(J.redate_reversals(on=TODAY.isoformat(), apply=True, current_user=cu, db=db))
    assert done["moved"] == 1 and _rev(b).date.date() == dt.date(2026, 10, 12) and _rev(a).date.date() == TODAY


def test_lock_date_is_saved_cleared_and_validated_on_the_company_profile():
    co = company("rd8", "general")
    u = types.SimpleNamespace(company_id=co.id, id=1, role="accountant")
    asyncio.run(CO.update_company(CO.CompanyUpdate(lock_date="2026-10-31"), current_user=u, db=db))
    assert db.query(Company).get(co.id).lock_date == dt.date(2026, 10, 31)
    assert asyncio.run(CO.get_company(current_user=u, db=db))["lock_date"] == "2026-10-31"
    asyncio.run(CO.update_company(CO.CompanyUpdate(lock_date=""), current_user=u, db=db))
    assert db.query(Company).get(co.id).lock_date is None
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        asyncio.run(CO.update_company(CO.CompanyUpdate(lock_date="31/10/2026"), current_user=u, db=db))
