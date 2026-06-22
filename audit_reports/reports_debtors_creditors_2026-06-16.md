# ZuZan Audit Report — Reports, Debtors & Creditors
**Date:** 2026-06-16  
**Scope:** Reports (`payroll.py` `/reports/*`), Debtors (AR), Creditors (AP), cross-module journal consistency  
**Files audited:**  
- Frontend: `App_js_fixed.js`  
- Backend: `payroll.py`, `companies.py`, `purchase_orders.py`, `journal.py`, `database.py`, `main.py`

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports — `/reports/dashboard` | ⚠️ FAIL — expenses VAT-inclusive, payroll uses projection not actuals, trend misses PO COGS |
| Reports — `/reports/management` | ⚠️ FAIL — same VAT issue; trend chart inconsistent with headline P&L |
| Reports — `/v1/summary` (main.py) | ✓ PASS — `_to_zar()` applied correctly |
| Debtors (AR) | ⚠️ PARTIAL — main aging view correct; reconciliation check ages from wrong date field |
| Creditors (AP) | ✓ PASS — correct filtering, decryption, and aging logic |
| Cross-module journal | ⚠️ FAIL — foreign-currency invoice payment entries silently fail and are never posted |

---

## 2. Reports

### `/reports/dashboard` and `/reports/management` (payroll.py)

**✓ `total_revenue`** — Correctly queries `Invoice.status == InvoiceStatus.paid` and applies `_to_zar()` for every invoice. For paid foreign-currency invoices uses `paid_amount_zar` when available, falling back to `amount × exchange_rate`. Revenue is not contaminated by expenses. (payroll.py:247–248, 696)

**✓ `total_outstanding`** — Correctly queries `status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])` and applies `_to_zar()`. Covers all unpaid non-draft invoices. No `pending` status exists in `InvoiceStatus` enum (database.py:36–40: draft/sent/paid/overdue), so the filter is complete. (payroll.py:250–254, 735–739)

**✗ HIGH — Expenses are summed VAT-inclusive, overstating `total_expenses` by ~13% for VAT-registered entities.**  
When an expense is created, `companies.py:271–272` stores `amount = data.amount + vat_amount` (the VAT-inclusive total). Reports then sum `e.amount` directly: `sum(e.amount for e in expenses)` (payroll.py:259–260, 702). This means reported expenses include the 15% VAT component that is recoverable from SARS. For a business with R100,000 net expenses, the report will show R115,000 — inflating expenses and understating gross profit by 13%. The double-entry journal handles this correctly (journal.py:215–217 splits net and VAT into separate accounts), but the P&L figure is wrong.  
**Affected endpoints:** `/reports/dashboard`, `/reports/management`, `/reports/monthly-trend`, `/reports/cash-flow`, `/reports/provisional-tax`

**✗ MEDIUM — Dashboard `total_payroll` uses projected salary, not actual payslip records.**  
payroll.py:276: `total_payroll = sum(calc_payroll(e.gross_salary)["total_cost"] for e in employees)` — this re-computes payroll from active employees' current salaries rather than summing committed `Payslip.total_cost` records. If a salary was raised mid-period or an employee terminated after a payslip was issued, the dashboard figure will differ from the actual cost incurred. The `provisional_tax` endpoint correctly uses `Payslip.total_cost` (payroll.py:826). The dashboard should use the same approach.

**✗ MEDIUM — Monthly trend excludes PO COGS; management P&L headline includes them.**  
The trend loop in `/reports/monthly-trend` (payroll.py:329–337) and the trend inside `/reports/management` (payroll.py:755–758) sums only `Expense.amount` per month. The main management P&L section *does* add PO COGS (payroll.py:710–719). This makes the trend chart show lower expenses than the headline P&L for the same month, and the computed `profit` in the trend is overstated.

**✓ PO COGS not double-counted** — `purchase_orders.py:218–220` explicitly suppresses creation of an `Expense` record when goods are received, so PO costs enter the reports only through the explicit `po_cogs` aggregation. No double-counting.

**✓ Management accounts trend loop applies `_to_zar()` consistently** — payroll.py:752–754 wraps each paid invoice with `_to_zar(inv)`.

**✓ `/v1/summary` (main.py:210–216)** — Uses `_to_zar()` for revenue and outstanding. String literals `"paid"`, `"sent"`, `"overdue"` used in queries are safe because `InvoiceStatus` is `str, enum.Enum` (database.py:36), so SQLAlchemy stores and compares string values.

---

## 3. Debtors (Accounts Receivable)

**Frontend** — `Debtors` component (App_js_fixed.js:3274–3389) calls `GET /reports/debtors-aging` on mount. Displays buckets: Not Yet Due, 0–30, 31–60, 61–90, 90+.

**✓ Correct invoice filter** — `/reports/debtors-aging` (payroll.py:886–889) queries `status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])`. Draft and paid invoices are excluded.

**✓ ZAR conversion** — All amounts use `_to_zar(inv)` (payroll.py:899).

**✓ Paid invoices excluded** — Only `sent` and `overdue` statuses are fetched; `paid` is absent from the filter.

**✓ Aging from `due_date`** — payroll.py:894 uses `inv.due_date or inv.issue_date or inv.created_at`. Primary key is `due_date`, falling back gracefully. Bucket assignment uses `days_overdue = (now - due).days` with negative values going to `not_due`.

**✗ MEDIUM — Reconciliation aging check uses `issue_date`, not `due_date`.**  
`/reports/reconciliation` rule 2 (payroll.py:453–470) identifies overdue > 90 days using:
```python
cutoff_90 = now - timedelta(days=90)
Invoice.issue_date <= cutoff_90
```
This ages from the invoice **issue date** rather than `due_date`. An invoice with 60-day payment terms issued 95 days ago is not overdue (due date is 35 days in the future) but will appear in the reconciliation warning. Conversely, short-term invoices issued 85 days ago can be missed if their `issue_date` is within 90 days. The **main debtors aging report is correct**; only the reconciliation health check is wrong.

---

## 4. Creditors (Accounts Payable)

**Frontend** — `Creditors` component (App_js_fixed.js:3392+) calls `GET /reports/creditors-aging` on mount and re-fetches on `live.expenses` change. Displays vendors grouped by aging bucket.

**✓ Correct PO filter** — `/reports/creditors-aging` (payroll.py:949–952) queries `status.in_(["received", "partial"])`. Fully paid POs (`status=="paid"`) are excluded. Draft and sent POs are excluded.

**✓ Received-but-unpaid POs appear as outstanding creditors** — All `received` and `partial` POs are included.

**✓ Paid POs excluded** — `status=="paid"` is absent from the filter (payroll.py:950).

**✓ Supplier bank details decrypted** — `decrypt_field()` is called for `bank_name`, `account_number`, and `branch_code` before building the vendor map (payroll.py:987–989).

**✓ Aging from `due_date`** — payroll.py:972–974: `due_date = received_date + timedelta(days=payment_terms)`, where `payment_terms` comes from the `Supplier` record (defaulting to 30 days if absent).

**✗ LOW — Frontend Creditors component re-fetches on `live.expenses` change.**  
App_js_fixed.js:3403–3407: the `useEffect` dependency is `[live.expenses]`. Creditors (AP) depend on Purchase Orders, not expense records. This triggers a spurious API call every time any expense is updated. Functionally harmless but semantically incorrect.

---

## 5. Cross-module Journal Coverage

| Event | Posting function | Called from | Status |
|---|---|---|---|
| Invoice raised | `post_invoice_raised` | companies.py:204 | ✓ |
| Invoice paid | `post_invoice_paid` | companies.py:229 | ✓ (but see Critical below) |
| Expense created | `post_expense` | companies.py:288 | ✓ |
| Payroll run | `post_payroll` | payroll.py:210 | ✓ |
| PO received | `post_po_received` | purchase_orders.py:226 | ✓ |
| PO paid | `post_po_paid` | purchase_orders.py:261 | ✓ |

All six event types have posting functions and are called at the right points. Backfill (`journal.py:369–443`) also covers all six for pre-existing data.

**✗ CRITICAL — Foreign-currency invoice payment journal entries silently fail.**  
`post_invoice_paid` (journal.py:196–203) builds:
```python
zar_received = invoice.paid_amount_zar if invoice.paid_amount_zar else invoice.total_amount
lines = [
    _line(entry.id, bank, debit=zar_received),        # e.g. ZAR 1,850
    _line(entry.id, ar,   credit=invoice.total_amount), # e.g. USD 100 (foreign units)
]
_assert_balanced(lines)   # 1850 ≠ 100 → raises ValueError
```
For any foreign-currency invoice where `paid_amount_zar ≠ total_amount` (i.e., virtually every foreign invoice), `_assert_balanced` raises `ValueError`. This is caught silently at companies.py:230–232:
```python
except Exception as e:
    logger.warning(f"Journal post failed for invoice payment {invoice.invoice_number}: {e}")
```
**Impact:** The AR control account (1100) is never credited and the Bank account (1000) is never debited for foreign-currency invoice payments. The balance sheet permanently overstates Accounts Receivable for these invoices and understates the cash position. The Debtors aging report will correctly exclude paid invoices (the status filter handles this), but the double-entry ledger is incomplete — meaning the trial balance will not reconcile for companies that invoice in foreign currencies.

**Balance sheet control account reconciliation:**
- Debtors Control (1100): Debited on invoice raised, credited on payment. Reconciles for ZAR invoices. Permanently out-of-sync for foreign-currency paid invoices due to the bug above.
- Creditors Control (2000): Credited on PO receipt, debited on PO payment. Fully correct.

---

## 6. Action Items

**Critical**

1. **Fix foreign-currency invoice payment journal entry** (`journal.py:196–204`). The AR credit must use `paid_amount_zar` (ZAR equivalent), not `invoice.total_amount` (foreign currency units). Add a realised FX gain/loss line to account for exchange differences between the original invoice ZAR equivalent and the actual ZAR received. Example fix:
   ```python
   zar_booked = _to_zar(invoice)          # ZAR value at time of raising
   zar_received = invoice.paid_amount_zar or zar_booked
   lines = [
       _line(entry.id, bank, debit=zar_received,    description="Cash received"),
       _line(entry.id, ar,   credit=zar_booked,     description=invoice.invoice_number),
   ]
   if abs(zar_received - zar_booked) > 0.01:
       fx_acct = get_account(cid, "4100", db)   # add FX Gain/Loss account
       diff = round(zar_received - zar_booked, 2)
       lines.append(_line(entry.id, fx_acct, credit=diff if diff > 0 else 0,
                                             debit=abs(diff) if diff < 0 else 0))
   ```

**High**

2. **Fix expense P&L reporting to use VAT-exclusive amounts** (`payroll.py:259–260, 702, 755, and others`). The `Expense.amount` column stores the VAT-inclusive total. Change all report queries to sum `e.amount - (e.vat_amount or 0)` for the P&L expense figure. Alternatively, add a `net_amount` column to `Expense` storing the ex-VAT value and use that in reports. Affects `/reports/dashboard`, `/reports/management`, `/reports/monthly-trend`, `/reports/cash-flow`, `/reports/provisional-tax`.

**Medium**

3. **Fix reconciliation debtor aging to use `due_date` instead of `issue_date`** (`payroll.py:454–458`). Change:
   ```python
   Invoice.issue_date <= cutoff_90
   ```
   to:
   ```python
   (Invoice.due_date != None), Invoice.due_date <= cutoff_90
   ```
   (with a null-safe fallback to `issue_date` for invoices without a due date.)

4. **Fix monthly trend to include PO COGS in expense calculation** (`payroll.py:329–337` and `payroll.py:755–758`). For each month in the trend loop, add a PO COGS sub-query matching the approach at payroll.py:710–719, so that trend `expenses` and `profit` columns are consistent with the headline P&L.

5. **Fix dashboard `total_payroll` to use actual payslip records** (`payroll.py:276`). Replace `calc_payroll(e.gross_salary)["total_cost"]` with a sum of `Payslip.total_cost` for the relevant period, matching the approach in `provisional_tax` (payroll.py:824–826).

**Low**

6. **Fix Creditors frontend dependency array** (`App_js_fixed.js:3407`). Change `}, [live.expenses])` to `}, [live.reload])` or remove the dependency entirely, since creditors depend on POs, not expense records.
