# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 7 November 2026 (scheduled run)
**Prior report:** 2026-11-06 (incl. addendum)

**Scope / method:** static review (grep/read, `ast` syntax check of payroll, main, csv_import, journal, financial_statements, database, purchase_orders — all parse OK; git diff vs 029f907). No live DB / pytest. **No code edited** (5b already implemented).

**Changes since last report:** commits ef1be26 / 784e8e5 / c08eef3 (2026-11-07) touched csv_import.py (fixed-assets import, Xero account-type fix, already reviewed 11-05/06), main.py (`_build_company_context` AI-bot context now includes GL-import revenue/expenses via `_gl_import_income/_gl_import_expenses`; `max_tokens` 500→1500) and App_js_fixed.js (+4 lines). payroll.py mtime changed 11-07 but has no content diff vs 029f907 (line endings only).

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | **PASS** — `_to_zar` logic intact (payroll.py:23); AI-context revenue/expense now consistent with dashboard (GL import included) |
| Debtors (AR) | **PASS** — unchanged |
| Creditors (AP) | **PASS** — reversal-aware sources and `decrypt_field` intact |
| Cross-module | **PASS (Medium residual carried)** — reclassify residual still open |
| IFRS (AFS) | **PASS** — no change; deferred tax verified |
| Tax (SARS) | **PASS** — 2026/2027 present, no rate changes |

**Overall: 0 Critical, 0 High, 1 Medium (carried), Low items carried.**

## 2. Reports
✓ No issues found. `VAT_RATE=0.15` payroll.py:20; `_to_zar` payroll.py:23. main.py `_build_company_context` now imports `_gl_import_income/_gl_import_expenses` (parity with dashboard/`/v1/summary`).
- Low (carried): payroll.py:159 `_gl_import_cutover` edge cases. main.py `_build_company_context` still hard-codes `/1.15` for manual expenses instead of `VAT_RATE`, and does not apply the cutover guard shown for the dashboard (possible GL/native double count in the AI context only — advisory text, not statements).

## 3. Debtors
✓ No issues found.

## 4. Creditors
✓ No issues found. `purchase_order_reversal` present: payroll.py (6 refs), purchase_orders.py (2), journal.py (1), financial_statements.py (2). `decrypt_field` for bank_name/account_number/branch_code at payroll.py:4353-4355.

## 5. Cross-module
- Journal coverage (invoice payments, expense payments, PO receipts, PO payments, payroll) unchanged ✓. Import-awareness paths untouched this run (not re-run live).
- **Medium (carried):** csv_import.py:1490 `_infer_type_from_xero_code` still applied in `/reclassify-gl-accounts` to import-created custom accounts; may retype custom 3xxx/4xxx accounts to expense. Fix: name-based mapping only, or dry-run/confirm.
- Owner action still open: check account types (2000/2100/3xxx/4000) in companies that imported a GL before 2026-11-05.

## 6. IFRS compliance (AFS)
- Framework: IFRS for SMEs (2nd ed.) — financial_statements.py. IFRS 18 and IFRS for SMEs 3rd edition effective for periods beginning on/after 1 Jan 2027 (first affected ZuZan FY starts 1 Mar 2027); no change found. Transition plan `ifrs_smes_3rd_edition_transition_plan.md` stands.
- **5b deferred tax — verified, not hard-coded:** financial_statements.py:674 `"deferred_tax": deferred_tax_expense`; `wear_and_tear_rate` in database.py (migration inside list). No edits.
- Finance costs below EBIT / tax from PBT unchanged ✓.

## 7. Tax updates (company + payroll)
- Tax year **2026/2027**: `TAX_YEARS["2026/2027"]` payroll.py:294 (brackets 18%→45%, thresholds 245,100 / 383,100 / 530,200 / 695,800 / 887,000 / 1,878,600; rebates 17,820 / 9,765 / 3,249; UIF ceiling 17,712); provisional "2027/2028" payroll.py:314 flagged `provisional`; `_current_tax_year()` payroll.py:332. UIF 1%+1%, SDL 1%, VAT 15%, CIT 27% — all current; no announced VAT/CIT change found.
- Sources: [SARS Guide for Employers 2027](https://www.sars.gov.za/guide-for-employers-in-respect-of-employees-tax-2027/), [Budget 2026 Tax Guide](https://www.treasury.gov.za/documents/national%20budget/2026/sars/Budget%202026%20Tax%20guide.pdf), [Accounter SARS tax tables 2026/27](https://accounter.co.za/news/sars-tax-tables-2026-2027), [SimplePay Budget 2026](https://www.simplepay.co.za/blog/2026/02/27/national-budget-speech-2026/). Search returned link lists only; values compared against prior-run verified figures. No tax-table edits made.

## 8. Action items
**Critical / High:** none open.

**Medium**
1. csv_import.py:1490 — restrict reclassify to name-based mapping or add dry-run/confirm.
2. Owner: check account types in companies that imported GL before 2026-11-05.

**Low** (carried)
3. payroll.py:159 cutover edge cases; apply same guard + `VAT_RATE` in main.py `_build_company_context`.
4. Fix "last payroll" query in `_build_company_context`.
5. POPIA/Privacy Policy coverage of AI-context disclosure.
6. Run full pytest locally (syntax only here).
7. Untracked leftovers: `commit_and_push.ps1`, `zuzan-app/public/sw.js`, `zuzan-backend/_to_delete/`, `find_default_password_accounts.py`, `fix_credit_note_vat_account.py`.
8. Normalise line endings (CRLF whole-file diffs).

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS-for-SMEs 3rd-ed. / IFRS 18 checklist Jan–Feb 2027.
