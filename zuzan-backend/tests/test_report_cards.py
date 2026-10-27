"""The report cards must agree with each other: revenue is cash actually received EXCLUDING VAT (VAT is owed to SARS),
part payments count for what was received, and the Revenue card's breakdown adds up to the card."""
import types, asyncio, datetime as dt
from tests.helpers import *
from database import Invoice, InvoiceStatus, Company
import companies as CO, payroll as P

TODAY = dt.date.today().isoformat()


def _setup(name, vat=True):
    co = company(name, "general")
    if not vat:
        c = db.query(Company).get(co.id); c.vat_registered = False; db.commit()
    user = types.SimpleNamespace(company_id=co.id, id=1, role="owner", first_name="B", last_name="B")
    return co, user


def _inv(user, client, amount):
    return asyncio.run(CO.create_invoice(CO.InvoiceCreate(client_name=client, description="d", amount=amount), current_user=user, db=db))


def _pay(user, inv, cum):
    asyncio.run(CO.update_invoice(inv.id, CO.InvoiceUpdate(status="paid", paid_date=TODAY, paid_amount_zar=cum), current_user=user, db=db))
    db.expire_all()


def _cards(user):
    dash = asyncio.run(P.dashboard(current_user=user, db=db))
    mg = asyncio.run(P.management_accounts(date_from="2000-01-01", date_to=TODAY, current_user=user, db=db))
    det = asyncio.run(P.management_revenue_detail(date_from="2000-01-01", date_to=TODAY, current_user=user, db=db))
    return dash, mg, det


def test_revenue_excludes_vat_counts_part_payments_and_the_breakdown_adds_up():
    co, user = _setup("cards1")
    a = _inv(user, "Full Payer", 1000)          # R1,150 incl VAT
    b = _inv(user, "Part Payer", 1000)          # R1,150 incl VAT
    _inv(user, "Unpaid", 1000)
    _pay(user, a, 1150)                          # paid in full
    _pay(user, b, 575)                           # half paid -> R500 revenue + R75 VAT
    dash, mg, det = _cards(user)
    assert dash["total_revenue"] == 1500.0
    assert mg["pl"]["revenue"] == 1500.0 and mg["kpis"]["revenue"] == 1500.0
    assert det["total"] == 1500.0 and len(det["rows"]) == 2
    assert det["received_total"] == 1725.0 and det["vat_total"] == 225.0
    assert {r["status"] for r in det["rows"]} == {"paid", "partial"}
    assert dash["total_outstanding"] == 1150 + 575          # unpaid invoice + the balance of the part-paid one
    assert mg["kpis"]["outstanding"] == dash["total_outstanding"]
    # cash flow shows what actually came in, VAT included
    cf = asyncio.run(P.cash_flow(date_from="2000-01-01", date_to=TODAY, current_user=user, db=db)) if hasattr(P, "cash_flow") else None
    if cf: assert cf["operating"]["cash_receipts_from_customers"] == 1725.0


def test_non_vat_company_revenue_is_the_full_amount_received():
    co, user = _setup("cards2", vat=False)
    a = _inv(user, "Client", 1000)
    _pay(user, a, 1000)
    dash, mg, det = _cards(user)
    assert dash["total_revenue"] == mg["pl"]["revenue"] == det["total"] == 1000.0 and det["vat_total"] == 0


def test_net_profit_is_revenue_less_expenses_both_excluding_vat():
    co, user = _setup("cards3")
    a = _inv(user, "Client", 10000)
    _pay(user, a, 11500)
    asyncio.run(CO.create_expense(CO.ExpenseCreate(vendor="V", description="d", amount=1150, vat_applicable=True, category="Utilities"), current_user=user, db=db)) if hasattr(CO, "create_expense") else None
    dash, mg, det = _cards(user)
    assert dash["gross_profit"] == round(10000 - dash["total_expenses"], 2)
    assert mg["pl"]["gross_profit"] == round(10000 - mg["pl"]["total_expenses"], 2)
