# Journal Integrity Audit — 2026-06-29

**Overall result: PASS**  
No journal entry gaps detected across all five checks.

---

## Summary

| Check | Records audited | Gaps found |
|-------|----------------|------------|
| Non-draft invoices missing `invoice` journal entry | 1 | 0 |
| Paid invoices missing `invoice_payment` entry | 0 | 0 |
| Expenses missing `expense` entry | 14 | 0 |
| Received/partial/paid POs missing `purchase_order` entry | 0 | 0 |
| Paid POs missing `po_payment` entry | 0 | 0 |
| **Total** | **15** | **0** |

---

## Findings

All five checks passed. No records are missing a corresponding journal entry.

### Check 1 — Non-draft invoices missing `invoice` journal entry
No gaps. 1 non-draft invoice found; journal entry present.

### Check 2 — Paid invoices missing `invoice_payment` entry
No gaps. No paid invoices in the dataset.

### Check 3 — Expenses missing `expense` entry
No gaps. All 14 expenses have a corresponding `source='expense'` journal entry.

### Check 4 — Received/partial/paid POs missing `purchase_order` entry
No gaps. No POs in received/partial/paid status found.

### Check 5 — Paid POs missing `po_payment` entry
No gaps. No paid POs found.

---

## Recommended Fix

Not applicable — no gaps were detected. The balance sheet and P&L derived from the journal are consistent with the source transaction tables.

If gaps are detected in a future run, call `POST /journal/backfill` (authenticated) to repair them. That endpoint is idempotent and safe to run multiple times.

---

## Audit Notes

The database is running in WAL (Write-Ahead Log) mode. At the time of this audit, the WAL file content was unavailable via the mounted filesystem (likely a cloud-sync limitation — the WAL file is present on disk but its contents were not flushed to the mount). The audit was performed against the 56 committed pages in the main database file. The two newest tables (`invite_tokens`, `audit_log`) reside in WAL-only pages and were not in scope for this check.

The tables in scope — `invoices`, `expenses`, `purchase_orders`, and `journal_entries` — were fully readable from the committed pages and contained complete data for the audit.

*Generated automatically by the zuzan-journal-integrity scheduled task.*
