# ZuZan Audit Report — Reports, Debtors & Creditors
**Date:** 2026-06-27  
**Scope:** Reports (`/reports/dashboard`, `/reports/management`, `/reports/monthly-trend`, `/v1/summary`), Debtors (AR), Creditors (AP), cross-module journal coverage  
**Files reviewed:** `payroll.py`, `main.py`, `journal.py`, `companies.py`, `purchase_orders.py`, `database.py`, `App_js_fixed.js`

---

## 1. Summary

| Section | Verdict | Notes |
|---|---|---|
| Reports — dashboard & management | ✅ PASS | Revenue, expenses, payroll, PO COGS all correct; `_to_zar()` applied consistently |
| Reports — `/v1/summary` | ✅ PASS | Consistent with dashboard; includes PO COGS and depreciation |
| Debtors (AR) | ✅ PASS | Correct status filter, ZAR conversion, aging from `due_date`, paid excluded |
| Creditors (AP) | ✅ PASS with minor UX issue | Data correct; frontend refresh trigger wired to wrong state key |
| Cross-module journal coverage | ✅ PASS | All 5 event types covered; backfill present |

**Overall verdict: No data-accuracy bugs found. Two low-severity UX issues flagged.**

---

## 2. Reports

### 2.1 `_to_zar()` — `payroll.py:17–24`

Correctly converts invoice totals to ZAR:
- Non-ZAR invoices: uses `paid_amount_zar` (actual cash received) if set, otherwise `total_amount × exchange_rate`.
- ZAR invoices: returns `total_amount` unchanged.

✅ Applied correctly throughout all report endpoints.

### 2.2 `/reports/dashboard` — `payroll.py:430–565`

| Check | Result |
|---|---|
| `total_revenue` sums only `paid` invoices | ✅ `Invoice.status == InvoiceStatus.paid` (line 442) |
| `total_revenue` uses `_to_zar()` | ✅ `sum(_to_zar(i) for i in paid_invoices)` (line 443) |
| `total_outstanding` covers `sent` + `overdue` | ✅ `status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])` (line 447) |
| `total_outstanding` uses `_to_zar()` | ✅ (line 449) |
| Expenses excluded from revenue | ✅ Expenses are a separate sum (line 455) |
| Expenses ex-VAT | ✅ `e.amount - (e.vat_amount or 0)` (line 455) |
| Payroll costs from actual payslips | ✅ Sums `Payslip.total_cost` across all employees incl. terminated (lines 479–489) |
| PO COGS from received POs | ✅ Status filter `["received", "partial", "paid"]`, ex-VAT (lines 458–465) |
| PO double-count detection | ✅ Runtime duplicate-expense warning (lines 504–541) |
| Depreciation included | ✅ `DepreciationEntry.amount` summed (lines 468–471) |

**Note on "pending" terminology**: The audit checklist references "pending" invoices. This codebase has no `pending` `InvoiceStatus` value — the enum is `draft / sent / paid / overdue` (`database.py:36–40`). The outstanding filter correctly uses `sent + overdue`, which is the semantic equivalent. No data issue, but the enum label mismatch between internal documentation and code should be noted.

### 2.3 `/reports/management` — `payroll.py:1020–1191`

| Check | Result |
|---|---|
| Revenue uses `_to_zar()` on paid invoices in date range | ✅ (line 1055) |
| Expenses ex-VAT | ✅ (lines 1063, 1068) |
| PO COGS (received in range) ex-VAT | ✅ (lines 1071–1082) |
| Payroll from period payslips | ✅ Filter by `Payslip.period` in range (lines 1100–1114) |
| Depreciation in range | ✅ `DepreciationEntry.period` between `from_period` and `to_period` (lines 1085–1092) |
| Revenue trend loop applies `_to_zar()` | ✅ `_to_zar(inv)` at line 1140 |
| Trend loop expenses ex-VAT | ✅ `ex.amount - (ex.vat_amount or 0)` (line 1146) |
| Trend loop PO COGS | ✅ (lines 1147–1153) |

### 2.4 `/v1/summary` — `main.py:245–287`

| Check | Result |
|---|---|
| Uses `_to_zar()` for revenue | ✅ (line 252) |
| Outstanding uses `_to_zar()` | ✅ (line 279) |
| Expenses ex-VAT | ✅ (line 255) |
| PO COGS included | ✅ (lines 257–264) |
| Depreciation included | ✅ (lines 266–269) |
| Payroll (all payslips) included | ✅ (lines 273–278) |

---

## 3. Debtors (Accounts Receivable)

### 3.1 Backend — `/reports/debtors-aging` (`payroll.py:1304–1364`)

| Check | Result |
|---|---|
| Status filter: `sent` + `overdue` only | ✅ `status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])` (line 1314–1315) |
| Paid invoices excluded | ✅ Not in the filter |
| Draft invoices excluded | ✅ Not in the filter |
| ZAR equivalent displayed | ✅ `round(_to_zar(inv), 2)` (line 1327) |
| Aging from `due_date`, not `date` | ✅ `due = inv.due_date` (line 1323); comment confirms the fix (line 1322) |
| Invoices with no `due_date` | ✅ Placed in `not_due` bucket, not falsely counted as overdue (lines 1332–1334) |
| Aging buckets: not_due / 0–30 / 31–60 / 61–90 / 90+ | ✅ All 5 buckets present (lines 1318, 1338–1347) |

### 3.2 Frontend — `Debtors` component (`App_js_fixed.js:4665–4781`)

| Check | Result |
|---|---|
| Calls `/reports/debtors-aging` | ✅ (line 4671) |
| Displays all 5 aging buckets | ✅ (lines 4674–4680) |
| Shows `inv.amount` (ZAR from backend) | ✅ (line 4737) |
| No manual currency conversion in frontend | ✅ All amounts are server-side ZAR |

**Minor issue (Low):** The `Debtors` component loads data once on mount (`useEffect` with empty dependency, line 4670–4672) and has no `live.reload` path. The `Creditors` component has a reload path (albeit wired to the wrong key — see §4). Debtors would not auto-refresh after a new payment is recorded without a full page reload. See Action Item 2.

---

## 4. Creditors (Accounts Payable)

### 4.1 Backend — `/reports/creditors-aging` (`payroll.py:1367–1461`)

| Check | Result |
|---|---|
| Status filter: `received` + `partial` only | ✅ `status.in_(["received", "partial"])` (line 1384–1385) — "paid" excluded |
| Fully paid POs excluded | ✅ `paid` not in filter |
| Received-but-unpaid POs included | ✅ `received` and `partial` statuses both included |
| Aging from `received_date + payment_terms` | ✅ `base_date + timedelta(days=payment_terms)` (line 1407) |
| Supplier bank details decrypted | ✅ `decrypt_field(sup.bank_name)`, `decrypt_field(sup.account_number)`, `decrypt_field(sup.branch_code)` (lines 1421–1424) |
| Vendors without `supplier_id` | ✅ `_get_supplier(None)` returns `None`; bank fields default to `None` gracefully |

### 4.2 Frontend — `Creditors` component (`App_js_fixed.js:4784–end`)

| Check | Result |
|---|---|
| Calls `/reports/creditors-aging` | ✅ (line 4791) |
| All 5 aging buckets displayed | ✅ (lines 4800–4806) |
| Per-vendor breakdown | ✅ (lines 4820–4825) |

**Issue (Low) — wrong reload dependency (`App_js_fixed.js:4794–4798`):**

```js
useEffect(() => {
  if (live.reload) {
    api("/reports/creditors-aging").then(setData).catch(()=>null);
  }
}, [live.expenses]);   // ← should be live.purchaseOrders
```

The creditors view subscribes to `live.expenses` changes but creditors are driven by purchase orders. A PO status change (receive / pay) will not trigger an automatic creditors refresh. The component will show stale data until the user navigates away and back. See Action Item 1.

---

## 5. Cross-module Journal Coverage

All five required event types have posting functions and are called from their respective endpoints. Backfill covers pre-existing records.

| Event | Posting function | Called from | Backfilled |
|---|---|---|---|
| Invoice raised | `post_invoice_raised` | `companies.py:209` | ✅ `journal.py:549` |
| Invoice payment | `post_invoice_paid` | `companies.py:245` | ✅ `journal.py:559` |
| Expense payment | `post_expense` | `companies.py:328`, `412`, `643` | ✅ `journal.py:565` |
| PO receipt | `post_po_received` | `purchase_orders.py:249` | ✅ `journal.py:589` |
| PO payment | `post_po_paid` | `purchase_orders.py:314` | ✅ `journal.py:601` |
| Payroll run | `post_payroll` | `payroll.py:336` | ✅ `journal.py:578` |

✅ No journal coverage gaps found.

### 5.1 Balance Sheet Account Reconciliation

The `/reports/reconciliation` endpoint (`payroll.py:725–914`) contains explicit reconciliation rules:

- **Rule 6 (AR control — account 1100):** Journal AR balance vs. sum of `_to_zar()` on outstanding invoices. Differences > R1.00 flagged as `fail` with `/journal/backfill` repair advice (`payroll.py:826–846`). ✅
- **Rule 7 (AP control — account 2000):** Journal AP balance vs. sum of `total_amount` on received/partial POs. Same tolerance and repair path (`payroll.py:848–865`). ✅

---

## 6. Action Items

| # | Severity | File | Description |
|---|---|---|---|
| 1 | **Low** | `App_js_fixed.js:4798` | Creditors component reloads on `live.expenses` change instead of `live.purchaseOrders` (or equivalent PO-state signal). Fix: change the `useEffect` dependency from `[live.expenses]` to `[live.purchaseOrders]` (or add a dedicated `live.purchaseOrders` counter that increments on PO receive/pay). Without this, the creditors view shows stale data after PO status changes until the user navigates away and back. |
| 2 | **Low** | `App_js_fixed.js:4670–4672` | Debtors component has no live-reload path — data fetched once on mount only. Add a `live.invoices` dependency (similar to how `Invoices` view handles it) so the debtors view refreshes when a payment is recorded. |
| 3 | **Low** | `database.py:36–40` / internal docs | `InvoiceStatus` enum has no `pending` value (`draft / sent / paid / overdue`). Internal documentation and the audit checklist both use the term "pending" to describe unsent/outstanding invoices. Clarify in CLAUDE.md or code comments that `sent ≡ pending` for AR purposes, to avoid confusion during future audits. |
| 4 | **Low** | `journal.py:260–287` (`post_expense`) | Expenses are journalised as immediately cash-paid (`CR Bank`) at creation time. There is no accrual path for credit-term expenses (e.g. a 30-day supplier invoice recorded as an expense). If users record credit expenses, the Bank account (1000) will be understated. Consider adding an `is_on_credit` flag to `Expense` that routes to `CR Accounts Payable` instead of `CR Bank`. Current risk is low given typical SME usage, but worth flagging as usage grows. |
