# Reports / Debtors / Creditors Audit — 2026-07-15

Scope: `/reports/dashboard`, `/reports/management`, `/v1/summary`, Debtors (AR), Creditors (AP), cross-module journal coverage, IFRS compliance (AFS) incl. deferred-tax verification (5b), SARS tax rates.
Files reviewed: payroll.py, main.py, journal.py, purchase_orders.py, csv_import.py, financial_statements.py, database.py, App_js_fixed.js.

Prior report: 2026-07-14. Changed since then: payroll.py, database.py, companies.py, main.py, App_js_fixed.js were all modified on 14 July after the last run. Git log shows subscription-gate/billing/landing work, **plus a new payroll feature: pension/provident fund (s11F) and medical aid (s6A MTC) support** — new columns on employees/payslips, new constants, and an extended `calc_payroll`. This new feature was audited in full and produced this run's main findings. All verification done with Read/Grep per the stale-mount pitfall.

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | **PASS** |
| Debtors (AR) | **PASS** |
| Creditors (AP) | **PASS** — reversal-aware netting intact at all four sites |
| Cross-module | **FAIL** — new payroll journal defect (C1) |
| IFRS compliance (AFS) | **PASS** — deferred tax implementation (2026-07-14) verified intact |
| Tax (company + payroll) | **PASS** — new 2026/27 s11F cap and MTC values verified correct against SARS |

**One Critical finding (C1):** `post_payroll` in journal.py was not updated for the new pension/medical deductions (nor for overtime): the journal entry no longer balances, `_assert_balanced` raises, and the whole payroll run rolls back with a 500 for any employee with overtime, pension, or medical aid.

## 2. Reports

✓ No issues found. (Line numbers shifted — payroll.py grew with the new payroll feature.)

- `total_revenue`: paid invoices only via `_to_zar()` (payroll.py:986–992) + bank-import income; `_to_zar` (payroll.py:17–24) prefers `paid_amount_zar`, falls back to amount × exchange_rate, ZAR passthrough ✓.
- `total_outstanding`: sent + overdue via `_to_zar()` (payroll.py:994–998) ✓.
- Expenses ex-VAT, excluded from revenue (payroll.py:1000–1004); PO COGS delivered-value only via `_po_delivered_net` (payroll.py:1006–1014) — no double-counting (duplicate-expense heuristic still present :1062–1099); depreciation included (:1016–1020); payroll costs from all payslips incl. terminated employees (:1026–1038).
- Management-accounts revenue trend applies `_to_zar()` + bank-import income per month bucket (payroll.py:1923–1927); PO COGS and depreciation per bucket (:1932–1945).
- `/v1/summary` (main.py:431–476) imports and uses `_to_zar`, `_po_delivered_net`, `_bank_import_income` — consistent with dashboard ✓.

## 3. Debtors

✓ No issues found.

- `/reports/debtors-aging` (payroll.py:2094–2154): status IN (sent, overdue) only (:2103–2106); paid/draft excluded; `_to_zar()` per invoice (:2117); aging strictly from `due_date`, invoices without one bucketed `not_due` (:2110–2137) ✓.
- Import fixes intact: auto journal backfill after invoice/expense import (csv_import.py:124–143, 501, 563); non-ZAR imports without an exchange rate rejected (csv_import.py:458–470) ✓.

## 4. Creditors

✓ No issues found.

- `/reports/creditors-aging` (payroll.py:2157+): received/partial POs only (:2173–2176); fully paid POs excluded; per-PO AP from journal account 2000 netting `credit − debit` incl. `purchase_order_reversal` (:2185–2201); aged from received date + supplier payment terms (:2220–2230); bank details decrypted via `decrypt_field` (:2236–2238) ✓.
- Reversal-awareness verified at all four sites: creditors-aging (payroll.py:2188–2199), Rule 7 (payroll.py:1526–1539), pay_po (purchase_orders.py:437–453), backfill (journal.py:790–805) ✓.

## 5. Cross-module

**✗ FAIL — one Critical defect introduced with the 2026-07-14 pension/medical payroll feature.**

### C1 (Critical): `post_payroll` journal entry no longer balances — payroll run blocked

`calc_payroll` (payroll.py:244–359) now computes: `net_pay = taxable_gross − paye_after_mtc − uif_employee − pension_employee_monthly − medical_aid_employee` (payroll.py:335), where `taxable_gross = gross + overtime` (:290). The payslip stores these fields (payroll.py:487–509).

But `post_payroll` (journal.py:360–394) still posts only:
DR 5100 `gross_salary` + DR 5110 (UIF-er + SDL) / CR 2200 PAYE + CR 2210 UIF + CR 2220 SDL + CR 1000 net_pay.

Debits − credits works out to `pension_employee + medical_aid_employee − overtime`. Whenever an employee has overtime, a pension deduction, or a medical aid deduction, the entry is unbalanced, `_assert_balanced` (journal.py:177–181) raises, and `run_payroll` rolls back the entire run with HTTP 500 (payroll.py:513–523). **Payroll cannot be processed at all for such employees.** Additionally `payslip.gross_salary` = base gross only (`c["gross"]`, payroll.py:490), so even the pre-existing overtime feature debits salary expense excluding overtime while crediting net pay including it.

Required fix (journal.py `post_payroll`): debit salary expense with gross + overtime; add DR employer pension/medical contributions (staff-cost expense) and CR a Pension/Provident Payable and Medical Aid Payable liability (new accounts, e.g. 2230/2240) for employee-deducted + employer amounts; keep PAYE/UIF/SDL lines as-is. Entry then balances for all input combinations.

### C1a (High): employer pension/medical costs absent from the journal

Even for employees where the entry happens to balance, employer pension (`pension_employer`) and employer medical aid (`medical_aid_employer_con`) are never journaled. The dashboard/management payroll cost uses `payslip.total_cost` (which includes them, payroll.py:338), while the journal — and therefore the AFS income statement and Rule-1-style checks — carries only gross + levies. Staff costs are understated in the journal by the employer pension/medical amounts → cross-module inconsistency between Reports and AFS. Fixed by the same `post_payroll` rework.

Everything else: ✓

- Journal coverage otherwise complete (journal.py): `post_invoice_raised` (:186), `post_invoice_paid` (:226), `post_invoice_cogs` (:260), `post_expense` (:285), `post_payroll` (:360), `post_expense_paid` (:397), `post_po_received` (:426), `post_po_paid` (:478), plus bank-import income and the import backfill.
- Import-awareness fixes of 2026-07-11 intact: Rules 6/7 exclude `source="import"` on 1100/2000 (payroll.py:1484–1496, 1560–1572); balance sheet includes 3999/3998 (payroll.py:1279–1299); unbalanced journal import groups rejected (csv_import.py:1035–1064); FX rate required for non-ZAR invoice imports (csv_import.py:458–470).
- New migrations (pension/medical columns, e@syFile refs, `wear_and_tear_rate`) are all **inside** the migrations list literal (database.py:1320–1339) — dead-code pitfall respected ✓.

## 6. IFRS compliance (AFS)

Framework: **IFRS for SMEs** — correct for a SA private company under Companies Act 71 of 2008 regulations.

financial_statements.py is unchanged since the 2026-07-14 implementation run (mtime 14 Jul 00:12). Standards status re-verified 15 July 2026 — **unchanged**: IFRS for SMEs third edition (issued Feb 2025) and IFRS 18 both effective for annual periods beginning on or after 1 January 2027; IFRS 18 binds full-IFRS preparers only. Current statements remain compliant on the second edition. First mandatory ZuZan FY on the third edition: 1 Mar 2027 – 29 Feb 2028.

Sources: [IFRS Foundation — IFRS for SMEs](https://www.ifrs.org/issued-standards/ifrs-for-smes/), [IFRS 18](https://www.ifrs.org/issued-standards/list-of-standards/ifrs-18-presentation-and-disclosure-in-financial-statements/), [IAS Plus — third edition](https://www.iasplus.com/en/news/2025/02/third-ifrs-for-smes), [Nexia SAB&T](https://www.nexia-sabt.co.za/ifrs-for-smes-accounting-standard-third-edition-2025/), [PKF SA — SME framework](https://www.pkf.co.za/news/2026/ifrs-for-sme-conceptual-framework/).

### Deferred tax (5b) — implemented 2026-07-14, VERIFIED intact this run

No longer hard-coded: `_CIT_RATE = 0.27` (financial_statements.py:78), `_wt_rate_pct` (:99), `_deferred_tax_balance` (:125–166, temporary difference × 27%, tax base floored at 0, zero-difference fallback when no rate), opening/closing/expense (:234–236), Note 9 movement + total_tax + effective rate + balances (:532–541), equity `deferred_tax_movement` (:612). Model column `wear_and_tear_rate` (database.py:454) with migration inside the list literal (database.py:1321). Finance costs still below EBIT with tax off `profit_before_tax` (:199–229). Frontend Note 9 row survived the 14-Jul frontend edits (App_js_fixed.js:11337–11338); fixed-asset deferred-tax view intact (:9947–9971). No re-implementation needed.

## 7. Tax updates (company + payroll)

Current SARS tax year: **2026/2027** (1 Mar 2026 – 28 Feb 2027).

- **PAYE 2026/2027** (payroll.py:127–139): brackets, primary rebate R17,820, UIF ceiling R17,712 — verified in prior runs, unchanged ✓. `CURRENT_TAX_YEAR = "2026/2027"` (:142) ✓.
- **NEW — s11F retirement deduction** (payroll.py:153–156): rate 27.5%, cap **R430,000** — ✓ correct; Budget 2026 raised the cap from R350,000 effective 1 Mar 2026 (first increase since 2016). Note: SARS carries excess contributions forward to the next year; the app treats excess as permanently post-tax (`s11f_excess_monthly`, payroll.py:313, 347) — acceptable simplification for monthly PAYE, note for annual reconciliation/IRP5.
- **NEW — s6A medical tax credits** (payroll.py:158–161, 215–228): **R376**/month main member and first dependant each, **R254**/month each additional — ✓ matches SARS 2026/27 (up from R364/R246). Non-refundable application ✓ (`max(0, paye − mtc)`, :322). Employer medical aid correctly added to the PAYE base as a fringe benefit (:296–298) ✓.
- **T1 (Medium) — employer retirement contributions not treated as fringe benefit**: since 1 Mar 2016, employer pension/provident contributions are a taxable fringe benefit (Seventh Schedule para 2(l)/12D) and are deemed employee contributions for s11F. `calc_payroll` ignores `pension_employer_*` in both the PAYE base and the s11F deemed contribution (payroll.py:293–316). Tax-neutral while under the 27.5%/R430k caps (add-then-deduct cancels), but overstates/understates PAYE once a cap binds, and the IRP5 remuneration figure will be wrong. Fix in the annual tax task or sooner.
- **T2 (Medium) — UIF base excludes overtime**: `uif_base = min(gross_monthly, ceil)` with comment "overtime … excluded per SARS" (payroll.py:324–327). Per the SARS/DoL guidance, UIF remuneration **includes** overtime (commission is the notable exclusion). Understates UIF (both 1% legs) for employees below the R17,712 ceiling who work overtime.
- **CIT 27%** ✓ (payroll.py:1042, 1897, 1994; financial_statements.py:78). **VAT 15%** ✓ (payroll.py:1361, 2350). No announced changes. EMP201 PAYE uses post-MTC `payslip.paye` ✓.

Sources: [SARS — s11F FAQ](https://www.sars.gov.za/faq/faq-what-are-s11f-annual-allowable-deductions/), [SARS — s11F(2)(a) clarification](https://www.sars.gov.za/latest-news/retirement-fund-contribution-deductions-section-11f2a/), [Moonstone — Budget 2026 retirement thresholds](https://www.moonstone.co.za/budgets-retirement-threshold-changes-in-effect-despite-legislative-omission/), [SARS — Medical Tax Credit Rates](https://www.sars.gov.za/tax-rates/medical-tax-credit-rates/), [SARS — Medical Credits](https://www.sars.gov.za/types-of-tax/personal-income-tax/medical-credits/), [SARS — UIF](https://www.sars.gov.za/types-of-tax/unemployment-insurance-fund/), [SARS — UIF employer guide (PDF)](https://www.sars.gov.za/wp-content/uploads/Ops/Guides/UIF-GEN-01-G01-Guide-for-Employers-in-respect-of-the-Unemployment-Insurance-Fund-External-Guide.pdf).

No edits made to tax tables (report-only; 5b needed verification only this run).

## 8. Action items

1. **[Critical — C1]** ~~Rework `post_payroll`~~ — **FIXED same day** (see section 9).
2. **[High — C1a]** ~~Journal employer pension/medical costs~~ — **FIXED same day** (same rework). No backfill needed: posting failed hard while C1 was live, so no mis-posted payslips exist.
3. **[Medium — T1]** ~~Employer retirement contributions fringe benefit + deemed s11F~~ — **FIXED same day**.
4. **[Medium — T2]** ~~Overtime in UIF base~~ — **FIXED same day**.
5. **[Low — carried]** Sync App_js_fixed.js → zuzan-app/src/App.js at next build (no frontend change needed for today's fixes); unify the two deferred-tax calculators (`/fixed-assets/deferred-tax` vs AFS helper); IFRS for SMEs 3rd-edition transition review ahead of FY2028; s11F excess carry-forward on annual reconciliation; secondary/tertiary rebates if 65+ employees onboarded; annual task flips `CURRENT_TAX_YEAR` on 1 Mar 2027.

## 9. Fixes applied 2026-07-15 (same-day, user-authorized)

- **C1/C1a — journal.py**: `post_payroll` (journal.py:368–444) reworked. Salary debit now `gross + overtime` (reconstructed from `overtime_amount + sunday_amount + ph_amount`); employer pension/medical posted as expense debits to new accounts **5120 Pension Contributions (Employer)** / **5130 Medical Aid Contributions (Employer)**; employee-deducted + employer amounts credited to new liabilities **2230 Pension Fund Payable** / **2240 Medical Aid Payable**. All four accounts added to `DEFAULT_ACCOUNTS` (journal.py:36–40, 48–50) — `init_accounts` upserts, and `run_payroll` calls it before posting, so existing companies get them automatically. A ≤5c rounding-residue fold into the salary debit (journal.py:436–441) prevents cent-level drift across independently-rounded payslip fields from ever hard-blocking a run. Entry balances identically for plain payslips (backward compatible); `getattr` defaults keep backfill of pre-migration payslips working. Journal staff cost now equals `payslip.total_cost` → AFS/dashboard reconcile.
- **T1 — payroll.py:299–325**: employer pension added to the PAYE base as a fringe benefit (para 2(l)/12D) and deemed an employee contribution for s11F (`pension_total_annual`); tax-neutral below the 27.5%/R430k caps, correct PAYE above. `s11f_excess` now measures the total contribution above cap (no downstream consumers — verified).
- **T2 — payroll.py:336–342**: UIF base now `min(taxable_gross, ceiling)` — overtime included per SARS UIF-GEN-01-G01.
- Verified balance algebra: DR − CR = taxable_gross − paye − uif_ee − pen_ee − med_ee − net_pay = 0 for every input combination. All edits verified with Read/Grep per the stale-mount pitfall. Restart the backend so `init_accounts` creates 5120/5130/2230/2240 on the next payroll run (no schema migration required — accounts are rows, not columns).

## 10. Changes since last run (2026-07-14)

- Deferred tax (L3, implemented last run) verified intact — including the frontend rows, which survived the 14-Jul App_js_fixed.js edits.
- **New pension/medical payroll feature landed 14 July** — constants (s11F R430k cap, MTC R376/R254) verified correct against SARS, but the journal layer was not updated with it → new Critical C1 / High C1a, plus Medium T1/T2 on fringe-benefit and UIF treatment.
- Subscription-gate/billing/landing changes reviewed for scope — no impact on Reports/AR/AP data paths.
- IFRS standards and SARS core rates (CIT/VAT/brackets/UIF/SDL) unchanged.
