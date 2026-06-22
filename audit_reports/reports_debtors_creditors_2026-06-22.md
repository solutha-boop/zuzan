# ZuZan Audit Report — Reports, Debtors & Creditors
**Date:** 2026-06-22  
**Scope:** `payroll.py` (reports), `companies.py`, `purchase_orders.py`, `journal.py`, `main.py`, `App_js_fixed.js`

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports — `/reports/dashboard` | ⚠️ PASS WITH WARNINGS — PO partial-receipt COGS overstated; management endpoint missing date upper-bound |
| Reports — `/reports/management` | ⚠️ PASS WITH WARNINGS — same PO partial-receipt issue; no upper date bound on PO COGS query |
| Reports — `/v1/summary` (public API) | ✓ PASS |
| Debtors (AR) | ❌ FAIL — Multi-currency AR journal posting records foreign amounts on AR account then clears at ZAR; AR control reconciliation will report false failures for any non-ZAR invoice |
| Creditors (AP) | ✓ PASS |
| Cross-module journal coverage | ✓ PASS — all six transaction types covered |

---

## 2. Reports

### `/reports/dashboard` — `payroll.py:310`

**`total_revenue` (line 319–323)**
```python
paid_invoices = db.query(Invoice).filter(
    Invoice.company_id == cid,
    Invoice.status == InvoiceStatus.paid,
).all()
total_revenue = sum(_to_zar(i) for i in paid_invoices)
```
✓ Correctly sums only paid invoices. `_to_zar()` at line 17–24 correctly returns `paid_amount_zar` for foreign-currency paid invoices, falling back to `total_amount × exchange_rate`, and returns `total_amount` as-is for ZAR. No issue.

**`total_outstanding` (line 325–329)**
```python
outstanding_invoices = db.query(Invoice).filter(
    Invoice.company_id == cid,
    Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])
).all()
```
✓ Covers all outstanding invoices (sent = awaiting payment, overdue = past due). `InvoiceStatus` enum has no `pending` value — the audit checklist used "pending" loosely; the enum is `draft/sent/paid/overdue`, so `sent` is the correct analogue. `_to_zar()` applied. No issue.

**Expenses excluded from revenue** ✓  
Expenses are summed separately at line 334–335. No cross-contamination with revenue.

**Payroll costs (line 347–358)**  
✓ Dashboard uses sum of all historical payslips (`Payslip.total_cost`) as primary; falls back to current-month calculated estimate only when no payslips exist. Correct all-time treatment.

**PO COGS — partial receipt overstates costs (line 337–344)** ⚠️ Medium
```python
po_cogs = sum(
    (po.total_amount or 0) - (po.vat_amount or 0)
    for po in db.query(PurchaseOrder).filter(
        PurchaseOrder.status.in_(["received", "partial", "paid"]),
    ).all()
)
```
POs with status `"partial"` (goods partially received) are included at the full `po.total_amount` rather than the amount actually received. If a R100 000 PO has 50% delivered, expenses are overstated by R50 000. The database model has no `received_amount` field to solve this cleanly.

**Duplicate-expense detection (line 371–387)**  
✓ Heuristic check warns if expense descriptions contain PO numbers. Fragile but present.

---

### `/reports/management` — `payroll.py:850`

**Revenue (line 859–864)** ✓ Uses `_to_zar()`, current month only, paid invoices. Correct.

**Expenses (line 866–871)** ✓ Ex-VAT treatment consistent with dashboard and monthly-trend.

**PO COGS — missing upper date bound (line 879–884)** ⚠️ Low
```python
po_cogs_items = db.query(PurchaseOrder).filter(
    PurchaseOrder.company_id == cid,
    PurchaseOrder.status.in_(["received", "partial", "paid"]),
    PurchaseOrder.received_date >= month_start,   # ← no upper bound
).all()
```
The monthly-trend endpoint (line 458–462) correctly bounds both sides:
```python
PurchaseOrder.received_date >= start,
PurchaseOrder.received_date < end,
```
Without `received_date < next_month_start`, any PO with a future `received_date` set by mistake would appear in the current-month management accounts. Low probability in practice, but inconsistent.

**Revenue trend loop (line 921–944)** ✓ Both `_to_zar(inv)` and ex-VAT expense calculation applied consistently across all six loop iterations.

**Payroll (line 896–904)** ✓ Uses actual payslips for the period when run, falls back to estimates.

---

### `/v1/summary` — `main.py:210`

✓ `_to_zar()` imported from payroll and applied to both `paid_invs` and `out_invs`. PO COGS included ex-VAT. Consistent with dashboard. The same partial-receipt COGS issue applies here but is a downstream consequence of the Medium item above.

---

### Reconciliation comment numbering — `payroll.py:697 and 717` ⚠️ Low (cosmetic)
Two reconciliation rules are both labeled `# ── RULE 7 ──` in comments. The second should be Rule 8 or Rule 9 depending on intent. Does not affect runtime behaviour.

---

## 3. Debtors (Accounts Receivable)

### Backend — `payroll.py:1075` (`/reports/debtors-aging`)

**Invoice filter (line 1084–1087)** ✓
```python
outstanding = db.query(Invoice).filter(
    Invoice.company_id == cid,
    Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])
).all()
```
Paid and draft invoices excluded. Correct.

**ZAR equivalents (line 1098)** ✓  
`_to_zar(inv)` applied to each invoice entry. Foreign currency invoices converted at `total_amount × exchange_rate`.

**Aging from `due_date` (line 1093–1118)** ✓  
```python
due = inv.due_date
...
days_overdue = (now - due).days
```
Aging is calculated from `due_date`, not `issue_date`. Invoices with no `due_date` are placed in `not_due` bucket (correct — avoids falsely inflating overdue balances). The previous `created_at` fallback was removed per the inline comment.

**Paid invoices excluded** ✓ (status filter above).

---

### Critical Issue: Multi-currency AR journal posting ❌ Critical

**File:** `journal.py:160–184` (`post_invoice_raised`) and `journal.py:187–211` (`post_invoice_paid`)

`post_invoice_raised` records:
```python
lines.append(_line(entry.id, ar, debit=invoice.total_amount, ...))
```
For a USD invoice where `total_amount = 1000` (USD), the AR account 1100 is debited **1000 (USD-denominated)**.

`post_invoice_paid` clears AR with:
```python
zar_received = invoice.paid_amount_zar if invoice.paid_amount_zar else invoice.total_amount
lines = [
    _line(entry.id, bank, debit=zar_received,  ...),
    _line(entry.id, ar,   credit=zar_received, ...),
]
```
For the same invoice paid at R18 200 ZAR, AR is credited **18 200**.

**Net AR account balance for this invoice: 1 000 DR − 18 200 CR = −17 200 (permanently wrong)**

Consequences:
- Balance sheet AR figure (account 1100) is materially wrong for any company with non-ZAR invoices.
- AR control reconciliation check at `payroll.py:660–676` compares journal AR balance (mix of USD and ZAR amounts) against `_to_zar()` totals (all ZAR), and will always report a discrepancy for multi-currency companies.
- Trial balance will not balance when foreign-currency invoices exist.

**Fix required:** In `post_invoice_raised`, convert `invoice.total_amount` to ZAR before recording on AR:
```python
# Replace:
debit=invoice.total_amount
# With:
debit=(invoice.total_amount or 0) * (invoice.exchange_rate or 1.0) if (invoice.currency and invoice.currency != "ZAR") else (invoice.total_amount or 0)
```
Similarly ensure `post_invoice_raised` credits Revenue and VAT at ZAR-equivalent amounts for foreign currency invoices, or add a separate FX difference account.

---

### Frontend — `App_js_fixed.js:3997` (`Debtors` component)

✓ Calls `api("/reports/debtors-aging")` and renders `data.buckets` and `data.totals` directly from the backend — no frontend-side currency conversion or amount manipulation.  
✓ Displays amounts via `fmt()` which formats as ZAR.  
✓ Bucket labels (Not Yet Due / 0–30 / 31–60 / 61–90 / 90+) match backend bucket keys exactly.  
✓ `due_date` displayed from backend data (not recalculated in frontend).

---

## 4. Creditors (Accounts Payable)

### Backend — `payroll.py:1138` (`/reports/creditors-aging`)

**PO filter (line 1154–1157)** ✓
```python
open_pos = db.query(PurchaseOrder).filter(
    PurchaseOrder.company_id == cid,
    PurchaseOrder.status.in_(["received", "partial"]),
)
```
Status `"paid"` excluded. Only received-but-unpaid POs appear. Correct.

**Received-but-unpaid POs appear** ✓  
Both `"received"` (fully received, awaiting payment) and `"partial"` (partially received) are included.

**Fully paid POs excluded** ✓  
`"paid"` status is not in the filter. Draft, sent, and cancelled POs are also excluded.

**Supplier bank details decrypted (line 1192–1195)** ✓
```python
"bank_name":      decrypt_field(sup.bank_name)      if sup else None,
"account_number": decrypt_field(sup.account_number) if sup else None,
"branch_code":    decrypt_field(sup.branch_code)    if sup else None,
```
`decrypt_field` from `crypto.py` is called for all three encrypted fields. Decryption is conditional on `sup` existing (anonymous POs return `None` values safely).

**Aging from due date (line 1177–1186)** ✓  
Due date computed as `received_date + payment_terms_days`. Falls back to `order_date` then `created_at` if `received_date` is null. Supplier's `payment_terms` field used; defaults to 30 days when not set.

**VAT treatment** ✓  
Creditor ledger correctly shows `po.total_amount` (VAT-inclusive) — this is the amount owed to the supplier, which is the correct AP balance. The ex-VAT deduction is applied only in the P&L expense calculation, not in AP.

---

### Frontend — `App_js_fixed.js:4116` (`Creditors` component)

✓ Calls `api("/reports/creditors-aging")`, renders `data.vendors` and `data.totals` from backend.  
✓ Bucket filter, vendor grouping, and per-vendor subtotals all calculated client-side from the already-correct backend data.  
✓ `days_until_due` field displayed for not-yet-due items.  
✓ Bank details (bank_name, account_number, branch_code) are present in the vendor object but are **not rendered in the frontend** — the Creditors view shows PO reference, description, received date, due date, overdue badge, and amount only. Bank details are available in the API response for future use but currently not displayed in the UI. This is not a bug, but if payment initiation features are added, the decrypted fields are ready.

---

## 5. Cross-module Journal Coverage

| Transaction type | Posting function | Called from | Status |
|---|---|---|---|
| Invoice raised | `post_invoice_raised` | `companies.py:208–219` | ✓ |
| Invoice paid | `post_invoice_paid` | `companies.py:239–249` | ✓ |
| Invoice COGS (inventory) | `post_invoice_cogs` | `companies.py:211–213` | ✓ |
| Expense paid | `post_expense` | `companies.py:306–314`, `companies.py:590–592` | ✓ |
| PO received | `post_po_received` | `purchase_orders.py:225–233` | ✓ |
| PO paid | `post_po_paid` | `purchase_orders.py:290–298` | ✓ |
| Payroll run | `post_payroll` | `payroll.py:209–218` | ✓ |
| Stock adjustment | `post_stock_adjustment` | inventory module | ✓ |
| Fixed asset acquisition | `post_asset_acquisition` | fixed_assets module | ✓ |
| Depreciation | `post_depreciation` | fixed_assets module | ✓ |
| Startup backfill | `backfill_company` | `main.py:22–37` | ✓ |

All six transaction types required by the checklist have journal postings. The backfill on startup ensures companies with pre-existing data before journal was introduced are caught up.

**Balance sheet AR/AP reconciliation checks:**
- AR control (account 1100) reconciliation at `payroll.py:660–676` ❌ Fails for multi-currency companies (see Critical issue in Section 3).
- AP control (account 2000) reconciliation at `payroll.py:679–695` ✓ Journal AP balance vs raw PO total — both use VAT-inclusive `total_amount`, consistent.

---

## 6. Action Items

**Critical**

1. **Fix multi-currency AR journal posting** (`journal.py:177`, `post_invoice_raised`).  
   Record AR debit at ZAR equivalent, not at the raw foreign-currency `invoice.total_amount`. For non-ZAR invoices: `debit = (invoice.total_amount or 0) * (invoice.exchange_rate or 1.0)`. Also update Revenue and VAT credits to ZAR amounts. After fixing, run `/journal/backfill` to repair historical entries, or provide a targeted migration that reverses and re-posts affected invoice entries.

**Medium**

2. **PO partial-receipt COGS overstated** (`payroll.py:337–344`, `payroll.py:879–884`, `payroll.py:937–942`, `main.py:222–228`).  
   For POs with status `"partial"`, the dashboard, management accounts, and public API all use `po.total_amount` (the full PO value) instead of the amount actually received. Consider adding a `received_amount` column to PurchaseOrder, or computing it from a PO lines table. Until then, document this as a known limitation in user-facing reports.

**Low**

3. **Missing upper date bound in management PO COGS query** (`payroll.py:880`).  
   Add `PurchaseOrder.received_date < month_end` to match the existing monthly-trend endpoint logic and prevent edge-case inclusion of future-dated POs.

4. **Duplicate "Rule 7" comment label in reconciliation endpoint** (`payroll.py:697` and `payroll.py:717`).  
   Rename the second occurrence to "Rule 8: Inventory Valuation" and the third to "Rule 9: Gross Margin Health" for audit trail clarity. Cosmetic only.
