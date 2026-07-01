# ZuZan Audit Report — Reports, Debtors & Creditors
**Date:** 2026-07-01  
**Scope:** Reports (dashboard/management/trend), Debtors (AR), Creditors (AP), Cross-module journal coverage  
**Files reviewed:** `payroll.py`, `journal.py`, `purchase_orders.py`, `companies.py`, `main.py`, `database.py`, `App_js_fixed.js`

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports — `/reports/dashboard` | ✅ PASS |
| Reports — `/reports/management` | ✅ PASS |
| Reports — `/reports/monthly-trend` | ✅ PASS |
| Reports — `/v1/summary` (Public API) | ✅ PASS |
| Debtors (AR) — backend `/reports/debtors-aging` | ✅ PASS |
| Debtors (AR) — frontend `Debtors` component | ✅ PASS |
| Creditors (AP) — backend `/reports/creditors-aging` | ⚠️ ISSUES FOUND |
| Creditors (AP) — frontend `Creditors` component | ✅ PASS |
| Cross-module journal coverage | ⚠️ ISSUES FOUND |

**Overall verdict:** Two high-severity bugs found in the partial PO receipt workflow. All other sections are correct.

---

## 2. Reports

### `/reports/dashboard` (payroll.py:430–569)

- **Total revenue** (line 443): `sum(_to_zar(i) for i in paid_invoices)` — correctly filters `status == InvoiceStatus.paid` and applies `_to_zar()` for multi-currency conversion. ✓
- **Total outstanding** (lines 445–449): filters `status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])` and applies `_to_zar()`. ✓
- **Expenses** (lines 452–455): ex-VAT (`e.amount - (e.vat_amount or 0)`) — correct for P&L. ✓
- **PO COGS** (lines 457–465): statuses `["received", "partial", "paid"]`, ex-VAT. Included in total_expenses. ✓
- **Depreciation** (lines 468–471): `DepreciationEntry` sum included in total_expenses. ✓
- **Payroll** (lines 479–489): sums `Payslip.total_cost` across all employees (including terminated) via joined query; falls back to estimated for companies with no payslips. ✓
- **Expenses excluded from revenue**: revenue is a separate variable from expenses. ✓
- **Duplicate-count detection** (lines 505–546): structural check comparing received PO amounts against expenses by supplier/month/amount with ±5% tolerance. ✓

### `/reports/management` (payroll.py:1064–1235)

- Revenue uses `_to_zar(i)` (line 1099). ✓
- Expenses ex-VAT (line 1107). ✓
- PO COGS: status `["received", "partial", "paid"]`, ex-VAT, filtered by `received_date` (lines 1115–1126). ✓
- Depreciation included per period range (lines 1129–1136). ✓
- Payroll: joins `Payslip.total_cost` for all employees in range (lines 1144–1158). ✓
- **Trend loop** (lines 1175–1205): uses `_to_zar(inv)` for each month's revenue, expenses ex-VAT, PO COGS, depreciation per period. ✓

### `/reports/monthly-trend` (payroll.py:572–641)

- Revenue per month: `_to_zar(inv)` applied (line 597). ✓
- Expenses ex-VAT per month (lines 604–611). ✓
- PO COGS per month by `received_date` (lines 613–622). ✓
- Depreciation per period string (lines 625–630). ✓

### `/v1/summary` (main.py:249–291)

- Imports `_to_zar` from payroll module (line 252). ✓
- Revenue: `sum(_to_zar(i) for i in paid_invs)` (line 256). ✓
- Expenses ex-VAT + PO COGS ex-VAT + depreciation + payroll (lines 258–282). ✓
- Outstanding: `sum(_to_zar(i) for i in out_invs)` (line 283). ✓

---

## 3. Debtors (AR)

### Backend — `/reports/debtors-aging` (payroll.py:1348–1408)

- **Status filter** (lines 1357–1360): `status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])`. The enum comment (database.py:38) confirms `sent` = "pending" in AR/audit terminology. Paid invoices are excluded. ✓
- **ZAR amounts** (line 1371): `"amount": round(_to_zar(inv), 2)` — foreign-currency invoices converted via exchange_rate or paid_amount_zar. ✓
- **Aging from `due_date`** (lines 1364–1391): invoices without a `due_date` go to `not_due` bucket rather than forcing a false overdue bucket. No fallback to `issue_date` or `created_at`. ✓
- **Aging bucket logic**: 
  - `< 0 days`: not_due ✓
  - `0–30`: current ✓
  - `31–60`: 31_60 ✓
  - `61–90`: 61_90 ✓
  - `> 90`: over_90 ✓

### Frontend — `Debtors` component (App_js_fixed.js:4669–4793)

- Calls `api("/reports/debtors-aging")` on mount (line 4676). ✓
- Refreshes when `live.invoices` changes (lines 4681–4684) — updates after invoice payments. ✓
- Displays `inv.amount` from API (line 4749) — ZAR value supplied by backend. ✓
- Falls back to mock data (lines 4695–4702) when API returns null (demo mode). ✓
- Five bucket cards + aging summary table rendered correctly. ✓

---

## 4. Creditors (AP)

### Backend — `/reports/creditors-aging` (payroll.py:1411–1555)

- **PO filter** (lines 1427–1430): `status.in_(["received", "partial"])` — fully paid POs excluded. ✓
- **On-credit expenses** (lines 1489–1537): unpaid on-credit expenses (`is_on_credit=True, paid_at=None`) included as AP items. ✓
- **Supplier bank details decrypted** (lines 1465–1467): `decrypt_field(sup.bank_name)`, `decrypt_field(sup.account_number)`, `decrypt_field(sup.branch_code)` called before including in response. ✓
- **Aging basis**: POs aged from `received_date + payment_terms` days; on-credit expenses aged from `expense_date + 30` days. ✓

**⚠️ Issue 1 (High):** For partial POs, `"amount": round(po.total_amount or 0, 2)` (line 1477) shows the **full PO value**, not the value of goods actually received. If only part of the PO was delivered, the creditor balance displayed to the user is overstated by the undelivered portion.

**⚠️ Issue 2 (High — see also Cross-module):** This overstated amount is consistent with the journal entry posted at receipt time (`post_po_received` posts `po.total_amount` to AP regardless of partial delivery). The UI and journal are internally consistent, but both are wrong for partial receipts. The root cause is in `receive_po` / `post_po_received` — see Action Item #1.

### Frontend — `Creditors` component (App_js_fixed.js:4795–end)

- Calls `api("/reports/creditors-aging")` on mount (line 4803). ✓
- Refreshes when `live.purchaseOrders` or `live.expenses` changes (lines 4807–4811). ✓
- Renders vendors grouped with aging buckets; bucket filter works client-side (lines 4833–4838). ✓
- Falls back to mock data when API returns null. ✓

---

## 5. Cross-module Journal Coverage

All primary financial events have journal posting functions in `journal.py` and are wired from their source routers:

| Event | Posting function | Called from | Status |
|---|---|---|---|
| Invoice raised | `post_invoice_raised` | companies.py:228 | ✓ |
| Invoice paid | `post_invoice_paid` | companies.py:275 | ✓ |
| Invoice COGS | `post_invoice_cogs` | companies.py:231 | ✓ |
| Invoice deleted | `reverse_journal_entries` (all sources) | companies.py:301 | ✓ |
| Expense incurred | `post_expense` | companies.py:421 | ✓ |
| On-credit expense paid | `post_expense_paid` | companies.py:552 | ✓ |
| PO received | `post_po_received` | purchase_orders.py:249 | ✓ |
| PO paid | `post_po_paid` | purchase_orders.py:314 | ✓ |
| PO deleted | `reverse_journal_entries` | purchase_orders.py:189 | ✓ |
| Payroll run | `post_payroll` | payroll.py:336 | ✓ |
| Fixed asset acquired | `post_asset_acquisition` | fixed_assets router (backfill) | ✓ |
| Depreciation | `post_depreciation` | fixed_assets router | ✓ |
| Asset disposal | `post_asset_disposal` | fixed_assets router | ✓ |

**AR Control (1100) reconciliation:** Checked in `/reports/reconciliation` (payroll.py:846–862) — compares journal balance against outstanding invoice sum via `_to_zar()`. Tolerance R1.00. ✓

**AP Control (2000) reconciliation:** Checked in `/reports/reconciliation` (payroll.py:865–898) — compares journal balance against open POs (`total_amount`) plus unpaid on-credit expenses. Tolerance R1.00. ✓

**⚠️ Issue 3 (High):** `receive_po` (purchase_orders.py:215–264) calls `post_po_received(po, db)` with **no deduplication guard**. The status check at line 219 blocks re-receiving a fully-received PO, but does NOT block re-receiving a **partial** PO:

```python
if po.status in ("received", "cancelled"):   # "partial" is NOT blocked
    raise HTTPException(...)
```

If a partial PO is received a second time, `post_po_received` posts the full `po.total_amount` again to COGS (5000) and AP (2000). This results in:
- **Double-counted COGS**: expenses and gross profit both misstated
- **AP control account (2000) overstated**: balance sheet fails to reconcile
- **Creditors-aging overstated**: supplier balance appears twice

The backfill function (`journal.py:632–641`) has deduplication via `("purchase_order", po.id) not in existing`, but the live `receive_po` endpoint does not.

**Note:** The `/reports/reconciliation` AP control check (rule 7) will flag this as a fail if it occurs, providing downstream detection — but the bug must be fixed at source.

---

## 6. Action Items

**#1 — Critical: Fix partial PO receipt to use `received_total` instead of `po.total_amount`**  
`purchase_orders.py`, `receive_po` endpoint (lines 231–249) and `journal.py`, `post_po_received` (lines 363–396).  
The variable `received_total` (line 231) is computed correctly but never passed to the journal. The journal should post `received_total` (net and VAT portions) to COGS and AP — not the full PO amount. Also update the creditors-aging response (payroll.py:1477) to show the received amount rather than `po.total_amount` for partial POs.

**#2 — High: Add deduplication guard in `receive_po` to prevent double-posting on partial re-receipts**  
`purchase_orders.py`, `receive_po` endpoint (lines 247–257).  
Before calling `post_po_received`, check whether a `("purchase_order", po.id)` journal entry already exists. If so, post only the **incremental** received amount (delta since last receipt), or block re-receive and require a new PO line. This mirrors the deduplication already in `backfill_company`.

**#3 — Medium: Creditors-aging shows full `po.total_amount` for partial POs**  
`payroll.py`, `creditors_aging` (line 1477).  
Once Action Item #1 is resolved and partial receipts post correct amounts, update this view to show the actual received-and-unpaid amount rather than the full PO total. Until then, add a UI note that partial PO amounts reflect the full order value.

**#4 — Low: PO received_date backfill uses `created_at` as a proxy**  
`main.py:53–72` (startup backfill) and `purchase_orders.py:267–290` (manual backfill endpoint).  
For legacy POs that existed before the `received_date` column, `created_at` is used. This can cause the monthly-trend and management-accounts PO COGS to be assigned to the wrong month if goods were received later than the PO was created. Consider prompting users to verify/correct received dates for older POs, or flagging these POs in the UI.
