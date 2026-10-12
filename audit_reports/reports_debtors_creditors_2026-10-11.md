# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 11 October 2026 (second scheduled run today; supersedes the 06:19 run)
**Prior report:** 2026-10-11 (earlier run) / 2026-10-09

**Change detection:** HEAD `b933dbc` (previous run: `e31144c`) — 13 commits since. Changed: `payroll.py` (+267), `csv_import.py` (employee import now upsert), `companies.py` (terminate/reinstate), `database.py` (employment_category, psspf_exempt, termination fields), `journal.py` (BC-levy payable line), frontend. `py_compile` passes on payroll, journal, financial_statements, database, purchase_orders, main, companies, csv_import. Reports/AR/AP/AFS/invoice-expense import code paths unchanged. No code edits made by this audit.

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | PASS |
| Debtors (AR) | PASS |
| Creditors (AP) | PASS — reversal-awareness intact |
| Cross-module | PASS (journal.py change reviewed, balanced) |
| IFRS (AFS) | PASS — no standards change; deferred tax (5b) already implemented |
| Tax (SARS) | PASS — 2026/2027 tables correct; **prior UIF-exemption finding is RESOLVED** |

**Overall: PASS. No Critical/High/Medium findings.**

## 2. Reports
✓ No issues found. `_to_zar()` `payroll.py:18`; dashboard `total_outstanding` `payroll.py:1926`; management accounts `:3233`; `/v1/summary` uses `_to_zar` (`main.py:473, :503`).

## 3. Debtors
✓ No issues found. `GET /reports/debtors-aging` `payroll.py:3515` (logic unchanged).

## 4. Creditors
✓ No issues found. `GET /reports/creditors-aging` `payroll.py:3578`. Reversal-aware lookups (`purchase_order` + `purchase_order_reversal`): `payroll.py:2460, :2932, :3614`, `journal.py:1166`, `purchase_orders.py:445`. Supplier bank details decrypted `payroll.py:3657-3659`, `suppliers.py:48-50`.

## 5. Cross-module
✓ No issues found. `journal.py` change this period: NBCPSS "BC levy payable" now credits employee deduction + employer share (`bc_levy_er + bc_levy_ee`), fixing a R7/employee journal imbalance that aborted payroll runs — consistent with `calc_payroll` deducting the levy from net pay. `csv_import.py` changes are employee-import only (upsert, encrypted bank fields via `encrypt_field`; read side decrypts at `companies.py:1601-1603`); invoice/expense import, backfill, Rule 6/7 import exclusion and unbalanced-journal rejection untouched.

## 6. IFRS compliance (AFS)
- Framework: IFRS for SMEs (`financial_statements.py:2, :623, :717`). IFRS 18 and IFRS for SMEs 3rd edition remain effective for periods beginning on/after 1 Jan 2027 — no change since last audit; transition plan (`audit_reports/ifrs_smes_3rd_edition_transition_plan.md`) stands.
- **5b deferred tax:** already implemented — `_deferred_tax_balance()` `:131`, expense = closing − opening `:266-268`, `total_tax` `:601`, `deferred_tax` `:606`, opening balance `:609`. `wear_and_tear_rate` column present in `database.py` with migration inside the list. Verified; no edits needed.
- Finance costs below EBIT / tax from profit_before_tax: unchanged ✓.

## 7. Tax updates (company + payroll)
- Tax year: 2026/2027 (1 Mar 2026 – 28 Feb 2027). `TAX_YEARS["2026/2027"]` `payroll.py:132`: brackets (18% to R245,100 … 45% > R1,878,600), primary R17,820, secondary R9,765, tertiary R3,249, UIF ceiling R17,712 — match SARS. Provisional `"2027/2028"` `:152` flagged `provisional`. `_current_tax_year()` `:170`.
- `UIF_RATE`/`SDL_RATE` 1% (`:189-190`), `VAT_RATE` 15%, `CORP_TAX_RATE` 27% (`:3415`): no announced changes found.
- **RESOLVED since last run:** UIF exemption now applies to `public_servant` only; `learnership`/`foreign_national`/`temp_labour` attract normal UIF and no category is SDL-exempt (`payroll.py` ~`:710-730`). Matches the earlier recommendation.
- NBCPSS (info): Year-4 minimums, PSSPF rate schedule (7.5%, watch item for announced temporary reduction pending FSCA approval), medical R122/R172.50, clause-8 annual bonus and anniversary logic added — domain-specific, not SARS; bonus now taxed with the SARS annual-bonus method (no ×12 annualisation) ✓. Clause-8 formula flagged in code as "confirm with the Council".
- Sources: [SARS Guide for Employers 2027](https://www.sars.gov.za/guide-for-employers-in-respect-of-employees-tax-2027/), [KPMG SA Budget Guide 2026](https://assets.kpmg.com/content/dam/kpmgsites/za/pdf/2026/02/SA%20Budget%20Guide%202026.pdf), prior-run SARS rates page check.

## 8. Action items
**Critical / High / Medium:** none.
**Low**
1. `companies.py:1777` — `terminate_employee` uses `datetime.fromisoformat(data.date)` unguarded; invalid input → 500. Return 400 (carried).
2. Confirm NBCPSS clause-8 bonus formula with the Council (`payroll.py` `nbcpss_annual_bonus`).
3. (carried) Confirm `reclass_expenses_2026-09-28.py` run on production; decide `zuzan.db` history purge; delete `zuzan.db.bak-20260928-184955`.
4. (carried) Backfill NULL `paid_date`/`expense_date` for `management_accounts()`.
5. (carried, Info) Clean untracked `zuzan-backend/_to_delete/`; verify split-schedule payroll runs both post journals and feed dashboard payroll cost.

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS-for-SMEs 3rd ed. / IFRS 18 checklist early 2027; watch PSSPF rate-reduction confirmation.
