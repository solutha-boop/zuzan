# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 25 July 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-07-24 (full PASS, no open action items).

**Change detection since last run:** Two files changed since the 07-24 audit — `database.py` (07-24 22:00) and `main.py` (07-24 22:07) — both post-dating the prior report. Diffed against the exact commit audited last time (`1c40b1c`, state as at 07-24 16:35) through current HEAD (`bb969b8`):
- `database.py`: added `overlaps="..."` kwargs to the `Company.stitch_bank_accounts` / `Company.stitch_transactions` / `StitchBankAccount.company` / `StitchTransaction.company` SQLAlchemy relationships. This silences a SQLAlchemy overlapping-relationship warning; no schema, migration, or `FixedAsset` change. Out of audit scope.
- `main.py`: added an admin-only `POST /admin/api/clients/{company_id}/extend-trial` endpoint plus an "Extend Trial" button/logout button in the admin dashboard HTML. Unrelated to Reports/Debtors/Creditors/`/v1/summary`/AFS/tax logic — `/v1/summary` block (main.py:443-488) is untouched.

All other audit-scope files are byte-identical to the 07-24 PASS (confirmed via mtime): `App_js_fixed.js` (07-18), `payroll.py` (07-19), `companies.py` (07-18), `suppliers.py` (06-15), `customers.py` (06-12), `purchase_orders.py` (07-13), `journal.py` (07-15), `financial_statements.py` (07-22), `csv_import.py` (07-11), `fixed_assets.py` (07-19). Re-verified the substantive logic directly (not just via mtime) by re-grepping/re-reading the actual line ranges for dashboard revenue, debtors-aging, creditors-aging, Rule 7 reversal netting, journal source coverage, and the deferred-tax module — all match prior findings exactly. Refreshed external (SARS/IFRS) research since those facts can change independent of the codebase.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ✅ PASS — logic unchanged, re-verified |
| Debtors (AR) | ✅ PASS — aged from due_date, paid excluded, ZAR amounts |
| Creditors (AP) | ✅ PASS — reversal-aware, bank details decrypted |
| Cross-module consistency | ✅ PASS — full journal coverage, import-awareness intact |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) verified again, no regressions |
| Tax rates (SARS) | ✅ PASS — 2026/2027 tables current, no Budget/SARS changes since 07-24 |

**Overall: PASS.** No open action items. Two unrelated files changed since the last run (SQLAlchemy relationship warning fix; admin trial-extension feature) — neither touches audited functionality.

---

## 2. Reports

✓ No issues found.

- `/v1/summary` (main.py:446-487) unchanged: `total_revenue = sum(_to_zar(i) for i in paid_invs) + _bank_import_income(...)` (:450-451); `outstanding = sum(_to_zar(i) for i in out_invs)` (:480); `net_profit = total_revenue - total_expenses - total_payroll` (:487).
- Dashboard (payroll.py:1237-1245): `total_revenue = sum(_to_zar(i) for i in paid_invoices)` then `+= _bank_import_income(db, cid)`; `total_outstanding = sum(_to_zar(i) for i in outstanding_invoices)` filtered to `status IN (sent, overdue)`.
- Expenses queried separately (ex-VAT), no overlap with revenue; payroll costs and PO COGS inclusion in expenses re-confirmed unchanged from prior audits.
- `_to_zar()` usage re-spot-checked across dashboard, debtors-aging and creditors-aging call sites — no raw-currency leakage.

## 3. Debtors

✓ No issues found.

- Frontend `Debtors` renders backend `/reports/debtors-aging` (App_js_fixed.js, unchanged).
- Backend filters `status IN (sent, overdue)` — paid and draft excluded (payroll.py:2350-2354, re-read this run).
- ZAR equivalents via `_to_zar(inv)` per invoice (payroll.py:2364).
- Aging strictly from `due_date` only (comment explicitly notes issue_date/created_at fallback was removed by a prior audit fix); invoices with no due date go to `not_due` rather than falsely inflating overdue totals. Buckets: not_due / current (0-30) / 31-60 / 61-90 / 90+ (payroll.py:2357-2400).

## 4. Creditors

✓ No issues found.

- Frontend `Creditors` renders backend `/reports/creditors-aging` (App_js_fixed.js, unchanged).
- Pulls received/partial POs; fully paid POs excluded (payroll.py:2419-2422).
- Supplier bank details decrypted via `decrypt_field` before display (payroll.py:2416, :2483-2485, re-read).
- **Reversal-awareness (2026-07-13 fixes) re-confirmed:** per-PO AP balance nets `SUM(credit − debit)` with `source IN ("purchase_order", "purchase_order_reversal")` — both in the creditors-aging endpoint (payroll.py:2433-2440) and in the Rule 7 reconciliation check (payroll.py:1770-1785). Comments in both locations explicitly document the 2026-07-13 fix rationale.

## 5. Cross-module consistency

✓ No issues found.

- Journal coverage complete (journal.py, re-grepped this run): `post_invoice_raised`, `post_invoice_paid`, `post_invoice_cogs`, `post_expense`, `post_bank_income`, `post_payroll`, `post_expense_paid`, `post_po_received`, `post_po_paid`, `post_stock_adjustment`, `post_asset_acquisition`, `post_depreciation`, `post_asset_disposal` — 13 posting functions, full coverage of every upstream module (invoices, expenses, payroll, POs, inventory, fixed assets).
- Debtors Control (1100) / Creditors Control (2000) reconciliation (Rules 6-7, payroll.py:1720-1830) compares journal balances to raw invoice/PO totals, both reversal- and import-aware.
- **Import-awareness (2026-07-11 fixes)** intact — `csv_import.py:_auto_backfill` runs `journal_engine.backfill_company()` automatically after both invoice/expense imports (csv_import.py:501-502, :563-564); Rules 6/7 exclude `source == "import"` lines when computing the raw-total comparison base (payroll.py:1736, :1812).
- Migration hygiene re-checked in `database.py`: this run's only change to that file was the `overlaps=` kwarg fix on Stitch bank-sync relationships — no migration-list edits, no dead code after the migrations for-loop.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (declared in AFS meta, rendered in frontend). Statements: income statement, statement of financial position, changes in equity, cash flow (indirect), notes 2-9.

**Standards status (re-confirmed via fresh web search):**
- IFRS 18 *Presentation and Disclosure in Financial Statements* — effective annual periods beginning on or after 1 Jan 2027; applies to full-IFRS preparers, not IFRS for SMEs. No ZuZan change required yet.
- IFRS for SMEs **third edition** — issued 27 Feb 2025, effective 1 Jan 2027, early application permitted (confirmed again via ifrs.org this run — no new update since 07-24). ZuZan's SA FY (1 March–28/29 Feb) is first caught by the FY beginning 1 March 2027; transition plan remains on file.

**Section 5b — deferred tax: already implemented, re-verified this run (financial_statements.py, re-read in full):**
- `_deferred_tax_balance` (:131-173): tax base = cost − straight-line SARS wear-and-tear apportioned monthly from purchase date, floored at 0; temporary difference = carrying value − tax base, × `_CIT_RATE`; unmappable-rate assets use carrying value as tax base (temporary difference exactly 0). No assets/no rate data ⇒ balance exactly 0.0.
- Note 9 reports period movement `deferred_tax_expense = dt_closing − dt_opening` (:266-268, :601-610); `total_tax = current_tax + deferred_tax` (:601); effective-rate calc unchanged.
- Balance sheet presents closing DTL (code 2600, non-current liability, :315-321) when `dt_closing > 0.005` or DTA (code 1900, non-current asset, :322-328) when `dt_closing < -0.005`, each with a matching retained-earnings adjustment — nothing posted to the journal, Assets = Equity + Liabilities preserved by construction.
- `wear_and_tear_rate` column, IN47 category mapping (`_CATEGORY_WT_RATES`, :90-103) and `SARS_WEAR_TEAR` lookup unchanged; frontend renders the Note 9 deferred-tax row when non-zero.

**CIT rate single-sourcing (fixed 07-22) re-confirmed:** `_CIT_RATE` imported from `fixed_assets.SA_CIT_RATE` with a `0.27` fallback (financial_statements.py:81-84); used consistently at :172 (deferred tax), :259-260 (tax_expense), :604 (Note 9 rate), :641 (effective rate) — no stray literal `0.27`/`27.0` elsewhere.

**Finance costs (2026-07-13 fix) re-confirmed:** `profit_before_tax = ebit − finance_costs` (:257); `tax_expense = max(0, profit_before_tax × _CIT_RATE)` (:258); `net_profit = profit_before_tax − tax_expense` (:259) — tax and net profit derive from profit-before-tax, not EBIT.

✓ No issues found.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date; `_current_tax_year()` derives it from today's date with newest-table fallback (payroll.py:171-187, unchanged).

- Fresh web search this run: SARS 2026 Filing Season is underway (auto-assessments ran to 12 July, manual filing opened 13 July, non-provisional deadline 23 Oct 2026, provisional/trusts 22 Jan 2027) — operational/filing-season news, no rate changes. SARS also published a draft Crypto Assets taxation guide (CARF reporting from 1 March 2026) — not applicable to ZuZan's scope (no crypto handling in the app).
- VAT: re-confirmed standard rate remains **15%** — the 2025-proposed 0.5%+0.5% VAT hikes (to 15.5% then 16%) were reversed by legislative/court action in April 2025 and Budget 2026 did not reinstate them. No VAT rate change effective or announced for the remainder of 2026. Code constants (payroll.py:1608, :2597) remain correct at 15%.
- **PAYE brackets 2026/2027** — TAX_YEARS entry present and unchanged (payroll.py:131-145). ✓
- **Rebates** — primary R17,820, secondary R9,765, tertiary R3,249 (:141-143) — match 2026/2027 Budget figures, unchanged. ✓
- **UIF** 1% employee + 1% employer, ceiling R17,712/month (:144, :187-188). **SDL** 1% (:189). ✓
- **Corporate income tax** 27% unchanged — dashboard (payroll.py:1289), management accounts (:2144), provisional tax (:2241), AFS via single-sourced `SA_CIT_RATE`. ✓
- **VAT registration threshold** — compulsory threshold rose R1m→R2.3m effective 1 Apr 2026 (re-confirmed this run); remains informational only in ZuZan, no code gate exists (consistent with prior findings — the app doesn't auto-register/de-register clients for VAT). ✓
- **s11F cap and medical tax credits** (R376/R254, effective 1 March 2026) current for 2026/2027 (:195-201). ✓
- **Provisional 2027/2028 entry** present, flagged `"provisional": True` (:151-166) — pending Budget Feb 2027. No change needed yet.
- Rates unchanged and current tax year present — no edits made (report-only per task rules).

**Sources consulted:** [IOL — SARS 2026 tax season](https://iol.co.za/business/2026-07-05-everything-you-need-to-know-about-sars-2026-tax-season-as-billions-flow-out-in-first-days/) · [SARS — Changes for Filing Season 2026](https://www.sars.gov.za/latest-news/changes-for-filing-season-2026/) · [SAnews — SARS announces 2026 filing season dates](https://www.sanews.gov.za/south-africa/sars-announces-2026-filing-season-dates) · [SAnews — Nearly 2 million auto-assessed](https://www.sanews.gov.za/south-africa/nearly-2-million-auto-assessed-sars-introduces-enhancements) · [IFRS Foundation — March 2026 IFRS for SMEs Accounting Standard Update](https://www.ifrs.org/supporting-implementation/2015-ifrs-for-smes-supporting-materials/sme-updates/2026/march-2026-ifrs-for-smes-accounting-standard-update/) · [IFRS Foundation — IFRS for SMEs third edition](https://www.ifrs.org/issued-standards/ifrs-for-smes/) · [Polity — Budget 2026: VAT wasn't raised](https://www.polity.org.za/article/budget-2026-vat-wasnt-raised-it-was-reengineered-for-a-modern-south-africa-2026-02-26) · [vatcalc.com — South Africa 2026 Budget ducks VAT rise](https://www.vatcalc.com/south-africa/south-africa-vat-rise/) · [thesait.org.za — VAT in 2026: Navigating Stability](https://thesait.org.za/vat-in-2026-navigating-stability-and-the-legacy-of-the-2025-reversals/)

## 8. Action items

None open.

**Standing reminders (not defects):** (a) replace the provisional 2027/2028 TAX_YEARS entry after Budget Feb 2027 and restart the backend; (b) early-2027 runs execute the IFRS for SMEs 3rd-edition transition-plan checklist (Section 23 revenue and Section 19 business-combinations changes are the most relevant to ZuZan); (c) VAT compulsory registration threshold (R2.3m, effective 1 Apr 2026) remains informational only, no code gate exists; (d) CGT annual exclusion (R50k) and primary-residence exclusion (R3m) changes from Budget 2026 are not modeled in ZuZan and are out of current scope — flag only if CGT calculation is ever added to the app.
