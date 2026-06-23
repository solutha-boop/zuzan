# ZuZan Audit Report — Reports, Debtors & Creditors
**Date:** 2026-06-23  
**Scope:** Reports (`/reports/dashboard`, `/reports/management`), Debtors (AR), Creditors (AP)  
**Files reviewed:** `payroll.py`, `companies.py`, `purchase_orders.py`, `journal.py`, `main.py`, `App_js_fixed.js`

---

## 1. Summary

| Section | Verdict |
|---------|---------|
| Reports — `/reports/dashboard` | ✅ PASS (1 High issue in `/v1/summary`) |
| Reports — `/reports/management` | ✅ PASS |
| Reports — `/v1/summary` (Public API) | ❌ FAIL — payroll omitted from net_profit |
| Debtors (AR) | ✅ PASS with 1 Low caveat |
| Creditors (AP) | ✅ PASS with 1 Medium display issue |
| Cross-module journal coverage | ⚠️ WARN — silent failure risk + backfill gaps |

---

## 2. Reports

### `/reports/dashboard` (payroll.py:430–536)

**total_revenue — PASS**  
- Sums only `InvoiceStatus.paid` invoices (line 439–443).  
- Applies `_to_zar()` throughout. `_to_zar()` uses `paid_amount_zar` when set (exact ZAR received), falls back to `total_amount × exchange_rate` for foreign currencies, and uses `total_amount` as-is for ZAR (lines 17–24). Correct.

**total_outstanding — PASS**  
- Filters on `status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])` (lines 445–449). Applies `_to_zar()`. Paid invoices are excluded by status filter. Correct.

**Expenses excluded from revenue — PASS**  
- Expenses are accumulated separately into `total_expenses` (lines 452–465). No mixing with revenue.

**Payroll in expenses — PASS**  
- Dashboard uses actual `Payslip.total_cost` sum (all-time) when payslips exist; falls back to `calc_payroll()` estimate for employees without payslips (lines 478–484). `net_profit = gross_profit - total_payroll` (line 487). Correct.

**PO COGS — PASS**  
- Received POs (status `received`, `partial`, `paid`) are summed ex-VAT: `(po.total_amount - po.vat_amount)` (lines 458–465). Added to `total_expenses` after expenses. No double-counting: `purchase_orders.py` line 219 explicitly sets `expense_id = None` to prevent auto-creating Expense records on PO receipt.

**Double-count detection — LOW risk**  
- The heuristic check at lines 497–513 scans expense `description + vendor` for PO number strings. This is unreliable; a structural comparison (same date range, same supplier, overlapping amount) would be more robust. Flag as LOW.

### `/reports/management` (payroll.py:984–1123)

**Revenue — PASS**  
- Applies `_to_zar()` (line 998). Current-month paid invoices only.

**Expenses — PASS**  
- Ex-VAT: `e.amount - (e.vat_amount or 0)` (line 1005). PO COGS included ex-VAT (lines 1013–1023). Depreciation included (lines 1026–1033).

**Payroll — PASS**  
- Uses actual `Payslip.total_cost` for the current period if run; otherwise estimates (lines 1041–1048). Correctly separated from expenses into `payroll_cost` field.

**Revenue trend loop — PASS**  
- `_to_zar()` applied at line 1074. PO COGS (lines 1081–1087) and depreciation (lines 1089–1094) added per-month. Consistent with dashboard.

### `/v1/summary` (main.py:210–231) — ❌ HIGH ISSUE

**Payroll omitted from net_profit:**  
```python
# main.py line 231
return {"net_profit": round(total_revenue - total_expenses, 2)}
```
`total_expenses` includes expenses + PO COGS (ex-VAT) but **does NOT include payroll costs**.  
The dashboard and management accounts both deduct `total_payroll` before computing `net_profit`, but the public API does not. For any company with employees, the public API returns an overstated `net_profit`.  
`_to_zar()` is applied correctly (line 217). The payroll omission is the only issue here.

---

## 3. Debtors (Accounts Receivable)

### Backend — `/reports/debtors-aging` (payroll.py:1226–1286)

**Status filter — PASS**  
- Filters `Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])` (lines 1235–1238). Paid invoices are excluded. New invoices are created directly as `InvoiceStatus.sent` (`companies.py` line 199), so `draft` invoices never enter the debtors book.

**ZAR display — PASS**  
- `amount` in each entry is `round(_to_zar(inv), 2)` (line 1249). Foreign-currency invoice amounts are converted correctly.

**Aging buckets from due_date — PASS**  
- Buckets are calculated from `inv.due_date` (lines 1244–1269). Invoices with no `due_date` are placed in `not_due` with a comment explaining the fix: "removed issue_date/created_at fallback" (line 1244). This prevents falsely overstating overdue balances.

**Bucket logic — PASS**  
- `< 0` days → `not_due`; `0–30` → `current`; `31–60` → `31_60`; `61–90` → `61_90`; `> 90` → `over_90` (lines 1260–1269). Correct.

**Paid invoices excluded — PASS**  
- Only `sent` and `overdue` statuses queried; paid invoices are not in the result set.

**Frontend `Debtors` component (App_js_fixed.js:4217–4333) — PASS**  
- Calls `/reports/debtors-aging` (line 4223). Renders `inv.amount` directly (the ZAR-converted value from backend). All 5 buckets displayed. No client-side currency conversion applied.

**Low caveat — Possible `pending` status orphans:**  
The `InvoiceStatus` enum may contain a `pending` value (evidenced by the frontend `StatusBadge` component at App_js_fixed.js line ~199). If any historical invoice records carry `status = 'pending'` (e.g., from older code versions), they are silently excluded from the debtors book. Current code creates all invoices as `sent`, so this is not a live issue, but a database sweep is recommended to confirm no `pending` invoices exist.

---

## 4. Creditors (Accounts Payable)

### Backend — `/reports/creditors-aging` (payroll.py:1289–1383)

**Status filter — PASS**  
- Queries POs with `status.in_(["received", "partial"])` (lines 1305–1308). Fully paid POs (status `paid`) are excluded. Correct.

**Aging calculation — PASS**  
- Due date = `received_date + payment_terms days` (lines 1327–1329). Falls back to `order_date`, then `created_at` if `received_date` is null (line 1328). Bucket logic mirrors debtors. Correct.

**Supplier bank field decryption — PASS**  
- `decrypt_field()` is called on `sup.bank_name`, `sup.account_number`, and `sup.branch_code` (lines 1343–1345) before including in the response. Correct.

**Fully paid POs excluded — PASS**  
- `status == "paid"` is not in the filter. `post_po_paid()` in journal.py (lines 356–377) posts DR AP / CR Bank to clear the liability. After `pay_po()` in purchase_orders.py (line 285), the PO status becomes `paid` and is no longer returned by `creditors-aging`.

**Medium issue — VAT-inclusive amounts displayed without label:**  
- The `amount` field for each creditor entry is `po.total_amount` (line 1355), which is the VAT-inclusive amount payable to the supplier. This is accounting-correct (AP = total owed) and consistent with how the AP control account (2000) is posted. However, the frontend displays this as "Amount" without indicating it is VAT-inclusive. Since expenses are shown ex-VAT elsewhere in the app, users may expect ex-VAT here. Recommend adding "(incl. VAT)" to the column label.

**Frontend `Creditors` component (App_js_fixed.js:4336–4489) — PASS**  
- Calls `/reports/creditors-aging` (line 4343). Renders `v.total` and `exp.amount` from backend. Bucket filter works correctly. Bank details would be decrypted server-side before display.

---

## 5. Cross-Module Journal Coverage

| Event | Live posting | Backfill coverage |
|-------|-------------|-------------------|
| Invoice raised | ✅ `companies.py:209` | ✅ `journal.py:539-545` |
| Invoice payment | ✅ `companies.py:242` | ✅ `journal.py:548-554` |
| Expense paid | ✅ `companies.py:307` | ✅ `journal.py:557-563` |
| Payroll run | ✅ `payroll.py:336` | ✅ `journal.py:566-573` |
| PO received | ✅ `purchase_orders.py:226` | ✅ `journal.py:576-585` |
| PO paid | ✅ `purchase_orders.py:291` | ✅ `journal.py:587-597` |
| Stock adjustment | ✅ `inventory.py` (post_stock_adjustment) | ❌ NOT in backfill |
| Asset acquisition | ✅ `fixed_assets.py` | ❌ NOT in backfill |
| Depreciation | ✅ `fixed_assets.py` | ❌ NOT in backfill |
| Asset disposal | ✅ `fixed_assets.py` | ❌ NOT in backfill |

**Silent journal failure for invoices and expenses — HIGH:**  
`companies.py` catches journal post errors silently for invoice creation (line 214–215), invoice payment (line 244–245), and expense creation (line 310). If `post_invoice_raised()` or `post_expense()` fails (e.g., accounts not initialised), the invoice/expense is committed to the database with no journal entry. This will cause:
- AR control account (1100) to diverge from outstanding invoice totals
- Bank account (1000) balance to understate actual cash inflows/outflows
- Reconciliation rule AR-6 (`/reports/reconciliation`) to flag a mismatch

By contrast, `payroll.py` (line 338–343) and `purchase_orders.py` (lines 229–234) correctly roll back the entire transaction and raise an HTTP error if journal posting fails. Invoice and expense handlers should do the same.

**Backfill gaps for fixed assets and inventory — MEDIUM:**  
`backfill_company()` in `journal.py` (lines 526–600) covers invoices, payments, expenses, payroll, and POs. It does NOT include `DepreciationEntry`, `InventoryItem` stock adjustments, or fixed asset acquisition/disposal events. Companies that had fixed assets or stock adjustments before the journal was first initialized will have incomplete trial balances and balance sheets. The fixed assets module should have its own backfill endpoint, or `backfill_company()` should be extended.

**Balance sheet accounts reconcile — PASS (conditional)**  
The reconciliation endpoint (payroll.py:689–878) checks:
- AR control (1100) vs outstanding invoice totals (Rule 6, lines 790–810)
- AP control (2000) vs open PO totals (Rule 7, lines 812–829)

Both use `_to_zar()` on the raw side and `account_balance()` on the journal side. Structurally correct. The checks will flag any divergence caused by the silent failure issue above.

---

## 6. Action Items

**Critical**  
*(none)*

**High**

1. **[High] `/v1/summary` payroll omission** (`main.py:231`)  
   Add payroll deduction to the public API net_profit calculation:
   ```python
   payroll = db.query(func.sum(Payslip.total_cost)).join(Employee)...scalar() or 0
   return {"net_profit": round(total_revenue - total_expenses - payroll, 2)}
   ```

2. **[High] Silent journal failures for invoices and expenses** (`companies.py:207–215`, `239–245`, `304–310`)  
   Wrap journal posts in a rollback-and-raise pattern identical to payroll.py (lines 337–343). If journal posting fails, roll back the invoice/expense commit and return HTTP 500 so the caller is aware and can retry. At minimum, add `db.rollback()` before the logger.error call so partial journal entries are not left in the database.

**Medium**

3. **[Medium] Fixed asset / stock backfill missing** (`journal.py:526–600`)  
   Extend `backfill_company()` to include `DepreciationEntry` records and fixed asset acquisition/disposal entries. Or create `/fixed-assets/backfill` and `/inventory/backfill` endpoints and run them alongside the existing backfill on startup.

4. **[Medium] Creditors column label lacks VAT indicator** (`App_js_fixed.js:4446`)  
   Change the "Amount" column header in the Creditors table to "Amount (incl. VAT)" to prevent confusion with the ex-VAT treatment used elsewhere in the app.

**Low**

5. **[Low] Sweep for `pending` status invoices in database**  
   Run `SELECT COUNT(*) FROM invoices WHERE status = 'pending'`. If any exist, either include `InvoiceStatus.pending` in the `debtors-aging` query or migrate those records to `sent`. Document the decision.

6. **[Low] PO double-count heuristic** (`payroll.py:497–513`)  
   Replace the text-matching check with a structural query: identify expenses whose `(expense_date, vendor, amount)` overlap with received POs by the same supplier in the same month. A data-driven warning is more reliable than description string matching.

---

*Report generated by automated audit — 2026-06-23*
