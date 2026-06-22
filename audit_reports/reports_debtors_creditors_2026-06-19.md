# ZuZan Audit Report — Reports, Debtors & Creditors
**Date:** 2026-06-19
**Files audited:**
- `zuzan-backend/payroll.py` (1,350 lines — reports, payroll engine)
- `zuzan-backend/main.py` (839 lines — public API `/v1/summary`)
- `zuzan-backend/journal.py` (583 lines — double-entry engine)
- `zuzan-backend/purchase_orders.py` (265 lines — PO receive/pay)
- `zuzan-backend/companies.py` (invoice/expense endpoints)
- `App_js_fixed.js` (7,008 lines — frontend)

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports — `/reports/dashboard` | ✅ PASS — revenue, outstanding, PO COGS, payroll all correct |
| Reports — `/reports/management` | ✅ PASS — consistent with dashboard; trend loop uses `_to_zar()` |
| Reports — `/reports/provisional-tax` | ❌ FAIL — uses VAT-inclusive expenses (over-deducts costs) |
| Reports — `/v1/summary` (public API) | ✅ PASS — `_to_zar()` used correctly; PO COGS included |
| Reports — `/reports/monthly-trend` | ⚠️ WARN — payroll excluded from trend "expenses"; shows gross not net profit |
| Debtors (AR) | ✅ PASS — correct filter, ZAR amounts, `due_date` aging, paid excluded |
| Creditors (AP) | ✅ PASS — correct filter, bank fields decrypted, aging from due date |
| Cross-module — Journal coverage | ✅ PASS — all five event types have posting functions; live hooks confirmed |
| Cross-module — AR/AP reconciliation | ⚠️ WARN — no automated comparison of journal account balances vs raw table totals |

---

## 2. Reports

### `/reports/dashboard` (payroll.py:253)
**✓ No issues found** on the core checklist.

- `total_revenue` (line 266): sums only `InvoiceStatus.paid`, applies `_to_zar()` ✓
- `total_outstanding` (lines 269–272): filters `sent` + `overdue`, applies `_to_zar()` ✓
- Expenses (line 276–278): ex-VAT (`e.amount - (e.vat_amount or 0)`) ✓
- Payroll (lines 290–301): uses actual payslip `total_cost` if run, falls back to estimate ✓
- PO COGS (lines 281–288): received/partial/paid POs; no double-count because `receive_po()` deliberately sets `expense_id = None` and does not create an `Expense` record ✓

### `/reports/management` (payroll.py:719)
**✓ No issues found.**

- Revenue: `_to_zar()` applied (line 733) ✓
- Expenses: ex-VAT (lines 740–745) ✓
- PO COGS: received/partial/paid, filtered by `received_date` in month (lines 747–758) ✓
- Revenue trend loop (lines 790–813): `_to_zar(inv)` applied consistently (line 799) ✓

### `/reports/monthly-trend` (payroll.py:322)
**⚠️ WARN (Medium) — Payroll excluded from trend.**

The trend endpoint includes expenses (ex-VAT) and PO COGS but does **not** subtract payroll from the "expenses" line or "profit" figure (unlike the management accounts which deducts payroll separately). Users reading the trend chart see gross margin, not net profit — this may be intentionally a gross margin view, but the field name `"profit"` (line 378) is misleading without a header or note clarifying it excludes payroll.

- **File:line** — `payroll.py:374–379`
- Revenue uses `_to_zar()` ✓ (line 347)

### `/reports/provisional-tax` (payroll.py:845)
**❌ FAIL (High) — VAT-inclusive expenses inflate cost deductions.**

`ytd_expenses` at line 875 sums `e.amount` (the full VAT-inclusive total) instead of `e.amount - (e.vat_amount or 0)`. Every other P&L endpoint (dashboard, management, monthly-trend, v1/summary) correctly strips input VAT from expenses. Using gross amounts here overstates YTD expenses, reduces computed taxable income, and understates the provisional tax liability. For a company with, e.g., R100k in VAT-inclusive expenses (R15k VAT), taxable income is understated by R15k and the IRP6 first payment will be R4,050 too low.

- **File:line** — `payroll.py:875`
- **Fix:** Change to `sum(e.amount - (e.vat_amount or 0) for e in expenses)`

### `/v1/summary` in `main.py` (main.py:210)
**✓ No issues found.**

- Revenue: `_to_zar()` (line 217) ✓
- Expenses: ex-VAT (line 220) ✓
- PO COGS: received/partial/paid (lines 222–229) ✓
- Outstanding: `_to_zar()` (line 230) ✓

---

## 3. Debtors (Accounts Receivable)

### Backend — `/reports/debtors-aging` (payroll.py:932)
**✓ No issues found on the primary checklist.**

- Status filter (line 941): `sent` and `overdue` only — paid invoices excluded ✓
- ZAR amounts (line 951): `_to_zar(inv)` — foreign-currency invoices converted correctly ✓
- Aging date (line 949): uses `due_date` first, falls back to `issue_date` then `created_at` only if `due_date` is null ✓
- Bucket logic (lines 959–968): correctly assigns not_due / 0–30 / 31–60 / 61–90 / 90+ ✓

**Minor observation (Low):** `InvoiceStatus` enum (database.py:36) has no `"pending"` value — only `draft`, `sent`, `paid`, `overdue`. The audit spec mentioned `('sent','pending','overdue')` but `pending` does not exist; the code is correct as-is.

### Frontend — `Debtors` component (App_js_fixed.js:3518)
**✓ No issues found.**

- Calls `/reports/debtors-aging` (line 3524) ✓
- Displays `inv.amount` which is the pre-computed `_to_zar()` value returned by the backend ✓
- Aging bucket labels and keys match backend response keys exactly ✓
- Falls back to mock data in demo mode (line 3535–3543) — clearly labelled with "Demo Mode" badge ✓

---

## 4. Creditors (Accounts Payable)

### Backend — `/reports/creditors-aging` (payroll.py:988)
**✓ No issues found on the primary checklist.**

- Status filter (line 1004): `received` and `partial` only — fully paid POs (`"paid"`) excluded ✓
- Supplier bank details (lines 1042–1045): `decrypt_field()` called for `bank_name`, `account_number`, `branch_code` before returning to client ✓
- Aging date (lines 1027–1029): `received_date + payment_terms days` → correct due-date calculation ✓
- PO amounts: `po.total_amount` (VAT-inclusive) — appropriate for AP since the full liability is owed ✓

**Minor cosmetic issue (Low):** `entry["days_overdue"]` is clamped to `max(0, days_overdue)` at line 1057, so items in the `"not_due"` bucket display `0 days` in the frontend table instead of a negative "days until due" figure. Not incorrect but slightly uninformative for items not yet due.

- **File:line** — `payroll.py:1057`

### Frontend — `Creditors` component (App_js_fixed.js:3637)
**✓ No issues found.**

- Calls `/reports/creditors-aging` (line 3644) ✓
- Displays amounts from backend ✓
- Bucket filter wired correctly — filters vendor list client-side by `entry.bucket` (line 3676) matching backend bucket keys ✓
- `useEffect` on `live.expenses` triggers reload (lines 3647–3651) ✓

---

## 5. Cross-Module Journal Coverage

### Posting functions in `journal.py`

| Event | Function | Status |
|---|---|---|
| Invoice raised | `post_invoice_raised` (line 160) | ✅ exists |
| Invoice paid | `post_invoice_paid` (line 187) | ✅ exists |
| Expense paid | `post_expense` (line 214) | ✅ exists |
| Payroll run | `post_payroll` (line 244) | ✅ exists |
| PO received | `post_po_received` (line 281) | ✅ exists |
| PO paid | `post_po_paid` (line 311) | ✅ exists |

### Live hook coverage (called from operational endpoints, not just backfill)

| Event | Caller | Status |
|---|---|---|
| Invoice raised | `companies.py:204` | ✅ wired |
| Invoice paid | `companies.py:229` | ✅ wired |
| Expense posted | `companies.py:288, 484` | ✅ wired (both create and bank-import paths) |
| Payroll run | `payroll.py:209–213` | ✅ wired |
| PO received | `purchase_orders.py:224–229` | ✅ wired |
| PO paid | `purchase_orders.py:259–263` | ✅ wired |

**⚠️ WARN (Medium) — Journal errors are silently swallowed in PO and payroll flows.**

All three live-hook call sites in `purchase_orders.py` (receive and pay) and `payroll.py` (run) wrap the journal post in a bare `try/except` that only logs a warning. If `post_po_received`, `post_po_paid`, or `post_payroll` raises (e.g., missing account, database timeout), the PO/payslip status is committed but no journal entry is created. Over time this causes the journal account balances for AR (1100), AP (2000), Bank (1000), and Payroll liabilities (2200/2210/2220) to diverge from the source tables without any user-visible alert.

- **File:lines** — `purchase_orders.py:224–229`, `purchase_orders.py:259–263`, `payroll.py:209–213`

### Balance Sheet — AR/AP Control Reconciliation
**⚠️ WARN (Medium) — No automated cross-check of journal balances vs raw table totals.**

The `/reports/reconciliation` endpoint checks the balance sheet equation (Rule 1) and reports raw open-PO AP totals (Rule 5), but does **not** compare:
- Account 1100 (AR journal balance) vs `SUM(_to_zar(inv))` for outstanding invoices
- Account 2000 (AP journal balance) vs `SUM(po.total_amount)` for open POs

If journal postings are missed (see swallowed-exception risk above), the journal-derived balance sheet will silently understate AR or AP while the debtors/creditors-aging reports (which read raw tables) show the correct outstanding amounts. A user relying on the balance sheet would see an incorrect figure.

- **File:line** — `payroll.py:465` (reconciliation endpoint — missing check)

---

## 6. Action Items

**#1 [HIGH] Fix VAT-inclusive expenses in provisional-tax endpoint**
`payroll.py:875` — Change `sum(e.amount for e in expenses)` to `sum(e.amount - (e.vat_amount or 0) for e in expenses)`. Also add PO COGS to `ytd_expenses` for consistency with the dashboard (currently omitted from provisional-tax calculation, which further understates the tax liability when POs are present).

**#2 [Medium] Raise/surface journal posting failures**
`purchase_orders.py:224–229`, `purchase_orders.py:259–263`, `payroll.py:209–213` — Replace silent `except` swallowing with either (a) raising an HTTP 500 so the user knows the journal didn't post, or (b) writing a `JournalError` flag to the PO/payslip record and surfacing it in the UI. Silent failure is the riskiest pattern in a double-entry system.

**#3 [Medium] Add AR/AP control-account reconciliation to `/reports/reconciliation`**
Compare account 1100 journal balance vs `SUM(_to_zar(outstanding_invoices))` and account 2000 journal balance vs `SUM(open_po.total_amount)`. Flag divergences > R1. This turns the reconciliation report into a genuine integrity check rather than just a balance-sheet-equation check.

**#4 [Medium] Clarify monthly-trend "profit" excludes payroll**
`payroll.py:374–379` — Either rename the `"profit"` field to `"gross_profit"` in the JSON response and update the frontend label, or add payroll costs to the trend calculation. Currently the trend "profit" is gross margin (before payroll), inconsistent with the management accounts `net_profit` figure.

**#5 [Low] Fix `days_overdue` display for not-yet-due creditors**
`payroll.py:1057` — Remove the `max(0, ...)` clamp (or keep it but add a `days_until_due` field) so the frontend can show "due in N days" for items in the `not_due` bucket instead of "0 days".
