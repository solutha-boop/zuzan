# ZuZan Audit Report — Reports, Debtors & Creditors
**Date:** 2026-06-26
**Scope:** `/reports/dashboard`, `/reports/management`, `/reports/debtors-aging`, `/reports/creditors-aging`, `/v1/summary`, frontend `Debtors` and `Creditors` components
**Files reviewed:** `payroll.py`, `journal.py`, `purchase_orders.py`, `companies.py`, `main.py`, `database.py`, `App_js_fixed.js`

---

## 1. Summary

| Section | Verdict |
|---------|---------|
| Reports — dashboard & management | ⚠️ One medium issue (payroll cost understated when headcount changed) |
| Debtors (AR) | ✅ Pass — data, ZAR conversion, aging, and filtering all correct |
| Creditors (AP) | ✅ Pass — correct filtering, bank details decrypted, aging correct |
| Cross-module journal coverage | ✅ Pass — all event types covered |

---

## 2. Reports

### `/reports/dashboard` (payroll.py line 430)

**total_revenue** (line 443):
```python
paid_invoices = db.query(Invoice).filter(..., Invoice.status == InvoiceStatus.paid)
total_revenue = sum(_to_zar(i) for i in paid_invoices)
```
✓ Only paid invoices. `_to_zar()` applied consistently — for non-ZAR invoices uses `paid_amount_zar` if set, otherwise `total_amount × exchange_rate`.

**total_outstanding** (line 445–449):
```python
Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])
total_outstanding = sum(_to_zar(i) for i in outstanding_invoices)
```
✓ Filters `sent` + `overdue`. Note: the `InvoiceStatus` enum (database.py line 36) has **no `pending` value** — only `draft`, `sent`, `paid`, `overdue`. The audit checklist reference to `pending` is moot; the filter is correct as-is.

**Expenses from revenue** (line 451–455):
✓ Expenses are summed separately (`total_expenses`). Revenue sums only paid invoices. No mixing.

**PO COGS** (line 457–465):
✓ Statuses `received`, `partial`, `paid` included. Ex-VAT treatment: `(po.total_amount or 0) - (po.vat_amount or 0)`. Double-count detection warning exists.

**Payroll costs** — ⚠️ **ISSUE** (lines 473–484):
```python
employees = db.query(Employee).filter(
    Employee.company_id == cid,
    Employee.is_active == True          # ← only active employees
).all()
actual_payslips_total = db.query(func.sum(Payslip.total_cost)).filter(
    Payslip.employee_id.in_([e.id for e in employees])  # ← only their payslips
).scalar()
```
**Terminated employees' payslips are excluded from the historical total.** If any employee left during the period, their `Payslip.total_cost` records are in the DB but silently dropped from `actual_payslips_total`, causing `net_profit` to be overstated for historical periods.

The fallback estimate (line 484) also only covers active employees — same gap.

**Depreciation** (line 468–471): ✓ All-time `DepreciationEntry.amount` summed via `func.sum`.

---

### `/reports/management` (payroll.py line 1015)

**Revenue** (line 1050): ✓ `_to_zar()` applied. Filtered to `paid` invoices within date range.

**Expenses** (line 1057–1058): ✓ Ex-VAT (`e.amount - (e.vat_amount or 0)`).

**PO COGS** (line 1065–1077): ✓ Ex-VAT. Filtered to `received_date` within range.

**Payroll cost** (lines 1089–1102): ⚠️ **Same terminated-employee gap as dashboard.** Active employees only (`Employee.is_active == True`), then payslips filtered by their IDs.

**Revenue trend loop** (lines 1119–1149): ✓ `_to_zar()` applied on each monthly bucket.

---

### `/v1/summary` (main.py line 245)

✓ Imports `_to_zar` from `payroll.py`. Uses it for both `paid_invs` (revenue) and `out_invs` (outstanding). Expenses ex-VAT. PO COGS included. Payroll via payslips.

⚠️ Same terminated-employee gap: `active_emps = db.query(Employee).filter(... Employee.is_active == True)`.

---

## 3. Debtors (Accounts Receivable)

**Backend:** `reports_router.get("/debtors-aging")` — payroll.py line 1292
**Frontend:** `function Debtors({live = {}})` — App_js_fixed.js line 4665

**Data source** (payroll.py line 1301–1304):
```python
outstanding = db.query(Invoice).filter(
    Invoice.company_id == cid,
    Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])
)
```
✓ Correct. No `draft` or `paid` invoices included.

**ZAR conversion** (payroll.py line 1315):
```python
"amount": round(_to_zar(inv), 2)
```
✓ Foreign-currency invoices converted to ZAR before display. Frontend reads `inv.amount` directly from this response — no second conversion needed.

**Aging from `due_date`** (payroll.py lines 1308–1335):
```python
due = inv.due_date
# ... only due_date used; no fallback to issue_date or created_at
if due is None:
    buckets["not_due"].append(entry)   # explicit null bucket, not overstated
```
✓ Correct. Prior fallback to `issue_date` was removed (comment at line 1309 confirms the audit fix).

**Paid invoices excluded**: ✓ — filtered out at query time.

**Bucket keys** match frontend exactly: `not_due`, `current`, `31_60`, `61_90`, `over_90`. ✓

---

## 4. Creditors (Accounts Payable)

**Backend:** `reports_router.get("/creditors-aging")` — payroll.py line 1355
**Frontend:** `function Creditors({live = {}})` — App_js_fixed.js line 4784

**Data source** (payroll.py line 1371–1374):
```python
open_pos = db.query(PurchaseOrder).filter(
    PurchaseOrder.company_id == cid,
    PurchaseOrder.status.in_(["received", "partial"]),
)
```
✓ Only received-but-unpaid POs. Status `paid` is correctly excluded.

**Received-but-unpaid POs as creditors**: ✓ `received` and `partial` statuses are included.

**Fully paid POs excluded**: ✓ `paid` status is absent from the filter.

**Aging calculation** (payroll.py lines 1393–1403):
```python
base_date = po.received_date or po.order_date or po.created_at
due_date = base_date + timedelta(days=payment_terms) if base_date else None
days_overdue = (now - due_date).days if due_date else 0
```
✓ Aged from received_date + payment_terms days. Fallback to `order_date` then `created_at` for legacy POs that lack `received_date` (startup backfill in main.py lines 52–72 already fills most of these).

**Supplier bank details** (payroll.py lines 1407–1415):
```python
"bank_name":     decrypt_field(sup.bank_name)      if sup else None,
"account_number":decrypt_field(sup.account_number) if sup else None,
"branch_code":   decrypt_field(sup.branch_code)    if sup else None,
```
✓ All encrypted bank fields are decrypted via `crypto.decrypt_field` before being returned. The `if sup else None` guard handles anonymous POs (no `supplier_id`).

**Amount displayed** (payroll.py line 1420):
```python
"amount": round(po.total_amount or 0, 2)
```
VAT-inclusive amount. The frontend column header correctly reads "Amount (incl. VAT)" (App_js_fixed.js line 4894). ✓

---

## 5. Cross-module Journal Coverage

| Event | Posting function | Called from | Status |
|-------|-----------------|-------------|--------|
| Invoice raised | `post_invoice_raised` | companies.py:209 | ✅ |
| Invoice paid | `post_invoice_paid` | companies.py:245 | ✅ |
| COGS on invoice | `post_invoice_cogs` | companies.py:212 | ✅ |
| Expense recorded | `post_expense` | companies.py:328,412,643 | ✅ |
| PO received | `post_po_received` | purchase_orders.py:249 | ✅ |
| PO paid | `post_po_paid` | purchase_orders.py:313 | ✅ |
| Payroll run | `post_payroll` | payroll.py:336 | ✅ |
| Fixed asset acquisition | `post_asset_acquisition` | fixed_assets router | ✅ |
| Depreciation charge | `post_depreciation` | fixed_assets router | ✅ |
| Asset disposal | `post_asset_disposal` | fixed_assets router | ✅ |

**No coverage gaps found.** Backfill (`/journal/backfill`) covers all historical records and is idempotent.

**Balance sheet accounts:**

- AR control account (1100) reconciled against outstanding invoices in `/reports/reconciliation` (payroll.py lines 825–841). Difference flagged if > R1.00. ✓
- AP control account (2000) reconciled against open PO totals in `/reports/reconciliation` (payroll.py lines 843–860). Difference flagged if > R1.00. ✓

---

## 6. Action Items

### HIGH

*(No critical-severity issues found. No data loss or misreporting path exists that would silently corrupt totals without detection.)*

### MEDIUM

**1. Payroll cost understated for historical periods when headcount changed**
- **Files:** `payroll.py` lines 473, 1089 (dashboard and management)
- **Root cause:** Query for payslip totals uses `Employee.is_active == True`, so terminated employees' payslip records are excluded.
- **Impact:** `net_profit`, `gross_profit`, `ebit`, and `tax_provision` are overstated in any period where employees have since left.
- **Fix:** Replace the active-employee filter with a direct payslip query joined on company:
  ```python
  # Instead of: db.query(func.sum(Payslip.total_cost)).filter(
  #                 Payslip.employee_id.in_([e.id for e in employees]))
  # Use:
  from database import Employee as _Emp
  total_payroll = db.query(func.sum(Payslip.total_cost))\
      .join(_Emp, Payslip.employee_id == _Emp.id)\
      .filter(_Emp.company_id == cid)\
      .scalar() or 0
  ```
  Apply the same fix to `/reports/management` (period-filtered) and `/v1/summary`.

### LOW

**2. `pending` status reference in internal documentation / audit checklists is outdated**
- `InvoiceStatus` enum (database.py line 36) contains: `draft`, `sent`, `paid`, `overdue`. There is no `pending` value.
- Any documentation, client-facing help text, or checklist that references a `pending` invoice status should be updated to use `sent` or `draft` as appropriate.
- No code change required.

**3. Cash-flow statement (`/reports/cash-flow`) includes VAT in cash payments — clarify documentation**
- `cash_paid_to_suppliers` uses `e.amount` (VAT-inclusive, payroll.py line 932). This is technically correct for a cash-flow statement (cash out equals the full VAT-inclusive payment), but the management P&L uses ex-VAT expenses. A note clarifying the intentional difference would help users who compare the two reports.
- No code change required; documentation/comment clarification recommended.
