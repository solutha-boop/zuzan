# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 15 October 2026 (scheduled run)
**Prior report:** 2026-10-14

**Change detection:** HEAD `d8431dd` (prior audit HEAD `c404f25`; 3 commits). Code diff since the prior audit is limited to `auth.py` (+14/-?), `main.py` (3 lines) and `purchase_orders.py:107` (supplier lookup scoped by `company_id`) — the same hardening reported as uncommitted on 14 Oct, now committed. `payroll.py`, `journal.py`, `financial_statements.py`, `csv_import.py`, `suppliers.py`, `companies.py`, `database.py` are unchanged. `py_compile` passes on all of them. No code edits made by this audit (5b already implemented). Line-level re-checks this run: `_to_zar` (`payroll.py:18`), `debtors_aging` (`:3688`), `creditors_aging` (`:3751`), reversal-aware lookups (`:2632, :3104, :3786`), `decrypt_field` (`:3829-3831`), deferred tax (`financial_statements.py:131, 266-268, 601-610, 681`), `TAX_YEARS` (`:132, :152`), `VAT_RATE=0.15` (`:2462, :2856, :3943`). No live DB re-queried.

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | PASS |
| Debtors (AR) | PASS |
| Creditors (AP) | PASS — reversal-awareness intact |
| Cross-module | PASS on code; payroll-delete journal orphaning still open |
| IFRS (AFS) | PASS — no standards change; deferred tax (5b) implemented |
| Tax (SARS) | PASS on rates/tables; EMP501 IRP5 code 4142 defect still open (deadline 31 Oct, 16 days) |

**Overall: PASS with two open defects (unchanged from 14 Oct).**

## 2. Reports
✓ No issues found. Code unchanged since 13 Oct.

## 3. Debtors
✓ No issues found. `debtors_aging` `payroll.py:3688` unchanged.

## 4. Creditors
✓ No issues found. `creditors_aging` `payroll.py:3751` unchanged; `purchase_orders.py:107` change only tightens tenant scoping.

## 5. Cross-module
- Latest journal integrity report on file: `journal_integrity_2026-10-12.md` (0 gaps). Import-awareness code unchanged.
- **OPEN (carried, High):** `payroll.py:1441-1472` `DELETE /payroll/payslips/{period}` deletes `Payslip` rows only; payroll journal entries (source `"payroll"`, `journal.py:601`, backfill `:1086`) are left orphaned, and re-running payroll creates duplicates. No EMP201-submitted guard.

## 6. IFRS compliance (AFS)
- Framework: IFRS for SMEs; `financial_statements.py` unchanged. IFRS 18 and IFRS for SMEs 3rd edition remain effective for periods beginning on/after 1 Jan 2027 (early application permitted); no change since prior audit. Transition plan `ifrs_smes_3rd_edition_transition_plan.md` stands.
- **5b deferred tax:** already implemented, verified (lines above); no edits.
- Finance costs below EBIT `:205-209`; tax from profit_before_tax ✓.

## 7. Tax updates (company + payroll)
- Tax year 2026/2027. `TAX_YEARS["2026/2027"]` present (`payroll.py:132`): brackets 18% to R245,100 … 45% above R1,878,600; rebates R17,820 / R9,765 / R3,249; UIF ceiling R17,712 — consistent with sources ([Accounter](https://accounter.co.za/news/sars-tax-tables-2026-2027), [GovChain](https://www.govchain.co.za/blog/how-to-calculate-paye-in-south-africa), [Treasury Budget 2026 Tax Guide](https://www.treasury.gov.za/documents/national%20budget/2026/sars/Budget%202026%20Tax%20guide.pdf)). Search surfaced no mid-year changes. Provisional `"2027/2028"` (`:152`) to be replaced after Budget Feb 2027.
- UIF 1%+1%, SDL 1%, VAT 15%, CIT 27%: no changes found.
- **OPEN (High, deadline 31 Oct 2026):** `payroll.py:1975` writes UIF under code `4142` (SDL code); UIF should be `4141`, SDL `4142`. Validate `4005` (`:1977`) and `4474` (`:1979`) against the SARS BRS code list. JSON mirrors at `:1700, :1714`.

## 8. Action items
**Critical:** none.
**High**
1. `payroll.py:1975-1979` — UIF → 4141, SDL → 4142; validate 4005/4474 before the 31 Oct 2026 EMP501 submission.
2. `payroll.py:1441-1472` — reverse/delete `"payroll"` journal entries when deleting a period; block when EMP201 submitted.
**Medium**
3. (carried) Backfill NULL `paid_date`/`expense_date` for `management_accounts()`.
**Low**
4. Confirm NBCPSS clause-8 bonus formula with the Council.
5. (carried) Confirm `reclass_expenses_2026-09-28.py` run on production; decide `zuzan.db` history purge; delete `zuzan.db.bak-20260928-184955`.
6. (carried, Info) Clean untracked `zuzan-backend/_to_delete/`, `commit_and_push.ps1`, `find_default_password_accounts.py`; set `SECRET_KEY` in Render.

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS-for-SMEs 3rd ed./IFRS 18 checklist early 2027.
