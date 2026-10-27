import datetime as dt, calendar
from tests.helpers import *
from database import Payslip, Employee
import payroll as P

def pay(g, **kw): return P.calc_payroll(g, tax_year="2026/2027", **kw)

def test_paye_hand_calculated_and_rebates():
    assert pay(30000)["paye"] == 4681.00                 # (44118 + .26*(360000-245100) - 17820)/12
    assert pay(10000)["paye"] == 315.00                  # 21600-17820 = 3780/12
    assert pay(3000)["paye"] == 0                        # below threshold: never negative
    assert P.calc_paye(300000, "2026/2027", age=65) == P.calc_paye(300000, "2026/2027") - 9765
    assert P.calc_paye(300000, "2026/2027", age=75) == P.calc_paye(300000, "2026/2027") - 9765 - 3249

def test_bracket_boundaries_are_continuous():
    for edge in (245100, 383100, 530200, 695800, 887000, 1878600):
        assert abs(P.calc_paye(edge + 1, "2026/2027") - P.calc_paye(edge, "2026/2027")) < 1.0, edge   # no jump at any boundary
    assert P.calc_paye(245100.50, "2026/2027") > 0

def test_uif_ceiling_and_sdl_threshold():
    r = pay(30000, annual_payroll_total=600000)
    assert r["uif_employee"] == r["uif_employer"] == 177.12 and r["sdl"] == 300
    assert pay(10000, annual_payroll_total=600000)["uif_employee"] == 100
    assert pay(30000, annual_payroll_total=500000)["sdl"] == 0          # must EXCEED R500k
    assert pay(30000, annual_payroll_total=500001)["sdl"] == 300
    assert pay(30000, employment_category="public_servant")["uif_employee"] == 0

def test_medical_credit_and_fringe_benefits():
    assert P.calc_medical_tax_credit(0) == 376 and P.calc_medical_tax_credit(1) == 752 and P.calc_medical_tax_credit(3) == 752 + 254 * 2
    r = pay(30000, medical_aid_employee=2000, medical_aid_employer=1000, medical_aid_dependants=1)
    assert r["medical_tax_credit"] == 752 and r["paye"] == round(max(0, r["paye_before_mtc"] - 752), 2)
    assert r["paye_before_mtc"] > pay(30000)["paye_before_mtc"]         # employer-paid medical aid is a taxable fringe benefit

def test_annual_bonus_is_not_annualised():
    r = pay(20000, annual_bonus=20000)
    assert abs(r["paye"] - 6907.00) < 0.02          # 2115 regular + (tax on 260,000 - tax on 240,000 = 30172 - 25380)
    assert r["paye"] < pay(40000)["paye"]            # far below taxing the bonus as if it were earned every month

def test_pension_s11f_limited_to_27_5_percent():
    r = pay(100000, pension_employee_pct=0.40)              # 40% contribution: only 27.5% is deductible
    capped = pay(100000, pension_employee_pct=0.275)
    assert r["paye"] == capped["paye"] and r["net_pay"] < capped["net_pay"]

def test_maternity_leave_pays_nothing_and_net_never_negative():
    r = pay(20000, on_maternity_leave=True, medical_aid_employee=500)
    assert r["taxable_gross"] == 0 and r["paye"] == 0 and r["uif_employee"] == 0

def test_run_payroll_part_month_leaver_and_no_duplicates():
    co = company("pe1", "general")
    today = dt.datetime.utcnow(); dim = calendar.monthrange(today.year, today.month)[1]
    first = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    full = emp(co, "F1", 31000)
    starter = emp(co, "S1", 31000, start_date=first + dt.timedelta(days=15))                    # starts on the 16th
    leaver = emp(co, "L1", 31000, termination_date=first + dt.timedelta(days=9))                   # left on the 10th
    gone = emp(co, "G1", 31000, termination_date=first - dt.timedelta(days=5))                     # left last month
    leaver.is_active = False; gone.is_active = False; db.commit()
    run(co)
    s = {e.employee_number: slip(e) for e in (full, starter, leaver, gone)}
    assert s["G1"] is None, "a leaver from a previous month must not be paid again"
    def g(p): return getattr(p, "gross_pay", None) or getattr(p, "gross", None) or getattr(p, "gross_salary", None)
    assert abs(g(s["F1"]) - 31000) < 0.01
    assert abs(g(s["S1"]) - round(31000 * (dim - 15) / dim, 2)) < 0.01
    assert abs(g(s["L1"]) - round(31000 * 10 / dim, 2)) < 0.01
    n = db.query(Payslip).filter(Payslip.employee_id.in_([full.id, starter.id, leaver.id])).count()
    run(co)                                                    # second run in the same month
    assert db.query(Payslip).filter(Payslip.employee_id.in_([full.id, starter.id, leaver.id])).count() == n
    assert unbal(co) == 0

def test_sdl_threshold_is_company_wide_in_run_payroll():
    co = company("pe2", "general")
    es = [emp(co, f"E{i}", 9000) for i in range(4)]        # 432k a year: below the threshold
    run(co)
    assert all(slip(e).sdl == 0 for e in es)
    co2 = company("pe3", "general")
    es2 = [emp(co2, f"E{i}", 9000) for i in range(5)]      # 540k a year: SDL applies
    run(co2)
    assert all(abs(slip(e).sdl - 90) < 0.01 for e in es2)
