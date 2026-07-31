# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 31 July 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-07-30 (full PASS, no open action items).

**Change detection since last run:** `git rev-parse HEAD` = `43084a7` (deploy 2026-07-27 20:01), identical to the commit audited on every run from 07-28 through 07-30. `git diff 43084a7..HEAD --stat` across all in-scope files (`App_js_fixed.js`, `payroll.py`, `companies.py`, `suppliers.py`, `customers.py`, `purchase_orders.py`, `journal.py`, `database.py`, `main.py`, `financial_statements.py`, `csv_import.py`, `fixed_assets.py`) returns empty; `git status` shows only untracked report/log files. **Zero code changes since yesterday's audit.**

Given no code drift, this run re-verifies the substantive logic directly via targeted greps (confirming line references still match) and refreshes external (IFRS/SARS) research, since those facts can change independent of the codebase.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ✅ PASS — logic unchanged, re-verified |
| Debtors (AR) | ✅ PASS — aged from due_date, paid excluded, ZAR amounts |
| Creditors (AP) | ✅ PASS — reversal-aware, bank details decrypted |
| Cross-module consistency | ✅ PASS — full journal coverage, import-awareness intact, migration hygiene intact |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) verified again, no regressions |
| Tax rates (SARS) | ✅ PASS — 2026/2027 tables current, no rate changes since 07-30 |

**Overall: PASS.** No code changes since the last audit; no new action items.

---

## 2. Reports

✓ No issues found. Unchanged from 07-30 — re-confirmed via grep:
- Dashboard (payroll.py:1237, 1245): `total_revenue = sum(_to_zar(i) for i in paid_invoices)`; `total_outstanding = sum(_to_zar(i) for i in outstanding_invoices)`. Expenses excluded from revenue (separate aggregation).
- `_to_zar()` (defined payroll.py:17) applied consistently across every revenue/outstanding aggregation site: lines 1237, 1245, 1397, 1630, 1642, 1725, 1854, 1917, 2078, 2153, 2170, 2345, 2458 — dashboard, VAT, cash-flow, management accounts, and YTD views all use the same helper. No divergence found.
- `/v1/summary` (main.py:447-488): imports `_to_zar`, `_po_delivered_net`, `_bank_import_income` from payroll.py; applies `_to_zar()` to both revenue and outstanding; `net_profit = total_revenue - total_expenses - total_payroll` — payroll costs reduce net profit, kept distinct from `total_expenses` so PO/expense-driven COGS isn't double-counted.

## 3. Debtors

✓ No issues found. Unchanged from 07-30.
- `/reports/debtors-aging` (payroll.py:2435-2495): filters `status IN (sent, overdue)`; ZAR via `_to_zar(inv)`; aging strictly from `due_date` (buckets `not_due`/`current`/`31_60`/`61_90`/`over_90`). Paid invoices excluded by the status filter.
- Frontend `Debtors` component (App_js_fixed.js) unchanged since 07-27.

## 4. Creditors

✓ No issues found. Unchanged from 07-30.
- `/reports/creditors-aging` (payroll.py:2498-2534+): pulls POs with `status IN (received, partial)`, excludes fully paid; supplier bank details decrypted via `decrypt_field`.
- **Reversal-awareness (2026-07-13 fixes) re-confirmed present in all five call sites:** creditors-aging (payroll.py:2527-2534), Rule 7 (payroll.py:1770-1778), `purchase_orders.py` pay_po (438-445), `journal.py` backfill (848), and `financial_statements.py:558` (balance sheet PO liability calc) — all net `SUM(credit − debit)` with `source IN ("purchase_order", "purchase_order_reversal")`.
- Frontend `Creditors` component (App_js_fixed.js) unchanged.

## 5. Cross-module consistency

✓ No issues found. Unchanged from 07-30.
- Journal coverage complete across invoices, expenses, payroll, POs, inventory, fixed assets.
- Import-awareness (2026-07-11 fixes) intact: `csv_import.py` auto-backfills the journal after imports; Rules 6/7 exclude `source == "import"` lines on 1100/2000.
- Balance sheet accounts (Debtors/Creditors Control) are built by **account type**, not hardcoded codes, so imported accounts such as 3998/3999 flow through automatically.
- Migration hygiene: `wear_and_tear_rate` migration (database.py:1363) remains correctly positioned inside the migrations list literal, not after the loop.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (declared in AFS meta). Statements: income statement, statement of financial position, changes in equity, cash flow (indirect), notes 2-9.

**Standards status (re-confirmed via fresh web search this run):**
- **IFRS 18** *Presentation and Disclosure in Financial Statements* — confirmed still effective for annual periods beginning on or after 1 Jan 2027, earlier application permitted; applies to full-IFRS preparers, not IFRS for SMEs. No change since 07-30.
- **IFRS for SMEs third edition** (issued 27 Feb 2025, effective 1 Jan 2027, early adoption permitted) — unchanged. Key changes (control definition aligned to IFRS 10, merged financial-instruments sections aligned to IFRS 9 principles, new revenue model closer to full IFRS, consolidated fair-value section, 2018 Conceptual Framework alignment) remain as previously documented; none require code changes yet given the 1 Jan 2027 effective date and ZuZan's IFRS-for-SMEs (2nd edition) presentation basis.
- No new consolidation-exception or exposure-draft developments found this run.

**Section 5b — deferred tax: already implemented, re-verified this run (financial_statements.py, read/grepped directly):**
- `_deferred_tax_balance` (financial_statements.py:131): tax base = cost − straight-line SARS wear-and-tear apportioned from purchase date, floored at 0; temporary difference × CIT rate.
- Note 9: `deferred_tax_expense = dt_closing − dt_opening` (:266-268); `total_tax = tax_expense + deferred_tax_expense` (:601).
- Balance sheet presents closing DTL/DTA (:606-610, :681 movement) with matching retained-earnings adjustment — Assets = Equity + Liabilities preserved by construction. No regressions.
- `wear_and_tear_rate` column on FixedAsset (database.py:483) and its migration (database.py:1363) confirmed present and correctly placed.

✓ No issues found.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date.

- No rate changes found since the 07-30 audit (which cross-checked directly against the official SARS Budget 2026 Tax Guide PDF). This run's search confirms filing-season operational news (auto-assessments issued 1-12 July, manual filing opened 13 July, non-provisional deadline 23 Oct 2026 / provisional 22 Jan 2027) but no changes to brackets, rebates, UIF ceiling, or CIT/VAT rates.
- **Brackets & rebates** (payroll.py:132-143) — unchanged, previously verified line-by-line against the SARS guide.
- **UIF ceiling** R17,712/month (payroll.py:144), **UIF** 1%/1% (payroll.py:188, 476-477), **SDL** 1% (payroll.py:189, 482) — unchanged.
- **VAT** standard rate 15% (payroll.py:1608, 2691) — unchanged. Compulsory VAT registration threshold increase to R2.3m (from R1m, effective 1 April 2026) reconfirmed this run — registration-threshold only, no bearing on ZuZan's `VAT_RATE` calculation logic.
- **Corporate income tax** 27% (`SA_CIT_RATE`, single-sourced) — unchanged, confirmed for years of assessment ending 1 April 2026 – 31 March 2027.
- Provisional `2027/2028` `TAX_YEARS` entry (payroll.py:151-166) remains a placeholder copy of 2026/2027 pending the Feb 2027 Budget — standing reminder, not a defect.
- Rates unchanged and current tax year present — no edits made (report-only per task rules).

**Sources consulted:** [IFRS 18 Presentation and Disclosure in Financial Statements — IFRS.org](https://www.ifrs.org/issued-standards/list-of-standards/ifrs-18-presentation-and-disclosure-in-financial-statements/) · [Applying IFRS: A closer look at IFRS 18 (updated April 2026) — EY](https://www.ey.com/content/dam/ey-unified-site/ey-com/en-gl/technical/ifrs-technical-resources/documents/ey-gl-ifrs-apply-ifrs-18-updated-v2-04-2026.pdf) · [IASB issues major update to IFRS for SMEs — IFRS.org](https://www.ifrs.org/news-and-events/news/2025/02/iasb-issues-major-update-smes-accounting-standard/) · [Third edition of the IFRS for SMEs Accounting Standard — ACCA](https://www.accaglobal.com/learning-and-events/corporate-reporting/third-edition-ifrs-for-smes.html) · [SARS Tax Calendar 2026 & Deadline Tracker — TaxTim](https://www.taxtim.com/za/tax-deadlines) · [Budget Speech 2026/2027: Tax Overview — Werksmans Attorneys](https://werksmans.com/budget-speech-2026-2027-tax-overview/) · [Budget 2026 FAQ — SARS](https://www.sars.gov.za/about/sars-tax-and-customs-system/budget/budget-2026-frequently-asked-questions/)

## 8. Action items

None open.

**Standing reminders (not defects, carried from prior reports):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry (payroll.py:151+) after Budget Feb 2027 and restart the backend;
(b) early-2027 runs should execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`) — Section 23 revenue and Section 19 business-combinations changes are most relevant to ZuZan; watch for any new Consolidation Exception exposure-draft developments;
(c) the AFS PayFast payment/ad-hoc tokenization feature and the `/reports/ai-insights` (AI management-pack) feature remain outside this audit's Reports/Debtors/Creditors/AFS-content/tax scope — flag for inclusion if a future audit's file list is expanded;
(d) NBCPSS private security payroll mode (grades, allowances, BC levy, PSIRA fee) predates this audit's baseline and doesn't affect the audited totals, but isn't yet part of this checklist's explicit scope — consider adding it to the payroll section of future audits.
