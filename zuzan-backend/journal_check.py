"""
Journal entry integrity audit for ZuZan.

Finds invoices, expenses, and purchase orders that have no corresponding
JournalEntry row -- i.e. a silent posting failure that would misstate the
balance sheet / P&L.

Source values (confirmed against journal.py _make_entry() call sites):
  post_invoice_raised -> source="invoice"
  post_invoice_paid   -> source="invoice_payment"
  post_expense        -> source="expense"
  post_po_received    -> source="purchase_order"
  post_po_paid        -> source="po_payment"

NOTE: queries use explicit column lists (not the ORM model classes) so the
audit is robust to schema drift between database.py and the actual DB file
(see report for a drift finding on this run).
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402
from database import SessionLocal, DATABASE_URL  # noqa: E402

db = SessionLocal()

def journal_source_ids(source):
    rows = db.execute(
        text("SELECT source_id FROM journal_entries WHERE source = :s"), {"s": source}
    ).all()
    return {r[0] for r in rows if r[0] is not None}

results = {}

# 1. Invoices missing "invoice" entry (status != draft)
inv_je_ids = journal_source_ids("invoice")
rows = db.execute(text(
    "SELECT id, company_id, invoice_number, status, total_amount FROM invoices WHERE status != 'draft'"
)).all()
results["invoices_missing_invoice_entry"] = [
    {"id": r[0], "company_id": r[1], "invoice_number": r[2], "status": r[3], "total_amount": r[4]}
    for r in rows if r[0] not in inv_je_ids
]

# 2. Paid invoices missing "invoice_payment" entry
pay_je_ids = journal_source_ids("invoice_payment")
rows = db.execute(text(
    "SELECT id, company_id, invoice_number, total_amount, paid_date FROM invoices WHERE status = 'paid'"
)).all()
results["paid_invoices_missing_payment_entry"] = [
    {"id": r[0], "company_id": r[1], "invoice_number": r[2], "total_amount": r[3], "paid_date": str(r[4]) if r[4] else None}
    for r in rows if r[0] not in pay_je_ids
]

# 3. Expenses missing "expense" entry
exp_je_ids = journal_source_ids("expense")
rows = db.execute(text("SELECT id, company_id, vendor, amount FROM expenses")).all()
results["expenses_missing_entry"] = [
    {"id": r[0], "company_id": r[1], "vendor": r[2], "amount": r[3]}
    for r in rows if r[0] not in exp_je_ids
]

# 4. Received/partial/paid POs missing "purchase_order" entry
po_je_ids = journal_source_ids("purchase_order")
rows = db.execute(text(
    "SELECT id, company_id, po_number, status, total_amount FROM purchase_orders WHERE status IN ('received','partial','paid')"
)).all()
results["pos_missing_purchase_order_entry"] = [
    {"id": r[0], "company_id": r[1], "po_number": r[2], "status": r[3], "total_amount": r[4]}
    for r in rows if r[0] not in po_je_ids
]

# 5. Paid POs missing "po_payment" entry
popay_je_ids = journal_source_ids("po_payment")
rows = db.execute(text(
    "SELECT id, company_id, po_number, total_amount FROM purchase_orders WHERE status = 'paid'"
)).all()
results["paid_pos_missing_payment_entry"] = [
    {"id": r[0], "company_id": r[1], "po_number": r[2], "total_amount": r[3]}
    for r in rows if r[0] not in popay_je_ids
]

total_gaps = sum(len(v) for v in results.values())

# Extra context: record counts + schema-drift check on invoices table
counts_ctx = {}
for t in ["invoices", "expenses", "purchase_orders", "journal_entries"]:
    counts_ctx[t] = db.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()

drift = []
if DATABASE_URL.startswith("sqlite"):
    expected_invoice_cols = {
        "id","company_id","invoice_number","client_name","client_email","description",
        "amount","vat_amount","total_amount","currency","exchange_rate","status",
        "issue_date","due_date","paid_date","paid_amount_zar","notes","portal_token",
        "portal_token_created_at","items_json","tour_ref","quote_ref","tax_ref",
        "travel_date","pax_count","passenger_name","created_at",
    }
    actual_cols = {r[1] for r in db.execute(text("PRAGMA table_info(invoices)")).all()}
    missing_cols = sorted(expected_invoice_cols - actual_cols)
    if missing_cols:
        drift.append({"table": "invoices", "missing_columns": missing_cols})

output = {
    "database_url": DATABASE_URL,
    "run_at_utc": datetime.now(timezone.utc).isoformat(),
    "total_gaps": total_gaps,
    "status": "PASS" if total_gaps == 0 else "FAIL",
    "counts": {k: len(v) for k, v in results.items()},
    "record_counts": counts_ctx,
    "schema_drift": drift,
    "details": results,
}

print(json.dumps(output, indent=2, default=str))

db.close()
