# Journal Entry Integrity Audit — 2026-07-13

## Summary

**Overall: PASS** — 0 gaps found across all 5 checks.

Database: `zuzan-backend/zuzan.db` (SQLite, file mtime 2026-06-29 as seen from the audit sandbox — if the app has written since then and results look wrong, re-run against a fresh copy). 16 journal entries total.

| Check | Population | Gaps |
|---|---|---|
| Non-draft invoices missing `invoice` entry | 1 | 0 |
| Paid invoices missing `invoice_payment` entry | 0 | 0 |
| Expenses missing `expense` entry | 14 | 0 |
| Received/partial/paid POs missing `purchase_order` entry | 0 | 0 |
| Paid POs missing `po_payment` entry | 0 | 0 |

## Findings

### 1. Invoices missing "invoice" journal entry
None. All 1 non-draft invoice has a `source='invoice'` journal entry.

### 2. Paid invoices missing "invoice_payment" entry
None. No invoices in `paid` status.

### 3. Expenses missing "expense" entry
None. All 14 expenses have a `source='expense'` journal entry.

### 4. Received/partial/paid POs missing "purchase_order" entry
None. No purchase orders in `received`, `partial`, or `paid` status.

### 5. Paid POs missing "po_payment" entry
None. No purchase orders in `paid` status.

## Recommended fix

No action required. If future runs find gaps, calling `POST /journal/backfill` (authenticated) will repair them.

---
*Source strings verified against `journal.py`: `invoice` (post_invoice_raised), `invoice_payment` (post_invoice_paid), `expense` (post_expense), `purchase_order` (post_po_received), `po_payment` (post_po_paid). Check script: `journal_check.py` in session outputs.*
