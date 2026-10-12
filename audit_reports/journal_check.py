"""ZuZan journal integrity audit. Usage: python3 journal_check.py <path-to-sqlite-db>"""
import sqlite3, sys, json
con = sqlite3.connect(sys.argv[1]); con.row_factory = sqlite3.Row
def q(sql): return [dict(r) for r in con.execute(sql)]
checks = {
 "1_invoices_missing_invoice_entry": "SELECT id, company_id, invoice_number, status, total_amount FROM invoices i WHERE status != 'draft' AND NOT EXISTS (SELECT 1 FROM journal_entries j WHERE j.source='invoice' AND j.source_id=i.id)",
 "2_paid_invoices_missing_invoice_payment_entry": "SELECT id, company_id, invoice_number, status, total_amount FROM invoices i WHERE status='paid' AND NOT EXISTS (SELECT 1 FROM journal_entries j WHERE j.source='invoice_payment' AND j.source_id=i.id)",
 "3_expenses_missing_expense_entry": "SELECT id, company_id, vendor, amount FROM expenses e WHERE NOT EXISTS (SELECT 1 FROM journal_entries j WHERE j.source='expense' AND j.source_id=e.id)",
 "4_pos_missing_purchase_order_entry": "SELECT id, company_id, po_number, status FROM purchase_orders p WHERE status IN ('received','partial','paid') AND NOT EXISTS (SELECT 1 FROM journal_entries j WHERE j.source='purchase_order' AND j.source_id=p.id)",
 "5_paid_pos_missing_po_payment_entry": "SELECT id, company_id, po_number, status FROM purchase_orders p WHERE status='paid' AND NOT EXISTS (SELECT 1 FROM journal_entries j WHERE j.source='po_payment' AND j.source_id=p.id)",
}
out = {"counts": {t: con.execute(f"select count(*) from {t}").fetchone()[0] for t in ["invoices","expenses","purchase_orders","journal_entries"]}, "checks": {}}
for k, s in checks.items(): out["checks"][k] = q(s)
out["total_gaps"] = sum(len(v) for v in out["checks"].values())
print(json.dumps(out, indent=1, default=str))
