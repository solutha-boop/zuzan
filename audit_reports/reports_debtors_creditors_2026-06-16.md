# ZuZan Audit Report — Reports, Debtors & Creditors
**Date:** 2026-06-16  
**Scope:** `payroll.py` (reports), `main.py` (/v1/summary), `purchase_orders.py`, `journal.py`, `suppliers.py`, `database.py`, `App_js_fixed.js`

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports — `/reports/dashboard` | ✓ Pass (minor caveats noted) |
| Reports — `/reports/management` | ✓ Pass |
| Reports — `/reports/monthly-trend` | ✗ Fail — missing `_to_zar()` |
| Reports — `/reports/cash-flow` | ✗ Fail — missing `_to_zar()` |
| Reports — `/reports/reconciliation` | ⚠ Warn — partial `_to_zar()` gaps |
| Reports — `/reports/provisional-tax` | ⚠ Warn — missing `_to_zar()` |
| Reports — `/v1/summary` (public API) | ✗ Fail — outstanding includes draft invoices |
| Debtors (AR) | ✗ Fail — amounts not converted to ZAR |
| Creditors (AP) | ✗ Fail — queries Expense table instead of PurchaseOrder table |
| Cross-module Journal | ⚠ Warn — backfill gap for paid POs |

---

## 2. Reports

### 2.1 `/reports/dashboard` — `payroll.py:235`

- **total_revenue** (`payroll.py:249`): `sum(_to_zar(i) for i in paid_invoices)` — ✓ correct multi-currency conversion applied.
- **total_outstanding** (`payroll.py:255`): `sum(_to_zar(i) for i in outstanding_invoices)` — ✓ correct.
- Outstanding filter (`payroll.py:252`): `status.in_([sent, overdue])` — ✓ draft and paid excluded. Note: `InvoiceStatus` has no `pending` value; enum values are `draft`, `sent`, `paid`, `overdue`.
- Expenses (`payroll.py:261`): summed from `Expense` table only — see §2.6 for PO cost gap.
- Payroll costs (`payroll.py:267`): uses `calc_payroll()["total_cost"]` (gross + employer UIF + SDL) — ✓ correct.
- **No issues** in dashboard itself beyond PO cost gap (§2.6).

### 2.2 `/reports/management` — `payroll.py:673`

- Revenue (`payroll.py:687`): `sum(_to_zar(i) for i in paid_invoices)` — ✓ correct.
- Trend loop (`payroll.py:730`): `sum(_to_zar(inv) for inv in ...)` — ✓ correct, consistent with management accounts.
- Payroll cost (`payroll.py:704`): included in EBIT — ✓ correct.
- Expenses: same PO cost gap as dashboard (§2.6).

### 2.3 `/reports/monthly-trend` — `payroll.py:289` — ✗ FAIL

**Issue (High):** `payroll.py:312–313` uses `inv.total_amount` directly without `_to_zar()`:

```python
revenue = sum(
    inv.total_amount for inv in db.query(Invoice).filter(...)
)
```

For multi-currency invoices (e.g., USD), `total_amount` stores the foreign-currency value, not ZAR. This endpoint is separate from `/management` and does **not** apply `_to_zar()`, causing the trend chart to show incorrect figures for companies with foreign-currency invoices.

**Fix:** Replace with `sum(_to_zar(inv) for inv in ...)`.

### 2.4 `/reports/cash-flow` — `payroll.py:570` — ✗ FAIL

**Issue (High):** `payroll.py:584`:

```python
cash_receipts = round(sum(i.total_amount for i in paid_this_month), 2)
```

No `_to_zar()` applied. Foreign-currency receipts are counted at face value (e.g., USD 1000 instead of ZAR ~18,500).

**Fix:** `sum(_to_zar(i) for i in paid_this_month)`.

### 2.5 `/reports/reconciliation` — `payroll.py:419` — ⚠ WARN

Two sub-issues:

**a) 90-day debtors check (`payroll.py:450`):**
```python
amount_90 = round(sum(i.total_amount for i in overdue_90), 2)
```
No `_to_zar()`. Overdue foreign-currency invoice amounts are wrong in the warning detail.

**b) Gross margin health check (`payroll.py:542`):**
```python
total_rev = round(sum(i.amount for i in db.query(Invoice)...paid...), 2)
```
Uses `i.amount` (excl. VAT) instead of `i.total_amount`, AND no `_to_zar()`. Inconsistent with all other revenue calculations which use `total_amount`. This causes:
- Revenue understated by VAT component (15% for ZAR invoices)
- Further distorted for foreign-currency invoices

**Fix both:** use `sum(_to_zar(i) for i in ...)`.

### 2.6 PO Costs not feeding Expense Totals — `purchase_orders.py:221` — ⚠ WARN (Medium)

When a PO is received, `purchase_orders.py:221–224` explicitly sets `expense_id = None` and does NOT create an `Expense` record:

```python
# NOTE: We use the double-entry journal (post_po_received) as the single
# source of truth — DR Inventory / CR Accounts Payable.
# Creating a separate Expense record would double-count the cost, so we
# ignore data.create_expense here; the journal entry IS the cost record.
expense_id = None
```

This is intentionally correct from a double-entry standpoint. However, `/reports/dashboard` and `/reports/management` calculate `total_expenses` from the `Expense` table only (`payroll.py:257–260`, `payroll.py:689–693`). Received PO costs (COGS) therefore **do not appear** in the P&L expense totals shown on the dashboard and management accounts. This means:

- Gross profit is overstated if goods are received via PO
- The PO cost is captured in the journal (Account 1200 Inventory / 2000 AP) but not surfaced in the income statement reports

**Fix:** Either (a) include a COGS line in the P&L/dashboard by querying received POs, or (b) add a dedicated COGS expense row sourced from `sum(po.total_amount for received POs)`.

### 2.7 `/v1/summary` — `main.py:206` — ✗ FAIL

**Issue (High):** `main.py:211`:

```python
out_invs = db.query(Invoice).filter(Invoice.company_id==company.id, Invoice.status!="paid").all()
outstanding = sum(_to_zar(i) for i in out_invs)
```

This includes **draft** invoices in the outstanding balance. Invoices in `draft` status have not been sent to clients and should not appear as receivables. Only `sent` and `overdue` should count.

Note: The string comparison `Invoice.status=="paid"` works here because `InvoiceStatus` is a `str` enum (`class InvoiceStatus(str, enum.Enum)`), so `"paid"` compares correctly.

**Fix:**
```python
out_invs = db.query(Invoice).filter(
    Invoice.company_id==company.id,
    Invoice.status.in_(["sent","overdue"])
).all()
```

### 2.8 `/reports/provisional-tax` — `payroll.py:786` — ⚠ WARN (Low)

`payroll.py:792`:
```python
ytd_revenue = round(sum(i.total_amount for i in paid_invoices), 2)
```
No `_to_zar()`. This is a low risk (provisional tax is an estimate) but creates inconsistency.

---

## 3. Debtors (Accounts Receivable)

### Backend `/reports/debtors-aging` — `payroll.py:855` — ✗ FAIL

**Source filter** (`payroll.py:864–867`): Queries `Invoice` with `status IN (sent, overdue)` — ✓ paid invoices excluded, draft excluded.

**Aging buckets** (`payroll.py:871–890`): Uses `inv.due_date or inv.created_at` as the reference date — ✓ aging is from `due_date`, not `issue_date`. Minor: fallback uses `created_at` rather than `issue_date`; for invoices without a due date, `created_at` (timestamp) may differ from `issue_date` (business date). Low impact.

**Issue (High) — no ZAR conversion** (`payroll.py:875`):
```python
"amount": round(inv.total_amount, 2),
```
No `_to_zar()` applied. For multi-currency invoices, the debtors book shows the foreign-currency face value (e.g., USD 5,000) not the ZAR equivalent (e.g., R92,500). All bucket totals and the grand total are wrong for companies with foreign-currency invoices.

**Fix:**
```python
"amount": round(_to_zar(inv), 2),
```
Import `_to_zar` into `payroll.py` (it's already defined in the same file).

### Frontend Debtors component — `App_js_fixed.js:3128`

- Calls `/reports/debtors-aging` ✓
- Displays `inv.amount` returned by backend ✓ (relies on backend to provide ZAR — fix in backend)
- Shows `due_date` column ✓
- Aging buckets correctly labelled (Not Yet Due, 0–30, 31–60, 61–90, 90+) ✓
- No client-side currency conversion needed once backend is fixed ✓

---

## 4. Creditors (Accounts Payable)

### Backend `/reports/creditors-aging` — `payroll.py:911` — ✗ FAIL (Critical)

**Critical Issue:** The entire creditors-aging endpoint queries the **`Expense` table**, not the `PurchaseOrder` table:

```python
# payroll.py:920–923
expenses = db.query(Expense).filter(
    Expense.company_id == cid
).order_by(Expense.expense_date.desc()).all()
```

This means:
- **Received-but-unpaid POs do not appear as creditors** — the primary source of AP is invisible
- The view shows expenses grouped by vendor (historical spending), not actual outstanding supplier liabilities
- A company could have R500k in received-but-unpaid POs and the creditors view would show R0 in AP for those suppliers

Fully paid POs are correctly excluded, but only because POs aren't queried at all — this is coincidental.

**Secondary Issue — aging from expense_date, not due_date** (`payroll.py:931`):
```python
days_old = (now - exp_date).days
```
For a proper AP aging, the aging should be from the supplier's due date (e.g., `po.delivery_date` or `order_date + payment_terms`). Aging from expense transaction date overstates age.

**Supplier bank details:** The `suppliers.py:to_dict()` correctly decrypts bank fields (`payroll.py:48–52` in suppliers.py), but supplier bank details are not surfaced in the creditors-aging view at all — bank fields would only appear if the creditors view were rebuilt to query POs joined to suppliers.

**Fix (Critical):** Rewrite `/reports/creditors-aging` to:
1. Query `PurchaseOrder` with `status IN ('received', 'partial')` for outstanding AP
2. Join to `Supplier` to get payment terms and bank details
3. Age from `po.delivery_date` + supplier `payment_terms` days
4. Continue showing `Expense` data as a separate "Other Expenses" section or merge as non-PO payables

### Frontend Creditors component — `App_js_fixed.js:3247`

- Calls `/reports/creditors-aging` ✓ (but gets wrong data from backend)
- Displays expense-based vendor ledger — will show correct data once backend is fixed
- No supplier bank details rendered — acceptable for on-screen view; decryption handled in backend

---

## 5. Cross-Module Journal Coverage

### Posting functions in `journal.py`

| Event | Function | Status |
|---|---|---|
| Invoice raised (sent) | `post_invoice_raised` (line 154) | ✓ |
| Invoice paid | `post_invoice_paid` (line 181) | ✓ |
| Expense paid | `post_expense` (line 207) | ✓ |
| Payroll run | `post_payroll` (line 237) | ✓ |
| PO received | `post_po_received` (line 274) | ✓ |
| PO paid | `post_po_paid` (line 304) | ✓ |
| Stock adjustment | `post_stock_adjustment` (line 328) | ✓ |

All major event types have journal posting functions. Live transactions post correctly.

### Backfill Gap — `journal.py:419`

**Issue (Medium):** `backfill_company` only backfills POs with status `received` or `partial`:

```python
# journal.py:419–428
for po in db.query(PurchaseOrder).filter(
    PurchaseOrder.company_id == company_id,
    PurchaseOrder.status.in_(["received", "partial"])
).all():
```

POs with status `paid` are excluded. For companies migrated from an older version (before the journal engine was added), paid POs will have **no journal entries** — neither the receive entry (DR Inventory / CR AP) nor the pay entry (DR AP / CR Bank). This causes:
- Account 2000 (Accounts Payable) balance understated
- Account 1200 (Inventory) potentially understated
- Account 1000 (Bank) potentially overstated

**Fix:** Extend backfill to cover paid POs — post `post_po_received` then `post_po_paid` for each paid PO not already in the journal.

### Balance Sheet vs AR/AP Reconciliation

- **AR (Account 1100):** Sourced from journal entries for invoice raised/paid. This will reconcile with the debtors-aging view *after* the `_to_zar()` fix in §3.
- **AP (Account 2000):** Sourced from journal entries for PO received/paid. This will **not** reconcile with the creditors-aging view because creditors-aging is based on expenses, not POs. Even after fixing the backfill, the creditors-aging backend rewrite (§4) is required for reconciliation.

---

## 6. Action Items

| # | Severity | File | Description |
|---|---|---|---|
| 1 | **Critical** | `payroll.py:920` | Rewrite `/reports/creditors-aging` to query `PurchaseOrder` table (`status IN received, partial`) instead of `Expense` table. Join to `Supplier` for payment terms and bank details. Age from due date. |
| 2 | **High** | `payroll.py:312` | Apply `_to_zar()` in `/reports/monthly-trend`: `sum(_to_zar(inv) for inv in ...)`. |
| 3 | **High** | `payroll.py:584` | Apply `_to_zar()` in `/reports/cash-flow` cash receipts: `sum(_to_zar(i) for i in paid_this_month)`. |
| 4 | **High** | `payroll.py:875` | Apply `_to_zar()` in `/reports/debtors-aging` amount field: `"amount": round(_to_zar(inv), 2)`. Update bucket totals accordingly. |
| 5 | **High** | `main.py:211` | Fix `/v1/summary` outstanding filter: change `Invoice.status!="paid"` to `Invoice.status.in_(["sent","overdue"])` to exclude draft invoices. |
| 6 | **Medium** | `payroll.py:257` | Surface PO/COGS costs in dashboard and management P&L. Either query received POs for a COGS line, or document that the dashboard P&L excludes inventory-route expenses by design. |
| 7 | **Medium** | `payroll.py:450` | Apply `_to_zar()` in `/reports/reconciliation` 90-day debtors check: `sum(_to_zar(i) for i in overdue_90)`. |
| 8 | **Medium** | `payroll.py:542` | Fix gross margin health check: use `_to_zar(i)` instead of `i.amount`. This fixes both the excl-VAT inconsistency and the multi-currency issue. |
| 9 | **Medium** | `journal.py:419` | Extend `backfill_company` to include paid POs: post `post_po_received` + `post_po_paid` for each paid PO not already journaled. |
| 10 | **Low** | `payroll.py:792` | Apply `_to_zar()` in `/reports/provisional-tax` YTD revenue: `sum(_to_zar(i) for i in paid_invoices)`. |
| 11 | **Low** | `payroll.py:872` | In `/reports/debtors-aging`, change due-date fallback from `inv.created_at` to `inv.issue_date` for consistency. |
