"""practice_mcp.py: read-only Claude connector for the practice user's client companies."""
import asyncio, datetime as dt, uuid
import pytest
from fastapi.testclient import TestClient
from tests.helpers import *
from database import User, CompanyMembership, Payslip
import auth, main

TOKEN = "t" * 40


@pytest.fixture()
def setup(monkeypatch):
    tag = uuid.uuid4().hex[:8]
    prac = company(f"mcp-practice-{tag}", "accounting")
    c1 = company(f"Cascade BB {tag}", "hospitality")
    c2 = company(f"Nogemane {tag}", "security")
    other = company(f"Not a client {tag}", "retail")
    u = User(email=f"soso-{tag}@solutha.test", hashed_password=auth.hash_password("x-Strong-1"), first_name="S", last_name="G",
             company_id=prac.id, role="owner")
    db.add(u); db.commit(); db.refresh(u)
    for c in (c1, c2):
        db.add(CompanyMembership(user_id=u.id, company_id=c.id, role="accountant"))
    db.commit()
    monkeypatch.setenv("PRACTICE_MCP_TOKEN", TOKEN)
    monkeypatch.setenv("PRACTICE_MCP_USER_EMAIL", f"SOSO-{tag}@solutha.test")
    return {"prac": prac, "c1": c1, "c2": c2, "other": other, "user": u}


def rpc(client, method, params=None, rid=1, token=TOKEN):
    h = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post("/mcp", json={"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}, headers=h)


def call(client, name, **args):
    r = rpc(client, "tools/call", {"name": name, "arguments": args})
    assert r.status_code == 200
    return r.json()["result"]


def test_auth_and_disabled(setup, monkeypatch):
    c = TestClient(main.app)
    assert rpc(c, "tools/list", token=None).status_code == 401
    assert rpc(c, "tools/list", token="wrong" * 10).status_code == 401
    monkeypatch.setenv("PRACTICE_MCP_TOKEN", "short")
    assert rpc(c, "tools/list").status_code == 503
    assert c.get("/mcp").status_code == 405


def test_initialize_list_and_notification(setup):
    c = TestClient(main.app)
    r = rpc(c, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t"}}).json()
    assert r["result"]["protocolVersion"] == "2025-06-18" and "tools" in r["result"]["capabilities"]
    n = c.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers={"Authorization": f"Bearer {TOKEN}"})
    assert n.status_code == 202
    names = {t["name"] for t in rpc(c, "tools/list").json()["result"]["tools"]}
    assert {"list_clients", "client_snapshot", "debtors_aging", "vat201", "emp201", "payroll_status", "reconciliation_checks"} <= names


def test_list_clients_scoped_to_memberships(setup):
    c = TestClient(main.app)
    import json
    res = call(c, "list_clients")
    ids = {x["company_id"] for x in json.loads(res["content"][0]["text"])}
    assert setup["c1"].id in ids and setup["c2"].id in ids and setup["prac"].id in ids
    assert setup["other"].id not in ids
    denied = call(c, "debtors_aging", company_id=setup["other"].id)
    assert denied["isError"] is True and "not one of" in denied["content"][0]["text"]


def test_reports_are_read_only_and_never_switch_the_users_home_company(setup):
    import json
    c = TestClient(main.app)
    co = setup["c1"]
    e = emp(co, "E1", 20000)
    run(co)
    snap = json.loads(call(c, "client_snapshot", company_id=co.id)["content"][0]["text"])
    assert snap["name"] == co.name and "debtors_aging" in snap and "emp201_last_month" in snap
    this_month = dt.datetime.utcnow().strftime("%Y-%m")
    ps = json.loads(call(c, "payroll_status", company_id=co.id, period=this_month)["content"][0]["text"])
    assert ps["payroll_run"] is True and ps["payslips"] == 1
    bad = call(c, "emp201", company_id=co.id, period="2026-13")
    assert bad["isError"] is True
    db.expire_all()
    assert db.query(User).filter_by(id=setup["user"].id).first().company_id == setup["prac"].id


def test_trial_balance_chart_and_account_activity(setup):
    import json
    c = TestClient(main.app)
    co = setup["c2"]
    emp(co, "E9", 15000)
    run(co)
    tb = json.loads(call(c, "trial_balance", company_id=co.id)["content"][0]["text"])
    assert tb["balanced"] is True and tb["accounts"]
    coa = json.loads(call(c, "chart_of_accounts", company_id=co.id)["content"][0]["text"])
    assert any(a["code"] == tb["accounts"][0]["code"] for a in coa)
    act = json.loads(call(c, "account_activity", company_id=co.id, account_code=tb["accounts"][0]["code"])["content"][0]["text"])
    assert act["account"]["code"] == tb["accounts"][0]["code"] and act["shown"] >= 1
    missing = call(c, "account_activity", company_id=co.id, account_code="ZZZ")
    assert missing["isError"] is True
    other = call(c, "trial_balance", company_id=setup["other"].id)
    assert other["isError"] is True
