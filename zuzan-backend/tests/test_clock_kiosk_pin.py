"""Auto-ported from the pre-launch verification scripts. Each test runs one end-to-end scenario against a throwaway SQLite DB and asserts every check."""
import sys, types, asyncio, os
from tests.helpers import *
import clocking as CL
from database import Employee, Company
from fastapi import HTTPException

_fails = []
def check(n, c, x=""):
    if not c: _fails.append(f"{n} {x}")

def test_clock_kiosk_pin():
    co=company("pinco","general"); cid=co.id
    emp(co,"E1",10000); emp(co,"E2",12000)
    emps=db.query(Employee).filter_by(company_id=cid).all()
    print("employees:",len(emps))
    c=db.query(Company).get(cid); c.kiosk_token="tok123"; db.commit()
    user=types.SimpleNamespace(company_id=cid,id=1,email="o@x.co",role="owner")
    e=emps[0]
    def clock(pin=None): return asyncio.run(CL.clock_event_kiosk(CL.KioskClock(kiosk_token="tok123",employee_id=e.id,event_type="in",pin=pin),db=db))
    check("no PIN set -> works as before", clock()["event_type"]=="in")
    r=asyncio.run(CL.generate_clock_pins(current_user=user,db=db)); pin=[p for p in r["pins"] if p["employee_id"]==e.id][0]["pin"]
    check("pins generated for all", r["generated"]==len(emps), r["generated"])
    info=asyncio.run(CL.kiosk_info(token="tok123",db=db)); check("kiosk-info flags pin_required", all(x["pin_required"] for x in info["employees"]))
    def tryit(p):
        try: clock(p); return "ok"
        except HTTPException as ex: return ex.status_code
    check("missing PIN -> 403", tryit(None)==403)
    check("wrong PIN -> 403", tryit("0000" if pin!="0000" else "1111")==403)
    check("correct PIN -> ok", tryit(pin)=="ok")
    wrong="0000" if pin!="0000" else "1111"
    for _ in range(5): tryit(wrong)
    check("5 wrong -> locked 429", tryit(pin)==429, tryit(pin))
    asyncio.run(CL.set_clock_pin(e.id,CL.PinSet(pin="4321"),current_user=user,db=db))
    check("manager reset unlocks + new PIN works", tryit("4321")=="ok")
    try: asyncio.run(CL.set_clock_pin(e.id,CL.PinSet(pin="12"),current_user=user,db=db)); check("short PIN rejected",False)
    except HTTPException: check("short PIN rejected",True)
    asyncio.run(CL.clear_clock_pin(e.id,current_user=user,db=db)); check("cleared -> no PIN needed", tryit(None)=="ok")

    assert not _fails, "\n".join(_fails)


