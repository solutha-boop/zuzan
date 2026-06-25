# ZuZan Audit Report — Reports, Debtors & Creditors
**Date:** 2026-06-25  
**Scope:** `/reports/dashboard`, `/reports/management`, `/reports/debtors-aging`, `/reports/creditors-aging`, cross-module journal consistency  
**Files reviewed:** `payroll.py`, `companies.py`, `purchase_orders.py`, `journal.py`, `database.py`, `main.py`, `App_js_fixed.js`

---

## 1. Summary

| Section | Verdict |
|---------|---------|
| Reports — `/reports/dashboard` | ✓ Pass with 1 medium note |
| Reports — `/reports/management` | ✓ Pass |
| Reports — `/v1/summary` | ✓ Pass |
| Debtors (AR) | ✓ Pass |
| Creditors (AP) | ✓ Pass |
| Cross-module journal — coverage | ✓ Pass |
| Cross-module journal — deletion reversals | ✗ **FAIL — Critical gaps** |

---

## 2. Reports

### `/reports/dashboard` (payroll.py lines 430–560)

**`total_revenue`** — sums paid invoices only (`Invoice.status == InvoiceStatus.paid`), applies `_to_zar()` for all entries. For foreign-currency invoices, `_to_zar()` uses `paid_amount_zar` if set (actual cash received), then falls back to `total_amount × exchange_rate`. ZAR invoices return `total_amount` directly. ✓

**`total_outstanding`** — filters `status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])` and applies `_to_zar()`. ✓

**Expenses excluded from revenue** — revenue and expenses are queried and summed independently. ✓

**Payroll costs** — uses sum of actual `Payslip.total_cost` records (all-time); falls back to a live `calc_payroll()` estimate if no payslips exist. Subtracted from gross_profit to get net_profit. ✓

**PO COGS** — received/partial/paid POs contribute to `total_expenses` ex-VAT (lines 457–465). The `receive_po` endpoint in `purchase_orders.py` (lines 218–220) explicitly does NOT create a duplicate `Expense` record; the journal is the single cost record. A runtime duplicate-warning check (lines 499–537) detects suspicious Expense/PO matches by supplier, month, and ±5% amount tolerance. ✓

**Depreciation** — all `DepreciationEntry` records for the company are summed and added to `total_expenses`. ✓

**Note (Medium):** The duplicate-expense warning (lines 499–537) is reactive — it detects potential double-counts but does not prevent them. Any legacy Expense records created manually for the same PO cost before the current no-auto-expense design was in place will permanently inflate `total_expenses`. See Action Item #4.

### `/reports/management` (payroll.py lines 1015–1179)

Revenue, expenses, PO COGS, depreciation, and payroll all apply `_to_zar()` consistently. Payroll uses actual payslip totals filtered by period, falling back to estimates. ✓

The 6-month revenue **trend** inside this endpoint (lines 1119–1149) applies `_to_zar()` to revenue per month. Expenses in the trend exclude payroll (as intended — the trend shows Gross Profit; payroll is shown separately in the P&L section). The frontend correctly renders this as "Gross Profit" (`App_js_fixed.js` line 707). ✓

### `/v1/summary` (main.py lines 231–271)

Uses `_to_zar()` for revenue and outstanding totals. PO COGS and depreciation included. Payroll via actual payslip sum. Consistent with `/reports/dashboard`. ✓

---

## 3. Debtors (Accounts Receivable)

**Backend:** `GET /reports/debtors-aging` (payroll.py lines 1292–1352)  
**Frontend:** `Debtors` component (App_js_fixed.js lines 4497–4613)

**Status filter** — `Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])`. `InvoiceStatus` enum (database.py lines 36–40) only has four values: `draft`, `sent`, `paid`, `overdue` — there is no `pending` status. The filter is exhaustive for all receivable-outstanding states. ✓

**ZAR equivalents** — each invoice entry uses `round(_to_zar(inv), 2)` (line 1315). The frontend renders `inv.amount` directly, which is the ZAR-converted figure returned by the backend. ✓

**Aging buckets from `due_date`** — the aging loop (lines 1308–1335) reads `inv.due_date`. Invoices with `due_date = None` are placed in `not_due` (line 1321–1322 — audit fix note confirms the prior fallback to `created_at` was removed). Days overdue = `(now − due_date).days`. Buckets: <0 → not_due; 0–30 → current; 31–60 → 31_60; 61–90 → 61_90; >90 → over_90. ✓

**Paid invoices excluded** — the status filter excludes `paid` and `draft`. ✓

**AR reconciliation** — Reconciliation Rule 6 (payroll.py lines 821–841) compares journal account 1100 balance against the same `sent + overdue` invoice set using `_to_zar()`. Consistent. ✓

✓ No functional issues found. See cross-module section for the deletion gap that can corrupt the AR journal balance.

---

## 4. Creditors (Accounts Payable)

**Backend:** `GET /reports/creditors-aging` (payroll.py lines 1355–1449)  
**Frontend:** `Creditors` component (App_js_fixed.js lines 4616–4769)

**Status filter** — `PurchaseOrder.status.in_(["received", "partial"])`. Fully paid POs (status `"paid"`) are excluded. ✓

**Received-but-unpaid POs as outstanding creditors** — only `received` and `partial` POs appear. ✓

**Aging** — base date is `po.received_date` (fallback: `order_date`, then `created_at`). Due date = base + `supplier.payment_terms` days (default 30). Days overdue computed from due date, not from received_date directly. ✓

**Supplier bank details decrypted** — `decrypt_field()` applied to `sup.bank_name`, `sup.account_number`, `sup.branch_code` (lines 1409–1411) before returning. ✓

**Amounts** — `po.total_amount` (VAT-inclusive). Frontend column header is "Amount (incl. VAT)". ✓

**AP reconciliation** — Reconciliation Rule 7 (payroll.py lines 843–860) compares journal account 2000 balance against open PO totals (received + partial). Consistent with creditors-aging filter. ✓

✓ No functional issues found. See cross-module section for the deletion gap.

---

## 5. Cross-Module Journal Coverage

### Posting coverage

| Event | Posting function | Called from | Status |
|-------|-----------------|-------------|--------|
| Invoice raised | `post_invoice_raised()` | companies.py line 209 | ✓ |
| Invoice paid | `post_invoice_paid()` | companies.py line 245 | ✓ |
| Invoice COGS (inventory) | `post_invoice_cogs()` | companies.py line 212 | ✓ |
| Expense added | `post_expense()` | companies.py lines 310, 394, 609 | ✓ |
| Payroll run | `post_payroll()` | payroll.py line 336 | ✓ |
| PO received | `post_po_received()` | purchase_orders.py line 226 | ✓ |
| PO paid | `post_po_paid()` | purchase_orders.py line 291 | ✓ |
| Asset acquisition | `post_asset_acquisition()` | backfill + fixed_assets router | ✓ |
| Depreciation | `post_depreciation()` | backfill + fixed_assets router | ✓ |
| Asset disposal | `post_asset_disposal()` | backfill + fixed_assets router | ✓ |
| Stock adjustment | `post_stock_adjustment()` | inventory router | ✓ |

### Journal deletion gaps — CRITICAL

**Invoice deletion (companies.py lines 257–264):** The `DELETE /invoices/{id}` endpoint calls `db.delete(invoice)` with no journal reversal. Deleting an invoice leaves two orphaned journal entries:
- `post_invoice_raised`: DR Accounts Receivable (1100) / CR Sales Revenue (4000) — overstates both AR and Revenue permanently
- If the invoice was marked paid first: `post_invoice_paid`: DR Bank (1000) / CR AR (1100) — also orphaned

The AR Control Account reconciliation (Rule 6) will diverge by the deleted invoice's ZAR amount with no mechanism to detect or repair it other than manual journal entries.

**Expense deletion (companies.py lines 407–414):** The `DELETE /expenses/{id}` endpoint calls `db.delete(expense)` with no journal reversal. The orphaned entry (DR Expense / DR VAT Input / CR Bank) permanently understates the Bank account and overstates the expense account. Note: expense *edits* do post a reversal (`source="expense_reversal"`, line 375), but plain DELETE does not.

**PO deletion (purchase_orders.py lines 174–179):** The `DELETE /purchase-orders/{id}` endpoint has no status guard and no journal reversal. A `received` or `partial` PO can be deleted, leaving `post_po_received` entries (DR COGS / DR VAT Input / CR Accounts Payable) permanently in the journal. This overstates COGS and AP, and the AP Control Account reconciliation (Rule 7) will diverge.

---

## 6. Action Items

| # | Severity | Issue | File | Lines | Fix |
|---|----------|-------|------|-------|-----|
| 1 | **Critical** | Invoice deletion leaves orphaned journal entries (DR AR, CR Revenue, and if paid: DR Bank, CR AR) | `companies.py` | 257–264 | Before `db.delete(invoice)`, call `journal_engine.post_invoice_raised_reversal()` (new function: negate original entry) and if paid, `post_invoice_paid_reversal()`. Or add a guard preventing deletion of invoices with journal entries, requiring void/credit-note workflow instead. |
| 2 | **Critical** | Expense deletion leaves orphaned journal entries (DR Expense, DR VAT Input, CR Bank) | `companies.py` | 407–414 | Before `db.delete(expense)`, post a reversal journal entry (mirror of `post_expense` with debits/credits swapped), or reuse the existing reversal pattern from expense edits (line 375). |
| 3 | **High** | PO deletion has no status guard and no journal reversal — received/partial POs can be deleted, corrupting COGS and AP | `purchase_orders.py` | 174–179 | Add status check: raise 400 if `po.status in ("received", "partial", "paid")`. For paid POs that must be removed, require a reversal workflow. Post `post_po_received` reversal before deleting received/partial POs. |
| 4 | **Medium** | Legacy duplicate-expense risk: if any Expense records were manually created for the same PO cost before the no-auto-expense design was enforced, `total_expenses` is permanently overstated. Warning fires at runtime but does not block or flag historic data. | `payroll.py` | 499–537 | Run a one-time audit query: find Expense records whose (vendor, month, net amount ±5%) match a received PO. Flag for human review. Add a database-level `po_id` FK on `Expense` to formally link and prevent future duplication. |
| 5 | **Low** | `create_expense: bool = True` field in `POReceive` model is silently ignored — API callers passing `create_expense=true` will not receive an Expense record and may not realise this | `purchase_orders.py` | 186, 218–220 | Remove the `create_expense` and `expense_category` fields from the `POReceive` model, or document in the API response (`"expense_created": false, "note": "Costs recorded via journal only"`) that the field is deprecated. |

---

*Report generated automatically by ZuZan scheduled audit task. Next run: scheduled.*
