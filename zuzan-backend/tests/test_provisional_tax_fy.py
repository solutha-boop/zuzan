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
    assert P._sbc_tax(95_750) == 0
    assert P._sbc_tax(365_000) == round(0.07 * (365_000 - 95_750), 2)
    assert P._sbc_tax(1_000_000) == round(57_698 + 0.27 * 450_000, 2)

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
