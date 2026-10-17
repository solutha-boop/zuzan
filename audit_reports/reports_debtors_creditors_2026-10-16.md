# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 16 October 2026 (scheduled run)
**Prior report:** 2026-10-15

**Change detection:** HEAD `d8431dd` (unchanged). Four files modified in the working tree (uncommitted, edited 16 Oct 21:22): `payroll.py`, `journal.py`, `companies.py`, `credit_notes.py`. `py_compile` passes on all audited backend files. No code edits made by this audit (5b already implemented). Local `zuzan.db` not re-queried (unchanged since 28 Sep).

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | PASS (VAT201 changes reviewed, see §2) |
| Debtors (AR) | PASS |
| Creditors (AP) | PASS — reversal-awareness intact |
| Cross-module | PASS on code; payroll-delete journal orphaning still open |
| IFRS (AFS) | PASS — no standards change; deferred tax (5b) implemented |
| Tax (SARS) | PASS on rates/tables; EMP501 IRP5 code 4142 defect still open (deadline 31 Oct, 15 days) |

**Overall: PASS with two open High defects (unchanged) and uncommitted improvements to commit/test.**

## 2. Reports
✓ No issues found in `/reports/dashboard`, `/reports/management`, `/v1/summary` (`_to_zar` at `payroll.py:18`; unchanged).
Uncommitted VAT201 changes reviewed (all improvements, no defects found):
- `payroll.py:3928` `_vat_due_date` — due date now last business day of the month after the period (was the 25th of the month after next). Uses `clocking._sa_holidays`; imports `_date`, `_calendar`, `timedelta` present (`:11-12`). Note: the 25th applies to manual/non-eFiling submissions; eFiling rule is the one implemented.
- `payroll.py:~4019-4054` output tax now deducts credit-note VAT and adds bank-import income VAT (source `bank_import_income`, account 2100) so VAT201 agrees with the ledger.
- `payroll.py:~4062-4081` input VAT taken per expense (NULL → 15/115 estimate; stored 0 → no claim); entertainment excluded (`journal.vat_not_claimable`, VAT Act s17(2)). Removes the previous invented claim.
- Recommend adding a regression test for VAT201 with credit notes / bank-import income before committing.

## 3. Debtors
✓ No issues found. `debtors_aging` `payroll.py:3688` unchanged (due_date ageing, `_to_zar`, paid excluded).
Related: `credit_notes.py:84-91` — default VAT now follows the linked invoice (0% if it had no VAT); `:192` credit-note VAT now debits account 2100 (VAT Output) instead of 2200 (PAYE Payable) — fixes a real mis-posting. Historic credit notes with VAT posted to 2200 are not corrected by this change (see Action 4).

## 4. Creditors
✓ No issues found. `creditors_aging` `payroll.py:3751`; reversal-aware lookups at `payroll.py:2632, 3104, 3786` (source `purchase_order` + `purchase_order_reversal`, credit − debit); `decrypt_field` on bank fields `payroll.py:3829-3831`.

## 5. Cross-module
- Latest journal integrity report: `journal_integrity_2026-10-12.md` (0 gaps). Import-awareness code (`csv_import.py`, `journal.py` rules 6/7, 3998/3999, unbalanced-group rejection, FX-rate requirement) unchanged.
- `journal.py:430-450` `post_expense` now treats entertainment VAT as cost (consistent with VAT201). Expenses already posted before this change keep their VAT Input lines → minor ledger/VAT201 mismatch for historic entertainment expenses.
- `companies.py:1962-1967` and `credit_notes.py:123-128` now fail loudly (rollback + HTTP 500) when the journal post fails instead of saving without a journal entry — closes a journal-coverage gap. Caveat: in the bank-import loop, `db.rollback()` only discards uncommitted work; confirm the loop does not commit per row, otherwise "nothing saved" is inaccurate.
- **OPEN (carried, High):** `payroll.py:1440` `DELETE /payroll/payslips/{period}` still deletes `Payslip` rows only; payroll journal entries (source `"payroll"`, `journal.py:601`, backfill `:1086`) are orphaned; re-run duplicates. No EMP201-submitted guard.

## 6. IFRS compliance (AFS)
- Framework: IFRS for SMEs; `financial_statements.py` unchanged since 21 Jul. IFRS 18 and IFRS for SMEs 3rd edition remain effective for annual periods beginning on/after 1 Jan 2027 (early application permitted); no change since prior audit. Transition plan `ifrs_smes_3rd_edition_transition_plan.md` stands. Sources: [Forvis Mazars SA](https://www.forvismazars.com/za/en/services/audit-assurance/financial-reporting/ifrs-for-smes-R-accounting-standard), [Accounting Academy](https://www.accountingacademy.co.za/news/read/updated-ifrs-for-smes-3rd-edition), [IFRS Foundation overview](https://ifrs.org/content/dam/ifrs/supporting-implementation/smes/2025-webcasts/overview-third-edition-ifrs-for-smes.pdf).
- **5b deferred tax:** already implemented, verified — `_deferred_tax_balance` `financial_statements.py:131`, opening/closing movement `:266-268`, `total_tax` incl. deferred `:601`, Note 9 `deferred_tax` `:606`, closing balance `:610`, equity adjustment `:681`; `wear_and_tear_rate` used at `:109`. No edits.
- Finance costs below EBIT `:205-209`; tax from profit_before_tax ✓.

## 7. Tax updates (company + payroll)
- Tax year 2026/2027 (1 Mar 2026 – 28 Feb 2027). `TAX_YEARS["2026/2027"]` present (`payroll.py:132`): 18% to R245,100 … 45% top; rebates R17,820 / R9,765 / R3,249; UIF ceiling R17,712. Web search surfaced no contradicting or mid-year changes ([Accounter](https://accounter.co.za/news/sars-tax-tables-2026-2027), [Treasury Budget 2026 Tax Guide](https://www.treasury.gov.za/documents/national%20budget/2026/sars/Budget%202026%20Tax%20guide.pdf), [Xero SA tax tables](https://www.xero.com/za/guides/sars-tax-tables-2026/)). Search results returned titles only this run, so figures rest on the prior runs' source reads. Provisional `"2027/2028"` (`:152`) to be replaced after Budget Feb 2027. `_current_tax_year()` `:170`.
- UIF 1%+1%, SDL 1%, VAT 15% (`VAT_RATE`; `credit_notes.py` default 0.15), CIT 27%: no announced changes found.
- **OPEN (High, deadline 31 Oct 2026):** `payroll.py:1975` writes employee UIF under IRP5 code `4142` (SDL code); UIF should be `4141`, SDL `4142`. Validate `4005` (`:1977`) and `4474` (`:1979`) vs the SARS BRS code list. JSON mirrors `:1700, :1714`.

## 8. Action items
**Critical:** none.
**High**
1. `payroll.py:1975-1979` — UIF → 4141, SDL → 4142; validate 4005/4474 before the 31 Oct 2026 EMP501 submission.
2. `payroll.py:1440-1472` — reverse/delete `"payroll"` journal entries when deleting a period; block when EMP201 submitted.
**Medium**
3. Commit and test today's uncommitted changes (VAT201, credit-note VAT, journal fail-loud); confirm bank-import loop has no per-row commit (`companies.py:1962`).
4. Correct historic credit-note VAT lines posted to 2200 (PAYE Payable) and historic entertainment-expense VAT Input lines, or document the cut-over.
5. (carried) Backfill NULL `paid_date`/`expense_date` for `management_accounts()`.
**Low**
6. Confirm NBCPSS clause-8 bonus formula with the Council.
7. (carried) Confirm `reclass_expenses_2026-09-28.py` run on production; decide `zuzan.db` history purge; delete `zuzan.db.bak-20260928-184955`.
8. (carried, Info) Clean untracked `zuzan-backend/_to_delete/`, `commit_and_push.ps1`, `find_default_password_accounts.py`; set `SECRET_KEY` in Render.

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS-for-SMEs 3rd ed./IFRS 18 checklist early 2027.
