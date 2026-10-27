"""Auto-ported from the pre-launch verification scripts. Each test runs one end-to-end scenario against a throwaway SQLite DB and asserts every check."""
import sys, types, asyncio, datetime as dt
from tests.helpers import *
from database import Invoice, InvoiceStatus, Expense, Account, JournalLine
import journal as J, companies as CO

_fails = []
def check(n, c, x=""):
    if not c: _fails.append(f"{n} {x}")

def test_bad_debts_and_motor_car():
    co=company("bdco","general"); cid=co.id
    user=types.SimpleNamespace(company_id=cid, id=1, role="owner")
    Y,Mo=now.year,now.month; D=lambda d: dt.datetime(Y,Mo,d)
    J.init_accounts(cid,db)
    i=Invoice(company_id=cid,invoice_number="B1",client_name="Deadbeat",amount=1000,vat_amount=150,total_amount=1150,status=InvoiceStatus.sent,issue_date=D(2),due_date=D(10))
    db.add(i); db.commit(); db.refresh(i); J.post_invoice_raised(i,db); db.commit()
    def vat(): return asyncio.run(P.vat201(current_user=user, db=db, period=f"{Y}-{Mo:02d}"))
    r=vat(); check("output VAT 150 before write-off", r["output"]["field_4a_output_vat"]==150.0, r["output"]["field_4a_output_vat"])
    res=asyncio.run(CO.write_off_bad_debt(i.id, CO.BadDebtWriteOff(reason="Debtor liquidated"), current_user=user, db=db))
    db.refresh(i); check("status written_off", i.status==InvoiceStatus.written_off)
    r=vat(); check("VAT201 net: output 150, bad-debt deduction 150", r["input"]["bad_debt_vat_deduction"]==150.0 and r["input"]["field_14_input_vat"]==150.0, (r["input"]["bad_debt_vat_deduction"], r["input"]["field_14_input_vat"]))
    def bal(code,sign):
        a=db.query(Account).filter_by(company_id=cid,code=code).first()
        return sum(sign*((l.debit or 0)-(l.credit or 0)) for l in db.query(JournalLine).filter_by(account_id=a.id))
    check("AR cleared", abs(bal("1100",1))<0.01, bal("1100",1))
    check("VAT output ledger net 0", abs(bal("2100",-1))<0.01, bal("2100",-1))
    try:
        asyncio.run(CO.write_off_bad_debt(i.id, CO.BadDebtWriteOff(reason="x"), current_user=user, db=db)); check("double write-off blocked",False)
    except Exception as e: check("double write-off blocked",True)
    asyncio.run(CO.recover_bad_debt(i.id, CO.BadDebtRecovery(amount=575), current_user=user, db=db))
    r=vat(); check("partial recovery adds 75 output VAT", abs(r["output"]["field_4a_output_vat"]-225)<0.01, r["output"]["field_4a_output_vat"])
    db.refresh(i); check("still written_off after partial", i.status==InvoiceStatus.written_off)
    asyncio.run(CO.recover_bad_debt(i.id, CO.BadDebtRecovery(), current_user=user, db=db))
    db.refresh(i); check("fully recovered -> paid", i.status==InvoiceStatus.paid)
    check("bank 1150 net", abs(bal("1000",1)-1150)<0.01, bal("1000",1))
    # motor car denial
    e=Expense(company_id=cid,vendor="Car",amount=230000,vat_amount=30000,category="Vehicles",vat_use="denied",expense_date=D(8)); db.add(e); db.commit(); db.refresh(e); J.post_expense(e,db); db.commit()
    r=vat(); inp=r["input"]["field_14_input_vat"]
    check("denied car VAT not claimed", abs(inp-150)<0.01, inp)
    check("ledger 1300 excludes car VAT", abs(bal("1300",1))<0.01, bal("1300",1))

    assert not _fails, "\n".join(_fails)


