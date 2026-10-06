# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 4 October 2026 (scheduled run, fired 06:31 UTC; scheduled for 3 Oct 22:18 UTC)
**Prior report:** 2026-10-02

**Change detection:** HEAD `ac4aa80` (was `d0d844c`). `git diff d0d844c HEAD` touches only `zuzan-backend/payroll.py` (+17/-6) and the prior audit report. The change adds `_not_example_emp()` (`payroll.py:192`) and applies it to the employee queries in `calculate_all` (~:749), `run_payroll` (~:870), `get_irp5` (~:1243), `get_easyfile_export` (~:1460), `dashboard` (~:1704) and `management_accounts` (~:2948), so the seeded `[zuzan-example]` employee (matched on `Employee.notes`, `database.py:191`) is excluded from payroll runs, EMP201/IRP5 and cost estimates. `py_compile` passes on `payroll.py`. All other backend files and `App_js_fixed.js` are unchanged. No code edits made this run. Line anchors in `payroll.py` below `:190` shifted by about +9 against earlier reports.

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | ✅ PASS |
| Debtors (AR) | ✅ PASS |
| Creditors (AP) | ✅ PASS — reversal-awareness intact |
| Cross-module | ✅ PASS — import-awareness intact |
| IFRS (AFS) | ✅ PASS — no standards change; deferred tax (5b) already implemented |
| Tax (SARS) | ✅ PASS — 2026/2027 tables present; no rate changes found |

**Overall: PASS.** No Critical/High/Medium findings. Carried Low item 1 (seeded example employee picked up by payroll) is now resolved.

## 2. Reports
✓ No issues found. `dashboard()` `payroll.py:1658`; `total_revenue = sum(_to_zar(i) for i in paid_invoices)` `:1670`; `total_outstanding` (`_to_zar`) `:1678`; `management_accounts()` `:2870`, outstanding `:2980` (`_to_zar`). The example-employee filter in the payroll-cost queries does not change totals for real employees. `/v1/summary` (main.py) unchanged.

## 3. Debtors
✓ No issues found. `debtors_aging()` `payroll.py:3263` unchanged (`_to_zar`, aged from `due_date`, paid excluded).

## 4. Creditors
✓ No issues found. `creditors_aging()` `payroll.py:3326` unchanged; `decrypt_field` on supplier bank details `:3404-3406`. Reversal-aware (`purchase_order` + `purchase_order_reversal`) lookups re-grepped at `payroll.py:2212, :2684, :3361`, `journal.py:1158`, `purchase_orders.py:445`.

## 5. Cross-module
✓ No issues found. `journal.py`, `csv_import.py`, `purchase_orders.py`, `database.py` unchanged, so journal coverage and import-awareness checks stand.

## 6. IFRS compliance (AFS)
- Framework: IFRS for SMEs (`financial_statements.py`, unchanged since 21 Jul). IFRS 18 and the IFRS for SMEs 3rd edition remain effective for periods beginning on/after 1 Jan 2027; no change since last audit. Transition plan stands.
- **5b deferred tax:** already computed. `_deferred_tax_balance()` `financial_statements.py:131`, opening/closing `:266-267`, expense `:268`; `FixedAsset.wear_and_tear_rate` `database.py:544`; migration inside list literal `database.py:1509`. No edits needed.
- Finance costs below EBIT / tax derived from profit_before_tax: unchanged.

## 7. Tax updates (company + payroll)
- Tax year: 2026/2027 (1 Mar 2026 – 28 Feb 2027). `TAX_YEARS["2026/2027"]` `payroll.py:132`; provisional `"2027/2028"` `:152`; `UIF_RATE=0.01` / `SDL_RATE=0.01` `:189-190`; `VAT_RATE=0.15` `:2042, :2436, :3518`; `CORP_TAX_RATE=0.27` `:3162`.
- Web search this run returned only aggregator pages for 2026/27 tables (no change signalled). The primary SARS/Treasury figures verified on 2 Oct are unchanged: CIT 27%, VAT 15%, primary rebate R17,820, UIF ceiling R17,712/month. No edits (report-only).
- Sources: [SARS Tax Tables 2026/27 (accounter.co.za)](https://accounter.co.za/news/sars-tax-tables-2026-2027), [payloop SARS tax tables](https://payloop.co.za/tax-tables), [sarstax.co.za brackets](https://sarstax.co.za/income-tax/brackets/), plus the SARS Budget 2026 FAQ and Treasury Tax Guide cited in the 2 Oct report.

## 8. Action items
No Critical / High / Medium items.
1. **Low (carried)** — confirm `reclass_expenses_2026-09-28.py` was run against production; decide on history purge of `zuzan.db` in origin; delete `zuzan.db.bak-20260928-184955`.
2. **Info (carried)** — `.git/index.lock` cannot be unlinked from the audit shell (delete-restricted); harmless.
3. **Resolved** — seeded example employee excluded from payroll/EMP201/IRP5/dashboard via `_not_example_emp()`. Suggest a regression test that a trial account's `run_payroll` ignores `[zuzan-example]`.

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS-for-SMEs 3rd edition / IFRS 18 checklist early 2027; ConCourt VAT s7(4) ruling pending; MIBCO Sector 5 Year 2 contributions TBC.

---
## Addendum — second scheduled run, 4 Oct 2026 ~22:20 UTC
**Change detection:** HEAD `f2f08d3` (was `ac4aa80`). Only `zuzan-backend/payroll.py` (+9/-4) changed. In `management_accounts()` the paid-invoice and expense period filters now use `COALESCE` (`_eff_paid` `payroll.py:2900`, `_eff_exp` `:2912`) so legacy rows with NULL `paid_date` / `expense_date` are still captured, matching the dashboard. `func` is imported (`:8`), `py_compile` passes, and revenue still sums only paid invoices via `_to_zar()` (`:2907`). Line anchors from the earlier report shift by about +5 after `:2895`; `debtors_aging` is now `:3268`, `creditors_aging` `:3331`, `CORP_TAX_RATE` `:3167`.

**Verdict: PASS (unchanged).** Reports, Debtors, Creditors, cross-module, IFRS (incl. 5b deferred tax, already implemented) and tax tables (`TAX_YEARS["2026/2027"]` `:132`) are unchanged. No edits made and no web re-check this run (same-day, no standards or rate changes since the earlier run). Action items are as in the report above; there are no new findings.
- **Low (note):** the COALESCE fallback to `created_at` can attribute a legacy paid invoice with NULL `paid_date` and `invoice_date` to its creation date, which is acceptable. Consider backfilling `paid_date` so the filter can use the index.
