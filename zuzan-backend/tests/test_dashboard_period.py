"""2026-11-22: the dashboard shows the current financial year by default, uses the same engine as the Management
Pack, and no longer drops imported ledger lines dated after the company's first native invoice/expense."""
import types, asyncio, datetime as dt
from tests.helpers import *
from database import Account, AccountType, Expense, Company
import journal as J, payroll as P


def _setup(name):
    co = company(name, "general")
    user = types.SimpleNamespace(company_id=co.id, id=1, role="owner", first_name="B", last_name="B")
    rev = Account(company_id=co.id, code="4100", name="Imported Sales", type=AccountType.revenue, is_system=False)
    exp = Account(company_id=co.id, code="6100", name="Imported Rent", type=AccountType.expense, is_system=False)
    db.add_all([rev, exp]); db.commit()
    return co, user, rev, exp


def _post(co, when, acct, amount, source, credit_side):
    bank = J.get_account(co.id, "1000", db)
    e = J._make_entry(co.id, dt.datetime.combine(when, dt.time()), f"{source} line", "T", source, None, db)
    if credit_side:      # income: DR bank / CR revenue
        db.add_all([J._line(e.id, bank, debit=amount), J._line(e.id, acct, credit=amount)])
    else:                # cost: DR expense / CR bank
        db.add_all([J._line(e.id, acct, debit=amount), J._line(e.id, bank, credit=amount)])
    db.commit()
    return e


def test_dashboard_defaults_to_financial_year_and_matches_management_pack():
    co, user, rev, exp = _setup("dashfy")
    today = dt.date.today()
    fy_start, fy_end = P._company_fy(db.query(Company).get(co.id), today)
    _post(co, today, rev, 1000, "import", True)                                   # this financial year
    _post(co, fy_start - dt.timedelta(days=10), rev, 5000, "import", True)       # last financial year
    _post(co, today, exp, 300, "import", False)
    d = asyncio.run(P.dashboard(current_user=user, db=db))
    assert d["date_from"] == fy_start.isoformat() and d["date_to"] == today.isoformat()
    assert d["fy_start"] == fy_start.isoformat() and d["fy_end"] == fy_end.isoformat()
    assert d["total_revenue"] == 1000 and d["total_expenses"] == 300
    mg = asyncio.run(P.management_accounts(date_from=d["date_from"], date_to=d["date_to"], current_user=user, db=db))
    assert mg["pl"]["revenue"] == d["total_revenue"] and mg["pl"]["total_expenses"] == d["total_expenses"]
    # a wider period on request
    alld = asyncio.run(P.dashboard(date_from="2000-01-01", date_to=today.isoformat(), current_user=user, db=db))
    assert alld["total_revenue"] == 6000


def test_native_expense_no_longer_hides_later_imported_lines():
    co, user, rev, exp = _setup("dashcut")
    today = dt.date.today()
    fy_start, _ = P._company_fy(db.query(Company).get(co.id), today)
    # one native expense on the first day of the year used to become the "cutover" and drop every
    # imported line dated after it
    db.add(Expense(company_id=co.id, vendor="Test", description="native", amount=115, vat_amount=15,
                   category="Office", expense_date=dt.datetime.combine(fy_start, dt.time())))
    db.commit()
    _post(co, today, rev, 2500, "import", True)
    d = asyncio.run(P.dashboard(current_user=user, db=db))
    assert d["total_revenue"] == 2500
    assert d["total_expenses"] == 100          # the native expense, excl. VAT


def test_manual_journals_count_and_imported_ledgers_get_no_payroll_estimate():
    co, user, rev, exp = _setup("dashman")
    today = dt.date.today()
    _post(co, today, rev, 800, "import", True)
    _post(co, today, exp, 120, "manual", False)            # accountant's adjusting journal
    emp(co, "E1", 20000)                                     # employee on file, but no payslips
    d = asyncio.run(P.dashboard(current_user=user, db=db))
    assert d["total_expenses"] == 120
    assert d["total_payroll"] == 0                          # the imported ledger already carries staff costs
    assert d["expense_breakdown"].get("Imported Rent") == 120
