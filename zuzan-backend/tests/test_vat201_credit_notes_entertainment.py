"""Auto-ported from the pre-launch verification scripts. Each test runs one end-to-end scenario against a throwaway SQLite DB and asserts every check."""
import sys, types, asyncio, datetime as dt
from tests.helpers import *
from database import Invoice, InvoiceStatus, Expense, CreditNote
import credit_notes as CNm, journal as J

_fails = []
def check(n, c, x=""):
    if not c: _fails.append(f"{n} {x}")

def test_vat201_credit_notes_entertainment():
    co=company("vatco","general"); cid=co.id
    user=types.SimpleNamespace(company_id=cid, id=1)
    Y,Mo=now.year,now.month; D=lambda d: dt.datetime(Y,Mo,d)
    def inv(no,amt,vat,d=5,status=InvoiceStatus.sent):
        i=Invoice(company_id=cid,invoice_number=no,client_name="C",amount=amt,vat_amount=vat,total_amount=amt+vat,status=status,issue_date=D(d),due_date=D(20))
        db.add(i); db.commit(); db.refresh(i); J.init_accounts(cid,db); J.post_invoice_raised(i,db) if hasattr(J,'post_invoice_raised') else None; db.commit(); return i
    i1=inv("I1",1000,150); i2=inv("I2",500,0)           # standard + zero-rated
    def exp(v,amt,vat,cat="Utilities"):
        e=Expense(company_id=cid,vendor=v,amount=amt,vat_amount=vat,category=cat,expense_date=D(8)); db.add(e); db.commit(); db.refresh(e); J.post_expense(e,db); db.commit(); return e
    e_vat=exp("A",1150,150); e_none=exp("B",400,0); e_ent=exp("C",1150,150,"Entertainment")
    def vat(): return asyncio.run(P.vat201(current_user=user, db=db, period=f"{Y}-{Mo:02d}"))
    r=vat()
    check("input VAT = only the 150 recorded (not 15/115 of everything)", r["input"]["field_14_input_vat"]==150.0, r["input"]["field_14_input_vat"])
    check("output VAT 150 before credit note", r["output"]["field_4a_output_vat"]==150.0, r["output"]["field_4a_output_vat"])
    # credit note on the standard invoice, rate inherited
    body=CNm.CreditNoteCreate(client_name="C", invoice_id=i1.id, description="return", amount=200, issue_date=D(10).isoformat())
    asyncio.run(CNm.create_credit_note(body=body,current_user=user,db=db))
    cn=db.query(CreditNote).filter_by(company_id=cid).order_by(CreditNote.id.desc()).first()
    check("credit note VAT 30", cn.vat_amount==30.0, cn.vat_amount)
    # credit note on zero-rated invoice must carry no VAT
    body0=CNm.CreditNoteCreate(client_name="C", invoice_id=i2.id, description="return0", amount=100, issue_date=D(10).isoformat())
    asyncio.run(CNm.create_credit_note(body=body0,current_user=user,db=db))
    cn0=db.query(CreditNote).filter_by(company_id=cid).order_by(CreditNote.id.desc()).first()
    check("credit note on zero-rated invoice has NO VAT", cn0.vat_amount==0, cn0.vat_amount)
    r=vat()
    check("output VAT reduced by credit note -> 120", r["output"]["field_4a_output_vat"]==120.0, r["output"]["field_4a_output_vat"])
    # ledger: VAT output account 2100 balance equals VAT201 output
    from database import Account, JournalLine
    acc=db.query(Account).filter_by(company_id=cid,code="2100").first()
    bal=sum((l.credit or 0)-(l.debit or 0) for l in db.query(JournalLine).filter_by(account_id=acc.id))
    paye=db.query(Account).filter_by(company_id=cid,code="2200").first()
    pb=sum((l.credit or 0)-(l.debit or 0) for l in db.query(JournalLine).filter_by(account_id=paye.id))
    check("ledger VAT Output (2100) == VAT201 output", abs(bal-r["output"]["field_4a_output_vat"])<0.01, f"ledger {bal} vs report {r['output']['field_4a_output_vat']}")
    check("PAYE Payable untouched by credit note", pb==0, pb)
    # entertainment: ledger VAT input excludes it
    a13=db.query(Account).filter_by(company_id=cid,code="1300").first()
    ib=sum((l.debit or 0)-(l.credit or 0) for l in db.query(JournalLine).filter_by(account_id=a13.id))
    check("ledger VAT Input (1300) == VAT201 input (entertainment excluded)", abs(ib-150)<0.01, ib)
    # due dates (25th, back to last business day if weekend/holiday)
    def due(per,m=1): return asyncio.run(P.vat201(current_user=user, db=db, period=per, months=m))
    for per,m,expd in (("2026-10",1,"25 November 2026"),("2026-11",1,"24 December 2026"),("2026-12",1,"25 January 2027"),("2026-10",2,"24 December 2026")):
        r2=due(per,m); check(f"due {per} months={m}", r2["due_date"]==expd, f'{r2["due_date"]} | {r2["period"]}')
    # bi-monthly spans both months
    e2=Expense(company_id=cid,vendor="N",amount=230,vat_amount=30,category="Utilities",expense_date=dt.datetime(Y,Mo,8)+dt.timedelta(days=40)); db.add(e2); db.commit(); J.post_expense(e2,db); db.commit()
    # not-VAT-registered company
    from database import Company
    co2=company("novat","general"); c2=db.query(Company).get(co2.id); c2.vat_registered=False; db.commit()
    u2=types.SimpleNamespace(company_id=co2.id,id=2)
    import companies as CO
    ex=asyncio.run(CO.create_expense(CO.ExpenseCreate(vendor="V",description="d",amount=1000,category="Utilities",expense_date=D(3).isoformat(),vat_applicable=True),current_user=u2,db=db))
    check("non-registered: expense carries no VAT", ex.vat_amount==0 and ex.amount==1000, (ex.vat_amount,ex.amount))
    iv=asyncio.run(CO.create_invoice(CO.InvoiceCreate(client_name="X",description="d",amount=1000,vat_applicable=True,due_date=D(25).isoformat()),current_user=u2,db=db)) if hasattr(CO,'create_invoice') else None
    if iv is not None:
        check("non-registered: invoice carries no VAT", (iv.vat_amount or 0)==0 and iv.total_amount==1000, (iv.vat_amount,iv.total_amount))
    rr=asyncio.run(P.vat201(current_user=u2, db=db, period=f"{Y}-{Mo:02d}"))
    check("vat201 flags not registered", rr["vat_registered"] is False)
    check("registered company flagged True", vat()["vat_registered"] is True)
    assert unbal(co)==0 and unbal(co2)==0

    assert not _fails, "\n".join(_fails)


