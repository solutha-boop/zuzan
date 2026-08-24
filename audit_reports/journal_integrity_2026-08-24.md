# Journal Entry Integrity Audit — 2026-08-24

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

Dataset is still small (1 non-draft invoice, 0 paid invoices, 14 expenses, 0 purchase orders in received/partial/paid/paid status) — consistent with Zuzan being in customer testing.

## 2. Findings

### 2.1 Invoices missing `invoice` entry
None. Query: invoices with `status != 'draft'` and no `journal_entries` row with `source='invoice'` and matching `source_id`.

### 2.2 Paid invoices missing `invoice_payment` entry
None. No invoices currently have `status='paid'`.

### 2.3 Expenses missing `expense` entry
None. All 14 expense records have a corresponding `journal_entries` row with `source='expense'`.

### 2.4 Purchase orders (received/partial/paid) missing `purchase_order` entry
None. No purchase orders currently have status in (`received`, `partial`, `paid`).

### 2.5 Paid purchase orders missing `po_payment` entry
None. No purchase orders currently have `status='paid'`.

## 3. Methodology note

While reading `journal.py`, found that `backfill_company()` treats an invoice's raised-entry as missing in one additional case beyond simple existence: if the invoice's only `source='invoice'` journal entry was itself reversed (`is_reversal_of` points to it, e.g. from a draft-time amount edit per the 2026-07-08 fix) and never re-posted, a naive existence check would wrongly report "has an entry" even though the AR/VAT liability is gone. The script reran check 2.1 with this reversal-aware logic as a cross-check — result was also 0 gaps, so this doesn't change the outcome today, but it's worth keeping in the script for future runs as the invoice volume grows and edits become more common.

## 4. Recommended fix

Not applicable this run — no gaps found. If a future run reports gaps, `POST /journal/backfill` (authenticated) will repair them; it is idempotent and safe to re-run (skips records that already have a journal entry, and is reversal-aware for the invoice case above).

---
*Script: `journal_check.py` (SQLite-only, no app runtime dependency). Source DB: `C:\Zuzan\zuzan-backend\zuzan.db`.*
