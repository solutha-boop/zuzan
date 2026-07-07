# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 2026-07-07 · **Scope:** payroll.py, main.py, journal.py, companies.py, suppliers.py, purchase_orders.py, database.py, App_js_fixed.js

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard, management, /v1/summary) | **PASS** — core figures correct; 3 VAT-related issues found |
| Debtors (AR) | **PASS** — no issues |
| Creditors (AP) | **PASS** — no issues |
| Cross-module / Journal | **PASS with caveats** — full journal coverage; invoice-edit desync risk |

## 2. Reports

### Verified correct
- `total_revenue` sums only `InvoiceStatus.paid` invoices (payroll.py:510–514) and applies `_to_zar()` (payroll.py:17–24: non-ZAR → `paid_amount_zar` or `total_amount × exchange_rate`; ZAR → as-is). Bank-import income added separately via journal source `bank_import_income` (payroll.py:516, 59–97) — no double-count with invoice revenue.
- `total_outstanding` covers `sent` + `overdue` with `_to_zar()` (payroll.py:518–522). Note: the enum has no `pending` status — `sent` **is** pending (database.py:38, documented in comment). Correct.
- Expenses excluded from revenue; expensed ex-VAT (payroll.py:528).
- Payroll included via sum of all payslips incl. terminated employees, with estimate fallback (payroll.py:554–564).
- PO COGS included ex-VAT for received/partial/paid POs using delivered-value logic `_po_delivered_net()` (payroll.py:533–540, 27–46); a structural double-count detector warns when an Expense mirrors a received PO (payroll.py:580–621). No double-counting: PO receipt does **not** create an Expense record (purchase_orders.py:315–319).
- Management accounts revenue + 6-month trend loop apply `_to_zar()` consistently, incl. bank income and PO COGS per month (payroll.py:1240–1242, 1332–1347).
- `/v1/summary` (main.py:264–309) mirrors the dashboard exactly: `_to_zar()`, ex-VAT expenses, PO COGS, depreciation, payroll.

### Issues
1. **[Medium] Dashboard VAT position ignores PO input VAT.** `input_vat` sums only `Expense.vat_amount` (payroll.py:577), but PO receipts post input VAT to account 1300 (journal.py:464–465). With received POs, `net_vat_payable` is overstated. Same gap in reconciliation Rule 3 (payroll.py:874–876).
2. **[Medium] VAT201 includes draft invoices.** `/reports/vat201` sums all invoices issued in the period with no status filter (payroll.py:1776–1784), while the dashboard deliberately excludes drafts (payroll.py:571–575). A draft raises no journal VAT liability, so VAT201 can overstate output VAT.
3. **[Medium] VAT201 not currency-converted.** Output figures sum raw `total_amount`/`vat_amount` without `_to_zar()` (payroll.py:1783–1784) — foreign-currency invoices are reported at face value, inconsistent with every other report.

## 3. Debtors

✓ No issues found.

- Backend `/reports/debtors-aging` (payroll.py:1501–1560): filters invoices to `sent` + `overdue` only (line 1511) — paid and draft excluded.
- Amounts are ZAR equivalents via `_to_zar()` (line 1523).
- Aging is computed strictly from `due_date` (lines 1517–1543); invoices with no due date go to `not_due` rather than falsely aging from `date`/`created_at` — comment confirms the issue_date fallback was removed.
- Buckets: not_due / 0–30 / 31–60 / 61–90 / 90+; grand total is the sum of buckets (lines 1550–1559).
- Frontend `Debtors` (App_js_fixed.js:4731–4854) renders the backend response verbatim and refreshes when an invoice payment lands (lines 4741–4745). Mock data is only shown with an explicit "Demo Mode" badge when the API returns nothing (line 4777).

## 4. Creditors

✓ No issues found.

- Backend `/reports/creditors-aging` (payroll.py:1563–1735): pulls POs with status `received`/`partial` (line 1581) — fully paid POs excluded (payment flips status to `paid`, purchase_orders.py:396, and re-receiving paid POs is blocked, purchase_orders.py:269–270). Unpaid on-credit expenses (`is_on_credit=True, paid_at IS NULL`) included as AP (lines 1671–1717) — paid ones excluded.
- Partial-PO amounts come from actual AP credits in the journal (account 2000, source `purchase_order`), not `po.total_amount` (lines 1584–1604, 1647–1651) — matches what was actually delivered.
- Aging from due date = received_date + supplier `payment_terms` (default 30) (lines 1620–1626); credit expenses aged from expense_date + 30 (lines 1679–1682).
- Supplier bank details decrypted with `decrypt_field` before display (payroll.py:1639–1641); suppliers.py encrypts on write and decrypts on read (suppliers.py:48–50, 68, 78).
- Frontend `Creditors` (App_js_fixed.js:4857–4999) renders backend data with bucket filtering; refreshes on PO/expense changes.

## 5. Cross-module

Journal coverage — all required events post balanced entries (journal.py) and are wired to their endpoints:

| Event | Posting fn | Called from |
|---|---|---|
| Invoice raised | `post_invoice_raised` (journal.py:181) | companies.py:251 |
| Invoice payment | `post_invoice_paid` (journal.py:221) | companies.py:298, portal.py:205 |
| Expense (cash/credit) | `post_expense` (journal.py:280) | companies.py:455, 539, 844 |
| Expense payment | `post_expense_paid` (journal.py:392) | companies.py:586 |
| PO receipt (incremental) | `post_po_received` (journal.py:421) | purchase_orders.py:332 |
| PO payment | `post_po_paid` (journal.py:473) | purchase_orders.py:431 |
| Payroll run | `post_payroll` (journal.py:355) | payroll.py:407 |

No coverage gaps. All postings are ZAR-denominated (journal.py:203–209) and atomic with their source records (commit-after-journal pattern with rollback on failure).

Control accounts reconcile:
- **Debtors Control (1100):** balance sheet reads journal balance (payroll.py:748); reconciliation Rule 6 compares it to `_to_zar()` sum of outstanding invoices and fails loudly on drift (payroll.py:929–949).
- **Creditors Control (2000):** Rule 7 compares journal balance to per-PO journal AP credits + unpaid credit expenses (payroll.py:951–1009); `pay_po` clears exactly the journal AP balance, not `po.total_amount` (purchase_orders.py:403–431).

### Caveats
4. **[High] Editing an invoice amount does not adjust its journal entry.** `update_invoice` recomputes `amount`/`vat_amount`/`total_amount` (companies.py:276–279) but never reverses/re-posts the original `post_invoice_raised` entry. AR control (1100) and Sales Revenue (4000) desync from the invoice table until `/journal/backfill` is run. Rule 6 will catch the drift, but the ledger is wrong in the interim. Deletion handles this correctly (companies.py:317–324); update does not.
5. **[Medium] Invoice update hardcodes 15% VAT** (companies.py:278) — an amount edit on a zero-rated or foreign-currency invoice forces standard VAT and applies ZAR math to foreign amounts.
6. **[Low] Un-paying an invoice posts no reversal.** Setting a paid invoice back to `sent` via `update_invoice` (companies.py:282–283) leaves the `invoice_payment` journal entry in place, overstating Bank and understating AR.
7. **[Low] Frontend static chart-of-accounts labels use codes 1120/2110** for Trade Receivables/Payables (App_js_fixed.js:258, 271) while the journal control accounts are 1100/2000 (journal.py:27, 31). Display-only inconsistency; balance sheet figures come from the backend and are correct.

## 6. Action items

1. **[High]** On `update_invoice` amount change, reverse and re-post the `invoice` journal entry (mirror the delete flow at companies.py:317–324). *(Item 4)* — **✅ FIXED 2026-07-07**
2. **[Medium]** Include PO input VAT (journal account 1300, source `purchase_order`) in the dashboard `input_vat` and reconciliation Rule 3. *(Item 1)* — **✅ FIXED 2026-07-07**
3. **[Medium]** Exclude draft invoices from VAT201 output tax and apply `_to_zar()` to its sums. *(Items 2, 3)* — **✅ FIXED 2026-07-07**
4. **[Medium]** Preserve the invoice's original VAT treatment and currency on amount edits instead of forcing `amount × 1.15`. *(Item 5)* — **✅ FIXED 2026-07-07**
5. **[Low]** Reverse the `invoice_payment` entry when a paid invoice is reverted to unpaid, or block that transition. *(Item 6)* — **✅ FIXED 2026-07-07**
6. **[Low]** Align frontend COA display codes (1120/2110) with the journal's control accounts (1100/2000). *(Item 7)* — **✅ FIXED 2026-07-07** (partially — see resolution log)

## 7. Resolution log (2026-07-07)

**Fix 1 — invoice edit journal sync (companies.py `update_invoice`).** Amount changes now reverse the original `invoice` journal entry and re-post it with the new amounts, mirroring the delete flow. Reversals are repeat-safe (`reverse_journal_entries` skips already-reversed entries; reversal entries get source `invoice_reversal` so they're never re-matched). Drafts are reversed but not re-posted (no AR/VAT liability for unissued invoices). Additionally, amount edits on invoices that *remain* paid are blocked with a 400 — the payment entry carries the old amount; the invoice must be reverted to unpaid first.

**Fix 2 — PO input VAT.** Dashboard `input_vat` = expense VAT + delivered-value PO VAT (`_po_delivered_total − _po_delivered_net`), consistent with the po_cogs treatment. Same addition to reconciliation Rule 3 and to VAT201 field 14 (period-filtered by `received_date`, reported separately as `po_input_vat`).

**Fix 3 — VAT201.** Output tax now excludes drafts (status filter sent/overdue/paid) and converts foreign-currency invoices to ZAR via `total_amount × exchange_rate` — the raised-basis rate matching `post_invoice_raised`, deliberately not `_to_zar()`'s paid-cash basis, since the VAT tax point is issue.

**Fix 4 — VAT treatment on edit.** Amount edits preserve the invoice's effective VAT rate (`vat_amount / amount`): zero-rated invoices stay at 0, standard stay at 15%, foreign-currency overrides scale proportionally.

**Fix 5 — paid→unpaid.** Reverting a paid invoice now reverses the `invoice_payment` journal entry and clears `paid_date` / `paid_amount_zar`.

**Fix 6 — COA display codes.** Trade Receivables renumbered 1120 → 1100 (matches journal Debtors Control). Trade Payables kept at 2110 because code 2000 is occupied by the Liabilities *header* row and the COA editor matches rows by code (a duplicate would corrupt edits); its description now states explicitly that it maps to journal Creditors Control 2000.
