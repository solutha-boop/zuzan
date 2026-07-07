# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 2026-07-06 (scheduled run)
**Scope:** payroll.py (reports endpoints), main.py (/v1/summary), journal.py, purchase_orders.py, companies.py, portal.py, suppliers.py, database.py, App_js_fixed.js (Debtors/Creditors views)

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1-summary) | **PASS** — revenue, outstanding, expenses, payroll, PO COGS all correct |
| Debtors (AR) | **PASS** — correct filters, ZAR conversion, due-date aging |
| Creditors (AP) | **PASS** — journal-backed amounts, paid POs excluded, bank details decrypted |
| Cross-module / journal | **PASS** — all five event types post journal entries; control accounts reconcile |

Overall: **PASS**. No data-accuracy defects found. Both low-severity items from the 2026-07-05 run remain resolved. Since yesterday, commits touched companies.py, portal.py, and App_js_fixed.js (PayFast per-client credentials, AFS add-on, payroll lock screen, nav/UI changes) — none altered the Reports/AR/AP data paths; journal postings in the changed files are intact.

---

## 2. Reports

### /reports/dashboard (payroll.py:501)
✓ No issues found.

- `total_revenue` sums ONLY `status == paid` invoices via `_to_zar()` (payroll.py:510–514), plus bank-import income kept structurally separate to avoid double-counting (payroll.py:516, 59–66).
- `total_outstanding` covers sent + overdue via `_to_zar()` (payroll.py:518–522). "sent" is the schema's "pending" (database.py:38). Draft and paid excluded.
- Expenses excluded from revenue; expenses are ex-VAT for P&L (payroll.py:528).
- Payroll cost from all-company payslip sum (incl. terminated employees) with active-employee estimate fallback (payroll.py:554–564); tracked separately from `total_expenses`, so no overlap.
- PO COGS: received/partial/paid POs at delivered ex-VAT value via `_po_delivered_net()` (payroll.py:533–540), matching the incremental journal postings. Structural duplicate expense-vs-PO warning guards double-counting (payroll.py:580–621).
- `_to_zar()` (payroll.py:17–24): non-ZAR uses `paid_amount_zar` when set, else `total_amount × exchange_rate`; ZAR passes through. Per spec.

### /reports/management (payroll.py:~1200)
✓ No issues found.

- Revenue = paid invoices in range via `_to_zar()` + bank-import income (payroll.py:1234–1242).
- 6-month revenue trend loop applies `_to_zar()` consistently (payroll.py:1332–1336) and includes per-month bank-import income, PO COGS, and depreciation.
- `total_outstanding` KPI: sent + overdue via `_to_zar()` (payroll.py:1311–1315).

### /v1/summary (main.py:264)
✓ No issues found. Mirrors dashboard: `_to_zar()` for revenue (main.py:271) and outstanding (main.py:301); ex-VAT expenses + delivered PO COGS + depreciation + payslip-based payroll (main.py:274–300).

---

## 3. Debtors (Accounts Receivable)

Backend: `/reports/debtors-aging` (payroll.py:1500). Frontend: `Debtors` component (App_js_fixed.js:4731) — pure presenter over the API, refreshes on `live.invoices`.

✓ No issues found.

- Pulls invoices with `status IN (sent, overdue)` (payroll.py:1509–1512) — "sent" = "pending". Paid and draft excluded from the outstanding balance everywhere.
- Amounts are ZAR equivalents via `_to_zar()` (payroll.py:1523); frontend renders backend values without recomputation.
- Aging strictly from `due_date` (payroll.py:1517–1543); invoices without a due_date go to `not_due` rather than inflating overdue (audit fix retained). Buckets: not_due / 0–30 / 31–60 / 61–90 / 90+.
- Reconciliation RULE 2 (>90-day debtors) item list uses `_to_zar()` (payroll.py:864) — yesterday's fix still in place.
- Frontend mock data only appears when the API call fails and is clearly badged "Demo Mode" (App_js_fixed.js:4777).

---

## 4. Creditors (Accounts Payable)

Backend: `/reports/creditors-aging` (payroll.py:1563). Frontend: `Creditors` component (App_js_fixed.js:4857) — presenter over the API, refreshes on `live.purchaseOrders` / `live.expenses`.

✓ No issues found.

- Sources: POs with `status IN (received, partial)` (payroll.py:1579–1582) plus unpaid on-credit expenses (`is_on_credit == True AND paid_at IS NULL`, payroll.py:1671–1675). Received-but-unpaid POs therefore appear as outstanding creditors.
- Fully paid POs excluded — status "paid" not in the filter; paid credit expenses excluded by the `paid_at IS NULL` filter.
- Per-PO amount = actual AP credits posted to account 2000 by each delivery (payroll.py:1587–1604, 1651), so partial POs show delivered value only; falls back to `po.total_amount` when no journal entry exists yet.
- Supplier bank details decrypted with `decrypt_field()` before display (payroll.py:1639–1641); suppliers.py list endpoint does the same (suppliers.py:48–50) and encrypts on write (suppliers.py:68, 78).
- Aging from due date = received_date + supplier payment_terms (default 30) for POs (payroll.py:1623–1626); expense_date + 30 for credit expenses (payroll.py:1679–1682).
- Bucket totals computed from the same entry list the vendors table shows, so cards and ledger always agree (payroll.py:1721–1734).
- PO amounts are VAT-inclusive by design (correct for a creditors book — you owe the supplier the gross amount); UI labels the column "Amount (incl. VAT)" (App_js_fixed.js:4968).

---

## 5. Cross-module consistency

✓ No journal coverage gaps.

| Event | Posting function (journal.py) | Called from |
|---|---|---|
| Invoice raised | post_invoice_raised:181 | companies.py:251 |
| Invoice payment | post_invoice_paid:221 | companies.py:298, portal.py:205 |
| Expense recorded | post_expense:280 | companies.py:455, 539, 844 |
| Expense payment (credit) | post_expense_paid:392 | companies.py:586 |
| PO receipt | post_po_received:421 | purchase_orders.py:332 |
| PO payment | post_po_paid:473 | purchase_orders.py:431 (pays journal AP balance, not face value) |
| Payroll run | post_payroll:355 | payroll.py:407 |
| Bank-import income | post_bank_income:315 | bank import flow |

A `/journal/backfill` repair path covers all of the above (journal.py:663–773). The PayFast portal payment path (changed yesterday for per-client credentials) still posts `post_invoice_paid` (portal.py:205).

**Control accounts:** the reconciliation endpoint cross-checks both — RULE 6 compares Debtors Control (1100) journal balance vs outstanding invoice `_to_zar` totals (payroll.py:929–949); RULE 7 compares Creditors Control (2000) vs per-PO journal AP credits + unpaid credit expenses (payroll.py:951–1009), correctly using delivered-value credits for partial POs. Both flag failures with a pointer to `/journal/backfill`.

---

## 6. Action items

None. No Critical, High, Medium, or Low items this run. Both Low items from 2026-07-05 (RULE 2 ZAR display; PO ZAR-only policy documentation) remain resolved.

---

*Change note vs 2026-07-05 run: only line-number drift from unrelated commits (PayFast credentials, AFS add-on, UI changes). All audited data paths unchanged and passing.*
