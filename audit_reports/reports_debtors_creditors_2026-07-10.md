# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 2026-07-10 · **Scope:** payroll.py, main.py, journal.py, companies.py, suppliers.py, purchase_orders.py, database.py, App_js_fixed.js

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard, management, /v1/summary) | **PASS with issues** — core endpoints clean; 2 new Medium issues in secondary report endpoints (provisional-tax, cash-flow) |
| Debtors (AR) | **PASS** — no issues |
| Creditors (AP) | **PASS** — both 2026-07-09 fixes verified in place |
| Cross-module / Journal | **PASS** — full event coverage; 1 Low carried over |

The dashboard, management accounts, aging books and `/v1/summary` all pass every checklist item. Today's two new findings are in report endpoints adjacent to the checklist — `/reports/provisional-tax` and `/reports/cash-flow` — where PO COGS and expense handling diverge from the (correct) dashboard treatment.

## 2. Reports

### Core endpoints — checklist items all pass
- `total_revenue`: paid invoices only, via `_to_zar()` (payroll.py:510–514). `_to_zar` uses `paid_amount_zar` (actual cash) first, else `total_amount × exchange_rate` for non-ZAR; ZAR invoices as-is (payroll.py:17–24). Bank-import income added from journal source `bank_import_income` — structurally separate from invoice revenue, no double-count; dedupe on import fixed 2026-07-04 (companies.py:967).
- `total_outstanding`: `sent` + `overdue` via `_to_zar()` (payroll.py:518–522). The enum has no separate `pending` — `sent` is pending by definition (database.py:38). Paid and draft excluded.
- Expenses never enter revenue; P&L expenses are ex-VAT (payroll.py:524–528).
- Payroll: all payslips including terminated employees, active-employee estimate as fallback (payroll.py:546–562); shown as its own line between gross and net profit (payroll.py:564–565).
- PO costs: received/partial/paid POs at delivered ex-VAT value via `_po_delivered_net()` (payroll.py:27–46, 533–538). No Expense record is created on receipt (purchase_orders.py:340–344), and a structural duplicate detector warns on supplier/month/amount matches (payroll.py:589–623) — no double-count.
- VAT position: drafts excluded from output VAT; input VAT includes delivered-value PO input VAT (payroll.py:568–584).
- Management accounts: revenue, PO COGS, depreciation, payroll and the 6-month trend loop all apply `_to_zar()` and period filters consistently (payroll.py:1243–1251, 1266–1276, 1341–1345, 1350–1356).
- `/v1/summary` (main.py:264–309) mirrors the dashboard: `_to_zar()` on revenue (271) and outstanding (301), ex-VAT expenses, `_po_delivered_net` PO COGS (279–285), depreciation, all-payslip payroll.

### Issues (new)
1. **[Medium] `/reports/provisional-tax` uses full PO value instead of delivered value.** `po_cogs_ytd` sums `(po.total_amount − po.vat_amount)` for received/**partial**/paid POs (payroll.py:1434–1441) instead of `_po_delivered_net()`. For a partially delivered PO, YTD expenses are overstated by the undelivered portion → taxable income and both IRP6 installments are **understated**. The comment claims "consistent with dashboard", but the dashboard uses delivered value (payroll.py:537). Fix: replace the sum with `_po_delivered_net(po)`.
2. **[Medium] `/reports/cash-flow` counts unpaid on-credit expenses as cash payments.** `cash_payments` sums `e.amount` for every expense filtered only by `expense_date` (payroll.py:1110–1117) — no `is_on_credit`/`paid_at` filter. An on-credit expense that has not been paid is an accrual, not a cash outflow, so cash payments are overstated in the accrual month; and when it is later paid (`POST /expenses/{id}/pay`, companies.py:699), the outflow is never shown in the payment month. Fix: exclude expenses where `is_on_credit == True and paid_at == None` from the period sum, and count paid credit expenses by `paid_at` date instead of `expense_date`.

## 3. Debtors

✓ No issues found.

- `/reports/debtors-aging` (payroll.py:1509–1569) filters to `sent` + `overdue` (1518–1521); paid and draft invoices excluded from the outstanding balance.
- ZAR equivalents via `_to_zar()` per entry (1532) — no raw foreign amounts.
- Aging strictly from `due_date` (1525–1552); a missing due date lands in `not_due`, never falsely aged (the issue_date/created_at fallback was removed in a prior audit fix).
- Buckets not_due / 0–30 / 31–60 / 61–90 / 90+ with grand total = sum of buckets (1554–1568).
- Frontend `Debtors` (App_js_fixed.js:4731–4854) renders backend data verbatim, refreshes on invoice payment (4741–4745); mock data only behind an explicit "Demo Mode" badge (4777). Dashboard KPIs use backend `total_revenue`/`total_outstanding` when live (App_js_fixed.js:651–653, 9639–9641).

## 4. Creditors

✓ No issues found. Both 2026-07-09 fixes verified in place:

- **Fix 1 (single commit)**: `receive_po` now validates without mutating, calls `init_accounts` before any PO mutation, and commits only after `post_po_received` succeeds (purchase_orders.py:280–318, 324–367); `pay_po` likewise commits status + journal together (purchase_orders.py:419–469). The "No changes were saved — please retry" message is now truthful and retry works.
- **Fix 2 (zero-value guard)**: all-zero deliveries rejected with a 400 before any state change (purchase_orders.py:313–318).

Checklist items:
- `/reports/creditors-aging` (payroll.py:1572–1744): POs with status `received`/`partial` only (1588–1591) — received-but-unpaid POs appear as outstanding; fully paid POs excluded (`pay_po` flips status to `paid`). Unpaid on-credit expenses included (1680–1684); paid ones excluded via `paid_at == None`.
- Partial-PO amounts come from actual journal AP credits on account 2000 (1596–1613, 1660), not `po.total_amount`; fallback to `po.total_amount` only when no journal entry exists.
- Aging from due date = received_date + supplier `payment_terms` (default 30) (1629–1634); credit expenses aged from expense_date + 30 (1688–1690).
- Supplier bank details decrypted with `decrypt_field` before display (1648–1650).
- POs are ZAR-only by design — documented at database.py:235–237; no conversion needed.
- Frontend `Creditors` (App_js_fixed.js:4857–5009) renders backend data, filters client-side, refreshes on PO/expense changes (4868–4872).

## 5. Cross-module

Journal event coverage — all wired and intact:

| Event | Posting fn | Called from |
|---|---|---|
| Invoice raised | `post_invoice_raised` (journal.py:181) | companies.py:251, 367, 381, 455 |
| Invoice payment | `post_invoice_paid` (journal.py:221) | companies.py:383, portal.py:205 |
| Expense (cash/credit) | `post_expense` (journal.py:280) | companies.py:554, 644, 961 |
| Expense payment | `post_expense_paid` (journal.py:392) | companies.py:699 |
| PO receipt (incremental) | `post_po_received` (journal.py:421) | purchase_orders.py:355 |
| PO payment | `post_po_paid` (journal.py:473) | purchase_orders.py:461 |
| Payroll run | `post_payroll` (journal.py:355) | payroll.py:407 |
| Bank-import income | `post_bank_income` (journal.py:315) | companies.py:996 |

No coverage gaps. Backfill (journal.py:688–798) repairs all event types.

Control accounts reconcile: balance sheet reads Debtors Control from journal 1100 and Creditors Control from 2000 (payroll.py:750, 760), matching the frontend COA mapping (App_js_fixed.js:258, 271). Rule 6 compares journal AR against `_to_zar` outstanding invoices (payroll.py:938–958); Rule 7 compares journal AP against per-PO journal AP credits + unpaid credit expenses (payroll.py:960–1018). `post_invoice_raised` posts ZAR-converted amounts so 1100 stays ZAR-denominated (journal.py:203–214), consistent with `_to_zar`.

**Carried over (Low, from 2026-07-09):** the per-PO AP-credit lookups (payroll.py:976–987, 1600–1613; purchase_orders.py:437–448) sum credits under source `"purchase_order"` only and ignore `"purchase_order_reversal"` debits. Currently unreachable in practice, but worth making reversal-aware.

## 6. Action items

1. **[Medium]** `/reports/provisional-tax`: replace the full-value PO COGS sum (payroll.py:1434–1441) with `_po_delivered_net(po)` so partially delivered POs don't understate IRP6 estimates. — **✅ FIXED 2026-07-10**
2. **[Medium]** `/reports/cash-flow`: exclude unpaid on-credit expenses from `cash_payments` (payroll.py:1110–1117) and recognise paid credit expenses by `paid_at` date. — **✅ FIXED 2026-07-10**
3. **[Low]** Make the per-PO AP-credit lookups reversal-aware (payroll.py:976–987, 1600–1613; purchase_orders.py:437–448) — carried over from 2026-07-09. — open

## 8. Resolution log (2026-07-10)

**Fix 1 — provisional-tax delivered-value PO COGS (payroll.py `provisional_tax`).** `po_cogs_ytd` now sums `_po_delivered_net(po)` instead of the full `(total_amount − vat_amount)`, so partially delivered POs contribute only the value actually received — consistent with dashboard, management accounts and `/v1/summary`.

**Fix 2 — cash-basis expense payments (payroll.py `cash_flow`).** `cash_payments` is now built from two NULL-safe queries: cash expenses (`is_on_credit.isnot(True)` — legacy NULL rows treated as cash) by `expense_date`, plus on-credit expenses with `paid_at` inside the period, counted at their payment date. Unpaid credit expenses no longer appear as cash outflows, and the real outflow shows in the month the expense was actually paid. `expenses_in_period` feeds the input-VAT figure too, so the VAT-to-SARS line is now cash-basis on both sides, matching the paid-invoice output VAT.

## 7. Changes since last run (2026-07-09)

`purchase_orders.py` was modified 2026-07-09 to apply both action items from the last audit — the single-commit-after-journal pattern in `receive_po`/`pay_po` and the zero-value delivery guard. Both are verified correctly implemented, including the subtle ordering around `init_accounts`' internal commit. No other backend files changed. Today's two new Medium findings come from extending the sweep to the secondary report endpoints (`provisional-tax`, `cash-flow`), which had not previously had their PO-COGS/expense treatment compared line-by-line against the dashboard. The Low reversal-awareness item remains open.
