"""Auto-ported from the pre-launch verification scripts. Each test runs one end-to-end scenario against a throwaway SQLite DB and asserts every check."""
import sys, types, asyncio, datetime as dt
from tests.helpers import *
from database import Base, engine, SessionLocal, Company, Employee, ClockEvent
import clocking as C, payroll as P
Base.metadata.create_all(bind=engine)
db = SessionLocal()
co = Company(name="Clock Co", email="c@example.com", industry="private_security"); db.add(co); db.commit(); db.refresh(co)
user = types.SimpleNamespace(company_id=co.id)

_fails = []
def check(n, c, x=""):
    if not c: _fails.append(f"{n} {x}")

def test_clocking_hours():

    # holidays
    h26 = sorted(C._sa_holidays(2026)); h27 = sorted(C._sa_holidays(2027))
    exp26 = {dt.date(2026,m,d) for m,d in [(1,1),(3,21),(4,3),(4,6),(4,27),(5,1),(6,16),(8,9),(8,10),(9,24),(12,16),(12,25),(12,26)]}
    exp27 = {dt.date(2027,m,d) for m,d in [(1,1),(3,21),(3,22),(3,26),(3,29),(4,27),(5,1),(6,16),(8,9),(9,24),(12,16),(12,25),(12,26),(12,27)]}
    check("holidays 2026", set(h26)==exp26, set(h26)^exp26)
    check("holidays 2027 (incl. observed Mondays)", set(h27)==exp27, set(h27)^exp27)
    check("2028 Good Friday 14 Apr", dt.date(2028,4,14) in C._sa_holidays(2028))

    def mk(no, grade=None):
        e = Employee(company_id=co.id, employee_number=no, first_name=no, last_name="X", gross_salary=7003, is_active=True,
                     security_grade=grade, security_area="1_2" if grade else None, pay_schedule="security" if grade else "salaried",
                     employment_type="salaried", hourly_rate=7003/208 if grade else None)
        db.add(e); db.commit(); db.refresh(e); return e
    def sast(y,m,d,h,mi=0): return dt.datetime(y,m,d,h,mi) - dt.timedelta(hours=2)   # SAST wall clock -> stored UTC
    def punch(e, t_in, t_out):
        for typ,t in (("in",t_in),("out",t_out)):
            if t: db.add(ClockEvent(company_id=co.id, employee_id=e.id, event_type=typ, timestamp=t, method="kiosk"))
        db.commit()
    def run(a,b): 
        rows = asyncio.run(C.payroll_hours(date_from=a, date_to=b, daily_threshold=8.0, round_minutes=15, current_user=user, db=db))
        return {r["employee_number"]: r for r in rows}

    g1 = mk("G1","C"); g2 = mk("G2","C"); g3 = mk("G3","C"); g4=mk("G4","C"); g5=mk("G5","C"); n1 = mk("N1")
    # G1: Nov 2026, Mon-Thu 06:00-18:00 every week (4x12 = 48h)
    for d in range(1,31):
        if dt.date(2026,11,d).weekday() in (0,1,2,3): punch(g1, sast(2026,11,d,6), sast(2026,11,d,18,3))
    # G2: one week with 5 weekday shifts (Mon-Fri 12h) -> 12h OT
    for d in range(2,7): punch(g2, sast(2026,11,d,6), sast(2026,11,d,18))
    # G3: night shift Mon 18:00 -> Tue 06:00, Sunday day shift, Heritage-day-style PH: 24 Sep 2026
    punch(g3, sast(2026,11,2,18), sast(2026,11,3,6))
    punch(g3, sast(2026,11,8,6), sast(2026,11,8,18))
    # G4: month-end night shift 31 Oct 18:00 -> 1 Nov 06:00 ; plus a missed clock-out on 10 Nov
    punch(g4, sast(2026,10,31,18), sast(2026,11,1,6))
    punch(g4, sast(2026,11,10,6), None); punch(g4, sast(2026,11,11,6), sast(2026,11,11,18))
    # G5: PH 
    punch(g5, sast(2026,9,24,6), sast(2026,9,24,18))
    # N1: non-security 12h shift
    punch(n1, sast(2026,11,3,6), sast(2026,11,3,18))

    nov = run("2026-11-01","2026-11-30")
    r=nov["G1"]; check("G1 4x12 weekly -> no OT, no night, not sent as normal hours", r["ot_hours"]==0 and r["night_shift_shifts"]==0 and r["apply_normal_hours"] is False, r)
    r=nov["G2"]; check("G2 5 weekday shifts -> 12h OT", abs(r["ot_hours"]-12)<0.01, r["ot_hours"])
    r=nov["G3"]; check("G3 night shift counted once, Sunday 12h", r["night_shift_shifts"]==1 and abs(r["sunday_hours"]-12)<0.01 and r["ot_hours"]==0, r)
    r=nov["G4"]; check("G4 month-end shift NOT in Nov; missed clock-out flagged", r["night_shift_shifts"]==0 and any(e["type"]=="missing_clock_out" for e in r["exceptions"]), r["exceptions"])
    r=nov["N1"]; check("N1 non-security keeps daily rule 8 normal + 4 OT", r["normal_hours"]==8 and r["ot_hours"]==4 and r["apply_normal_hours"], r)
    octo = run("2026-10-01","2026-10-31")
    r=octo["G4"]; check("G4 month-end night shift paid in OCT once", r["night_shift_shifts"]==1 and abs(r["hours_worked"]-12)<0.01, r)
    sep = run("2026-09-01","2026-09-30")
    r=sep["G5"]; check("G5 public holiday 12h", abs(r["ph_hours"]-12)<0.01 and r["ot_hours"]==0, r)

    # pay: guard fed from clocking must still be paid the contract salary
    r=nov["G1"]
    pay = P.calc_payroll(gross_monthly=7003.0, is_security=True, security_grade="C", security_area="1_2",
            explicit_hourly_rate=7003/208, normal_hours=(r["normal_hours"] if r["apply_normal_hours"] else None),
            overtime_hours=r["ot_hours"], sunday_hours=r["sunday_hours"], ph_hours=r["ph_hours"], night_shift_shifts=r["night_shift_shifts"])
    check("G1 pay = contract + cleaning only (no phantom OT)", pay["overtime"]["total_overtime"]==0 and abs(pay["taxable_gross"]-7035)<0.01, pay["taxable_gross"])

    # kiosk ignores client timestamp
    co.kiosk_token="tok"; db.commit()
    ev = asyncio.run(C.clock_event_kiosk(C.KioskClock(kiosk_token="tok", employee_id=g1.id, event_type="in", timestamp=dt.datetime(2020,1,1)), db=db))
    check("kiosk ignores client timestamp", not ev["timestamp"].startswith("2020"), ev["timestamp"])
    check("timestamps carry Z", ev["timestamp"].endswith("Z"))

    assert not _fails, "\n".join(_fails)


