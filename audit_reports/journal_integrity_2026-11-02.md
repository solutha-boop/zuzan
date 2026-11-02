# Journal Integrity Audit — 2026-11-02

## 1. Summary

**Overall result: PASS** — 0 gaps found across all 5 checks.

Database audited: local SQLite `zuzan-backend/zuzan.db` (last modified 2026-10-26; WAL unchanged since 2026-09-28). A copy of the db and WAL was audited read-only. Record counts: 1 invoice, 14 expenses, 0 purchase orders, 16 journal entries (identical to the 2026-10-26 run).

Caveat: this covers only the local SQLite file. If production runs on a different `DATABASE_URL` (e.g. Postgres), it was not checked.

## 2. Findings

| # | Check | Gaps | Affected IDs (company_id) |
|---|-------|------|---------------------------|
| 1 | Non-draft invoices missing `invoice` entry | 0 | none |
| 2 | Paid invoices missing `invoice_payment` entry | 0 | none |
| 3 | Expenses missing `expense` entry | 0 | none |
| 4 | Received/partial/paid POs missing `purchase_order` entry | 0 | none |
| 5 | Paid POs missing `po_payment` entry | 0 | none |

## 3. Recommended fix

No journal repair needed. If gaps appear in future runs, calling `POST /journal/backfill` (authenticated) will repair them.

Script: `audit_reports/journal_check.py` (usage: `python3 journal_check.py <path-to-sqlite-db>`). `/sessions/outputs` was not writable on the device, so the existing script in this folder was reused unchanged.
