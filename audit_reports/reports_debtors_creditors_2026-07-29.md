# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 29 July 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-07-28 (full PASS, no open action items).

**Change detection since last run:** `git rev-parse HEAD` = `43084a7` (deploy 2026-07-27 20:01), identical to the commit audited on 07-28. `git diff 43084a7..HEAD --stat` across all in-scope files returns empty, and `git status` shows a clean working tree (no uncommitted changes). **Zero code changes since yesterday's audit** — every file in scope (`payroll.py`, `main.py`, `companies.py`, `suppliers.py`, `customers.py`, `purchase_orders.py`, `journal.py`, `database.py`, `financial_statements.py`, `csv_import.py`, `fixed_assets.py`, `App_js_fixed.js`) is byte-identical to what was reviewed on 07-28.

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
| Tax rates (SARS) | ✅ PASS — 2026/2027 tables current, no Budget/SARS rate changes since 07-28 |

**Overall: PASS.** No code changes since the last audit; no new action items.

---

## 2. Reports

✓ No issues found. Unchanged from 07-28 — re-confirmed via grep:
- Dashboard (payroll.py:1237-1245): `total_revenue = sum(_to_zar(i) for i in paid_invoices)` then `+= _bank_import_income(db, cid)`; `total_outstanding = sum(_to_zar(i) for i in outstanding_invoices)` over `status IN (sent, overdue)`. Expenses excluded from revenue (separate `total_expenses` aggregation, payroll.py:1247+).
- `gross_profit = total_revenue - total_expenses`; `net_profit = gross_profit - total_payroll` (payroll.py:1287-1288) — payroll costs correctly reduce net profit, kept separate from `total_expenses` so there's no double count with PO/expense-driven COGS.
- Management-accounts revenue trend and `/reports/management` outstanding block (payroll.py:2151-2216) apply the same `_to_zar()` pattern.
- `/v1/summary` (main.py:447-481): imports `_to_zar`, `_po_delivered_net`, `_bank_import_income` from payroll.py and applies `_to_zar()` to both `total_revenue` (paid invoices) and `outstanding` (sent/overdue invoices) — consistent with the dashboard.

## 3. Debtors

✓ No issues found. Unchanged from 07-28.
- `/reports/debtors-aging` (payroll.py:2435-2495): filters `status IN (sent, overdue)`; ZAR via `_to_zar(inv)` (line 2458); aging strictly from `due_date` — invoices with no due date go to `not_due`, never inflate overdue (lines 2454, 2463-2465); buckets `not_due` / `current` (≤30) / `31_60` / `61_90` / `over_90`. Paid invoices excluded by the status filter.
- Frontend `Debtors` component (App_js_fixed.js) unchanged since 07-27.

## 4. Creditors

✓ No issues found. Unchanged from 07-28.
- `/reports/creditors-aging` (payroll.py:2498-2534+): pulls POs with `status IN (received, partial)`, excludes fully paid; supplier bank details decrypted via `decrypt_field` (payroll.py:2509).
- **Reversal-awareness (2026-07-13 fixes) re-confirmed:** both the creditors-aging endpoint (payroll.py:2526-2534) and Rule 7 (payroll.py:1770-1778) net `SUM(credit − debit)` with `source IN ("purchase_order", "purchase_order_reversal")`.
- Frontend `Creditors` component (App_js_fixed.js) unchanged.

## 5. Cross-module consistency

✓ No issues found. Unchanged from 07-28.
- Journal coverage complete across invoices, expenses, payroll, POs, inventory, fixed assets.
- Import-awareness (2026-07-11 fixes) intact and unchanged: `csv_import.py` auto-backfills the journal after imports (`_auto_backfill`, csv_import.py:124-143, invoked at lines 501 and 563); Rules 6/7 exclude `source == "import"` lines (payroll.py:1736, :1812).
- Balance sheet accounts (Debtors/Creditors Control) are built by **account type**, not hardcoded codes — `_acct_lines(db, cid, AccountType.asset/liability/equity, ...)` (financial_statements.py:273, 287, 299 and others) — so imported accounts such as 3998/3999 flow through automatically regardless of code, confirming reconciliation robustness without needing a hardcoded account-code check.
- Migration hygiene: `database.py` has had no new migrations since 07-26; the `wear_and_tear_rate` migration (database.py:1363) remains correctly positioned inside the migrations list literal, not after the loop.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (declared in AFS meta). Statements: income statement, statement of financial position, changes in equity, cash flow (indirect), notes 2-9.

**Standards status (re-confirmed via fresh web search this run):**
- IFRS 18 *Presentation and Disclosure in Financial Statements* — still effective for annual periods beginning on or after 1 Jan 2027; applies to full-IFRS preparers, not IFRS for SMEs. No ZuZan change required yet.
- IFRS for SMEs **third edition** (issued Feb 2025, effective 1 Jan 2027, early adoption permitted) — no change since 07-28. The IASB published a June 2026 IFRS for SMEs Accounting Standard Update and continues to release supporting educational modules (remaining modules due Q3 2026) — implementation guidance only, no new recognition/measurement requirement affecting ZuZan.
- The IASB's proposed extension of the consolidation exception for eligible SMEs remains an open Exposure Draft, comment period to 9 September 2026 — still not finalized, unchanged from last run.

**Section 5b — deferred tax: already implemented, re-verified this run (financial_statements.py, read/grepped directly):**
- `_deferred_tax_balance` (financial_statements.py:131): tax base = cost − straight-line SARS wear-and-tear apportioned from purchase date, floored at 0; temporary difference × `_CIT_RATE` (single-sourced from `fixed_assets.SA_CIT_RATE`, financial_statements.py:78-84).
- Note 9: `deferred_tax_expense = dt_closing − dt_opening` (:266-268); `total_tax = current_tax + deferred_tax` (:601, :606).
- Balance sheet presents closing DTL/DTA (:609-610, :681 movement) with matching retained-earnings adjustment — Assets = Equity + Liabilities preserved by construction. No regressions.
- `wear_and_tear_rate` column on FixedAsset (database.py:483) and its migration (database.py:1363) confirmed present and correctly placed.

✓ No issues found.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date.

- Fresh web search this run confirms no rate changes since 07-28: SARS Filing Season 2026 news (auto-assessment expansion to some provisional taxpayers, ITR12 form redesign, WhatsApp notice-of-assessment delivery, prepopulated medical-aid dropdown) are individual-taxpayer filing/process changes with no bearing on ZuZan's payroll/company tax calculations.
- The s20A ring-fencing-of-losses change (39% marginal-rate trigger instead of 45%, for years of assessment from 1 March 2026) remains an individual/personal-tax provision with no equivalent in ZuZan's company/payroll logic — no code impact, noted for completeness only (unchanged from 07-28).
- 2026/2027 brackets (payroll.py:131-145) re-confirmed unchanged: top bracket threshold R1,878,600 at 45%, base R666,339; primary rebate R17,820, secondary R9,765, tertiary R3,249; UIF ceiling R17,712/month.
- **UIF** 1%/1% employee/employer (payroll.py:188) and **SDL** 1% (payroll.py:189) — unchanged, current.
- **VAT** — standard rate confirmed still **15%**; code constants (payroll.py:1608, :2691) correct.
- **Corporate income tax** 27%, single-sourced via `SA_CIT_RATE` — unchanged. ✓
- Provisional `2027/2028` TAX_YEARS entry (payroll.py:151+, a deliberate copy of 2026/2027 so the date-selector has an explicit match from 1 March 2027) remains a placeholder pending the Feb 2027 Budget — flagged as a standing reminder, not a defect for the current tax year.
- Rates unchanged and current tax year present — no edits made (report-only per task rules).

**Sources consulted:** [June 2026 IFRS for SMEs Accounting Standard Update — IFRS.org](https://www.ifrs.org/supporting-implementation/2015-ifrs-for-smes-supporting-materials/sme-updates/2026/june-2026-ifrs-for-smes-accounting-standard-update/) · [IASB proposes extending consolidation exception for eligible SMEs — IFRS.org](https://www.ifrs.org/news-and-events/news/2026/05/iasb-proposes-extending-consolidation-exception-eligible-smes/) · [Third edition of the IFRS for SMEs Accounting Standard — ACCA](https://www.accaglobal.com/learning-and-events/corporate-reporting/third-edition-ifrs-for-smes.html) · [SARS announces dates for tax season 2026 — BusinessTech](https://businesstech.co.za/news/finance/863009/sars-announces-dates-for-tax-season-2026-when-to-expect-auto-assessments/) · [Changes for Filing Season 2026 — SARS](https://www.sars.gov.za/latest-news/changes-for-filing-season-2026/) · [SARS tax season 2026: Here's what's changed — TheSouthAfrican](https://www.thesouthafrican.com/news/sars-tax-season-2026-heres-whats-changed/) · [SARS rolls out phased Filing Season — SARS media release](https://www.sars.gov.za/media-release/sars-rolls-out-phased-filing-season-urges-taxpayers-to-wait-their-turn/)

## 8. Action items

None open.

**Standing reminders (not defects, carried from prior reports):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry (payroll.py:151+) after Budget Feb 2027 and restart the backend;
(b) early-2027 runs execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`) — Section 23 revenue and Section 19 business-combinations changes are most relevant to ZuZan; watch the May-2026 Consolidation Exception exposure draft (comment period closes 9 September 2026);
(c) the AFS PayFast payment/ad-hoc tokenization feature and the `/reports/ai-insights` (AI management-pack) feature remain outside this audit's Reports/Debtors/Creditors/AFS-content/tax scope — flag for inclusion if a future audit's file list is expanded;
(d) NBCPSS private security payroll mode (grades, allowances, BC levy, PSIRA fee) predates this audit's baseline and doesn't affect the audited totals, but isn't yet part of this checklist's explicit scope — consider adding it to the payroll section of future audits.
