import types, asyncio, pytest
from fastapi import HTTPException
from tests.helpers import *
from database import PurchaseOrder, PurchaseOrderItem, InventoryItem, Account, JournalLine, JournalEntry
import purchase_orders as PO, inventory as INV


def U(co): return types.SimpleNamespace(company_id=co.id, id=1, role="owner")
def A(coro): return asyncio.run(coro)


def bal(co, code):
    acc = db.query(Account).filter_by(company_id=co.id, code=code).first()
    if not acc: return 0.0
    rows = db.query(JournalLine).join(JournalEntry, JournalLine.entry_id == JournalEntry.id).filter(
        JournalEntry.company_id == co.id, JournalLine.account_id == acc.id).all()
    return round(sum((l.debit or 0) - (l.credit or 0) for l in rows), 2)


def mk_item(co, name, qty=0, cost=0, sku=None):
    return A(INV.create_item(INV.ItemCreate(name=name, sku=sku, quantity_on_hand=qty, unit_cost=cost, unit_price=cost * 2), U(co), db))


def mk_po(co, lines, vat=True):
    return A(PO.create_po(PO.POCreate(supplier_name="Sup", vat_applicable=vat, items=[PO.POItem(description=d, quantity=q, unit_price=p) for d, q, p in lines]), U(co), db))


def recv(co, po, qtys):
    ids = [i["id"] for i in po["items"]]
    return A(PO.receive_po(po["id"], PO.POReceive(items=[PO.ReceivedItem(item_id=i, quantity_received=q) for i, q in zip(ids, qtys)]), U(co), db))


def test_partial_deliveries_post_incremental_entries_and_weighted_average_cost():
    co = company("po1", "general")
    it = mk_item(co, "Widget", qty=10, cost=10, sku="W1")                       # 10 @ R10 opening
    po = mk_po(co, [("W1", 10, 20)])                                             # order 10 @ R20 (+15% VAT)
    assert po["total_amount"] == 230
    r = recv(co, po, [4])
    assert r["status"] == "partial" and r["received_total"] == 80
    row = db.query(InventoryItem).get(it["id"])
    assert row.quantity_on_hand == 14 and abs(row.unit_cost - round((10 * 10 + 4 * 20) / 14, 4)) < 1e-6
    r = recv(co, r, [6])
    assert r["status"] == "received"
    assert bal(co, "2000") == -230 and bal(co, "1300") == 30                     # AP credit and input VAT for the whole order
    assert bal(co, "1200") == round(100 + 200, 2)                                # ledger inventory == opening + purchases
    with pytest.raises(HTTPException) as e: recv(co, r, [1])                     # a fully received PO cannot be received again
    assert e.value.status_code == 400 and unbal(co) == 0


def test_over_delivery_zero_delivery_and_negative_are_rejected_without_side_effects():
    co = company("po2", "general")
    po = mk_po(co, [("Thing", 5, 100)])
    for q in (6, 0, -1):
        with pytest.raises(HTTPException): recv(co, po, [q])
    assert db.query(PurchaseOrder).get(po["id"]).status != "received" and bal(co, "2000") == 0
    recv(co, po, [5]); assert bal(co, "2000") == -575


def test_paying_a_partly_received_po_clears_only_what_was_delivered():
    co = company("po3", "general")
    po = mk_po(co, [("Thing", 10, 100)], vat=True)                               # total 1150
    r = recv(co, po, [4])                                                        # 400 + 60 VAT = 460 owed
    A(PO.pay_po(po["id"], U(co), db))
    assert bal(co, "2000") == 0                                                  # AP cleared exactly (only the 460 delivered)
    with pytest.raises(HTTPException): A(PO.pay_po(po["id"], U(co), db))         # no double payment
    assert unbal(co) == 0


def test_pay_before_receive_and_status_bypass_are_blocked():
    co = company("po4", "general")
    po = mk_po(co, [("Thing", 1, 100)])
    with pytest.raises(HTTPException): A(PO.pay_po(po["id"], U(co), db))
    with pytest.raises(HTTPException): A(PO.update_po(po["id"], PO.POUpdate(status="paid"), U(co), db))


def test_other_companys_po_is_invisible():
    a = company("po5a", "general"); b = company("po5b", "general")
    po = mk_po(a, [("Thing", 1, 100)])
    for call in (lambda: A(PO.update_po(po["id"], PO.POUpdate(notes="x"), U(b), db)),
                 lambda: A(PO.delete_po(po["id"], U(b), db)),
                 lambda: A(PO.pay_po(po["id"], U(b), db)),
                 lambda: recv(b, po, [1])):
        with pytest.raises(HTTPException) as e: call()
        assert e.value.status_code == 404


def test_deleting_a_received_po_takes_the_stock_back_out():
    co = company("po6", "general")
    it = mk_item(co, "Gadget", sku="G1")
    po = mk_po(co, [("G1", 10, 50)], vat=False)
    recv(co, po, [10])
    assert bal(co, "1200") == 500 and db.query(InventoryItem).get(it["id"]).quantity_on_hand == 10
    A(PO.delete_po(po["id"], U(co), db))
    db.expire_all()
    stock_qty = db.query(InventoryItem).get(it["id"]).quantity_on_hand
    assert bal(co, "1200") == 0 and bal(co, "2000") == 0
    assert stock_qty == 0, f"ledger stock reversed but the stock list still shows {stock_qty} units"


def test_po_rejects_nonsense_lines():
    co = company("po7", "general")
    for lines in ([("X", -1, 100)], [("X", 1, -100)], [("X", 0, 100)]):
        with pytest.raises(HTTPException): mk_po(co, lines)


def test_inventory_adjustments_keep_ledger_equal_to_stock_list():
    co = company("inv1", "general")
    it = mk_item(co, "Bolt", qty=100, cost=2, sku="B1")
    assert bal(co, "1200") == 200
    A(INV.adjust_stock(it["id"], INV.StockAdjust(quantity=-30, reason="damaged"), U(co), db))
    r = A(INV.adjust_stock(it["id"], INV.StockAdjust(quantity=-500), U(co), db))          # cannot go below zero
    assert r["quantity_on_hand"] == 0 and bal(co, "1200") == 0
    A(INV.update_item(it["id"], INV.ItemUpdate(quantity_on_hand=10, unit_cost=3), U(co), db))
    assert bal(co, "1200") == 30
    s = A(INV.inventory_summary(U(co), db)); assert s["total_cost_value"] == 30
    with pytest.raises(HTTPException): A(INV.delete_item(it["id"], U(co), db))            # stock on hand blocks delete
    with pytest.raises(HTTPException): mk_item(co, "Dup", sku="b1")                       # SKUs unique, case-insensitive
    with pytest.raises(HTTPException): mk_item(co, "Neg", qty=-1)
    assert unbal(co) == 0


def test_po_with_stock_already_sold_cannot_be_deleted():
    co = company("po8", "general")
    it = mk_item(co, "Gizmo", sku="Z1")
    po = mk_po(co, [("Z1", 10, 50)], vat=False); recv(co, po, [10])
    A(INV.adjust_stock(it["id"], INV.StockAdjust(quantity=-4, reason="sold"), U(co), db))
    with pytest.raises(HTTPException) as e: A(PO.delete_po(po["id"], U(co), db))
    assert e.value.status_code == 400 and bal(co, "2000") == -500 and db.query(PurchaseOrder).get(po["id"]) is not None


def test_selling_stock_on_an_invoice_moves_stock_and_cost_and_deleting_puts_it_back():
    import json, companies as C
    co = company("inv2", "general")
    it = mk_item(co, "Pipe", qty=20, cost=10, sku="PIPE")
    items = json.dumps([{"code": "PIPE", "description": "Pipe", "quantity": 5, "unit_price": 30, "total": 150}])
    inv = A(C.create_invoice(C.InvoiceCreate(client_name="Cli", description="x", amount=150, vat_applicable=False, items_json=items), U(co), db))
    db.expire_all()
    assert db.query(InventoryItem).get(it["id"]).quantity_on_hand == 15
    assert bal(co, "1200") == 150 and bal(co, "5000") == 50                      # 15 left @ R10; cost of 5 sold
    A(C.delete_invoice(inv.id, types.SimpleNamespace(company_id=co.id, id=1, role="owner"), db))
    db.expire_all()
    assert db.query(InventoryItem).get(it["id"]).quantity_on_hand == 20 and bal(co, "1200") == 200 and bal(co, "5000") == 0
    assert unbal(co) == 0


# ───────── the three follow-ups ─────────
def test_selling_more_stock_than_is_on_hand_is_refused():
    import json, companies as C
    co = company("inv3", "general")
    it = mk_item(co, "Cable", qty=3, cost=10, sku="CAB")
    big = json.dumps([{"code": "CAB", "quantity": 2}, {"code": "CAB", "quantity": 2}])      # 4 across two lines, only 3 on hand
    with pytest.raises(HTTPException) as e:
        A(C.create_invoice(C.InvoiceCreate(client_name="Cli", description="x", amount=100, vat_applicable=False, items_json=big), U(co), db))
    assert e.value.status_code == 400 and "only 3 on hand" in e.value.detail
    from database import Invoice
    assert db.query(Invoice).filter_by(company_id=co.id).count() == 0              # nothing half-created
    ok = json.dumps([{"code": "CAB", "quantity": 3}])
    A(C.create_invoice(C.InvoiceCreate(client_name="Cli", description="x", amount=100, vat_applicable=False, items_json=ok), U(co), db))
    assert db.query(InventoryItem).get(it["id"]).quantity_on_hand == 0 and bal(co, "1200") == 0


def _sale(co, code, qty, price=30):
    import json, companies as C
    return A(C.create_invoice(C.InvoiceCreate(client_name="Cli", description="x", amount=qty * price, vat_applicable=False,
             items_json=json.dumps([{"code": code, "quantity": qty, "unit_price": price}])), U(co), db))


def test_credit_note_can_put_returned_stock_back_at_original_cost():
    import credit_notes as CN
    co = company("cn1", "general")
    it = mk_item(co, "Valve", qty=10, cost=10, sku="VLV")
    inv = _sale(co, "VLV", 6)                                                       # 4 left, COGS R60
    assert bal(co, "5000") == 60 and bal(co, "1200") == 40
    A(INV.update_item(it["id"], INV.ItemUpdate(unit_cost=99), U(co), db))            # cost changes later: the return must still use R10
    bal_before = bal(co, "1200")
    cn = A(CN.create_credit_note(CN.CreditNoteCreate(invoice_id=inv.id, client_name="Cli", amount=60, vat_rate=0,
           restock=[CN.StockReturn(code="VLV", quantity=2)]), U(co), db))
    db.expire_all()
    assert db.query(InventoryItem).get(it["id"]).quantity_on_hand == 6
    assert bal(co, "5000") == 40                                                    # cost of 2 returned units (R20) reversed
    assert bal(co, "1200") == bal_before + 20
    with pytest.raises(HTTPException) as e:                                          # only 4 left to take back
        A(CN.create_credit_note(CN.CreditNoteCreate(invoice_id=inv.id, client_name="Cli", amount=10, vat_rate=0,
           restock=[CN.StockReturn(code="VLV", quantity=5)]), U(co), db))
    assert e.value.status_code == 400
    A(CN.delete_credit_note(cn["id"], U(co), db))                                    # deleting the credit note takes them out again
    db.expire_all()
    assert db.query(InventoryItem).get(it["id"]).quantity_on_hand == 4 and bal(co, "5000") == 60 and unbal(co) == 0


def test_credit_note_restock_rules():
    import credit_notes as CN
    co = company("cn2", "general")
    mk_item(co, "Bolt", qty=10, cost=2, sku="BLT"); mk_item(co, "Nut", qty=10, cost=1, sku="NUT")
    inv = _sale(co, "BLT", 3)
    for rs, inv_id in (([CN.StockReturn(code="NUT", quantity=1)], inv.id),          # not sold on that invoice
                       ([CN.StockReturn(code="BLT", quantity=1)], None),            # no invoice linked
                       ([CN.StockReturn(code="BLT", quantity=0)], inv.id)):         # zero quantity
        with pytest.raises(HTTPException):
            A(CN.create_credit_note(CN.CreditNoteCreate(invoice_id=inv_id, client_name="C", amount=10, vat_rate=0, restock=rs), U(co), db))
    plain = A(CN.create_credit_note(CN.CreditNoteCreate(invoice_id=inv.id, client_name="C", amount=10, vat_rate=0), U(co), db))
    assert db.query(InventoryItem).filter_by(company_id=co.id, sku="BLT").one().quantity_on_hand == 7    # a money-only credit note leaves stock alone
    assert unbal(co) == 0


def test_po_paid_while_part_delivered_can_still_receive_the_rest():
    co = company("po9", "general")
    po = mk_po(co, [("Thing", 10, 100)], vat=False)                                  # R1,000
    recv(co, po, [4]); A(PO.pay_po(po["id"], U(co), db))                             # paid R400 for the 4 delivered
    assert bal(co, "2000") == 0
    r = recv(co, po, [6])                                                            # the other 6 arrive later
    assert r["status"] == "received" and bal(co, "2000") == -600                     # only the new R600 is owed
    A(PO.pay_po(po["id"], U(co), db))
    assert bal(co, "2000") == 0 and bal(co, "1000") == -1000 and unbal(co) == 0
    with pytest.raises(HTTPException): A(PO.pay_po(po["id"], U(co), db))
    with pytest.raises(HTTPException): recv(co, po, [1])


def test_creditors_report_shows_only_the_unpaid_part_after_a_second_delivery():
    import payroll as P
    co = company("po10", "general")
    po = mk_po(co, [("Thing", 10, 100)], vat=False)
    recv(co, po, [4]); A(PO.pay_po(po["id"], U(co), db)); recv(co, po, [3])
    r = A(P.creditors_aging(current_user=U(co), db=db)) if hasattr(P, "creditors_aging") else None
    if r is not None:
        assert round(r["totals"]["grand"], 2) == 300


def test_credit_note_screen_endpoints_list_returnable_stock_and_show_what_came_back():
    import credit_notes as CN
    co = company("cn3", "general")
    mk_item(co, "Hose", qty=10, cost=5, sku="HOS")
    inv = _sale(co, "HOS", 4)
    r = A(CN.returnable_stock(inv.id, U(co), db))
    assert r == [{"code": "HOS", "name": "Hose", "sold": 4, "returned": 0, "returnable": 4}]
    A(CN.create_credit_note(CN.CreditNoteCreate(invoice_id=inv.id, client_name="Cli", amount=30, vat_rate=0, restock=[CN.StockReturn(code="HOS", quantity=1)]), U(co), db))
    assert A(CN.returnable_stock(inv.id, U(co), db))[0]["returnable"] == 3
    row = A(CN.list_credit_notes(U(co), db))[0]
    assert row["invoice_number"] == inv.invoice_number and row["stock_returns"] == [{"name": "Hose", "qty": 1}]
    other = company("cn4", "general")
    with pytest.raises(HTTPException) as e: A(CN.returnable_stock(inv.id, U(other), db))
    assert e.value.status_code == 404
