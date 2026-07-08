# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 2026-07-08 · **Scope:** payroll.py, main.py, journal.py, companies.py, suppliers.py, purchase_orders.py, database.py, App_js_fixed.js

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard, management, /v1/summary, VAT201) | **PASS** — all 2026-07-07 fixes verified in place; 1 low-severity VAT201 edge case |
| Debtors (AR) | **PASS** — no issues |
| Creditors (AP) | **PASS** — no issues |
| Cross-module / Journal | **PASS with issues** — full event coverage, but expense edit/delete and invoice draft transitions can desync the ledger |

All six action items from the 2026-07-07 report are confirmed fixed in the current code. Today's new findings are in the *edges* of those flows: repeated expense amount edits, deletion of paid credit expenses, and invoice draft-status round-trips.

## 2. Reports

### Verified correct (including yesterday's fixes)
- `total_revenue`: paid invoices only, `_to_zar()` applied (payroll.py:510–516); bank-import income added separately with no invoice double-count (payroll.py:61–103).
- `total_outstanding`: sent + overdue with `_to_zar()` (payroll.py:518–522). Enum has no `pending`; `sent` is pending.
- Expenses excluded from revenue; ex-VAT in P&L (payroll.py:528).
- Payroll cost = all payslips incl. terminated employees, estimate fallback (payroll.py:551–563).
- PO COGS: delivered-value ex-VAT for received/partial/paid POs via `_po_delivered_net()` (payroll.py:533–538, 27–46); no Expense record created on receipt (purchase_orders.py:315–332), plus structural double-count detector (payroll.py:587–626). No double-counting.
- **Fix 2 verified:** dashboard `input_vat` = expense VAT + delivered-value PO input VAT (payroll.py:575–585); same in reconciliation Rule 3 (payroll.py:869–886) and VAT201 field 14 with `received_date` period filter (payroll.py:1822–1833).
- **Fix 3 verified:** VAT201 output tax excludes drafts (status filter sent/overdue/paid, payroll.py:1786–1793) and converts foreign currency at `exchange_rate` (raised-basis, payroll.py:1795–1804).
- Management accounts + 6-month trend apply `_to_zar()`, bank income, PO COGS, and depreciation consistently per month (payroll.py:1243–1251, 1330–1364).
- `/v1/summary` (main.py:264–309) mirrors the dashboard: `_to_zar()`, ex-VAT expenses, delivered-value PO COGS, depreciation, payroll.

### Issues
1. **[Low] VAT201 output VAT fallback misfires on fully zero-rated periods.** If every issued invoice in the period has `vat_amount = 0` (all zero-rated), `output_vat_exact` is 0 and the code falls back to estimating 15/115 of turnover (payroll.py:1805), overstating output VAT. Also `field_1b_zero_rated_supplies` is hardcoded to 0 (payroll.py:1858). Only affects VAT-registered users invoicing exclusively zero-rated supplies in a period.

## 3. Debtors

✓ No issues found.

- `/reports/debtors-aging` (payroll.py:1509–1571): filters to `sent` + `overdue` only (line 1519) — paid and draft excluded.
- ZAR equivalents via `_to_zar()` (line 1531).
- Aging strictly from `due_date` (lines 1526–1552); no due date → `not_due`, never falsely aged from issue date.
- Buckets not_due / 0–30 / 31–60 / 61–90 / 90+; grand total = sum of buckets (lines 1556–1570).
- Frontend `Debtors` (App_js_fixed.js:4731+) renders the backend response verbatim, refreshes on invoice payment (lines 4737–4744); mock data only behind an explicit "Demo Mode" badge (line 4777).

## 4. Creditors

✓ No issues found.

- `/reports/creditors-aging` (payroll.py:1572–1746): POs with status `received`/`partial` only (line 1590) — paid POs excluded (`pay_po` flips status to paid, purchase_orders.py:396). Unpaid on-credit expenses included as AP (lines 1685–1731); paid ones excluded (`paid_at == None` filter).
- Partial-PO amounts come from actual AP credits in the journal (account 2000, source `purchase_order`), not `po.total_amount` (lines 1596–1614, 1660–1665).
- Aging from due date = received_date + supplier `payment_terms` (default 30); credit expenses aged from expense_date + 30.
- Supplier bank details decrypted with `decrypt_field` before display (payroll.py:1650–1652); suppliers.py encrypts on write, decrypts on read.
- Frontend `Creditors` (App_js_fixed.js:4857+) renders backend data, refreshes on PO/expense changes.

## 5. Cross-module

Journal event coverage — all wired and intact:

| Event | Posting fn | Called from |
|---|---|---|
| Invoice raised | `post_invoice_raised` (journal.py:181) | companies.py:251, 343 |
| Invoice payment | `post_invoice_paid` (journal.py:221) | companies.py:345, portal.py:205 |
| Expense (cash/credit) | `post_expense` (journal.py:280) | companies.py:502, 586, 891 |
| Expense payment | `post_expense_paid` (journal.py:392) | companies.py:633 |
| PO receipt (incremental) | `post_po_received` (journal.py:421) | purchase_orders.py:332 |
| PO payment | `post_po_paid` (journal.py:473) | purchase_orders.py:431 |
| Payroll run | `post_payroll` (journal.py:355) | payroll.py:407 |

**Fix 1 verified:** `update_invoice` reverses and re-posts the raised entry on amount change, blocks amount edits on invoices that remain paid (400), and reverses the payment entry on paid→unpaid (companies.py:271–357). **Fix 4 verified:** effective VAT rate preserved on edit (companies.py:289–298). **Fix 5 verified:** paid→unpaid reversal clears `paid_date`/`paid_amount_zar` (companies.py:320–330). **Fix 6 verified:** frontend COA shows Trade Receivables at 1100; Trade Payables at 2110 with an explicit note mapping it to journal 2000 (App_js_fixed.js:258, 271).

Control accounts: Rule 6 (AR 1100) and Rule 7 (AP 2000) reconcile journal balances against raw invoice/PO+credit-expense totals with journal-based per-PO AP credits and fail loudly on drift ≥ R1 (payroll.py:944–1023).

### New issues found today

2. **[High] Repeated expense amount edits double-reverse the original journal entry.** `update_expense`'s manual reversal loop (companies.py:558–581) reverses **every** entry with source `expense` for that expense, with no `is_reversal_of` tracking and no already-reversed skip (unlike `reverse_journal_entries`, journal.py:850–882). The re-posted correction entry also has source `expense`, so a **second** amount edit reverses both the original (again) and the first correction — net ledger effect after two edits is `new entry − original entry` instead of `new entry`. Expense/VAT-input/Bank (or AP) accounts drift by the original amount; for on-credit expenses Rule 7 will fail. One edit is safe; two or more corrupt the ledger.
3. **[Medium] Deleting a paid on-credit expense leaves its payment entry in the ledger.** `delete_expense` reverses only source `expense` (companies.py:654), not `expense_payment`. For a credit expense that was paid then deleted, the DR AP / CR Bank payment entry survives: Bank is understated and AP carries a debit residue → Rule 7 fails. Invoice deletion handles this correctly by reversing all three sources (companies.py:369–373); expense deletion should mirror it.
4. **[Medium] Invoice draft-status transitions never sync the journal, and backfill can't repair one path.** The Amend modal exposes "Draft" (App_js_fixed.js:1363). Two reachable desyncs in `update_invoice`:
   - *sent → draft (status-only edit):* nothing is reversed, so the raised entry (AR/revenue/VAT) stays in the ledger while dashboard, VAT201, and Rule 6 all exclude drafts → Rule 6 fails high.
   - *amount edit while draft, then draft → sent (status-only edit):* the amount edit reverses the raised entry and correctly skips re-posting (companies.py:339–343), but the later status-only transition posts nothing, and `backfill_company` skips the invoice because a (`"invoice"`, id) entry still exists (journal.py:655–662) → AR/revenue permanently understated; Rule 6 fails low with no self-service repair.
5. **[Low] Journal failure during expense amount edit is swallowed.** The `except` at companies.py:588–590 logs and continues ("Non-fatal — still save the field update"), so the expense row updates even when the correcting journal entries failed — silent drift. Every other flow (invoice update/delete, expense create/delete, PO receive/pay) rolls back and raises 500.

## 6. Action items

1. **[High]** Replace the manual reversal loop in `update_expense` with `journal_engine.reverse_journal_entries(cid, "expense", expense.id, db)` (which sets `is_reversal_of` and skips already-reversed entries), or add equivalent tracking — so repeated amount edits net correctly. *(Item 2)* — **✅ FIXED 2026-07-08**
2. **[Medium]** In `delete_expense`, also reverse source `expense_payment` (mirror the invoice delete loop over sources). *(Item 3)* — **✅ FIXED 2026-07-08**
3. **[Medium]** Handle draft transitions in `update_invoice`: on issued→draft reverse the raised entry; on draft→issued (re-)post it if no unreversed raised entry exists. Alternatively remove "Draft" from the Amend modal and block the transition server-side. Consider making `backfill_company` treat a fully-reversed (`"invoice"`, id) pair as missing. *(Item 4)* — **✅ FIXED 2026-07-08**
4. **[Low]** Make the expense-edit journal failure fatal (rollback + 500), consistent with all other flows. *(Item 5)* — **✅ FIXED 2026-07-08**
5. **[Low]** VAT201: skip the 15/115 fallback when invoices explicitly carry `vat_amount = 0` (zero-rated), and populate field 1b from zero-rated invoice totals. *(Item 1)* — **✅ FIXED 2026-07-08**

## 8. Resolution log (2026-07-08)

**Fix 1 — expense edit reversal (companies.py `update_expense`).** The manual reversal loop was replaced with tracked reversals via `reverse_entry_by_id` (sets `is_reversal_of`), reversing only currently-unreversed `expense` entries before re-posting the new amounts. A legacy guard pairs pre-fix untracked `expense_reversal` entries to unreversed entries by total amount (oldest first) so expenses edited once under the old code are not double-reversed by the new code. Additionally, amount edits on **paid** on-credit expenses are now blocked with a 400 (the AP-clearing payment entry carries the old amount) — same rule as paid invoices.

**Fix 2 — expense delete (companies.py `delete_expense`).** Now reverses both `expense` and `expense_payment` sources, mirroring the invoice delete flow, so deleting a paid credit expense no longer leaves the DR AP / CR Bank payment entry behind.

**Fix 3 — invoice draft transitions.** `update_invoice` now reverses the raised entry on issued→draft and re-posts it on draft→issued when no unreversed raised entry is in force (helper `_has_active_raised_entry`). The `/invoices/{id}/send` endpoint applies the same re-post guard, since it also transitions draft→sent. `backfill_company` (journal.py) is now reversal-aware: a fully-reversed raised entry counts as missing and is re-posted for issued invoices; drafts are skipped, and legacy drafts still carrying an active raised entry get it reversed (reported as `draft_reversals`) — so Rule 6 is self-service repairable via `/journal/backfill`, as its error message promises.

**Fix 4 — fatal journal failure on expense edit.** The swallowed exception now rolls back and raises 500, consistent with every other posting flow.

**Fix 5 — VAT201 zero-rated handling.** Output VAT is computed per invoice: `vat_amount == 0` means explicitly zero-rated (accumulated into field 1b, no VAT estimated); the 15/115 estimate applies only to rows where `vat_amount` is NULL. `total_invoiced_incl_vat` now includes zero-rated supplies.

## 7. Changes since last run (2026-07-07)

All six 2026-07-07 action items verified fixed in current code (payroll.py, companies.py, App_js_fixed.js modified 2026-07-07 17:52–20:24). No regressions found in the fixed areas. Today's five findings are new (or newly reachable): three concern expense edit/delete journal handling in companies.py, one the invoice draft-status path introduced alongside Fix 1's draft handling, and one a VAT201 zero-rated edge case.
