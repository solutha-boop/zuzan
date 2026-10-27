"""Auto-ported from the pre-launch verification scripts. Each test runs one end-to-end scenario against a throwaway SQLite DB and asserts every check."""
import sys, types, asyncio, datetime as dt
from tests.helpers import *
from database import Invoice, InvoiceStatus, Expense
import companies as CO, journal as J

_fails = []
def check(n, c, x=""):
    if not c: _fails.append(f"{n} {x}")

def test_exempt_supplies_apportionment():
    Y,Mo=now.year,now.month; D=lambda d: dt.datetime(Y,Mo,d)
    def scenario(name, exempt_amt):
        co=company(name,"general"); u=types.SimpleNamespace(company_id=co.id,id=1)
        mk=lambda amt,st: asyncio.run(CO.create_invoice(CO.InvoiceCreate(client_name="X",description="d",amount=amt,supply_type=st,vat_applicable=(st=="standard"),due_date=D(25).isoformat()),current_user=u,db=db))
        s1=mk(10000,"standard"); 
        ex=mk(exempt_amt,"exempt") if exempt_amt else None
        def e(amt,use): 
            return asyncio.run(CO.create_expense(CO.ExpenseCreate(vendor="V",description="d",amount=amt,category="Utilities",expense_date=D(3).isoformat(),vat_applicable=True,vat_use=use),current_user=u,db=db))
        e(1000,None); e(1000,"taxable"); e(1000,"exempt")      # VAT 150 each
        r=asyncio.run(P.vat201(current_user=u,db=db,period=f"{Y}-{Mo:02d}"))
        return co,ex,r
    co,ex,r=scenario("ex1",1000)
    check("exempt invoice carries no VAT", ex.vat_amount==0 and ex.total_amount==1000 and ex.supply_type=="exempt")
    check("output VAT only on standard (1500)", r["output"]["field_4a_output_vat"]==1500.0, r["output"]["field_4a_output_vat"])
    check("exempt supplies shown (box 3)", r["output"]["field_3_exempt_supplies"]==1000.0)
    ap=r["input"]["apportionment"]
    check("ratio = 10000/11000 = 0.91", ap["ratio"]==0.91, ap["ratio"])
    check("input claimed = 150 taxable + 150*0.91 shared = 286.5; exempt-only 0", r["input"]["field_14_input_vat"]==286.5, r["input"]["field_14_input_vat"])
    check("non-deductible = 450-286.5 = 163.5", ap["non_deductible_input_vat"]==163.5, ap["non_deductible_input_vat"])
    co,ex,r=scenario("ex2",400)
    check("de minimis: exempt 400/10400 (>=95% taxable) -> ratio 1.0, shared fully claimed", r["input"]["apportionment"]["ratio"]==1.0 and r["input"]["field_14_input_vat"]==300.0, r["input"]["field_14_input_vat"])
    co,ex,r=scenario("ex3",None)
    check("no exempt supplies: all but exempt-tagged claimed (300)", r["input"]["field_14_input_vat"]==300.0 and r["input"]["apportionment"]["ratio"]==1.0, r["input"]["field_14_input_vat"])
    bad=False
    try:
        asyncio.run(CO.create_invoice(CO.InvoiceCreate(client_name="X",description="d",amount=1,supply_type="bogus"),current_user=types.SimpleNamespace(company_id=co.id,id=1),db=db))
    except Exception as exn: bad=True
    check("bad supply_type rejected", bad)
    assert unbal(co)==0

    assert not _fails, "\n".join(_fails)


