# Journal Entry Integrity Audit — 2026-07-06

Database: `zuzan-backend/zuzan.db` (SQLite, opened read-only; file last modified 2026-06-29)
Script: `journal_check.py` — checks for invoices, expenses, and purchase orders with no corresponding journal entry.

## 1. Summary

**Overall result: PASS** — 0 gaps found across all 5 checks.

| # | Check | Records in scope | Gaps |
|---|-------|-----------------|------|
| 1 | Non-draft invoices missing `invoice` entry | 1 | 0 |
| 2 | Paid invoices missing `invoice_payment` entry | 0 | 0 |
| 3 | Expenses missing `expense` entry | 14 | 0 |
| 4 | Received/partial/paid POs missing `purchase_order` entry | 0 | 0 |
| 5 | Paid POs missing `po_payment` entry | 0 | 0 |

Database contents at time of audit: 1 invoice (status `overdue`), 14 expenses, 0 purchase orders, 16 journal entries (1 `invoice`, 14 `expense`, 1 `payroll`).

## 2. Findings

### Check 1 — Invoices missing "invoice" journal entry
No gaps. The single non-draft invoice (status `overdue`) has a matching `source='invoice'` journal entry.

### Check 2 — Paid invoices missing "invoice_payment" entry
No gaps. No invoices with status `paid` exist.

### Check 3 — Expenses missing "expense" entry
No gaps. All 14 expenses have matching `source='expense'` journal entries.

### Check 4 — Received/partial/paid POs missing "purchase_order" entry
No gaps. No purchase orders exist in the database.

### Check 5 — Paid POs missing "po_payment" entry
No gaps. No purchase orders exist in the database.

## 3. Recommended fix

None required — no gaps found. If gaps appear in a future run, calling `POST /journal/backfill` (authenticated) will repair them.

## Notes

- Journal-entry matching was scoped by `company_id` in addition to `source`/`source_id`, per the data model.
- Invoice/PO statuses compared case-insensitively (enum values are stored lowercase).
- Consistent with the previous run (2026-06-29): PASS, no change.
