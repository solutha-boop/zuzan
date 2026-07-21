# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 20 July 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-07-19 (full PASS, all carried items closed same day).

**Change detection since last run (2026-07-19 10:04):** only `main.py` and `auth.py` were modified (both 2026-07-19 20:18). A working-tree diff against the committed version nets to **zero content change** (pure line reordering/whitespace — every added line has an identical removed counterpart); regardless, `/v1/summary` was re-read line-by-line this run. All other audit-scope files (payroll.py, database.py, financial_statements.py, fixed_assets.py, journal.py, purchase_orders.py, csv_import.py, App_js_fixed.js) are byte-unchanged since the prior verified run; key checkpoints were still freshly re-read/grepped, and line references below reflect today's files. Note: payroll.py line refs shifted ~+105 vs the 07-19 report body (that report's refs predate the same-morning s11F/rebate additions).

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ✅ PASS — all totals ZAR-converted and mutually consistent |
| Debtors (AR) | ✅ PASS — aged from due_date, paid excluded, ZAR amounts |
| Creditors (AP) | ✅ PASS — reversal-aware in all locations, bank details decrypted |
| Cross-module consistency | ✅ PASS — full journal coverage, import-awareness intact |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) implemented 2026-07-14, re-verified |
| Tax rates (SARS) | ✅ PASS — 2026/2027 tables current and web-verified |

**Overall: PASS.** No regressions; yesterday's post-run edits were content-neutral. One new cosmetic Low item logged (section 8).

---

## 2. Reports

✓ No issues found.

- `total_revenue` sums only paid invoices via `_to_zar()` (payroll.py:1233-1237); `_to_zar()` prefers `paid_amount_zar` for paid foreign-currency invoices, falls back to `total_amount × exchange_rate`, ZAR passthrough (payroll.py:17-24). Bank-import income added separately without double-count (payroll.py:1239; `_bank_import_income` reads only journal `bank_import_income` entries, payroll.py:59-97).
- `total_outstanding` covers `sent` + `overdue` with `_to_zar()` (payroll.py:1241-1245). `sent` is the app's "pending" status, so pending + overdue is satisfied.
- Expenses excluded from revenue; taken ex-VAT (payroll.py:1251).
- Payroll included via all-company payslip sum incl. terminated employees, active-employee estimate fallback (payroll.py:1275-1285).
- PO COGS: received/partial/paid POs at delivered-value ex-VAT via `_po_delivered_net` (payroll.py:1256-1261, helper :27-46); structural double-count warning against matching expenses (payroll.py:1309-1346). Not double-counted.
- PO input VAT in dashboard VAT position (payroll.py:1298-1307) — 2026-07-07 fix intact; depreciation included (payroll.py:1263-1267).
- Management accounts: period revenue uses `_to_zar()` + date-ranged bank-import income (payroll.py:2072-2080), delivered-value PO COGS (:2096-2108), depreciation (:2110-2118); the 6-month trend loop applies `_to_zar()`, `_bank_import_income`, `_po_delivered_net` and depreciation each month (payroll.py:2160-2193).
- `/v1/summary` imports and uses `_to_zar`, `_po_delivered_net`, `_bank_import_income` consistently with the dashboard, incl. depreciation and all-payslip payroll (main.py:443-488) — fully re-verified after yesterday evening's (content-neutral) main.py touch.

## 3. Debtors

✓ No issues found.

- Frontend `Debtors` renders backend `/reports/debtors-aging` verbatim and refreshes on invoice payment (App_js_fixed.js:5930, :5936).
- Backend filters `status IN (sent, overdue)` — paid and draft excluded (payroll.py:2350-2353).
- ZAR equivalents via `_to_zar()` per invoice (payroll.py:2364).
- Aging strictly from `due_date`; invoices without one go to `not_due` — no issue-date fallback (payroll.py:2357-2384). Buckets not_due / current(0-30) / 31-60 / 61-90 / 90+ with per-bucket and grand totals (payroll.py:2386-2400).

## 4. Creditors

✓ No issues found.

- Frontend `Creditors` renders backend `/reports/creditors-aging` and refreshes on PO payment (App_js_fixed.js:6057, :6063).
- Pulls received/partial POs (payroll.py:2420-2423) + unpaid on-credit expenses (`is_on_credit == True`, `paid_at == None`, payroll.py:2515-2519); fully paid POs and paid credit expenses excluded.
- Supplier bank details decrypted with `decrypt_field` before display (payroll.py:2483-2485).
- Aging from due date = received_date (fallback order_date/created_at) + supplier payment_terms, default 30 (payroll.py:2464-2477); credit expenses aged from expense_date + 30 (payroll.py:2521-2526).
- **Reversal-awareness (2026-07-13 fixes) verified in all locations** — each nets `SUM(credit − debit)` on account 2000 and includes source `purchase_order_reversal`:
  - payroll.py Rule 7 reconciliation (payroll.py:1770-1778)
  - creditors-aging per-PO lookup (payroll.py:2432-2448), `po.total_amount` fallback when no journal entry exists (payroll.py:2495)
  - purchase_orders.py `pay_po` AP-balance clear (purchase_orders.py:438-445)
  - journal.py backfill (journal.py:848)
  - financial_statements.py Note 7 (financial_statements.py:541-554)

## 5. Cross-module consistency

✓ No issues found.

- Journal coverage complete in journal.py (unchanged since 07-15, freshly re-grepped): `post_invoice_raised` (:194), `post_invoice_paid` (:234), `post_invoice_cogs` (:268), `post_expense` (:293), `post_bank_income` (:328), `post_payroll` (:368), `post_expense_paid` (:447), `post_po_received` (:476), `post_po_paid` (:528), `post_stock_adjustment` (:556), plus idempotent `backfill_company` (:702). Invoice payments, expense payments, PO receipts, PO payments and payroll runs are all covered.
- Debtors Control (1100) and Creditors Control (2000) reconciliation rules compare journal balances to raw invoice/PO totals (payroll.py Rules 6/7 region, :1723-1812).
- **Import-awareness (2026-07-11 fixes) all re-verified:**
  - Invoice/expense imports auto-run journal backfill via `_auto_backfill` (csv_import.py:124, :501, :563)
  - Rules 6/7 exclude `source="import"` lines on 1100/2000, reported as opening balances (payroll.py:1727-1736, :1805-1812)
  - Balance sheet includes 3999 Opening Balance Equity and 3998 imported Retained Earnings offsets (payroll.py:1526-1546; csv_import.py:726-733, :925-946)
  - Unbalanced journal import groups rejected with per-row errors (csv_import.py:1035-1064)
  - Non-ZAR invoice imports without a positive exchange rate rejected row-by-row (csv_import.py:458-475)
- Migration hygiene: all ALTER TABLE strings are inside the migrations list literal, which closes at database.py:1418 and executes in the try/except loop (:1419-1424); code after the loop is only data backfills (paid_date :1425-1434, portal_token :1437+). No dead-code migrations.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs, declared in the AFS meta and rendered in the frontend (App_js_fixed.js:6241, :11786). Statements: income statement, statement of financial position, changes in equity, cash flow (indirect), notes 2–9.

**Standards status (web search 2026-07-20 — unchanged since prior audits, moving on per task rules):**
- IFRS 18 *Presentation and Disclosure in Financial Statements* — effective annual periods beginning on or after 1 Jan 2027; applies to full-IFRS preparers, not IFRS for SMEs preparers. No ZuZan change required.
- IFRS for SMEs **third edition** (Feb 2025) — effective annual periods beginning on or after 1 Jan 2027, early application permitted. ZuZan's SA FY (1 March–28/29 Feb) first caught by FY beginning 1 March 2027. Transition plan already on file (`audit_reports/ifrs_smes_3rd_edition_transition_plan.md`); early-2027 runs execute its checklist.

**Section 5b — deferred tax: ALREADY IMPLEMENTED (2026-07-14) — verified this run, no code changes required or made.** financial_statements.py unchanged since 2026-07-19 10:02; fresh reads confirm:
- Note 9 does **not** hard-code `"deferred_tax": 0.0` — reports period movement `dt_closing − dt_opening`, `total_tax = current + deferred`, opening/closing balances and effective rate (financial_statements.py:266-268, :601-610).
- `wear_and_tear_rate` column on FixedAsset (database.py:480); ALTER TABLE migration inside the list literal (database.py:1360; list closes :1418, loop :1419-1424) — not dead code.
- Computation (financial_statements.py:78-173): tax base = cost − straight-line SARS wear-and-tear apportioned monthly from purchase date, floored at 0; temporary difference = carrying value − tax base, × CIT 27% (`SA_CIT_RATE` imported from fixed_assets, single source of truth since 07-19). Rate priority: explicit `wear_and_tear_rate` → IN47 `sars_category` → category-name heuristic → None (zero difference). Disposed assets reverse; no assets / no rates ⇒ exactly 0.0; output shape backward-compatible.
- Balance sheet presents closing DTL/DTA as a computed line with matching retained-earnings adjustment (financial_statements.py:348 region, :681); nothing posted to the journal.
- Frontend renders the Note 9 deferred tax row when non-zero, "Nil" otherwise (App_js_fixed.js:11724-11726) and DTL/DTA badges in the asset register (App_js_fixed.js:10255-10292).

**Finance costs (2026-07-13 fix) re-confirmed:** interest lines (6700/name-matched) presented below EBIT; `profit_before_tax = ebit − finance_costs`, tax and net profit derive from profit_before_tax, not EBIT (financial_statements.py:207-261, :636-639).

**New minor observation:** current tax at financial_statements.py:260 uses a literal `0.27` instead of the unified `_CIT_RATE` constant available in the same file. Value is identical; cosmetic only (logged as Low).

✓ No new issues of substance found.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date; `_current_tax_year()` derives it from today's date with newest-table fallback (payroll.py:169-182). Rates verified by web search 2026-07-20.

- **PAYE brackets 2026/2027** — TAX_YEARS entry present and matches SARS published tables exactly (payroll.py:131-145): 18% to R245,100; 26% to R383,100 (base R44,118); 31% to R530,200 (R79,998); 36% to R695,800 (R125,599); 39% to R887,000 (R185,215); 41% to R1,878,600 (R259,783); 45% above (R666,339). ✓
- **Rebates** — primary R17,820 ✓, secondary R9,765 ✓, tertiary R3,249 ✓ (payroll.py:141-143); age-based application via `calc_paye(age)` implemented 07-19.
- **UIF** 1% + 1% ✓ (payroll.py:188), ceiling R17,712/month ✓ (payroll.py:144). **SDL** 1% ✓ (payroll.py:189).
- **Corporate income tax** 27% unchanged ✓ — dashboard (payroll.py:1289), management accounts (:2144), provisional tax (:2241), AFS via `SA_CIT_RATE`.
- **VAT** 15% unchanged ✓ (payroll.py:1608, :2597). s11F cap R430,000 (payroll.py:195-196) and 2026/2027 medical tax credits R376/R254 (payroll.py:200-201) current.
- **Provisional 2027/2028 entry** present, flagged `"provisional": True` (payroll.py:151-166) — standing annual task must replace it with actual Budget Feb 2027 rates, then restart the backend.
- Rates unchanged and current tax year present — no edits made (report-only per task rules; 5b needed no edits).

**Sources consulted:** [SARS — Rates of Tax for Individuals](https://www.sars.gov.za/tax-rates/income-tax/rates-of-tax-for-individuals/) · [National Treasury — Budget 2026 Tax Guide](https://www.treasury.gov.za/documents/national%20budget/2026/sars/Budget%202026%20Tax%20guide.pdf) · [SARS — Budget 2026 FAQ](https://www.sars.gov.za/about/sars-tax-and-customs-system/budget/budget-2026-frequently-asked-questions/) · [TaxTim — Tax bracket calculator](https://www.taxtim.com/za/calculators/tax-bracket) · [IFRS — IFRS for SMEs](https://www.ifrs.org/issued-standards/ifrs-for-smes/) · [IAS Plus — third IFRS for SMEs](https://www.iasplus.com/en/news/2025/02/third-ifrs-for-smes) · [Grant Thornton — Get ready for IFRS 18](https://www.grantthornton.global/en/insights/articles/get-ready-for-ifrs-18/) · [PKF SA — IFRS for SMEs Conceptual Framework (2026)](https://www.pkf.co.za/news/2026/ifrs-for-sme-conceptual-framework/)

## 8. Action items

| # | Severity | Item |
|---|---|---|
| 1 | Low | **Cosmetic:** financial_statements.py:260 computes current tax with literal `0.27`; use `_CIT_RATE` for full single-source-of-truth consistency (value identical today — no financial impact). |

**Standing reminders (not defects):** (a) replace the provisional 2027/2028 TAX_YEARS entry after Budget Feb 2027 and restart the backend; (b) early-2027 runs execute the IFRS for SMEs 3rd-edition transition-plan checklist.
