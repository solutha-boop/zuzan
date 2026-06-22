# ZuZan Reports / Debtors / Creditors Audit
**Date:** 2026-06-20  
**Audited by:** Automated scheduled task  
**Scope:** Reports (dashboard, management), Debtors (AR aging), Creditors (AP aging), Cross-module journal consistency

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports — `/reports/dashboard` | ⚠️ ISSUE: PO COGS added VAT-inclusive — overstates expenses by 15% |
| Reports — `/reports/management` | ⚠️ ISSUE: Same PO COGS VAT inconsistency |
| Reports — `/reports/monthly-trend` | ⚠️ ISSUE: Same PO COGS VAT inconsistency |
| Reports — `/reports/provisional-tax` | ⚠️ ISSUE: Same PO COGS VAT inconsistency |
| Reports — `/v1/summary` | ✓ No issues |
| Debtors (AR Aging) | ✓ No critical issues; one minor frontend drill-down discrepancy |
| Creditors (AP Aging) | ✓ No issues |
| Cross-module journal coverage | ⚠️ ISSUE: Invoice and expense creation use warn-only on journal failure |
| Balance sheet AR/AP reconciliation | Depends on journal completeness (see cross-module) |

---

## 2. Reports

### 2.1 `/reports/dashboard` — `payroll.py` lines 258–324

**`total_revenue`** — `payroll.py:271`
```python
total_revenue = sum(_to_zar(i) for i in paid_invoices)
```
✓ Correctly applies `_to_zar()`. Only sums `InvoiceStatus.paid` invoices. Expenses excluded.

**`total_outstanding`** — `payroll.py:277`
```python
total_outstanding = sum(_to_zar(i) for i in outstanding_invoices)
```
✓ Correctly applies `_to_zar()`. Filters to `sent` + `overdue` status only.

**Expenses (ex-VAT)** — `payroll.py:283`
```python
total_expenses = sum(e.amount - (e.vat_amount or 0) for e in expenses)
```
✓ Correctly uses VAT-exclusive amounts for P&L.

**Payroll costs** — `payroll.py:300–306`
```python
actual_payslips_total = db.query(func.sum(Payslip.total_cost)) ...
```
✓ Uses actual all-time payslip totals (`total_cost` = gross + employer UIF + SDL) where available, falls back to current-month estimate. Correctly included in expenses.

**🔴 CRITICAL — PO COGS VAT inconsistency** — `payroll.py:286–293`
```python
po_cogs = sum(
    po.total_amount or 0
    for po in db.query(PurchaseOrder).filter(
        PurchaseOrder.status.in_(["received", "partial", "paid"]),
    ).all()
)
total_expenses = total_expenses + po_cogs
```
`po.total_amount` is computed as `subtotal + vat` in `purchase_orders.py:44`. This means PO COGS are added **VAT-inclusive** while all other expenses are **VAT-exclusive** (`e.amount - e.vat_amount`). For any VAT-applicable PO, COGS is overstated by 15%.

**Fix required:** Replace `po.total_amount` with `(po.total_amount or 0) - (po.vat_amount or 0)` (i.e., `po.subtotal`).

Same defect exists in:
- `/reports/management` — `payroll.py:801`
- `/reports/monthly-trend` — `payroll.py:369–376`
- `/reports/provisional-tax` — `payroll.py:927–935`

All four endpoints must be corrected together.

### 2.2 `/reports/management` — `payroll.py` lines 767–889

**Revenue trend loop** — `payroll.py:847`
```python
rev = round(sum(_to_zar(inv) for inv in db.query(Invoice)...paid...), 2)
```
✓ `_to_zar()` applied consistently in every iteration.

Expenses ex-VAT, payroll from actual payslips — ✓ consistent with dashboard.

🔴 PO COGS `po.total_amount` VAT-inclusive — same issue as above (`payroll.py:854–860`).

### 2.3 `/v1/summary` — `main.py` lines 210–231

```python
total_revenue  = sum(_to_zar(i) for i in paid_invs)
total_expenses = sum(e.amount - (e.vat_amount or 0) for e in exp_rows)
po_cogs = sum(po.total_amount or 0 ...)
total_expenses = total_expenses + po_cogs
```
Revenue and outstanding ✓ use `_to_zar()`. Expenses ✓ ex-VAT.

🔴 Same PO COGS VAT issue at `main.py:222–229`.

### 2.4 Frontend dashboard expense drill-down — `App_js_fixed.js` lines 396–401

```js
total: rows.reduce((s,e) => s + (e.amount||0), 0),
```
⚠️ `Expense.amount` is stored **VAT-inclusive** (`exp_total = data.amount + exp_vat`, `companies.py:272–273`) but the backend dashboard KPI uses VAT-exclusive (`e.amount - e.vat_amount`). The drill-down total will therefore be ~15% higher than the dashboard KPI card it is expanding, causing user-visible discrepancy.

**Fix required:** Frontend should subtract VAT: `rows.reduce((s,e) => s + ((e.amount||0) - (e.vat_amount||0)), 0)`.

---

## 3. Debtors (Accounts Receivable)

### 3.1 Backend — `payroll.py` lines 992–1045 (`/reports/debtors-aging`)

**Status filter** — `payroll.py:1001–1004`
```python
outstanding = db.query(Invoice).filter(
    Invoice.company_id == cid,
    Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])
).all()
```
✓ `InvoiceStatus` enum (`database.py:36–40`) only defines `draft`, `sent`, `paid`, `overdue`. No `pending` status exists in the DB. The filter correctly excludes `draft` and `paid`. 

Note: The frontend dashboard drill-down (`App_js_fixed.js:404`) filters by `["pending","sent","overdue"]` including "pending" which is not a valid backend status — this is harmless (no records will ever match "pending") but is dead code.

**ZAR conversion** — `payroll.py:1014`
```python
"amount": round(_to_zar(inv), 2),
```
✓ ZAR equivalents displayed, not raw foreign-currency amounts.

**Aging buckets from `due_date`** — `payroll.py:1009`
```python
due = inv.due_date or inv.issue_date or inv.created_at
days_overdue = (now - due).days if due else 0
```
✓ Ages from `due_date`, with sensible fallbacks. Invoices where `due_date` is in the future land in `not_due` bucket (days_overdue < 0).

**Paid invoices excluded** — ✓ query filters to `sent/overdue` only.

### 3.2 Frontend — `App_js_fixed.js` lines 3539–3655

✓ Calls `/reports/debtors-aging`. Displays ZAR amounts (sourced from backend). Bucket labels and aging summary table correct.

Minor cosmetic note: the "Amount" column header does not explicitly say "ZAR" — low priority.

---

## 4. Creditors (Accounts Payable)

### 4.1 Backend — `payroll.py` lines 1048–1142 (`/reports/creditors-aging`)

**Data source** — `payroll.py:1063–1067`
```python
open_pos = db.query(PurchaseOrder).filter(
    PurchaseOrder.company_id == cid,
    PurchaseOrder.status.in_(["received", "partial"]),
)
```
✓ Pulls from `purchase_orders` table. Status `"paid"` is excluded — fully paid POs do not appear.

**Received-but-unpaid POs** — ✓ `"received"` and `"partial"` statuses correctly represent outstanding obligations.

**Aging from due date** — `payroll.py:1087–1089`
```python
base_date = po.received_date or po.order_date or po.created_at
due_date = base_date + timedelta(days=payment_terms) if base_date else None
days_overdue = (now - due_date).days if due_date else 0
```
✓ Ages correctly from delivery date + supplier payment terms.

**Supplier bank details decryption** — `payroll.py:1102–1105`
```python
"bank_name":      decrypt_field(sup.bank_name)      if sup else None,
"account_number": decrypt_field(sup.account_number) if sup else None,
"branch_code":    decrypt_field(sup.branch_code)    if sup else None,
```
✓ `decrypt_field` from `crypto.py` is called before returning bank details. The startup migration in `main.py:39–74` also encrypts any plain-text fields on boot.

**Note on VAT in AP amounts:** Creditors aging shows `po.total_amount` (VAT-inclusive). This is **correct for AP** — the company owes the supplier the full VAT-inclusive invoice amount. This is intentionally different from the P&L treatment (where input VAT is recoverable). No issue here.

### 4.2 Frontend — `App_js_fixed.js` lines 3658–3811

✓ Calls `/reports/creditors-aging`. Vendor grouping, bucket filtering, and per-PO detail all correctly render backend data. Expanded view shows bank details (sourced from backend, already decrypted).

Minor: `useEffect` at line 3672 uses `[live.expenses]` as dependency but the comment says `live.reload`. Functionally harmless but unclear intent.

---

## 5. Cross-Module Journal Coverage

| Event | Posting function | Triggered from | Status |
|---|---|---|---|
| Invoice raised | `post_invoice_raised` | `companies.py:203` | ⚠️ Warn-only on failure |
| Invoice paid | `post_invoice_paid` | `companies.py:229` | ⚠️ Warn-only on failure |
| Expense paid | `post_expense` | `companies.py:287` | ⚠️ Warn-only on failure |
| Payroll run | `post_payroll` | `payroll.py:211` | ✓ Hard rollback on failure |
| PO received | `post_po_received` | `purchase_orders.py:226` | ✓ Hard rollback on failure |
| PO paid | `post_po_paid` | `purchase_orders.py:265` | ✓ Hard rollback on failure |
| Stock adjustment | `post_stock_adjustment` | inventory module | ✓ |
| Fixed asset acquisition | `post_asset_acquisition` | fixed_assets module | ✓ |
| Depreciation | `post_depreciation` | fixed_assets module | ✓ |
| Asset disposal | `post_asset_disposal` | fixed_assets module | ✓ |

**🟡 HIGH — Inconsistent journal failure handling:**  
Invoice creation (`companies.py:207`) and invoice payment (`companies.py:232`) and expense creation (`companies.py:290`) all use `logger.warning()` on journal post failure and allow the transaction to succeed without a journal entry. Payroll and PO operations use hard rollbacks. 

This means invoices and expenses can silently exist without matching journal entries, causing AR control (1100) and expense accounts to be understated in the trial balance and balance sheet. The AR/AP reconciliation checks in `/reports/reconciliation` (payroll.py lines 573–612) will flag these mismatches with a "diff" message, but the root cause is the soft-failure mode.

**Fix required:** Invoice and expense endpoints should either hard-rollback on journal failure (preferred, matching payroll/PO behavior) or clearly mark the record as "journal pending" for retry.

**Balance sheet accounts:** 
- AR control (1100) reconciles against outstanding invoice totals in `/reports/reconciliation` — ✓ check exists.
- AP control (2000) reconciles against open PO totals — ✓ check exists.
- However, if journal entries are missing (due to warn-only failures above), these checks will produce `fail` results at runtime.

---

## 6. Action Items (by Severity)

### 🔴 Critical

1. **PO COGS VAT inconsistency in all P&L endpoints** — `payroll.py` lines 287, 369, 801, 854; `main.py` line 222.  
   Replace `po.total_amount` with `(po.total_amount or 0) - (po.vat_amount or 0)` (i.e., use `po.subtotal`) everywhere PO COGS is added to VAT-exclusive expenses. Affects `/reports/dashboard`, `/reports/management`, `/reports/monthly-trend`, `/reports/provisional-tax`, and `/v1/summary`. This overstates COGS by 15% on all VAT-applicable purchase orders.

### 🟡 High

2. **Inconsistent journal failure handling for invoices and expenses** — `companies.py` lines 207, 232, 290.  
   Change invoice creation, invoice payment, and expense creation to hard-rollback (raise HTTPException) on journal post failure, consistent with payroll and PO behavior. Currently, these can succeed without a corresponding journal entry, causing silent balance sheet errors.

### 🟠 Medium

3. **Frontend expense drill-down total uses VAT-inclusive amount** — `App_js_fixed.js` line 400.  
   The dashboard "Expenses" KPI expands to a drill-down whose total sums `e.amount` (VAT-inclusive stored value). The KPI itself is VAT-exclusive. Fix: subtract `e.vat_amount` in the drill-down total.

### 🔵 Low

4. **Frontend references "pending" invoice status** — `App_js_fixed.js` line 404.  
   The outstanding invoice filter includes `"pending"` but `InvoiceStatus` enum has no such value (`database.py:36–40`). Dead code — remove to avoid confusion.

5. **Creditors `useEffect` dependency comment mismatch** — `App_js_fixed.js` line 3672.  
   Dependency array is `[live.expenses]` but the guarding condition checks `live.reload`. Clarify intent.

6. **Debtors amount column missing "ZAR" label** — `App_js_fixed.js` line 3601.  
   Column header says "Amount" with no currency indicator. Since foreign-currency invoices are converted, label should read "Amount (ZAR)" for clarity.
