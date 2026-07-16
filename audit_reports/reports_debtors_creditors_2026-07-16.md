# Reports / Debtors / Creditors Audit — 2026-07-16

Scope: `/reports/dashboard`, `/reports/management`, `/v1/summary`, Debtors (AR), Creditors (AP), cross-module journal coverage, IFRS compliance (AFS) incl. deferred-tax verification (5b), SARS tax rates.
Files reviewed: payroll.py, main.py, journal.py, purchase_orders.py, csv_import.py, financial_statements.py, database.py, App_js_fixed.js.

Prior report: 2026-07-15. Changed since then: main.py (Sentry error monitoring, plan feature gating) and auth.py (welcome-email/notification fixes) — neither touches AR/AP/report data paths; `/v1/summary` re-verified intact. journal.py and payroll.py carry yesterday's same-day payroll journal fixes (C1/C1a/T1/T2), all re-verified intact this run. financial_statements.py and App_js_fixed.js unchanged since 14 July. All verification done with Read/Grep per the stale-mount pitfall.

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | **PASS** |
| Debtors (AR) | **PASS** |
| Creditors (AP) | **PASS** — reversal-aware netting intact at all four sites |
| Cross-module | **PASS** — yesterday's payroll journal fix (C1/C1a) verified intact |
| IFRS compliance (AFS) | **PASS with one new Medium finding (F1)** — COGS/staff-cost split misclassified on the income statement |
| Tax (company + payroll) | **PASS** — 2026/27 rates current; T1/T2 fixes verified intact |

**One new Medium finding (F1):** the AFS income statement classifies all `51xx` accounts as Cost of Sales — but in this chart, 5000 is Cost of Sales and 51xx are staff costs. Gross profit/margin are misstated (net profit unaffected). Yesterday's new 5120/5130 employer-contribution accounts widen the error.

## 2. Reports

✓ No issues found.

- `total_revenue`: paid invoices only via `_to_zar()` (payroll.py:999–1006) + bank-import income; `_to_zar` (payroll.py:17–24) prefers `paid_amount_zar`, falls back to amount × exchange_rate, ZAR passthrough ✓.
- `total_outstanding`: sent + overdue only via `_to_zar()` (payroll.py:1008–1012) — paid/draft excluded ✓.
- Expenses ex-VAT, excluded from revenue (payroll.py:1014–1018); PO COGS delivered-value only via `_po_delivered_net` (payroll.py:1020–1028) — no double-counting; depreciation included (:1030–1034); payroll costs from all payslips incl. terminated employees (:1040–1052).
- Management-accounts revenue trend applies `_to_zar()` + bank-import income per month bucket (payroll.py:1937–1948); PO COGS per bucket ✓.
- `/v1/summary` (main.py:443–488): unchanged in substance by the 15-Jul Sentry/gating edits — still imports and uses `_to_zar`, `_po_delivered_net`, `_bank_import_income`; expenses ex-VAT, PO delivered value, depreciation, all-payslip payroll — consistent with dashboard ✓.
- Plan feature gating (new 15 Jul) affects endpoint *access* by subscription tier, not data accuracy — no impact on the figures any tier sees.

## 3. Debtors

✓ No issues found.

- `/reports/debtors-aging` (payroll.py:2109+): status IN (sent, overdue) only; paid/draft excluded; `_to_zar()` per invoice (:2131); aging strictly from `due_date`, invoices without one bucketed `not_due` (:2125–2132) ✓.
- Import fixes intact: auto journal backfill after invoice/expense import (csv_import.py:124–143, 501, 563); non-ZAR imports without an exchange rate rejected (csv_import.py:458–463) ✓.

## 4. Creditors

✓ No issues found.

- `/reports/creditors-aging` (payroll.py:2172+): received/partial POs only; fully paid excluded; per-PO AP from journal account 2000 netting `credit − debit` incl. `purchase_order_reversal` (:2200–2207); aged from received date + supplier payment terms (:2236–2237); bank details decrypted via `decrypt_field` (:2250–2252) ✓.
- Reversal-awareness verified at all four sites: creditors-aging (payroll.py:2200–2207), Rule 7 (payroll.py:1537–1545), pay_po (purchase_orders.py:438–445), backfill (journal.py:848) ✓.

## 5. Cross-module

✓ No issues found. Yesterday's Critical fix verified intact:

- **C1/C1a re-verification**: `post_payroll` (journal.py:368+) still posts salary at gross + overtime (:402), employer pension/medical as expense debits 5120/5130 with liability credits 2230/2240 (:412–432), rounding-residue fold before `_assert_balanced` (:438–442). All four accounts present in `DEFAULT_ACCOUNTS` (journal.py:39–40, 52–53) so `init_accounts` upserts them on the next payroll run ✓. Reminder from yesterday stands: **restart the backend** so the new accounts are created before the next payroll run.
- Journal coverage complete: invoice raised/paid/COGS, expense, expense paid, PO received/paid, payroll, depreciation, plus bank-import income and the import backfill — every poster runs `_assert_balanced` ✓.
- Import-awareness fixes of 2026-07-11 intact: Rules 6/7 exclude `source="import"` on 1100/2000 (payroll.py:1503, 1579); balance sheet includes 3999/3998 (payroll.py:1293–1313); unbalanced journal import groups rejected (csv_import.py:1035–1064); FX rate required for non-ZAR invoice imports (csv_import.py:458–463) ✓.
- Migrations all inside the list literal (database.py) — dead-code pitfall respected ✓.

## 6. IFRS compliance (AFS)

Framework: **IFRS for SMEs** — correct for a SA private company under Companies Act 71 of 2008 regulations.

Standards status re-verified 16 July 2026 — **unchanged**: IFRS for SMEs third edition (issued 27 Feb 2025) and IFRS 18 both effective for annual periods beginning on or after 1 January 2027; IFRS 18 binds full-IFRS preparers only, so current second-edition statements remain compliant. First mandatory ZuZan FY on the third edition: 1 Mar 2027 – 29 Feb 2028.

Sources: [IFRS Foundation — IFRS for SMEs](https://www.ifrs.org/issued-standards/ifrs-for-smes/), [IASB — third edition announcement](https://www.ifrs.org/news-and-events/news/2025/02/iasb-issues-major-update-smes-accounting-standard/), [IAS Plus — IFRS 18 effective date](https://www.iasplus.com/en/events/effective-dates/2027/ifrs-18), [PwC Viewpoint — IFRS for SMEs 3rd ed.](https://viewpoint.pwc.com/dt/gx/en/pwc/in_briefs/in_briefs_INT/in_briefs_INT/iasb-issues.html), [ICAEW](https://www.icaew.com/insights/viewpoints-on-the-news/2025/feb-2025/iasb-publishes-third-edition-of-ifrs-for-smes-accounting-standard).

### Deferred tax (5b) — implemented 2026-07-14, VERIFIED intact this run (no re-implementation needed)

financial_statements.py unchanged since 14 July. `_CIT_RATE = 0.27` (:78), `_wt_rate_pct` (:99), `_deferred_tax_balance` (:125–166: tax base = cost − cumulative W&T floored at 0, temporary difference × 27%, zero fallback when no rate), opening/closing/expense (:234–236), Note 9 movement + `total_tax` + effective rate + balances (:532–541), equity `deferred_tax_movement` (:612). Model column `wear_and_tear_rate` with migration inside the list literal (database.py). Finance costs below EBIT, tax off `profit_before_tax` (:198–229). Frontend Note 9 deferred-tax row (App_js_fixed.js:11353–11354) and fixed-asset DTL/DTA view (:9963–9987) intact ✓.

### F1 (Medium — NEW): income-statement COGS split catches staff costs, misses actual Cost of Sales

financial_statements.py:207–209 splits expenses with `l["code"].startswith("51")` labelled "COGS", everything else opex. But in the chart of accounts (journal.py:48–53): **5000 = Cost of Sales** (the account actually debited by `post_invoice_cogs` journal.py:281 and `post_po_received` :514) does **not** start with "51" → lands in opex; while **5100 Salaries, 5110 Payroll Levies, and the new 5120/5130 employer pension/medical accounts** all start with "51" → presented as cost of sales.

Effect: `gross_profit`/`gross_margin` (:211–213) = revenue − staff costs instead of revenue − cost of sales; EBIT, PBT and net profit are unaffected (both groups are deducted before EBIT). Under IFRS for SMEs 5.11 (function-of-expense presentation) the cost-of-sales line must be actual COGS, and employee benefits should be disclosable as such. Yesterday's (correct) payroll journal fix routes more value through 51xx, widening the misstated subtotal.

Suggested fix (report-only — outside 5b authorization): cogs_lines = codes starting "50" (5000 Cost of Sales; 5950 inventory adjustments if desired); present 51xx as a "Staff costs" opex group. Frontend AFS view labels should follow.

## 7. Tax updates (company + payroll)

Current SARS tax year: **2026/2027** (1 Mar 2026 – 28 Feb 2027).

- **PAYE 2026/2027** (payroll.py:127–142): entry present, primary rebate **R17,820** ✓, UIF ceiling **R17,712/month** ✓, brackets carry the 3.4% inflation adjustment verified in prior runs; `CURRENT_TAX_YEAR = "2026/2027"` (:142) and the engine defaults to it (:232, 286) ✓.
- **s11F** 27.5% / **R430,000** cap (payroll.py:155–156) ✓; **s6A MTC** R376/R254 (:160–161) ✓ — unchanged since yesterday's verification.
- **T1/T2 fixes verified intact**: employer pension in the PAYE base and deemed employee contribution for s11F (payroll.py:299–316); UIF base `min(taxable_gross, ceil)` including overtime (:339–341) ✓.
- **CIT 27%** ✓ (payroll.py:1056, 1911, 2008; financial_statements.py:78, 228). **VAT 15%** ✓ (payroll.py:1375, 2364). No announced rate changes as at 16 July 2026.
- Rebates: only the primary rebate is implemented; secondary (R9,765) / tertiary (R3,249) remain a carried Low item pending 65+ employees.
- New e@syFile/IRP5 export (landed 14 Jul, BRS v25.3.0) uses payslip-level IRP5 codes incl. 3713 for the employer medical fringe benefit (payroll.py:620–634) — consistent with the T1 fringe-benefit treatment; full e@syFile validation is out of scope for this audit.

Sources: [SARS — rates of tax for individuals](https://www.sars.gov.za/tax-rates/income-tax/rates-of-tax-for-individuals/), [SARS — Budget 2026 FAQ](https://www.sars.gov.za/about/sars-tax-and-customs-system/budget/budget-2026-frequently-asked-questions/), [KPMG SA Budget Guide 2026/27](https://assets.kpmg.com/content/dam/kpmgsites/za/pdf/2026/02/SA%20Budget%20Guide%202026.pdf), [Stip — SARS tax tables 2026/27 employer guide](https://stip.co.za/blog/sars-tax-tables-2026-2027).

No edits made to tax tables (report-only; 5b needed verification only this run).

## 8. Action items

1. **[Medium — F1]** ~~Fix the AFS COGS split~~ — **FIXED same day** (see section 9).
2. **[High — operational, carried]** Restart the backend so `init_accounts` creates 5120/5130/2230/2240 before the next payroll run (yesterday's C1 fix depends on it).
3. **[Low — carried]** Sync App_js_fixed.js → zuzan-app/src/App.js at next build; unify the two deferred-tax calculators (`/fixed-assets/deferred-tax` vs AFS helper); IFRS for SMEs 3rd-edition transition review ahead of FY2028; s11F excess carry-forward on annual reconciliation; secondary/tertiary rebates if 65+ employees onboarded; annual task flips `CURRENT_TAX_YEAR` on 1 Mar 2027.

## 9. Fix applied 2026-07-16 (same-day, user-authorized)

**F1 — financial_statements.py:207–234**: the `startswith("51")` COGS split replaced with name-aware classification. Staff costs are detected by name ("salar", "wage", "payroll", "pension", "medical aid", "staff cost") and always presented in opex — so the journal's 5100/5110/5120/5130 accounts leave cost of sales. COGS = codes starting "50" (5000 Cost of Sales), name-matched "cost of sales"/"cost of goods"/"stock adjust"/"inventory adjust" (covers 5950 Stock Adjustments and imported accounts such as "6000 - Cost of Sales"), plus remaining non-staff 51xx codes — preserving imported charts that use the 51xx-as-COGS convention (5110 Purchases, 5140 Direct Labour, per the frontend COA template App_js_fixed.js:399–404). Finance costs unchanged (still below EBIT). EBIT/PBT/net profit are algebraically unaffected; only the gross-profit subtotal moves. Output shape unchanged (`cogs_lines`/`opex_lines`) — no frontend edit needed since the AFS view renders those arrays generically (App_js_fixed.js:10950–10959). Classification verified against the full backend chart plus imported-COA cases via standalone logic test; file edits verified with Read/Grep per the stale-mount pitfall. No journal data affected — presentation-only; regenerating/viewing the AFS reflects the fix immediately.

## 10. Changes since last run (2026-07-15)

- Yesterday's same-day fixes (C1/C1a payroll journal, T1 fringe benefit, T2 UIF overtime) all **verified intact** — no regressions from the 15-Jul Sentry/plan-gating/auth commits.
- main.py and auth.py modified after the last report (Sentry monitoring, plan feature gating, welcome-email fixes) — reviewed for scope; `/v1/summary` unchanged in substance; no impact on Reports/AR/AP data paths.
- **New finding F1** (Medium): AFS income-statement COGS/staff-cost misclassification — pre-existing, but surfaced by tracing where the new 5120/5130 accounts land on the statements.
- IFRS standards and SARS rates (CIT/VAT/PAYE/rebate/UIF/SDL/s11F/MTC) unchanged.
