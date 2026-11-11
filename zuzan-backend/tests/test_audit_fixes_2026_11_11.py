"""Fixes from the 2026-11-10 reports/debtors/creditors audit."""
from starlette.testclient import TestClient
from tests.helpers import *
from database import Account, AccountType, JournalEntry, JournalLine, FixedAsset
import csv_import as CI

_n = [0]


def _login():
    import main
    try: main.limiter.enabled = False
    except Exception: pass
    import auth
    auth.limiter.enabled = False
    try: auth.limiter.reset()
    except Exception: pass
    c = TestClient(main.app, raise_server_exceptions=False)
    _n[0] += 1
    r = c.post("/auth/register", json={"company_name": f"Aud{_n[0]}", "first_name": "A", "last_name": "U",
                                       "email": f"aud1111_{_n[0]}@test.local", "password": "Audit-Test-123!"})
    assert r.status_code in (200, 201), r.text
    return c, {"Authorization": f"Bearer {r.json()['access_token']}"}


def _up(c, h, path, text, **params):
    return c.post(path, files={"file": ("x.csv", text.encode("utf-8-sig"), "text/csv")}, headers=h, params=params)


# ── High 1: useful-life header unit ──────────────────────────────────────────
def test_life_header_months_beats_life():
    assert CI._life_header_is_years("Useful Life Months") is False
    assert CI._life_header_is_years("life (months)") is False
    assert CI._life_header_is_years("life_in_months") is False
    assert CI._life_header_is_years("Useful Life Years") is True
    assert CI._life_header_is_years("Effective Life") is True
    assert CI._life_header_is_years("Asset Life") is True


def test_fixed_asset_import_months_column_not_multiplied():
    c, h = _login()
    csv = ("Asset Name,Category,Purchase Date,Cost,Useful Life Months\n"
           "Laptop A,Computer equipment,2026-03-01,12000,36\n")
    pv = _up(c, h, "/import/fixed_assets/preview", csv)
    assert pv.status_code == 200, pv.text
    assert pv.json()["rows"][0]["useful_life_months"] == 36
    r = _up(c, h, "/import/fixed_assets", csv)
    assert r.status_code == 200, r.text
    db = SessionLocal()
    fa = db.query(FixedAsset).filter(FixedAsset.asset_name == "Laptop A").order_by(FixedAsset.id.desc()).first()
    assert fa is not None and fa.useful_life_months == 36
    db.close()


def test_fixed_asset_import_years_column():
    c, h = _login()
    csv = ("Asset Name,Category,Purchase Date,Cost,Useful Life Years\n"
           "Desk B,Office furniture,2026-03-01,6000,6\n")
    r = _up(c, h, "/import/fixed_assets", csv)
    assert r.status_code == 200, r.text
    db = SessionLocal()
    fa = db.query(FixedAsset).filter(FixedAsset.asset_name == "Desk B").order_by(FixedAsset.id.desc()).first()
    assert fa.useful_life_months == 72
    db.close()


# ── Low: wear-and-tear rate stored as a percentage ───────────────────────────
def test_wt_rate_parsed_to_percent():
    assert CI._parse_wt_rate_pct("20%") == 20
    assert CI._parse_wt_rate_pct("20") == 20
    assert CI._parse_wt_rate_pct("0.2") == 20
    assert CI._parse_wt_rate_pct("1") == 100
    assert CI._parse_wt_rate_pct("33.33") == 33.33
    assert CI._parse_wt_rate_pct("") is None and CI._parse_wt_rate_pct("abc") is None


def test_wt_rate_reader_handles_legacy_decimal_and_percent():
    from financial_statements import _wt_rate_pct
    class FA: sars_category = None; category = ""
    a = FA(); a.wear_and_tear_rate = 0.2
    assert abs(_wt_rate_pct(a) - 20.0) < 1e-9
    a.wear_and_tear_rate = 1.0
    assert _wt_rate_pct(a) == 100.0
    a.wear_and_tear_rate = 33.33
    assert _wt_rate_pct(a) == 33.33


# ── Low: "loan" keyword ──────────────────────────────────────────────────────
def test_loan_to_director_is_an_asset():
    assert CI._guess_account_type("Loan to director") == AccountType.asset
    assert CI._guess_account_type("Loans receivable") == AccountType.asset
    assert CI._guess_account_type("Bank loan") == AccountType.liability
    assert CI._guess_account_type("Accounts Payable (A/P)") == AccountType.liability


# ── High 2 / Medium: QuickBooks GL import ────────────────────────────────────
QBO_GL = (
    "Example Co\nGeneral Ledger\nJanuary 2026\n\n"
    ",Date,Transaction Type,Num,Name,Memo/Description,Split,Amount,Balance\n"
    "Checking QBGL,,,,,,,,\n"
    ",2026-01-10,Payment,P-1,Cust QBGL,Receipt,Accounts Receivable (A/R),500.00,500.00\n"
    "Total for Checking QBGL,,,,,,,500.00,\n"
    "Accounts Receivable (A/R),,,,,,,,\n"
    ",2026-01-05,Invoice,1001,Cust QBGL,Consulting,Consulting QBGL,500.00,500.00\n"
    ",2026-01-10,Payment,P-1,Cust QBGL,Receipt,Checking QBGL,-500.00,0.00\n"
    "Total for Accounts Receivable (A/R),,,,,,,0.00,\n"
    "Consulting QBGL,,,,,,,,\n"
    ",2026-01-05,Invoice,1001,Cust QBGL,Consulting,Accounts Receivable (A/R),500.00,500.00\n"
    "Total for Consulting QBGL,,,,,,,500.00,\n"
)


def test_qbo_gl_imports_balanced_and_uses_existing_chart():
    c, h = _login()
    coa = "Number,Account name,Type,Detail type\n1888,Checking QBGL,Bank,Checking\n4888,Consulting QBGL,Income,Service/Fee Income\n"
    assert _up(c, h, "/qbo/accounts", coa).status_code == 200
    r = _up(c, h, "/qbo/general-ledger", QBO_GL)
    assert r.status_code == 200, r.text                 # used to 500 after committing (pick() on list rows)
    body = r.json()
    assert body["imported"] == 4 and not body["errors"], body

    db = SessionLocal()
    rev = db.query(Account).filter(Account.name == "Consulting QBGL").all()
    assert len(rev) == 1 and rev[0].type == AccountType.revenue      # no duplicate "asset" copy
    lines = db.query(JournalLine).filter(JournalLine.account_id == rev[0].id).all()
    assert round(sum(l.credit - l.debit for l in lines), 2) == 500.0  # income credited, not debited
    db.close()

    again = _up(c, h, "/qbo/general-ledger", QBO_GL).json()
    assert again["imported"] == 0                                     # duplicates skipped


def test_qbo_gl_without_chart_classifies_by_name():
    c, h = _login()
    gl = QBO_GL.replace("Consulting QBGL", "Sales QBGL2").replace("Checking QBGL", "Bank QBGL2")
    r = _up(c, h, "/qbo/general-ledger", gl)
    assert r.status_code == 200, r.text
    assert r.json()["imported"] == 4 and not r.json()["errors"], r.json()
    db = SessionLocal()
    sales = db.query(Account).filter(Account.name == "Sales QBGL2").all()
    assert len(sales) == 1 and sales[0].type == AccountType.revenue
    db.close()
