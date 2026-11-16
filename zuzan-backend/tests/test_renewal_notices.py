import datetime as dt
from tests.helpers import *
from database import Company, User, SubscriptionStatus
import billing as B


def _sub(name, in_hours, plan="professional", token="tok", parent=None, exempt=False, status=SubscriptionStatus.active):
    co = company(name, "general")
    co.subscription_status = status
    co.payfast_token = token
    co.next_billing_date = dt.datetime.utcnow() + dt.timedelta(hours=in_hours)
    co.parent_company_id = parent
    co.billing_exempt = exempt
    from database import PlanType
    co.plan = PlanType(plan)
    db.add(User(company_id=co.id, email=f"{name}@owner.test", first_name="Own", last_name="Er", role="owner", hashed_password="x"))
    db.commit(); db.refresh(co)
    return co


def _run(monkeypatch):
    import email_service as ES
    sent = []
    monkeypatch.setattr(ES, "send_renewal_notice_email", lambda **kw: sent.append(kw))
    B.send_renewal_notices()
    return {s["company_name"]: s for s in sent}


def test_3_day_and_1_day_windows(monkeypatch):
    _sub("rn_far", 24 * 5)          # 5 days out: nothing yet
    _sub("rn_3d", 24 * 3 - 2)       # ~2d22h: 3-day notice
    _sub("rn_2d", 24 * 2)           # 2 days: still the 3-day notice
    _sub("rn_1d", 20)               # 20h: 1-day notice
    _sub("rn_past", -5)             # already due: charge job's business, no notice
    got = _run(monkeypatch)
    assert "rn_far" not in got and "rn_past" not in got
    assert got["rn_3d"]["days_until"] == 3 and got["rn_2d"]["days_until"] == 3
    assert got["rn_1d"]["days_until"] == 1
    assert got["rn_1d"]["email"] == "rn_1d@owner.test"


def test_sent_once_per_billing_date_then_again_for_1d(monkeypatch):
    co = _sub("rn_once", 24 * 2)
    assert "rn_once" in _run(monkeypatch)
    assert "rn_once" not in _run(monkeypatch)            # restart / second run: no duplicate
    co.next_billing_date = dt.datetime.utcnow() + dt.timedelta(hours=10); db.commit()
    got = _run(monkeypatch)
    assert got["rn_once"]["days_until"] == 1             # 1-day notice is separate
    assert "rn_once" not in _run(monkeypatch)
    # after a successful charge the date moves 30 days on, so next cycle's notices are fresh
    co.next_billing_date = dt.datetime.utcnow() + dt.timedelta(hours=60); db.commit()
    assert "rn_once" in _run(monkeypatch)


def test_skips_ineligible(monkeypatch):
    parent = _sub("rn_parent", 24 * 9)
    _sub("rn_child", 20, parent=parent.id)
    _sub("rn_notoken", 20, token=None)
    _sub("rn_exempt", 20, exempt=True)
    _sub("rn_trial", 20, status=SubscriptionStatus.trial)
    _sub("rn_exp", 20, status=SubscriptionStatus.expired)
    got = _run(monkeypatch)
    assert not any(k in got for k in ["rn_child", "rn_notoken", "rn_exempt", "rn_trial", "rn_exp"])


def test_announced_amount_is_the_charged_amount(monkeypatch):
    co = _sub("rn_amt", 20, plan="business")
    co.payroll_enabled = True; co.payroll_employees = 10; db.commit()
    got = _run(monkeypatch)["rn_amt"]
    amount, plan, cycle = B.subscription_amount(co, db)
    assert got["amount"] == amount == 999 + 230
    assert got["plan"] == "Business"

    posted = {}
    class R:
        status_code = 200; content = b"x"
        def json(self): return {"code": 200, "data": {"response": "pf1"}}
    monkeypatch.setattr(B._requests, "post", lambda url, data=None, **k: (posted.update(data), R())[1])
    B.adhoc_charge(co, db)
    assert posted["amount"] == str(int(amount * 100))


def test_renewal_email_content():
    import email_service as ES
    out = []
    orig = ES.send_email
    ES.send_email = lambda to, subj, html, **k: out.append((to, subj, html))
    try:
        ES.send_renewal_notice_email(first_name="Sam", email="o@x.co", company_name="A & B", plan="Starter",
            billing_cycle="monthly", amount=399, billing_date_str="19 Nov 2026", days_until=1,
            subscribe_url="https://zuzan.co.za/settings?tab=subscription")
    finally:
        ES.send_email = orig
    to, subj, html = out[0]
    assert to == "o@x.co" and "renews tomorrow" in subj and "R399.00" in subj
    assert "19 Nov 2026" in html and "A &amp; B" in html and "&amp;amp;" not in html
    assert 'href="https://zuzan.co.za/settings?tab=subscription"' in html
