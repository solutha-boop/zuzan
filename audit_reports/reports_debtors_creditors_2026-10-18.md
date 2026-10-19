# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 18 October 2026 (scheduled run, evening; supersedes the earlier catch-up run, saved as `reports_debtors_creditors_2026-10-18_run1.md`)
**Prior report:** 2026-10-18 (run 1)

**Change detection:** HEAD `c7a61af` (17 Oct 08:13) unchanged. No source file modified since 17 Oct 06:13 (App_js_fixed.js 17 Oct 05:19). `py_compile` passes on payroll.py, financial_statements.py, journal.py, main.py. Untracked: `commit_and_push.ps1`, `_to_delete/`, `find_default_password_accounts.py`, `fix_credit_note_vat_account.py`. No code edits made (5b already implemented). Local `zuzan.db` not re-queried (unchanged since 28 Sep). Because the code is identical to the previous run, findings below are carried forward after spot-check re-verification of the key line references.

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | PASS |
| Debtors (AR) | PASS |
| Creditors (AP) | PASS — reversal-awareness intact |
| Cross-module | PASS on code; payroll-delete journal orphaning still open |
| IFRS (AFS) | PASS — no standards change; deferred tax (5b) verified |
| Tax (SARS) | PASS on rates/tables; EMP501 IRP5 code defect still open (deadline 31 Oct, 13 days) |

**Overall: PASS with two open High defects (unchanged).**

## 2. Reports
✓ No issues found. `_to_zar` (`payroll.py:18`) drives dashboard revenue/outstanding, management trend and `/v1/summary` (`main.py` ~:513, :543). Revenue = paid invoices only; outstanding = pending/overdue(+sent); expenses excluded from revenue. Carried Low items: VAT201 due-date rule (25th vs eFiling last business day) to be labelled; add VAT201 regression tests; `VAT_RATE` redefined locally in three functions (`payroll.py` ~:2462, 2856, 3958).

## 3. Debtors
✓ No issues found. `debtors_aging` `payroll.py:3688`: due_date ageing, `_to_zar`, paid and written-off excluded.

## 4. Creditors
✓ No issues found. `creditors_aging` `payroll.py:3751`; reversal-aware lookups (sources `purchase_order` + `purchase_order_reversal`, credit − debit) at `payroll.py:2632, 3104, 3786`, `financial_statements.py:592`, `purchase_orders.py` pay_po, `journal.py` backfill; bank fields decrypted via `decrypt_field`. Carried Low: PO-line→inventory matching by exact description==SKU/name is brittle; consider explicit inventory_item_id.

## 5. Cross-module
- Latest journal integrity report: `journal_integrity_2026-10-12.md` (0 gaps); no newer one. Journal covers invoices, payments, expenses, PO receipts/payments, payroll.
- Import-awareness intact (unchanged code): auto-backfill after import, Rules 6/7 exclude `source="import"`, 3998/3999 handled, unbalanced journal groups rejected, non-ZAR invoice imports require an exchange rate.
- **OPEN (High, carried):** `payroll.py:1440-1472` `DELETE /payslips/{period}` deletes `Payslip` rows only (confirmed again: loop of `db.delete(ps)`, no journal reversal, no EMP201-submitted guard); payroll journal entries orphaned, re-run duplicates them.
- Carried caveat: confirm no per-row commit in the bank-import loop (`companies.py` ~:1962).

## 6. IFRS compliance (AFS)
- Framework: IFRS for SMEs. IFRS 18 and IFRS for SMEs 3rd edition remain effective for annual periods beginning on/after 1 Jan 2027 (early application permitted); no change found. Transition plan `ifrs_smes_3rd_edition_transition_plan.md` stands. Sources: [Forvis Mazars SA](https://www.forvismazars.com/za/en/services/audit-assurance/financial-reporting/ifrs-for-smes-R-accounting-standard), [Accounting Academy](https://www.accountingacademy.co.za/news/read/updated-ifrs-for-smes-3rd-edition), [KPMG IFRS for SMEs](https://kpmg.com/xx/en/our-insights/ifrg/2024/ifrs-sme.html). Search returned titles only this run.
- **5b deferred tax:** already implemented, not hard-coded 0.0 (`financial_statements.py:640` `"deferred_tax": deferred_tax_expense`); `wear_and_tear_rate` column in `database.py` (~:568) with ALTER inside the migrations list (~:1534). No edits this run.
- Finance costs below EBIT, tax from profit_before_tax ✓. Income-tax-payable estimate must be netted against any future journalled provisional-tax payments (Medium, carried).

## 7. Tax updates (company + payroll)
- Tax year: 2026/2027 (1 Mar 2026 – 28 Feb 2027). `TAX_YEARS["2026/2027"]` present (`payroll.py:132`): 18% to R245,100 … 45% top; rebates R17,820 / R9,765 / R3,249; UIF ceiling R17,712. `_current_tax_year()` at `:170` selects by date. Provisional `"2027/2028"` (`:152`) to be replaced after Budget Feb 2027.
- Sources: [Accounter 2026/27 tables](https://accounter.co.za/news/sars-tax-tables-2026-2027), [GovChain PAYE 2026/27](https://www.govchain.co.za/blog/how-to-calculate-paye-in-south-africa), [TaxTim](https://www.taxtim.com/za/calc/payroll-tax/). Search returned titles only; no contradicting or mid-year changes surfaced; figures rest on prior source reads.
- UIF 1%+1%, SDL 1%, VAT 15%, CIT 27%: no changes found.
- **OPEN (High, EMP501 deadline 31 Oct 2026):** `payroll.py:1975` writes employee UIF under IRP5 code `4142` (SDL code); UIF = `4141`, SDL = `4142`. Validate `4005` (`:1977`) and `4474` (`:1979`) against SARS BRS list.

## 8. Action items
**Critical:** none.
**High**
1. `payroll.py:1975-1979` — UIF → 4141, SDL → 4142; validate 4005/4474 before 31 Oct 2026 EMP501 (13 days).
2. `payroll.py:1440-1472` — reverse/delete `"payroll"` journal entries on period delete; block when EMP201 submitted.
**Medium**
3. Confirm bank-import loop has no per-row commit (`companies.py` ~:1962).
4. Correct historic credit-note VAT lines posted to 2200 and historic entertainment VAT Input lines, or document cut-over.
5. Net AFS "Income Tax Payable (estimate)" against future provisional-tax journals.
6. Backfill NULL `paid_date`/`expense_date` for `management_accounts()`.
**Low**
7. Label VAT201 due-date rule; add VAT201 regression tests; explicit inventory_item_id on PO lines; consolidate `VAT_RATE`.
8. Confirm NBCPSS clause-8 bonus formula with the Council.
9. Confirm `reclass_expenses_2026-09-28.py` run on production; decide `zuzan.db` history purge; delete `zuzan.db.bak-20260928-184955`; clean untracked files; set `SECRET_KEY` in Render.

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS-for-SMEs 3rd ed./IFRS 18 checklist early 2027.
