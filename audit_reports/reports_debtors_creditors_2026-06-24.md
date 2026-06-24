# ZuZan Audit Report — Reports, Debtors & Creditors
**Date:** 2026-06-24  
**Auditor:** Automated scheduled audit  
**Files reviewed:** `payroll.py`, `journal.py`, `purchase_orders.py`, `companies.py`, `main.py`, `App_js_fixed.js`

---

## 1. Summary

| Section | Verdict | Notes |
|---------|---------|-------|
| Reports — `/reports/dashboard` | ✅ PASS (with notes) | Revenue, outstanding, payroll, PO COGS all correct; depreciation included |
| Reports — `/reports/management` | ✅ PASS | Consistent with dashboard; trend loop applies `_to_zar()` correctly |
| Reports — `/v1/summary` | ⚠️ WARN | Missing depreciation in `total_expenses` — inconsistent with dashboard |
| Debtors (AR) | ✅ PASS | Correct filtering, ZAR conversion, aging from `due_date` |
| Creditors (AP) | ✅ PASS (with notes) | Correct filtering; bank fields decrypted; NULL `received_date` edge case |
| Cross-module journal | ⚠️ WARN | All posting functions wired up; PO COGS journal/P&L architectural discrepancy flagged |

---

## 2. Reports

### `/reports/dashboard` — `payroll.py:430`

**`total_revenue`**
- Queries `Invoice WHERE status = 'paid'` and sums `_to_zar(inv)` for each. ✓
- `_to_zar()` correctly uses `paid_amount_zar` if set, otherwise `total_amount × exchange_rate` for non-ZAR, or `total_amount` for ZAR. `payroll.py:17–24`

**`total_outstanding`**
- Queries `Invoice WHERE status IN ('sent', 'overdue')` and sums `_to_zar(inv)`. ✓ `payroll.py:445–449`

**Expenses excluded from revenue**
- `total_expenses` is built from `Expense` records only; revenue uses only `Invoice` records. No cross-contamination. ✓

**Payroll costs**
- Uses actual `Payslip.total_cost` (all-time) from DB if payroll has been run; falls back to `calc_payroll()` estimate. ✓ `payroll.py:478–484`

**PO COGS**
- Includes received/partial/paid POs ex-VAT: `(po.total_amount - po.vat_amount)`. ✓ `payroll.py:457–465`
- A heuristic duplicate-expense detection warning is shown if a same-supplier, same-month Expense record closely matches a received PO (±5% tolerance). This is a sensible safeguard. ✓

**Depreciation**
- `DepreciationEntry` amounts are summed and added to `total_expenses`. ✓ `payroll.py:468–471`

**⚠️ Architectural note — PO COGS vs. Journal Inventory (HIGH)**
`post_po_received()` in `journal.py:327` posts: DR 1200 Inventory / CR 2000 Accounts Payable. However, the P&L in `/reports/dashboard` independently queries the `PurchaseOrder` table and adds PO amounts as COGS expenses immediately on receipt (`payroll.py:457–465`). This means:
- The Balance Sheet (journal-based) shows PO amounts as Inventory (asset).
- The P&L (direct query) shows the same PO amounts as an expense, before the goods are sold.
- For businesses holding physical stock, this overstates P&L expenses and understates profit when inventory is on hand.

This is a design-level inconsistency between the journal-based Balance Sheet and the direct-query P&L. It resolves correctly only when inventory is fully sold (via `post_invoice_cogs` which credits 1200), but diverges whenever there is unsold stock.

**Action required:** Either (a) move PO COGS out of the direct-query P&L and instead read from journal account 5000, or (b) change `post_po_received()` to debit a COGS/expense account directly when the PO represents a service (not goods), and only use 1200 for physical goods. See Action Items #1 and #2.

### `/reports/management` — `payroll.py:1015`

- Revenue: paid invoices from `month_start`, `_to_zar()` applied. ✓
- Expenses: ex-VAT, consistent with dashboard. ✓
- PO COGS: received POs in month filtered by `received_date >= month_start`. ✓
- Depreciation: added via `DepreciationEntry.period`. ✓
- Revenue trend loop (lines 1096–1126): `_to_zar(inv)` applied to each invoice in each month's paid query. ✓
- Expense trend loop: ex-VAT, PO COGS ex-VAT, depreciation all applied. ✓

✓ No issues found beyond the architectural note above.

### `/v1/summary` — `main.py:210`

- `_to_zar()` used for `total_revenue` and `outstanding`. ✓ `main.py:217, 237`
- Expenses: ex-VAT, consistent with dashboard. ✓
- PO COGS: added. ✓ `main.py:221–229`
- Payroll: uses actual payslips. ✓ `main.py:231–235`

**⚠️ Missing depreciation (MEDIUM)**
`DepreciationEntry` is never imported or queried in `/v1/summary`. The dashboard (`payroll.py:468–471`) adds depreciation to `total_expenses`; the API summary does not. API consumers therefore see a lower `total_expenses` and higher `net_profit` than the dashboard shows. `main.py:219–229`

**Action required:** Import `DepreciationEntry` and add the same depreciation sum as in `/reports/dashboard`. See Action Item #3.

---

## 3. Debtors (Accounts Receivable)

### Backend — `payroll.py:1269` `/reports/debtors-aging`

**Invoice filtering**
- Queries `Invoice WHERE status IN ('sent', 'overdue')`. Paid invoices are excluded. ✓

**ZAR equivalents**
- `entry["amount"] = round(_to_zar(inv), 2)` — foreign-currency amounts are converted before bucketing. ✓ `payroll.py:1289`

**Aging buckets**
- Buckets are computed from `inv.due_date`. Invoices without a `due_date` go to `not_due` — this prevents overstating overdue balances. ✓ `payroll.py:1288–1312`
- Days are measured as `(now - due).days`:
  - `< 0`: not yet due
  - `0–30`: current
  - `31–60`: 31_60
  - `61–90`: 61_90
  - `> 90`: over_90

**AR control account reconciliation**
The `/reports/reconciliation` endpoint (rule 6, `payroll.py:821`) compares journal account 1100 balance against outstanding invoices using `_to_zar()` on both sides. ✓

### Frontend — `App_js_fixed.js:4480`

- Calls `api("/reports/debtors-aging")`. ✓
- Displays `inv.amount` (already ZAR-converted by backend). ✓
- Bucket labels match backend bucket keys. ✓
- Aging summary table totals match `data.totals` from backend. ✓

✓ No issues found.

---

## 4. Creditors (Accounts Payable)

### Backend — `payroll.py:1332` `/reports/creditors-aging`

**PO filtering**
- Queries `PurchaseOrder WHERE status IN ('received', 'partial')`. Fully paid POs are excluded. ✓ `payroll.py:1348–1352`

**Received-but-unpaid POs**
- Both `received` and `partial` statuses appear in the creditors book. ✓

**Fully paid POs excluded**
- Status `'paid'` is not in the filter. ✓

**Supplier bank decryption**
- All three bank fields use `decrypt_field()` before inclusion in the response: `payroll.py:1386–1390`
  ```python
  "bank_name":      decrypt_field(sup.bank_name),
  "account_number": decrypt_field(sup.account_number),
  "branch_code":    decrypt_field(sup.branch_code),
  ```
  ✓ Encrypted fields are correctly decrypted.

**Aging**
- Due date computed as `received_date + payment_terms days` from supplier record (default 30 days if not set). `payroll.py:1371–1373`
- Aging buckets: not_due / 0–30 / 31–60 / 61–90 / 90+. ✓

**AP control account reconciliation**
Rule 7 in `/reports/reconciliation` (`payroll.py:844`) compares journal account 2000 balance against open POs (received/partial) by `po.total_amount`. Both `post_po_received()` and the reconciliation check use `total_amount` (VAT-inclusive), so they are consistent. ✓

**⚠️ NULL `received_date` edge case (LOW)**
For POs that were marked received before the `received_date` column was added (or via the old `/receive` endpoint), `received_date` may be NULL. The aging falls back to `order_date` or `created_at` (`payroll.py:1371`), which may overstate how long an invoice has been outstanding.

The manual backfill endpoint `POST /purchase-orders/backfill-received-dates` exists to fix this (`purchase_orders.py:244`) but must be run explicitly per company. It is not called automatically on startup.

**Action required:** See Action Item #4.

### Frontend — `App_js_fixed.js:4598`

- Calls `api("/reports/creditors-aging")`. ✓
- Displays vendor totals and per-PO amounts. ✓
- Bucket filter works client-side by re-filtering `v.invoices`. ✓
- Bank details (if shown) come from the backend response and are already decrypted. ✓

✓ No functional issues found beyond the NULL `received_date` edge case noted above.

---

## 5. Cross-Module Journal Coverage

| Event | Posting function | Called from | Status |
|-------|-----------------|-------------|--------|
| Invoice raised | `post_invoice_raised()` | `companies.py:209` | ✅ |
| Invoice paid | `post_invoice_paid()` | `companies.py:242` | ✅ |
| Invoice COGS (inventory) | `post_invoice_cogs()` | `companies.py:212` (when `cogs_amount` provided) | ✅ |
| Expense created | `post_expense()` | `companies.py:307, 391, 606` | ✅ |
| Payroll run | `post_payroll()` | `payroll.py:336` | ✅ |
| PO received | `post_po_received()` | `purchase_orders.py:226` | ✅ |
| PO paid | `post_po_paid()` | `purchase_orders.py:291` | ✅ |
| Fixed asset acquisition | `post_asset_acquisition()` | `journal.py backfill` + `fixed_assets.py` | ✅ |
| Depreciation run | `post_depreciation()` | `journal.py backfill` + `fixed_assets.py` | ✅ |
| Asset disposal | `post_asset_disposal()` | `journal.py backfill` + `fixed_assets.py` | ✅ |

**Balance sheet accounts (1100 AR / 2000 AP) reconciliation:**
- AR: `post_invoice_raised()` debits 1100; `post_invoice_paid()` credits 1100. Net balance = outstanding invoices. ✓
- AP: `post_po_received()` credits 2000; `post_po_paid()` debits 2000. Net balance = received-but-unpaid POs. ✓

**⚠️ PO receipt posts to Inventory (1200), not COGS (5000) (HIGH — see Reports section)**
`post_po_received()` always debits account 1200 (Inventory at Cost). For service purchases (no physical stock), this misclassifies the cost as an asset on the balance sheet rather than an operating expense. Combined with the P&L dashboard independently expensing PO COGS from the raw PO table, this creates a discrepancy between the journal-based Balance Sheet and the P&L.

**⚠️ Duplicate rule label in reconciliation (LOW — code quality)**
In `payroll.py`, reconciliation rules are labelled RULE 1 through RULE 8, but "RULE 7" appears twice (line 844 and line 882). The second one should be RULE 8 (Gross Margin Health). This is a comment/label error only, not a logic bug.

---

## 6. Action Items

### Critical
*None.*

### High

**#1 — PO COGS: prevent premature expensing of unsold inventory**
**File:** `payroll.py:457–465`, `journal.py:327–354`  
The P&L dashboard expenses all received POs immediately, while the journal books them as Inventory. For businesses with physical stock, this overstates expenses and understates profit when goods are on hand. Options:
- Short-term: add a note in the dashboard that "PO COGS" reflects goods received, not necessarily sold.
- Long-term: drive P&L COGS from the journal account 5000 balance rather than the PO table.

**#2 — `post_po_received()`: route service POs to expense account, not inventory**
**File:** `journal.py:327–354`  
All PO receipts currently debit 1200 (Inventory). For POs that represent services (consulting, utilities, subscriptions), this incorrectly inflates the inventory asset on the balance sheet. Consider adding a `po_type` field (`goods` vs `service`) and routing service POs to account 5000 or the relevant expense account.

### Medium

**#3 — Add depreciation to `/v1/summary`**
**File:** `main.py:219–229`  
`total_expenses` in the public API summary does not include `DepreciationEntry`. The dashboard and management report both include it. Fix:
```python
from database import DepreciationEntry
total_depreciation = db.query(func.sum(DepreciationEntry.amount)).filter(
    DepreciationEntry.company_id == company.id
).scalar() or 0
total_expenses = total_expenses + total_depreciation
```

### Low

**#4 — Auto-backfill NULL `received_date` on POs at startup**
**File:** `main.py` (lifespan), `purchase_orders.py:244`  
POs with NULL `received_date` use `order_date` or `created_at` as a fallback in the creditors aging, which may show incorrect aging. The backfill endpoint exists but must be triggered manually. Consider calling it during the startup lifespan alongside the journal backfill, or add a migration in `init_db()`.

**#5 — Fix duplicate "RULE 7" comment label in reconciliation**
**File:** `payroll.py:882`  
The second occurrence of `# ── RULE 7:` (Gross Margin Health check) should be relabelled `# ── RULE 8:` to avoid confusion when reading the code. No logic impact.

---

*End of report.*
