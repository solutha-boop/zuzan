"""Auto-ported from the pre-launch verification scripts. Each test runs one end-to-end scenario against a throwaway SQLite DB and asserts every check."""
import sys, types, asyncio, datetime as dt
from tests.helpers import *
from database import Invoice, InvoiceStatus, Account, JournalLine
import journal as J, companies as CO

_fails = []
def check(n, c, x=""):
    if not c: _fails.append(f"{n} {x}")

def test_foreign_currency_payment():
    co=company("fxco","general"); cid=co.id; user=types.SimpleNamespace(company_id=cid,id=1,role="owner")
    J.init_accounts(cid,db)
    i=Invoice(company_id=cid,invoice_number="F1",client_name="US",amount=100,vat_amount=0,total_amount=100,currency="USD",exchange_rate=18.0,status=InvoiceStatus.sent,issue_date=dt.datetime.now(),due_date=dt.datetime.now())
    db.add(i); db.commit(); db.refresh(i); J.post_invoice_raised(i,db); db.commit()
    asyncio.run(CO.update_invoice(i.id, CO.InvoiceUpdate(status="paid",paid_amount_zar=1750), current_user=user, db=db))
    def bal(code):
        a=db.query(Account).filter_by(company_id=cid,code=code).first() or db.query(Account).filter_by(company_id=cid,code=code).first()
        return sum((l.debit or 0)-(l.credit or 0) for l in db.query(JournalLine).filter_by(account_id=a.id))
    check("AR cleared on FX invoice", abs(bal("1100"))<0.01, bal("1100"))
    check("bank 1750", abs(bal("1000")-1750)<0.01, bal("1000"))
    check("FX loss 50 posted", abs(bal("5960")-50)<0.01, bal("5960"))
    try:
        asyncio.run(CO.update_invoice(i.id, CO.InvoiceUpdate(status="written_off"), current_user=user, db=db)); check("PUT written_off blocked",False)
    except Exception as e: check("PUT written_off blocked",True)

    assert not _fails, "\n".join(_fails)


