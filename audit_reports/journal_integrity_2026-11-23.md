# Journal Integrity Audit — 2026-11-23

## 1. Summary

**Overall result: PASS** — 0 gaps found across all 5 checks.

Database audited: local SQLite `zuzan-backend/zuzan.db` (the default `DATABASE_URL` in `database.py`, `sqlite:///./zuzan.db`). The db file was last modified 2026-10-26, so it is unchanged since the 2026-11-16 run. A copy of the db plus its WAL/SHM files was audited read-only; the live file was not touched.

Record counts: 3 companies, 1 invoice (status `overdue`), 14 expenses, 0 purchase orders, 16 journal entries — identical to the previous run.

Source values were re-confirmed against `journal.py` (which changed on 2026-11-23): `post_invoice_raised` → `invoice`, `post_invoice_paid` → `invoice_payment`, `post_expense` → `expense`, `post_po_received` → `purchase_order`, `post_po_paid` → `po_payment`. The backfill routine uses the same source keys.

Caveat: this covers only the local SQLite file. If production runs on a different `DATABASE_URL` (e.g. Postgres on Render), that database was not checked.

## 2. Findings

| # | Check | Gaps | Affected IDs (company_id) |
|---|-------|------|---------------------------|
| 1 | Non-draft invoices missing `invoice` entry | 0 | none |
| 2 | Paid invoices missing `invoice_payment` entry | 0 | none (no paid invoices exist) |
| 3 | Expenses missing `expense` entry | 0 | none |
| 4 | Received/partial/paid POs missing `purchase_order` entry | 0 | none (no POs exist) |
| 5 | Paid POs missing `po_payment` entry | 0 | none (no POs exist) |

## 3. Recommended fix

No journal repair needed. If gaps appear in a future run, calling `POST /journal/backfill` (authenticated) will repair them.

Script: `audit_reports/journal_check_2026-11-23.py` (usage: `python3 journal_check_2026-11-23.py <path-to-sqlite-db>`; opens the db read-only). The configured `/sessions/outputs/` path isn't reachable from this run, so the script was saved alongside the report.
