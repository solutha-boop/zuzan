"""Auto-ported from the pre-launch verification scripts. Each test runs one end-to-end scenario against a throwaway SQLite DB and asserts every check."""
import sys, types, asyncio, json, datetime as dt
from tests.helpers import *
from database import Account, JournalLine, InventoryItem, Invoice, InvoiceStatus, PurchaseOrder
import journal as J, companies as CO, inventory as IV, purchase_orders as PO

_fails = []
def check(n, c, x=""):
    if not c: _fails.append(f"{n} {x}")

def test_stock_linked_to_invoices_and_pos():
    co=company("stkco","general"); cid=co.id; user=types.SimpleNamespace(company_id=cid,id=1,role="owner")
    J.init_accounts(cid,db)
    def bal(code):
        a=db.query(Account).filter_by(company_id=cid,code=code).first()
        return sum((l.debit or 0)-(l.credit or 0) for l in db.query(JournalLine).filter_by(account_id=a.id)) if a else 0
    it=asyncio.run(IV.create_item(IV.ItemCreate(name="Widget",sku="WID1",unit_cost=10,unit_price=25,quantity_on_hand=0),current_user=user,db=db))
    try: asyncio.run(IV.create_item(IV.ItemCreate(name="W2",sku="wid1"),current_user=user,db=db)); check("dup sku blocked",False)
    except Exception: check("dup sku blocked",True)
    # purchase 100 @ 12 (ex VAT) via PO
    po=asyncio.run(PO.create_po(PO.POCreate(supplier_name="Sup",vat_applicable=True,items=[PO.POItem(description="Widget",quantity=100,unit_price=12)]),current_user=user,db=db))
    pid=po["id"]; itemid=po["items"][0]["id"]
    asyncio.run(PO.receive_po(pid,PO.POReceive(items=[PO.ReceivedItem(item_id=itemid,quantity_received=100)]),current_user=user,db=db))
    check("stock ledger 1200 = 1200", abs(bal("1200")-1200)<0.01, bal("1200"))
    check("COGS 5000 untouched by stock purchase", abs(bal("5000"))<0.01, bal("5000"))
    d=db.query(InventoryItem).get(it["id"]); check("qty 100, cost 12", d.quantity_on_hand==100 and abs(d.unit_cost-12)<0.001,(d.quantity_on_hand,d.unit_cost))
    # sell 30
    items=json.dumps([{"code":"wid1","description":"Widget","quantity":30,"unit_price":25,"vat_applicable":True}])
    inv=asyncio.run(CO.create_invoice(CO.InvoiceCreate(client_name="Cli",description="sale",amount=750,items_json=items),current_user=user,db=db))
    db.refresh(d)
    check("qty 70 after sale", d.quantity_on_hand==70, d.quantity_on_hand)
    check("COGS 360 posted", abs(bal("5000")-360)<0.01, bal("5000"))
    check("inventory ledger 840 == 70x12", abs(bal("1200")-840)<0.01, bal("1200"))
    # amend qty to 10 via items -> restock + repost
    items2=json.dumps([{"code":"WID1","description":"Widget","quantity":10,"unit_price":25,"vat_applicable":True}])
    asyncio.run(CO.update_invoice(inv.id,CO.InvoiceUpdate(items_json=items2),current_user=user,db=db))
    db.refresh(d)
    check("amend: qty 90, COGS 120", d.quantity_on_hand==90 and abs(bal("5000")-120)<0.01, (d.quantity_on_hand,bal("5000")))
    check("amend: ledger == stock list", abs(bal("1200")-90*12)<0.01, bal("1200"))
    asyncio.run(CO.delete_invoice(inv.id,current_user=user,db=db)); db.refresh(d)
    check("delete: qty 100, COGS back to 0", d.quantity_on_hand==100 and abs(bal("5000"))<0.01, (d.quantity_on_hand,bal("5000")))

    assert not _fails, "\n".join(_fails)


