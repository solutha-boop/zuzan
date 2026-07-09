# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 2026-07-09 · **Scope:** payroll.py, main.py, journal.py, companies.py, suppliers.py, purchase_orders.py, database.py, App_js_fixed.js

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard, management, /v1/summary) | **PASS** — all conversions, inclusions and exclusions correct |
| Debtors (AR) | **PASS** — no issues |
| Creditors (AP) | **PASS with issues** — data sourcing correct, but 2 PO-endpoint edge cases can desync the book |
| Cross-module / Journal | **PASS** — full event coverage; all five 2026-07-08 fixes verified in place |

Today's findings are not in the report/aging queries themselves (those are clean) but in the PO receive/pay endpoints that feed them: a commit-ordering flaw that breaks atomicity on journal failure, and a missing zero-quantity guard. One latent fragility in the AP-credit lookups noted for the record.

## 2. Reports

✓ No issues found.

- `total_revenue`: paid invoices only with `_to_zar()` (payroll.py:510–514); `_to_zar` applies `paid_amount_zar` first, else `exchange_rate`, for non-ZAR invoices (payroll.py:17–24). Bank-import income added separately from journal source `bank_import_income` with no invoice overlap (payroll.py:59–97, 516).
- `total_outstanding`: `sent` + `overdue` with `_to_zar()` (payroll.py:518–522). The enum has no `pending`; `sent` is pending by definition (database.py:38). Paid and draft invoices excluded.
- Expenses never enter revenue; P&L expenses are ex-VAT (payroll.py:525–528).
- Payroll cost: sum of ALL payslips incl. terminated employees, with an active-employee estimate fallback (payroll.py:546–562); included in `net_profit`, not in `total_expenses` — presented as its own line (payroll.py:564–565, 634).
- PO costs: received/partial/paid POs at delivered ex-VAT value via `_po_delivered_net()` (payroll.py:27–46, 533–538). No Expense record is created on receipt (purchase_orders.py:315–319), and a structural duplicate-expense detector warns on supplier/month/amount matches (payroll.py:589–623) — no double-counting.
- VAT position: output VAT excludes drafts; input VAT = expense VAT + delivered-value PO input VAT (payroll.py:568–584).
- Management accounts: revenue, 6-month trend, PO COGS, depreciation and bank income all apply `_to_zar()` / period filters consistently (payroll.py:1243–1251, 1266–1276, 1341–1345).
- `/v1/summary` (main.py:264–309) mirrors the dashboard: `_to_zar()` on revenue and outstanding, ex-VAT expenses, delivered-value PO COGS, depreciation, all-payslip payroll.

## 3. Debtors

✓ No issues found.

- `/reports/debtors-aging` (payroll.py:1509–1569) filters invoices to `sent` + `overdue` (line 1520); paid and draft excluded.
- ZAR equivalents via `_to_zar()` per entry (line 1532).
- Aging strictly from `due_date` (lines 1525–1552); missing due date → `not_due`, never falsely aged.
- Buckets not_due / 0–30 / 31–60 / 61–90 / 90+; grand total = sum of buckets (lines 1556–1568).
- Frontend `Debtors` (App_js_fixed.js:4731–4854) renders backend data verbatim and refreshes on invoice payment (4736–4745); mock figures appear only behind an explicit "Demo Mode" badge (4777).

## 4. Creditors

Data sourcing is correct; two endpoint edge cases found upstream.

### Verified correct
- `/reports/creditors-aging` (payroll.py:1572–1746): POs with status `received`/`partial` only (line 1590); fully paid POs excluded (`pay_po` flips status, purchase_orders.py:396). Unpaid on-credit expenses included (lines 1680–1684); paid ones excluded via `paid_at == None`.
- Partial-PO amounts come from actual AP credits in the journal (account 2000, source `purchase_order`), not `po.total_amount` (lines 1596–1613, 1660).
- Aging from due date = received_date + supplier `payment_terms` (default 30, line 1629–1634); credit expenses aged from expense_date + 30.
- Supplier bank details decrypted with `decrypt_field` before display (payroll.py:1648–1650); decrypt_field handles legacy plaintext safely (crypto.py:42–52).
- Frontend `Creditors` (App_js_fixed.js:4857–5009) renders backend data, bucket-filters client-side, refreshes on PO/expense changes.

### Issues
1. **[Medium] PO receive/pay commit state before the journal entry — "rolled back" error message is false and retry is impossible.** `receive_po` commits `quantity_received` + status at purchase_orders.py:321 and only then posts the journal entry (line 332); `pay_po` commits `status="paid"` at line 397 before posting (line 431). If the journal post fails, the `db.rollback()` (lines 341, 435) cannot undo the already-committed status change, yet the 500 detail claims "Receipt/Payment has been rolled back — please retry" (lines 344, 438). Retrying then hits the status guards (line 269: "Cannot receive a PO with status 'received'"; line 391: "already been paid"). Result: a received/paid PO with no journal entry — dashboard COGS (direct query) diverges from the journal, and Rule 7 (AP control) fails. Mitigated by `/journal/backfill`, which re-posts missing PO receive and payment entries (journal.py:734–779), but the endpoint should use the single-commit-after-journal pattern already used by `update_invoice` (companies.py:341–393).
2. **[Medium] Zero-quantity receive flips a PO to "partial" with no journal entry, overstating the creditors book.** `receive_po` validates only non-negative and not-exceeding quantities (purchase_orders.py:282–293) — a delivery of all zeros passes, sets status "partial" (line 309), and skips the journal post (`received_total_with_vat > 0` guard, line 331). The PO then enters `open_pos` in creditors-aging with **no** journal AP credits, so the fallback shows the full `po.total_amount` (payroll.py:1660); Rule 7 uses the same fallback (payroll.py:990–993) and fails against the zero journal balance; `_po_delivered_net`'s legacy fallback (payroll.py:44–46, all `quantity_received` = 0) simultaneously puts the full subtotal into P&L COGS. Fix: reject receipts where `received_total <= 0` with a 400.

## 5. Cross-module

Journal event coverage — all wired and intact:

| Event | Posting fn | Called from |
|---|---|---|
| Invoice raised | `post_invoice_raised` (journal.py:181) | companies.py:251, 367, 381, 455 |
| Invoice payment | `post_invoice_paid` (journal.py:221) | companies.py:383, portal.py:205 |
| Expense (cash/credit) | `post_expense` (journal.py:280) | companies.py:554, 644, 961 |
| Expense payment | `post_expense_paid` (journal.py:392) | companies.py:699 |
| PO receipt (incremental) | `post_po_received` (journal.py:421) | purchase_orders.py:332 |
| PO payment | `post_po_paid` (journal.py:473) | purchase_orders.py:431 |
| Payroll run | `post_payroll` (journal.py:355) | payroll.py:407 |

No coverage gaps. Backfill (`journal.py:660–779`) repairs all seven event types, is reversal-aware for invoices, and posts delivered-value amounts for partial/paid POs.

Control accounts reconcile: Rule 6 checks journal AR (1100) against outstanding invoices at `_to_zar` (payroll.py:938–958); Rule 7 checks journal AP (2000) against per-PO journal AP credits + unpaid credit expenses (payroll.py:960–1018). Balance sheet reads Debtors Control from 1100 and Creditors Control from 2000 (payroll.py:750, 760), matching the frontend COA mapping (App_js_fixed.js:258, 271).

**All five 2026-07-08 action items verified still in place:** tracked expense-edit reversals via `reverse_entry_by_id` (companies.py:637), expense delete reverses `expense` + `expense_payment` (companies.py:718–724), draft transitions handled with `_has_active_raised_entry` (companies.py:266, 355–367, 453), fatal journal failure on expense edit, and per-invoice VAT201 zero-rated handling with field 1b populated (payroll.py:1799–1820, 1870).

### Latent fragility (for the record)
3. **[Low] AP-credit lookups ignore reversal entries.** The three per-PO AP-credit queries (payroll.py:1600–1613, 976–987; purchase_orders.py:416–429) sum `JournalLine.credit` where source == `"purchase_order"` only. Reversals are posted under source `"purchase_order_reversal"` (journal.py:858), so their AP debits are invisible to these sums. Currently unreachable — PO reversals only happen on delete, which removes the PO from every query — but if any future path reverses a receive entry while leaving the PO in `received`/`partial`, creditors-aging, Rule 7 and `pay_po` would all overstate AP. Consider netting reversal debits or excluding reversed entries (via `is_reversal_of`) in these lookups.

## 6. Action items

1. **[Medium]** Restructure `receive_po` and `pay_po` to a single commit after the journal post succeeds (mirror `update_invoice`, companies.py:341–393), so a journal failure genuinely rolls back the status change and the "please retry" guidance works. (Issue 1) — **✅ FIXED 2026-07-09**
2. **[Medium]** In `receive_po`, reject zero-value deliveries: after the quantity loop, `if received_total <= 0: raise HTTPException(400, ...)`. (Issue 2) — **✅ FIXED 2026-07-09**
3. **[Low]** Make the per-PO AP-credit lookups reversal-aware (net out `purchase_order_reversal` debits or skip reversed entries) in payroll.py:1600–1613, payroll.py:976–987 and purchase_orders.py:416–429. (Issue 3) — open

## 8. Resolution log (2026-07-09)

**Fix 1 — single-commit PO endpoints (purchase_orders.py `receive_po`, `pay_po`).** Both endpoints now mutate the PO and post the journal entry inside one transaction, committed only after the post succeeds; a journal failure rolls back the receipt/payment too, and the 500 message now truthfully says "No changes were saved — please retry" (retry works, since the status guards no longer see a half-applied state). Two ordering subtleties handled: `init_accounts` commits internally, so it is called *before* any PO mutation in both endpoints; and `receive_po`'s validation loop no longer mutates `item.quantity_received` directly — it collects new quantities in a dict and applies them only after `init_accounts`, so nothing is persisted early. (`_make_entry` only flushes, so the single commit holds.)

**Fix 2 — zero-value receive guard (purchase_orders.py `receive_po`).** Deliveries where `received_total <= 0` are rejected with a 400 before any state change, so an all-zero receive can no longer flip a PO to "partial" with no journal entry (which overstated the creditors book via the `po.total_amount` fallback, false-failed Rule 7, and pushed the full subtotal into P&L COGS via `_po_delivered_net`'s legacy fallback).

## 7. Changes since last run (2026-07-08)

No source files changed since the last audit (latest backend mtimes 2026-07-07 20:24). All five 2026-07-08 fixes remain in place with no regressions. The report/aging queries pass every checklist item. Today's three findings are new, found by auditing the PO endpoint transaction ordering rather than the queries: two Medium issues in `receive_po`/`pay_po` (commit-before-journal atomicity; missing zero-quantity guard) and one Low latent fragility in the AP-credit lookups.
