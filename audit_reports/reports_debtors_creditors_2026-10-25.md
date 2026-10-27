# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 25 October 2026 (scheduled run)
**Prior report:** 2026-10-24 (incl. its section 9 remediation notes)

**Change detection:** HEAD `4954751` (auto-commits of 25 Oct: QuickBooks/Xero migration wizards, partial payments, multi-entity switcher). Working tree has only untracked files (tests, helper scripts, `_to_delete/`). `py_compile` passes for payroll, main, companies, journal, financial_statements, database, purchase_orders, csv_import, suppliers, customers. pytest is not installed in this sandbox (the device VM), so the suite was not run. No code edited this run (5b already implemented). Line numbers below are as at this run (payroll.py has shifted ~+30 to +100 lines since 24 Oct).

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | **PASS** — revenue/outstanding/trend/summary logic intact; revenue is now net of VAT (see note) |
| Debtors (AR) | **PASS** — sent/overdue/partial, aging from `due_date`, ZAR via `_balance_zar` |
| Creditors (AP) | **PASS** — reversal-aware; bank details decrypted |
| Cross-module | **PASS with Medium** — journal coverage and import-awareness intact; 24 Oct "lost fixes" are now back in HEAD |
| IFRS (AFS) | **PASS** — standards unchanged, deferred tax verified, provisional-tax netting restored |
| Tax (SARS) | **PASS** — 2026/2027 tables match SARS page re-read this run; CIT 27%, VAT 15% |

**Overall: PASS — 0 Critical, 0 High, 2 Medium, 2 Low.** The High from 24 Oct (remediation lost from repo) is **resolved**: the working-tree edits were committed in the 25 Oct auto-commits.

## 2. Reports
- `dashboard` (`payroll.py:2333`): paid + partial invoices only for revenue; `total_revenue = sum(_received_net_zar(i))` (`:2345`) plus bank-import income (`:2347`); `total_outstanding = sum(_balance_zar(...))` over sent/overdue/partial (`:2351-2353`). Expenses excluded; payroll cost and received/partial/paid PO costs (`_po_delivered_net`, `:2366`) included once. ✓
- **Note (design change, not a defect):** revenue is now **ex-VAT** (`_received_net_zar`, `payroll.py:32-41`): a VAT-registered company's revenue no longer includes output VAT. This is the correct IFRS treatment; the original checklist wording ("amount × exchange_rate / paid_amount_zar") is still how the gross ZAR figure is derived (`_to_zar`, `:22`), then apportioned by net/gross ratio. Non-ZAR conversion intact; part-paid foreign invoices use `paid_amount_zar`.
- `_balance_zar` (`:44`), `_received_zar` (`:52`) intact. `/v1/summary` (`main.py`) uses `_to_zar`/`_balance_zar`. Management accounts at `:3645` unchanged in structure.
- **LOW (resolved):** single module-level `VAT_RATE = 0.15` at `payroll.py:19`; `CORP_TAX_RATE` now imports `SA_CIT_RATE` (`:3947`). Still duplicated: `companies.py:516`, `quotes.py:16` (values correct).

## 3. Debtors
✓ No issues found. `debtors_aging` (`payroll.py:4048`): sent/overdue/partial only, amount via `_balance_zar` (`:4070`), buckets computed from `due_date` (`:4066-4090`), invoices without a due date go to not-due; paid excluded.

## 4. Creditors
✓ No issues found. `creditors_aging` (`payroll.py:4111`) nets `credit − debit` on 2000 with sources `purchase_order` + `purchase_order_reversal` (11 occurrences across payroll/purchase_orders/journal/financial_statements). Received/partial POs outstanding, paid excluded. Supplier bank name/account/branch decrypted via `decrypt_field` (`payroll.py:4121, 4189-4191`).

## 5. Cross-module
- ✓ Journal coverage unchanged: invoice raise/payment (`journal.py:442 post_invoice_paid(..., ar_zar=None)`, `_open_zar_parts :379`), partial-aware bad debt, expense, PO receipt/payment, payroll runs. DB not available in this run, so live control-account reconciliation was not executed.
- ✓ Import-awareness: `csv_import.py:125 _auto_backfill` (called `:574`), exchange-rate requirement for non-ZAR (`:530-535`), unbalanced journal groups rejected (`:1259-1291`), Rules 6/7 exclude `source="import"` (`payroll.py:2875-2884, 2953`), 3998/3999 included in AFS.
- ✓ **24 Oct items now present in HEAD:** `Emp201Submission` (`database.py:699`; submit/unsubmit endpoints `payroll.py:3586-3636`; 409 guard on payslip delete `:1538`), bank-import SAVEPOINT (`companies.py:2222`), AFS provisional-tax netting (`financial_statements.py:348`).
- **MEDIUM (carried, still open): `main.py` admin clear-data (`~:866-869`) imports `StockMovement`, `BankTransaction`, `Document` from `database`; none exist** (only `StandardBankTransaction`, `CompanyDocument`). The endpoint raises `ImportError` at runtime.
- **MEDIUM (process):** the repo is auto-committed every few minutes with a stale message ("QuickBooks migration wizard + Xero wizard + partial payments…"), and the 24 Oct incident showed stale-file overwrites between `C:\Zuzan` and the OneDrive Projects copy. Recommend one canonical working copy.
- Carried Low: untracked `fix_credit_note_vat_account.py`, `find_default_password_accounts.py`, `tests/`, `pytest.ini`, `requirements-test.txt`, `_to_delete/`, `commit_and_push.ps1`, `zuzan-app/public/sw.js`.

## 6. IFRS compliance (AFS)
- Framework unchanged: IFRS for SMEs (2nd ed.). IFRS 18 (replaces IAS 1; full IFRS) and the IFRS for SMEs 3rd edition both apply to periods beginning on/after 1 Jan 2027 — first affected ZuZan FY starts 1 Mar 2027. Web search this run returned no new announcements (same sources as prior run): [Forvis Mazars SA](https://www.forvismazars.com/za/en/services/audit-assurance/financial-reporting/ifrs-for-smes-R-accounting-standard), [Accounting Academy](https://www.accountingacademy.co.za/news/read/updated-ifrs-for-smes-3rd-edition), [IFRS Foundation overview](https://ifrs.org/content/dam/ifrs/supporting-implementation/smes/2025-webcasts/overview-third-edition-ifrs-for-smes.pdf). `ifrs_smes_3rd_edition_transition_plan.md` stands; no change since last audit.
- **5b deferred tax — verified, not hard-coded:** `_deferred_tax_balance` (`financial_statements.py:139`), opening/closing movement (`:283-285`), Note 9 `deferred_tax` = movement and `total_tax` = current + deferred (`:669-678`); `wear_and_tear_rate` column (`database.py:570`) with ALTER inside the migrations list (`:1551`). No edits needed.
- Finance costs: 6700/name-matched interest below EBIT; PBT = EBIT − finance costs; tax and net profit derive from PBT. ✓
- Income Tax Payable now "net of provisional payments" when applicable (`:348`). ✓

## 7. Tax updates (company + payroll)
- Tax year at run date: **2026/2027** (1 Mar 2026 – 28 Feb 2027). `TAX_YEARS["2026/2027"]` (`payroll.py:189-203`) compared to the [SARS individual rates page](https://www.sars.gov.za/tax-rates/income-tax/rates-of-tax-for-individuals/) re-read this run: brackets 18% ≤R245,100; 26% to R383,100 (base 44,118); 31% to R530,200 (79,998); 36% to R695,800 (125,599); 39% to R887,000 (185,215); 41% to R1,878,600 (259,783); 45% above (666,339); rebates R17,820 / R9,765 / R3,249 — **all match**. UIF ceiling R17,712 unchanged. `_current_tax_year` (`:227`) date-derived with newest-table fallback; provisional `2027/2028` entry present (`:209`) — must be replaced after Budget Feb 2027.
- UIF 1%+1% (`:246`), SDL 1% (`:247`), VAT 15%, CIT 27% (companies, years ending on/after 31 Mar 2024 until changed): no announced changes found in [Grant Thornton 2026 Budget commentary](https://www.grantthornton.co.za/insights2/2026-budget-analysis-and-commentary/) / [SAIT VAT 2026](https://thesait.org.za/vat-in-2026-navigating-stability-and-the-legacy-of-the-2025-reversals/) search titles (search returned titles only; no rate change reported).
- No edits to tax tables (report-only).

## 8. Action items
**Medium**
1. Fix `main.py` admin clear-data imports (use `StandardBankTransaction`, `CompanyDocument`; drop/map `StockMovement`) and add a test.
2. Establish a single canonical working copy (C:\Zuzan vs OneDrive Projects) and replace the repeated auto-commit message with meaningful ones, to prevent a repeat of the 24 Oct overwrite.
**Low**
3. Single `VAT_RATE` import for `companies.py:516` and `quotes.py:16`.
4. Install pytest in the audit environment (or run the suite locally) so regression tests run on schedule; commit untracked tests/scripts.

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS-for-SMEs 3rd-ed. checklist Jan–Feb 2027; EMP501 annual reconciliation due 31 Oct 2026.

## 9. Remediation (26 Oct 2026, after report) — uncommitted working-tree edits
- **Medium #1 fixed:** `main.py` `admin_clear_company_data` now imports only existing models (`CompanyDocument`, and the six bank-transaction models `Stitch/SaltEdge/Absa/Nedbank/Investec/StandardBankTransaction`); the non-existent `StockMovement` is dropped. New regression test `tests/test_admin_clear_data_imports.py` (passes).
- **Low #3 fixed:** `companies.py:516` and `quotes.py:16` now `from payroll import VAT_RATE` (single source, 0.15; import verified, no cycle).
- **Medium #2 partly fixed:** `commit_and_push.bat` default commit message is now `chore: sync working copy [stamp]` (was a stale feature message) and it stages the tests/pytest files. **Not fixable by me:** choosing the single canonical working copy (C:\Zuzan vs OneDrive Projects folder) — recommend working only in `C:\Zuzan` and excluding it from OneDrive sync.
- **Low #4:** pytest installed in the device VM (`PYTHONPATH=$HOME/pkgs`); `-k "clear or admin or vat or quote"` = 18 pass, plus the new test. Full suite not re-run. Nothing committed or pushed.
