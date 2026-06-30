# ZuZan Audit Report — Reports, Debtors & Creditors
**Date:** 2026-06-30  
**Auditor:** Automated scheduled audit  
**Scope:** payroll.py (`/reports/*`), companies.py, purchase_orders.py, journal.py, main.py, App_js_fixed.js

---

## 1. Summary

| Section | Verdict |
|---------|---------|
| Reports — `/reports/dashboard` | ⚠️ MEDIUM issues (2): draft invoices inflate dashboard VAT; PO/expense double-count risk |
| Reports — `/reports/management` | ✅ PASS |
| Reports — `/v1/summary` (main.py) | ✅ PASS |
| Debtors (AR) | ✅ PASS |
| Creditors (AP) | ✅ PASS — minor aging fallback note |
| Cross-module journal coverage | ✅ PASS — all transaction types covered |

**Overall: 2 medium-severity issues, 2 low-severity issues requiring attention.**

---

## 2. Reports

### `/reports/dashboard` — `payroll.py` lines 430–565

**`total_revenue` (lines 439–443)**  
✅ Correctly filters to `status == InvoiceStatus.paid` only. Applies `_to_zar()` to every invoice. For foreign-currency invoices: uses `paid_amount_zar` if set, otherwise `total_amount × exchange_rate`. ZAR invoices: uses `total_amount` as-is. No expenses included in this sum.

**`total_outstanding` (lines 445–449)**  
✅ Correctly filters to `status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])`. Applies `_to_zar()`. Note: `InvoiceStatus.sent` is the system's "pending" status (confirmed by `database.py` line 38 comment: `# aka "pending" in AR/audit terminology`). No `pending` enum value exists — `sent` IS pending. This is correct.

**Expenses excluded from revenue**  
✅ Expenses are summed separately (`total_expenses`). No cross-contamination with revenue.

**Payroll costs (lines 473–492)**  
✅ Sums `Payslip.total_cost` across all employees (including terminated) for all-time payroll. Falls back to estimated cost from active employees if no payslips recorded. Correctly included in `net_profit = gross_profit - total_payroll`.

**PO COGS (lines 457–465)**  
✅ Received/partial/paid POs included ex-VAT: `(po.total_amount or 0) - (po.vat_amount or 0)`. Consistent with expense treatment.  
⚠️ **MEDIUM — Double-count risk:** The dashboard adds both `total_expenses` (from the `expenses` table) and `po_cogs` (from the `purchase_orders` table) as separate sums. The PO receive endpoint (`purchase_orders.py` lines 238–241) includes a comment explicitly avoiding expense record creation to prevent double-counting. However, this is a convention, not a database constraint. If any PO cost also exists as an expense record (e.g., manual entry, older data), both will be counted. The dashboard's `duplicate_expense_warning` check (lines 501–542) detects and warns about this in the API response but does not prevent or correct it. Users who don't surface this warning field would see silently inflated expenses.

**VAT position (lines 496–499)**  
⚠️ **MEDIUM — Draft invoices inflate output VAT:**  
```python
all_invoices_vat = db.query(Invoice).filter(Invoice.company_id == cid).all()
output_vat = round(sum(i.vat_amount or 0 for i in all_invoices_vat), 2)
```
This queries **all** invoices regardless of status, including `draft` invoices. Draft invoices have not been issued to clients and should not create a VAT output liability. If a company has draft invoices with VAT amounts recorded, `output_vat` and `net_vat_payable` on the dashboard will be overstated. The same issue exists in the reconciliation VAT check at `payroll.py` lines 778–782. The VAT201 report (`/reports/vat201`) correctly filters by `issue_date`, so the formal return is accurate — but the dashboard KPI and reconciliation check are misleading.

**Depreciation (lines 467–471)**  
✅ All-time `DepreciationEntry.amount` summed and added to `total_expenses`. Consistent with IAS 16 treatment.

### `/reports/management` — `payroll.py` lines 1056–1227

✅ Revenue: filters `status == InvoiceStatus.paid` with `paid_date` in range, applies `_to_zar()`.  
✅ Expenses: ex-VAT with `Expense.expense_date` in range.  
✅ PO COGS: received/partial/paid POs with `received_date` in range, ex-VAT.  
✅ Depreciation: `DepreciationEntry.period` range filter.  
✅ Payroll: sums `Payslip.total_cost` for all employees in range; falls back to estimate.  
✅ Trend loop (lines 1166–1197): applies `_to_zar()` consistently on each month's paid invoices.  
✅ Outstanding (lines 1159–1164): filters `sent` + `overdue`, applies `_to_zar()`.

### `/v1/summary` — `main.py` lines 249–291

✅ Imports and uses `_to_zar` from `payroll.py`.  
✅ `total_revenue`: paid invoices only via `_to_zar()`.  
✅ `outstanding`: sent + overdue via `_to_zar()`.  
✅ Expenses ex-VAT, PO COGS ex-VAT, depreciation, and payroll all included — consistent with `/reports/dashboard`.

---

## 3. Debtors (Accounts Receivable)

### Backend: `/reports/debtors-aging` — `payroll.py` lines 1340–1400

**Status filter (line 1349–1352)**  
✅ Correctly filters `status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])`. Draft and paid invoices excluded.

**ZAR equivalents (lines 1360–1364)**  
✅ Each invoice amount is `round(_to_zar(inv), 2)`. Foreign-currency invoices are converted at the stored `exchange_rate` (or `paid_amount_zar` if available). The `amount` field in each bucket entry is always ZAR.

**Aging buckets from `due_date` (lines 1356–1383)**  
✅ Aging is computed from `due_date` exclusively:
```python
due = inv.due_date
```
Invoices with `due_date = None` are placed in the `not_due` bucket (lines 1368–1370). The comment at line 1358 explicitly notes this is an audit fix: "removed issue_date/created_at fallback". Aging is calculated as `(now - due).days` with negative values (future due dates) going to `not_due`.

**Paid invoices excluded**  
✅ Only `sent` and `overdue` statuses are queried — paid invoices cannot appear.

### Frontend: `App_js_fixed.js` lines 4671–4793

✅ Calls `/reports/debtors-aging` on mount and on `live.invoices` change.  
✅ Displays `inv.amount` which is the ZAR-equivalent value set by the backend. Column header "Amount (ZAR)" is accurate.  
✅ Bucket labels ("Not Yet Due", "0–30 Days", "31–60 Days", "61–90 Days", "90+ Days") correctly match backend bucket keys.

**Low-severity note:** Frontend dashboard drill-down for "outstanding" (App_js_fixed.js line 523) filters `["pending","sent","overdue"]`. There is no `pending` status in the backend — `sent` is the pending status. The "pending" string in the client-side filter is a dead filter entry (no invoice will ever have `status: "pending"` from the API) but it is harmless and does not suppress any invoices. Low severity.

---

## 4. Creditors (Accounts Payable)

### Backend: `/reports/creditors-aging` — `payroll.py` lines 1403–1547

**PO filter (lines 1419–1422)**  
✅ Filters `status.in_(["received", "partial"])`. Status `"paid"` is explicitly excluded — fully paid POs do not appear in the creditors book.

**Received-but-unpaid POs**  
✅ All POs with status `received` or `partial` are included. These represent goods/services delivered but supplier not yet paid.

**On-credit expenses (lines 1482–1529)**  
✅ Unpaid on-credit expenses (`is_on_credit == True`, `paid_at == None`) are included as AP liabilities. This is correct — these create an AP entry in the journal (`post_expense` credits account 2000 when `is_on_credit=True`).

**Supplier bank details decryption (lines 1456–1460)**  
✅ `decrypt_field()` from `crypto.py` is called for `bank_name`, `account_number`, and `branch_code` before they are placed in the response. Plain-text fields are never exposed.

**Aging base date fallback (line 1442)**  
```python
base_date = po.received_date or po.order_date or po.created_at
```
⚠️ **Low severity:** If `received_date` is NULL and `order_date` predates delivery, aging from `order_date` would overstate how long the creditor has been outstanding. In practice, the startup backfill in `main.py` (lines 57–72) sets `received_date = created_at` for all POs with status `received/partial/paid` where `received_date` is NULL. For new POs, `purchase_orders.py` line 236 sets `received_date = datetime.utcnow()` at receipt time. Risk is low but a `partial` PO that was never fully received might still hit the fallback in edge cases.

### Frontend: `App_js_fixed.js` lines 4795–4935

✅ Calls `/reports/creditors-aging` on mount and on `live.purchaseOrders` change.  
✅ Displays `exp.amount` which is `po.total_amount` (VAT-inclusive) from the backend. Column header "Amount (incl. VAT)" is accurate.  
✅ Bucket filter works correctly via `bucketFilter` state.

**Low-severity note:** The Creditors view refreshes when `live.purchaseOrders` changes but NOT when an on-credit expense is marked as paid (which would remove it from the AP list). A user who pays a credit expense would need to manually refresh to see it removed from the creditors book.

---

## 5. Cross-Module Journal Coverage

| Transaction Type | Posting Function | Called From | Status |
|-----------------|-----------------|-------------|--------|
| Invoice raised | `post_invoice_raised` | `companies.py` line 228 | ✅ |
| Invoice paid | `post_invoice_paid` | `companies.py` line 275 | ✅ |
| Invoice COGS | `post_invoice_cogs` | `companies.py` line 231 | ✅ (when cogs_amount provided) |
| Invoice deleted | `reverse_journal_entries` (3 sources) | `companies.py` line 301 | ✅ |
| Expense incurred (cash + credit) | `post_expense` | `companies.py` line 421 | ✅ |
| On-credit expense paid | `post_expense_paid` | `companies.py` (pay endpoint) | ✅ |
| PO received | `post_po_received` | `purchase_orders.py` line 249 | ✅ |
| PO paid | `post_po_paid` | `purchase_orders.py` line 314 | ✅ |
| PO deleted | `reverse_journal_entries` (2 sources) | `purchase_orders.py` line 189 | ✅ |
| Payroll run | `post_payroll` | `payroll.py` line 336 | ✅ |
| Fixed asset acquisition | `post_asset_acquisition` | `fixed_assets.py` (via backfill/live) | ✅ |
| Depreciation | `post_depreciation` | `fixed_assets.py` (via backfill/live) | ✅ |
| Asset disposal | `post_asset_disposal` | `fixed_assets.py` (via backfill/live) | ✅ |
| Stock adjustment | `post_stock_adjustment` | `inventory.py` | ✅ |

**All major transaction types produce journal entries.**

**Balance sheet control account reconciliation:**
- AR Control (1100) vs outstanding invoices: checked in `/reports/reconciliation` Rule 6 (`payroll.py` lines 834–854). Uses `_to_zar()` consistently. ✅
- AP Control (2000) vs open POs + unpaid credit expenses: checked in Rule 7 (lines 857–890). AP total uses `po.total_amount` (VAT-inclusive), which matches `post_po_received` which credits `total_amount` to account 2000. ✅

**No missing journal event types identified.**

---

## 6. Action Items

### Critical
_None identified._

### High
_None identified._

### Medium

**M1 — Dashboard output VAT includes draft invoices**  
`payroll.py` lines 496–499 and 778–782.  
Query `all_invoices_vat` filters on `Invoice.company_id == cid` only, with no status filter. Draft invoices inflate `output_vat` and `net_vat_payable` on the dashboard and the reconciliation VAT control check.  
**Fix:** Add `Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue, InvoiceStatus.paid])` to the `all_invoices_vat` query. Apply the same fix to the reconciliation check.

**M2 — PO/expense double-count advisory-only**  
`payroll.py` lines 457–465 and 500–542.  
Dashboard adds both `total_expenses` (expenses table) and `po_cogs` (purchase_orders table). Detection logic warns via `po_duplicate_warning` in the API response but this field is not surfaced in the frontend. If a PO cost is also entered as an expense record (historical data, manual entry), it will be silently double-counted in all P&L views.  
**Fix (short-term):** Surface the `po_duplicate_warning` field visibly in the frontend's dashboard or management reports view. **Fix (long-term):** Add a DB-level guard: set `purchase_order_id` FK on the `expenses` table and reject duplicate expense records that reference a PO already received.

### Low

**L1 — Frontend "pending" status in outstanding filter is dead code**  
`App_js_fixed.js` line 523: `["pending","sent","overdue"]`.  
No invoice will ever have `status: "pending"` from the backend API (the status enum has no such value). This is cosmetic but could mislead future developers.  
**Fix:** Remove `"pending"` from the array.

**L2 — Creditors view does not refresh on on-credit expense payment**  
`App_js_fixed.js` lines 4807–4811: refresh only fires on `live.purchaseOrders`, not on credit expense payment.  
**Fix:** Add `live.expenses` to the Creditors `useEffect` dependency and refresh `creditors-aging` when it changes.

---

_Report generated automatically on 2026-06-30 by scheduled audit task `zuzan-reports-audit`._
