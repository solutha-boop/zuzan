"""Regression tests for fixes made after launch."""
import types, json, asyncio, datetime as dt
import pytest
from fastapi import HTTPException
from sqlalchemy import text
from tests.helpers import *
from database import Invoice, InvoiceStatus, Account, JournalEntry, JournalLine, User
import journal as J, companies as CO, auth, payroll as P, database


def test_credit_note_vat_migration_moves_lines_from_paye_to_vat_output():
    co = company("cnmig", "general"); cid = co.id
    paye = db.query(Account).filter_by(company_id=cid, code="2200").first()
    ar = db.query(Account).filter_by(company_id=cid, code="1100").first()
    vat = db.query(Account).filter_by(company_id=cid, code="2100").first()
    je = JournalEntry(company_id=cid, date=dt.datetime.utcnow(), description="cn", reference="CN1", source="credit_note", source_id=1)
    db.add(je); db.flush()
    db.add(JournalLine(entry_id=je.id, account_id=paye.id, debit=30, credit=0))
    db.add(JournalLine(entry_id=je.id, account_id=ar.id, debit=0, credit=30)); db.commit()
    sql = next(s for s in _migration_sqls() if s.startswith("UPDATE journal_lines SET account_id"))
    for _ in range(2):          # idempotent
        db.execute(text(sql)); db.commit()
    lines = db.query(JournalLine).filter_by(entry_id=je.id).all()
    assert {l.account_id for l in lines} == {vat.id, ar.id}


def _migration_sqls():
    import inspect, re
    src = inspect.getsource(database)
    return [m.group(1) for m in re.finditer(r'"((?:UPDATE|ALTER)[^"]*)"', src)]


def test_default_password_cannot_log_in():
    from starlette.testclient import TestClient
    import main
    co = company("defpw", "general")
    for email, pw in (("owner@defpw.co.za", "Zuzan2025"), ("real@defpw.co.za", "S0me-Strong-Pass!")):
        db.add(User(email=email, hashed_password=auth.hash_password(pw), first_name="O", last_name="W", company_id=co.id, role="owner"))
    db.commit()
    c = TestClient(main.app)
    bad = c.post("/auth/login", json={"email": "owner@defpw.co.za", "password": "Zuzan2025"})
    assert bad.status_code in (401, 403), (bad.status_code, bad.text)
    assert "access_token" not in bad.text
    good = c.post("/auth/login", json={"email": "real@defpw.co.za", "password": "S0me-Strong-Pass!"})
    assert good.status_code == 200 and "access_token" in good.json(), (good.status_code, good.text)


def test_emp201_honours_selected_period_and_business_day_due_date():
    co = company("emp201", "general"); e = emp(co, "E1", 20000)
    user = types.SimpleNamespace(company_id=co.id, id=1)
    r = asyncio.run(P.emp201(current_user=user, db=db, period="2026-03"))
    assert r["period_key"] == "2026-03" and r["period"] == "March 2026"
    assert r["due_date"] == "07 April 2026"           # Tuesday
    r2 = asyncio.run(P.emp201(current_user=user, db=db, period="2026-05"))
    assert r2["due_date"] == "05 June 2026"           # 7 June 2026 is a Sunday -> Friday 5 June
    with pytest.raises(HTTPException):
        asyncio.run(P.emp201(current_user=user, db=db, period="bad"))


def test_non_registered_company_lines_carry_no_vat():
    from database import Company
    co = company("novatlines", "general"); c = db.query(Company).get(co.id); c.vat_registered = False; db.commit()
    user = types.SimpleNamespace(company_id=co.id, id=1, role="owner")
    items = json.dumps([{"code": "X", "description": "d", "quantity": 2, "unit_price": 100, "vat_applicable": True, "vat_amount": 30, "total": 230}])
    inv = asyncio.run(CO.create_invoice(CO.InvoiceCreate(client_name="Z", description="d", amount=200, items_json=items), current_user=user, db=db))
    assert inv.vat_amount == 0 and inv.total_amount == 200
    line = json.loads(inv.items_json)[0]
    assert line["vat_amount"] == 0 and line["vat_applicable"] is False
    # amending must not bring VAT back
    items2 = json.dumps([{"code": "X", "description": "d", "quantity": 3, "unit_price": 100, "vat_applicable": True, "vat_amount": 45, "total": 345}])
    inv2 = asyncio.run(CO.update_invoice(inv.id, CO.InvoiceUpdate(items_json=items2, amount=300), current_user=user, db=db))
    assert inv2.vat_amount == 0 and inv2.total_amount == 300


def test_dashboard_expenses_match_ledger_for_stock_and_backfill_restores_stock_net():
    """A stock purchase is an asset, not an expense: the dashboard must show cost only when the goods are sold
    (or written off), exactly as the ledger does."""
    import inventory as IV, purchase_orders as PO
    from database import PurchaseOrder
    co = company("dashstk", "general"); cid = co.id
    user = types.SimpleNamespace(company_id=cid, id=1, role="owner")
    it = asyncio.run(IV.create_item(IV.ItemCreate(name="Gadget", sku="GAD1", unit_cost=10, unit_price=25, quantity_on_hand=0), current_user=user, db=db))
    po = asyncio.run(PO.create_po(PO.POCreate(supplier_name="S", vat_applicable=True, items=[PO.POItem(description="Gadget", quantity=100, unit_price=12)]), current_user=user, db=db))
    asyncio.run(PO.receive_po(po["id"], PO.POReceive(items=[PO.ReceivedItem(item_id=po["items"][0]["id"], quantity_received=100)]), current_user=user, db=db))

    def dash():
        return asyncio.run(P.dashboard(current_user=user, db=db))["total_expenses"]

    def ledger_expenses():
        tot = 0.0
        for a in db.query(Account).filter_by(company_id=cid):
            if getattr(a.type, "value", a.type) == "expense":
                tot += sum((l.debit or 0) - (l.credit or 0) for l in db.query(JournalLine).filter_by(account_id=a.id))
        return round(tot, 2)

    assert dash() == 0 and ledger_expenses() == 0          # bought stock, sold nothing: no expense yet
    items = json.dumps([{"code": "GAD1", "description": "Gadget", "quantity": 30, "unit_price": 25, "vat_applicable": True}])
    asyncio.run(CO.create_invoice(CO.InvoiceCreate(client_name="C", description="s", amount=750, items_json=items), current_user=user, db=db))
    assert ledger_expenses() == 360 and dash() == 360, (dash(), ledger_expenses())
    asyncio.run(IV.adjust_stock(it["id"], IV.StockAdjust(quantity=-5, reason="damaged"), current_user=user, db=db)) if hasattr(IV, "adjust_stock") else None
    assert abs(dash() - ledger_expenses()) < 0.01, (dash(), ledger_expenses())

    # backfill for purchase orders received before stock_received_net existed
    row = db.query(PurchaseOrder).get(po["id"])
    assert row.stock_received_net == 1200
    row.stock_received_net = 0; db.commit()
    sql = next(s for s in _migration_sqls() if s.startswith("UPDATE purchase_orders SET stock_received_net"))
    for _ in range(2):
        db.execute(text(sql)); db.commit()
    db.refresh(row); assert row.stock_received_net == 1200
