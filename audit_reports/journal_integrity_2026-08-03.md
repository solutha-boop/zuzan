# Journal Entry Integrity Audit — 2026-08-03

## Summary

**Overall result: PASS**

Total gaps found across all checks: **0**

No invoices, expenses, or purchase orders were found without a corresponding journal entry. The dataset checked is small and unchanged since the last few runs (1 non-draft invoice, 0 paid invoices, 14 expenses, 0 delivered/paid POs), and the underlying `zuzan.db` file's mtime (2026-06-29) has not advanced since the 2026-06-29 audit — see **Notes** below on database scope.

## Findings

### 1. Invoices missing "invoice" journal entry
Check: non-draft invoices (`status != 'draft'`) with no `JournalEntry(source='invoice', source_id=invoice.id)`.
Non-draft invoices checked: 1. **Gaps found: 0.**

### 2. Paid invoices missing "invoice_payment" entry
Check: paid invoices (`status='paid'`) with no `JournalEntry(source='invoice_payment', source_id=invoice.id)`.
Paid invoices checked: 0. **Gaps found: 0.**

### 3. Expenses missing "expense" entry
Check: all expenses with no `JournalEntry(source='expense', source_id=expense.id)`.
Expenses checked: 14. **Gaps found: 0.**

### 4. Received/partial/paid POs missing "purchase_order" entry
Check: purchase orders with `status IN ('received','partial','paid')` and no `JournalEntry(source='purchase_order', source_id=po.id)`.
POs checked: 0. **Gaps found: 0.**

### 5. Paid POs missing "po_payment" entry
Check: purchase orders with `status='paid'` and no `JournalEntry(source='po_payment', source_id=po.id)`.
POs checked: 0. **Gaps found: 0.**

## Recommended fix

None required — no gaps found. If a future run of this audit does surface gaps, calling the authenticated endpoint `POST /journal/backfill` for the affected company will repair them (it posts any missing invoice, invoice_payment, expense, expense_payment, purchase_order, po_payment, fixed_asset, and depreciation entries, and is safe to re-run).

## Notes

- **Database scope caveat**: this audit ran against `C:\Zuzan\zuzan-backend\zuzan.db` (SQLite, default `DATABASE_URL` from `database.py` — no `.env` override found in the backend directory). This file's last-modified timestamp is 2026-06-29 and has not changed across the 2026-06-29, 07-06, 07-13, 07-20, 07-27, and today's runs, and it holds only 16 journal entries total. By contrast, `audit_reports/reports_debtors_creditors_2026-08-03.md` (generated today, ~14KB) implies materially more invoice/receivable activity than this local file contains. This strongly suggests the live/customer-testing environment (per project memory, deployed on Netlify/Render) is running against a different `DATABASE_URL` (likely PostgreSQL) than this local SQLite file — so a PASS here confirms integrity of this static local dataset, not necessarily of the production ledger. Recommend re-pointing this check at the production `DATABASE_URL` (or running `journal_check.py` from within the deployed environment) to get a result that matches what customers are actually seeing.
- This audit uses a direct-existence check (does *any* matching `JournalEntry` row exist), matching the check definitions in the task spec. It does not account for the reversal-aware logic used internally by `backfill_company()` in `journal.py` (e.g. a draft invoice that still carries a reversed "invoice" entry would count as "has an entry" here, not as a gap). Given zero gaps were found either way in this run, this distinction didn't affect the result today.
- Script used: `journal_check.py` (SQLite existence-check queries for all 5 checks).
