import types, datetime as dt
from tests.helpers import *
from database import Invoice, InvoiceStatus, Expense, Account, JournalLine, FixedAsset
import journal as J, financial_statements as FS, fixed_assets as FA


def _bank_ledger(cid):
    a = db.query(Account).filter_by(company_id=cid, code="1000").first()
    return sum((l.debit or 0) - (l.credit or 0) for l in db.query(JournalLine).filter_by(account_id=a.id))


def test_statements_balance_roll_forward_and_reconcile_to_bank():
    co = company("afsco", "general"); cid = co.id
    user = types.SimpleNamespace(company_id=cid, id=1, role="owner")

    def inv(no, amt, d):
        i = Invoice(company_id=cid, invoice_number=no, client_name="C", amount=amt, vat_amount=0, total_amount=amt,
                    status=InvoiceStatus.sent, issue_date=d, due_date=d)
        db.add(i); db.commit(); db.refresh(i); J.post_invoice_raised(i, db); db.commit(); return i

    # FY2026 = 1 Mar 2025 .. 28 Feb 2026
    inv("A", 10000, dt.datetime(2025, 3, 1))            # exactly on the year start (midnight)
    b = inv("B", 5000, dt.datetime(2025, 6, 10))
    b.status = InvoiceStatus.paid; b.paid_date = dt.datetime(2025, 6, 20); b.paid_amount_zar = 5000; db.commit()
    J.post_invoice_paid(b, db); db.commit()
    e = Expense(company_id=cid, vendor="V", amount=2000, vat_amount=0, category="Utilities", expense_date=dt.datetime(2025, 7, 1))
    db.add(e); db.commit(); db.refresh(e); J.post_expense(e, db); db.commit()
    fa = FixedAsset(company_id=cid, asset_number="FA1", asset_name="Laptop", category="Computers", purchase_date=dt.datetime(2025, 8, 1),
                    cost=6000, residual_value=0, useful_life_months=36, depreciation_method="straight_line",
                    accumulated_depreciation=0, status="active")
    db.add(fa); db.commit(); db.refresh(fa); J.post_asset_acquisition(fa, db); db.commit()

    r = FS.annual_financial_statements(year=2026, db=db, current_user=user)
    eq, cf, bs = r["changes_in_equity"], r["cash_flow"], r["balance_sheet"]

    assert bs["balanced"], (bs["total_assets"], bs["total_equity_and_liabilities"])
    # an invoice dated exactly on 1 March belongs to the new year only, not to the opening balances
    assert eq["opening_retained"] == 0
    rolled = round(eq["opening_total"] + eq["net_profit"] + eq["contributions"] - eq["drawings"] + eq["deferred_tax_movement"], 2)
    assert abs(rolled - eq["closing_total"]) < 0.01, (rolled, eq["closing_total"])
    assert cf["reconciles_to_ledger"], (cf["closing_cash"], cf["ledger_closing_cash"])
    assert abs(cf["closing_cash"] - _bank_ledger(cid)) < 0.01
    assert any(l["code"] == "2400" for l in bs["liabilities"]["current"])   # income tax payable (estimate) carried
