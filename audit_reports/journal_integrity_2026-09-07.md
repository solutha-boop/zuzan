# Journal Entry Integrity Audit — 2026-09-07

## 1. Summary

**Overall: PASS** — 0 gaps found across all 5 checks.

| Check | Records evaluated | Gaps found |
|---|---|---|
| Invoices missing `invoice` entry | 1 non-draft invoice | 0 |
| Paid invoices missing `invoice_payment` entry | 0 paid invoices | 0 |
| Expenses missing `expense` entry | 14 expenses | 0 |
| Received/partial/paid POs missing `purchase_order` entry | 0 qualifying POs | 0 |
| Paid POs missing `po_payment` entry | 0 paid POs | 0 |
| **Total gaps** | | **0** |

Dataset is unchanged since the last run (2026-08-24): 1 non-draft invoice (INV-0001, status `overdue`, company 3), 0 paid invoices, 14 expenses, 0 purchase orders in any of received/partial/paid status. Company 3 is Solutha, the known test-data tenant — not a live customer.

## 2. Findings

### 2.1 Invoices missing `invoice` entry
None. Query: invoices with `status != 'draft'` and no `journal_entries` row with `source='invoice'` and matching `source_id`. INV-0001 (id 1, company 3) has journal entry id 14 with `source='invoice'`.

### 2.2 Paid invoices missing `invoice_payment` entry
None. No invoices currently have `status='paid'`.

### 2.3 Expenses missing `expense` entry
None. All 14 expense records (company 3) have a corresponding `journal_entries` row with `source='expense'`.

### 2.4 Purchase orders (received/partial/paid) missing `purchase_order` entry
None. No purchase orders exist in the database at all (0 rows in `purchase_orders`).

### 2.5 Paid purchase orders missing `po_payment` entry
None. Same reason as 2.4 — no purchase orders exist.

## 3. Methodology notes

- **Reversal-aware cross-check**: `journal.backfill_company()` treats an invoice's raised-entry as missing if its only `source='invoice'` entry was later reversed (`is_reversal_of` set, e.g. from a draft-time amount edit) and never re-posted. Re-ran the invoice check with this logic — confirmed 0 `is_reversal_of` rows exist in the whole `journal_entries` table today, so this doesn't change the result, but the distinction matters as invoice edits become more common.
- **Source string values** were confirmed by reading `journal.py` directly rather than assumed: `post_invoice_raised` → `source="invoice"`, `post_invoice_paid` → `source="invoice_payment"`, `post_expense` → `source="expense"`, `post_po_received` → `source="purchase_order"`, `post_po_paid` → `source="po_payment"`. These match the task brief.
- **Scope caveat**: this audit ran against the local SQLite file at `C:\Zuzan\zuzan-backend\zuzan.db` (the `DATABASE_URL` default fallback — no environment override was present in this run). Given the very small record counts (1 invoice, 14 expenses, 0 POs, all under company 3/Solutha test data) and that zuzan.co.za is live in customer testing on what is presumably a separate hosted database, this file is most likely a local/dev copy rather than the production database. If a production Postgres instance exists, it should be audited separately using the same script with `DATABASE_URL` (or `ZUZAN_DB_PATH` for SQLite) pointed at it.

## 4. Recommended fix

Not applicable this run — no gaps found. If a future run reports gaps, `POST /journal/backfill` (authenticated) will repair them; per `journal.py`, it is idempotent (skips source/source_id pairs that already have an entry) and reversal-aware for the invoice case in section 3.

---
*Script: `journal_check.py` (SQLite-only, no app runtime dependency). Source DB: `C:\Zuzan\zuzan-backend\zuzan.db`.*
