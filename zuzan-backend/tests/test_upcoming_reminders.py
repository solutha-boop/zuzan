import datetime as dt
from tests.helpers import *
from database import Invoice, InvoiceStatus
import billing as B


def _inv(co, num, due_in, status=InvoiceStatus.sent, email="c@example.com"):
    due = dt.datetime.utcnow().replace(hour=12, minute=0, second=0, microsecond=0) + dt.timedelta(days=due_in)
    i = Invoice(company_id=co.id, invoice_number=num, client_name="Cli", client_email=email,
                amount=1000.0, total_amount=1150.0, status=status, due_date=due, issue_date=dt.datetime.utcnow())
    db.add(i); db.commit()
    return i


def _run(monkeypatch):
    sent = []
    monkeypatch.setattr(B, "send_upcoming_invoice_reminder", lambda **kw: sent.append(kw))
    B.send_upcoming_due_reminders()
    return {s["invoice_number"]: s["days_until_due"] for s in sent}


def test_reminders_sent_3_and_1_days_before_only(monkeypatch):
    co = company("upc1", "general")
    for n, d in [("U-3", 3), ("U-1", 1), ("U-2", 2), ("U-0", 0), ("U-7", 7), ("U-NEG", -1)]:
        _inv(co, n, d)
    _inv(co, "U-PAID", 3, status=InvoiceStatus.paid)
    _inv(co, "U-NOMAIL", 1, email=None)
    got = _run(monkeypatch)
    assert got.get("U-3") == 3 and got.get("U-1") == 1
    assert not any(k in got for k in ["U-2", "U-0", "U-7", "U-NEG", "U-PAID", "U-NOMAIL"])


def test_respects_reminders_switch(monkeypatch):
    co = company("upc2", "general")
    co.overdue_reminders_enabled = False; db.commit()
    _inv(co, "UOFF-3", 3)
    assert "UOFF-3" not in _run(monkeypatch)


def test_email_content():
    import email_service as ES
    out = []
    orig = ES.send_email
    ES.send_email = lambda to, subj, html, **k: out.append((subj, html))
    try:
        ES.send_upcoming_invoice_reminder(client_email="a@b.co", client_name="<b>X</b>", company_name="Co & Sons",
            invoice_number="INV-1", amount=1150, days_until_due=1, due_date_str="17 Nov 2026", portal_url="https://p/x")
    finally:
        ES.send_email = orig
    subj, html = out[0]
    assert "due tomorrow" in subj and "R1,150.00" in html and "17 Nov 2026" in html
    assert "<b>X</b>" not in html and "&amp;amp;" not in html
