# Journal Integrity Audit — 2026-10-26

## 1. Summary

**Overall result: PASS** — 0 gaps found across all 5 checks.

Database audited: local SQLite `zuzan-backend/zuzan.db` (WAL snapshot last modified 2026-09-28; unchanged since the previous run). Record counts: 1 invoice, 14 expenses, 0 purchase orders, 16 journal entries.

Caveat: this covers only the local SQLite file. If production runs on a different `DATABASE_URL` (e.g. Postgres), it was not checked.

Source values confirmed against `journal.py`: `invoice`, `invoice_payment`, `expense`, `purchase_order`, `po_payment`.

## 2. Findings

| # | Check | Gaps | Affected IDs (company_id) |
|---|-------|------|---------------------------|
| 1 | Non-draft invoices missing `invoice` entry | 0 | none |
| 2 | Paid invoices missing `invoice_payment` entry | 0 | none |
| 2b | Part-paid invoices with Bank payment shortfall | 0 | none |
| 3 | Expenses missing `expense` entry | 0 | none |
| 4 | Received/partial/paid POs missing `purchase_order` entry | 0 | none |
| 5 | Paid POs missing `po_payment` entry | 0 | none |

### Side observation: schema drift (not a journal gap)
The `invoices` table in the local `zuzan.db` lacks columns defined in `database.py`: `items_json`, `passenger_name`, `pax_count`, `quote_ref`, `tax_ref`, `tour_ref`, `travel_date`. The audit script uses explicit column lists so it is unaffected, but ORM queries against this local DB file would fail until the schema is migrated.

## 3. Recommended fix

No journal repair needed. If gaps appear in future runs, calling `POST /journal/backfill` (authenticated) will repair them.

Script: `zuzan-backend/journal_check.py` (run with `DATABASE_URL=sqlite:///./zuzan.db python3 journal_check.py` from the backend folder; requires `sqlalchemy`).
