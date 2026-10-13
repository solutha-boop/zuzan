# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 12 October 2026 (scheduled run)
**Prior report:** 2026-10-11

**Change detection:** HEAD `5f21fa9` (prior audit HEAD `b933dbc`). Changed since: `payroll.py` (+67: casual schedule, NBCPSS medical double-deduction fix, payslip logo/total_deductions, interim EMP501 + code 4142), `companies.py` (terminate_employee date validation), `database.py` (+2 kiosk_token columns), `clocking.py`, frontend. `py_compile` passes on payroll, journal, financial_statements, database, purchase_orders, main, companies, csv_import, suppliers. Reports/AR/AP/AFS/journal/import code paths unchanged. Spot-checks re-run (see below). No code edits made by this audit. Line numbers in payroll.py have shifted ~+20 vs. prior report.

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | PASS |
| Debtors (AR) | PASS |
| Creditors (AP) | PASS — reversal-awareness intact |
| Cross-module | PASS (journal.py/csv_import.py unchanged; journal_integrity_2026-10-12 = 0 gaps) |
| IFRS (AFS) | PASS — no standards change; deferred tax (5b) already implemented |
| Tax (SARS) | PASS on rates/tables; **1 new Medium: EMP501 IRP5 code 4142 mapping** |

**Overall: PASS with one new Medium finding (EMP501 export code).**

## 2. Reports
✓ No issues found. `_to_zar()` `payroll.py:18`; used for dashboard revenue/outstanding (`:1947, :1955`), management accounts (`:3184, :3262, :3279` trend loop), debtors (`:3567`). `/v1/summary` in main.py unchanged. Normalised payroll cost change (`effective_gross` for the journal) does not touch dashboard expense totals.

## 3. Debtors
✓ No issues found. `debtors_aging` `payroll.py:3545`: filters sent+overdue (pending is not a distinct state in this path — unchanged from prior passing audits), ages from `due_date`, ZAR via `_to_zar` (`:3567`), paid excluded.

## 4. Creditors
✓ No issues found. `creditors_aging` `payroll.py:3608`. Reversal-aware lookups (`purchase_order` + `purchase_order_reversal`): `payroll.py:2489, :2961, :3643`, `journal.py:1166`, `purchase_orders.py:445`. Supplier bank details decrypted with `decrypt_field` `payroll.py:3686-3688`.

## 5. Cross-module
✓ No issues found. `journal_integrity_2026-10-12.md`: 0 gaps (invoice, invoice_payment, expense, PO receipt, PO payment). Payroll journal now posts `effective_gross` (actual hours × rate) keeping hourly/casual runs balanced. Import-awareness items (backfill after import, Rule 6/7 `source="import"` exclusion, 3998/3999 on balance sheet, unbalanced journal-group rejection, non-ZAR exchange-rate requirement) — `csv_import.py`/`journal.py` unchanged since last verified run.

## 6. IFRS compliance (AFS)
- Framework: IFRS for SMEs (`financial_statements.py:2, :623, :717`). No change: IFRS 18 and IFRS for SMEs 3rd edition both apply to periods beginning on/after 1 Jan 2027 (earlier application permitted). Transition plan `audit_reports/ifrs_smes_3rd_edition_transition_plan.md` stands. Sources consulted: [Forvis Mazars SA – IFRS for SMEs new edition](https://www.forvismazars.com/za/en/services/audit-assurance/financial-reporting/ifrs-for-smes-R-accounting-standard), [Accounting Academy – IFRS for SMEs 3rd ed.](https://www.accountingacademy.co.za/news/read/updated-ifrs-for-smes-3rd-edition).
- **5b deferred tax:** already implemented (not hard-coded 0.0): `wear_and_tear_rate` column `database.py:554` with migration inside the list `:1519`; rate resolution `financial_statements.py:107-110`; `deferred_tax` in Note 9 `:606`; expense = closing − opening; `total_tax` includes deferred. Verified; no edits.
- Finance costs below EBIT; tax from profit_before_tax: unchanged ✓.

## 7. Tax updates (company + payroll)
- Tax year: 2026/2027 (1 Mar 2026 – 28 Feb 2027). `TAX_YEARS["2026/2027"]` (`payroll.py:~132`): brackets 18% to R245,100 … 45% > R1,878,600; primary R17,820, secondary R9,765, tertiary R3,249; UIF ceiling R17,712 — match SARS/Budget 2026. Provisional `"2027/2028"` flagged. `_current_tax_year()` selects by date.
- UIF/SDL 1% (`:189-190`), VAT 15% (`:2319, :2713, :3800`), CIT 27% (`:3444`): no announced changes found this run (search results: [SARS Guide for Employers 2027](https://www.sars.gov.za/guide-for-employers-in-respect-of-employees-tax-2027/), [Budget 2026 Tax Guide](https://www.treasury.gov.za/documents/national%20budget/2026/sars/Budget%202026%20Tax%20guide.pdf)).
- **NEW (Medium) — `payroll.py:1831-1832` interim EMP501 export:** emits employee UIF as IRP5 code `4142`. To my knowledge SARS code 4141 = UIF contribution (employee + employer combined) and 4142 = SDL contribution; 4149 = total PAYE+SDL+UIF. Using 4142 for employee UIF would likely mis-state SDL/UIF on the certificate and fail reconciliation in e@syFile. Also SDL is emitted as `4474` (`:1834`) and "pension/provident" as `4005` (`:1833`) — verify all three against the current SARS IRP5/IT3(a) BRS code list before the end-October interim EMP501 submission. The `total_all_amounts` control total (`:1843`) now includes UIF accordingly. I could not fetch the BRS to confirm in this run — treat as "verify", not confirmed defect.
- Interim period logic (Mar–Aug, recon end `{ty-1}08`, 6 months) is consistent with SARS interim reconciliation (due 31 Oct).

## 8. Action items
**Critical / High:** none.
**Medium**
1. `payroll.py:1831-1834` — verify/correct IRP5 codes in EMP501 export (UIF → 4141 employee+employer; SDL → 4142; check 4005/4474) before the 31 Oct 2026 interim EMP501 submission.
**Low**
2. Confirm NBCPSS clause-8 bonus formula with the Council.
3. (carried) Confirm `reclass_expenses_2026-09-28.py` run on production; decide `zuzan.db` history purge; delete `zuzan.db.bak-20260928-184955`.
4. (carried) Backfill NULL `paid_date`/`expense_date` for `management_accounts()`.
5. (carried, Info) Clean untracked `zuzan-backend/_to_delete/`; verify split-schedule payroll runs post journals and feed dashboard payroll cost.
6. **RESOLVED:** `terminate_employee` date validation now happens before mutation (`companies.py`, returns 400).

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS-for-SMEs 3rd ed./IFRS 18 checklist early 2027; PSSPF rate-reduction watch.
