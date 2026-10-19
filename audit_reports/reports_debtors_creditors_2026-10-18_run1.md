# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 18 October 2026 (scheduled run; originally due 17 Oct 22:08 UTC)
**Prior report:** 2026-10-16

**Change detection:** HEAD `c7a61af` (17 Oct 08:13; 12 commits since the prior audited HEAD `d8431dd`, the last ones being "payroll table shows actuals"). Working tree clean apart from untracked `commit_and_push.ps1`, `_to_delete/`, `find_default_password_accounts.py`, `fix_credit_note_vat_account.py`. `py_compile` passes on all backend files. The uncommitted changes noted on 16 Oct are now committed. This audit made no code edits (5b already implemented). Local `zuzan.db` not re-queried (unchanged since 28 Sep).

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | PASS |
| Debtors (AR) | PASS |
| Creditors (AP) | PASS — reversal-awareness intact |
| Cross-module | PASS on code; payroll-delete journal orphaning still open |
| IFRS (AFS) | PASS — no standards change; deferred tax (5b) verified; AFS cash-flow improvements reviewed |
| Tax (SARS) | PASS on rates/tables; EMP501 IRP5 code defect still open (deadline 31 Oct, 13 days) |

**Overall: PASS with two open High defects (unchanged, now closer to the EMP501 deadline).**

## 2. Reports
✓ No issues found. `_to_zar` (`payroll.py:18`) is used for dashboard revenue/outstanding (`:2090`, `:2098`), management trend (`:3422`), and `/v1/summary` (`main.py:513`, `:543`). Revenue sums paid invoices only; outstanding covers pending/overdue(+sent); expenses are not in revenue.
Changes since last audit (reviewed, no defects):
- Invoice status filters now include `written_off` for VAT/revenue-recognition sets (`payroll.py:2149, 2503, 2864`, `financial_statements.py` ~:502). Revenue paid-only totals unchanged.
- VAT201 (`payroll.py` ~3943-4200): bi-monthly `months` param, exempt supplies, credit-note output adjustment, bad-debt VAT (s22), s7 asset-disposal output VAT, BGR 16 input apportionment. Logic reviewed, consistent with ledger sources.
- **Low:** `_vat_due_date` (`payroll.py:~3928`) now uses the 25th (previous business day if weekend/holiday). The 16 Oct report described a last-business-day rule for eFiling; the code was changed back to the 25th. SARS: eFiling submissions are due the last business day of the month, manual the 25th — confirm which is intended and label accordingly.
- **Low:** Add regression tests for VAT201 with credit notes, bank-import income, bad debts and apportionment (none seen).

## 3. Debtors
✓ No issues found. `debtors_aging` `payroll.py:3688`: due_date ageing, `_to_zar` at `:3710`, paid excluded; written-off excluded from outstanding.

## 4. Creditors
✓ No issues found. `creditors_aging` `payroll.py:3751`; reversal-aware lookups (source `purchase_order` + `purchase_order_reversal`, credit − debit) at `payroll.py:2632, 3104, 3786`, `purchase_orders.py:475`, `journal.py:1291`; `decrypt_field` on bank fields `payroll.py:3829-3831`.
New since last audit: `receive_po` (`purchase_orders.py:~309-390`) routes lines matching an inventory SKU/name to Inventory (1200) and updates weighted-average cost; cost reaches COGS on sale, so no double counting with expenses. Supplier ownership check added on update. PO VAT now respects company VAT registration.
- **Low:** matching by exact description==SKU/name is brittle (a typo silently expenses the line instead of stocking it). Consider an explicit inventory_item_id on PO lines.

## 5. Cross-module
- Latest journal integrity report: `journal_integrity_2026-10-12.md` (0 gaps); no newer report in the folder. Journal sources covered: invoices, payments, expenses, PO receipts/payments, payroll (`journal.py:690, 1211`).
- Import-awareness unchanged and intact: auto-backfill after import (`csv_import.py:125, 502`), Rules 6/7 exclude `source="import"` on 1100/2000 (`payroll.py:2590, 2666`), 3998/3999 handled (`csv_import.py:727, 926`; `payroll.py:2381`), unbalanced journal groups rejected (`csv_import.py:1036-1065`), non-ZAR invoice imports require an exchange rate (`csv_import.py:459-473`).
- **OPEN (carried, High):** `payroll.py:1440-1472` `DELETE /payslips/{period}` still deletes `Payslip` rows only; payroll journal entries (source `"payroll"`) are orphaned and a re-run duplicates them. No EMP201-submitted guard.
- Carried caveat: confirm no per-row commit in the bank-import loop (`companies.py:~1962`) so the fail-loud rollback is accurate.

## 6. IFRS compliance (AFS)
- Framework: IFRS for SMEs. IFRS 18 and IFRS for SMEs 3rd edition remain effective for annual periods beginning on/after 1 Jan 2027 (early application permitted); no change found. Transition plan `ifrs_smes_3rd_edition_transition_plan.md` stands. Sources: [Accounting Academy](https://www.accountingacademy.co.za/news/read/updated-ifrs-for-smes-3rd-edition), [Forvis Mazars SA](https://www.forvismazars.com/za/en/services/audit-assurance/financial-reporting/ifrs-for-smes-R-accounting-standard), [IFRS Foundation overview](https://ifrs.org/content/dam/ifrs/supporting-implementation/smes/2025-webcasts/overview-third-edition-ifrs-for-smes.pdf). Search returned titles only this run.
- **5b deferred tax:** already implemented; verified. `"deferred_tax"` is computed (`financial_statements.py:640`, no longer hard-coded 0.0); `wear_and_tear_rate` column in `database.py:568` with ALTER in the migrations list (`:1534`). No edits.
- `financial_statements.py` changed since 16 Oct (reviewed, improvements): opening balances use strictly-before-year-start (`before_start`); current-year income tax carried as computed liability "2400 Income Tax Payable (estimate)" with matching retained-earnings reduction (balance sheet still balances); cash flow now includes other working-capital movements, disposal gain/loss removal, investing "other" and financing (contributions/drawings/long-term liabilities); output adds `ledger_closing_cash` and `reconciles_to_ledger`.
- **Medium:** The income-tax-payable estimate is presented even if tax was actually paid via provisional payments that are journalled (no tax payments journalled today, so net is consistent) — if provisional-tax payments are ever journalled, the estimate must be netted against them or the liability will double-count.
- Finance costs below EBIT, tax derived from profit_before_tax: ✓.

## 7. Tax updates (company + payroll)
- Tax year: 2026/2027 (1 Mar 2026 – 28 Feb 2027). `TAX_YEARS["2026/2027"]` present (`payroll.py:132`): 18% to R245,100 … 45% above R1,878,600; rebates R17,820 / R9,765 / R3,249; UIF ceiling R17,712. Selector `_current_tax_year()` (`:170`) derives year from the date. Provisional `"2027/2028"` (`:152`) flagged — replace after Budget Feb 2027.
- Sources: [Accounter 2026/27 tables](https://accounter.co.za/news/sars-tax-tables-2026-2027), [Xero SA tax tables](https://www.xero.com/za/guides/sars-tax-tables-2026/), [SARS Guide for Employers 2027](https://www.sars.gov.za/guide-for-employers-in-respect-of-employees-tax-2027/), [Grant Thornton Budget 2026](https://www.grantthornton.co.za/contentassets/334ab82b24354cfa91de433a7de8ed56/2026-budget-analysis-and-commentary_fa.pdf). Search surfaced titles only; no contradicting changes seen; figures rest on prior source reads.
- UIF 1%+1%, SDL 1%, VAT 15% (`VAT_RATE` at `payroll.py:2462, 2856, 3958`), CIT 27%: no changes found.
- **OPEN (High, EMP501 deadline 31 Oct 2026):** `payroll.py:1975` writes employee UIF under IRP5 code `4142` (SDL code). UIF = `4141`, SDL = `4142`. Also validate `4005` (`:1977`) and `4474` (`:1979`) against the SARS BRS code list. JSON mirrors ~`:1700, :1714`.
- **Low:** `VAT_RATE = 0.15` is redefined locally in three functions; consolidate to the module constant.

## 8. Action items
**Critical:** none.
**High**
1. `payroll.py:1975-1979` — UIF → 4141, SDL → 4142; validate 4005/4474 before the 31 Oct 2026 EMP501 submission (13 days).
2. `payroll.py:1440-1472` — reverse/delete `"payroll"` journal entries when deleting a period; block when EMP201 submitted.
**Medium**
3. Confirm bank-import loop has no per-row commit (`companies.py:~1962`).
4. Correct historic credit-note VAT lines posted to 2200 and historic entertainment-expense VAT Input lines, or document the cut-over.
5. AFS "Income Tax Payable (estimate)" must be netted against any future journalled provisional-tax payments.
6. (carried) Backfill NULL `paid_date`/`expense_date` for `management_accounts()`.
**Low**
7. Clarify VAT201 due-date rule (25th vs eFiling last business day) and label it.
8. Add VAT201 regression tests; explicit inventory_item_id on PO lines; consolidate `VAT_RATE`.
9. Confirm NBCPSS clause-8 bonus formula with the Council.
10. (carried) Confirm `reclass_expenses_2026-09-28.py` run on production; decide `zuzan.db` history purge; delete `zuzan.db.bak-20260928-184955`; clean untracked files; set `SECRET_KEY` in Render.

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS-for-SMEs 3rd ed./IFRS 18 checklist early 2027.
