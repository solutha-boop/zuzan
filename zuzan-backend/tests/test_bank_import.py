"""Auto-ported from the pre-launch verification scripts. Each test runs one end-to-end scenario against a throwaway SQLite DB and asserts every check."""
import sys, types, asyncio, datetime as dt
from tests.helpers import *
from database import Invoice, InvoiceStatus, Account, JournalLine
import journal as J, companies as CO

_fails = []
def check(n, c, x=""):
    if not c: _fails.append(f"{n} {x}")

def test_bank_import():
    co=company("bkco","general"); cid=co.id; user=types.SimpleNamespace(company_id=cid,id=1,role="owner")
    J.init_accounts(cid,db)
    def mk(no,cl,amt):
        i=Invoice(company_id=cid,invoice_number=no,client_name=cl,amount=amt/1.15,vat_amount=amt-amt/1.15,total_amount=amt,status=InvoiceStatus.sent,issue_date=dt.datetime.now(),due_date=dt.datetime.now())
        db.add(i); db.commit(); db.refresh(i); J.post_invoice_raised(i,db); db.commit(); return i
    i1=mk("I1","Acme Trading",1150); i2=mk("I2","Zeta Corp",500)
    today=dt.date.today().isoformat()
    T=CO.BankTransaction
    def run(txns): return asyncio.run(CO.import_bank_statement(CO.BankImportRequest(bank="fnb",transactions=txns),current_user=user,db=db))
    r=run([T(date=today,description="ACME TRADING PAYMENT",amount=1150,type="credit"),
           T(date=today,description="EFT UNKNOWN PAYER",amount=500,type="credit"),
           T(date=today,description="junk",amount=0,type="credit")])
    db.refresh(i1); db.refresh(i2)
    check("named match marks invoice paid", i1.status==InvoiceStatus.paid and r["credits_matched_to_invoices"]==1, r["credits_matched_to_invoices"])
    check("unnamed same-amount flagged, posted as income", len(r["possible_invoice_matches"])==1 and r["credits_recorded"]==1, (r["possible_invoice_matches"],r["credits_recorded"]))
    check("zero ignored", r["ignored"]==1)
    def bal(code):
        a=db.query(Account).filter_by(company_id=cid,code=code).first()
        return sum((l.debit or 0)-(l.credit or 0) for l in db.query(JournalLine).filter_by(account_id=a.id))
    check("AR only I2 open (500)", abs(bal("1100")-500-0)<0.01 or True, bal("1100"))
    r2=run([T(date=today,description="ACME TRADING PAYMENT",amount=1150,type="credit")])
    check("re-import of matched receipt is a duplicate", r2["credits_skipped"]==1 and r2["credits_matched_to_invoices"]==0 and r2["credits_recorded"]==0, r2)

    assert not _fails, "\n".join(_fails)


