import types, asyncio, datetime as dt
import pytest
from fastapi import HTTPException
from tests.helpers import *
from database import Invoice, InvoiceStatus, Account, JournalLine, CreditNote
import journal as J, credit_notes as CN


def _bal(cid, code):
    a = db.query(Account).filter_by(company_id=cid, code=code).first()
    return round(sum((l.debit or 0) - (l.credit or 0) for l in db.query(JournalLine).filter_by(account_id=a.id)), 2)


def _inv(cid, amount, vat=0, cur="ZAR", rate=1.0, no="I1"):
    i = Invoice(company_id=cid, invoice_number=no, client_name="Client", amount=amount, vat_amount=vat, total_amount=amount + vat,
                status=InvoiceStatus.sent, issue_date=dt.datetime.utcnow(), due_date=dt.datetime.utcnow(), currency=cur, exchange_rate=rate)
    db.add(i); db.commit(); db.refresh(i); J.post_invoice_raised(i, db); db.commit(); return i


def _mk(user, **kw):
    kw.setdefault("client_name", "Client")
    return asyncio.run(CN.create_credit_note(CN.CreditNoteCreate(**kw), current_user=user, db=db))


def test_credit_note_validation_overcredit_and_delete_reverses_ledger():
    co = company("cnval", "general"); cid = co.id
    user = types.SimpleNamespace(company_id=cid, id=1, role="owner")
    inv = _inv(cid, 1000, vat=150)
    for bad in (dict(amount=0), dict(amount=-5), dict(amount=10, vat_rate=2), dict(amount=10, issue_date="nonsense"), dict(amount=10, invoice_id=99999)):
        with pytest.raises(HTTPException) as ex:
            _mk(user, **bad)
        assert ex.value.status_code in (400, 404), bad
    before_ar, before_rev = _bal(cid, "1100"), _bal(cid, "4000")
    cn = _mk(user, invoice_id=inv.id, amount=400)
    assert cn["vat_amount"] == 60 and cn["total_amount"] == 460
    assert _bal(cid, "1100") == before_ar - 460 and _bal(cid, "4000") == before_rev + 400
    with pytest.raises(HTTPException) as ex:                       # 400 + 700 > 1000 invoiced
        _mk(user, invoice_id=inv.id, amount=700)
    assert ex.value.status_code == 400
    _mk(user, invoice_id=inv.id, amount=600)                       # exactly the rest is fine
    # deleting a credit note must put the ledger back
    asyncio.run(CN.delete_credit_note(cn["id"], current_user=user, db=db))
    assert db.query(CreditNote).filter_by(id=cn["id"]).first() is None
    assert _bal(cid, "1100") == before_ar - 690 and _bal(cid, "4000") == before_rev + 600
    assert unbal(co) == 0


def test_foreign_currency_credit_note_is_converted_to_rand():
    co = company("cnfx", "general"); cid = co.id
    user = types.SimpleNamespace(company_id=cid, id=1, role="owner")
    inv = _inv(cid, 100, vat=0, cur="USD", rate=18.5, no="U1")
    with pytest.raises(HTTPException):                              # no linked invoice -> no rate
        _mk(user, amount=10, currency="USD")
    ar0 = _bal(cid, "1100")
    cn = _mk(user, invoice_id=inv.id, amount=40, currency="USD", vat_rate=0)
    assert cn["currency"] == "ZAR" and cn["amount"] == 740.0 and "USD 40.00" in (cn["description"] or "")
    assert _bal(cid, "1100") == round(ar0 - 740, 2)
    with pytest.raises(HTTPException):                              # remaining USD 60 = R1110; R1200 is too much
        _mk(user, invoice_id=inv.id, amount=1200 / 18.5, currency="USD", vat_rate=0)
