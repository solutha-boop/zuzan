# Journal Integrity Audit — 2026-10-05

Database: `C:\Zuzan\zuzan-backend\zuzan.db` (SQLite, opened read-only). Script: `audit_reports\journal_check_2026-10-05.py`.

## 1. Summary

**Overall: PASS — 0 gaps found across all 5 checks.**

Record counts: 1 invoice (status: overdue), 14 expenses, 0 purchase orders. Journal entries by source: expense 14, invoice 1, payroll 1.

## 2. Findings

| # | Check | Gaps | Affected records (id / company_id) |
|---|-------|------|------|
| 1 | Non-draft invoices missing `invoice` entry | 0 | none |
| 2 | Paid invoices missing `invoice_payment` entry | 0 | none |
| 3 | Expenses missing `expense` entry | 0 | none |
| 4 | Received/partial/paid POs missing `purchase_order` entry | 0 | none |
| 5 | Paid POs missing `po_payment` entry | 0 | none |

## 3. Recommended fix

None required. (If gaps appear in future runs, an authenticated `POST /journal/backfill` will repair them.)
