import datetime as dt, hashlib
import pytest
from starlette.testclient import TestClient
from tests.helpers import *
from database import Invoice, InvoiceStatus, Account, JournalLine
import journal as J, portal as PT, main


def _bal(cid, code):
    a = db.query(Account).filter_by(company_id=cid, code=code).first()
    return round(sum((l.debit or 0) - (l.credit or 0) for l in db.query(JournalLine).filter_by(account_id=a.id)), 2)


def _inv(name, status=InvoiceStatus.sent, total=1150, tok="tok"):
    co = company(name, "general")
    now = dt.datetime.utcnow()
    i = Invoice(company_id=co.id, invoice_number="INV-0001", client_name="Jane Doe", amount=1000, vat_amount=150, total_amount=total,
                status=InvoiceStatus.sent, issue_date=now, due_date=now, portal_token=tok + name)
    db.add(i); db.commit(); db.refresh(i); J.post_invoice_raised(i, db); db.commit()
    if status != InvoiceStatus.sent:
        i.status = status; db.commit()
    return co, i


def _itn(inv, amount="1150.00", sign=True, **over):
    d = {"m_payment_id": inv.portal_token, "pf_payment_id": "123", "payment_status": "COMPLETE", "item_name": f"Invoice {inv.invoice_number}",
         "amount_gross": amount, "merchant_id": PT.PAYFAST_MERCHANT_ID, "custom_str3": ""}
    d.update(over)
    if sign:
        d["signature"] = hashlib.md5(PT._pf_param_string(d, PT.PAYFAST_PASSPHRASE).encode()).hexdigest()
    return d


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(PT, "_pf_validate_remote", lambda data: True)
    return TestClient(main.app)


def _status(inv): db.expire_all(); return db.query(Invoice).get(inv.id).status


def test_signature_uses_given_order_and_url_encoding():
    ps = PT._pf_param_string({"merchant_id": "1", "item_name": "Invoice INV-0001", "amount": "10.00", "empty": ""}, "pass word")
    assert ps == "merchant_id=1&item_name=Invoice+INV-0001&amount=10.00&passphrase=pass+word"      # not alphabetical, '+' for spaces


def test_forged_unsigned_notification_cannot_mark_an_invoice_paid(client):
    co, inv = _inv("pf1")
    r = client.post("/portal/notify", data=_itn(inv, sign=False))
    assert r.status_code == 400 and _status(inv) == InvoiceStatus.sent
    bad = _itn(inv); bad["signature"] = "0" * 32
    assert client.post("/portal/notify", data=bad).status_code == 400 and _status(inv) == InvoiceStatus.sent


def test_short_payment_wrong_merchant_and_unconfirmed_are_rejected(client, monkeypatch):
    co, inv = _inv("pf2")
    assert client.post("/portal/notify", data=_itn(inv, amount="1.00")).status_code == 400
    assert client.post("/portal/notify", data=_itn(inv, merchant_id="99999999")).status_code == 400
    monkeypatch.setattr(PT, "_pf_validate_remote", lambda data: False)
    assert client.post("/portal/notify", data=_itn(inv)).status_code == 400
    def boom(data): raise RuntimeError("network down")
    monkeypatch.setattr(PT, "_pf_validate_remote", boom)
    assert client.post("/portal/notify", data=_itn(inv)).status_code == 503        # PayFast will retry
    assert _status(inv) == InvoiceStatus.sent


def test_genuine_payment_marks_paid_and_posts_the_ledger_once(client):
    co, inv = _inv("pf3")
    assert client.post("/portal/notify", data=_itn(inv)).status_code == 200
    assert _status(inv) == InvoiceStatus.paid and _bal(co.id, "1100") == 0 and _bal(co.id, "1000") == 1150
    assert client.post("/portal/notify", data=_itn(inv)).status_code == 200        # duplicate delivery
    assert _bal(co.id, "1000") == 1150                                             # not booked twice
    assert unbal(co) == 0


def test_payment_on_a_written_off_invoice_is_not_silently_marked_paid(client):
    co, inv = _inv("pf4", status=InvoiceStatus.written_off)
    r = client.post("/portal/notify", data=_itn(inv))
    assert r.status_code == 200 and _status(inv) == InvoiceStatus.written_off


def test_subscription_notification_cannot_be_forged(client, monkeypatch):
    import billing as BL
    from database import Company, SubscriptionStatus
    co = company("pfsub", "general")
    row = db.query(Company).get(co.id); row.subscription_status = SubscriptionStatus.trial; db.commit()

    def itn(sign=True, **over):
        d = {"m_payment_id": f"sub-{co.id}-1700000000", "pf_payment_id": "77", "payment_status": "COMPLETE", "amount_gross": "299.00",
             "merchant_id": PT.PAYFAST_MERCHANT_ID, "token": "evil-token"}
        d.update(over)
        if sign:
            d["signature"] = hashlib.md5(PT._pf_param_string(d, PT.PAYFAST_PASSPHRASE).encode()).hexdigest()
        return d

    st = lambda: (db.expire_all(), db.query(Company).get(co.id))[1]
    assert client.post("/billing/payfast-notify", data=itn(sign=False)).status_code == 200
    assert st().subscription_status == SubscriptionStatus.trial and st().payfast_token != "evil-token"      # forged: nothing happened
    monkeypatch.setattr(PT, "_pf_validate_remote", lambda d: False)
    client.post("/billing/payfast-notify", data=itn()); assert st().subscription_status == SubscriptionStatus.trial
    monkeypatch.setattr(PT, "_pf_validate_remote", lambda d: True)
    client.post("/billing/payfast-notify", data=itn(amount_gross="0.00")); assert st().subscription_status == SubscriptionStatus.trial
    client.post("/billing/payfast-notify", data=itn())                                                        # genuine
    assert st().subscription_status == SubscriptionStatus.active
