# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 19 October 2026 (scheduled run)
**Prior report:** 2026-10-18 (evening run)

**Change detection:** HEAD `829ffc7` (19 Oct 21:50; two new commits since `c7a61af`). Only source change: `zuzan-backend/payroll.py` (+20/−6) — this closes both High items carried from the last report (see below). `py_compile` passes on payroll.py, journal.py, financial_statements.py, main.py. Other files (auth/billing/companies/main) show 19 Oct mtimes but are byte-identical to the previous commit. Local `zuzan.db` unchanged since 28 Sep (journal integrity 2026-10-19: 0 gaps). No code edits made by this run (5b already implemented).

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | PASS |
| Debtors (AR) | PASS |
| Creditors (AP) | PASS — reversal-awareness intact |
| Cross-module | PASS — payroll-delete journal orphaning now FIXED |
| IFRS (AFS) | PASS — no standards change; deferred tax (5b) verified |
| Tax (SARS) | PASS — rates/tables current; EMP501 IRP5 code defect now FIXED |

**Overall: PASS. Both previously open High defects were resolved in commit(s) of 19 Oct. No Critical/High items open.**

## 2. Reports
✓ No issues found. `_to_zar` (`payroll.py:18`) drives dashboard revenue/outstanding, management trend and `/v1/summary` in main.py. Revenue = paid invoices only; outstanding = pending/overdue(+sent); expenses excluded from revenue. Carried Low: label VAT201 due-date rule; add VAT201 regression tests; `VAT_RATE` redefined locally in several functions.

## 3. Debtors
✓ No issues found. `debtors_aging` (`payroll.py:3702`): due_date-based ageing, `_to_zar`, paid/written-off excluded.

## 4. Creditors
✓ No issues found. `creditors_aging` (`payroll.py:3765`); reversal-aware lookups (sources `purchase_order` + `purchase_order_reversal`, credit − debit) at `payroll.py:2646, 3118, 3800`, `financial_statements.py:592`, `purchase_orders.py:475`, `journal.py:1291`; bank fields decrypted via `decrypt_field`. Carried Low: PO-line→inventory matching by description==SKU/name is brittle; add explicit inventory_item_id.

## 5. Cross-module
- Journal coverage: invoices, invoice payments, expenses, PO receipts, PO payments, payroll — 0 gaps (`journal_integrity_2026-10-19.md`, local SQLite only).
- Import-awareness unchanged (no edits to csv_import/journal import code).
- **RESOLVED (was High):** `payroll.py:1467-1486` `DELETE /payslips/{period}` now calls `reverse_journal_entries(company_id, "payroll", ps.id, …)` (`journal.py:1376`, posts `payroll_reversal` entries, idempotent), wrapped in try/rollback, and returns `journal_entries_reversed`. Verified `journal.py:690` posts payroll entries with source `payroll`/`source_id=payslip.id`, so the reversal matches. Backfill (`journal.py:1211`) won't recreate entries for deleted payslips.
- Residual (Medium, new): no guard blocking deletion when the period's EMP201 is already submitted; and reports/ledger consumers should treat `payroll_reversal` alongside `payroll` (net credit−debit is correct, but any per-source filter on `"payroll"` alone would ignore reversals — not found in payroll.py/financial_statements.py grep, which use account-level totals).
- Carried caveat: confirm no per-row commit in the bank-import loop (`companies.py` ~:1962).

## 6. IFRS compliance (AFS)
- Framework: IFRS for SMEs. IFRS 18 and IFRS for SMEs 3rd edition remain effective for annual periods beginning on/after 1 Jan 2027 (early application permitted); no change found. `ifrs_smes_3rd_edition_transition_plan.md` stands. Sources: [Forvis Mazars SA](https://www.forvismazars.com/za/en/services/audit-assurance/financial-reporting/ifrs-for-smes-R-accounting-standard), [Accounting Academy](https://www.accountingacademy.co.za/news/read/updated-ifrs-for-smes-3rd-edition), [IFRS Foundation 3rd ed. overview](https://ifrs.org/content/dam/ifrs/supporting-implementation/smes/2025-webcasts/overview-third-edition-ifrs-for-smes.pdf). Search returned titles only this run.
- **5b deferred tax:** already implemented (`financial_statements.py:640` `"deferred_tax": deferred_tax_expense`; `wear_and_tear_rate` column in database.py with migration inside the list). Not changed since 17 Oct; no edits.
- Finance costs below EBIT; tax from profit_before_tax ✓. Medium carried: net AFS "Income Tax Payable (estimate)" against future provisional-tax journals.

## 7. Tax updates (company + payroll)
- Tax year at run date: 2026/2027 (1 Mar 2026 – 28 Feb 2027). `TAX_YEARS["2026/2027"]` (`payroll.py:132`): 18% to R245,100 … 45% above R1,878,600; rebates R17,820 / R9,765 / R3,249; UIF ceiling R17,712. `_current_tax_year()` (`:170`) selects by date; provisional `"2027/2028"` (`:152`) to be replaced after Budget Feb 2027.
- Sources: [SARS Employer Guide (2027)](https://www.sars.gov.za/guide-for-employers-in-respect-of-employees-tax-2027/), [Budget 2026 Tax Guide](https://www.treasury.gov.za/documents/national%20budget/2026/sars/Budget%202026%20Tax%20guide.pdf), [Accounter 2026/27](https://accounter.co.za/news/sars-tax-tables-2026-2027), [Xero SARS tables 2026](https://www.xero.com/za/guides/sars-tax-tables-2026/). Search returned titles only; no contradicting changes surfaced; figures rest on prior source reads.
- UIF 1%+1%, SDL 1%, VAT 15%, CIT 27%: no changes found.
- **RESOLVED (was High):** EasyFile employer export `payroll.py:1989` now writes UIF as `4141`, `:1993` SDL as `4142`. Remaining Medium: validate codes `4005` (`:1991`) and `7002` against the SARS BRS code list before the 31 Oct 2026 EMP501 deadline (12 days); the old `4474` line was replaced by `4142`.

## 8. Action items
**Critical:** none.
**High:** none open (two closed 19 Oct).
**Medium**
1. Add EMP201-submitted guard to `DELETE /payslips/{period}` (`payroll.py:~1450`).
2. Validate IRP5 codes 4005/7002 against SARS BRS before 31 Oct 2026 EMP501; run one test EasyFile export.
3. Confirm bank-import loop has no per-row commit (`companies.py` ~:1962).
4. Correct historic credit-note VAT lines posted to 2200 and historic entertainment VAT Input lines (`fix_credit_note_vat_account.py` untracked — run/commit or document cut-over).
5. Net AFS "Income Tax Payable (estimate)" against future provisional-tax journals.
6. Backfill NULL `paid_date`/`expense_date` for `management_accounts()`.
**Low**
7. Label VAT201 due-date rule; VAT201 regression tests; explicit inventory_item_id on PO lines; consolidate `VAT_RATE`.
8. Confirm NBCPSS clause-8 bonus formula with the Council.
9. Confirm `reclass_expenses_2026-09-28.py` run on production; decide `zuzan.db` history purge; delete stale `.bak`; clean untracked files; set `SECRET_KEY` in Render.

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS-for-SMEs 3rd ed./IFRS 18 checklist early 2027.
