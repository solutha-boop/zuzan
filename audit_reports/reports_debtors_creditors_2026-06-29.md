# ZuZan Audit Report — Reports, Debtors & Creditors
**Date:** 2026-06-29  
**Scope:** `/reports/dashboard`, `/reports/management`, `/reports/debtors-aging`, `/reports/creditors-aging`, cross-module journal coverage  
**Files reviewed:** `payroll.py`, `companies.py`, `suppliers.py`, `customers.py`, `purchase_orders.py`, `journal.py`, `database.py`, `main.py`, `App_js_fixed.js`

---

## 1. Summary

| Section | Verdict |
|---|---|
| **Reports — dashboard** | ✅ PASS — revenue, outstanding, expenses, PO COGS, depreciation, payroll all correct |
| **Reports — management** | ⚠️ PASS WITH NOTE — one labelling issue on outstanding KPI scope |
| **Reports — /v1/summary** | ✅ PASS — consistent with dashboard |
| **Debtors (AR)** | ✅ PASS — correct filter, ZAR amounts, aging from due_date, paid excluded |
| **Creditors (AP)** | ❌ FAIL — on-credit expenses create permanent AP balance with no clearance path; AP reconciliation will produce false failures; on-credit expenses invisible in Creditors Book |
| **Cross-module journal** | ❌ FAIL — missing `post_expense_paid` for on-credit expenses; AP control account (2000) will diverge from creditors-aging totals wherever credit expenses are used |

---

## 2. Reports

### `/reports/dashboard` (payroll.py)

**`total_revenue`** (lines 439–443)
- Queries `Invoice.status == InvoiceStatus.paid` only. ✓
- Sums `_to_zar(i)` for every paid invoice. ✓ Non-ZAR invoices use `paid_amount_zar` when available, falling back to `total_amount × exchange_rate`. Multi-currency conversion is correct.

**`total_outstanding`** (lines 445–449)
- Queries `status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])`. ✓
- Applies `_to_zar()`. ✓

**Expenses excluded from revenue** ✓
- Expenses are accumulated into `total_expenses`, not added to revenue. No bleed-through.

**Payroll costs** (lines 473–492)
- Sums `Payslip.total_cost` across ALL payslips for the company (including terminated employees). ✓
- Falls back to estimated cost from currently active employees when no payslips exist. ✓
- Payroll is tracked separately and subtracted after `gross_profit`, not conflated with `total_expenses`. ✓

**PO COGS** (lines 457–465)
- Queries `PurchaseOrder.status.in_(["received", "partial", "paid"])`. ✓
- Uses `(po.total_amount or 0) - (po.vat_amount or 0)` — ex-VAT. ✓
- Added to `total_expenses` only once. ✓
- Heuristic double-count guard (lines 501–540) warns if an expense record closely matches a received PO by supplier, month, and amount (±5%). ✓

**Depreciation** (lines 467–471)
- Sums all `DepreciationEntry.amount` for the company and adds to `total_expenses`. ✓

**No issues found in `/reports/dashboard`.**

---

### `/reports/management` (payroll.py)

**Revenue + trend loop** (lines 1068–1074, 1159–1180)
- Both apply `_to_zar()` consistently. ✓
- PO COGS and depreciation included in trend months. ✓
- Payroll estimated from period payslips with active-employee fallback. ✓

**Issue — outstanding KPI scope** (lines 1142–1147): The `total_outstanding` field in the management report KPIs queries ALL outstanding invoices regardless of the `date_from`/`date_to` filter. While this is defensible as a point-in-time AR snapshot, the UI presents it alongside period-filtered revenue and expenses with no explanatory label, which could mislead users filtering by a historical date range.

**`_to_zar()` in trend loop** (lines 1159–1162): Applied consistently per month. ✓

---

### `/v1/summary` (main.py, lines 249–291)

- `_to_zar()` applied to paid invoices. ✓
- PO COGS included ex-VAT. ✓
- Depreciation added. ✓
- Payroll summed from payslips (`Payslip.total_cost`). ✓
- All calculations are consistent with `/reports/dashboard`.

**✓ No issues found.**

---

## 3. Debtors (Accounts Receivable)

### Backend — `/reports/debtors-aging` (payroll.py, lines 1323–1383)

**Status filter** (line 1332–1335): Queries `InvoiceStatus.sent` and `InvoiceStatus.overdue`. The audit checklist references a `pending` status — this does not exist in `InvoiceStatus` (database.py, line 36–40); `sent` serves this role (documented at database.py line 38). Filter is correct. ✓

**ZAR amounts** (line 1344): `_to_zar(inv)` applied to each invoice. ✓

**Aging from `due_date`** (line 1342): Aging is computed from `inv.due_date`, not `issue_date` or `created_at`. An earlier fallback to issue_date was removed and documented in the comment at line 1341. ✓

**Paid invoices excluded**: Only `sent` and `overdue` statuses queried. `paid` invoices are never included. ✓

**Invoices without a due_date** (lines 1351–1353): Go into `not_due` bucket rather than being aged — prevents false overdue inflation. ✓

**Bucket boundaries** (lines 1358–1366): `current` = 0–30 days, `31_60` = 31–60 days, `61_90` = 61–90 days, `over_90` = 91+ days. Consistent with frontend labels. ✓

### Frontend — `Debtors` component (App_js_fixed.js, lines 4670–4793)

- Calls `/reports/debtors-aging`. ✓
- Displays `inv.amount` which is the ZAR-converted value from the backend. ✓
- Refreshes automatically on `live.invoices` change. ✓
- Shows `due_date` in table. ✓

**✓ No issues found in Debtors.**

---

## 4. Creditors (Accounts Payable)

### Backend — `/reports/creditors-aging` (payroll.py, lines 1386–1480)

**Status filter** (lines 1403–1405): Queries `status.in_(["received", "partial"])`. Fully paid POs (`status == "paid"`) are correctly excluded. ✓

**Due date aging** (lines 1425–1427): Computed as `base_date + timedelta(days=payment_terms)` where `base_date = po.received_date or po.order_date or po.created_at`. This is correct — payment terms run from delivery, not order date. ✓

**Supplier bank details decrypted** (lines 1440–1443): `decrypt_field()` is called for `bank_name`, `account_number`, and `branch_code` before they are returned to the client. ✓

**Critical gap — on-credit expenses invisible** (HIGH — see Section 5 for details): The creditors-aging endpoint only queries the `PurchaseOrder` table. Expenses marked `is_on_credit=True` (which journal as DR Expense / CR AP 2000) are never surfaced here, so they are hidden from the Creditors Book. ❌

### Frontend — `Creditors` component (App_js_fixed.js, lines 4796–4940)

- Calls `/reports/creditors-aging`. ✓
- Refreshes on `live.purchaseOrders` change. ✓
- Column header "Amount (incl. VAT)" correctly describes that `po.total_amount` is VAT-inclusive. ✓

---

## 5. Cross-module Journal Coverage

| Event | Posting function | Trigger | Status |
|---|---|---|---|
| Invoice raised | `post_invoice_raised` | companies.py:228 | ✓ |
| Invoice paid | `post_invoice_paid` | companies.py:275 | ✓ |
| Invoice COGS | `post_invoice_cogs` | companies.py:231 | ✓ |
| Expense (cash) | `post_expense` | companies.py:421 | ✓ |
| Expense (on-credit) — created | `post_expense` → CR AP 2000 | companies.py:421 | ✓ |
| Expense (on-credit) — **paid/cleared** | **MISSING** | **no endpoint** | ❌ |
| Payroll run | `post_payroll` | payroll.py:336 | ✓ |
| PO received | `post_po_received` | purchase_orders.py:249 | ✓ |
| PO paid | `post_po_paid` | purchase_orders.py:312 | ✓ |
| Fixed asset acquisition | `post_asset_acquisition` | fixed_assets router | ✓ |
| Depreciation charge | `post_depreciation` | fixed_assets router | ✓ |
| Asset disposal | `post_asset_disposal` | fixed_assets router | ✓ |

### Gap: No AP clearance for on-credit expenses

`database.py` line 125 defines `Expense.is_on_credit = Column(Boolean, default=False)`. When `is_on_credit=True`, `post_expense` in `journal.py` (lines 283–285) credits **Account 2000 (Accounts Payable)** instead of Account 1000 (Bank):

```python
credit_acct = get_account(cid, "2000" if on_credit else "1000", db)
```

There is no `post_expense_paid` function in `journal.py` and no `/expenses/{id}/pay` endpoint in `companies.py`. This creates three compounding problems:

1. **AP account permanently overstated**: The AP journal balance (account 2000) accumulates credits from on-credit expenses that are never debited when the invoice is settled, making the balance sheet liability overstatement grow with every credit expense recorded.

2. **AP reconciliation (Rule 7) produces false failures** (payroll.py, lines 857–873): The reconciliation compares the journal balance of account 2000 against `sum(po.total_amount for open POs)`. Any credit expense in the journal balance has no matching PO, so the difference will always flag as a fail with a misleading error message ("Likely caused by a missed journal posting. Run /journal/backfill to repair.").

3. **Creditors Book hides credit expense liabilities**: `/reports/creditors-aging` queries only `PurchaseOrder`, so credit-expense creditors are invisible to the user in the AP view. This understates true creditor exposure.

### Balance Sheet Reconciliation

- AR control account (1100) vs outstanding invoices (Rule 6, lines 834–854): Logic is correct — journal AR is compared against `sum(_to_zar(i) for i in outstanding_invoices)`. ✓
- AP control account (2000) vs open POs (Rule 7, lines 857–873): Structurally correct for POs only, but will diverge whenever on-credit expenses are used (see above). ❌

### Duplicate "RULE 8" label (cosmetic)

`payroll.py` has two consecutive `# ── RULE 8:` comment headings: one for "Inventory Valuation" (line 875) and one for "Unmatched revenue" / Gross Margin Health (line 895). The second should be labelled RULE 9. Does not affect calculations.

---

## 6. Action Items

**#1 — HIGH — Add on-credit expense AP clearance**  
Create `post_expense_paid(expense, db)` in `journal.py`:
```
DR Accounts Payable (2000)   expense.amount
CR Bank / Cash (1000)        expense.amount
```
Add a `POST /expenses/{expense_id}/pay` endpoint in `companies.py` that calls this function and marks the expense as paid. This mirrors the `pay_po` endpoint in `purchase_orders.py`.

**#2 — HIGH — Include on-credit expenses in `/reports/creditors-aging`**  
After fix #1, query unpaid on-credit expenses (where `is_on_credit=True` and `is_paid=False` — a new flag, or inferred from journal entries) and surface them in the creditors-aging response alongside POs, grouped by vendor.

**#3 — HIGH — Fix AP reconciliation Rule 7 false failures**  
Update Rule 7 in `payroll.py` (line 857–873) so that `ap_raw_total` includes both open POs and outstanding on-credit expenses:
```python
ap_raw_total = open_po_total + unpaid_credit_expense_total
```
Until #1 and #2 are done, add a note to the Rule 7 failure message that credit expenses may contribute to the discrepancy.

**#4 — MEDIUM — Label `total_outstanding` scope in management accounts**  
In `/reports/management` (line 1142–1147), add a `"outstanding_note"` field or UI label clarifying that outstanding AR is as-at-now (not period-scoped). Alternatively, filter to invoices issued before `period_end` to make it period-consistent.

**#5 — LOW — Fix duplicate RULE 8 comment label**  
In `payroll.py`, rename the second `# ── RULE 8:` (line 895) to `# ── RULE 9:` (Gross Margin Health). Purely cosmetic — no functional impact.

---

*Report generated automatically by scheduled audit task. Review with a qualified accountant before acting on findings.*
