"""Bank lines allocated to Debtors/Creditors Control or PPE (audit fix 2026-11-22).

- 1100 (receipt) settles the matching open invoice; 2110 (payment) settles the matching received PO or
  unpaid on-credit expense. Nothing is booked as a loose bank journal that the sub-ledger can't see.
- No single match -> the line is NOT posted and is reported in needs_matching.
- A payment allocated to PPE goes into the fixed-asset register (DR 1500, VAT to 1300).
- AFS: picker PPE (1211-1219) is non-current and investing; 2410/2420 loans are non-current and
  financing; 2150/2160 stay current but their cash flows are financing.
"""
import types, asyncio, datetime as dt
from tests.helpers import *
from database import (Invoice, InvoiceStatus, Account, JournalLine, JournalEntry, PurchaseOrder,
                      Expense, FixedAsset)
import journal as J, companies as CO, financial_statements as FS

T = CO.BankTransaction


def _user(co):
    return types.SimpleNamespace(company_id=co.id, id=1, role="owner")


def _run(co, txns):
    return asyncio.run(CO.import_bank_statement(CO.BankImportRequest(bank="fnb", transactions=txns),
                                                current_user=_user(co), db=db))


def _bal(cid, code):
    a = db.query(Account).filter_by(company_id=cid, code=code).first()
    if not a:
        return 0.0
    return round(sum((l.debit or 0) - (l.credit or 0) for l in db.query(JournalLine).filter_by(account_id=a.id)), 2)


def _loose(cid):
    return db.query(JournalEntry).filter_by(company_id=cid, source="bank_import_transfer").count()


def test_receipt_to_debtors_control_settles_invoice():
    co = company("ctrl_ar", "general"); cid = co.id
    inv = Invoice(company_id=cid, invoice_number="INV-9", client_name="Mokoena Builders", amount=1000,
                  vat_amount=150, total_amount=1150, status=InvoiceStatus.sent,
                  issue_date=dt.datetime.now(), due_date=dt.datetime.now())
    db.add(inv); db.commit(); db.refresh(inv); J.post_invoice_raised(inv, db); db.commit()
    day = "2026-11-10"
    r = _run(co, [T(date=day, description="MOKOENA BUILDERS EFT", amount=1150, type="credit",
                    category="1100 - Trade Receivables (Debtors)")])
    db.refresh(inv)
    assert r["documents_settled"] == 1 and not r["needs_matching"], r
    assert inv.status == InvoiceStatus.paid and inv.paid_date.date().isoformat() == day
    assert abs(_bal(cid, "1100")) < 0.01 and _loose(cid) == 0
    r2 = _run(co, [T(date=day, description="MOKOENA BUILDERS EFT", amount=1150, type="credit",
                     category="1100 - Trade Receivables (Debtors)")])
    assert r2["documents_settled"] == 0 and r2["transfers_skipped"] == 1, r2
    assert abs(_bal(cid, "1000") - 1150) < 0.01


def test_unmatched_control_allocation_is_not_posted():
    co = company("ctrl_none", "general"); cid = co.id
    r = _run(co, [T(date="2026-11-10", description="SOMEONE", amount=999, type="credit",
                    category="1100 - Trade Receivables (Debtors)"),
                  T(date="2026-11-10", description="SUPPLIER X", amount=500, type="debit",
                    category="2110 - Trade Payables (Creditors)")])
    assert len(r["needs_matching"]) == 2 and r["documents_settled"] == 0, r
    assert _bal(cid, "1000") == 0 and _loose(cid) == 0


def test_payment_to_creditors_control_settles_po_and_expense():
    co = company("ctrl_ap", "general"); cid = co.id
    po = PurchaseOrder(company_id=cid, po_number="PO-77", supplier_name="Bolt Hardware", status="received",
                       subtotal=2000, vat_amount=300, total_amount=2300)
    db.add(po); db.commit(); db.refresh(po); J.post_po_received(po, db); db.commit()
    ex = Expense(company_id=cid, vendor="Cape Printers", description="Flyers", amount=575, vat_amount=75,
                 category="Marketing", expense_date=dt.datetime(2026, 11, 1), is_on_credit=True)
    db.add(ex); db.commit(); db.refresh(ex); J.post_expense(ex, db); db.commit()
    assert abs(_bal(cid, "2000") + 2875) < 0.01
    r = _run(co, [T(date="2026-11-12", description="BOLT HARDWARE PMT", amount=2300, type="debit",
                    category="2110 - Trade Payables (Creditors)"),
                  T(date="2026-11-13", description="CAPE PRINTERS", amount=575, type="debit",
                    category="2110 - Trade Payables (Creditors)")])
    db.refresh(po); db.refresh(ex)
    assert r["documents_settled"] == 2 and not r["needs_matching"], r
    assert po.status == "paid" and ex.paid_at.date().isoformat() == "2026-11-13"
    assert abs(_bal(cid, "2000")) < 0.01 and _loose(cid) == 0
    pay = db.query(JournalEntry).filter_by(company_id=cid, source="po_payment", source_id=po.id).one()
    assert pay.date.date().isoformat() == "2026-11-12"
    r2 = _run(co, [T(date="2026-11-12", description="BOLT HARDWARE PMT", amount=2300, type="debit",
                     category="2110 - Trade Payables (Creditors)")])
    assert r2["transfers_skipped"] == 1 and r2["documents_settled"] == 0, r2
    assert unbal(co) == 0


def test_ppe_allocation_goes_to_register_and_afs_classification():
    co = company("ctrl_ppe", "general"); cid = co.id
    r = _run(co, [T(date="2026-06-15", description="INCREDIBLE CONNECTION", amount=11500, type="debit",
                    category="1213 - Computer Equipment", has_vat=True, vat_amount=1500),
                  T(date="2026-06-01", description="BANK LOAN ADVANCE", amount=50000, type="credit",
                    category="2210 - Long-term Loan"),
                  T(date="2026-06-02", description="DIRECTOR LOAN", amount=8000, type="credit",
                    category="2160 - Directors Loan Account")])
    assert r["assets_registered"] == 1, r
    fa = db.query(FixedAsset).filter_by(company_id=cid).one()
    assert fa.cost == 10000 and fa.category == "Computer Equipment" and fa.useful_life_months == 36
    assert abs(_bal(cid, "1500") - 10000) < 0.01 and abs(_bal(cid, "1300") - 1500) < 0.01
    assert _bal(cid, "1213") == 0
    r2 = _run(co, [T(date="2026-06-15", description="INCREDIBLE CONNECTION", amount=11500, type="debit",
                     category="1213 - Computer Equipment", has_vat=True, vat_amount=1500)])
    assert r2["transfers_skipped"] == 1 and db.query(FixedAsset).filter_by(company_id=cid).count() == 1

    afs = FS.annual_financial_statements(year=2027, db=db, current_user=_user(co))
    bs = afs["balance_sheet"]
    assert bs["balanced"], bs
    ncl = {l["code"] for l in bs["liabilities"]["non_current"]}
    cl = {l["code"] for l in bs["liabilities"]["current"]}
    assert "2410" in ncl and "2410" not in cl and "2160" in cl
    cf = afs["cash_flow"]
    assert abs(cf["financing"]["change_in_long_term_liabilities"] - 58000) < 0.01, cf["financing"]
    assert abs(cf["investing"]["purchase_of_fa"] + 10000) < 0.01, cf["investing"]


def test_afs_legacy_picker_ppe_is_non_current_and_investing():
    co = company("ctrl_legacy", "general"); cid = co.id
    # a vehicle booked to 1212 by a manual journal (or an import before 2026-11-22)
    veh = J.allocation_account(cid, "1212 - Vehicles", db)
    bank = J.get_account(cid, "1000", db)
    e = J._make_entry(cid, dt.date(2026, 7, 1), "Vehicle", "MJ1", "manual", None, db)
    db.add(J._line(e.id, veh, debit=200000, description="Vehicle"))
    db.add(J._line(e.id, bank, credit=200000, description="Bank"))
    db.commit()
    afs = FS.annual_financial_statements(year=2027, db=db, current_user=_user(co))
    nca = {l["code"] for l in afs["balance_sheet"]["assets"]["non_current"]}
    assert "1212" in nca
    cf = afs["cash_flow"]
    assert abs(cf["investing"]["other"] + 200000) < 0.01, cf["investing"]
    assert abs(cf["operating"]["change_in_other_assets"]) < 0.01, cf["operating"]
