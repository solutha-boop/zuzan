# Journal Entry Integrity Audit — 2026-07-27

## Summary

**Overall result: PASS**

Total gaps found across all checks: **0**

No invoices, expenses, or purchase orders were found without a corresponding journal entry. The current dataset is small (1 non-draft invoice, 14 expenses, 0 delivered/paid POs), so this is a clean but low-volume result — re-run this audit as transaction volume grows.

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

- This audit uses a direct-existence check (does *any* matching `JournalEntry` row exist), matching the check definitions in the task spec. It does not account for the reversal-aware logic used internally by `backfill_company()` in `journal.py` (e.g. a draft invoice that still carries a reversed "invoice" entry would count as "has an entry" here, not as a gap). Given zero gaps were found either way in this run, this distinction didn't affect the result today, but is worth keeping in mind if invoice-status edits become more frequent.
- Database checked: `C:\Zuzan\zuzan-backend\zuzan.db` (SQLite, default `DATABASE_URL`).
