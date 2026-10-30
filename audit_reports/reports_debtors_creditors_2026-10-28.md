# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 28 October 2026 (scheduled run)
**Prior report:** 2026-10-27

**Change detection:** payroll.py and main.py last modified 28 Oct 04:51 UTC, journal.py 28 Oct 03:50 UTC (the benefit-scheme journal fix). csv_import.py, purchase_orders.py, financial_statements.py, database.py are unchanged since 24–26 Oct. `py_compile` passes for all staged backend modules. Static review only (no live DB / pytest). No code edited (5b already implemented). Note: C:\Zuzan git tooling was not usable from the device shell this run (device_bash timed out); files were reviewed via staged copies.

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | **PASS** — `_to_zar` (payroll.py:23), VAT_RATE=0.15 (payroll.py:20) intact |
| Debtors (AR) | **PASS** — `debtors_aging` (payroll.py:4094) unchanged |
| Creditors (AP) | **PASS** — reversal-aware sources at payroll.py:2972, 3443, 4192; purchase_orders.py:505; journal.py:1347; `decrypt_field` at payroll.py:4167, 4235-4237 |
| Cross-module | **PASS** — prior High (benefit schemes not journalled) is now fixed in journal.py |
| IFRS (AFS) | **PASS** — no change in standards; deferred tax verified |
| Tax (SARS) | **PASS** — 2026/2027 table unchanged |

**Overall: 0 Critical, 0 High, 1 Low.**

## 2. Reports
✓ No issues found.

## 3. Debtors
✓ No issues found.

## 4. Creditors
✓ No issues found.

## 5. Cross-module
- **Resolved (prior High):** journal.py now defines account 2330 Benefit Schemes Payable (journal.py:~72) and 5190 Employer Benefit Scheme Contributions (journal.py:94); `post_payroll` reads `benefit_contributions_json` (journal.py:815-826) and posts DR 5190 (employer share) / CR 2330 (employee + employer) (journal.py:881-886). Balance check: employee share reduces bank net pay and is credited to 2330; employer share is DR 5190 / CR 2330 — entry balances. Matches the payroll.py:1240-1285 computation (net_pay −ee, total_cost +er). The regression scenario in `test_payroll_journal_balance.py` was not re-run here (not staged) — run locally to confirm.
- Journal coverage for invoices, expenses, PO receipts/payments, payroll and import-awareness (backfill, Rules 6/7, 3998/3999, unbalanced-group rejection, non-ZAR rate): unchanged, csv_import.py/purchase_orders.py not modified since 24–25 Oct.
- Live control-account reconciliation not executed here; see `reconciliation_2026-10-26.md` / `journal_integrity_2026-10-26.md`.
- Minor observation (Low): the benefit parse in journal.py swallows malformed JSON by zeroing both amounts (journal.py:824-825), which would silently unbalance that payslip's entry; the balance assertion would then raise rather than post wrongly, so it fails safe.

## 6. IFRS compliance (AFS)
- Framework unchanged: IFRS for SMEs (2nd ed.). IFRS 18 and IFRS for SMEs 3rd ed. both effective for periods beginning on/after 1 Jan 2027 (first ZuZan FY starting 1 Mar 2027). Searches this run found no new announcements ([Forvis Mazars SA](https://www.forvismazars.com/za/en/services/audit-assurance/financial-reporting/ifrs-for-smes-R-accounting-standard), [Accounting Academy](https://www.accountingacademy.co.za/news/read/updated-ifrs-for-smes-3rd-edition), [IFRS Foundation](https://www.ifrs.org/content/ifrs/home/news-and-events/news/2025/02/iasb-issues-major-update-smes-accounting-standard.html)). Transition plan `ifrs_smes_3rd_edition_transition_plan.md` stands.
- **5b deferred tax — verified, not hard-coded:** `wear_and_tear_rate` column (database.py:606) with migration inside the list (database.py:1587); `_deferred_tax_balance` (financial_statements.py:139); opening/closing (:283-284); `total_tax = tax_expense + deferred_tax_expense` (:669); Note 9 fields (:674-678); equity movement (:749). No edits.
- Finance costs below EBIT / tax from PBT: unchanged ✓.

## 7. Tax updates (company + payroll)
- Tax year: **2026/2027** (1 Mar 2026 – 28 Feb 2027); `_current_tax_year()` (payroll.py:228) selects by date. `TAX_YEARS["2026/2027"]` (payroll.py:190-203): 18% to R245,100 … 45% above R1,878,600; rebates R17,820 / R9,765 / R3,249; UIF ceiling R17,712 — unchanged. Sources: [SARS rates for individuals](https://www.sars.gov.za/tax-rates/income-tax/rates-of-tax-for-individuals/), [SARS Employer Guide 2027](https://www.sars.gov.za/guide-for-employers-in-respect-of-employees-tax-2027/), [SimplePay Budget 2026](https://www.simplepay.co.za/blog/2026/02/27/national-budget-speech-2026/), [Accounter 2026/27 tables](https://accounter.co.za/news/sars-tax-tables-2026-2027). Search returned titles only; no change announcements found.
- UIF 1%+1%, SDL 1% (payroll.py:248), VAT 15%, CIT 27%: no announced changes found. Provisional `2027/2028` entry (payroll.py:210, flagged `provisional`) must be replaced after Budget Feb 2027. No tax-table edits made.

## 8. Action items
**Low**
1. Run `test_payroll_journal_balance.py` / full pytest locally to confirm the benefit-scheme scenario (not executed in this environment); commit/delete untracked helpers (`commit_and_push.ps1`, `zuzan-app/public/sw.js`, `zuzan-backend/_to_delete/`, etc.).

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS-for-SMEs 3rd-ed. checklist Jan–Feb 2027; EMP501 annual reconciliation due 31 Oct 2026.
