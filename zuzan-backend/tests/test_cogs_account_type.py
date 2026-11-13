"""Audit 2026-11-11: the cogs AccountType (6b071ac) must behave as a debit-normal P&L account everywhere."""
import io, types, asyncio
from fastapi import UploadFile
from tests.helpers import *
from database import Account, AccountType, JournalLine
import csv_import as CI
import journal as J
import payroll as P


def _up(text):
    return UploadFile(filename="x.csv", file=io.BytesIO(text.encode("utf-8")))


def _cu(name):
    co = company(name, "general")
    return co, types.SimpleNamespace(company_id=co.id, id=1, role="owner")


def _acct(cid, code):
    return db.query(Account).filter_by(company_id=cid, code=code).first()


def _net_dr(cid, code):
    a = _acct(cid, code)
    return round(sum((l.debit or 0) - (l.credit or 0) for l in db.query(JournalLine).filter_by(account_id=a.id)), 2)


def test_signed_dr_cr_cogs_is_debit_normal():
    assert CI._signed_dr_cr(AccountType.cogs, 500.0) == (500.0, 0.0)
    assert CI._signed_dr_cr(AccountType.cogs, -50.0) == (0.0, 50.0)


def test_profit_loss_import_accepts_cost_of_sales_and_balance_sheet_balances():
    co, cu = _cu("cogsA")
    csv = ("Type,Code,Account Name,Amount\n"
           "Revenue,4100,Product sales,10000\n"
           "Cost of Sales,5010,Purchases,4000\n"
           "Expense,6100,Hall hire,1000\n")
    r = asyncio.run(CI.import_profit_loss(file=_up(csv), as_at="2025-02-28", replace=False, db=db, cu=cu))
    assert r["imported"] == 3 and not r["errors"], r
    a = _acct(co.id, "5010")
    assert a.type == AccountType.cogs
    assert _net_dr(co.id, "5010") == 4000                       # debit side
    assert J.account_balance(a, db) == 4000                     # debit-normal balance, not -4000
    assert unbal(co) == 0
    bs = asyncio.run(P.balance_sheet(current_user=cu, db=db))
    assert bs["balanced"], bs["imbalance"]


def test_trial_balance_balance_column_posts_cogs_as_debit():
    co, cu = _cu("cogsB")
    r = asyncio.run(CI.import_trial_balance(file=_up(
        "Code,Account Name,Type,Balance\n"
        "1000,Bank,Asset,6000\n"
        "5010,Cost of sales,Cost of Sales,4000\n"
        "4100,Sales,Revenue,10000\n"), as_at="2025-02-28", replace=False, db=db, cu=cu))
    assert r["imported"] == 3 and not r["errors"], r
    assert _acct(co.id, "5010").type == AccountType.cogs
    assert _net_dr(co.id, "5010") == 4000
    assert abs(r["balancing_to_opening_equity"]) == 0
    tb = asyncio.run(J.trial_balance(current_user=cu, db=db))
    assert tb["balanced"]
    row = next(x for x in tb["accounts"] if x["code"] == "5010")
    assert row["type"] == "cogs" and row["balance"] == 4000
    bs = asyncio.run(P.balance_sheet(current_user=cu, db=db))
    assert bs["balanced"], bs["imbalance"]


def test_gl_import_expenses_empty_shape_has_cogs_total():
    co, _ = _cu("cogsC")
    out = P._gl_import_expenses(db, co.id)
    assert "cogs_total" in out


# ── audit 2026-11-12 low items ──────────────────────────────────────────────
def test_xero_migrate_types_cost_of_sales_as_cogs_not_revenue():
    import xero_migrate as X
    for text in ("Direct Costs", "Cost of Sales", "Cost of Goods Sold", "COGS"):
        assert X.classify_account_type(text, "310") == AccountType.cogs, text
    assert X.classify_account_type("Sales", "200") == AccountType.revenue
    assert X.classify_account_type("Other Income", "260") == AccountType.revenue
    assert X.classify_account_type("Overhead", "400") == AccountType.expense
    assert X.classify_account_type("Expense", "400") == AccountType.expense


def test_custom_coa_cost_of_sales_account_syncs_as_cogs():
    from database import CompanyAccount
    co, cu = _cu("cogsD")
    db.add(CompanyAccount(company_id=co.id, code="5077", name="Packaging", group="Cost of Sales"))
    db.add(CompanyAccount(company_id=co.id, code="6077", name="Sundry", group="Expenses"))
    db.commit()
    assert J.expense_account(co.id, "5077 - Packaging", db).type == AccountType.cogs
    assert J.expense_account(co.id, "6077 - Sundry", db).type == AccountType.expense
