"""ZuZan journal entry integrity audit.
Usage: python3 journal_check.py <sqlite-db-path>
Opens the DB read-only (immutable copy recommended) and prints JSON results.
Sources (journal.py _make_entry call sites): invoice, invoice_payment, expense, purchase_order, po_payment.
"""
import json, sqlite3, sys

db_path = sys.argv[1]
con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
con.row_factory = sqlite3.Row

def q(sql):
    return [dict(r) for r in con.execute(sql)]

def missing(table, source, where):
    return q(f"""
        SELECT t.id, t.company_id, t.status FROM {table} t
        WHERE {where}
          AND NOT EXISTS (SELECT 1 FROM journal_entries je
                          WHERE je.source = '{source}' AND je.source_id = t.id)
        ORDER BY t.company_id, t.id""")

exp_cols = [r[1] for r in con.execute("PRAGMA table_info(expenses)")]
exp_status = "t.status" if "status" in exp_cols else "NULL AS status"

checks = {
  "1_invoices_missing_invoice": missing("invoices", "invoice", "LOWER(t.status) != 'draft'"),
  "2_paid_invoices_missing_invoice_payment": missing("invoices", "invoice_payment", "LOWER(t.status) = 'paid'"),
  "3_expenses_missing_expense": q(f"""SELECT t.id, t.company_id, {exp_status} FROM expenses t
        WHERE NOT EXISTS (SELECT 1 FROM journal_entries je WHERE je.source='expense' AND je.source_id=t.id)
        ORDER BY t.company_id, t.id"""),
  "4_pos_missing_purchase_order": missing("purchase_orders", "purchase_order", "LOWER(t.status) IN ('received','partial','paid')"),
  "5_paid_pos_missing_po_payment": missing("purchase_orders", "po_payment", "LOWER(t.status) = 'paid'"),
}
counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
          for t in ("invoices","expenses","purchase_orders","journal_entries","companies")}
inv_status = q("SELECT status, COUNT(*) n FROM invoices GROUP BY status")
po_status = q("SELECT status, COUNT(*) n FROM purchase_orders GROUP BY status")
print(json.dumps({"counts": counts, "invoice_status": inv_status, "po_status": po_status,
                  "checks": checks, "total_gaps": sum(len(v) for v in checks.values())}, indent=2, default=str))
