# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 14 October 2026 (scheduled run)
**Prior report:** 2026-10-13

**Change detection:** HEAD `c404f25` (prior audit HEAD `4f228ba`; 1 commit, a report-only commit). Uncommitted working-tree changes in `auth.py` (empty-password guard, min 8-char register, reset-password rate limit, SECRET_KEY warning), `main.py` (`_check_admin` constant-time compare) and `purchase_orders.py:107` (supplier lookup now scoped by `company_id`). None affect Reports/AR/AP/journal/AFS logic. `py_compile` passes on payroll, journal, financial_statements, database, purchase_orders, main, companies, csv_import, suppliers. `journal.py`, `financial_statements.py`, `suppliers.py` unchanged. No code edits made by this audit. No live DB re-queried (local zuzan.db unchanged since 28 Sep).

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | PASS |
| Debtors (AR) | PASS |
| Creditors (AP) | PASS — reversal-awareness intact |
| Cross-module | PASS on code; **new finding: DELETE payroll period leaves orphan journal entries** |
| IFRS (AFS) | PASS — no standards change; deferred tax (5b) already implemented |
| Tax (SARS) | PASS on rates/tables; **EMP501 IRP5 code 4142 defect still open (deadline 31 Oct)** |

**Overall: PASS with two open defects (EMP501 codes; payroll-delete journal orphaning).**

## 2. Reports
✓ No issues found. `_to_zar()` `payroll.py:18`; reports code unchanged from 13 Oct (same function set as prior report). `purchase_order` + `purchase_order_reversal` lookups present at `payroll.py:2632, :3104, :3786`. Tax provision 27% unchanged.

## 3. Debtors
✓ No issues found. `debtors_aging` `payroll.py:3688` unchanged (due_date-based ageing, `_to_zar`, paid excluded).

## 4. Creditors
✓ No issues found. `creditors_aging` `payroll.py:3751`; reversal-aware lookups `payroll.py:3786`, `journal.py`, `purchase_orders.py`; supplier bank fields decrypted via `decrypt_field` `payroll.py:3829-3831`. `purchase_orders.py:107` change only tightens tenant scoping (improvement).

## 5. Cross-module
- Latest journal integrity report `journal_integrity_2026-10-12.md`: 0 gaps. Import-awareness code (`csv_import.py`, `journal.py`) unchanged since prior audit.
- **NEW (Medium → High if used in production): `payroll.py:1441-1472` `DELETE /payroll/payslips/{period}`** deletes `Payslip` rows only. Payroll journal entries are posted with source `"payroll"` keyed by payslip id (`journal.py:601`, backfill `journal.py:1086`). Deleting a period therefore leaves orphaned payroll postings (salary expense/PAYE/UIF/SDL liabilities, overstating expenses and liabilities), and re-running payroll creates new payslip ids → duplicate postings. Endpoint also does no journal reversal and no check for already-submitted EMP201 periods.

## 6. IFRS compliance (AFS)
- Framework: IFRS for SMEs (`financial_statements.py` unchanged since 21 Jul). Standards unchanged since prior audit: IFRS 18 and IFRS for SMEs 3rd edition both effective for annual periods beginning on/after 1 Jan 2027 (early application permitted). Transition plan `audit_reports/ifrs_smes_3rd_edition_transition_plan.md` stands. Sources: [Forvis Mazars SA](https://www.forvismazars.com/za/en/services/audit-assurance/financial-reporting/ifrs-for-smes-R-accounting-standard), [Accounting Academy](https://www.accountingacademy.co.za/news/read/updated-ifrs-for-smes-3rd-edition), [IFRS Foundation overview](https://ifrs.org/content/dam/ifrs/supporting-implementation/smes/2025-webcasts/overview-third-edition-ifrs-for-smes.pdf).
- **5b deferred tax:** already implemented (no hard-coded 0.0) — `_deferred_tax_balance` `financial_statements.py:131`, opening/closing movement `:266-268`, `total_tax` incl. deferred `:601`, Note 9 `deferred_tax` `:606`, closing balance `:610`, equity adjustment `:681`. Verified; no edits.
- Finance costs (6700 or name-matched) presented below EBIT `:205-209`; tax derives from profit_before_tax ✓.

## 7. Tax updates (company + payroll)
- Tax year: 2026/2027 (1 Mar 2026 – 28 Feb 2027). `TAX_YEARS["2026/2027"]` `payroll.py:132` present (18% to R245,100 … 45% top; rebates R17,820/R9,765/R3,249; UIF ceiling R17,712) — unchanged; web search returned no contradicting changes ([Accounter 2026/27 tables](https://accounter.co.za/news/sars-tax-tables-2026-2027), [GovChain PAYE guide](https://www.govchain.co.za/blog/how-to-calculate-paye-in-south-africa)). Provisional `"2027/2028"` entry `:152` still to be replaced after Budget Feb 2027. `_current_tax_year()` `:170`.
- UIF 1%+1%, SDL 1% (R500k threshold), VAT 15% (`:2462, :2856, :3943`), CIT 27%: no announced changes found.
- **OPEN (High, deadline 31 Oct 2026) — `payroll.py:1975` EMP501 export** writes employee UIF under IRP5 code `4142` (SDL code); UIF should be `4141`, SDL `4142`. `4474` (`:1979`) and `4005` (`:1977`) should be validated against the SARS BRS code list. JSON summary mirrors at `:1700, :1714`. Unchanged since 13 Oct.

## 8. Action items
**Critical:** none.
**High**
1. `payroll.py:1975-1979` — emit UIF as 4141 and SDL as 4142; validate 4005/4474 vs SARS BRS before the 31 Oct 2026 interim EMP501 submission.
2. `payroll.py:1441-1472` — DELETE payroll period must also reverse/delete journal entries with source `"payroll"` for the deleted payslip ids (and block deletion when the period's EMP201 is submitted). Until fixed, avoid using it on production periods or run journal cleanup manually.
**Medium**
3. (carried) Backfill NULL `paid_date`/`expense_date` for `management_accounts()`.
**Low**
4. Confirm NBCPSS clause-8 bonus formula with the Council.
5. (carried) Confirm `reclass_expenses_2026-09-28.py` run on production; decide `zuzan.db` history purge; delete `zuzan.db.bak-20260928-184955`.
6. (carried, Info) Clean untracked `zuzan-backend/_to_delete/`, `commit_and_push.ps1`; commit the pending auth/main/purchase_orders hardening changes (set `SECRET_KEY` in Render).

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS-for-SMEs 3rd ed./IFRS 18 checklist early 2027.
