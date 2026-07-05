# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 2026-07-05 (scheduled run)
**Scope:** payroll.py (reports endpoints), main.py (/v1/summary), journal.py, purchase_orders.py, companies.py, portal.py, database.py, App_js_fixed.js (Debtors/Creditors views)

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1-summary) | **PASS** — revenue, outstanding, expenses, payroll, PO COGS all correct |
| Debtors (AR) | **PASS** — correct filters, ZAR conversion, due-date aging |
| Creditors (AP) | **PASS** — journal-backed amounts, paid POs excluded, bank details decrypted |
| Cross-module / journal | **PASS** — all five event types post journal entries; control accounts reconcile by design |

Overall: **PASS**, with 2 low-severity observations (below). No data-accuracy defects found.

---

## 2. Reports

### /reports/dashboard (payroll.py:501)
✓ No issues found.

- `total_revenue` sums ONLY `status == paid` invoices via `_to_zar()` (payroll.py:510–514), plus bank-import income kept structurally separate to avoid double-count (payroll.py:516, 59–66).
- `total_outstanding` covers sent (aka "pending", per database.py:38) + overdue via `_to_zar()` (payroll.py:518–522). Draft and paid excluded.
- Expenses excluded from revenue; expenses ex-VAT for P&L (payroll.py:528).
- Payroll included via all-company payslip sum (incl. terminated employees) with active-employee estimate fallback (payroll.py:554–564); kept separate from `total_expenses`, so no overlap.
- PO COGS: received/partial/paid POs at delivered ex-VAT value via `_po_delivered_net()` (payroll.py:533–540), matching incremental journal postings. A structural duplicate-expense-vs-PO warning guards against double-counting (payroll.py:580–621).
- `_to_zar()` (payroll.py:17–24): non-ZAR uses `paid_amount_zar` when set, else `total_amount × exchange_rate`; ZAR passthrough. Per spec.

### /reports/management (payroll.py:1203)
✓ No issues found.

- Revenue = paid invoices in range via `_to_zar()` + bank-import income (payroll.py:1232–1240).
- 6-month trend loop applies `_to_zar()` consistently (payroll.py:1330–1334) and includes PO COGS + depreciation per month.
- `total_outstanding` KPI: sent + overdue via `_to_zar()` (payroll.py:1309–1313).

### /v1/summary (main.py:264)
✓ No issues found. Mirrors dashboard: `_to_zar()` for revenue (main.py:271) and outstanding (main.py:301), ex-VAT expenses + delivered PO COGS + depreciation + payslip-based payroll (main.py:274–300).

---

## 3. Debtors (Accounts Receivable)

Backend: `/reports/debtors-aging` (payroll.py:1498). Frontend: `Debtors` component (App_js_fixed.js:4731) — pure presenter over the API, refreshes on `live.invoices`.

✓ No issues found.

- Pulls invoices with `status IN (sent, overdue)` (payroll.py:1507–1510). "sent" is the schema's "pending" (database.py:38). Paid and draft excluded everywhere.
- Amounts are ZAR equivalents via `_to_zar()` (payroll.py:1521); frontend formats with `R` locale formatter (App_js_fixed.js:28).
- Aging strictly from `due_date` (payroll.py:1517, 1530); invoices with no due_date go to `not_due` rather than inflating overdue (audit fix retained, payroll.py:1515–1516). Buckets: not_due / 0–30 / 31–60 / 61–90 / 90+.
- Frontend mock data appears only when the API call fails and is clearly badged "Demo Mode" (App_js_fixed.js:4777).

Observation (Low): reconciliation RULE 2's per-item list shows raw `i.total_amount` for >90-day invoices (payroll.py:862) while the bucket total uses `_to_zar()` (payroll.py:852) — a foreign-currency invoice would display its raw amount in that detail list only. Totals unaffected.

---

## 4. Creditors (Accounts Payable)

Backend: `/reports/creditors-aging` (payroll.py:1561). Frontend: `Creditors` component (App_js_fixed.js:4857) — presenter over the API, refreshes on `live.purchaseOrders` / `live.expenses`.

✓ No issues found.

- Pulls POs with `status IN (received, partial)` (payroll.py:1577–1580) — received-but-unpaid POs appear as outstanding; fully paid POs excluded. Unpaid on-credit expenses (`is_on_credit AND paid_at IS NULL`) also included (payroll.py:1669–1673), matching the AP control definition.
- Per-PO amount = actual AP credits posted to account 2000 by each delivery (payroll.py:1585–1602, 1649), so partial POs show delivered value, not full order value; falls back to `po.total_amount` only when no journal entry exists.
- Aged from due date = received_date + supplier payment_terms (default 30) (payroll.py:1618–1624); credit expenses aged from expense_date + 30 (payroll.py:1677–1679).
- Supplier bank details decrypted with `decrypt_field` from crypto.py before display (payroll.py:1572, 1637–1639).

Observation (Low): POs have no currency/exchange-rate handling anywhere in the AP chain — acceptable if POs are ZAR-only by design, but worth confirming as multi-currency invoicing already exists on the sales side.

---

## 5. Cross-module consistency

✓ No journal coverage gaps.

| Event | Posting function (journal.py) | Called from |
|---|---|---|
| Invoice raised | post_invoice_raised:181 | companies.py:242 |
| Invoice payment | post_invoice_paid:221 | companies.py:289, portal.py:195 |
| Expense recorded | post_expense:280 | companies.py:446, 530, 835 |
| Expense payment (credit) | post_expense_paid:392 | companies.py:577 |
| PO receipt | post_po_received:421 | purchase_orders.py:330 |
| PO payment | post_po_paid:473 | purchase_orders.py:429 (pays journal AP balance, not face value) |
| Payroll run | post_payroll:355 | payroll.py:407 |
| Bank-import income | post_bank_income:315 | bank import flow |

A `/journal/backfill` repair path exists for all of the above (journal.py:663–773).

**Control accounts:** balance sheet reads Debtors Control (1100) and Creditors Control (2000) directly from journal balances (payroll.py:748, 758), and the reconciliation endpoint independently cross-checks them: RULE 6 compares 1100 vs outstanding invoice `_to_zar` totals (payroll.py:927–947); RULE 7 compares 2000 vs per-PO journal AP credits + unpaid credit expenses (payroll.py:949–1007), correctly using delivered-value credits for partial POs. Both flag failures with a pointer to `/journal/backfill`.

---

## 6. Action items

1. **Low** — ✅ RESOLVED 2026-07-05: payroll.py Debtors Ageing (>90 days) items list now uses `round(_to_zar(i), 2)` instead of raw `i.total_amount`.
2. **Low** — ✅ RESOLVED 2026-07-05: PO currency policy documented as ZAR-only by design — policy comments added to the `PurchaseOrder` model (database.py:230) and `POCreate` schema (purchase_orders.py:21) warning that any future currency field requires exchange-rate handling across the full AP chain.

No Critical, High, or Medium items.

---

*Compared to the 2026-07-02/03 audit fixes referenced in code comments: all previously fixed items (delivered-value PO COGS, draft-invoice VAT exclusion, due-date-only debtor aging, partial-PO AP credits) remain correctly in place.*
