# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 7 October 2026 (scheduled run)
**Prior report:** 2026-10-06

**Change detection:** HEAD `b125db4` (was `9629530`). Commits since last report: dual pay-schedule tabs (Security Officers / Salaried Staff) — `payroll.py` `RunPayrollRequest.pay_schedule` + filtered employee query in `run_payroll` (`:756, :885-905`); `Employee.pay_schedule` column + startup backfill (`database.py:202, :1681-1685`); `companies.py` `_employee_dict` heuristic; `main.py:863-882` admin clear-payroll endpoint (deletes payslips/leave, clears `source="payroll"` journal entries via `_clear_journal_for_sources`); frontend `App_js_fixed.js` / `zuzan-app/src/App.js`. The diff did NOT touch `_to_zar`, `dashboard()`, `management_accounts()`, `debtors_aging()`, `creditors_aging()`, `TAX_YEARS`, `VAT_RATE`, `CORP_TAX_RATE`, `journal.py`, `purchase_orders.py`, `csv_import.py` or `financial_statements.py`. `py_compile` passes on payroll, financial_statements, database, journal, purchase_orders, main, companies, csv_import. No code edits made this run.

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | ✅ PASS |
| Debtors (AR) | ✅ PASS |
| Creditors (AP) | ✅ PASS — reversal-awareness intact |
| Cross-module | ✅ PASS (one Info item re payroll clear endpoint) |
| IFRS (AFS) | ✅ PASS — no standards change; deferred tax (5b) already implemented |
| Tax (SARS) | ✅ PASS — 2026/2027 table present; no rate changes found |

**Overall: PASS.** No Critical/High/Medium findings.

## 2. Reports
✓ No issues found. `_to_zar()` `payroll.py:18`; `dashboard()` `:1688`; `management_accounts()` `:2900`; `/v1/summary` `main.py:469-503` imports and applies `_to_zar` (revenue `:473`, outstanding `:503`). Functions unchanged by this week's commits.
Info: payroll runs can now be executed per pay schedule (two runs per period). Dashboard payroll cost sums actual payslips, so it is unaffected, but confirm both schedules' runs for the same period are both counted (no per-period de-duplication assumed).

## 3. Debtors
✓ No issues found. `debtors_aging()` `payroll.py:3298` unchanged: sent/overdue invoices, `_to_zar`, aged from `due_date`, paid excluded.

## 4. Creditors
✓ No issues found. `creditors_aging()` `payroll.py:3361` unchanged; supplier bank fields decrypted via `decrypt_field` (`suppliers.py:48-50`, `payroll.py:3371`). Reversal-aware lookups (`purchase_order` + `purchase_order_reversal`) re-grepped: `payroll.py:2242, :2714, :3396`, `journal.py:1158`, `purchase_orders.py:445`.

## 5. Cross-module
✓ No issues found. `journal.py`, `csv_import.py`, `purchase_orders.py` unchanged; import-awareness intact.
Info (new): `main.py:863-882` admin clear-payroll endpoint removes payroll journal entries together with payslips, so the ledger stays consistent; ensure it stays admin-only and that re-running payroll re-posts journals (covered by `test_payroll_journal_balance.py`).

## 6. IFRS compliance (AFS)
- Framework: IFRS for SMEs (`financial_statements.py:2, :623, :717`), unchanged. IFRS 18 and IFRS for SMEs 3rd edition remain effective for periods beginning on/after 1 Jan 2027; searches this run found no change. Transition plan `ifrs_smes_3rd_edition_transition_plan.md` stands.
- **5b deferred tax:** already computed (no `"deferred_tax": 0.0` hard-code). `_deferred_tax_balance()` `financial_statements.py:131`; Note 9 `deferred_tax` `:606`; `FixedAsset.wear_and_tear_rate` `database.py:544`. No edits needed. File unchanged since 21 Jul.
- Finance costs below EBIT / tax from profit_before_tax: unchanged.
- Sources: [Accounting Academy SA](https://www.accountingacademy.co.za/news/read/updated-ifrs-for-smes-3rd-edition), [Forvis Mazars SA](https://www.forvismazars.com/za/en/services/audit-assurance/financial-reporting/ifrs-for-smes-R-accounting-standard), [ACCA](https://www.accaglobal.com/learning-and-events/corporate-reporting/third-edition-ifrs-for-smes).

## 7. Tax updates (company + payroll)
- Tax year: 2026/2027 (1 Mar 2026 – 28 Feb 2027). `TAX_YEARS["2026/2027"]` `payroll.py:132` (brackets to 45% above R1,878,600; primary R17,820, secondary R9,765, tertiary R3,249; UIF ceiling R17,712); provisional `"2027/2028"` `:152`; `VAT_RATE=0.15` (`:2072, :2466, :3553`); `CORP_TAX_RATE=0.27` `:3197`.
- Web search returned the same sources as prior runs (SARS Guide for Employers 2027, tax tables) with no signal of a rate change. Report-only; no edits.
- Sources: [SARS Guide for Employers 2027](https://www.sars.gov.za/guide-for-employers-in-respect-of-employees-tax-2027/), [Xero SA tax tables 2026](https://www.xero.com/za/guides/sars-tax-tables-2026/), [Accounter SARS tax tables](https://accounter.co.za/news/sars-tax-tables-2026-2027).

## 8. Action items
No Critical / High / Medium items.
1. **Low (carried)** — confirm `reclass_expenses_2026-09-28.py` was run on production; decide on history purge of `zuzan.db` in origin; delete `zuzan.db.bak-20260928-184955`.
2. **Low (carried)** — backfill NULL `paid_date`/`expense_date` for index use in `management_accounts()`.
3. **Info (carried)** — untracked `zuzan-backend/_to_delete/` awaits cleanup.
4. **Info** — verify split-schedule payroll runs (security vs salaried) both post journals and both feed dashboard payroll cost for the same period.

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS-for-SMEs 3rd edition / IFRS 18 checklist early 2027; ConCourt VAT s7(4) ruling pending.
