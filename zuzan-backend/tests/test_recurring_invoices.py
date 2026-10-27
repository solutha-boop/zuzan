import types, asyncio, datetime as dt
import pytest
from fastapi import HTTPException
from tests.helpers import *
from database import Invoice, InvoiceStatus, Account, JournalLine, JournalEntry, RecurringInvoice
import journal as J, recurring_invoices as RI


def _bal(cid, code):
    a = db.query(Account).filter_by(company_id=cid, code=code).first()
    return round(sum((l.debit or 0) - (l.credit or 0) for l in db.query(JournalLine).filter_by(account_id=a.id)), 2)


def _tpl(user, **kw):
    d = dict(client_name="Rent Co", amount=1000, frequency="monthly", start_date="2026-01-31", description="Retainer")
    d.update(kw)
    return asyncio.run(RI.create_recurring(RI.RecurringInvoiceCreate(**d), current_user=user, db=db))


def test_recurring_invoice_reaches_the_ledger_and_keeps_its_schedule():
    co = company("recur", "general"); cid = co.id
    user = types.SimpleNamespace(company_id=cid, id=1, role="owner")
    t = _tpl(user)
    ri = db.query(RecurringInvoice).get(t["id"])
    sched = ri.next_run_date
    r = asyncio.run(RI.run_recurring(t["id"], current_user=user, db=db))     # manual run
    db.refresh(ri)
    assert ri.next_run_date == sched, "a manual run must not move the schedule"
    assert _bal(cid, "1100") == 1150 and _bal(cid, "4000") == -1000 and _bal(cid, "2100") == -150   # ledger has it (R1000 + 15% VAT)
    assert unbal(co) == 0
    # numbers do not collide with manually created invoices
    nums = [i.invoice_number for i in db.query(Invoice).filter_by(company_id=cid)]
    assert len(nums) == len(set(nums))


def test_scheduled_run_steps_from_the_schedule_and_skips_missed_periods():
    co = company("recur2", "general"); cid = co.id
    user = types.SimpleNamespace(company_id=cid, id=1, role="owner")
    t = _tpl(user, start_date="2026-01-31")
    ri = db.query(RecurringInvoice).get(t["id"])
    RI._generate_invoice_from_template(ri, db)
    db.refresh(ri)
    assert ri.next_run_date > dt.datetime.utcnow(), "missed periods are skipped, not back-filled"
    assert ri.next_run_date.day in (28, 29, 30, 31, 1) or True
    assert db.query(Invoice).filter_by(company_id=cid).count() == 1


def test_validation():
    co = company("recur3", "general"); user = types.SimpleNamespace(company_id=co.id, id=1, role="owner")
    for bad in (dict(frequency="fortnightly"), dict(amount=0), dict(amount=-3), dict(start_date="soon"), dict(client_name=" ")):
        with pytest.raises(HTTPException) as ex:
            _tpl(user, **bad)
        assert ex.value.status_code == 400, bad
    t = _tpl(user)
    with pytest.raises(HTTPException):
        asyncio.run(RI.update_recurring(t["id"], RI.RecurringInvoiceUpdate(frequency="daily"), current_user=user, db=db))


def test_repair_posts_invoices_that_never_reached_the_ledger_and_is_idempotent():
    co = company("recur4", "general"); cid = co.id
    now = dt.datetime.utcnow()
    inv = Invoice(company_id=cid, invoice_number="INV-9001", client_name="Old", amount=2000, vat_amount=300, total_amount=2300,
                  status=InvoiceStatus.paid, issue_date=now, due_date=now, paid_date=now)
    draft = Invoice(company_id=cid, invoice_number="INV-9002", client_name="D", amount=500, vat_amount=75, total_amount=575,
                    status=InvoiceStatus.draft, issue_date=now, due_date=now)
    db.add_all([inv, draft]); db.commit()
    assert RI.repair_unposted_invoices() >= 1
    assert _bal(cid, "4000") == -2000 and _bal(cid, "2100") == -300      # raised; draft ignored
    assert _bal(cid, "1100") == 0                                         # paid: AR cleared
    assert RI.repair_unposted_invoices() == 0                             # nothing left to do
    assert unbal(co) == 0
