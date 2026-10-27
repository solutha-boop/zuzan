import types, asyncio
import pytest
from fastapi import HTTPException
from tests.helpers import *
from database import Invoice, InvoiceStatus, Account, JournalLine
import companies as CO, payroll as P, accountant as ACC, portal as PO


def _bal(cid, code):
    a = db.query(Account).filter_by(company_id=cid, code=code).first()
    return round(sum((l.debit or 0) - (l.credit or 0) for l in db.query(JournalLine).filter_by(account_id=a.id)), 2)


def _setup(name):
    co = company(name, "general")
    user = types.SimpleNamespace(company_id=co.id, id=1, role="owner", first_name="B", last_name="B")
    inv = asyncio.run(CO.create_invoice(CO.InvoiceCreate(client_name="Client", description="d", amount=1000), current_user=user, db=db))
    return co, user, inv


def _pay(user, inv, cum, status="paid"):
    asyncio.run(CO.update_invoice(inv.id, CO.InvoiceUpdate(status=status, paid_date="2026-10-22", paid_amount_zar=cum), current_user=user, db=db))
    db.expire_all()
    return db.query(Invoice).filter_by(id=inv.id).first()


def test_part_payment_flow_ledger_and_reports():
    co, user, inv = _setup("pp1")
    assert inv.total_amount == 1150
    i = _pay(user, inv, 500)
    assert i.status == InvoiceStatus.partial and i.paid_amount_zar == 500
    assert _bal(co.id, "1100") == 650 and _bal(co.id, "1000") == 500
    # reports show the balance outstanding
    d = asyncio.run(P.dashboard(current_user=user, db=db))
    assert d["total_outstanding"] == 650
    assert ACC._invoice_summary(co.id, db)["unpaid_total"] == 650
    # second part payment (cumulative) stays partial, ledger moves by the delta only
    i = _pay(user, inv, 800)
    assert i.status == InvoiceStatus.partial
    assert _bal(co.id, "1100") == 350 and _bal(co.id, "1000") == 800
    # final payment settles it
    i = _pay(user, inv, 1150)
    assert i.status == InvoiceStatus.paid
    assert _bal(co.id, "1100") == 0 and _bal(co.id, "1000") == 1150


def test_part_payment_validation_and_plain_mark_paid():
    co, user, inv = _setup("pp2")
    with pytest.raises(HTTPException): _pay(user, inv, 2000)          # more than owed
    with pytest.raises(HTTPException): _pay(user, inv, 0)
    with pytest.raises(HTTPException): _pay(user, inv, None, status="partial")
    _pay(user, inv, 500)
    with pytest.raises(HTTPException): _pay(user, inv, 300)           # below what is already recorded
    # 'mark as paid' with no amount settles the balance and posts it
    i = asyncio.run(CO.update_invoice(inv.id, CO.InvoiceUpdate(status="paid"), current_user=user, db=db))
    db.expire_all(); i = db.query(Invoice).filter_by(id=inv.id).first()
    assert i.status == InvoiceStatus.paid and _bal(co.id, "1100") == 0 and _bal(co.id, "1000") == 1150


def test_part_payment_revert():
    co, user, inv = _setup("pp3")
    _pay(user, inv, 400)
    asyncio.run(CO.update_invoice(inv.id, CO.InvoiceUpdate(status="sent"), current_user=user, db=db))
    db.expire_all()
    assert db.query(Invoice).filter_by(id=inv.id).first().status == InvoiceStatus.sent
    assert _bal(co.id, "1100") == 1150 and _bal(co.id, "1000") == 0


def test_writeoff_part_paid_writes_off_only_the_balance_and_recovery():
    co, user, inv = _setup("pp5")                     # total 1150 incl 150 VAT
    _pay(user, inv, 575)                              # half paid
    asyncio.run(CO.write_off_bad_debt(inv.id, CO.BadDebtWriteOff(reason="Debtor gone"), current_user=user, db=db))
    db.expire_all()
    assert db.query(Invoice).filter_by(id=inv.id).first().status == InvoiceStatus.written_off
    assert _bal(co.id, "1100") == 0                   # nothing left owing
    assert _bal(co.id, "7300") == 500                 # net of the unpaid half
    assert _bal(co.id, "2100") == -75                 # output VAT 150 less VAT 75 on the written-off half
    asyncio.run(CO.recover_bad_debt(inv.id, CO.BadDebtRecovery(), current_user=user, db=db))   # recovers the 575 balance
    db.expire_all()
    i = db.query(Invoice).filter_by(id=inv.id).first()
    assert i.status == InvoiceStatus.paid and i.paid_amount_zar == 1150
    assert _bal(co.id, "1000") == 1150 and _bal(co.id, "7300") == 0


def test_foreign_currency_part_payments():
    co = company("ppfx", "general"); cid = co.id
    user = types.SimpleNamespace(company_id=cid, id=1, role="owner")
    import journal as J, datetime as dt
    J.init_accounts(cid, db)
    i = Invoice(company_id=cid, invoice_number="F1", client_name="US", amount=100, vat_amount=0, total_amount=100, currency="USD",
                exchange_rate=18.0, status=InvoiceStatus.sent, issue_date=dt.datetime.now(), due_date=dt.datetime.now())
    db.add(i); db.commit(); db.refresh(i); J.post_invoice_raised(i, db); db.commit()
    # first 50 USD arrives as R880 and is only a part payment
    asyncio.run(CO.update_invoice(i.id, CO.InvoiceUpdate(status="paid", paid_amount_zar=880, final_payment=False), current_user=user, db=db))
    db.expire_all(); i = db.query(Invoice).filter_by(id=i.id).first()
    assert i.status == InvoiceStatus.partial and _bal(cid, "1100") == 920 and _bal(cid, "1000") == 880
    assert P._balance_zar(i) == 920
    # the rest arrives as R890 (cumulative 1770 vs 1800 carried): settled, R30 realised FX loss
    asyncio.run(CO.update_invoice(i.id, CO.InvoiceUpdate(status="paid", paid_amount_zar=1770), current_user=user, db=db))
    db.expire_all(); i = db.query(Invoice).filter_by(id=i.id).first()
    assert i.status == InvoiceStatus.paid
    assert _bal(cid, "1100") == 0 and _bal(cid, "1000") == 1770 and _bal(cid, "5960") == 30


def test_bank_statement_deposit_matching_the_balance_settles_part_paid_invoice():
    co, user, inv = _setup("pp6")
    inv = _pay(user, inv, 500)
    inv.client_name = "Acme Trading"; db.commit()
    import datetime as dt
    T = CO.BankTransaction
    r = asyncio.run(CO.import_bank_statement(CO.BankImportRequest(bank="fnb", transactions=[
        T(date=dt.date.today().isoformat(), description="ACME TRADING EFT", amount=650, type="credit")]), current_user=user, db=db))
    assert r["credits_matched_to_invoices"] == 1
    db.expire_all(); i = db.query(Invoice).filter_by(id=inv.id).first()
    assert i.status == InvoiceStatus.paid and i.paid_amount_zar == 1150
    assert _bal(co.id, "1100") == 0 and _bal(co.id, "1000") == 1150


def test_portal_charges_balance_only():
    co, user, inv = _setup("pp4")
    inv = _pay(user, inv, 500)
    tok = inv.portal_token
    if tok:
        r = asyncio.run(PO.get_portal_invoice(tok, db=db))
        assert r["balance_due"] == 650 and r["paid_so_far"] == 500


def test_payments_this_month_counts_part_payment_received_now():
    co, user, inv = _setup("pp7")
    _pay(user, inv, 500)
    r = asyncio.run(CO.invoice_payments_this_month(current_user=user, db=db))
    assert r["by_invoice"].get(inv.id) == 500 and r["total"] == 500
    _pay(user, inv, 800)                       # a further 300 this month
    r = asyncio.run(CO.invoice_payments_this_month(current_user=user, db=db))
    assert r["by_invoice"][inv.id] == 800
    asyncio.run(CO.update_invoice(inv.id, CO.InvoiceUpdate(status="sent"), current_user=user, db=db))   # reverted
    r = asyncio.run(CO.invoice_payments_this_month(current_user=user, db=db))
    assert r["total"] == 0
