"""ZuZan AI chat (/ai/chat) and Business-plan AI insights (/reports/ai-insights).
The AI provider is replaced by a fake so no network call or API key is ever used."""
import sys, types
import pytest
from starlette.testclient import TestClient
from tests.helpers import *
from database import User, Company
import auth as AU


class FakeAnthropic(types.ModuleType):
    calls = []
    raise_error = False
    reply = "  Go to Sales → Invoices.  "

    def __init__(self):
        super().__init__("anthropic")
        outer = self

        class _Msgs:
            def create(self, **kw):
                outer.__class__.calls.append(kw)
                if outer.__class__.raise_error:
                    raise RuntimeError("upstream exploded: sk-ant-SECRET")
                return types.SimpleNamespace(content=[types.SimpleNamespace(text=outer.__class__.reply)])

        class Anthropic:
            def __init__(self, api_key=None):
                self.api_key = api_key
                self.messages = _Msgs()
        self.Anthropic = Anthropic


@pytest.fixture
def ai(monkeypatch):
    FakeAnthropic.calls = []; FakeAnthropic.raise_error = False; FakeAnthropic.reply = "  Go to Sales → Invoices.  "
    monkeypatch.setitem(sys.modules, "anthropic", FakeAnthropic())
    sys.modules.pop("main", None)
    import main
    monkeypatch.setattr(main, "_ANTHROPIC_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    return main, TestClient(main.app, raise_server_exceptions=False)


def _user(co, email):
    u = User(company_id=co.id, first_name="F", last_name="L", email=email, hashed_password=AU.hash_password("Password123"),
             role="owner", is_active=True, email_verified=True)
    db.add(u); db.commit(); db.refresh(u)
    return {"Authorization": "Bearer " + AU.create_token({"user_id": u.id, "company_id": u.company_id})}


def test_chat_needs_a_login(ai):
    main, c = ai
    assert c.post("/ai/chat", json={"message": "hi"}).status_code in (401, 403)
    assert FakeAnthropic.calls == []


def test_chat_returns_the_trimmed_reply_and_sends_only_the_users_own_question(ai):
    main, c = ai
    co = company("ai1", "general"); h = _user(co, "ai1@x.com")
    r = c.post("/ai/chat", json={"message": "How do I create an invoice?", "context": "invoices"}, headers=h)
    assert r.status_code == 200 and r.json() == {"reply": "Go to Sales → Invoices."}
    call = FakeAnthropic.calls[0]
    assert call["model"].startswith("claude-") and call["max_tokens"] <= 600
    assert call["system"] == main.ZUZAN_SYSTEM_PROMPT
    sent = call["messages"]
    assert len(sent) == 1 and sent[0]["role"] == "user" and "How do I create an invoice?" in sent[0]["content"] and "invoices" in sent[0]["content"]
    assert "ai1@x.com" not in str(call) and "ai1" not in sent[0]["content"].replace("invoices", "")      # no company or user data leaves the app


def test_chat_without_a_key_says_so_and_never_calls_out(ai, monkeypatch):
    main, c = ai
    monkeypatch.setattr(main, "_ANTHROPIC_KEY", "")
    h = _user(company("ai2", "general"), "ai2@x.com")
    r = c.post("/ai/chat", json={"message": "hello"}, headers=h)
    assert "not configured" in r.json()["reply"] and FakeAnthropic.calls == []


def test_chat_falls_back_to_built_in_answers_when_the_ai_fails_and_leaks_nothing(ai):
    main, c = ai
    h = _user(company("ai3", "general"), "ai3@x.com")
    FakeAnthropic.raise_error = True
    r = c.post("/ai/chat", json={"message": "How do I record a part payment?"}, headers=h)
    assert r.status_code == 200 and "Partial" in r.json()["reply"] and "sk-ant" not in r.text and "exploded" not in r.text
    assert "Credit Notes" in c.post("/ai/chat", json={"message": "How do I issue a credit note"}, headers=h).json()["reply"]
    assert "ZuZan" in c.post("/ai/chat", json={"message": "tell me a joke"}, headers=h).json()["reply"]          # polite redirect


def test_chat_rejects_empty_and_oversized_messages_before_paying_for_them(ai):
    main, c = ai
    h = _user(company("ai4", "general"), "ai4@x.com")
    assert c.post("/ai/chat", json={"message": ""}, headers=h).status_code == 422
    assert c.post("/ai/chat", json={"message": "x" * 2001}, headers=h).status_code == 422
    assert c.post("/ai/chat", json={"message": "hi", "context": "y" * 101}, headers=h).status_code == 422
    assert c.post("/ai/chat", json={"message": "x" * 2000}, headers=h).status_code == 200
    assert len(FakeAnthropic.calls) == 1


def test_chat_is_rate_limited(ai, monkeypatch):
    main, c = ai
    monkeypatch.setattr(main, "_ANTHROPIC_KEY", "")                 # keep each call instant
    h = _user(company("ai5", "general"), "ai5@x.com")
    codes = [c.post("/ai/chat", json={"message": "hi"}, headers=h).status_code for _ in range(34)]
    assert 429 in codes and codes[0] == 200


def test_the_assistants_facts_match_the_app():
    sys.modules.pop("main", None)
    import main, payroll as P
    s = main.ZUZAN_SYSTEM_PROMPT
    assert f"R{P.UIF_CEIL * 0.01:,.2f}" in s and f"R{P.PRIMARY_REBATE:,}" in s and "R500,000" in s and "15%" in s
    assert "Part payments" in s and "Credit Notes" in s and "s12C" in s
    from config import PLAN_PRICES
    fb = main._keyword_fallback("what plans do you have", "")["reply"]
    for plan in ("starter", "professional", "business"):
        assert f"R{PLAN_PRICES[plan]['monthly']:,}" in fb


def _plan(co, plan):
    from database import PlanType
    c = db.query(Company).get(co.id); c.plan = getattr(PlanType, plan); db.commit()


INSIGHT = {"period": "Oct 2026", "revenue": 100000, "total_expenses": 40000, "gross_profit": 60000, "payroll_cost": 20000, "net_profit": 40000,
           "gross_margin_pct": 60, "net_margin_pct": 40, "outstanding": 15000, "overdue_count": 2, "employee_count": 3,
           "expense_breakdown": {"Rent": 12000}, "trend": [{"month": "Sep", "revenue": 90000, "expenses": 35000, "gross_profit": 55000}]}


def test_insights_are_business_plan_only_and_send_only_the_figures(ai):
    main, c = ai
    co = company("ai6", "general"); h = _user(co, "ai6@x.com")
    _plan(co, "starter")
    assert c.post("/reports/ai-insights", json=INSIGHT, headers=h).status_code == 403 and FakeAnthropic.calls == []
    _plan(co, "business")
    FakeAnthropic.reply = "**Revenue** Up. Good. Do more.\n**Expenses** Rent high. Bad. Renegotiate."
    r = c.post("/reports/ai-insights", json=INSIGHT, headers=h)
    assert r.status_code == 200 and len(r.json()["insights"]) == 2 and r.json()["period"] == "Oct 2026"
    prompt = FakeAnthropic.calls[0]["messages"][0]["content"]
    assert "R100,000" in prompt and "Rent: R12,000" in prompt and "ai6" not in prompt and "@" not in prompt


def test_insights_survive_messy_input_and_hide_provider_errors(ai):
    main, c = ai
    co = company("ai7", "general"); h = _user(co, "ai7@x.com"); _plan(co, "business")
    messy = {**INSIGHT, "trend": [{"month": "Sep"}, {"revenue": "abc"}, "junk"], "expense_breakdown": {"X": "oops"}}
    assert c.post("/reports/ai-insights", json=messy, headers=h).status_code == 200
    assert c.post("/reports/ai-insights", json={**INSIGHT, "period": "p" * 61}, headers=h).status_code == 422
    FakeAnthropic.raise_error = True
    r = c.post("/reports/ai-insights", json=INSIGHT, headers=h)
    assert r.status_code == 500 and "sk-ant" not in r.text and "exploded" not in r.text
    assert c.post("/reports/ai-insights", json=INSIGHT).status_code in (401, 403)


def test_insights_without_a_key_report_unavailable(ai, monkeypatch):
    main, c = ai
    co = company("ai8", "general"); h = _user(co, "ai8@x.com"); _plan(co, "business")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert c.post("/reports/ai-insights", json=INSIGHT, headers=h).status_code == 503
