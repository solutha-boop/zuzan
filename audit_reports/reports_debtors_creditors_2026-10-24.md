# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 24 October 2026 (scheduled run)
**Prior report:** 2026-10-23 (incl. its sections 9–10 remediation notes)

**Change detection:** HEAD `9ee80a0`; 12 commits since `4de6a4c`. No uncommitted tracked changes. `py_compile` passes for payroll, main, companies, journal, financial_statements, database, purchase_orders, csv_import, suppliers, customers. pytest is not installed in this sandbox, so the suite was not run. Local `zuzan.db` is stale and was not queried. No code edited this run (5b already implemented).

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | **PASS** — revenue/outstanding/trend/summary logic intact; foreign part-paid `_balance_zar` fix still present |
| Debtors (AR) | **PASS** — sent/overdue/partial, aging from `due_date`, ZAR via `_balance_zar` |
| Creditors (AP) | **PASS** — reversal-aware; bank details decrypted |
| Cross-module | **PASS with High** — Critical/High from 23 Oct (journal `_open_zar_parts`, `ar_zar`, partial-aware bad debt) confirmed fixed and committed; import-awareness intact |
| IFRS (AFS) | **FAIL (Medium)** — standards unchanged, deferred tax verified, but the AFS provisional-tax netting claimed on 24 Oct is gone from HEAD |
| Tax (SARS) | **PASS** — 2026/2027 tables, CIT 27%, VAT 15% unchanged |

**Overall: PASS on calculations, FAIL on change retention — 0 Critical, 1 High, 3 Medium.** The 24 Oct follow-up remediation (prior report section 10) was partly lost from the repo after it was committed.

## 2. Reports
- `dashboard` (`payroll.py:2310`): `total_revenue` = `_received_zar` over paid/part-paid invoices (`:2322`); `total_outstanding` = `_balance_zar` over sent/overdue/partial (`:2330`); expenses excluded; payroll and received-PO costs (`_po_delivered_net`) included once. Management accounts `total_outstanding` uses `_balance_zar` (`:3655`). `/v1/summary` (`main.py:515-550`) uses `_to_zar`/`_balance_zar`. ✓
- `_balance_zar` (`payroll.py:28-33`) multiplies `total_amount` by `exchange_rate` for foreign part-paid invoices, and `_received_zar` (`:36`) exists. 23 Oct Medium confirmed fixed.
- **LOW (regressed): `VAT_RATE = 0.15` is defined locally again** at `payroll.py:2694, 3088, 4208`, plus `companies.py:516` and `quotes.py:16`. The 24 Oct "defined once" fix is no longer in HEAD. The values are correct; the risk is only future drift.
- **LOW (regressed): `CORP_TAX_RATE = 0.27` literal is back** at `payroll.py:3837` (24 Oct fix to use `SA_CIT_RATE` lost). Value is correct.

## 3. Debtors
✓ No issues found. `debtors_aging` (`payroll.py:3938`) filters sent/overdue/partial (`:3948`), ages from `due_date` (`:3956`), amounts via `_balance_zar` (`:3960`); paid invoices excluded.

## 4. Creditors
✓ No issues found. `creditors_aging` (`payroll.py:4001`) nets `credit − debit` on 2000 with sources `purchase_order` + `purchase_order_reversal` (occurrences: payroll 6, purchase_orders 2, journal 1, financial_statements 2). Received/partial POs outstanding, paid excluded. Supplier bank name/account/branch decrypted via `decrypt_field` (`payroll.py:4079-4081`).

## 5. Cross-module
- ✓ **23 Oct Critical resolved and committed:** `journal.py:379` `_open_zar_parts`, `:442` `post_invoice_paid(..., ar_zar=None)`; `companies.py:947` and `:1161` call the new signatures. Bad-debt write-off/recovery use the open balance (`journal.py:399, 424`). No `TypeError` path remains.
- ✓ Journal coverage unchanged: invoice raise/payment, expense, PO receipt/payment, payroll runs. Balance-sheet Debtors/Creditors control reconciliation code unchanged (DB stale, not run).
- ✓ Import-awareness: `csv_import.py:125` `_auto_backfill`, `:497-502` non-ZAR exchange-rate requirement, `:1226-1258` unbalanced journal groups rejected; Rules 6/7 exclude `source="import"` (`payroll.py:2822, 2898`); 3998/3999 included in AFS.
- **HIGH (new): 24 Oct follow-up remediation was lost from the repo.** `4de6a4c` added these; later commits reverted them (`dedc9e1` removed the `Emp201Submission` table; `ef9fab5`/`2f46dc6`/`9ee80a0` removed the rest). HEAD has none of:
  - `Emp201Submission` model (`database.py`) and `/reports/emp201/submit/{period}` (`payroll.py`); `DELETE /payslips/{period}` (`payroll.py:1510`) again has no submitted-period guard.
  - Per-line `begin_nested()` SAVEPOINTs in bank import (`companies.py`, rollbacks at ~`2273, 2344, 2360` are whole-session again).
  - AFS "Income Tax Payable (estimate, net of provisional payments)" netting (`financial_statements.py`).
  - `SA_CIT_RATE` use at `payroll.py:3837` and single `VAT_RATE`.
  
  The IRP5 SARS-code keys (4102 etc.) and journal/`_balance_zar` fixes survive. Likely cause: a stale copy of these files was saved over the newer ones (the OneDrive/Windows sync caveat). `test_followups_2026_10_24.py` would fail against HEAD.
- **MEDIUM (carried, still open): `main.py:865-868` admin clear-data imports `StockMovement`, `BankTransaction`, `Document` from `database`; none exist there** (only `StandardBankTransaction`, `CompanyDocument`). The endpoint raises `ImportError` at runtime.
- Carried Low: untracked `fix_credit_note_vat_account.py`, `find_default_password_accounts.py`, `tests/`, `pytest.ini`, `requirements-test.txt`, `_to_delete/`, `commit_and_push.ps1`; auto-commit messages are all the same stale text.

## 6. IFRS compliance (AFS)
- Framework unchanged: IFRS for SMEs (2nd ed.). IFRS 18 (full IFRS, replaces IAS 1) effective for periods beginning ≥ 1 Jan 2027; IFRS for SMEs 3rd edition effective ≥ 1 Jan 2027. A web search this run returned no change (titles only; same sources as prior report: [Forvis Mazars SA](https://www.forvismazars.com/za/en/services/audit-assurance/financial-reporting/ifrs-for-smes-R-accounting-standard), [Accounting Academy](https://www.accountingacademy.co.za/news/read/updated-ifrs-for-smes-3rd-edition), [ACCA](https://www.accaglobal.com/learning-and-events/corporate-reporting/third-edition-ifrs-for-smes)). `ifrs_smes_3rd_edition_transition_plan.md` stands; first affected ZuZan FY starts 1 Mar 2027.
- **5b deferred tax — verified, not hard-coded.** `"deferred_tax": deferred_tax_expense` (`financial_statements.py:656`), `_deferred_tax_balance` (`:139`), `wear_and_tear_rate` column (`database.py:570`) with the ALTER inside the migrations list (`:1538`). No edits needed.
- Finance costs: account 6700 or name-matched interest presented below EBIT (`:222-226`); `profit_before_tax = ebit − finance_costs` (`:276`), tax and net profit derive from it (`:277-278`). ✓
- **MEDIUM (regressed): Income Tax Payable is again the gross estimate**, not net of provisional tax paid (2127 debits). See section 5.

## 7. Tax updates (company + payroll)
- Tax year at run date: **2026/2027** (1 Mar 2026 – 28 Feb 2027). `TAX_YEARS["2026/2027"]` present and unchanged: brackets 18% to R245,100, 26% to R383,100, 31% to R530,200, 36% to R695,800, 39% to R887,000, 41% to R1,878,600, 45% above; bases 44,118 / 79,998 / 125,599 / 185,215 / 259,783 / 666,339; rebates R17,820 / R9,765 / R3,249; UIF ceiling R17,712. Provisional `2027/2028` entry (flagged) present; `_current_tax_year` (`payroll.py:211`) is date-derived with newest-table fallback.
- Sources: [SARS individual rates](https://www.sars.gov.za/tax-rates/income-tax/rates-of-tax-for-individuals/), [SARS employer tax deduction tables guide](https://www.sars.gov.za/guide-for-employers-in-respect-of-tax-deduction-tables/), [Xero SA tax tables 2026](https://www.xero.com/za/guides/sars-tax-tables-2026/). The search returned titles only this run; the values were verified against the prior run's SARS page read and no change was announced.
- UIF 1% + 1%, SDL 1%, VAT 15%, CIT 27% (to 31 Mar 2027): unchanged. No announced-but-pending changes found.
- No edits to tax tables (report-only).

## 8. Action items
**High**
1. Re-apply the lost 24 Oct follow-ups from commit `4de6a4c` (`git diff 4de6a4c HEAD -- zuzan-backend/database.py zuzan-backend/payroll.py zuzan-backend/companies.py zuzan-backend/financial_statements.py`): `Emp201Submission` + submit/unsubmit endpoints + payslip-delete 409 guard; bank-import SAVEPOINTs; AFS provisional-tax netting. Then find why a stale file was saved over them (OneDrive sync of `C:\Zuzan` vs. the Projects folder copy), and run `tests/test_followups_2026_10_24.py`.
**Medium**
2. Fix `main.py:865-868` admin clear-data imports (`StandardBankTransaction`, `CompanyDocument`, remove `StockMovement`, or map to the real models) and cover it with a test.
3. Install pytest in the sandbox (or run the suite on the user's machine) so the scheduled audit can run the regression tests.
**Low**
4. Single `VAT_RATE` (`payroll.py:2694, 3088, 4208`, `companies.py:516`, `quotes.py:16`) and `CORP_TAX_RATE = SA_CIT_RATE` (`payroll.py:3837`).
5. Commit the untracked tests and scripts; use descriptive commit messages instead of the repeated "partial invoice payments" text.

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS-for-SMEs 3rd-ed. checklist Jan–Feb 2027; EMP501 reconciliation due 31 Oct 2026 (validate an EasyFile export; the EMP201 lock is not currently in the code).

## 9. Remediation (24 Oct 2026, after report)
Re-applied from `4de6a4c` as uncommitted working-tree edits (LF endings, matching the repo): `Emp201Submission` model + `/reports/emp201/submit/{period}` + 409 guard on `DELETE /payslips/{period}` + IRP5 SARS-code keys + overdue-count from `due_date` (`database.py`, `payroll.py`); per-line SAVEPOINT bank import (`companies.py`); AFS "Income Tax Payable (net of provisional payments)" (`financial_statements.py`). Also: single module-level `VAT_RATE` in `payroll.py`; `CORP_TAX_RATE` now uses `SA_CIT_RATE`; `saltedge.py:115` `inv.invoice_date` → `inv.issue_date` (nonexistent attribute); `test_payroll_year_end.py` updated to `code_4102_paye`.
Tests (sandbox, pytest installed): 163 pass, 9 fail — 4 `test_bank_feeds.py` auto-match failures (also fail on clean HEAD; still open), 4 `test_excel_imports.py` (sandbox/reader environment), 1 payroll-journal runner (sandbox cannot delete its temp DB). `main.py:865` clear-data import bug still open. Not committed.
