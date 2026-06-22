# ZuZan Audit Report — Reports, Debtors & Creditors
**Date:** 2026-06-18  
**Scope:** Reports (dashboard, management, monthly-trend), Debtors (AR), Creditors (AP), Journal cross-module coverage  
**Files reviewed:** `payroll.py`, `companies.py`, `purchase_orders.py`, `journal.py`, `database.py`, `main.py`, `App_js_fixed.js`

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports — `/reports/dashboard` | ❌ **FAIL** — `func` not imported; NameError crashes endpoint when employees exist |
| Reports — `/reports/management` | ⚠️ **WARN** — Expenses VAT-inclusive (inconsistent with dashboard); trend loop missing PO COGS |
| Reports — `/reports/monthly-trend` | ✅ Pass — `_to_zar()` applied; PO COGS included |
| Reports — `/v1/summary` | ✅ Pass — `_to_zar()` applied; expenses ex-VAT; PO COGS included |
| Debtors (AR) | ✅ Pass — correct filters, ZAR equivalents, aging from `due_date`, paid excluded |
| Creditors (AP) | ✅ Pass — received/partial only, paid excluded, bank decrypted |
| Cross-module Journal | ⚠️ **WARN** — Bank import expenses missing journal entries |

---

## 2. Reports

### 2.1 `/reports/dashboard` — `payroll.py` lines 235–301

**CRITICAL — `func` not imported (NameError)**

`payroll.py` line 277 calls `func.sum(Payslip.total_cost)` but `func` is never imported. The only SQLAlchemy import is `from database import get_db, ...`; `func` from `sqlalchemy import func` is absent. When any active employees exist, the endpoint raises `NameError: name 'func' is not defined` and returns HTTP 500.

```python
# payroll.py line 277 — func is undefined
actual_payslips_total = db.query(func.sum(Payslip.total_cost)).filter(...)
```

Fix: add `from sqlalchemy import func` to `payroll.py` imports.

**Revenue — ✓ Correct**  
`total_revenue` sums only `InvoiceStatus.paid` invoices and applies `_to_zar()`. Lines 246–248.

**Outstanding — ✓ Correct**  
`total_outstanding` covers `sent` + `overdue` (the two non-draft, non-paid statuses in the enum) and applies `_to_zar()`. Lines 250–254. Note: `InvoiceStatus` has no `pending` value — enum is `draft/sent/paid/overdue` — so `sent` is the correct "live but unpaid" status.

**Expenses — ✓ Correct**  
`total_expenses` uses `e.amount - (e.vat_amount or 0)` (ex-VAT). Line 260. PO COGS added separately. Lines 262–270.

**Payroll — ✓ Correct in fallback path**  
Falls back to `calc_payroll(e.gross_salary)["total_cost"]` when `actual_payslips_total` is None (which it always will be due to the `func` crash). Fix the import and both paths work correctly.

---

### 2.2 `/reports/management` — `payroll.py` lines 701–805

**HIGH — Expenses are VAT-inclusive; inconsistent with `/reports/dashboard`**

`total_expenses` at line 721 sums `e.amount` for each expense, which is stored VAT-inclusive (the creation endpoint sets `amount = data.amount + vat`, `companies.py` line 278). The dashboard uses `e.amount - (e.vat_amount or 0)`, i.e., ex-VAT. The two P&L endpoints report different expense figures for the same underlying data.

```python
# payroll.py line 721 — VAT-inclusive (wrong for P&L)
total_expenses = round(sum(e.amount for e in expenses), 2)

# payroll.py line 260 — ex-VAT (correct for P&L)
total_expenses = sum(e.amount - (e.vat_amount or 0) for e in expenses)
```

The `expense_by_cat` breakdown (lines 723–726) has the same issue.

**HIGH — Trend loop excludes PO COGS**

The 6-month trend loop inside `/reports/management` (lines 762–777) computes expenses as `ex.amount` only — no PO COGS are added. The standalone `/reports/monthly-trend` endpoint (lines 304–363) correctly adds PO COGS for each month. The two trend arrays will diverge whenever there are received POs.

```python
# payroll.py lines 774–777 — no PO COGS added in trend
exp = round(sum(ex.amount for ex in db.query(Expense)...), 2)
trend.append({"month":..., "revenue": rev, "expenses": exp, ...})
```

**Revenue — ✓ Correct**  
`revenue` applies `_to_zar()` on paid invoices, filtered to current month. Lines 710–715.

**Payroll — MEDIUM — Uses estimated cost, not actual payslips**  
`total_payroll_cost` at line 745 always recalculates from `calc_payroll()` on live salary figures rather than querying this month's actual payslips. This will diverge if salaries changed mid-month or if the payroll run has not been executed yet.

---

### 2.3 `/reports/reconciliation` — `payroll.py` lines 447–595

**MEDIUM — Gross Margin Health uses VAT-inclusive expenses**

Lines 570–573: `total_exp = round(sum(e.amount for e in all_expenses), 2)` is VAT-inclusive. When compared against revenue (which is VAT-exclusive equivalent via `_to_zar()`), the expense ratio is overstated by ~15%, inflating the health warning threshold.

---

### 2.4 `/reports/monthly-trend` — `payroll.py` lines 304–363

✓ Applies `_to_zar()` on revenue. Lines 329–335.  
✓ Expenses ex-VAT via `exp.amount - (exp.vat_amount or 0)`. Lines 337–342.  
✓ PO COGS added per month by `received_date`. Lines 344–354.

---

### 2.5 `/v1/summary` — `main.py` lines 206–227

✓ `_to_zar()` imported from `payroll` and applied. Lines 209–213.  
✓ Expenses ex-VAT: `e.amount - (e.vat_amount or 0)`. Lines 215–216.  
✓ PO COGS included for `received/partial/paid` POs. Lines 218–225.  
✓ Expenses are explicitly excluded from revenue (separate sum). ✓

---

## 3. Debtors (Accounts Receivable)

**Backend:** `payroll.py` `/reports/debtors-aging` lines 896–948  
**Frontend:** `App_js_fixed.js` `function Debtors` lines 3274–3390

**Filter — ✓ Correct**  
Queries `Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])`. Paid and draft invoices are excluded. Lines 905–908.

**ZAR equivalents — ✓ Correct**  
Each entry uses `round(_to_zar(inv), 2)` for the `amount` field. Line 916. Frontend displays this value directly (`inv.amount`), not the raw foreign-currency field.

**Aging from `due_date` — ✓ Correct**  
`due = inv.due_date or inv.issue_date or inv.created_at`. Primary sort key is `due_date`; `issue_date` and `created_at` are fallbacks when `due_date` is null. `days_overdue` is computed as `(now - due).days`. Lines 913–914.

**Paid invoices excluded — ✓ Correct**  
Status filter excludes `paid` and `draft`. Paid invoices cannot appear in outstanding buckets.

**Balance sheet reconciliation**  
The AR account (code 1100) balance in the journal should equal the debtors-aging `grand` total. These will match as long as all invoices have journal entries — which is guaranteed by the creation hook in `companies.py` line 203 and the backfill in `journal.py` lines 383–397.

---

## 4. Creditors (Accounts Payable)

**Backend:** `payroll.py` `/reports/creditors-aging` lines 952–1045  
**Frontend:** `App_js_fixed.js` `function Creditors` lines 3393–3535

**Source table — ✓ Correct**  
Pulls from `PurchaseOrder` filtered `status.in_(["received", "partial"])`. Lines 968–971. Supplier invoice entries are not a separate model — POs serve as the AP source.

**Received-but-unpaid POs — ✓ Correct**  
`received` and `partial` statuses represent delivered goods not yet paid. ✓

**Fully paid POs excluded — ✓ Correct**  
Status `paid` is excluded from the filter. ✓

**Supplier bank details decrypted — ✓ Correct**  
`decrypt_field(sup.bank_name)`, `decrypt_field(sup.account_number)`, `decrypt_field(sup.branch_code)` are called before including the fields in the vendor map. Lines 1006–1010. The `decrypt_field` function from `crypto.py` is imported at line 963.

**Aging from due date — ✓ Correct**  
`due_date = base_date + timedelta(days=payment_terms)` where `base_date` is `received_date`. Lines 991–992. Payment terms come from the supplier record (default 30 days). ✓

---

## 5. Cross-Module Journal Coverage

| Transaction type | Posting function | Where called | Status |
|---|---|---|---|
| Invoice raised | `post_invoice_raised` | `companies.py` line 203 | ✅ |
| Invoice paid | `post_invoice_paid` | `companies.py` line 228 | ✅ |
| Expense added | `post_expense` | `companies.py` line 287 | ✅ |
| Payroll run | `post_payroll` | `payroll.py` line 209 | ✅ |
| PO received | `post_po_received` | `purchase_orders.py` line 225 | ✅ |
| PO paid | `post_po_paid` | `purchase_orders.py` line 259 | ✅ |
| Stock adjustment | `post_stock_adjustment` | inventory module (backfill confirmed) | ✅ |
| **Bank import expense** | — | `companies.py` lines 458–493 | ❌ **MISSING** |

**WARN — Bank statement import creates Expense rows without journal entries**

The `POST /bank/import` endpoint (`companies.py` lines 443–495) creates `Expense` objects directly via `db.add(expense)` + `db.commit()` but never calls `journal_engine.post_expense()`. Any expense imported from a bank statement is absent from the double-entry ledger: the Bank/Cash (1000) account is not credited and no expense account is debited. This silently understates costs in the trial balance and balance sheet while the expense appears in the P&L expense sum (which reads directly from the `expenses` table).

**Balance sheet accounts — Debtors & Creditors Control**

- Debtors Control (account 1100): Sourced from journal (all `post_invoice_raised` DR minus `post_invoice_paid` CR). Should equal the debtors-aging grand total for all companies that have been backfilled. The startup backfill in `main.py` lines 21–36 handles companies with no prior entries. ✓  
- Creditors Control (account 2000): Sourced from journal (`post_po_received` CR minus `post_po_paid` DR). Should equal the sum of all open (received/partial) POs. ✓ Gap: if bank-imported expenses were meant to represent supplier payments, they would not clear AP — but since imports only create expenses (not AP-clearing entries), this gap is contained to operating expenses, not AP.

---

## 6. Action Items

| # | Severity | File | Description |
|---|---|---|---|
| 1 | **Critical** | `payroll.py` line 5 | Add `from sqlalchemy import func` to imports. Without it, `/reports/dashboard` raises `NameError` for any company with active employees. |
| 2 | **High** | `payroll.py` line 721 | Change `e.amount` to `e.amount - (e.vat_amount or 0)` in `/reports/management` expense sum to match the dashboard's ex-VAT treatment. Apply same fix to `expense_by_cat` loop (line 726). |
| 3 | **High** | `payroll.py` lines 774–777 | Add PO COGS to the trend loop inside `/reports/management`. Mirror the pattern from `/reports/monthly-trend` lines 344–354 (filter by `received_date` within each month). |
| 4 | **High** | `companies.py` line 480 | After `db.commit()` in the bank import loop, call `journal_engine.post_expense(expense, db)` for each created expense to ensure bank-imported costs are recorded in the double-entry ledger. |
| 5 | **Medium** | `payroll.py` line 571 | Fix Gross Margin Health check to use ex-VAT expenses: `sum(e.amount - (e.vat_amount or 0) for e in all_expenses)`. |
| 6 | **Medium** | `payroll.py` line 745 | `/reports/management` payroll cost should query actual payslips for the current month (like `/reports/cash-flow` does at line 620) rather than re-running `calc_payroll()` estimates. |
| 7 | **Low** | `payroll.py` trend loop line 774 | Align expense treatment in management trend with dashboard: use `ex.amount - (ex.vat_amount or 0)` instead of `ex.amount`. |
