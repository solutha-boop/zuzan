# Reports / Debtors / Creditors Audit — 2026-07-12

Scope: `/reports/dashboard`, `/reports/management`, `/v1/summary`, Debtors (AR), Creditors (AP), cross-module journal coverage, IFRS compliance (AFS), SARS tax rates.
Files reviewed: payroll.py, main.py, journal.py, purchase_orders.py, companies.py, csv_import.py, financial_statements.py, database.py, App_js_fixed.js.

Prior report: 2026-07-11 (run 2). Change detection: **payroll.py, csv_import.py, journal.py, companies.py, purchase_orders.py are byte-unchanged since the last audit** (mtimes precede it). Changed since: **financial_statements.py** (M4 fix), **main.py + database.py** (site analytics, category-rules), **App_js_fixed.js** (invoice status alignment, employee edit modal, Patterson grades, bank-import parser rewrite). This run focused verification on the changed files plus spot-checks on the stable ones.

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | **PASS** |
| Debtors (AR) | **PASS** |
| Creditors (AP) | **PASS** |
| Cross-module | **PASS** — L1 (Low) carried over; new tables' migrations correctly placed |
| IFRS compliance (AFS) | **PASS** — yesterday's M4 accrual fix verified intact; standards unchanged |
| Tax (company + payroll) | **PASS** — 2026/2027 tables current, re-verified against SARS/Treasury |

New findings this run: one Low (stale "pending" status filter in a management-accounts drill-down). No regressions.

## 2. Reports

✓ No issues found.

- `total_revenue`: paid invoices only via `_to_zar()` (payroll.py:512–516) + bank-import income; `_to_zar` (payroll.py:17) prefers `paid_amount_zar`, falls back to amount × exchange_rate, ZAR passthrough. Unchanged since last audit.
- `total_outstanding`: sent + overdue via `_to_zar()` (payroll.py:522, 1426). Expenses excluded from revenue; payroll and PO COGS (`_po_delivered_net`) included in expenses without double-counting.
- Management trend loop applies `_to_zar()` per month (payroll.py:1444); tax provision at `CORP_TAX_RATE` 27% (1514, 1573).
- `/v1/summary` (main.py:266–303) still imports and uses `_to_zar`, `_po_delivered_net`, `_bank_import_income` — verified intact after main.py's analytics changes.
- **Frontend drill-down improvement verified:** the dashboard "Outstanding" drill now filters `["sent","overdue"]` (App_js_fixed.js:579) and the invoice list derives overdue from `due_date` client-side (`isOverdue`), matching backend semantics. Revenue drill uses paid-only with backend-identical ZAR conversion (App_js_fixed.js:525–543).

## 3. Debtors

✓ No issues found.

- `/reports/debtors-aging` unchanged (payroll.py): status IN (sent, overdue); paid/draft excluded; `_to_zar()` per invoice; aging strictly from `due_date` with no-due-date invoices in `not_due`.
- Frontend `Debtors` (App_js_fixed.js:5093–5107) purely backend-driven, refreshes on invoice changes. Buckets not_due / 0–30 / 31–60 / 61–90 / 90+ (5109–5114).
- Chart-of-accounts labels corrected in frontend: Trade Receivables now code 1100 matching journal Debtors Control; Trade Payables note documents the 2110-display / 2000-journal mapping. Cosmetic consistency improvement, no data-flow effect.
- Import fixes (H1 auto-backfill csv_import.py:124–136, 501, 563; M3 non-ZAR exchange-rate enforcement csv_import.py:458–492) — file unchanged, verified by spot-check.

## 4. Creditors

✓ No issues found.

- `/reports/creditors-aging` unchanged: received/partial POs only, fully-paid excluded; AP from journal credits on account 2000; aged from `received_date` + supplier payment terms; bank details decrypted via `decrypt_field`.
- Frontend `Creditors` (App_js_fixed.js:5226–5232) backend-driven.
- `pay_po` still clears the journal AP balance (purchase_orders.py unchanged).

## 5. Cross-module

Journal event coverage — all posting call sites verified present (40 references across 8 files): invoice raised/payment (companies.py, portal.py), expense + expense payment (companies.py), PO receipt/payment (purchase_orders.py), payroll run (payroll.py), bank-import income (companies.py), import auto-backfill (csv_import.py).

Import-awareness fixes of 2026-07-11 — all in unchanged files, spot-checked intact: Rules 6/7 import exclusions on 1100/2000, balance sheet 3998/3999 + other imported accounts, unbalanced journal-group rejection, non-ZAR import exchange-rate requirement.

New schema objects since last audit (database.py:1175–1204): `category_rules` and `site_visits` tables + indexes are **correctly placed inside the migrations list literal** before the executing loop (list closes at :1205) — the dead-code migration pitfall does not recur. Neither table touches the accounting data flow.

Findings:

- **[L5 — Low, new]** Management-accounts "Outstanding" drill-down still filters `["pending","sent","overdue"]` (App_js_fixed.js:4007) while the dashboard drill was corrected to `["sent","overdue"]` (:579). Harmless — no invoice ever holds status "pending" — but inconsistent; align for clarity.
- **[L1 — Low, carried over]** Per-PO AP-credit lookups ignore reversal debits (payroll.py ~1698–1718; purchase_orders.py ~427–448). Still unreachable in practice (since 2026-07-09).

## 6. IFRS compliance (AFS)

Framework: **IFRS for SMEs** (financial_statements.py:410 meta basis; docstring). Correct for a SA private company under Companies Act 71 of 2008 regulations.

**Yesterday's M4 fix verified intact in code** (financial_statements.py changed 2026-07-11 10:55):

- Basis-of-preparation note states accrual recognition at invoice issue per Section 23 (financial_statements.py:497–503).
- Note 4 (Revenue by customer) uses all issued invoices — sent/overdue/paid (:297–304).
- Note 3 (Receivables aging) converts via `_inv_total_zar` at the raised-basis rate (:64–65, 275–286), matching 1100 AR control postings.

Standards status re-verified 12 July 2026 — **unchanged since last audit**: IFRS for SMEs 3rd edition effective for periods beginning on/after 1 Jan 2027 (first mandatory ZuZan FY: 1 Mar 2027 – 29 Feb 2028); IFRS 18 (1 Jan 2027) applies to full-IFRS preparers only, not applicable to an IFRS for SMEs entity. Current statements remain compliant on the 2015 second edition.
Sources: [IFRS Foundation — IFRS for SMEs](https://www.ifrs.org/issued-standards/ifrs-for-smes/), [IFRS Foundation — 3rd edition announcement](https://www.ifrs.org/news-and-events/news/2025/02/iasb-issues-major-update-smes-accounting-standard/), [IFRS 18](https://www.ifrs.org/issued-standards/list-of-standards/ifrs-18-presentation-and-disclosure-in-financial-statements/), [SAICA — new IFRS standards](https://www.saica.org.za/resources/corporate-reporting/financial-reporting/new-ifrs-standards/).

Carried-over Low items: `deferred_tax` hard-coded 0.0 (:395); `finance_costs` hard-coded 0.0 (:424) — wire to journal interest accounts before bank-feed interest lands.

## 7. Tax updates (company + payroll)

Current SARS tax year: **2026/2027** (1 Mar 2026 – 28 Feb 2027). Re-verified against SARS/Treasury — **all rates current, no changes required, no changes since last audit**:

- **PAYE 2026/2027** (payroll.py:127–139): brackets 18% to R245,100 … 45% above R1,878,600 ✓; primary rebate R17,820 ✓ (tax-free threshold R99,000). Secondary R9,765 / tertiary R3,249 still not implemented — acceptable, noted as future enhancement.
- **Tax-year selection**: `CURRENT_TAX_YEAR = "2026/2027"` (payroll.py:142), safe fallback in `calc_paye`/`calc_payroll` (:206, 240) ✓. Annual task must flip on 1 Mar 2027.
- **UIF**: ceiling R17,712/month (:138), 1% + 1% ✓ (max R177.12 each). **SDL** 1% with R500k exemption ✓.
- **CIT 27%** (payroll.py:566, 1417, 1514; financial_statements.py tax note) ✓ — unchanged for years of assessment ending 1 Apr 2026 – 31 Mar 2027.
- **VAT 15%** (`VAT_RATE` payroll.py:885, 1867; 15/115 fraction in VAT201) ✓ — no announced rate change.
- **EMP201 due-day**: 7th of following month ✓.
- Frontend payroll module price changed R17.50 → R34/employee (App_js_fixed.js) — commercial, not a tax rate; no audit impact.

Sources: [SARS — rates of tax for individuals](https://www.sars.gov.za/tax-rates/income-tax/rates-of-tax-for-individuals/), [Treasury — Budget 2026 Tax Guide](https://www.treasury.gov.za/documents/national%20budget/2026/sars/Budget%202026%20Tax%20guide.pdf), [SARS — Budget 2026 FAQ](https://www.sars.gov.za/about/sars-tax-and-customs-system/budget/budget-2026-frequently-asked-questions/), [KPMG SA Budget Guide 2026](https://assets.kpmg.com/content/dam/kpmgsites/za/pdf/2026/02/SA%20Budget%20Guide%202026.pdf), [SARS — Guide for Employers: Employees' Tax 2027](https://www.sars.gov.za/guide-for-employers-in-respect-of-employees-tax-2027/).

## 8. Action items

1. **[Low — L5, new]** ~~Align the management-accounts outstanding drill filter to `["sent","overdue"]`~~ — **RESOLVED same day** (App_js_fixed.js:4007 now filters `["sent","overdue"]`, matching the dashboard drill).
2. **[Low — L1]** Make per-PO AP-credit lookups reversal-aware (carried over from 2026-07-09).
3. **[Low — L3]** Revisit deferred-tax disclosure once fixed-asset temporary differences are material (financial_statements.py:395).
4. **[Low — L4]** Wire `finance_costs` to journal interest accounts before bank-feed interest lands (financial_statements.py:424).
5. **[Low — planning]** IFRS for SMEs 3rd-edition transition review ahead of FY2028; secondary/tertiary rebates if 65+ employees onboarded; annual tax task flips `CURRENT_TAX_YEAR` on 1 Mar 2027.

## 9. Changes since last run (2026-07-11 run 2)

The M4 accrual fix in financial_statements.py is verified intact. New code since last audit (site analytics, category-rules learning, employee edit endpoint, Settings redesign, bank-import parser rewrite, invoice "pending"→"sent" status alignment) does not touch the audited reporting/AR/AP data paths, except the frontend drill-down filters — one of which (dashboard) was correctly fixed and one (management accounts, L5) was missed. New migrations are correctly placed. No Critical/High/Medium findings; all prior fixes hold.
