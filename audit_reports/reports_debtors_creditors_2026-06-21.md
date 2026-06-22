# ZuZan Audit Report — Reports, Debtors & Creditors
**Date:** 2026-06-21  
**Auditor:** Automated scheduled audit  
**Scope:** Reports (`/reports/dashboard`, `/reports/management`, `/reports/monthly-trend`), Debtors (AR), Creditors (AP), cross-module journal coverage  
**Files reviewed:**
- `payroll.py` — reports_router, debtors_aging, creditors_aging
- `companies.py` — invoices_router, expenses_router, bank_router
- `purchase_orders.py` — receive_po, pay_po
- `journal.py` — all posting functions, backfill
- `main.py` — /v1/summary public API
- `database.py` — models and enums
- `App_js_fixed.js` — Debtors, Creditors, StatusBadge components

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports — `/reports/dashboard` | ⚠️ WARN — minor PO double-count risk; see item #4 |
| Reports — `/reports/management` | ⚠️ WARN — PO COGS may miss POs with null `received_date` |
| Reports — `/reports/monthly-trend` | ✓ PASS |
| `/v1/summary` public API | ✓ PASS |
| Debtors (AR) | ⚠️ WARN — aging fallback date; missing "sent" badge mapping |
| Creditors (AP) | ✓ PASS |
| Cross-module journal coverage | ❌ FAIL — no COGS posting on invoice, `update_expense` skips VAT recalc |

---

## 2. Reports

### `/reports/dashboard` (payroll.py:258–333)

**`total_revenue` — PASS**  
Correctly filters `Invoice.status == InvoiceStatus.paid` (line 268–270) and applies `_to_zar()` (line 271). Foreign-currency invoices use `paid_amount_zar` when set, otherwise `total_amount × exchange_rate`. Expenses are not included in revenue. ✓

**`total_outstanding` — PASS**  
Filters `status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])` (line 273–276). Uses `_to_zar()` (line 277). Paid invoices are excluded. Note: the `InvoiceStatus` enum has no `pending` value — "sent" is the correct pre-payment status. ✓

**`total_expenses` — PASS**  
Correctly computes `e.amount - (e.vat_amount or 0)` (line 283) to strip the stored VAT-inclusive amount back to excl-VAT. ✓

**Payroll costs — PASS**  
Uses actual payslip `total_cost` sum if payroll has been run; falls back to current-month estimate (lines 300–306). ✓

**PO COGS — WARN (item #4)**  
Lines 287–293 add PO COGS for `received`, `partial`, and `paid` POs excl-VAT. This is correct accounting. **However**, no safeguard prevents a user from also manually creating an `Expense` record for the same cost. If they do, the cost will appear in both `total_expenses` (via the expenses query) and the `po_cogs` addition — double-counted. There is no uniqueness constraint or deduplication check.

**VAT position — PASS**  
Output VAT sums `vat_amount` across all invoices; input VAT sums `vat_amount` across all expenses. ✓

---

### `/reports/management` (payroll.py:776–898)

**Revenue — PASS**  
Filters paid invoices with `paid_date >= month_start`. Uses `_to_zar()` throughout including the 6-month trend loop (lines 856–870). ✓

**Expenses — PASS**  
Monthly expenses use `e.amount - (e.vat_amount or 0)` consistently with the dashboard. ✓

**PO COGS in monthly trend — WARN (item #6)**  
The trend loop at line 863–868 filters with `PurchaseOrder.received_date >= start`. POs received via `/purchase-orders/{id}/receive` always have `received_date` set (via `po.received_date = datetime.utcnow()` in purchase_orders.py:212). However, POs that pre-date this field being populated (e.g. imported via backfill or direct DB writes) may have a null `received_date` and will be silently excluded from the monthly P&L trend. The all-time dashboard total is unaffected (no date filter).

**Payroll costs — PASS**  
Uses actual payslips for the current period; falls back to estimate. ✓

---

### `/reports/monthly-trend` (payroll.py:336–397)

Revenue, expenses, and PO COGS all use `_to_zar()` / excl-VAT consistently. The 6-month loop correctly handles month/year wraparound. ✓ No issues found.

---

### `/v1/summary` (main.py:210–231)

Imports and uses `_to_zar` from `payroll.py`. Correctly filters paid invoices, subtracts `vat_amount` from expenses, adds PO COGS excl-VAT. ✓ No issues found.

---

## 3. Debtors (Accounts Receivable)

### Backend — `/reports/debtors-aging` (payroll.py:1001–1054)

**Status filter — PASS**  
Filters `Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])` (line 1011–1012). Paid invoices are excluded. ✓

**ZAR equivalents — PASS**  
Each entry uses `round(_to_zar(inv), 2)` (line 1023). Foreign-currency outstanding invoices are converted at `exchange_rate`. ✓

**Aging from `due_date` — PASS (with caveat)**  
Line 1018: `due = inv.due_date or inv.issue_date or inv.created_at` — aging is calculated from `due_date` as required. ✓  
**Caveat (item #7):** If `due_date` is None, aging falls back to `issue_date` (when the invoice was issued) or `created_at`. An invoice without a due_date will appear more overdue than it actually is, potentially misclassifying invoices into the 31–60 or 61–90+ buckets. Low risk if all invoices have due dates set, but no enforcement exists at the database level.

**Paid invoices excluded — PASS**  
Only `sent` and `overdue` statuses are queried. ✓

### Frontend — `Debtors` component (App_js_fixed.js:3557–3673)

Calls `/reports/debtors-aging` on mount (line 3563). Displays buckets `not_due`, `current` (0–30), `31_60`, `61_90`, `over_90` with ZAR amounts. Amounts come from the backend `_to_zar()` result so display is in ZAR. ✓

**WARN (item #5):** The `StatusBadge` component (line 158–162) maps `{paid:..., pending:..., overdue:...}`. There is no `sent` key. Invoices with `status:"sent"` fall through to `m.pending` (line 160: `const [c,bg,l]=m[status]||m.pending`), so they display as "Pending" instead of "Sent". This is a UI-only cosmetic issue but may confuse users.

---

## 4. Creditors (Accounts Payable)

### Backend — `/reports/creditors-aging` (payroll.py:1057–1151)

**Source data — PASS**  
Queries `PurchaseOrder` filtered to `status.in_(["received", "partial"])` (line 1073–1074). Fully paid POs (`status == "paid"`) are excluded. ✓

**Outstanding creditors — PASS**  
Only received-but-unpaid POs appear. The `/purchase-orders/{id}/pay` endpoint transitions to `"paid"` and posts `DR AP / CR Bank`, so paid POs drop out of the creditor view. ✓

**Supplier bank details decryption — PASS**  
Lines 1111–1113 call `decrypt_field(sup.bank_name)`, `decrypt_field(sup.account_number)`, `decrypt_field(sup.branch_code)` before including them in the response. Fields for POs with no linked `supplier_id` return `None` gracefully. ✓

**Aging from due date — PASS**  
Lines 1095–1105: aging is calculated as `received_date + payment_terms days`, which is the correct creditors due date. The `days_overdue` and bucket assignment logic is correct. ✓

### Frontend — `Creditors` component (App_js_fixed.js:3676–3829)

Calls `/reports/creditors-aging` on mount and reloads when `live.expenses` changes (lines 3682–3690). Displays vendor-grouped POs with received date, due date, days overdue. Bank details (account number, branch code) are NOT displayed in the UI — only the vendor name and amounts — so there is no risk of sensitive bank details leaking to the screen. ✓

---

## 5. Cross-Module Consistency

### Journal coverage

| Event | Posting function | Where called | Status |
|---|---|---|---|
| Invoice raised | `post_invoice_raised` | `companies.py:203` | ✓ |
| Invoice paid | `post_invoice_paid` | `companies.py:234` | ✓ |
| Expense created | `post_expense` | `companies.py:298` | ✓ |
| Bank import expense | `post_expense` | `companies.py:499` | ✓ (non-fatal on error) |
| Payroll run | `post_payroll` | `payroll.py:211` | ✓ |
| PO received | `post_po_received` | `purchase_orders.py:226` | ✓ |
| PO paid | `post_po_paid` | `purchase_orders.py:264` | ✓ |
| **Inventory sold on invoice** | **none** | **—** | **❌ MISSING** |
| Fixed asset acquisition | `post_asset_acquisition` | `fixed_assets.py` (not reviewed) | assumed ✓ |

**CRITICAL MISSING: Inventory COGS journal on sale (item #1)**  
When an invoice is created for a product that exists in inventory, there is no journal entry to debit Cost of Sales (5000) and credit Inventory at Cost (1200). This means:
- Inventory account (1200) remains inflated after goods are sold
- COGS is understated unless the PO path is used
- Balance sheet trade receivables and inventory may both be overstated simultaneously
- The `post_stock_adjustment` function exists in `journal.py:335` and is called from `inventory.py:92` for manual adjustments, but is NOT called from `companies.py:create_invoice`

**CRITICAL: `update_expense` skips VAT recalculation (item #2)**  
`companies.py:311–318` — when an expense is updated via `PUT /expenses/{id}`, the new `amount` is stored directly but `vat_amount` is NOT recalculated. Since `expense.amount` is stored VAT-inclusive, after an update the `vat_amount` field becomes stale. All reports using `e.amount - (e.vat_amount or 0)` will return an incorrect excl-VAT figure. The journal entry is also not re-posted, creating a ledger discrepancy.

### Balance sheet account reconciliation

**Debtors Control (1100) — PASS**  
The reconciliation endpoint (payroll.py:586–602) compares the journal AR balance against outstanding invoice totals and flags any gap > R1. Both sides use `_to_zar()`. ✓

**Creditors Control (2000) — PASS**  
The reconciliation endpoint (payroll.py:604–621) compares journal AP balance against open PO totals. Both sides use `po.total_amount` (VAT-inclusive) consistently. ✓

### Tax tables

**2024/2025 and 2025/2026 brackets are identical (item #8)**  
`payroll.py:29–55` — the PAYE brackets and primary rebate for `2024/2025` and `2025/2026` are byte-for-byte identical (R237,100 first threshold, R17,235 primary rebate). If SARS published different tables for these years, the 2024/2025 audit history calculations will be incorrect. Verify against SARS published tables.

---

## 6. Action Items

**CRITICAL**

1. **Add COGS journal entry on invoice creation** (`companies.py:create_invoice`)  
   When invoice line items reference inventory SKUs, call `post_stock_adjustment` (or a new `post_invoice_cogs`) to DR Cost of Sales (5000) / CR Inventory at Cost (1200) for each item's `unit_cost × quantity`. Without this, the balance sheet overstates inventory and understates COGS.

2. **Fix `update_expense` to recalculate VAT** (`companies.py:311–318`)  
   When `amount` is updated, recalculate `vat_amount = round(new_amount * VAT_RATE / 1.15, 2)` (back-calculate from VAT-inclusive) or require the caller to pass `vat_amount` explicitly. Also re-post the journal entry (or post a reversing + correcting entry). Without this fix, any expense edit corrupts the report figures.

**HIGH**

3. **Guard against PO COGS + manual Expense double-counting** (`payroll.py:286–293`, `payroll.py:805–815`)  
   Add a check: if an Expense record's `description` or `vendor` references a PO number, warn the user or exclude it from the general expense sum. Alternatively, document clearly that once a PO is received, no corresponding manual Expense should be created.

4. **Backfill `received_date` on existing POs** (database migration)  
   Any PO with `status IN ('received','partial','paid')` and `received_date IS NULL` will be excluded from the monthly P&L trend. Run a migration to set `received_date = created_at` for these records, or add a null-guard in the trend queries (`OR PurchaseOrder.received_date IS NULL`).

**MEDIUM**

5. **Add `sent` mapping to `StatusBadge`** (`App_js_fixed.js:158–162`)  
   Add `sent:[C.blue, C.blueLt, "Sent"]` to the mapping object so sent invoices display "Sent" rather than "Pending".

6. **Enforce `due_date` on invoices or fix aging fallback** (`payroll.py:1018`, `companies.py:create_invoice`)  
   Either make `due_date` a required field on invoice creation, or change the aging fallback to use today's date instead of `issue_date`/`created_at` (so invoices without a due date are placed in "Not Yet Due" rather than appearing overdue).

7. **Verify PAYE tax tables for 2024/2025 vs 2025/2026** (`payroll.py:29–55`)  
   Confirm with SARS published tables that the brackets and primary rebate were truly unchanged between these two years. If they differed, correct the `2024/2025` entry so historical payslip recalculations are accurate.

**LOW**

8. **Balance sheet equity fallback may hide manual adjustments** (`payroll.py:442`)  
   The condition `if retained_income == 0` triggers revenue-minus-expenses derivation even if the user has made manual equity journal entries that net to zero. Consider removing the fallback and always presenting the journal balance (even if R0).

9. **Bank import expenses lack VAT metadata** (`companies.py:486–492`)  
   Imported bank statement debits store `amount = txn.amount` with no `vat_amount`. If the bank statement amounts are VAT-inclusive, input VAT is understated. Consider prompting the user to specify whether imported transactions include VAT, or apply a configurable VAT rate during import.

---

*Report generated automatically by ZuZan scheduled audit — 2026-06-21*
