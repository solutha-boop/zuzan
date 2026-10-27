# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 26 October 2026 (scheduled run, 2nd firing today; the 25 Oct report is the most recent prior)
**Prior report:** 2026-10-25 (incl. its section 9 remediation notes)

**Change detection:** HEAD is still `4954751` (25 Oct 22:25). The 26 Oct remediation edits (main.py clear-data imports, VAT_RATE single-source in companies.py/quotes.py, commit_and_push.bat, tests) are **staged but not committed** (`git status`: 59 files changed vs HEAD). `py_compile` passes for payroll, main, companies, journal, financial_statements, database, purchase_orders, csv_import, suppliers, customers. Targeted spot-checks only this run (no live DB, pytest suite not re-run). No code edited (5b already implemented).

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | **PASS** — `_to_zar`/`_received_net_zar`/`_balance_zar` intact (payroll.py:23/33/45); dashboard at :2379, management at :3691 |
| Debtors (AR) | **PASS** — sent/overdue/partial, aged from `due_date`, ZAR via `_balance_zar` |
| Creditors (AP) | **PASS** — reversal-aware (`purchase_order_reversal` in payroll 6, purchase_orders 2, journal 1, financial_statements 2); bank details decrypted |
| Cross-module | **PASS** — no change to journal/import code since 25 Oct |
| IFRS (AFS) | **PASS** — standards unchanged; deferred tax verified |
| Tax (SARS) | **PASS** — 2026/2027 table unchanged and correct |

**Overall: PASS — 0 Critical, 0 High, 1 Medium, 1 Low.**

## 2. Reports
✓ No issues found. `VAT_RATE = 0.15` at payroll.py:20; CIT sourced from `fixed_assets.SA_CIT_RATE` (payroll.py:3249, 3993; financial_statements.py:86). Revenue remains ex-VAT (design change noted 25 Oct).

## 3. Debtors
✓ No issues found. `debtors_aging` (payroll.py:4094): status in sent/overdue/partial, amount via `_balance_zar`, buckets from `due_date`, no-due-date invoices go to not-due, paid excluded.

## 4. Creditors
✓ No issues found. `creditors_aging` (payroll.py:4157): received/partial POs; per-PO AP nets `credit − debit` over sources `purchase_order`, `purchase_order_reversal`, `po_payment`, `po_payment_reversal`; `decrypt_field` imported from crypto and applied to supplier bank fields.

## 5. Cross-module
- ✓ Journal coverage (invoice raise/payment, expense, PO receipt/payment, payroll) and import-awareness (auto-backfill, Rules 6/7 excluding `source="import"`, 3998/3999, unbalanced-group rejection, non-ZAR exchange-rate requirement) unchanged since 25 Oct — files journal.py (24 Oct), csv_import.py (25 Oct), purchase_orders.py (24 Oct), financial_statements.py (24 Oct) not modified since last audit. Live control-account reconciliation not executed (no DB in this environment); see `reconciliation_2026-10-26.md` and `journal_integrity_2026-10-26.md` for that.
- ✓ 25 Oct Medium #1 (main.py clear-data imports) and Low #3 (VAT_RATE single source: companies.py:516, quotes.py:16) are fixed in the working tree/index.
- **MEDIUM (open): remediation not yet committed.** The staged changes (59 files) are not in HEAD; the repo auto-commit has been stale since 25 Oct 22:25. Commit them and settle on a single canonical working copy (C:\Zuzan vs OneDrive Projects) to avoid a repeat of the 24 Oct overwrite.
- Carried Low: untracked helper scripts (`fix_credit_note_vat_account.py`, `find_default_password_accounts.py`), `_to_delete/`.

## 6. IFRS compliance (AFS)
- Framework unchanged: IFRS for SMEs (2nd ed.). IFRS 18 (full IFRS) and IFRS for SMEs 3rd edition both apply to periods beginning on/after 1 Jan 2027 — first affected ZuZan FY starts 1 Mar 2027. Web search this run returned no new announcements (titles only): [Accounting Academy](https://www.accountingacademy.co.za/news/read/updated-ifrs-for-smes-3rd-edition), [Forvis Mazars SA](https://www.forvismazars.com/za/en/services/audit-assurance/financial-reporting/ifrs-for-smes-R-accounting-standard), [IFRS Foundation overview](https://ifrs.org/content/dam/ifrs/supporting-implementation/smes/2025-webcasts/overview-third-edition-ifrs-for-smes.pdf). `ifrs_smes_3rd_edition_transition_plan.md` stands; no change since last audit.
- **5b deferred tax — verified, not hard-coded:** `_deferred_tax_balance` (financial_statements.py:139), opening/closing movement (:283-285), `total_tax = tax_expense + deferred_tax_expense` (:669), Note 9 `deferred_tax` (:674) and opening balance (:677). No edits needed.
- Finance costs below EBIT, tax/net profit from PBT: unchanged ✓.

## 7. Tax updates (company + payroll)
- Tax year at run date: **2026/2027** (1 Mar 2026 – 28 Feb 2027). `TAX_YEARS["2026/2027"]` (payroll.py:190-203): 18% ≤R245,100; 26% to R383,100 (base 44,118); 31% to R530,200 (79,998); 36% to R695,800 (125,599); 39% to R887,000 (185,215); 41% to R1,878,600 (259,783); 45% above (666,339); rebates R17,820/R9,765/R3,249; UIF ceiling R17,712 — unchanged from the 25 Oct verification against the [SARS individual rates page](https://www.sars.gov.za/tax-rates/income-tax/rates-of-tax-for-individuals/). Search results this run ([TaxTim Budget 2026](https://www.taxtim.com/blog/budget-2026), [Treasury Budget 2026 Tax guide](https://www.treasury.gov.za/documents/national%20budget/2026/sars/Budget%202026%20Tax%20guide.pdf), [SARS Employer Guide 2027](https://www.sars.gov.za/guide-for-employers-in-respect-of-employees-tax-2027/)) returned titles only, with no rate change reported.
- UIF 1%+1%, SDL 1% (threshold R500k payroll, payroll.py:797), VAT 15%, CIT 27%: no announced changes found. Provisional `2027/2028` entry (payroll.py:210) present — must be replaced after Budget Feb 2027.
- No edits to tax tables (report-only).

## 8. Action items
**Medium**
1. Commit/push the staged 26 Oct remediation (59 files); fix the stale auto-commit; choose one canonical working copy (exclude C:\Zuzan from OneDrive sync).
**Low**
2. Commit or remove untracked helper scripts / `_to_delete/`; run the full pytest suite locally.

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS-for-SMEs 3rd-ed. checklist Jan–Feb 2027; EMP501 annual reconciliation due 31 Oct 2026.
