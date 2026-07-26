# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 26 July 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-07-25 (full PASS, no open action items).

**Change detection since last run:** Zero audit-scope files changed since the 07-25 audit. Confirmed via mtime for all in-scope files: `App_js_fixed.js` (Jul 18), `payroll.py` (Jul 19), `companies.py` (Jul 18), `suppliers.py` (Jun 15), `customers.py` (Jun 12), `purchase_orders.py` (Jul 13), `journal.py` (Jul 15), `database.py` (Jul 24 22:00 — same as reported 07-25, no further edits), `main.py` (Jul 24 22:07 — same as reported 07-25), `financial_statements.py` (Jul 22), `csv_import.py` (Jul 11), `fixed_assets.py` (Jul 19). `git status` shows uncommitted working-tree changes to `auth.py` and `test_reg.py` (both out of audit scope) plus doc/config files (`.gitignore`, `README.md`, `main_py_fixed_backup.py`) — none touch Reports/Debtors/Creditors/AFS/tax logic.

Re-verified the substantive logic directly via targeted greps (not relying on mtime alone) for: dashboard revenue/outstanding (`payroll.py:1237-1245`), reversal-aware AP netting (`payroll.py:1770-1785`, `:2433-2440`), deferred-tax module and CIT single-sourcing (`financial_statements.py:78-268`, `:601-610`), and the `wear_and_tear_rate` migration placement inside the migrations list literal (`database.py:1360`) — all identical to the 07-25 findings. Refreshed external (SARS/IFRS/VAT) research since those facts can change independent of the codebase.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ✅ PASS — logic unchanged, re-verified |
| Debtors (AR) | ✅ PASS — aged from due_date, paid excluded, ZAR amounts |
| Creditors (AP) | ✅ PASS — reversal-aware, bank details decrypted |
| Cross-module consistency | ✅ PASS — full journal coverage, import-awareness intact |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) verified again, no regressions |
| Tax rates (SARS) | ✅ PASS — 2026/2027 tables current, no Budget/SARS rate changes since 07-25 |

**Overall: PASS.** No open action items. No audit-scope files changed since the last run.

---

## 2. Reports

✓ No issues found. Unchanged from 07-25 — re-confirmed via grep:
- `/v1/summary` (main.py:446-487): revenue from paid invoices + `_bank_import_income`, outstanding via `_to_zar()`, expenses/payroll excluded from revenue.
- Dashboard (payroll.py:1237-1245): `total_revenue = sum(_to_zar(i) for i in paid_invoices)` then `+= _bank_import_income(db, cid)`; `total_outstanding = sum(_to_zar(i) for i in outstanding_invoices)`.
- `_to_zar()` / `_bank_import_income()` usage consistent across management-accounts revenue trend loop (payroll.py:1405, :1919, :2080, :2174, :2253) and dashboard.

## 3. Debtors

✓ No issues found. Unchanged from 07-25.
- `/reports/debtors-aging` filters `status IN (sent, overdue)`; ZAR via `_to_zar(inv)`; aging strictly from `due_date` (no issue_date fallback); buckets not_due / current / 31-60 / 61-90 / 90+.

## 4. Creditors

✓ No issues found. Unchanged from 07-25.
- `/reports/creditors-aging` pulls received/partial POs, excludes fully paid; supplier bank details decrypted via `decrypt_field`.
- **Reversal-awareness (2026-07-13 fixes) re-confirmed:** both the creditors-aging endpoint (payroll.py:2433-2440) and Rule 7 (payroll.py:1770-1785) net `SUM(credit − debit)` with `source IN ("purchase_order", "purchase_order_reversal")`.

## 5. Cross-module consistency

✓ No issues found. Unchanged from 07-25.
- Journal coverage complete (13 posting functions in journal.py) spanning invoices, expenses, payroll, POs, inventory, fixed assets.
- Debtors/Creditors Control reconciliation (Rules 6-7) remains reversal- and import-aware.
- Import-awareness (2026-07-11 fixes) intact: `csv_import.py` auto-backfills the journal after imports; Rules 6/7 exclude `source == "import"` lines.
- `database.py` migration hygiene re-checked: `wear_and_tear_rate` ALTER TABLE (line 1360) remains inside the migrations list literal, not after the for-loop.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (declared in AFS meta). Statements: income statement, statement of financial position, changes in equity, cash flow (indirect), notes 2-9.

**Standards status (re-confirmed via fresh web search this run):**
- IFRS 18 *Presentation and Disclosure in Financial Statements* — still effective for annual periods beginning on or after 1 Jan 2027; applies to full-IFRS preparers, not IFRS for SMEs. No ZuZan change required yet.
- IFRS for SMEs **third edition** (issued 27 Feb 2025, effective 1 Jan 2027, early adoption permitted) — no new IASB update since 07-25; IASB implementation support materials for Section 23 (revenue, aligned to IFRS 15 five-step model) and the merged financial-instruments section continue to roll out through 2026. ZuZan's transition plan (first caught at FY beginning 1 March 2027) remains on file, unchanged.

**Section 5b — deferred tax: already implemented, re-verified this run (financial_statements.py, grepped in full):**
- `_deferred_tax_balance` (:131-172): tax base = cost − straight-line SARS wear-and-tear apportioned from purchase date, floored at 0; temporary difference × `_CIT_RATE`.
- Note 9: `deferred_tax_expense = dt_closing − dt_opening` (:266-268, :606-610); `total_tax = current_tax + deferred_tax` (:601).
- Balance sheet presents closing DTL/DTA with matching retained-earnings adjustment — Assets = Equity + Liabilities preserved by construction. No regressions.
- CIT single-sourcing (`_CIT_RATE` from `fixed_assets.SA_CIT_RATE`, :82-84) and finance-costs-below-EBIT treatment (`profit_before_tax = ebit − finance_costs`, :259-261) both re-confirmed unchanged.

✓ No issues found.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date.

- Fresh web search this run confirms: 2026 Filing Season for individuals/trusts opened 1 July 2026 (auto-assessments issued 1–12 July); operational/filing-season news only, no rate changes.
- One newly-surfaced item, **out of ZuZan's scope**: for years of assessment from 1 March 2026, s20A ring-fencing of assessed losses now triggers at the 39% marginal rate instead of the top 45% rate. This is an individual (sole-prop/personal) assessed-loss ring-fencing rule with no equivalent in ZuZan's company/payroll tax logic — no code change needed, noted for completeness only.
- **VAT** — re-confirmed standard rate remains **15%**; the 2025-proposed increases to 15.5%/16% stayed reversed; Budget 2026 raised the *compulsory registration threshold* to R2.3m (informational only, no code gate in ZuZan) rather than the rate. Code constants (payroll.py:1608, :2597) remain correct at 15%.
- **PAYE brackets / rebates / UIF / SDL** (payroll.py:131-145, :187-189) — unchanged, previously confirmed to include the 3.4% inflation adjustment for 2026/2027. ✓
- **Corporate income tax** 27%, single-sourced via `SA_CIT_RATE` — unchanged. ✓
- **s11F cap / medical tax credits** (R376/R254, effective 1 March 2026) — current. ✓
- Rates unchanged and current tax year present — no edits made (report-only per task rules).

**Sources consulted:** [SARS — Changes for Filing Season 2026](https://www.sars.gov.za/latest-news/changes-for-filing-season-2026/) · [Accounter — SARS Tax Tables 2026/2027](https://accounter.co.za/news/sars-tax-tables-2026-2027) · [Moonstone — Income tax brackets, medical tax credits adjusted for inflation](https://www.moonstone.co.za/income-tax-brackets-medical-tax-credits-adjusted-for-inflation/) · [MSN — SARS tax season 2026: what's changed](https://www.msn.com/en-za/news/other/sars-tax-season-2026-here-s-what-s-changed/ar-AA26eAey) · [IFRS Foundation — March 2026 IFRS for SMEs Accounting Standard Update](https://www.ifrs.org/supporting-implementation/2015-ifrs-for-smes-supporting-materials/sme-updates/2026/march-2026-ifrs-for-smes-accounting-standard-update/) · [IFRS Foundation — IFRS for SMEs third edition PDF](https://www.ifrs.org/content/dam/ifrs/publications/ifrs-for-smes/english/2025/ifrs-for-smes.pdf?bypass=on) · [SAIT — VAT in 2026: Navigating Stability](https://thesait.org.za/vat-in-2026-navigating-stability-and-the-legacy-of-the-2025-reversals/) · [Standard Bank — Budget 2026 VAT threshold increase](https://www.standardbank.co.za/southafrica/news-and-media/newsroom/budget-2026-delivers-sme-relief-as-vat-threshold-increases-to-r2.3-million) · [Mondaq — Africa Tax In Brief, 14 July 2026](https://www.mondaq.com/southafrica/sales-taxes-vat-gst/1818540/africa-tax-in-brief-14-july-2026)

## 8. Action items

None open.

**Standing reminders (not defects):** (a) replace the provisional 2027/2028 TAX_YEARS entry after Budget Feb 2027 and restart the backend; (b) early-2027 runs execute the IFRS for SMEs 3rd-edition transition-plan checklist (Section 23 revenue and Section 19 business-combinations changes are the most relevant to ZuZan); (c) VAT compulsory registration threshold (R2.3m, effective 1 Apr 2026) remains informational only, no code gate exists; (d) CGT annual exclusion/primary-residence exclusion changes and the new s20A ring-fencing 39%-marginal-rate trigger are individual/personal-tax provisions not modeled in ZuZan — flag only if personal/individual tax calculations are ever added to the app.
