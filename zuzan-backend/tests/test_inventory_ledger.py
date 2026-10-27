"""Auto-ported from the pre-launch verification scripts. Each test runs one end-to-end scenario against a throwaway SQLite DB and asserts every check."""
import sys, types, asyncio
from tests.helpers import *
from database import Account, JournalLine
import inventory as IV

_fails = []
def check(n, c, x=""):
    if not c: _fails.append(f"{n} {x}")

def test_inventory_ledger():
    co=company("ivco","general"); cid=co.id; user=types.SimpleNamespace(company_id=cid,id=1,role="owner")
    def bal(code):
        a=db.query(Account).filter_by(company_id=cid,code=code).first()
        return sum((l.debit or 0)-(l.credit or 0) for l in db.query(JournalLine).filter_by(account_id=a.id)) if a else 0
    r=asyncio.run(IV.create_item(IV.ItemCreate(name="Widget",unit_cost=10,unit_price=20,quantity_on_hand=100),current_user=user,db=db))
    check("opening stock on ledger 1000", abs(bal("1200")-1000)<0.01, bal("1200"))
    iid=r["id"]
    asyncio.run(IV.adjust_stock(iid,IV.StockAdjust(quantity=-10),current_user=user,db=db)); check("write-off 10 -> 900", abs(bal("1200")-900)<0.01, bal("1200"))
    asyncio.run(IV.update_item(iid,IV.ItemUpdate(unit_cost=12),current_user=user,db=db)); check("reval 90 units x2 -> 1080", abs(bal("1200")-1080)<0.01, bal("1200"))
    asyncio.run(IV.update_item(iid,IV.ItemUpdate(quantity_on_hand=80),current_user=user,db=db)); check("count to 80 @12 -> 960", abs(bal("1200")-960)<0.01, bal("1200"))
    s=asyncio.run(IV.inventory_summary(current_user=user,db=db)); check("ledger == stock list value", abs(s["total_cost_value"]-bal("1200"))<0.01,(s["total_cost_value"],bal("1200")))
    try: asyncio.run(IV.delete_item(iid,current_user=user,db=db)); check("delete blocked with stock",False)
    except Exception: check("delete blocked with stock",True)
    try: asyncio.run(IV.create_item(IV.ItemCreate(name="Bad",unit_cost=-1),current_user=user,db=db)); check("negative blocked",False)
    except Exception: check("negative blocked",True)

    assert not _fails, "\n".join(_fails)


