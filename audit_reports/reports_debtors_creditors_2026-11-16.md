# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 16 November 2026 (scheduled run)
**Prior report:** 2026-11-14 (no 2026-11-15 run on file)

**Method:** static review of the commits since the last report (0315e76 → HEAD 4fd92ee; working tree clean), anchor greps across the backend and App_js_fixed.js, review of the new `management_report.py`, and web checks against SARS and the IFRS Foundation. No live DB; tests not run. **No code edited** (5b was already implemented; tax tables are report-only).

**Changes since the last report (10 commits, 15–16 Nov):**
- payroll.py: GL-import revenue/expense helpers now skip reversed imports (`_live_import_entry_ids`, payroll.py:169); management accounts add revenue/COGS breakdowns; balance sheet lists each equity account (`other_equity_lines`); **provisional tax rewritten** (company financial year, `_period_pl` incl. GL imports, SBC estimate, 3rd payment, 80% check — payroll.py:3369-3456, 4177-4262).
- journal.py: reversals can keep the original entry's date (`same_date`, journal.py:1467-1480); new `PUT /journal/accounts/by-code/{code}` to rename/retype ledger accounts (journal.py:1681).
- csv_import.py: replaced opening-balance imports are reversed on their own date (csv_import.py:1149); Xero code inference limited to 3-digit codes; trial-balance "Total" lines skipped; source-aware reclassify tool.
- database.py: `ManagementReport` model, renewal-notice columns, one-off UPDATE re-dating `REV-OB-%` import reversals (inside the migrations list ✓).
- New `management_report.py` (monthly management report PDF, ledger-based) and `practice_mcp.py` additions; billing renewal / upcoming-due reminders.
- financial_statements.py unchanged since 2026-11-11.

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | **PASS** — `_to_zar` (payroll.py:23), VAT 15% (payroll.py:20), main.py:531 imports unchanged; new ledger-based management report is internally consistent |
| Debtors (AR) | **PASS with 1 Medium** — aging unchanged; Rule 6 false-fails after a replaced opening-balance import |
| Creditors (AP) | **PASS with 1 Medium** — reversal-aware PO lookups intact; Rule 7 has the same import-reversal gap |
| Cross-module | **PASS** — journal coverage and import-awareness intact |
| IFRS (AFS) | **PASS** — no standards change; deferred tax still computed |
| Tax (SARS) | **FAIL (2 Medium)** — SBC table is the 2025/26 table; 3rd provisional payment months are reversed. PAYE/UIF/SDL/VAT/CIT current |

**Overall: 0 Critical, 0 High, 3 Medium (1 AR/AP reconciliation, 2 provisional tax), 2 Low.**

## 2. Reports
✓ No issues found in `/reports/dashboard`, `/reports/management` or `/v1/summary`.
- The GL-import helpers now exclude import entries that have been reversed (payroll.py:169-183), and the reversal is dated like the original (csv_import.py:1149, database.py migration). A replaced import therefore drops out of both periods instead of staying in the P&L. ✓
- `_gl_import_expenses` now splits `breakdown` (opex only) and `cogs_breakdown`; `total` still includes both, so totals are unchanged. ✓
- `_period_pl` (payroll.py:3369) now selects payslips by `Payslip.period` instead of `generated_at`, matching the management accounts. ✓
- Tax provision lines still at 27% (payroll.py:2567, 3982).
- **Low (informational):** the new monthly management report (management_report.py:134-305) reads the ledger (accrual basis: all revenue/COGS/expense accounts). `/reports/management` still builds revenue from *paid* invoices plus imports. The two will show different revenue for the same month whenever invoices are unpaid. Both are valid; consider labelling the in-app management accounts "cash-received revenue" or noting the basis in the PDF footer so clients aren't confused. The report's balance sheet adds cumulative P&L as retained earnings and checks `balanced`; its cash flow checks `reconciles` ✓. Finance costs (6700 / "interest") are below operating profit ✓.

## 3. Debtors
- `debtors_aging` (payroll.py:4266) unchanged: status sent/overdue/partial, aged from `due_date`, ZAR balances ✓.
- **Medium — Rule 6 (AR control 1100) false-fails after a replaced opening-balance import.** payroll.py:3056-3063 subtracts only `source == "import"` lines on 1100. When an opening balance is replaced (`_guard_reimport`, csv_import.py:1130-1149), the old entry is reversed with source `import_reversal`. The journal balance nets both out, but the check still subtracts the original import, so the check is off by the replaced amount and recommends a backfill that cannot fix it. This has been possible since the replace feature (Oct 24); it now matters because Okwendalo replaced its opening balances on 15 Nov. **Fix:** filter `JournalEntry.source.in_(["import", "import_reversal"])` (sum is debit − credit, so the reversal nets automatically).

## 4. Creditors
- Per-PO AP lookups still net credit − debit and include `purchase_order_reversal` / `po_payment_reversal` (payroll.py:3103, 3608, 4367; purchase_orders.py:505; journal.py:1347; financial_statements.py:642) ✓.
- **Medium — Rule 7 (AP control 2000) has the same gap** at payroll.py:3131-3138: include `import_reversal` in the source filter.

## 5. Cross-module
✓ No issues found.
- Import-awareness: `_auto_backfill` still runs after invoice/expense imports (csv_import.py:126, 575, 788); unbalanced journal groups rejected (csv_import.py:1518-1555); non-ZAR invoice imports still read an exchange rate (csv_import.py:531-560); balance sheet still handles 3998/3999 and now lists other equity accounts one by one (payroll.py:2856-2915), with the total unchanged.
- New ledger-account editor (journal.py:1681-1717): system accounts keep their names and can only move between expense and COGS; changes are audit-logged ✓. Retyping an imported account changes historic P&L/BS classification immediately, which is intended.

## 6. IFRS compliance (AFS)
- Framework unchanged: IFRS for SMEs (2nd ed.) presentation. IFRS 18 and IFRS for SMEs 3rd edition apply to periods beginning on or after 1 Jan 2027 (first affected ZuZan FY: 1 Mar 2027). No deferral found. **Standards unchanged since the prior report.**
- **5b deferred tax: verified, still computed.** `"deferred_tax": deferred_tax_expense` (financial_statements.py:690); `_deferred_tax_balance` (financial_statements.py:143); `wear_and_tear_rate` (database.py:609, migration inside the list at database.py:1611-1615); `SA_CIT_RATE = 0.27` (fixed_assets.py:84); frontend Note 9 row (App_js_fixed.js:15442).
- Finance costs below EBIT; tax from profit_before_tax ✓ (file unchanged).
- AFS reads the full ledger, so same-dated import reversals net out correctly in the right year ✓.
- Sources: [IFRS — IFRS 18](https://www.ifrs.org/issued-standards/list-of-standards/ifrs-18-presentation-and-disclosure-in-financial-statements/), [IFRS — Nov 2026 EEG technical update](https://www.ifrs.org/content/dam/ifrs/meetings/2026/november/eeg/ap3-iasb-technical-update.pdf).

## 7. Tax updates (company + payroll)
- Tax year at run date: **2026/2027**. `TAX_YEARS["2026/2027"]` (payroll.py:312) present; provisional "2027/2028" (payroll.py:332); `_current_tax_year` (payroll.py:350); `SDL_RATE = 0.01` (payroll.py:370); VAT 15% (payroll.py:20); CIT 27% (fixed_assets.py:84) — confirmed 27% for years of assessment ending 1 Apr 2026–31 Mar 2027. Unchanged since last run.
- **Medium — SBC table is out of date.** payroll.py:3433-3434 uses the 2025/26 table (0% to R95,750; R18,848; R57,698) and the comment says "unchanged since". SARS's table for years of assessment ending 1 Apr 2026 – 31 Mar 2027 (Budget 25 Feb 2026) is:
  - 0% up to R99,000
  - 7% of the amount above R99,000 (R99,001 – R365,000)
  - R18,620 + 21% above R365,000 (R365,001 – R550,000)
  - R57,470 + 27% above R550,000
  The current table overstates SBC tax by up to R227.50. **Fix:** key the table by year of assessment (pick by the financial year's end date) and add the 2027 table. The old table stays for years ending before 1 Apr 2026.
- **Medium — 3rd provisional tax payment months are reversed.** payroll.py:4219 (and the docstring at 4188) uses 6 months for a February year-end and 7 months otherwise. SARS says the opposite: **7 months for a February year-end (30 September)** and **6 months for any other year-end** (e.g. 30 April → 31 October). Now a Feb-year-end company is shown 31 August, a month early, and other year-ends are shown a month late, which could lead to interest. **Fix:** `7 if fy_end.month == 2 else 6`.
- **Low — 80% check wording/reference.** payroll.py:4189 cites "s 89quat" for the 20% penalty; the under-estimation penalty is para 20 of the Fourth Schedule (s 89quat is interest). The check at payroll.py:4213 uses last year's taxable income as a proxy for this year's actual income, which is a fair early warning, and the user note at 4235-4236 describes the rule correctly. Correct the docstring reference only.
- MTBPS (Oct 2026): no rate changes in force. Next changes are expected in Budget Feb 2027.
- Sources: [SARS — Companies, trusts and SBC rates](https://www.sars.gov.za/tax-rates/income-tax/companies-trusts-and-small-business-corporations-sbc/), [SARS — FAQ: When must provisional tax be paid?](https://www.sars.gov.za/faq/faq-when-must-provisional-tax-be-paid/), [SARS — Provisional tax](https://www.sars.gov.za/businesses-and-employers/provisional-tax/). No tax-table edits made.

## 8. Action items
**Critical / High:** none.

**Medium**
1. (New) Rules 6/7: include `import_reversal` with `import` in the opening-balance exclusion at payroll.py:3061 and payroll.py:3137. Okwendalo will currently see AR/AP control failures equal to its replaced opening debtors/creditors.
2. (New) Provisional tax 3rd payment: payroll.py:4219 → `7 if fy_end.month == 2 else 6`; fix the docstring at payroll.py:4188.
3. (New) SBC table: replace payroll.py:3433-3434 with a year-of-assessment-keyed table including the 2026/27 figures (R99,000 / R18,620 / R57,470). Handle this in the annual tax-table task or as a quick fix.

**Low**
4. (New) Docstring reference payroll.py:4189: "s 89quat" → "para 20, Fourth Schedule".
5. (New, informational) State the revenue basis (accrual ledger vs cash-received) on the monthly management report PDF and/or the in-app management accounts.
6. (Carried) Run `tests/test_practice_mcp.py`; consider defaulting `vat_registered` to False in practice_mcp.py when the attribute is missing.
7. (Owner, carried) Run GL account-type review / `reclassify-gl-accounts` in prod for older imports.
8. (Owner, carried) POPIA privacy page: legal review + Netlify publish.
9. (Owner, carried) Run `check_fixed_asset_useful_life.py` dry run in prod.

Standing reminders: replace the provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027 (and add the 2027/28 SBC table then); IFRS for SMEs 3rd ed. / IFRS 18 checklist Jan–Feb 2027.

---
## Fixes applied (17 Nov 2026, on request)
- **Medium 1 (fixed):** Rules 6/7 now treat `import` and `import_reversal` lines as opening balances (payroll.py Rule 6 + Rule 7 filters). New test `test_ar_ap_control_checks_net_out_a_replaced_opening_balance`.
- **Medium 2 (fixed):** 3rd provisional payment = 7 months after a February year-end (30 Sep), 6 months otherwise; docstring corrected (also Low 4: "Fourth Schedule para 20").
- **Medium 3 (fixed):** SBC tables are now keyed by year of assessment (`_SBC_TABLES`, `_sbc_brackets_for`); 2026/27 table R99,000 / R18,620 / R57,470 added, 2023–2026 table kept; provisional tax passes the financial year-end.
- **VAT deadline (owner request):** one helper `_vat_due_day` (25th of the month after the period, earlier business day on a weekend/public holiday) now drives both `/reports/vat201` and the 13-week cash-flow forecast (the forecast used the bare 25th). In-app assistant text (main.py, App_js_fixed.js, zuzan-app/src/App.js) now states the 25th.
- Tests: tests/test_provisional_tax_fy.py and tests/test_import_replace_and_statement.py pass (9/9). In the full suite, the only failures were order-dependent or environment-only (signup flow and migration wizards pass when run alone; the payroll-journal runner cannot delete its temp DB in the mounted folder), and none involve the changed code. Not yet committed.
