# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 6 November 2026 (scheduled run)
**Prior report:** 2026-11-04 (incl. its "Fixes applied 2026-11-05" section)

**Scope / method:** static review (grep/read + `ast` syntax check of payroll, main, csv_import, journal, financial_statements, database — all parse OK). No live DB / pytest. **No code edited** (5b already implemented). Files changed since last report: only the 2026-11-05 fixes (csv_import.py, payroll.py, main.py, App_js_fixed.js).

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | **PASS** — `_to_zar` revenue/outstanding logic intact; GL-import income/expenses now in dashboard (payroll.py:2498, 2527), management accounts (3838, 3881, 3943, 3963) and `/v1/summary` (main.py:525, 545) with cutover guard (payroll.py:159) |
| Debtors (AR) | **PASS** — unchanged |
| Creditors (AP) | **PASS** — reversal-aware sources intact; `decrypt_field` on supplier bank details |
| Cross-module | **PASS (Low residual)** — 11-05 Critical/High fixes verified in code; one narrow residual on reclassify |
| IFRS (AFS) | **PASS** — no change; deferred tax verified |
| Tax (SARS) | **PASS** — 2026/2027 present, no rate changes |

**Overall: 0 Critical, 0 High, 1 Medium (residual), Low items carried.**

## 2. Reports
✓ No issues found. `VAT_RATE=0.15` payroll.py:20; `_to_zar` payroll.py:23; main.py:519 imports `_to_zar`, `_gl_import_income`, `_gl_import_expenses`. 11-05 Medium fixes (dashboard / `/v1/summary` parity, double-count cutover) confirmed present.
- Residual (Low): `_gl_import_cutover` (payroll.py:159-166) only compares against earliest native invoice/expense date; a GL containing payroll/depreciation lines before that date is still counted (accepted in 11-05 notes). Native payroll-only companies with no invoices/expenses have cutover=None → full GL counted.

## 3. Debtors
✓ No issues found.

## 4. Creditors
✓ No issues found. Reversal sources `purchase_order_reversal` present at payroll.py:3078, 3549, 4310; purchase_orders.py:505; journal.py:1347; financial_statements.py:610. `decrypt_field` for bank_name/account_number/branch_code at payroll.py:4353-4355.

## 5. Cross-module
- **Verified fixed (11-05 Critical):** csv_import.py:1398-1405 uses name-based type then GAAP code inference (`_infer_type_from_code`), `retype` only when Xero type column present (`retype=bool(_xt)`); csv_import.py:927 never retypes `is_system`. `/reclassify-gl-accounts` (csv_import.py:1449-1500) skips system accounts, DEFAULT_ACCOUNTS codes, accounts with native journal lines, and accounts with no import lines.
- **Verified fixed (11-05 High):** `DELETE /import/all` has `require_role("owner","admin","accountant")` (csv_import.py:2034-2037); orphan cleanup limited to accounts touched by deleted entries (csv_import.py:2064-2075). UI path now `/import/reclassify-gl-accounts` (App_js_fixed.js:6526).
- **Medium (residual, NEW):** reclassify still applies Xero code-range inference (`_infer_type_from_xero_code`) to import-created custom accounts whose codes sit outside the default chart. A custom ZuZan-style revenue account (e.g. 4100) or equity account (3xxx not in defaults) created purely by import would be retyped to expense. Fix: use `_type_from_xero_name` only, or require the Xero `Name` type column / show a dry-run preview before applying. UI text (App_js_fixed.js:6512) advertises Xero-code reclassification.
- Journal coverage (invoice payments, expense payments, PO receipts, PO payments, payroll) unchanged ✓. Import-awareness (backfill after invoice/expense import, Rules 6/7 excluding `import`, 3998/3999 on BS, unbalanced group rejection, non-ZAR exchange rate required) — code paths untouched since last run; not re-run live.
- Owner action still open: companies that ran a GL import / reclassify before 2026-11-05 should have 2000/2100/3xxx/4000 account types checked.

## 6. IFRS compliance (AFS)
- Framework: IFRS for SMEs (2nd ed.), financial_statements.py:2, 691, 794-797, 819. IFRS 18 and IFRS for SMEs 3rd edition both effective for periods beginning on/after 1 Jan 2027; first affected ZuZan FY starts 1 Mar 2027. Re-searched (accountingacademy.co.za, Forvis Mazars, ACCA, IFRS Foundation 2026 SMEs session) — dates unchanged. Transition plan `ifrs_smes_3rd_edition_transition_plan.md` stands.
- **5b deferred tax — verified, not hard-coded:** financial_statements.py:674 `"deferred_tax": deferred_tax_expense`; IN47 rate lookup financial_statements.py:95-118; `wear_and_tear_rate` database.py:606; migration database.py:1587 inside list. No edits.
- Finance costs below EBIT / tax from PBT unchanged ✓.

## 7. Tax updates (company + payroll)
- Tax year **2026/2027** (run date 6 Nov 2026): `TAX_YEARS["2026/2027"]` payroll.py:294; provisional `"2027/2028"` payroll.py:314; `_current_tax_year()` payroll.py:332; `UIF_CEIL` from current year payroll.py:350. UIF 1%+1% (payroll.py:351, 895-896), SDL 1% with R500k threshold (payroll.py:352, 901-903), VAT 15% (payroll.py:20), CIT 27% (payroll.py:2550, 3912) — all current. No announced VAT/CIT change.
- Sources: [SARS Guide for Employers 2027](https://www.sars.gov.za/guide-for-employers-in-respect-of-employees-tax-2027/), [Accounter SARS tax tables 2026/27](https://accounter.co.za/news/sars-tax-tables-2026-2027), [Xero SARS tax tables](https://www.xero.com/za/guides/sars-tax-tables-2026/), plus prior-run sources (TaxTim Budget 2026, EWN, Times Live). Bracket values were not re-diffed this run (no change since 4 Nov check). No tax-table edits made.

## 8. Action items
**Critical / High:** none open.

**Medium**
1. csv_import.py:1449-1500 — restrict reclassify to name-based mapping or add dry-run/confirm; avoid retyping import-created custom 3xxx/4xxx accounts by Xero code range.
2. Owner: check account types (2000/2100/3xxx/4000) in companies that imported GL before 2026-11-05.

**Low** (carried)
3. payroll.py:159 cutover edge cases (payroll-only companies; pre-cutover payroll/depreciation in GL).
4. main.py `_build_company_context`: use `VAT_RATE`, fix "last payroll" query.
5. POPIA/Privacy Policy coverage of AI-context disclosure.
6. Run full pytest locally (this run: syntax only).
7. Untracked leftovers: `commit_and_push.ps1`, `zuzan-app/public/sw.js`, `zuzan-backend/_to_delete/`, `find_default_password_accounts.py`, `fix_credit_note_vat_account.py`.
8. Normalise line endings (CRLF whole-file diffs).

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS-for-SMEs 3rd-ed. / IFRS 18 checklist Jan–Feb 2027.

---
## Addendum — second scheduled run, 2026-11-06 22:06 UTC
- **No source changes** since the earlier 2026-11-06 run: newest modified files are csv_import.py (11-05 21:09) and App_js_fixed.js (11-05 21:10). No code edited this run.
- `ast` syntax check of payroll, main, csv_import, journal, financial_statements, database: all OK.
- Re-verified: `"deferred_tax": deferred_tax_expense` (financial_statements.py:674, not hard-coded); `TAX_YEARS` "2026/2027" (payroll.py:294) and provisional "2027/2028" (payroll.py:314) present; Medium reclassify residual still open (`_infer_type_from_xero_code` used at csv_import.py:1490).
- Standards/tax re-searched (IFRS for SMEs 3rd ed. / IFRS 18 effective 1 Jan 2027; SARS 2026/27 tables, VAT 15%, CIT 27%): no new announcements or changes found. Sources: [Forvis Mazars](https://www.forvismazars.com/za/en/services/audit-assurance/financial-reporting/ifrs-for-smes-R-accounting-standard), [Accounting Academy SA](https://www.accountingacademy.co.za/news/read/updated-ifrs-for-smes-3rd-edition), [SARS Guide for Employers 2027](https://www.sars.gov.za/guide-for-employers-in-respect-of-employees-tax-2027/), [SimplePay Budget 2026](https://www.simplepay.co.za/blog/2026/02/27/national-budget-speech-2026/).
- **Verdict unchanged:** 0 Critical, 0 High, 1 Medium (reclassify residual), Low items carried. Action items as per the report above.
