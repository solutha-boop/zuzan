# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 28 July 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-07-27 (full PASS, no open action items).

**Change detection since last run:** `git diff bb969b8..HEAD` (baseline 2026-07-24 22:07) across the audit-scope files shows real changes in only two files, both **out of audit scope**:
- `payroll.py` (+98/-0 lines): a new `/reports/ai-insights` POST endpoint (Business-plan AI management-pack summaries via Anthropic API) and a `PLAN_PRICES` fallback dict price change (professional R899→R699, business R1499→R1299). Neither touches revenue/outstanding/expense/payroll/PO aggregation logic.
- `App_js_fixed.js` (+107/-16 lines): frontend for the same AI Insights panel, a Reports-tab reorder (cosmetic), plan-price display updates, and a "Manage Billing" button replaced with a PayFast "Add/Update Payment Method" flow. No changes to the `Debtors`/`Creditors` components (still at `App_js_fixed.js:6002` and `:6128`, byte-unchanged) or to any Reports data-fetching logic.
- `main.py` (ignore-whitespace diff): +4/-3 real lines — `run_monthly_charges()` added to the startup billing-check sequence, a growing disabled-middleware comment, and the same MRR price-dict change. `/v1/summary` (main.py:444-489) is byte-identical to 07-27.
- `database.py`: no diff since 07-26 (already covered by 07-27's report — payfast_token/next_billing_date columns, afs_payments table, correctly inside the migrations list literal).
- `companies.py`, `suppliers.py`, `customers.py`, `purchase_orders.py`, `journal.py`, `financial_statements.py`, `csv_import.py`, `fixed_assets.py` — zero diff since 2026-07-24.

Re-verified the substantive logic directly via targeted greps (line numbers shifted slightly due to the new ai-insights endpoint, but content is intact): dashboard revenue/outstanding (`payroll.py:1230-1245`), reversal-aware AP netting (`payroll.py:1770-1778` Rule 7, `:2499-2534` creditors-aging), debtors-aging bucket logic (`payroll.py:2438-2495`), deferred-tax module (`financial_statements.py:78-328`), and the 2026/2027 `TAX_YEARS` bracket table (`payroll.py:131-145`) — all identical to 07-27 findings. Refreshed external (SARS/IFRS) research since those facts can change independent of the codebase.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ✅ PASS — logic unchanged, re-verified |
| Debtors (AR) | ✅ PASS — aged from due_date, paid excluded, ZAR amounts |
| Creditors (AP) | ✅ PASS — reversal-aware, bank details decrypted |
| Cross-module consistency | ✅ PASS — full journal coverage, import-awareness intact, migration hygiene intact |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) verified again, no regressions |
| Tax rates (SARS) | ✅ PASS — 2026/2027 tables current, no Budget/SARS rate changes since 07-27 |

**Overall: PASS.** No open action items. Only out-of-scope AI Insights feature and billing/PayFast changes since the last run; audited accounting logic unchanged.

---

## 2. Reports

✓ No issues found. Unchanged from 07-27 — re-confirmed via grep:
- `/v1/summary` (main.py:444-489): revenue from paid invoices + `_bank_import_income`; expenses = ex-VAT expense rows + PO COGS (`_po_delivered_net`, received/partial/paid POs only) + depreciation; payroll cost summed separately from `Payslip.total_cost`; outstanding via `_to_zar()` on sent/overdue invoices only. No double counting between expense categories.
- Dashboard (payroll.py:1230-1245): `total_revenue = sum(_to_zar(i) for i in paid_invoices)` then `+= _bank_import_income(db, cid)`; `total_outstanding = sum(_to_zar(i) for i in outstanding_invoices)`.
- New `/reports/ai-insights` endpoint (payroll.py, added since 07-27) is a read-only summarisation layer over numbers the frontend already computed from these same endpoints — it does not recompute or alter revenue/expense/outstanding totals, and is gated to the Business plan.

## 3. Debtors

✓ No issues found. Unchanged from 07-27.
- `/reports/debtors-aging` (payroll.py:2438-2495) filters `status IN (sent, overdue)`; ZAR via `_to_zar(inv)`; aging strictly from `due_date` (invoices with no due date go to `not_due`, never inflate overdue); buckets not_due / current / 31-60 / 61-90 / 90+. Paid invoices excluded (status filter).
- Frontend `Debtors` component (App_js_fixed.js:6002) unchanged.

## 4. Creditors

✓ No issues found. Unchanged from 07-27.
- `/reports/creditors-aging` (payroll.py:2498-2534+) pulls received/partial POs, excludes fully paid; supplier bank details decrypted via `decrypt_field` (payroll.py:2509, :2577-2579).
- **Reversal-awareness (2026-07-13 fixes) re-confirmed:** both the creditors-aging endpoint (payroll.py:2527-2534) and Rule 7 (payroll.py:1770-1778) net `SUM(credit − debit)` with `source IN ("purchase_order", "purchase_order_reversal")`.
- Frontend `Creditors` component (App_js_fixed.js:6128) unchanged.

## 5. Cross-module consistency

✓ No issues found. Unchanged from 07-27.
- Journal coverage complete across invoices, expenses, payroll, POs, inventory, fixed assets.
- Debtors/Creditors Control reconciliation (Rules 6-7) remains reversal- and import-aware.
- Import-awareness (2026-07-11 fixes) intact: `csv_import.py` auto-backfills the journal after imports; Rules 6/7 exclude `source == "import"` lines. File unchanged since 2026-07-11.
- Migration hygiene: no new `database.py` migrations since 07-26 (already verified inside the migrations list literal in the 07-27 report); nothing further to check this run.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (declared in AFS meta). Statements: income statement, statement of financial position, changes in equity, cash flow (indirect), notes 2-9.

**Standards status (re-confirmed via fresh web search this run):**
- IFRS 18 *Presentation and Disclosure in Financial Statements* — still effective for annual periods beginning on or after 1 Jan 2027; applies to full-IFRS preparers, not IFRS for SMEs. No ZuZan change required yet.
- IFRS for SMEs **third edition** (issued Feb 2025, effective 1 Jan 2027, early adoption permitted) — aligns SME revenue recognition with IFRS 15 while retaining simplifications. No new IASB update materially affecting ZuZan since 07-27.
- The IASB's proposed extension of the consolidation exception for eligible SMEs remains an open Exposure Draft (comment period to 9 September 2026); if finalized it would apply from 1 Jan 2027 alongside the third edition — still not yet applicable, unchanged from last run.

**Section 5b — deferred tax: already implemented, re-verified this run (financial_statements.py, grepped directly):**
- `_deferred_tax_balance` (:131-172, per the earlier grep hit at :131): tax base = cost − straight-line SARS wear-and-tear apportioned from purchase date, floored at 0; temporary difference × `_CIT_RATE` (single-sourced from `fixed_assets.SA_CIT_RATE`, :78-84).
- Note 9: `deferred_tax_expense = dt_closing − dt_opening` (:266-268); `total_tax = current_tax + deferred_tax` (:601, :606).
- Balance sheet presents closing DTL/DTA (:609-610, :681 movement) with matching retained-earnings adjustment — Assets = Equity + Liabilities preserved by construction. No regressions.

✓ No issues found.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date.

- Fresh web search this run confirms no rate changes since 07-27: 2026/2027 brackets/rebates unchanged — top bracket threshold R1,878,600 at 45% matches `payroll.py:131-145` exactly (top bracket "min": 1878601, base 666339).
- SARS Filing Season 2026 updates found this run (eFiling UX refresh, expanded auto-assessment windows, prepopulated investment income) are individual-taxpayer filing/process changes with no bearing on ZuZan's payroll/company tax calculations.
- The s20A ring-fencing-of-losses change (39% marginal-rate trigger instead of 45%, for years of assessment from 1 March 2026) remains an individual/personal-tax provision with no equivalent in ZuZan's company/payroll logic — no code impact, noted for completeness only (unchanged from 07-27).
- **VAT** — standard rate confirmed still **15%**; code constants (payroll.py:1608, :2691) correct.
- **PAYE brackets / rebates / UIF / SDL** (payroll.py:131-145) — unchanged, current for 2026/2027. UIF ceiling R17,712/month, 1%/1% employee/employer, SDL 1% — consistent with current SARS rules. ✓
- **Corporate income tax** 27%, single-sourced via `SA_CIT_RATE` — unchanged. ✓
- Rates unchanged and current tax year present — no edits made (report-only per task rules).

**Sources consulted:** [SARS tax season 2026: Here's what's changed](https://www.msn.com/en-za/news/other/sars-tax-season-2026-here-s-what-s-changed/ar-AA26eAey) · [Changes for Filing Season 2026 — SARS](https://www.sars.gov.za/latest-news/changes-for-filing-season-2026/) · [SARS Tax Calendar 2026 & Deadline Tracker — TaxTim](https://www.taxtim.com/za/tax-deadlines) · [SARS 2026 Tax Filing Dates & Deadlines — Accounter](https://accounter.co.za/tools/tax-calendar) · [SARS Tax Changes for 2026 — Joburg ETC](https://www.joburgetc.com/business/sars-tax-changes-2026-south-africa/) · [SARS Auto-Assessment Updates, Tax Season 2026 — CTF](https://ctfsa.com/sars-auto-assessment-updates-tax-season-2026/) · [SARS Opens 2026 Tax Filing Season — InboundSA](https://inboundsa.com/sars-2026-tax-filing-season-key-dates-changes/) · [IASB proposes extending consolidation exception for eligible SMEs — IFRS.org](https://www.ifrs.org/news-and-events/news/2026/05/iasb-proposes-extending-consolidation-exception-eligible-smes/) · [Third edition of the IFRS for SMEs Accounting Standard — ACCA](https://www.accaglobal.com/learning-and-events/corporate-reporting/third-edition-ifrs-for-smes.html) · [IFRS for SMEs Training Modules for the third edition — Deloitte DART](https://dart.deloitte.com/iGAAP/home/financial-reporting/financial-reporting-literature/ifrs-for-smes-accounting-standard/ifrs-for-smes-effective-from-1/ifrs-for-smes-training-modules-for)

## 8. Action items

None open.

**Standing reminders (not defects):** (a) replace the provisional 2027/2028 TAX_YEARS entry after Budget Feb 2027 and restart the backend; (b) early-2027 runs execute the IFRS for SMEs 3rd-edition transition-plan checklist (Section 23 revenue and Section 19 business-combinations changes are the most relevant to ZuZan; watch the May-2026 Consolidation Exception exposure draft, comment period closes 9 September 2026); (c) the AFS PayFast payment / ad-hoc tokenization feature and now the new `/reports/ai-insights` (AI management-pack) feature both remain outside this audit's Reports/Debtors/Creditors/AFS-content/tax scope — flag for inclusion if a future audit's file list is expanded; (d) NBCPSS private security payroll mode (grades, allowances, BC levy, PSIRA fee) predates this audit's baseline and doesn't affect the audited totals, but isn't yet part of this checklist's explicit scope — consider adding it to the payroll section of future audits given it introduces new statutory-adjacent deductions.
