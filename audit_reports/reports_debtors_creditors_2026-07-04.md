# ZuZan Audit Report — Reports, Debtors & Creditors
**Date:** 2026-07-04
**Scope:** Reports (dashboard/management/trend/summary), Debtors (AR), Creditors (AP), Cross-module journal coverage
**Files reviewed:** `payroll.py`, `journal.py`, `purchase_orders.py`, `companies.py`, `main.py`, `database.py`, `portal.py`, `bank_direct_feeds.py`, `saltedge.py`, `App_js_fixed.js`

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports — `/reports/dashboard` | ⚠️ ISSUE (bank-import VAT defects feed into expense & VAT figures) |
| Reports — `/reports/management` | ⚠️ Same upstream issue |
| Reports — `/reports/monthly-trend` | ⚠️ Same upstream issue |
| Reports — `/v1/summary` (Public API) | ⚠️ Same upstream issue |
| Debtors (AR) — backend + frontend | ✅ PASS |
| Creditors (AP) — backend + frontend | ✅ PASS |
| Cross-module journal coverage | ⚠️ ISSUE (bank-import re-import duplicates; VAT201 includes drafts) |

**Overall verdict:** All four fixes from the 2026-07-03 audit are verified in source and correct. The report endpoints themselves are structurally sound and consistent. However, the **bank statement import feature added yesterday evening** (companies.py `/bank/import`, journal `post_bank_income`, `_bank_import_income` report helper) introduces three new bugs: imported expenses silently drop their VAT split, duplicate detection on debits can never match, and credits have no duplicate detection at all — so re-importing a statement double-counts both expenses and revenue in every report.

### Changes since last audit (2026-07-03)

Code changed after yesterday's 07:16 run: `payroll.py` (23:00), `journal.py` + `companies.py` (21:07), `fixed_assets.py` + `purchase_orders.py` (17:20), `database.py` + `main.py` (07:40), `portal.py` (07:12). `App_js_fixed.js` unchanged since 2026-07-02 21:28.

**Yesterday's fixes re-verified in today's source:**
- Portal IPN posts `journal_engine.post_invoice_paid(inv, db)` on the request's own session with commit, ERROR-level logging on failure (portal.py:184–205). ✓
- `_po_delivered_net()` treats `"paid"` like `"partial"` — delivered sum when tracking data exists, full-subtotal fallback for legacy POs (payroll.py:27–46); same condition in backfill receive loop (journal.py:725–735); backfill payment loop clears only actual AP credits, mirroring `pay_po` (journal.py:741–776). ✓
- Dead migration statements moved INTO the migrations list: portal DO block, invite_tokens/audit_log CREATE TABLEs, role backfill (database.py:1088–1129). Plus new (2026-07-03) performance indexes added correctly inside the list (database.py:1130–1144). ✓
- `update_po` whitelists status transitions (purchase_orders.py:137–146). ✓

**New feature since last run — bank statement import:**
- `POST /bank/import` (companies.py:771–848): debits → Expense records + `post_expense` journal; credits → journal-only entries via `post_bank_income` (journal.py:315–352, source `"bank_import_income"`, DR Bank 1000 / CR Revenue / CR VAT Output 2100).
- `_bank_import_income()` helper (payroll.py:59–97) adds journal-only bank income to revenue in dashboard (516), monthly-trend (680), cash-flow receipts (1096), management + trend (1240, 1334), provisional tax (1413), and `/v1/summary` (main.py:272). Applied consistently across all endpoints, with correct date-range filtering. No double-count with invoice revenue (credits never create invoices; debits create Expenses picked up by the existing expense sums). ✓ architecture, ❌ three implementation bugs below.
- SaltEdge/ABSA direct feeds (`bank_direct_feeds.py`, `saltedge.py`): transactions are only *matched* to existing invoices/expenses (`_auto_match`, bank_direct_feeds.py:112–140) — no Expense/Invoice/journal records created, so no report impact and no double-count. ✓

---

## 2. Reports

### Structure — all four P&L endpoints ✓

- `/reports/dashboard` (payroll.py:501–644): revenue = paid invoices via `_to_zar()` (514) + bank-import income (516); outstanding = sent + overdue via `_to_zar()` (518–522); expenses ex-VAT (528), PO COGS via `_po_delivered_net()` for received/partial/paid (533–540), depreciation (543–546), payroll incl. terminated employees with estimate fallback (554–564), duplicate-expense structural warning (583–621). ✓
- `/reports/monthly-trend` (payroll.py:647–719): same components per month, bank income date-filtered (680). ✓
- `/reports/management` (payroll.py:1203–1383): period P&L + 6-month trend, bank income in both (1240, 1334), `_to_zar()` and `_po_delivered_net()` throughout. ✓
- `/v1/summary` (main.py:264–309): imports and applies `_to_zar`, `_po_delivered_net`, `_bank_import_income` — consistent with dashboard. ✓

### ❌ Issue 1 (High — new): imported bank expenses always lose their VAT split

companies.py:801 checks `txn.vat_applicable` — but the frontend BankImport component sends `has_vat` and `vat_amount` and **never sends `vat_applicable`** (App_js_fixed.js:5679–5687; the Pydantic model defaults `vat_applicable=False`, companies.py:763). The credit branch handles this correctly (`post_bank_income` checks `has_vat OR vat_applicable`, journal.py:327), but the debit branch does not. Every imported expense is stored with `vat_amount = 0`, so:
- P&L expenses are **overstated** by the VAT portion (dashboard 528, trend 682–688, management 1248, summary main.py:275 all compute `amount − vat_amount`);
- input VAT is **understated** in the dashboard VAT position (payroll.py:577), Rule 3 (873), and VAT201 (1796–1797);
- the expense's journal entry posts no DR to VAT Input 1300 (journal.py:300–308).

Fix: mirror the credit branch — `has_v = txn.has_vat or txn.vat_applicable`, and prefer the frontend-precomputed `txn.vat_amount` over the 15/115 recalculation (companies.py:800–806).

### ⚠️ Issue 5 (Medium — pre-existing, first time flagged): VAT201 output tax includes draft invoices

payroll.py:1774–1778 sums **all** invoices issued in the period with no status filter. Draft invoices are not issued documents, so output VAT and standard-rated supplies are overstated whenever drafts exist. Inconsistent with the dashboard (574) and Rule 3 (869), which both exclude drafts. Fix: add `Invoice.status.in_([sent, overdue, paid])`.

---

## 3. Debtors (AR)

✓ No issues found. (Endpoint unchanged since yesterday's pass; frontend unchanged since 2026-07-02.)

- **Status filter** (payroll.py:1507–1510): `status.in_([sent, overdue])` — paid and draft excluded. ✓
- **ZAR amounts** (payroll.py:1521): `_to_zar(inv)` on every entry. ✓
- **Aging from `due_date`** (payroll.py:1514–1541): no issue-date fallback; null due dates → `not_due`; buckets not_due / ≤30 / 31–60 / 61–90 / 90+. ✓
- **Frontend `Debtors`** (App_js_fixed.js:4670–4793): fetches `/reports/debtors-aging`, refreshes on invoice changes, displays backend ZAR amounts as-is. ✓
- Bank-import income never touches AR (DR Bank / CR Revenue only) — no contamination of the debtors book. ✓

---

## 4. Creditors (AP)

✓ No issues found. (Endpoint unchanged since yesterday's pass.)

- **PO filter** (payroll.py:1577–1580): `status.in_(["received","partial"])` — fully paid POs excluded. ✓
- **Partial PO amounts** (payroll.py:1585–1602, 1649): creditor amount = journal AP credits (account 2000) per delivery, `total_amount` fallback only when no entry exists. ✓
- **On-credit expenses** (payroll.py:1669–1715): unpaid `is_on_credit` expenses included, aged from `expense_date + 30`. ✓
- **Bank details decrypted** (payroll.py:1637–1639): `decrypt_field()` on bank_name / account_number / branch_code. ✓
- **Frontend `Creditors`** (App_js_fixed.js:4796–4930): unchanged, verified previously. ✓
- Bank-import debits post DR Expense / CR Bank (cash), never AP — no contamination of the creditors book. ✓

*Note (Low, carried):* decrypted supplier bank details are returned by the aging API but never rendered by the frontend.

---

## 5. Cross-module Journal Coverage

| Event | Posting function | Called from | Status |
|---|---|---|---|
| Invoice raised / COGS / paid / deleted | post_invoice_* / reverse | companies.py:242, 245, 289 | ✓ |
| Invoice paid via client portal (PayFast IPN) | post_invoice_paid | portal.py:195 | ✓ *(fixed 2026-07-03, verified today)* |
| Expense incurred / credit expense paid | post_expense(_paid) | companies.py:446, 530, 577 | ✓ |
| **Bank import — expense (debit)** | post_expense | companies.py:822 | ✓ *(new; VAT bug — Issue 1)* |
| **Bank import — income (credit)** | post_bank_income | companies.py:832 | ✓ *(new; no dedupe — Issue 3)* |
| Direct feeds (SaltEdge/ABSA) matching | — (match-only, no postings) | bank_direct_feeds.py | ✓ by design (see note) |
| PO received / paid | post_po_received / post_po_paid | purchase_orders.py | ✓ |
| Payroll run | post_payroll | payroll.py:361 | ✓ |
| Asset acquisition / depreciation | post_asset_* / post_depreciation | fixed_assets.py | ✓ |

**AR Control (1100):** Rule 6 (payroll.py:927–947) — journal balance vs outstanding invoices via `_to_zar()`, tolerance R1.00. ✓
**AP Control (2000):** Rule 7 (payroll.py:949–1007) — journal-derived per-PO AP credits + unpaid credit expenses. ✓
**Backfill safety:** backfill is additive (skips existing `(source, source_id)` pairs, journal.py:655–657) and never deletes — journal-only `bank_import_income` entries (source_id = None) survive backfill runs. ✓

### ❌ Issue 2 (High — new): bank-import duplicate detection for debits can never match

companies.py:790–794 dedupes on `Expense.description == txn.description`, but the created Expense stores `description = "Imported from {BANK} statement"` and puts the transaction description in `vendor` (companies.py:810–811). The filter compares the raw bank narrative against the literal string "Imported from FNB statement" — it will never match, so **re-importing the same statement (or an overlapping date range) creates duplicate expenses**, overstating expenses and input VAT in every report. The comment claims "same vendor, amount and date" but neither vendor nor date is filtered. Fix: dedupe on `Expense.vendor == txn.description[:100]`, `Expense.amount == txn.amount`, and `Expense.expense_date == txn.date`.

### ❌ Issue 3 (High — new): no duplicate detection for bank-import credits

companies.py:827–836 posts a `bank_import_income` journal entry for every credit with no duplicate check at all. Re-importing a statement **double-counts revenue** in dashboard, monthly-trend, management, cash-flow, provisional tax, and `/v1/summary` — and inflates the Bank account balance on the balance sheet. Because these entries are journal-only (no source record, `source_id = None`), there is nothing for backfill to reconcile against and no natural repair path short of manually deleting journal entries. Fix: skip when an entry with source `"bank_import_income"`, the same company, date, description, and total debit amount already exists (or store an idempotency hash in `JournalEntry.reference`).

### ⚠️ Issue 4 (Medium — new): bank-income output VAT invisible to VAT reporting

`post_bank_income` credits VAT Output 2100 when `has_vat` is set (journal.py:342–347), but the dashboard VAT position (payroll.py:576), Rule 3 VAT control (872), and VAT201 output tax (1774–1784) all compute output VAT **from invoice records only**. VAT collected on imported bank income is posted to the ledger but never surfaces in any VAT report — net VAT payable is understated. Fix: add the period's 2100 credits from `bank_import_income` entries to each of the three output-VAT calculations.

*Workflow note (Low):* direct-feed matching (`bank_direct_feeds.py`) links a credit to an open invoice but does **not** mark the invoice paid or post a journal entry — a matched invoice still requires a manual "mark paid". Confirm this is intended, otherwise revenue recognition lags the bank feed.

---

## 6. Action Items

**#1 — High: Honor `has_vat`/`vat_amount` in the bank-import debit branch**
companies.py:800–806. Use `txn.has_vat or txn.vat_applicable` (mirror journal.py:327) and prefer the provided `txn.vat_amount`; fall back to 15/115 only when it's absent. Existing imported expenses with dropped VAT need a one-off correction.

**#2 — High: Fix debit duplicate detection**
companies.py:790–794. Match on `vendor == txn.description[:100]` + `amount` + `expense_date`, not `description`.

**#3 — High: Add credit duplicate detection**
companies.py:827–836. Skip credits whose (company, date, description, amount) already exist as a `bank_import_income` entry.

**#4 — Medium: Include bank-income VAT (2100 credits) in output-VAT calculations**
payroll.py:576 (dashboard), 872 (Rule 3), 1774–1784 (VAT201).

**#5 — Medium: Exclude draft invoices from VAT201 output tax**
payroll.py:1774–1778. Add the same status filter used by the dashboard (574).

**#6 — Low: Confirm direct-feed match behavior**
bank_direct_feeds.py — matched credits don't mark invoices paid; decide whether matching should trigger (or prompt) the paid flow.

**#7 — Low (carried): legacy `received_date` backfill uses `created_at` as proxy**
purchase_orders.py — unchanged; data-quality item on pre-existing rows.

**#8 — Low (carried): decrypted supplier bank details returned by `/reports/creditors-aging` but never rendered**
payroll.py:1637–1639. Left in place per the audit brief's requirement; owner to decide.

---

## 7. Fixes Applied (same day, 2026-07-04, on user request)

Action items #1–#3 (the three High bugs) were fixed after this audit was written. All changes are in `companies.py` `/bank/import`:

| # | Fix | Location |
|---|---|---|
| 1 | Debit VAT split now honors `txn.has_vat or txn.vat_applicable` (mirroring `post_bank_income`), prefers the frontend-precomputed `txn.vat_amount`, and falls back to the 15/115 back-calculation only when no amount was provided. | companies.py:805–819 |
| 2 | Debit dedupe now matches what imported expenses actually store: `vendor == txn.description[:100]` + `amount` + `expense_date` (previously compared the bank narrative against the fixed "Imported from ..." description string, which never matched). | companies.py:789–803 |
| 3 | Credits now have a dedupe: skip when a `bank_import_income` journal entry already exists with the same company, date, description ("Bank income — {narrative}") and bank-debit line amount — the exact fields `post_bank_income` writes. Skipped credits are counted in the existing `credits_skipped` response field. Date filter is dropped only for unparseable dates, matching `post_bank_income`'s own utcnow fallback. | companies.py:840–864 |

**Verification:** edited regions re-read from disk via the Read tool (stale-mount pitfall — not bash). Within-batch duplicates are also caught: the debit branch flushes each expense before the next iteration, and the credit dedupe query autoflushes pending journal entries. Known limitation (noted in code): two genuinely identical credits — same day, same description, same amount — will be treated as duplicates and must be captured manually.

**Data repair note:** these fixes prevent future damage but do not correct existing rows. If statements were imported before 2026-07-04: (a) expenses imported with a VAT flag have `vat_amount = 0` and need a one-off correction; (b) any duplicates created by re-imports should be deleted (expenses via the UI — journal reversal is posted automatically; duplicate `bank_import_income` journal entries need manual removal).

**Still open:** #4 (bank-income output VAT invisible to VAT reports), #5 (VAT201 includes drafts), #6–#8 (Low).

*Verification method: all cited regions read from disk via the Read/Grep file tools (per the stale-mount pitfall — not bash).*
