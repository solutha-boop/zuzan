import sys, types, datetime as dt
import pytest
from sqlalchemy import func
from starlette.testclient import TestClient
from tests.helpers import *
from database import (User, Company, Invoice, InvoiceStatus, Expense, Employee, Customer, Supplier, Quote, InventoryItem,
                      PurchaseOrder, CompanyMembership, FixedAsset)
import auth as AU

MARK = "SECRETMARKERA"


def _client():
    sys.modules.pop("main", None)
    import main
    return main.app, TestClient(main.app, raise_server_exceptions=False)


def _user(co, email, role="owner", pw="Password123", active=True):
    u = User(company_id=co.id, first_name="F", last_name="L", email=email, hashed_password=AU.hash_password(pw),
             role=role, is_active=active, email_verified=True)
    db.add(u); db.commit(); db.refresh(u); return u


def _hdr(u, company_id=None):
    return {"Authorization": "Bearer " + AU.create_token({"user_id": u.id, "company_id": company_id or u.company_id})}


# ── password reset / login ────────────────────────────────────────────────────

def test_forgot_password_is_case_insensitive_and_does_not_reveal_who_has_an_account():
    app, c = _client()
    co = company("authA", "general")
    u = _user(co, "Mixed.Case@Example.com")                      # stored as typed, as older accounts are
    known = c.post("/auth/forgot-password", json={"email": "mixed.case@example.com"})
    unknown = c.post("/auth/forgot-password", json={"email": "nobody@example.com"})
    assert known.status_code == unknown.status_code == 200 and known.json() == unknown.json()
    db.expire_all()
    code = db.query(User).filter_by(id=u.id).one().reset_token
    assert code                                                    # a code really was issued to the mixed-case account
    assert c.post("/auth/reset-password", json={"token": code, "new_password": "short"}).status_code == 400
    assert c.post("/auth/reset-password", json={"token": code, "new_password": "BrandNewPass1"}).status_code == 200
    assert c.post("/auth/reset-password", json={"token": code, "new_password": "BrandNewPass2"}).status_code == 400   # code is single use
    assert c.post("/auth/login", json={"email": "MIXED.case@example.com", "password": "BrandNewPass1"}).status_code == 200


def test_deactivated_user_cannot_log_in_or_use_an_old_token():
    app, c = _client()
    co = company("authB", "general")
    u = _user(co, "gone@example.com", role="accountant")
    h = _hdr(u)
    assert c.get("/auth/team", headers=h).status_code == 200
    u.is_active = False; db.commit()
    assert c.post("/auth/login", json={"email": "gone@example.com", "password": "Password123"}).status_code == 401
    assert c.get("/auth/team", headers=h).status_code == 401
    assert c.get("/auth/team").status_code in (401, 403)             # no token at all
    assert c.get("/auth/team", headers={"Authorization": "Bearer not.a.token"}).status_code == 401


# ── team: roles, outside accountants, re-invites ───────────────────────────────

def test_roles_limit_what_a_user_can_do_to_the_team():
    app, c = _client()
    co = company("authC", "general")
    owner = _user(co, "own@c.com", "owner"); acct = _user(co, "acc@c.com", "accountant"); emp_ = _user(co, "emp@c.com", "employee")
    assert c.post("/auth/team/invite", headers=_hdr(acct), json={"email": "x@y.com", "role": "admin"}).status_code == 403
    assert c.delete(f"/auth/team/{emp_.id}", headers=_hdr(emp_)).status_code == 403
    assert c.patch(f"/auth/team/{emp_.id}", headers=_hdr(acct), json={"role": "admin"}).status_code == 403
    assert c.get("/auth/audit-log", headers=_hdr(emp_)).status_code == 403
    r = c.patch(f"/auth/team/{acct.id}", headers=_hdr(owner), json={"role": "superuser"})
    assert r.status_code == 400
    assert c.delete(f"/auth/team/{owner.id}", headers=_hdr(owner)).status_code == 400            # owner cannot be removed


def test_outside_accountant_is_visible_and_can_be_removed_without_killing_their_own_account():
    app, c = _client()
    client_co = company("authD1", "general"); firm = company("authD2", "general")
    owner = _user(client_co, "owner@d1.com", "owner")
    pro = _user(firm, "pro@d2.com", "owner")                                    # accountant whose home is his own firm
    db.add(CompanyMembership(user_id=pro.id, company_id=client_co.id, role="accountant")); db.commit()
    team = c.get("/auth/team", headers=_hdr(owner)).json()
    assert any(m["email"] == "pro@d2.com" and m.get("external") for m in team)
    # he can work in the client company...
    assert c.get("/auth/team", headers=_hdr(pro, client_co.id)).status_code == 200
    # ...until the owner removes him
    assert c.delete(f"/auth/team/{pro.id}", headers=_hdr(owner)).status_code == 200
    assert not any(m["email"] == "pro@d2.com" for m in c.get("/auth/team", headers=_hdr(owner)).json())
    db.expire_all()
    assert db.query(User).filter_by(id=pro.id).one().is_active is True            # his own firm account is untouched
    # a stale token for the client company now falls back to his own firm, not the client's data
    me = c.get("/auth/team", headers=_hdr(pro, client_co.id)).json()
    assert all(m["email"] != "owner@d1.com" for m in me)


def test_removed_member_can_be_invited_back():
    app, c = _client()
    co = company("authE", "general")
    owner = _user(co, "o@e.com", "owner"); m = _user(co, "Back@E.com", "accountant")
    assert c.delete(f"/auth/team/{m.id}", headers=_hdr(owner)).status_code == 200
    assert c.post("/auth/team/invite", headers=_hdr(owner), json={"email": "back@e.com", "role": "admin"}).status_code == 200
    from database import InviteToken
    tok = db.query(InviteToken).filter_by(company_id=co.id, email="back@e.com").one().token
    r = c.post("/auth/accept-invite", json={"token": tok, "first_name": "B", "last_name": "K", "password": "Whatever123"})
    assert r.status_code == 200, r.text
    db.expire_all()
    u = db.query(User).filter_by(id=m.id).one()
    assert u.is_active and u.role == "admin"
    assert db.query(User).filter(func.lower(User.email) == "back@e.com").count() == 1      # no duplicate account


# ── cross-company isolation ───────────────────────────────────────────────────

_SEED = {}


def _seed_a():
    if "v" in _SEED:
        a, b, ua, ub = _SEED["v"]
        return db.get(Company, a.id), db.get(Company, b.id), db.get(User, ua.id), db.get(User, ub.id)
    _SEED["v"] = _seed_a_once()
    return _SEED["v"]


def _seed_a_once():
    a = company("isoA", "general"); b = company("isoB", "general")
    ua = _user(a, "a@iso.com"); ub = _user(b, "b@iso.com")
    now = dt.datetime.utcnow()
    inv = Invoice(company_id=a.id, invoice_number="ISO-1", client_name=MARK, description=MARK, amount=100, vat_amount=15,
                  total_amount=115, status=InvoiceStatus.sent, issue_date=now, due_date=now)
    db.add_all([inv,
                Expense(company_id=a.id, vendor=MARK, description=MARK, amount=50, vat_amount=0, category=MARK),
                Employee(company_id=a.id, first_name=MARK, last_name="Z", gross_salary=1000, is_active=True, employee_number=MARK),
                Customer(company_id=a.id, name=MARK), Supplier(company_id=a.id, name=MARK),
                Quote(company_id=a.id, quote_number="Q-ISO", client_name=MARK, amount=10, total_amount=10),
                InventoryItem(company_id=a.id, name=MARK, sku=MARK)])
    db.commit()
    return a, b, ua, ub


def test_company_b_cannot_read_company_a_records_through_any_get_route():
    app, c = _client()
    a, b, ua, ub = _seed_a()
    hb = _hdr(ub)
    assert MARK in c.get("/invoices/", headers=_hdr(ua)).text                 # sanity: the owner does see their own data
    import re
    leaks = []; calls = 0
    ids = range(1, 25)
    for rpath, ops in app.openapi()["paths"].items():
        if "get" not in ops:
            continue
        params = re.findall(r"\{(\w+)(?::\w+)?\}", rpath)
        if len(params) > 1 or any(not p.endswith("id") for p in params):
            continue
        for i in (ids if params else [None]):
            path = rpath if not params else re.sub(r"\{\w+(?::\w+)?\}", str(i), rpath)
            if any(x in path for x in ("/docs", "/openapi", "/redoc")):
                continue
            try:
                resp = c.get(path, headers=hb); calls += 1
            except Exception:
                continue
            if MARK in resp.text:
                leaks.append(f"{path} -> {resp.status_code}")
            if not params:
                break
    assert calls > 100, calls
    assert not leaks, "Company B can read Company A data via:\n" + "\n".join(leaks[:20])


def test_company_b_cannot_change_or_delete_company_a_records():
    app, c = _client()
    a, b, ua, ub = _seed_a()
    hb = _hdr(ub)
    import re
    def snapshot():
        db.expire_all()
        return (db.query(Invoice).filter_by(company_id=a.id).count(), db.query(Expense).filter_by(company_id=a.id).count(),
                db.query(Employee).filter_by(company_id=a.id, first_name=MARK).count(), db.query(Customer).filter_by(company_id=a.id).count(),
                db.query(Supplier).filter_by(company_id=a.id).count(), db.query(Quote).filter_by(company_id=a.id).count(),
                db.query(InventoryItem).filter_by(company_id=a.id).count(),
                [(i.client_name, i.status, i.total_amount) for i in db.query(Invoice).filter_by(company_id=a.id)],
                [(x.vendor, x.amount) for x in db.query(Expense).filter_by(company_id=a.id)],
                [(x.name) for x in db.query(Customer).filter_by(company_id=a.id)])
    before = snapshot()
    calls = 0
    for rpath, ops in app.openapi()["paths"].items():
        params = re.findall(r"\{(\w+)(?::\w+)?\}", rpath)
        if len(params) != 1 or not params[0].endswith("id"):
            continue
        if rpath.startswith("/auth") or "/team" in rpath:
            continue
        for i in range(1, 25):
            path = re.sub(r"\{\w+(?::\w+)?\}", str(i), rpath)
            for m in set(ops) & {"delete", "put", "patch"}:
                c.request(m.upper(), path, headers=hb, json={"client_name": "HACKED", "vendor": "HACKED", "name": "HACKED", "amount": 1, "status": "paid"})
                calls += 1
    assert calls > 200, calls
    assert snapshot() == before


# ── payment webhooks cannot be spoofed ────────────────────────────────────────

def test_hand_made_payfast_posts_cannot_activate_plans_or_unlock_the_afs(monkeypatch):
    monkeypatch.delenv("PORTAL_IPN_SKIP_SIGNATURE", raising=False)
    monkeypatch.delenv("PAYFAST_SANDBOX", raising=False)            # unset = the "sandbox" default that used to skip the checks
    app, c = _client()
    from database import SubscriptionStatus, AfsPayment
    co = company("payX", "general")
    co.subscription_status = SubscriptionStatus.expired; db.commit()
    r = c.post("/payments/notify", data={"m_payment_id": "1", "payment_status": "COMPLETE", "custom_str1": str(co.id),
                                         "custom_str2": "enterprise", "custom_str3": "annual", "amount_gross": "1.00"})
    assert r.status_code == 410
    c.post("/billing/payfast-notify", data={"m_payment_id": f"sub-{co.id}-1", "payment_status": "COMPLETE", "amount_gross": "1.00",
                                            "custom_str2": "enterprise"})
    c.post("/billing/afs-notify", data={"m_payment_id": f"afs-{co.id}-2026", "payment_status": "COMPLETE", "amount_gross": "1.00"})
    db.expire_all()
    assert db.get(Company, co.id).subscription_status == SubscriptionStatus.expired
    assert db.query(AfsPayment).filter_by(company_id=co.id).count() == 0
