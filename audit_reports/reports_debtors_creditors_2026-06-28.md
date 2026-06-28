# ZuZan Audit Report — Reports, Debtors & Creditors
**Date:** 2026-06-28  
**Files reviewed:**
- `App_js_fixed.js` (frontend)
- `zuzan-backend/payroll.py` (Reports router)
- `zuzan-backend/companies.py` (Invoice creation & payment)
- `zuzan-backend/purchase_orders.py` (PO lifecycle)
- `zuzan-backend/journal.py` (double-entry engine)
- `zuzan-backend/main.py` (`/v1/summary` public API)
- `zuzan-backend/database.py` (models & `InvoiceStatus` enum)

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports — `/reports/dashboard` | ✅ PASS — revenue, outstanding, expenses, payroll and PO COGS all correct; `_to_zar()` applied consistently |
| Reports — `/reports/management` | ✅ PASS — same correctness; trend loop also applies `_to_zar()` and depreciation |
| Reports — `/v1/summary` (public API) | ✅ PASS — mirrors dashboard logic faithfully |
| Debtors (Accounts Receivable) | ✅ PASS — correct status filter, ZAR display, `due_date`-based aging, paid invoices excluded |
| Creditors (Accounts Payable) | ✅ PASS — correct received-but-unpaid filter, paid POs excluded, bank fields decrypted |
| Cross-module journal coverage | ✅ PASS — all five event types post to journal in real time, with one structural concern (see item 1 below) |

**Overall: no data-accuracy failures in the reporting layer itself. However two HIGH severity defects exist in adjacent code that can produce silent data integrity gaps.**

---

## 2. Reports

### 2.1 `/reports/dashboard` — `payroll.py`

**`total_revenue` (lines 439–443)**
- Filters `Invoice.status == InvoiceStatus.paid` ✅
- Applies `_to_zar()` to every invoice ✅
- `_to_zar()` logic (lines 17–24): uses `paid_amount_zar` if set, otherwise `total_amount × exchange_rate`, ZAR falls through to `total_amount` ✅
- Expenses are summed separately; no cross-contamination ✅

**`total_outstanding` (lines 445–449)**
- Filters `status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])` ✅
- Applies `_to_zar()` ✅
- Note: the `InvoiceStatus` enum (`database.py` line 36) has no `pending` value — `sent` serves as "pending/awaiting payment" (per the inline comment). The filter is semantically correct.

**Expenses (lines 451–471)**
- All expenses ex-VAT: `e.amount - (e.vat_amount or 0)` ✅
- PO COGS: received/partial/paid POs, ex-VAT ✅
- Depreciation from `DepreciationEntry` included ✅
- Payroll: sums ALL payslips including terminated employees (lines 479–489); falls back to estimated if no payslips exist ✅
- Double-count detection for PO + manual expense overlap present (lines 501–542) — raises `po_duplicate_warning` in response ✅

**`/reports/monthly-trend` (lines 568–637)**
- `_to_zar()` applied to paid invoices per month ✅
- Expenses ex-VAT per month ✅
- PO COGS by `received_date` per month ✅
- Depreciation per `DepreciationEntry.period` per month ✅

### 2.2 `/reports/management` — `payroll.py` (lines 1020–1191)

- Revenue via `_to_zar()` on paid invoices in date range ✅
- Expenses ex-VAT in date range ✅
- PO COGS by `received_date`, ex-VAT ✅
- Depreciation via `DepreciationEntry.period` range ✅
- Trend section (lines 1131–1161) also applies `_to_zar()`, PO COGS, and depreciation consistently ✅
- Payroll from payslips for ALL employees (including terminated) within period ✅

**⚠️ MEDIUM — VAT201 uses `created_at` instead of `issue_date` (lines 1499–1504)**

```python
all_invoices = db.query(Invoice).filter(
    Invoice.company_id == cid,
    Invoice.created_at >= start,   # ← should be issue_date
    Invoice.created_at < end,
```

For VAT, the tax point is the invoice date (`issue_date`), not the database creation timestamp. Backdated invoices or invoices imported in bulk would be reported in the wrong VAT period.

**⚠️ MEDIUM — Cash flow omits VAT remittances to SARS (lines 917–964)**

The `/reports/cash-flow` endpoint includes VAT collected (via `_to_zar()` on total_amount for receipts) but has no line item for VAT paid to SARS. This overstates net operating cash flow by the net VAT payable amount. A `cash_paid_to_sars_vat` line should be added.

### 2.3 `/v1/summary` — `main.py` (lines 245–287)

- Imports and applies `_to_zar()` from `payroll.py` ✅
- Revenue: paid invoices via `_to_zar()` ✅
- Expenses: ex-VAT ✅
- PO COGS: received/partial/paid, ex-VAT ✅
- Depreciation: included ✅
- Payroll: all payslips summed ✅
- Outstanding: `sent` + `overdue` via `_to_zar()` ✅

### 2.4 Balance sheet omits income tax payable (lines 674–681)

The balance sheet calculation hardcodes only accounts 2000, 2100, 2200, 2210, 2220 in `total_liabilities`. Account **2126 — Income Tax Payable** and **2127 — Provisional Tax Payable** are defined in the chart of accounts (journal.py DEFAULT_ACCOUNTS) and exist in the frontend CoA display (App_js_fixed.js line 2126), but are never read in the balance sheet calculation. Any manually posted income tax liabilities are omitted from `total_liabilities`, causing a balance sheet understatement and potentially a false `balanced=True` result.

---

## 3. Debtors (Accounts Receivable)

### 3.1 Frontend — `App_js_fixed.js`

- `Debtors` component (line 4674) calls `GET /reports/debtors-aging` on mount ✅
- Refreshes when `live.invoices` changes (line 4684–4688) — triggers re-fetch after invoice payment ✅
- Displays amounts from `entry.amount` which is populated via `_to_zar()` on the backend ✅
- Aging buckets: Not Yet Due / 0–30 / 31–60 / 61–90 / 90+ (lines 4690–4695) match backend bucket keys ✅

### 3.2 Backend — `/reports/debtors-aging` (payroll.py lines 1304–1364)

- **Status filter**: `sent` and `overdue` (line 1313–1315) — correct; `draft` and `paid` excluded ✅
- **ZAR equivalents**: `_to_zar(inv)` applied to every entry (line 1327) ✅
- **Aging from `due_date`**: explicitly uses `inv.due_date` (line 1323), with a documented fix comment stating the `issue_date`/`created_at` fallback was removed ✅
- **No `due_date`**: invoices without a due date go into `not_due` bucket rather than overstating overdue (lines 1332–1334) ✅
- **Paid invoices excluded**: only `sent` and `overdue` are queried; `paid` invoices are never in the result ✅

✓ No issues found in the Debtors section.

---

## 4. Creditors (Accounts Payable)

### 4.1 Frontend — `App_js_fixed.js`

- `Creditors` component (line 4800) calls `GET /reports/creditors-aging` on mount ✅
- Refreshes when `live.purchaseOrders` changes (line 4811–4815) ✅
- Displays amounts per PO entry from backend ✅

### 4.2 Backend — `/reports/creditors-aging` (payroll.py lines 1367–1461)

- **Source**: queries `PurchaseOrder` table filtered to `status.in_(["received", "partial"])` (lines 1383–1386) — received-but-unpaid POs only ✅
- **Fully paid POs excluded**: status `"paid"` is not in the filter ✅
- **Aging**: calculated from `received_date or order_date or created_at` + supplier `payment_terms` days (lines 1406–1415) ✅
- **Bank details decryption**: `decrypt_field()` called for `bank_name`, `account_number`, `branch_code` on the supplier record (lines 1421–1424); gracefully handles `None` supplier (no decrypt attempt) ✅
- **Amounts**: uses `po.total_amount` (VAT-inclusive) — consistent with AP control account reconciliation in `payroll.py` line 856 and with `post_po_received` crediting AP for `total_amount` ✅

✓ No issues found in the Creditors section.

---

## 5. Cross-module Journal Coverage

| Event | Posting function | Triggered from |
|---|---|---|
| Invoice raised | `post_invoice_raised` | `companies.py` line 209 ✅ |
| Invoice paid | `post_invoice_paid` | `companies.py` line 245 ✅ |
| Expense recorded | `post_expense` | `companies.py` (expense create endpoint) ✅ |
| Payroll run | `post_payroll` | `payroll.py` line 334–343 ✅ |
| PO received | `post_po_received` | `purchase_orders.py` line 249 ✅ |
| PO paid | `post_po_paid` | `purchase_orders.py` line 314 ✅ |
| Depreciation | `post_depreciation` | `fixed_assets.py` (run depreciation endpoint) ✅ |
| Asset acquisition | `post_asset_acquisition` | `fixed_assets.py` (asset create endpoint) ✅ |

All five event categories in the audit checklist are covered by real-time journal posting. The backfill mechanism (`journal.py` `backfill_company`) also runs at startup for companies with no prior journal entries.

**AR Control Account (1100):** Reconciliation rule 6 (payroll.py lines 826–846) compares journal AR balance with outstanding invoices via `_to_zar()` — consistent methodology ✅

**AP Control Account (2000):** Reconciliation rule 7 (lines 848–865) compares journal AP balance with open PO `total_amount` — consistent with how `post_po_received` credits AP ✅

---

## 6. Action Items

### 🔴 High — Fix immediately

**1. Invoice payment: `db.commit()` before journal post breaks rollback atomicity**  
`companies.py` ~line 241:
```python
db.commit()   # ← invoice status committed as "paid" BEFORE journal entry
if not was_paid and invoice.status == InvoiceStatus.paid:
    try:
        journal_engine.post_invoice_paid(invoice, db)
        db.commit()
    except Exception as e:
        ...
        db.rollback()   # ← only undoes the journal attempt; invoice status is already committed
```
If `post_invoice_paid` raises, the invoice is permanently marked "paid" with no corresponding journal entry. This silently breaks the AR control account reconciliation and causes any company hitting this edge case to report an AR imbalance with no obvious cause.  
**Fix:** Move the journal call inside the same transaction as the invoice update, committing once only after both succeed.

**2. Frontend payroll calculator: backslash keys in `TAX_YEARS` object**  
`App_js_fixed.js` lines 126–137:
```javascript
const TAX_YEARS = {
  "2024\2025": { ... },   // ← \2 and \0 are JS octal escape sequences
  "2025\2026": { ... },
  "2026\2027": { ... },
};
const CURRENT_TAX_YEAR = "2026/2027";   // ← forward slash
```
JavaScript interprets `\2`, `\0`, `\2` as octal escape characters, so none of the keys match `CURRENT_TAX_YEAR`. When `calcPayroll()` is called, `yr` resolves to `undefined`, causing a `TypeError` on `yr.uifCeil`. The frontend payroll preview/calculator tab crashes silently.  
**Fix:** Replace all backslashes with forward slashes in the TAX_YEARS keys: `"2024/2025"`, `"2025/2026"`, `"2026/2027"`.  
Note: The backend `payroll.py` uses forward slashes throughout and is unaffected.

### 🟠 Medium — Fix in next sprint

**3. VAT201 filters invoices by `created_at` instead of `issue_date`**  
`payroll.py` lines 1499–1504. Tax point for SA VAT is the invoice date (`issue_date`), not the database creation timestamp. Backdated invoices, or invoices created in the system after the fact, will be allocated to the wrong VAT period.  
**Fix:** Replace `Invoice.created_at` with `Invoice.issue_date` in the VAT201 query filter.

**4. Balance sheet omits income tax payable accounts (2126, 2127) from `total_liabilities`**  
`payroll.py` lines 674–681. The hardcoded liability sum only reads accounts 2000, 2100, 2200, 2210, 2220. Accounts 2126 (Income Tax Payable) and 2127 (Provisional Tax Payable) exist in the chart of accounts but are never read.  
**Fix:** Add `bal("2126")` and `bal("2127")` to the `total_liabilities` sum. Alternatively, query all accounts of type `liability` dynamically.

**5. Cash flow statement omits VAT remittances to SARS**  
`payroll.py` lines 917–964. Cash receipts include VAT collected (via `total_amount` in `_to_zar()`), but there is no corresponding outflow for VAT paid to SARS. Net operating cash flow is overstated by the net VAT payable balance.  
**Fix:** Add a `cash_paid_to_sars_vat` line using `net_vat_payable` from the VAT position query, or query VAT201 payments from the `Expense` table filtered to a VAT category.

### 🟡 Low — Address before GA

**6. AP aging display uses VAT-inclusive totals; document as intentional**  
`payroll.py` line 1432–1443. The Creditors view shows `po.total_amount` (VAT-inclusive) while the P&L uses ex-VAT PO COGS. This is correct accounting (AP = gross liability) but may confuse users comparing the Creditors total to the P&L. Add a note in the UI tooltip or documentation.

**7. `InvoiceStatus` has no `pending` value — update documentation**  
`database.py` line 36–40. The enum is `draft / sent / paid / overdue`. External checklists and support documentation that reference `status = 'pending'` will be misleading. The `sent` status serves as pending. Update all external references to use `sent`.
