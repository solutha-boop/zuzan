"""Plan locks are enforced by the server, not just hidden in the screens; limits, prices and the AI Insights fix."""
import sys, types, asyncio, datetime as dt
import pytest
from starlette.testclient import TestClient
from tests.helpers import *
from database import Invoice, InvoiceStatus, User, PlanType, InviteToken
import auth as AU
import companies as CO
import plans as PL

_n = [0]


def _client():
    sys.modules.pop("main", None)
    import main
    return TestClient(main.app, raise_server_exceptions=False)


def _setup(plan, exempt=False, role="owner"):
    _n[0] += 1
    co = company(f"pg{_n[0]}", "general")
    co.plan = PlanType(plan); co.billing_exempt = exempt; db.commit()
    u = User(company_id=co.id, first_name="F", last_name="L", email=f"pg{_n[0]}@plan-test.com", hashed_password=AU.hash_password("Str0ng-Pass-77"),
             role=role, is_active=True, email_verified=True)
    db.add(u); db.commit(); db.refresh(u)
    h = {"Authorization": "Bearer " + AU.create_token({"user_id": u.id, "company_id": co.id})}
    return co, u, h


GATES = {   # path -> lowest plan that includes it
    "/budgets/?year=2026": "professional",
    "/inventory/": "professional",
    "/purchase-orders/": "professional",
    "/documents/": "business",
    "/api-keys/": "business",
    "/reports/cash-flow-13week": "business",
    "/reports/creditors-aging": "professional",
    "/reports/reconciliation": "professional",
}
ORDER = ["starter", "professional", "business"]


@pytest.mark.parametrize("plan", ORDER)
def test_every_locked_area_is_refused_below_its_plan_and_open_at_or_above(plan):
    c = _client(); co, u, h = _setup(plan)
    for path, need in GATES.items():
        r = c.get(path, headers=h)
        if ORDER.index(plan) < ORDER.index(need):
            assert r.status_code == 403 and "plan" in r.text.lower(), (plan, path, r.status_code)
        else:
            assert r.status_code != 403, (plan, path, r.status_code, r.text[:120])


def test_ai_insights_business_only():
    c = _client()
    for plan, expect_403 in (("starter", True), ("professional", True), ("business", False)):
        co, u, h = _setup(plan)
        r = c.post("/reports/ai-insights", headers=h, json={"period": "x"})
        assert (r.status_code == 403) == expect_403, (plan, r.status_code)


def test_write_calls_are_gated_too_not_just_reads():
    c = _client(); co, u, h = _setup("starter")
    assert c.post("/budgets/", headers=h, json={}).status_code == 403
    assert c.post("/inventory/", headers=h, json={}).status_code == 403
    assert c.delete("/documents/1", headers=h).status_code in (403, 405)


def test_fixed_assets_and_debtor_data_are_open_on_starter():
    c = _client(); co, u, h = _setup("starter")
    assert c.get("/fixed-assets/", headers=h).status_code != 403
    assert c.get("/invoices/", headers=h).status_code == 200


def test_partner_companies_are_not_locked():
    c = _client(); co, u, h = _setup("starter", exempt=True)
    assert c.get("/documents/", headers=h).status_code != 403


def _make_invoices(co, n):
    for i in range(n):
        db.add(Invoice(company_id=co.id, invoice_number=f"X-{co.id}-{i}", client_name="C", description="d", amount=10,
                       vat_amount=0, total_amount=10, status=InvoiceStatus.sent, created_at=dt.datetime.utcnow()))
    db.commit()


def _new_invoice(co):
    user = types.SimpleNamespace(company_id=co.id, id=1, role="owner", first_name="B", last_name="B")
    return asyncio.run(CO.create_invoice(CO.InvoiceCreate(client_name="Z", description="d", amount=100), current_user=user, db=db))


@pytest.mark.parametrize("plan,limit", [("starter", 20), ("professional", 80)])
def test_monthly_invoice_limit(plan, limit):
    co, u, h = _setup(plan)
    _make_invoices(co, limit - 1)
    _new_invoice(co)                                         # the last one allowed
    with pytest.raises(Exception) as e:
        _new_invoice(co)
    assert "limit" in str(getattr(e.value, "detail", e.value)).lower() and str(limit) in str(e.value.detail)


def test_business_invoices_unlimited_in_practice():
    co, u, h = _setup("business")
    _make_invoices(co, 120)
    _new_invoice(co)


def test_recurring_run_cannot_bypass_invoice_limit():
    import recurring_invoices as RI
    co, u, h = _setup("starter")
    _make_invoices(co, 20)
    ri = types.SimpleNamespace(company_id=co.id)
    with pytest.raises(Exception) as e:
        RI._generate_invoice_from_template(ri, db)
    assert getattr(e.value, "status_code", None) == 403


def test_user_limit_counts_members_and_open_invites():
    c = _client(); co, u, h = _setup("starter")              # owner = 1 of 2
    r1 = c.post("/auth/team/invite", headers=h, json={"email": "a@team-test.com", "role": "accountant"})
    assert r1.status_code == 200, r1.text
    r2 = c.post("/auth/team/invite", headers=h, json={"email": "b@team-test.com", "role": "accountant"})
    assert r2.status_code == 403 and "2 users" in r2.text
    # re-inviting the same address is a replacement, not an extra seat
    r3 = c.post("/auth/team/invite", headers=h, json={"email": "a@team-test.com", "role": "accountant"})
    assert r3.status_code == 200


def test_business_invite_allowed_beyond_starter_limit():
    c = _client(); co, u, h = _setup("business")
    for i in range(3):
        assert c.post("/auth/team/invite", headers=h, json={"email": f"m{i}@biz-test.com", "role": "accountant"}).status_code == 200


def test_prices_are_consistent_everywhere():
    import billing, config, email_service
    assert billing.PLAN_PRICES["business"] == {"monthly": 999, "annual": 9990}
    assert config.PLAN_PRICES["business"] == {"monthly": 999, "annual": 9990}
    assert billing.PLAN_PRICES["professional"]["monthly"] == 699 and billing.PLAN_PRICES["starter"]["monthly"] == 399
    assert PL.INVOICE_LIMIT["professional"] == 80 and PL.USER_LIMIT == {"starter": 2, "professional": 5, "business": 20}
