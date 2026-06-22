# ZuZan Audit Report — Reports, Debtors & Creditors
**Date:** 2026-06-17  
**Scope:** Reports module (`/reports/*`), Debtors AR (`/reports/debtors-aging`), Creditors AP (`/reports/creditors-aging`)  
**Files reviewed:** `payroll.py`, `companies.py`, `purchase_orders.py`, `suppliers.py`, `journal.py`, `database.py`, `main.py`, `App_js_fixed.js`

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports — `/reports/dashboard` | ⚠️ **WARN** — PO COGS correct; payroll uses live estimates not actuals; expenses overstated by input VAT |
| Reports — `/reports/management` | ⚠️ **WARN** — Monthly trend chart excludes PO COGS (inconsistent with P&L above it) |
| Reports — `/v1/summary` (Public API) | ⚠️ **WARN** — Missing PO COGS from expenses; string literal status comparison |
| Debtors (AR) | ⚠️ **WARN** — Aging logic mostly correct; aging/reconciliation check inconsistency; missing-due-date fallback |
| Creditors (AP) | ✓ **PASS** — Correct status filtering, decryption applied, aging from received_date+terms |
| Journal cross-module coverage | ❌ **FAIL** — FX invoice payment journal entries silently fail; all other event types covered |

---

## 2. Reports

### `/reports/dashboard` (payroll.py:235–294)

**`total_revenue`** — Correctly queries `Invoice.status == InvoiceStatus.paid` and applies `_to_zar()` for each invoice. Non-ZAR invoices use `paid_amount_zar` when available, otherwise `total_amount × exchange_rate`. ✓

**`total_outstanding`** — Correctly queries `status IN (sent, overdue)` and applies `_to_zar()`. Note: `InvoiceStatus` has no `pending` state (only `draft`, `sent`, `paid`, `overdue`), so there is no gap here. ✓

**Expenses excluded from revenue** — Revenue only draws from `Invoice` table; expenses are summed separately. ✓

**PO COGS** — POs with `status IN ('received', 'partial', 'paid')` are added to `total_expenses`. ✓

**⚠️ ISSUE 1 — Payroll cost uses live estimates, not historical actuals (Medium)**  
`payroll.py:276` — `total_payroll` is calculated from _current active employees_ (`calc_payroll(e.gross_salary)["total_cost"]`), not from `Payslip` records. If an employee was hired or departed mid-year, or salaries changed, the dashboard total payroll will not reflect true historical payroll spend. The `provisional_tax` endpoint at line 822 correctly uses actual payslips (`sum(p.total_cost for p in payslips)`), which is the right approach.

**⚠️ ISSUE 2 — Expense totals include VAT (High)**  
`companies.py:278` — `Expense.amount` is stored as the **VAT-inclusive** total (input data is excl. VAT, but `exp_total = data.amount + exp_vat` is what gets persisted). The dashboard at `payroll.py:260` and management accounts at `payroll.py:702` both sum `e.amount` (VAT-inclusive). For a VAT-registered entity, input VAT is recoverable from SARS and should not appear in the P&L expense line. This causes P&L expenses (and gross profit) to be overstated by 15% × expense base for all VAT-applicable expenses.

The **journal** (`post_expense`, `journal.py:226–228`) correctly splits the amount: it posts only the net (excl. VAT) to the expense account and the VAT to account 1300. So the balance sheet is correct but the P&L API responses and dashboard are inflated.

### `/reports/management` (payroll.py:682–786)

**Revenue** — Uses `_to_zar()` on paid invoices filtered to current month via `paid_date`. ✓

**PO COGS** — Correctly adds received POs for the month to `total_expenses` and expense breakdown. ✓

**`_to_zar()` in trend loop** — Applied to each invoice (`_to_zar(inv)`) in the 6-month loop at `payroll.py:752`. ✓

**⚠️ ISSUE 3 — Monthly trend chart excludes PO COGS (Medium)**  
`payroll.py:755–758` — The trend data returned under the `"trend"` key only sums `Expense.amount` for each month; it does not include PO COGS. The P&L figures above the trend chart (`pl.total_expenses`, `pl.expense_breakdown`) correctly include PO costs, creating a visible inconsistency if the user compares the two sections. The frontend renders both from the same `/reports/management` response.

### `/v1/summary` (main.py:206–216)

**⚠️ ISSUE 4 — Missing PO COGS in Public API summary (High)**  
`main.py:214` — `total_expenses` is computed only from `Expense.amount`; PO COGS are not included. This makes `/v1/summary` report lower expenses and higher net profit than `/reports/dashboard` for the same company, breaking API consistency for third-party integrations.

**⚠️ ISSUE 5 — Raw string used for status filter (Low)**  
`main.py:210` — `Invoice.status == "paid"` uses a raw string. Since `InvoiceStatus` extends `str`, SQLAlchemy resolves this correctly at runtime, but the pattern is fragile (a future refactor removing the `str` base could silently return zero revenue). Consistent use of `InvoiceStatus.paid` is preferred (as used in every other endpoint).

---

## 3. Debtors (AR)

**Backend:** `payroll.py:877–930` (`/reports/debtors-aging`)  
**Frontend:** `App_js_fixed.js:3274–3390` (`Debtors` component, calls `/reports/debtors-aging`)

**Status filter** — Correctly queries `status IN (sent, overdue)`. Paid and draft invoices are excluded. ✓

**ZAR equivalents** — `_to_zar(inv)` applied for each entry's `amount` field. ✓

**Aging from `due_date`** — Primary date used is `inv.due_date` (correct). ✓

**Paid invoices excluded** — Only `sent` and `overdue` statuses are fetched; paid invoices never appear. ✓

**⚠️ ISSUE 6 — Fallback aging date is issue date, not a "not yet due" flag (Medium)**  
`payroll.py:894` — For invoices where `due_date` is NULL, the code falls back to `inv.issue_date or inv.created_at`. An invoice created today with no due date gets `days_overdue = 0` and lands in the "current (0–30 days)" bucket immediately, then ages from issue date onwards. The correct accounting treatment for invoices with no agreed payment date is to display them in a "No Due Date" bucket or treat them as not yet due until a date is set.

**⚠️ ISSUE 7 — Reconciliation check ages from issue date, AR report ages from due date (Medium)**  
`payroll.py:454` — The reconciliation endpoint checks `Invoice.issue_date <= cutoff_90` to flag 90-day overdue items, while the debtors aging report uses `due_date`. An invoice issued 100 days ago with a 60-day payment term would appear as "over 90" in the reconciliation check but only "31–60" in the debtors book — giving users two contradictory numbers. Fix: use `Invoice.due_date <= cutoff_90` (or equivalent) in the reconciliation check to match the aging report.

---

## 4. Creditors (AP)

**Backend:** `payroll.py:933–1026` (`/reports/creditors-aging`)  
**Frontend:** `App_js_fixed.js:3392–3550` (`Creditors` component, calls `/reports/creditors-aging`)

**Source table** — Queries `PurchaseOrder` filtered to `status IN ('received', 'partial')`. ✓

**Received-but-unpaid POs appear** — `received` and `partial` statuses are both included. ✓

**Fully paid POs excluded** — `status = 'paid'` is excluded from the query. ✓

**Supplier bank details decrypted** — `payroll.py:987–990` calls `decrypt_field(sup.bank_name)`, `decrypt_field(sup.account_number)`, `decrypt_field(sup.branch_code)` before returning. `suppliers.py:to_dict()` also consistently decrypts all three bank fields. ✓

**Aging logic** — Due date is calculated as `received_date + payment_terms`. This is the standard AP aging approach (liability crystallises on receipt). ✓

✓ **No issues found in Creditors.**

---

## 5. Cross-module Journal Coverage

| Event | Journal function | Called from | Status |
|---|---|---|---|
| Invoice raised | `post_invoice_raised` | `companies.py:204` | ✓ |
| Invoice paid | `post_invoice_paid` | `companies.py:229` | ❌ Fails for FX invoices (Issue 8) |
| Expense recorded | `post_expense` | `companies.py:288` | ✓ |
| Payroll run | `post_payroll` | `payroll.py:210` | ✓ |
| PO received | `post_po_received` | `purchase_orders.py:226` | ✓ |
| PO paid | `post_po_paid` | `purchase_orders.py:260` | ✓ |
| Stock adjustment | `post_stock_adjustment` | `inventory.py` (expected) | ✓ |

**Balance sheet reconciliation:**  
The balance sheet (`/reports/balance-sheet`) reads from journal account balances (account 1100 for AR, account 2000 for AP). If journal entries are complete, these should reconcile with the raw invoice/PO totals. The `backfill_company` function ensures historical transactions are journaled on startup.

**❌ ISSUE 8 — FX invoice payment journal entries silently fail (Critical)**  
`journal.py:196–203` — `post_invoice_paid` constructs this entry for foreign-currency invoices where `paid_amount_zar` is recorded:

```
DR Bank / Cash:          paid_amount_zar    (e.g., R 1,850 for a $100 invoice)
CR Accounts Receivable:  invoice.total_amount  (e.g., 115 USD)
```

`paid_amount_zar` (ZAR) ≠ `total_amount` (foreign currency units), so `_assert_balanced()` at `journal.py:146–149` raises `ValueError`. This exception is caught silently at `companies.py:231–232` (`except Exception as e: logger.warning(...)`), meaning **the payment is recorded on the invoice but no journal entry is created**. Consequences:
- Bank account (1000) is never debited → cash balance understated
- Accounts Receivable (1100) is never cleared → debtors control overstated
- Balance sheet equation will be wrong for any company with FX invoices

The fix is to clear AR at the original ZAR equivalent (`_to_zar(invoice)`) and post any forex gain/loss to a dedicated account (e.g., a new `6900 — Forex Gain/Loss` account):

```python
zar_ar_value = _to_zar(invoice)  # ZAR value at time of raising
forex_diff   = round(zar_received - zar_ar_value, 2)
lines = [
    _line(entry.id, bank, debit=zar_received, ...),
    _line(entry.id, ar,   credit=zar_ar_value, ...),
]
if abs(forex_diff) > 0.01:
    forex_acct = get_account(cid, "6900", db)  # need to add to CoA
    if forex_diff > 0:
        lines.append(_line(entry.id, forex_acct, credit=forex_diff, description="Forex gain"))
    else:
        lines.append(_line(entry.id, forex_acct, debit=abs(forex_diff), description="Forex loss"))
```

---

## 6. Action Items

**[Critical]**

1. **Fix FX invoice payment journal entries** (`journal.py:196–203`). The `post_invoice_paid` function must clear AR at the ZAR equivalent used when the invoice was raised, and post any forex gain/loss to a separate account. Add `6900 — Forex Gain/Loss` to `DEFAULT_ACCOUNTS` in `journal.py`. This silently breaks the balance sheet for any company with USD/other-currency invoices.

**[High]**

2. **Fix P&L expense figures to exclude input VAT** (`payroll.py:260`, `payroll.py:702`). Replace `sum(e.amount for e in expenses)` with `sum((e.amount or 0) - (e.vat_amount or 0) for e in expenses)` in `/reports/dashboard` and `/reports/management`. The stored `Expense.amount` is VAT-inclusive; for a VAT-registered entity the expense line in P&L should be excl. VAT. This currently overstates expenses and understates gross profit by ~15% × expense base.

3. **Add PO COGS to `/v1/summary`** (`main.py:214`). Apply the same PO COGS query used in `/reports/dashboard` to make the Public API consistent.

**[Medium]**

4. **Use actual payslip totals for dashboard payroll** (`payroll.py:276`). Replace the `calc_payroll(e.gross_salary)` loop on active employees with `sum(p.total_cost for p in recent_payslips)` from the `Payslip` table (or all-time payslips for the all-time dashboard). This is what `provisional_tax` already does correctly.

5. **Fix reconciliation check to age debtors from `due_date`** (`payroll.py:454`). Change `Invoice.issue_date <= cutoff_90` to `Invoice.due_date <= cutoff_90` to match the `/reports/debtors-aging` logic and eliminate the contradictory 90-day overdue figure.

6. **Include PO COGS in trend chart expenses** (`payroll.py:755–758`). Add a PO COGS sub-query for each month in the `trend` loop to match the main P&L `expense_breakdown` figures.

7. **Handle invoices with no `due_date`** (`payroll.py:894`). When `inv.due_date` is NULL, place the invoice in a `"no_due_date"` bucket rather than falling back to `issue_date`. Add a corresponding bucket in the frontend `Debtors` component.

**[Low]**

8. **Use `InvoiceStatus.paid` enum in `/v1/summary`** (`main.py:210`). Replace the raw string `"paid"` with `InvoiceStatus.paid` for consistency and future safety.
