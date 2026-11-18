"""Provisional tax uses the company's own financial year and includes GL-imported books (2026-11-15)."""
import io, types, asyncio, datetime as dt
from fastapi import UploadFile
from tests.helpers import *
from database import Company
import csv_import as CI
import payroll as P

def test_company_fy_bounds_and_leap_year():
    co = types.SimpleNamespace(financial_year_end="02-28")
    assert P._company_fy(co, dt.date(2026, 11, 15)) == (dt.date(2026, 3, 1), dt.date(2027, 2, 28))
    assert P._company_fy(co, dt.date(2024, 2, 29)) == (dt.date(2023, 3, 1), dt.date(2024, 2, 29))
    assert P._company_fy(types.SimpleNamespace(financial_year_end="06-30"), dt.date(2026, 7, 1)) == (dt.date(2026, 7, 1), dt.date(2027, 6, 30))

def test_sbc_table():
    # years of assessment ending 1 Apr 2023 - 31 Mar 2026
    fy26 = dt.date(2026, 2, 28)
    assert P._sbc_tax(95_750, fy26) == 0
    assert P._sbc_tax(365_000, fy26) == round(0.07 * (365_000 - 95_750), 2)
    assert P._sbc_tax(1_000_000, fy26) == round(57_698 + 0.27 * 450_000, 2)
    # years of assessment ending 1 Apr 2026 - 31 Mar 2027 (Budget 2026): R99,000 / R18,620 / R57,470
    fy27 = dt.date(2027, 2, 28)
    assert P._sbc_tax(99_000, fy27) == 0
    assert P._sbc_tax(365_000, fy27) == 18_620.0
    assert P._sbc_tax(550_000, fy27) == 57_470.0
    assert P._sbc_tax(1_000_000, fy27) == round(57_470 + 0.27 * 450_000, 2)
    assert P._sbc_tax(1_000_000) == P._sbc_tax(1_000_000, fy27)     # default = current table

def test_vat_due_day_is_25th_or_earlier_business_day():
    assert P._vat_due_day(2026, 12) == dt.date(2026, 12, 24)    # 25 Dec is a holiday -> Thu 24 Dec
    assert P._vat_due_day(2027, 1) == dt.date(2027, 1, 25)      # Monday
    assert P._vat_due_day(2026, 10) == dt.date(2026, 10, 23)    # Sun 25 Oct -> Fri 23 Oct

def test_endpoint_uses_fy_and_gl_imports():
    co = company("provA", "general"); co.financial_year_end = "02-28"; db.commit()
    cu = types.SimpleNamespace(company_id=co.id, id=1, role="owner")
    today = dt.date.today()
    fy_start, fy_end = P._company_fy(co, today)
    prev_end = fy_start - dt.timedelta(days=1)
    # last year: R2m profit, imported as an opening TB at the previous year-end
    tb = ("Code,Account Name,Type,Debit,Credit\n1010,Bank,asset,2000000,\n4000,Fuel Sales,revenue,,10000000\n"
          "5010,Purchases,cogs,8000000,\n")
    asyncio.run(CI.import_trial_balance(file=UploadFile(filename="x.csv", file=io.BytesIO(tb.encode())),
                                        as_at=prev_end.isoformat(), replace=False, db=db, cu=cu))
    r = asyncio.run(P.provisional_tax(current_user=cu, db=db))
    assert r["financial_year"] == {"start": fy_start.isoformat(), "end": fy_end.isoformat()}
    assert r["ytd"]["revenue"] == 0                       # last year's figures are not this year's
    assert r["prior_year"]["taxable_income"] == 2_000_000 and r["prior_year"]["has_data"]
    assert r["prior_year"]["estimate_below_80_percent"]   # nothing yet this year vs R2m last year
    assert r["irp6"]["second_due"] == fy_end.strftime("%d %B %Y")
    assert "third_due" in r["irp6"]
    # SARS: February year-end -> 7 months after year-end (30 September); other year-ends -> 6 months
    assert r["irp6"]["third_due"] == dt.date(fy_end.year, 9, 30).strftime("%d %B %Y")
