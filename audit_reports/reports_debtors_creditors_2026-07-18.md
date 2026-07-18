# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 18 July 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-07-17. All four of its same-day fixes (M1 Note 7 reversal-aware payables, L1 Note 7 as-at filter, L2 AI-prompt rebate text, L3 date-derived tax year) **re-verified intact this run** with fresh code reads. No new code changes were required or made today.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ✅ PASS — all totals ZAR-converted and mutually consistent |
| Debtors (AR) | ✅ PASS — aged from due_date, paid excluded, ZAR amounts |
| Creditors (AP) | ✅ PASS — reversal-aware in all locations, bank details decrypted |
| Cross-module consistency | ✅ PASS — full journal coverage, import-awareness intact |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) implemented (2026-07-14), verified; Note 7 fixes (07-17) verified |
| Tax rates (SARS) | ✅ PASS — 2026/2027 tables current; tax-year selection now date-derived |

**Overall: PASS.** No critical, high, medium, or new low-severity findings. Only previously carried low items remain open (section 8).

---

## 2. Reports

✓ No issues found.

- `total_revenue` sums only paid invoices via `_to_zar()` (payroll.py:1013-1017); `_to_zar()` prefers `paid_amount_zar` for paid foreign-currency invoices, falls back to `total_amount × exchange_rate`, ZAR passthrough (payroll.py:17-24). Bank-import income added separately without double-count (payroll.py:1019, `_bank_import_income` reads only journal `bank_import_income` entries, payroll.py:59-66).
- `total_outstanding` covers `sent` + `overdue` with `_to_zar()` (payroll.py:1021-1025). `sent` is the app's "pending" status, so "pending + overdue" is satisfied.
- Expenses excluded from revenue; taken ex-VAT (payroll.py:1031).
- Payroll included via all-company payslip sum incl. terminated employees, with active-employee estimate fallback (payroll.py:1053-1065).
- PO COGS: received/partial/paid POs at delivered-value ex-VAT via `_po_delivered_net` (payroll.py:1036-1041); structural double-count warning against matching expenses (payroll.py:1089-1126). Not double-counted.
- PO input VAT in dashboard VAT position (payroll.py:1083-1086) — 2026-07-07 fix intact.
- Management accounts: period revenue uses `_to_zar()` + bank-import income (payroll.py:1858-1860); the 6-month trend loop applies `_to_zar()`, bank-import income, delivered-value PO COGS and per-period depreciation each month (payroll.py:1950-1973).
- `/v1/summary` imports and uses `_to_zar`, `_po_delivered_net`, `_bank_import_income`, depreciation and payroll consistently with the dashboard (main.py:446-487).

## 3. Debtors

✓ No issues found.

- Frontend `Debtors` component renders backend `/reports/debtors-aging` verbatim and refreshes on invoice payment (App_js_fixed.js:5747, :5753).
- Backend filters `status IN (sent, overdue)` — paid and draft excluded (payroll.py:2130-2133).
- ZAR equivalents via `_to_zar()` per invoice (payroll.py:2144).
- Aging strictly from `due_date`; invoices without one go to `not_due` (no issue-date fallback) (payroll.py:2137-2164). Buckets: not_due / 0-30 / 31-60 / 61-90 / 90+, with per-bucket and grand totals (payroll.py:2166-2181).

## 4. Creditors

✓ No issues found.

- Frontend `Creditors` renders backend `/reports/creditors-aging` and refreshes on PO payment (App_js_fixed.js:5874, :5880).
- Pulls received/partial POs + unpaid on-credit expenses; fully paid POs (`status` excludes `paid`) and paid credit expenses (`paid_at == None`) excluded (payroll.py:2200-2203, :2295-2299).
- Supplier bank details decrypted with `decrypt_field` before display (payroll.py:2263-2265).
- Aging from due date = received_date (fallback order_date/created_at) + supplier payment_terms, default 30 (payroll.py:2244-2257); credit expenses aged from expense_date + 30 (payroll.py:2301-2306).
- **Reversal-awareness (2026-07-13 fixes) verified in all locations** — each nets `SUM(credit − debit)` on account 2000 and includes source `purchase_order_reversal`:
  - payroll.py Rule 7 reconciliation (payroll.py:1550-1558)
  - creditors-aging per-PO lookup (payroll.py:2212-2228), with `po.total_amount` fallback when no journal entry exists (payroll.py:2275)
  - purchase_orders.py `pay_po` AP-balance clear (purchase_orders.py:438-445)
  - journal.py backfill (journal.py:848)
  - financial_statements.py Note 7 (financial_statements.py:552) — yesterday's M1 fix, see section 6.

## 5. Cross-module consistency

✓ No issues found.

- Journal coverage complete in journal.py: `post_invoice_raised` (:194), `post_invoice_paid` (:234), `post_invoice_cogs` (:268), `post_expense` (:293), `post_bank_income` (:328), `post_payroll` (:368), `post_expense_paid` (:447), `post_po_received` (:476), `post_po_paid` (:528), `post_stock_adjustment` (:556), asset acquisition/depreciation/disposal (:597/:623/:650), plus idempotent `backfill_company` (:702).
- Debtors Control (1100) and Creditors Control (2000) reconciliation rules compare journal balances to raw invoice/PO totals (payroll.py Rules 6/7, :1507-1597).
- **Import-awareness (2026-07-11 fixes) all verified:**
  - Invoice/expense imports auto-run the journal backfill via `_auto_backfill`; a backfill failure never fails the import (csv_import.py:124-143, :501, :563)
  - Rules 6/7 exclude `source="import"` lines on 1100/2000 and report them as opening balances (payroll.py:1507-1516, :1585-1592)
  - Balance sheet includes 3998 (imported retained earnings) and 3999 (opening balance equity) offsets (payroll.py:1306-1326)
  - Unbalanced journal import groups rejected (csv_import.py:1035-1064)
  - Non-ZAR invoice imports without a positive exchange rate are rejected row-by-row with a clear message (csv_import.py:458-475)

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (declared in the AFS meta/accounting policies and rendered in the frontend — App_js_fixed.js:6058, :11415). Statements produced: income statement, statement of financial position, statement of changes in equity, cash flow (indirect), notes 2-9.

**Standards status (web search 2026-07-18 — unchanged since prior audits):**
- IFRS 18 *Presentation and Disclosure in Financial Statements* — effective annual periods beginning on or after 1 Jan 2027; applies to full-IFRS preparers, not IFRS for SMEs preparers. No ZuZan change required.
- IFRS for SMEs **third edition** (Feb 2025) — effective annual periods beginning on or after 1 Jan 2027, early application permitted. ZuZan's SA FY (1 March–28/29 Feb) is first caught by the FY beginning 1 March 2027 (FY2028). Not yet mandatory — carried action item L4.
- No change in applicable standards since the last audit — moving on per task rules.

**Prior-fix verification (all intact, fresh reads):**
- Finance costs (2026-07-13): interest lines (account 6700 or "interest"/"finance cost" name-match) presented below EBIT; `profit_before_tax = ebit − finance_costs`; tax and net profit derive from `profit_before_tax` (financial_statements.py:199-205, :241, :253-255). ✓
- COGS/staff-cost classifier F1 (2026-07-16) intact (financial_statements.py:211 region). ✓
- **M1 (2026-07-17)**: Note 7 `payables_summary.open_pos` uses journal-netted per-PO AP amounts (credit − debit on 2000, incl. `purchase_order_reversal`, dated ≤ FY end), `po.total_amount` fallback (financial_statements.py:534-565). ✓
- **L1 (2026-07-17)**: open POs NULL-safely filtered to `(received_date or order_date or created_at) <= end`; unpaid credit expenses filtered `expense_date <= end` (financial_statements.py:527-533, :566-571). ✓

**Section 5b — deferred tax: ALREADY IMPLEMENTED (2026-07-14 run) — verified this run, no code changes:**
- Note 9 does **not** hard-code `"deferred_tax": 0.0` — it reports the period movement (`dt_closing − dt_opening`), `total_tax = current + deferred`, effective rate, and opening/closing balances (financial_statements.py:260-262, :593-604).
- `wear_and_tear_rate` column on FixedAsset (database.py:454); ALTER TABLE migration **inside** the migrations list literal (database.py:1321, list closes :1342, executed in the try/except loop :1343-1347) — not dead code.
- Computation (financial_statements.py:78-166): per asset, tax base = cost − straight-line SARS wear-and-tear apportioned from purchase date, floored at 0; temporary difference = carrying − tax base; balance × `_CIT_RATE` 27%. Rate priority: explicit `wear_and_tear_rate` → IN47 category table → name heuristic → None (tax base = carrying ⇒ zero difference). Safety: no assets / no rates ⇒ exactly 0.0; output shape backward-compatible.
- Balance sheet presents the closing balance as a computed non-current DTL/DTA line with matching retained-earnings adjustment so Assets = Equity + Liabilities holds; nothing posted to the journal; equity statement discloses the movement (financial_statements.py:306-342, :675).
- Frontend renders the Note 9 deferred tax row when non-zero (App_js_fixed.js:11353-11354) and DTL/DTA badges in the asset register (App_js_fixed.js:9963-9987). ✓

✓ No new issues found.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date. Verified by web search 2026-07-18 (sources below).

- **PAYE brackets 2026/2027** — TAX_YEARS entry present and matches published tables exactly (payroll.py:127-139): 18% to R245,100; 26% to R383,100; 31% to R530,200; 36% to R695,800; 39% to R887,000; 41% to R1,878,600; 45% above. Base amounts arithmetically consistent. ✓
- **Primary rebate** R17,820 ✓ (payroll.py:137). Secondary/tertiary rebates not implemented (carried note — only relevant if 65+ employees are onboarded).
- **UIF**: 1% employee + 1% employer ✓ (payroll.py:161); ceiling R17,712/month ✓ (payroll.py:138) — matches the R177.12/month cap. **SDL**: 1% ✓ (payroll.py:162).
- **Tax-year selection (L3 fix verified)**: `CURRENT_TAX_YEAR = _current_tax_year()` derives the label from today's date (month ≥ March ⇒ Y/Y+1) with newest-table fallback so payroll never KeyErrors on 1 March (payroll.py:142-155). Resolves to 2026/2027 today. ✓ (Evaluated at import — backend restart picks up a new year; annual task must still add 2027/2028 brackets before 1 March 2027.)
- **Corporate income tax**: 27% unchanged ✓ — dashboard (payroll.py:1069), management accounts (:1924), provisional tax, AFS (`_CIT_RATE`, financial_statements.py:78, :254).
- **VAT**: 15% unchanged ✓ (Budget 2026 kept the rate; the previously proposed increase withdrawn) — payroll.py VAT201 and rate constants; s11F cap R430,000 and 2026/2027 medical tax credits (R376/R254) present (payroll.py:166-174).
- **EMP201 due-day** 7th of following month ✓; IRP6 two-installment logic present ✓ (payroll.py:2106-2117).
- **L2 fix verified**: `ZUZAN_SYSTEM_PROMPT` now quotes "2026/2027 primary rebate R17,820" (main.py:515). ✓

✓ No new issues found. No tax-table edits made (report-only per task rules; 5b needed no edits).

**Sources consulted:** [SARS — Rates of Tax for Individuals](https://www.sars.gov.za/tax-rates/income-tax/rates-of-tax-for-individuals/) · [SARS — Value-Added Tax](https://www.sars.gov.za/types-of-tax/value-added-tax/) · [SARS — Budget 2026 FAQ](https://www.sars.gov.za/about/sars-tax-and-customs-system/budget/budget-2026-frequently-asked-questions/) · [KPMG SA Budget Guide 2026](https://assets.kpmg.com/content/dam/kpmgsites/za/pdf/2026/02/SA%20Budget%20Guide%202026.pdf) · [vatcalc — SA 2026 Budget VAT](https://www.vatcalc.com/south-africa/south-africa-vat-rise/) · [PwC Tax Summaries — South Africa](https://taxsummaries.pwc.com/south-africa/corporate/other-taxes) · [IFRS — IFRS 18](https://www.ifrs.org/issued-standards/list-of-standards/ifrs-18-presentation-and-disclosure-in-financial-statements/) · [IFRS — IFRS for SMEs](https://www.ifrs.org/issued-standards/ifrs-for-smes/) · [IAS Plus — SA reporting framework](https://www.iasplus.com/en/jurisdictions/africa/south-africa) · [SAICA — A new era for financial reporting](https://www.saica.org.za/news/a-new-era-for-financial-reporting/)

## 8. Action items

No new items this run. Carried low-severity items:

| # | Severity | Item | Status |
|---|---|---|---|
| 1 | Low | **L4:** Plan IFRS for SMEs third-edition transition for the FY beginning 1 March 2027 (Section 23 revenue rewrite, updated disclosures); revisit in early-2027 runs. | Open (carried) |
| 2 | Low | Carried from 07-15/07-17: sync App_js_fixed.js → zuzan-app/src/App.js at next build; unify the two deferred-tax calculators (`/fixed-assets/deferred-tax` vs AFS helper); s11F excess carry-forward on annual reconciliation; secondary/tertiary rebates if 65+ employees onboarded. | Open (carried) |
| 3 | Low | Annual tax task: add 2027/2028 TAX_YEARS entry before 1 March 2027 (selection is now date-derived but needs the table; restart backend after adding). | Open (standing) |
