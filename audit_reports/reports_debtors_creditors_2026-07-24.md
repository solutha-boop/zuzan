# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 24 July 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-07-23 (full PASS, no open action items).

**Change detection since last run:** All audit-scope files are byte-unchanged since the 07-23 PASS (confirmed via mtimes): App_js_fixed.js (07-18), payroll.py (07-19), companies.py (07-18), suppliers.py (06-15), customers.py (06-12), purchase_orders.py (07-13), journal.py (07-15), database.py (07-19), main.py (07-22), financial_statements.py (07-22), csv_import.py (07-11), fixed_assets.py (07-19). No code changes to verify this run — re-confirmed prior findings by direct grep of the same file:line references, and refreshed the external (SARS/IFRS) research since those facts can change independent of the codebase.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ✅ PASS — logic unchanged, re-verified |
| Debtors (AR) | ✅ PASS — aged from due_date, paid excluded, ZAR amounts |
| Creditors (AP) | ✅ PASS — reversal-aware, bank details decrypted |
| Cross-module consistency | ✅ PASS — full journal coverage, import-awareness intact |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) verified again, no regressions |
| Tax rates (SARS) | ✅ PASS — 2026/2027 tables current, no Budget/SARS changes since 07-23 |

**Overall: PASS.** No open action items.

---

## 2. Reports

✓ No issues found.

- `/v1/summary` (main.py:443-488) unchanged: `total_revenue` sums only paid invoices via `_to_zar()` plus `_bank_import_income`; expenses ex-VAT; PO COGS via `_po_delivered_net` over received/partial/paid POs, no double-count; `outstanding` filters `status IN (sent, overdue)` with `_to_zar()`.
- Dashboard (payroll.py:1237-1245): `total_revenue = sum(_to_zar(i) for i in paid_invoices) + _bank_import_income(...)` (:1237, :1239); `total_outstanding = sum(_to_zar(i) for i in outstanding_invoices)` (:1245).
- `_to_zar()` re-grepped: used consistently across dashboard, debtors-aging, cash-flow, management accounts, and provisional-tax revenue calcs (payroll.py:1397, :1630, :1642, :1725, :1854, :1917, :2078, :2153, :2170, :2251, :2364) — no raw-currency leakage found anywhere revenue/outstanding is summed.
- Payroll costs and PO COGS inclusion in expenses unchanged from prior verification.

## 3. Debtors

✓ No issues found.

- Frontend `Debtors` renders backend `/reports/debtors-aging` (App_js_fixed.js:5930, :5936).
- Backend filters `status IN (sent, overdue)` — paid and draft excluded (payroll.py:2350-2354).
- ZAR equivalents via `_to_zar()` per invoice (payroll.py:2364-2365).
- Aging strictly from `due_date`; buckets not_due / current(0-30) / 31-60 / 61-90 / 90+ (payroll.py:2357-2400).

## 4. Creditors

✓ No issues found.

- Frontend `Creditors` renders backend `/reports/creditors-aging` (App_js_fixed.js:6057, :6063).
- Pulls received/partial POs plus unpaid on-credit expenses; fully paid POs and paid credit expenses excluded (payroll.py:2419-2422).
- Supplier bank details decrypted with `decrypt_field` before display (payroll.py:2416, :2483-2485).
- **Reversal-awareness (2026-07-13 fixes) re-confirmed:** `SUM(credit − debit)` netting with source `IN ("purchase_order", "purchase_order_reversal")` at payroll.py:1770-1778 (Rule 7) and :2433-2440 (creditors-aging per-PO); same pattern in financial_statements.py Note 7 payables, unchanged.

## 5. Cross-module consistency

✓ No issues found.

- Journal coverage complete (journal.py, unchanged, re-grepped): `post_invoice_raised`, `post_invoice_paid`, `post_invoice_cogs`, `post_expense`, `post_bank_income`, `post_payroll`, `post_expense_paid`, `post_po_received`, `post_po_paid`, plus asset acquisition/depreciation/disposal — all source types covered.
- Debtors Control (1100) / Creditors Control (2000) reconciliation compares journal balances to raw invoice/PO totals, reversal- and import-aware (payroll.py Rules 6-7, :1720-1815).
- **Import-awareness (2026-07-11 fixes)** intact — csv_import.py unchanged: 2 matches for `source=="import"` exclusion logic on Rules 6/7 (payroll.py), consistent with prior counts; auto-backfill on invoice/expense import, balanced-group requirement, and non-ZAR invoice imports requiring a positive exchange rate all unchanged.
- Migration hygiene: all `ALTER TABLE` statements remain inside the migrations list literal — no dead-code migrations after the for loop.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (declared in AFS meta, rendered in frontend). Statements: income statement, statement of financial position, changes in equity, cash flow (indirect), notes 2-9.

**Standards status (re-confirmed via fresh web search, unchanged since prior audit):**
- IFRS 18 *Presentation and Disclosure in Financial Statements* — effective annual periods beginning on or after 1 Jan 2027; applies to full-IFRS preparers, not IFRS for SMEs. No ZuZan change required yet.
- IFRS for SMEs **third edition** — issued 27 Feb 2025, effective 1 Jan 2027 (early application permitted). Key third-edition changes confirmed this run: Section 23 (Revenue) realigned with IFRS 15, Section 19 (Business Combinations) realigned with IFRS 3. ZuZan's SA FY (1 March–28/29 Feb) is first caught by the FY beginning 1 March 2027; transition plan remains on file.

**Section 5b — deferred tax: already implemented, verified fresh this run (financial_statements.py, re-grepped):**
- `_deferred_tax_balance` (:131-173): tax base = cost − straight-line SARS wear-and-tear apportioned monthly, floored at 0; temporary difference = carrying value − tax base, × `_CIT_RATE`. No assets/no rates ⇒ exactly 0.0.
- Note 9 reports period movement `dt_closing − dt_opening` (:266-268, :606-610), `total_tax = current + deferred` (:601).
- Balance sheet presents closing DTL (code 2600, :315-321) or DTA (code 1900, :322-328) as a computed line with matching retained-earnings adjustment (:349) — nothing posted to the journal; Assets = Equity + Liabilities preserved.
- `wear_and_tear_rate` column and IN47 category mapping (:87-110) unchanged; frontend renders the Note 9 deferred-tax row when non-zero.

**CIT rate single-sourcing (fixed 07-22, re-confirmed):** `_CIT_RATE` imported from `fixed_assets.SA_CIT_RATE` with a `0.27` fallback if unavailable (financial_statements.py:78-84); used consistently at :172, :260, :604, :641 — no stray literal `0.27`/`27.0` remaining.

**Finance costs (2026-07-13 fix) re-confirmed:** `profit_before_tax = ebit − finance_costs`; tax and net profit derive from `profit_before_tax`, not EBIT (financial_statements.py:257-261).

✓ No issues found.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date; `_current_tax_year()` derives it from today's date with newest-table fallback (payroll.py:171-182, :185-187).

- Fresh web search this run confirms: PIT brackets/rebates for 2026/27 adjusted 3.4% for inflation (Budget 2026, 25 Feb); corporate tax rate remains 27%; CGT annual exclusion raised R40k→R50k and primary-residence exclusion R2m→R3m (not modeled in ZuZan — out of current scope, no code claims to handle CGT); VAT registration threshold raised R1m→R2.3m effective 1 Apr 2026 (informational, no code gate — consistent with prior findings); proposed R20bn tax increases were withdrawn. No change to PAYE brackets, rebates, UIF, SDL, CIT, or standard VAT rate.
- **PAYE brackets 2026/2027** — TAX_YEARS entry present and unchanged (payroll.py:131-145). ✓
- **Rebates** — primary R17,820 (:141), secondary R9,765 (:142), tertiary R3,249 (:143) — match 2026/2027 Budget figures. ✓
- **UIF** 1% employee + 1% employer, ceiling R17,712/month (:144, :187-188). **SDL** 1% (:189). ✓
- **Corporate income tax** 27% unchanged — dashboard (payroll.py:1289), management accounts (:2144), provisional tax (:2241), AFS via single-sourced `SA_CIT_RATE`. ✓
- **VAT** 15% unchanged (payroll.py:1608, :2597 — both constants match). Registration thresholds (compulsory R2.3m, voluntary R120k, effective 1 Apr 2026) remain informational only; no code gate exists. ✓
- **s11F cap and medical tax credits** (R376/R254, effective 1 March 2026) current for 2026/2027 (:195-201). ✓
- **Provisional 2027/2028 entry** present, flagged `"provisional": True` (:151-166) — pending Budget Feb 2027. No change needed yet.
- Rates unchanged and current tax year present — no edits made (report-only per task rules; section 5b needed no new edits this run, only verification).

**Sources consulted:** [Werksmans — Budget Speech 2026/2027 Tax Overview](https://werksmans.com/budget-speech-2026-2027-tax-overview/) · [SARS — Changes for Filing Season 2026](https://www.sars.gov.za/latest-news/changes-for-filing-season-2026/) · [TaxTim — Budget 2026: a small win for taxpayers](https://www.taxtim.com/za/blog/budget-2026) · [Moonstone — Income tax brackets, medical tax credits adjusted for inflation](https://www.moonstone.co.za/income-tax-brackets-medical-tax-credits-adjusted-for-inflation/) · [Accounter — SARS Tax Tables 2026/2027](https://accounter.co.za/news/sars-tax-tables-2026-2027) · [IFRS Foundation — March 2026 IFRS for SMEs Accounting Standard Update](https://www.ifrs.org/supporting-implementation/2015-ifrs-for-smes-supporting-materials/sme-updates/2026/march-2026-ifrs-for-smes-accounting-standard-update/) · [EY — IASB issues third edition of IFRS for SMEs accounting standard](https://www.ey.com/en_gl/technical/ifrs-technical-resources/iasb-issues-third-edition-of-ifrs-for-smes-accounting-standard)

## 8. Action items

None open.

**Standing reminders (not defects):** (a) replace the provisional 2027/2028 TAX_YEARS entry after Budget Feb 2027 and restart the backend; (b) early-2027 runs execute the IFRS for SMEs 3rd-edition transition-plan checklist (Section 23 revenue and Section 19 business-combinations changes are the most relevant to ZuZan); (c) VAT registration thresholds changed 1 Apr 2026 (compulsory R2.3m, voluntary R120k) — informational only, no code gate exists; (d) CGT annual exclusion (R50k) and primary-residence exclusion (R3m) changes from Budget 2026 are not modeled in ZuZan and are out of current scope — flag only if CGT calculation is ever added to the app.
