import types, asyncio, datetime as dt
from tests.helpers import *
from database import Payslip, Employee, Company
import payroll as P


def _user(co): return types.SimpleNamespace(company_id=co.id, id=1, role="owner")


def _relabel(emp_ids, period):
    for s in db.query(Payslip).filter(Payslip.employee_id.in_(emp_ids)).all():
        if not getattr(s, "_fixed", False) and s.period not in ("2026-03", "2026-04", "2026-05"):
            s.period = period
    db.commit()


def _setup():
    co = company("ye1", "general")
    a = emp(co, "A1", 30000); b = emp(co, "B1", 20000)
    run(co); _relabel([a.id, b.id], "2026-03")                      # March: both paid
    b.is_active = False; b.termination_date = dt.datetime(2026, 3, 31); db.commit()   # B leaves at the end of March
    run(co); _relabel([a.id], "2026-04")                            # April: only A (run skips inactive staff)
    return co, a, b


def test_leaver_is_on_the_irp5_and_the_emp501_agrees_with_the_irp5s():
    co, a, b = _setup()
    irp5 = asyncio.run(P.get_irp5(tax_year=2027, current_user=_user(co), db=db))
    names = {e["employee_number"]: e for e in irp5["employees"]}
    assert set(names) == {"A1", "B1"}, names.keys()                 # B has left but was paid, so gets a certificate
    assert names["B1"]["periods_count"] == 1 and names["A1"]["periods_count"] == 2
    emp501 = asyncio.run(P.get_emp501(tax_year=2027, current_user=_user(co), db=db))
    assert round(sum(e["code_4102_paye"] for e in irp5["employees"]), 2) == emp501["total_paye"]
    assert emp501["total_employees"] == 2 and emp501["months_submitted"] == 2
    assert irp5["period_to"] == "28 February 2027"


def test_leap_year_label_and_tax_year_boundaries():
    assert P._tax_year_end_label(2028) == "29 February 2028" and P._tax_year_end_label(2027) == "28 February 2027"
    periods = P._tax_year_periods(2027)
    assert periods[0] == "2026-03" and periods[-1] == "2027-02" and len(periods) == 12


def test_emp201_for_a_month_matches_the_payslips_and_the_ledger():
    co, a, b = _setup()
    r = asyncio.run(P.emp201(current_user=_user(co), db=db, period="2026-03"))
    slips = db.query(Payslip).filter(Payslip.period == "2026-03", Payslip.employee_id.in_([a.id, b.id])).all()
    assert r["employee_count"] == 2
    assert r["total_paye"] == round(sum(s.paye for s in slips), 2)
    assert r["total_uif"] == round(sum(s.uif_employee + s.uif_employer for s in slips), 2)
    assert r["total_sdl"] == round(sum(s.sdl for s in slips), 2)
    assert r["total_due_sars"] == round(r["total_paye"] + r["total_uif"] + r["total_sdl"], 2)
    assert r["due_date"] == "07 April 2026" or "April 2026" in r["due_date"]            # 7 Apr 2026 is a Tuesday
    r2 = asyncio.run(P.emp201(current_user=_user(co), db=db, period="2026-04"))
    assert r2["employee_count"] == 1                                                      # the leaver is not in April
    assert asyncio.run(P.emp201(current_user=_user(co), db=db, period="2026-12"))["total_due_sars"] == 0


def test_easyfile_gives_the_leaver_a_certificate_with_their_real_employment_dates():
    co, a, b = _setup()
    c = db.query(Company).filter_by(id=co.id).one()
    c.paye_ref = "7123456789"; c.name = "Ye Co"; db.commit()
    resp = asyncio.run(P.get_easyfile_export(tax_year=2027, mode="TEST", interim=False, current_user=_user(co), db=db))
    txt = resp.body.decode()
    assert txt.count('3015,"IRP5"') == 2
    assert "5001,2" in txt
    assert "3180,20260331" in txt                        # B's certificate ends the day they left
    assert "3180,20270228" in txt                        # A's runs to the end of the year
