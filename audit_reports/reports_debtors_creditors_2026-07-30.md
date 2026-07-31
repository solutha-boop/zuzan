# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 30 July 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-07-29 (full PASS, no open action items).

**Change detection since last run:** `git rev-parse HEAD` = `43084a7` (deploy 2026-07-27 20:01), identical to the commit audited on every run from 07-28 through 07-29. `git diff 43084a7..HEAD --stat` across all in-scope files returns empty, and `git status` shows only untracked report/log files (no changes to any audited source file). **Zero code changes since yesterday's audit** — every file in scope (`payroll.py`, `main.py`, `companies.py`, `suppliers.py`, `customers.py`, `purchase_orders.py`, `journal.py`, `database.py`, `financial_statements.py`, `csv_import.py`, `fixed_assets.py`, `App_js_fixed.js`) is byte-identical to what was reviewed on 07-29.

Given no code drift, this run re-verifies the substantive logic directly via targeted greps/reads (confirming line references still match) and refreshes external (IFRS/SARS) research, since those facts can change independent of the codebase.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ✅ PASS — logic unchanged, re-verified |
| Debtors (AR) | ✅ PASS — aged from due_date, paid excluded, ZAR amounts |
| Creditors (AP) | ✅ PASS — reversal-aware, bank details decrypted |
| Cross-module consistency | ✅ PASS — full journal coverage, import-awareness intact, migration hygiene intact |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) verified again, no regressions |
| Tax rates (SARS) | ✅ PASS — 2026/2027 tables current, cross-checked against official SARS Budget 2026 Tax Guide PDF |

**Overall: PASS.** No code changes since the last audit; no new action items.

---

## 2. Reports

✓ No issues found. Unchanged from 07-29 — re-confirmed via grep:
- Dashboard (payroll.py:1237-1245): `total_revenue = sum(_to_zar(i) for i in paid_invoices)`; `total_outstanding = sum(_to_zar(i) for i in outstanding_invoices)` over `status IN (sent, overdue)`. Expenses excluded from revenue (separate `total_expenses` aggregation).
- `_to_zar()` applied consistently across every revenue/outstanding aggregation site in payroll.py (lines 1237, 1245, 1630, 1725, 1854, 1917, 2078, 2153, 2345) — dashboard, VAT, cash-flow, management accounts, and YTD views all use the same helper, no divergence found.
- Management-accounts revenue trend and `/reports/management` outstanding block (payroll.py:2151-2216) apply the same `_to_zar()` pattern.
- `/v1/summary` (main.py:447-488): imports `_to_zar`, `_po_delivered_net`, `_bank_import_income` from payroll.py; applies `_to_zar()` to both `total_revenue` (paid invoices, plus bank-import income) and `outstanding` (sent/overdue invoices); `net_profit = total_revenue - total_expenses - total_payroll` (line 488) — payroll costs correctly reduce net profit, kept distinct from `total_expenses` so PO/expense-driven COGS isn't double-counted.

## 3. Debtors

✓ No issues found. Unchanged from 07-29.
- `/reports/debtors-aging` (payroll.py:2435-2495): filters `status IN (sent, overdue)`; ZAR via `_to_zar(inv)`; aging strictly from `due_date` — invoices with no due date go to `not_due`, never inflate overdue; buckets `not_due` / `current` (≤30) / `31_60` / `61_90` / `over_90`. Paid invoices excluded by the status filter.
- Frontend `Debtors` component (App_js_fixed.js) unchanged since 07-27.

## 4. Creditors

✓ No issues found. Unchanged from 07-29.
- `/reports/creditors-aging` (payroll.py:2498-2534+): pulls POs with `status IN (received, partial)`, excludes fully paid; supplier bank details decrypted via `decrypt_field`.
- **Reversal-awareness (2026-07-13 fixes) re-confirmed present in all four call sites:** creditors-aging (payroll.py:2527-2534), Rule 7 (payroll.py:1770-1778), `purchase_orders.py` pay_po (438-445), and `journal.py` backfill (848) — all net `SUM(credit − debit)` with `source IN ("purchase_order", "purchase_order_reversal")`. `financial_statements.py:558` (balance sheet PO liability calc) also included in this set.
- Frontend `Creditors` component (App_js_fixed.js) unchanged.

## 5. Cross-module consistency

✓ No issues found. Unchanged from 07-29.
- Journal coverage complete across invoices, expenses, payroll, POs, inventory, fixed assets.
- Import-awareness (2026-07-11 fixes) intact and unchanged: `csv_import.py` auto-backfills the journal after imports; Rules 6/7 exclude `source == "import"` lines.
- Balance sheet accounts (Debtors/Creditors Control) are built by **account type**, not hardcoded codes, so imported accounts such as 3998/3999 flow through automatically.
- Migration hygiene: `database.py` unchanged; `wear_and_tear_rate` migration (database.py:1363) remains correctly positioned inside the migrations list literal, not after the loop.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (declared in AFS meta). Statements: income statement, statement of financial position, changes in equity, cash flow (indirect), notes 2-9.

**Standards status (re-confirmed via fresh web search this run):**
- IFRS 18 *Presentation and Disclosure in Financial Statements* — still effective for annual periods beginning on or after 1 Jan 2027; applies to full-IFRS preparers, not IFRS for SMEs. EY published an updated "Introduction of IFRS 18" note in July 2026 reiterating the 1 Jan 2027 effective date and the three income/expense categories + two subtotals + management performance measures note — no new information changing ZuZan's applicability (IFRS for SMEs preparer, not full IFRS).
- IFRS for SMEs **third edition** (issued Feb 2025, effective 1 Jan 2027, early adoption permitted) — unchanged since 07-29. IASB continues publishing supporting educational modules, remaining modules due Q3 2026; a call for SMEIG membership nominations is administrative only. No new recognition/measurement requirement affecting ZuZan.
- No new consolidation-exception or other exposure-draft developments found this run.

**Section 5b — deferred tax: already implemented, re-verified this run (financial_statements.py, read/grepped directly):**
- `_deferred_tax_balance` (financial_statements.py:131-172): tax base = cost − straight-line SARS wear-and-tear apportioned from purchase date, floored at 0; temporary difference × `_CIT_RATE` (single-sourced from `fixed_assets.SA_CIT_RATE`, financial_statements.py:78-84).
- Note 9: `deferred_tax_expense = dt_closing − dt_opening` (:266-268); `total_tax = current_tax + deferred_tax` (:601).
- Balance sheet presents closing DTL/DTA (:609-610, :681 movement) with matching retained-earnings adjustment — Assets = Equity + Liabilities preserved by construction. No regressions.
- `wear_and_tear_rate` column on FixedAsset (database.py:483) and its migration (database.py:1363) confirmed present and correctly placed.

✓ No issues found.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date.

- Fetched the official **SARS Budget 2026 Tax Guide** PDF directly this run (rather than relying on secondary aggregator sites) and cross-checked every figure line-by-line against payroll.py:
  - Brackets (payroll.py:132-140) match the SARS guide exactly: 18% to R245,100; 26% to R383,100 (base 44,118); 31% to R530,200 (base 79,998); 36% to R695,800 (base 125,599); 39% to R887,000 (base 185,215); 41% to R1,878,600 (base 259,783); 45% above (base 666,339).
  - Rebates (payroll.py:141-143): primary R17,820, secondary R9,765, tertiary R3,249 — all match the SARS guide exactly. (Note: one third-party aggregator search result this run showed incorrect secondary/tertiary figures of R9,444/R3,145; the official SARS PDF was fetched directly to resolve the discrepancy and confirms the code's R9,765/R3,249 are correct — no action needed, but flagging that aggregator sites should not be trusted over the primary SARS source.)
  - UIF ceiling R17,712/month (payroll.py:144) — confirmed unchanged since 1 June 2021, still current for 2026/2027.
- **UIF** 1%/1% employee/employer (payroll.py:188, 476-477) and **SDL** 1% (payroll.py:189, 482) — match SARS guide exactly.
- **VAT** — standard rate confirmed still **15%** per SARS guide; code constants (payroll.py:1608, :2691) correct. Note: compulsory VAT registration threshold increased to R2.3m per Budget 2026 — this is a registration-threshold change with no bearing on ZuZan's VAT calculation logic (VAT_RATE only), no code impact.
- **Corporate income tax** 27%, confirmed unchanged in the SARS guide for years of assessment ending 1 April 2026 – 31 March 2027; single-sourced via `SA_CIT_RATE`. ✓
- Provisional `2027/2028` TAX_YEARS entry (payroll.py:151-166, verified via Read to be a correctly-typed key — not a stray escape sequence as a grep display artifact briefly suggested) remains a placeholder copy of 2026/2027 pending the Feb 2027 Budget — flagged as a standing reminder, not a defect.
- Rates unchanged and current tax year present — no edits made (report-only per task rules).

**Sources consulted:** [SARS Budget 2026 Tax Guide (official PDF)](https://www.sars.gov.za/wp-content/uploads/Docs/Budget/Budget2026/Budget-tax-guide-2026-web-version.pdf) · [Changes for Filing Season 2026 — SARS](https://www.sars.gov.za/latest-news/changes-for-filing-season-2026/) · [Budget 2026 FAQ — SARS](https://www.sars.gov.za/about/sars-tax-and-customs-system/budget/budget-2026-frequently-asked-questions/) · [SARS Tax Tables 2026/2027 — Accounter](https://accounter.co.za/news/sars-tax-tables-2026-2027) · [UIF Rates & Ceiling History — UIFCalculator](https://uifcalculator.com/uif-rates-by-year) · [June 2026 IFRS for SMEs Accounting Standard Update — IFRS.org](https://www.ifrs.org/supporting-implementation/2015-ifrs-for-smes-supporting-materials/sme-updates/2026/june-2026-ifrs-for-smes-accounting-standard-update/) · [Introduction of IFRS 18 — EY, July 2026](https://www.ey.com/en_az/newsroom/2026/07/introduction-of-ifrs-18-presentation-and-disclosure-in-financial-statements)

## 8. Action items

None open.

**Standing reminders (not defects, carried from prior reports):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry (payroll.py:151+) after Budget Feb 2027 and restart the backend;
(b) early-2027 runs execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`) — Section 23 revenue and Section 19 business-combinations changes are most relevant to ZuZan; watch for any new Consolidation Exception exposure-draft developments;
(c) the AFS PayFast payment/ad-hoc tokenization feature and the `/reports/ai-insights` (AI management-pack) feature remain outside this audit's Reports/Debtors/Creditors/AFS-content/tax scope — flag for inclusion if a future audit's file list is expanded;
(d) NBCPSS private security payroll mode (grades, allowances, BC levy, PSIRA fee) predates this audit's baseline and doesn't affect the audited totals, but isn't yet part of this checklist's explicit scope — consider adding it to the payroll section of future audits.
