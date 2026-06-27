# Journal Integrity Audit — 2026-06-27

**Overall Status: ⚠️ FAIL**
**Total gaps found: 15**

---

## Summary

The audit identified **15 transactions with no corresponding double-entry journal entries**. The root cause is that the `journal_entries` table (and related `journal_lines`, `accounts` tables) does not exist in the live database (`zuzan.db`). This means the journal engine has never been initialised for this database instance — no financial events have been posted to the ledger.

As a result, the balance sheet and P&L are entirely derived from raw transaction tables rather than the journal, and any journal-based reporting (trial balance, reconciliation) will produce empty or incorrect results.

---

## Findings

### Check 1 — Non-draft invoices missing `invoice` journal entry

**Result: FAIL — 1 gap**

| Invoice ID | Company ID | Invoice Number | Status |
|-----------|------------|----------------|--------|
| 1 | 3 | INV-0001 | sent |

---

### Check 2 — Paid invoices missing `invoice_payment` journal entry

**Result: PASS — 0 gaps**

No paid invoices found without a payment entry. (No invoices are currently in `paid` status.)

---

### Check 3 — Expenses missing `expense` journal entry

**Result: FAIL — 14 gaps**

| Expense ID | Company ID | Vendor | Amount (ZAR) | Date |
|-----------|------------|--------|-------------|------|
| 1 | 2 | C*Bp Ballito Motors | 500.00 | 2026-03-10 |
| 2 | 2 | Bex Ballito | 933.00 | 2026-04-07 |
| 3 | 2 | Bp Drive In Motors Csbcnr Simb | 700.00 | 2026-04-08 |
| 4 | 2 | Checkers Sixty60 C/O Old | 347.94 | 2026-04-10 |
| 5 | 2 | Checkers Sixty60 C/O Old | 399.92 | 2026-04-10 |
| 6 | 2 | Dl Uber Office 1 | 101.79 | 2026-04-11 |
| 7 | 2 | Dl Uber Office 1 | 10.18 | 2026-04-14 |
| 8 | 2 | Checkers Sixty60 C/O Old | 255.90 | 2026-04-16 |
| 9 | 2 | Airbnb * Hme3ydbb9n 20-22 Be | 8,601.42 | 2026-04-17 |
| 10 | 2 | Flysafair Hbbenn:52442northern | 3,138.61 | 2026-04-17 |
| 11 | 2 | Flysafair M5pt7i:52437northern | 2,158.61 | 2026-04-17 |
| 12 | 2 | Flysafair Hbbenn-502b7northern | 150.00 | 2026-04-17 |
| 13 | 2 | Flysafair M5pt7i-B1537northern | 30.00 | 2026-04-17 |
| 14 | 3 | JPS | 8,500.00 | 2026-05-27 |

Total unposted expense value: **R 25,327.37**

---

### Check 4 — Received/partial/paid POs missing `purchase_order` journal entry

**Result: PASS — 0 gaps**

The `purchase_orders` table does not exist in this database. No purchase orders to audit.

---

### Check 5 — Paid POs missing `po_payment` journal entry

**Result: PASS — 0 gaps**

No purchase orders table present.

---

## Root Cause

The `journal_entries`, `journal_lines`, and `accounts` tables are **absent from the database**. These are created by `init_db()` (via `Base.metadata.create_all`) in `database.py`. The database appears to be a partial/older schema that predates the journal engine, or `init_db()` was not run against this instance.

This is not an individual posting failure — it is a schema initialisation gap affecting all companies.

---

## Recommended Fix

**Step 1 — Initialise the schema**

Run the application normally so `init_db()` executes, or connect directly and apply the `CREATE TABLE` statements for `accounts`, `journal_entries`, and `journal_lines` from `database.py`.

**Step 2 — Backfill all companies**

Once the schema exists, call the backfill endpoint for each company to post all historical transactions:

```
POST /journal/backfill
Authorization: Bearer <token>
```

This is safe to run multiple times — `backfill_company()` in `journal.py` skips records that already have a matching `(source, source_id)` entry.

**Step 3 — Re-run this audit**

After backfill completes, re-run this script to confirm zero gaps.

---

*Audit script: `journal_check.py` | Database: `C:\Zuzan\zuzan-backend\zuzan.db` | Run at: 2026-06-27*
