"""Posted income tax vs the 27% estimate (2026-11-22).

Companies migrated from QuickBooks/Xero can carry a booked tax charge. The AFS must not treat it
as an operating expense and then tax the profit again, and a part-year posting (e.g. six months
only) must be topped up to the estimate with a review message."""
import io, types, asyncio
from fastapi import UploadFile
from tests.helpers import *
import csv_import as CI, financial_statements as FS, management_report as MR

H = "Date,Reference,Description,Account Code,Account Name,Debit,Credit\n"
BASE = (  # FY2026 (1 Mar 2025 - 28 Feb 2026): sales 100,000, rent 20,000 -> profit before tax 80,000, 27% = 21,600
    "2025-04-10,S1,Sale,1010,Bank - current account,100000,\n2025-04-10,S1,Sale,4000,Sales,,100000\n"
    "2025-05-10,R1,Rent,6100,Rent,20000,\n2025-05-10,R1,Rent,1010,Bank - current account,,20000\n")
TAX = "2025-08-31,T1,Income tax,6910,Income Tax Expense,{a},\n2025-08-31,T1,Income tax,2126,Income Tax Payable,,{a}\n"


def _co(name, extra=""):
    co = company(name, "general"); co.financial_year_end = "02-28"; db.commit()
    cu = types.SimpleNamespace(company_id=co.id, id=1, role="accountant", first_name="S", last_name="G", email="s@x.com")
    r = asyncio.run(CI.import_journals(file=UploadFile(filename="j.csv", file=io.BytesIO((H + BASE + extra).encode())), db=db, cu=cu))
    assert not r["errors"], r["errors"]
    return co


def _afs(co):
    return FS.annual_financial_statements(year=2026, db=db, current_user=types.SimpleNamespace(company_id=co.id, id=1, role="owner"))


def _tax_line(r):
    lines = [l for l in r["balance_sheet"]["liabilities"]["current"] if "income tax" in l["name"].lower()]
    assets = [l for l in r["balance_sheet"]["assets"]["current"] if "income tax" in l["name"].lower()]
    assert len(lines) + len(assets) <= 1, (lines, assets)          # one tax line, never two
    return lines[0]["amount"] if lines else (-assets[0]["amount"] if assets else 0.0)


def _healthy(r):
    assert r["balance_sheet"]["balanced"], (r["balance_sheet"]["assets"]["total"], r["balance_sheet"]["total_equity_and_liabilities"])
    assert r["cash_flow"]["reconciles_to_ledger"]
    ce = r["changes_in_equity"]
    assert abs(ce["opening_total"] + ce["net_profit"] + ce["contributions"] - ce["drawings"] + ce["deferred_tax_movement"] - ce["closing_total"]) < 0.05


# ── the check itself ──────────────────────────────────────────────────────────

def test_reasonability_rules():
    c = FS.income_tax_reasonability(80000, 0, False)
    assert (c["status"], c["tax_expense"], c["adjustment"]) == ("estimate", 21600, 21600)
    c = FS.income_tax_reasonability(80000, 21000, True)            # within R5,000 tolerance
    assert (c["status"], c["tax_expense"], c["adjustment"], c["needs_review"]) == ("posted", 21000, 0, False)
    c = FS.income_tax_reasonability(80000, 10800, True)            # six months booked
    assert (c["status"], c["tax_expense"], c["adjustment"], c["needs_review"]) == ("under_posted", 21600, 10800, True)
    assert "assessed loss" in c["message"] and "50.0%" in c["message"]
    c = FS.income_tax_reasonability(80000, 40000, True)
    assert (c["status"], c["tax_expense"], c["adjustment"]) == ("over_posted", 21600, -18400)
    c = FS.income_tax_reasonability(-5000, 0, False)                # loss: no tax
    assert c["tax_expense"] == 0 and c["status"] == "estimate"
    big = FS.income_tax_reasonability(10_000_000, 2_600_000, True)  # 5% of 2.7m = 135k tolerance
    assert big["status"] == "posted"


def test_tax_accounts_are_recognised_but_not_vat_paye_or_deferred():
    f = FS._is_income_tax_account
    assert f("6910", "Income Tax Expense") and f("Income tax expense", "Income tax expense") and f("7000", "Taxation")
    assert not f("2100", "VAT Output") and not f("6010", "PAYE Employer Contributions") and not f("7100", "Deferred tax expense")
    assert not f("5250", "Tax")                                     # generic expense category: not assumed to be income tax


# ── annual financial statements ───────────────────────────────────────────────

def test_nothing_posted_keeps_the_27_percent_estimate():
    r = _afs(_co("itxNone"))
    inc = r["income_statement"]
    assert inc["profit_before_tax"] == 80000 and inc["tax_expense"] == 21600 and inc["net_profit"] == 58400
    assert _tax_line(r) == 21600
    _healthy(r)


def test_full_year_posted_is_used_once_not_taxed_twice():
    r = _afs(_co("itxFull", TAX.format(a=21600)))
    inc = r["income_statement"]
    assert all("income tax" not in l["name"].lower() for l in inc["opex_lines"])
    assert inc["profit_before_tax"] == 80000                        # booked tax no longer reduces profit before tax
    assert inc["tax_expense"] == 21600 and inc["tax_adjustment"] == 0 and inc["tax_check"]["status"] == "posted"
    assert inc["net_profit"] == 58400
    assert _tax_line(r) == 21600                                    # 2126 and the estimate are not both shown
    _healthy(r)


def test_six_months_posted_is_topped_up_to_the_estimate_and_flagged():
    r = _afs(_co("itxHalf", TAX.format(a=10800)))
    inc = r["income_statement"]
    assert inc["tax_check"]["status"] == "under_posted" and inc["tax_check"]["needs_review"]
    assert inc["tax_expense"] == 21600 and inc["tax_adjustment"] == 10800 and inc["net_profit"] == 58400
    assert _tax_line(r) == 21600
    tn = r["notes"]["tax_note"]
    assert (tn["posted_tax"], tn["expected_tax"], tn["year_end_adjustment"], tn["current_tax"]) == (10800, 21600, 10800, 21600)
    _healthy(r)


def test_over_posted_is_reduced_to_the_estimate():
    r = _afs(_co("itxOver", TAX.format(a=40000)))
    inc = r["income_statement"]
    assert inc["tax_check"]["status"] == "over_posted" and inc["tax_expense"] == 21600 and inc["tax_adjustment"] == -18400
    assert _tax_line(r) == 21600
    _healthy(r)


def test_posted_tax_provisional_payment_and_top_up_net_to_one_line():
    prov = "2025-08-31,P1,IRP6,2127,Provisional Tax Payable,10000,\n2025-08-31,P1,IRP6,1010,Bank - current account,,10000\n"
    r = _afs(_co("itxProv", TAX.format(a=10800) + prov))
    assert r["income_statement"]["tax_expense"] == 21600
    assert _tax_line(r) == 11600                                    # 10,800 posted + 10,800 top-up - 10,000 paid
    _healthy(r)


# ── management report ─────────────────────────────────────────────────────────

def test_management_report_is_before_tax_and_carries_the_check():
    co = _co("itxMR", TAX.format(a=10800))
    f = MR.build_figures(db, co, "2026-02")
    inc = f["income_statement"]
    assert all("income tax" not in r["name"].lower() for r in inc["opex"])
    assert inc["net_profit_before_tax"]["ytd"] == 80000
    assert inc["total_income_tax_posted"]["ytd"] == 10800
    assert inc["tax_check"]["status"] == "under_posted"
    assert f["cash_flow"]["ytd"]["reconciles"] and f["cash_flow"]["month"]["reconciles"]
    assert "Income tax" in MR._summary_for_ai(f)
    assert "assessed loss" in MR._template_commentary(f)
