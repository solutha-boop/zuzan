import types, asyncio, datetime as dt
from tests.helpers import *
from database import Invoice, InvoiceStatus, Expense, CreditNote
import payroll as P

D = dt.datetime(2026, 8, 10)
_n = [0]


def _u(co): return types.SimpleNamespace(company_id=co.id, id=1, role="owner")


def inv(co, amt, vat, status=InvoiceStatus.sent, cur="ZAR", rate=1, supply=None, date=D):
    _n[0] += 1
    i = Invoice(company_id=co.id, invoice_number=f"V{_n[0]}", client_name="C", amount=amt, vat_amount=vat,
                total_amount=amt + (vat or 0), currency=cur, exchange_rate=rate, status=status, issue_date=date, supply_type=supply)
    db.add(i); db.commit(); return i


def exp(co, amt, vat, use=None, date=D, cat="Office"):
    e = Expense(company_id=co.id, vendor="V", amount=amt, vat_amount=vat, category=cat, expense_date=date, vat_use=use)
    db.add(e); db.commit(); return e


def vat(co, period="2026-08", months=1):
    return asyncio.run(P.vat201(current_user=_u(co), db=db, period=period, months=months))


def test_basic_standard_zero_and_input():
    co = company("vat1", "general")
    inv(co, 1000, 150); inv(co, 500, 0, supply="zero_rated"); inv(co, 800, 120, status=InvoiceStatus.partial)
    inv(co, 999, 149.85, status=InvoiceStatus.draft)                       # drafts never count
    inv(co, 100, 15, date=dt.datetime(2026, 7, 31))                        # other period
    exp(co, 115, 15); exp(co, 100, 0)                                      # explicit no-VAT expense claims nothing
    r = vat(co)
    assert r["output"]["field_4a_output_vat"] == 270 and r["output"]["field_1a_standard_supplies_excl_vat"] == 1800
    assert r["output"]["field_1b_zero_rated_supplies"] == 500 and r["output"]["invoice_count"] == 3
    assert r["input"]["field_14_input_vat"] == 15 and r["net"]["field_15_net_vat"] == 255 and r["net"]["status"] == "payable"


def test_foreign_invoice_is_converted_and_credit_note_reduces_output():
    co = company("vat2", "general")
    inv(co, 100, 15, cur="USD", rate=18)                                   # R1800 + R270 VAT
    r = vat(co)
    assert r["output"]["field_1a_standard_supplies_excl_vat"] == 1800 and r["output"]["field_4a_output_vat"] == 270
    db.add(CreditNote(company_id=co.id, credit_note_number="CN1", client_name="C", amount=1000, vat_amount=150,
                      total_amount=1150, issue_date=D)); db.commit()
    r = vat(co)
    assert r["output"]["field_4a_output_vat"] == 120 and r["output"]["credit_notes_vat_deducted"] == 150


def test_foreign_credit_note_is_converted_to_rand():
    co = company("vat3", "general")
    i = inv(co, 100, 15, cur="USD", rate=18)
    db.add(CreditNote(company_id=co.id, invoice_id=i.id, credit_note_number="CN2", client_name="C", amount=100, vat_amount=15,
                      total_amount=115, currency="USD", issue_date=D)); db.commit()
    r = vat(co)
    assert r["output"]["field_4a_output_vat"] == 0, r["output"]       # R270 raised, R270 credited


def test_exempt_apportionment():
    co = company("vat4", "general")
    inv(co, 1000, 150); inv(co, 1000, 0, supply="exempt")                 # ratio 0.5
    exp(co, 230, 30, use="taxable"); exp(co, 230, 30, use="exempt"); exp(co, 230, 30)   # shared 30
    r = vat(co)
    assert r["output"]["field_3_exempt_supplies"] == 1000 and r["input"]["apportionment"]["ratio"] == 0.5
    assert r["input"]["field_14_input_vat"] == 30 + 30 * 0.5
    assert r["input"]["apportionment"]["non_deductible_input_vat"] == 45


def test_de_minimis_and_entertainment_not_claimable():
    co = company("vat5", "general")
    inv(co, 10000, 1500); inv(co, 100, 0, supply="exempt")                # >95% taxable -> full claim
    exp(co, 115, 15); exp(co, 115, 15, cat="Entertainment")
    r = vat(co)
    assert r["input"]["apportionment"]["ratio"] == 1.0 and r["input"]["field_14_input_vat"] == 15


def test_bimonthly_period_and_due_date_and_empty():
    co = company("vat6", "general")
    inv(co, 1000, 150, date=dt.datetime(2026, 7, 20)); inv(co, 1000, 150, date=dt.datetime(2026, 8, 20))
    inv(co, 1000, 150, date=dt.datetime(2026, 9, 1))
    r = vat(co, period="2026-07", months=2)
    assert r["output"]["field_4a_output_vat"] == 300 and "July" in r["period"] and "August" in r["period"]
    assert "September 2026" in r["due_date"] and r["due_date"].startswith(("25", "24", "23"))   # 25 Sep 2026 is Heritage Day
    z = vat(co, period="2026-01")
    assert z["net"]["field_15_net_vat"] == 0 and z["output"]["invoice_count"] == 0
    # December -> bi-monthly Dec+Jan crosses the year boundary
    assert "2027" in vat(co, period="2026-12", months=2)["due_date"]


def test_legacy_null_vat_is_estimated_and_company_isolation():
    co = company("vat7", "general"); other = company("vat8", "general")
    i0 = inv(co, 1150, 0); i0.vat_amount = None; db.commit(); inv(other, 5000, 750); exp(other, 1150, 150)
    r = vat(co)
    assert r["output"]["field_4a_output_vat"] == 150 and r["input"]["field_14_input_vat"] == 0
