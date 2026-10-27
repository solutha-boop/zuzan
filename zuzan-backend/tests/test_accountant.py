import types, asyncio
import pytest
from tests.helpers import *
from database import User, Company, CompanyMembership, InviteToken
import accountant as AC, auth


def test_onboard_client_invite_link_matches_the_app_and_text_is_escaped(monkeypatch):
    prac = company("practice", "accounting")
    u = User(email="acc@practice.co.za", hashed_password=auth.hash_password("x-Strong-1"), first_name="Ann", last_name="Acc", company_id=prac.id, role="owner")
    db.add(u); db.commit(); db.refresh(u)
    sent = {}
    monkeypatch.setattr(AC, "send_email", lambda to, subject, html, **kw: sent.update(to=to, subject=subject, html=html) or True)
    out = asyncio.run(AC.onboard_client(AC.OnboardClientIn(company_name='Evil <img src=x onerror=1> Ltd', contact_name='<b>Bob</b>', contact_email="bob@client.co.za"),
                                        current_user=u, db=db))
    assert out["email_sent"] is True
    assert "/accept-invite/" + out["invite_token"] in sent["html"] and "?token=" not in sent["html"]
    assert "<img" not in sent["html"] and "<b>Bob" not in sent["html"] and "&lt;img" in sent["html"]
    assert db.query(CompanyMembership).filter_by(user_id=u.id, company_id=out["id"], role="accountant").count() == 1
    assert db.query(InviteToken).filter_by(token=out["invite_token"]).count() == 1
    monkeypatch.setattr(AC, "send_email", lambda *a, **k: False)                     # provider down: must not claim success
    out2 = asyncio.run(AC.onboard_client(AC.OnboardClientIn(company_name="Second Co", contact_name="Sue", contact_email="sue@client.co.za"), current_user=u, db=db))
    assert out2["email_sent"] is False
