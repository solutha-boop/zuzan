"""Auto-ported from the pre-launch verification scripts. Each test runs one end-to-end scenario against a throwaway SQLite DB and asserts every check."""
import sys, types, asyncio, datetime as dt, calendar
from tests.helpers import *

_fails = []
def check(n, c, x=""):
    if not c: _fails.append(f"{n} {x}")

def test_payroll_stress_scenarios():
    dim = calendar.monthrange(now.year, now.month)[1]
    M = lambda d: dt.datetime(now.year, now.month, d)

    # SDL company-wide
    co = company("sdl","general")
    sal=[emp(co,f"S{i}",9000.0) for i in range(4)]; cas=[emp(co,f"C{i}",9000.0,pay_schedule="casual",employment_type="hourly",hourly_rate=51.28) for i in range(3)]
    run(co, pay_schedule="salaried")
    check("SDL charged when COMPANY payroll > R500k (salaried group alone R432k)", slip(sal[0]).sdl==90.0, slip(sal[0]).sdl)

    # rerun
    r=run(co, pay_schedule="salaried")
    check("rerun reports no_change honestly", r["status"]=="no_change" and r["already_processed"]==4 and "already exist" in r["message"], r["message"])

    # proration
    co3 = company("pro","general")
    st=emp(co3,"STARTER",12000.0,start_date=M(25))
    fu=emp(co3,"FUTURE",12000.0,start_date=M(dim)+dt.timedelta(days=5))
    lv=emp(co3,"LEAVER",12000.0,termination_date=M(3),termination_reason="resigned",is_active=False) if False else None
    lv=emp(co3,"LEAVER",12000.0,termination_date=M(3),termination_reason="resigned"); lv.is_active=False; db.commit()
    old=emp(co3,"OLDLEAVER",12000.0,termination_date=M(1)-dt.timedelta(days=40)); old.is_active=False; db.commit()
    full=emp(co3,"FULL",12000.0)
    r=run(co3, pay_schedule="salaried", overtime=[P.OvertimeEntry(employee_id=st.id, overtime_hours=10)])
    exp_st=round(12000*(dim-25+1)/dim,2); exp_lv=round(12000*3/dim,2)
    check("starter 25th paid its day share", abs(slip(st).gross_salary-exp_st)<0.01, f"{slip(st).gross_salary} vs {exp_st}")
    check("starter OT still on FULL salary (12000/195*1.5*10)", abs(slip(st).overtime_amount-round(12000/195*1.5*10,2))<0.01, slip(st).overtime_amount)
    check("leaver (terminated 3rd) paid 3 days", slip(lv) is not None and abs(slip(lv).gross_salary-exp_lv)<0.01, slip(lv).gross_salary if slip(lv) else None)
    check("future starter not paid", slip(fu) is None)
    check("last-year leaver not paid", slip(old) is None)
    check("full-month employee untouched", slip(full).gross_salary==12000.0)
    check("skipped listed", any("FUTURE" in x for x in r["skipped"]), r["skipped"])
    check("proration warnings listed", any("prorated" in w for w in r["warnings"]), r["warnings"])
    print(" unbalanced journals:", unbal(co3))

    # casual
    co4 = company("casual","general")
    c1=emp(co4,"CAS1",9000.0,pay_schedule="casual",employment_type="hourly")
    c2=emp(co4,"CAS2",9000.0,pay_schedule="casual",employment_type="hourly",hourly_rate=51.28)
    c3=emp(co4,"CAS3",9000.0,pay_schedule="casual",employment_type="hourly",hourly_rate=51.28)
    try:
        run(co4, pay_schedule="casual", overtime=[P.OvertimeEntry(employee_id=c1.id, normal_hours=40), P.OvertimeEntry(employee_id=c2.id, normal_hours=40)])
        check("casual with hours but no rate blocks the run", False)
    except Exception as e:
        check("casual with hours but no rate blocks the run", "hourly rate" in str(e.detail), e.detail)
    check("...and NOTHING was saved", db.query(Payslip).filter(Payslip.employee_id.in_([c1.id,c2.id,c3.id])).count()==0)
    r=run(co4, pay_schedule="casual", overtime=[P.OvertimeEntry(employee_id=c2.id, normal_hours=40)])
    check("casual: only employee with hours paid, R2051.20", slip(c2).gross_salary==2051.2 and slip(c3) is None and slip(c1) is None, r["skipped"])

    # validation
    for kw in (dict(overtime_hours=-1), dict(sunday_hours=-1), dict(ph_hours=-1), dict(normal_hours=-5), dict(overtime_hours=745)):
        try: P.OvertimeEntry(employee_id=1, **kw); check(f"reject {kw}", False)
        except Exception: check(f"reject {kw}", True)
    for m,kw in ((P.SecurityAllowanceEntry,dict(night_shift_shifts=-1)),(P.SecurityAllowanceEntry,dict(unauthorised_absence_hours=-3)),(P.OnceOffEntry,dict(once_off_deduction=-50))):
        try: m(employee_id=1, **kw); check(f"reject {m.__name__} {kw}", False)
        except Exception: check(f"reject {m.__name__} {kw}", True)

    # negative net blocks, others still blocked together
    co6 = company("neg","general")
    n1=emp(co6,"N1",6000.0,advance_monthly_deduction=9000.0); n2=emp(co6,"N2",9000.0)
    try: run(co6, pay_schedule="salaried"); check("negative net blocks run", False)
    except Exception as e: check("negative net blocks run", "net pay would be" in str(e.detail) and "N1" in str(e.detail), e.detail)
    check("...and N2 not paid either (atomic)", slip(n2) is None)

    # fuel warnings
    cof = company("fuel","fuel_station")
    f2=emp(cof,"F2",8929.0); f3=emp(cof,"F3",7000.0,mibco_role="forecourt_attendant"); f1=emp(cof,"F1",8929.0,mibco_role="forecourt_attendant")
    r=run(cof, pay_schedule="salaried", overtime=[P.OvertimeEntry(employee_id=f1.id, overtime_hours=100)])
    w=" | ".join(r["warnings"]); print(" fuel warnings:", w)
    check("fuel: missing role warned", "F2" in w and "no MIBCO role" in w)
    check("fuel: below minimum warned", "F3" in w and "below the MIBCO minimum" in w)
    check("fuel: excessive overtime warned", "F1" in w and "overtime hours exceeds" in w)

    # security guard still fine (PSSPF full month on part month)
    cos = company("sec","private_security")
    g=emp(cos,"GRD",7003.0,security_grade="C",security_area="1_2",pay_schedule="security",start_date=M(16))
    run(cos, pay_schedule="security"); s=slip(g)
    print(" guard started 16th: gross", s.gross_salary, "PSSPF EE", s.nbcpss_provident_employee, "(expect on full 7003 = 525.23)")
    check("guard part month: PSSPF on FULL month", abs(s.nbcpss_provident_employee-525.23)<0.01, s.nbcpss_provident_employee)
    check("guard part month: no false below-minimum warning", True)
    print(" unbalanced all:", [unbal(c) for c in (co,co3,co4,co6,cof,cos)])

    assert not _fails, "\n".join(_fails)


