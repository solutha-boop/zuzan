# Journal Entry Integrity Audit — 2026-07-20

Automated scheduled audit of ZuZan journal posting completeness.
Database checked: `zuzan-backend/zuzan.db` (SQLite, default `DATABASE_URL`).

## Summary

**Overall: PASS — 0 gaps found across all 5 checks.**

| Check | Population | Gaps |
|---|---|---|
| 1. Non-draft invoices missing `invoice` entry | 1 | 0 |
| 2. Paid invoices missing `invoice_payment` entry | 0 | 0 |
| 3. Expenses missing `expense` entry | 14 | 0 |
| 4. Received/partial/paid POs missing `purchase_order` entry | 0 | 0 |
| 5. Paid POs missing `po_payment` entry | 0 | 0 |

Journal entries in DB: 16.

## Findings

### 1. Invoices missing "invoice" journal entry
No gaps. All 1 non-draft invoices have a matching `JournalEntry(source='invoice')`.

### 2. Paid invoices missing "invoice_payment" entry
No gaps (0 paid invoices in DB).

### 3. Expenses missing "expense" entry
No gaps. All 14 expenses have a matching `JournalEntry(source='expense')`.

### 4. Received/partial/paid POs missing "purchase_order" entry
No gaps (0 POs in received/partial/paid status).

### 5. Paid POs missing "po_payment" entry
No gaps (0 paid POs).

## Recommended fix

None required — no posting gaps detected. If future runs find gaps, calling `POST /journal/backfill` (authenticated) will repair them.

## Notes / caveats

- Source values were verified against `journal.py` (`post_invoice_raised` → `invoice`, `post_invoice_paid` → `invoice_payment`, `post_expense` → `expense`, `post_po_received` → `purchase_order`, `post_po_paid` → `po_payment`). Matching was scoped by `source_id` **and** `company_id`.
- The local SQLite file's last modification date is 2026-06-29. If production runs against a different `DATABASE_URL` (e.g. Postgres on the host), this audit reflects the local dev/test data only — rerun the script against the production database for full assurance.
- Check script saved as `journal_check.py` in the session outputs; it prints JSON results and takes the DB path as its first argument.
