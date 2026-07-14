# Reports / Debtors / Creditors Audit — 2026-07-14

Scope: `/reports/dashboard`, `/reports/management`, `/v1/summary`, Debtors (AR), Creditors (AP), cross-module journal coverage, IFRS compliance (AFS) incl. one-time deferred-tax implementation (5b), SARS tax rates.
Files reviewed: payroll.py, main.py, journal.py, purchase_orders.py, companies.py, csv_import.py, financial_statements.py, fixed_assets.py, database.py, App_js_fixed.js.

Prior report: 2026-07-13. Change detection: no source files changed since the last run apart from the 2026-07-13 same-day fixes (reversal-aware AP netting, finance costs), which this run confirmed in place via Read/Grep. Note: the bash mount again served stale content (wc reported database.py at 1,226 lines vs actual 1,335) — all verification was done with Read/Grep per the standing pitfall.

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | **PASS** |
| Debtors (AR) | **PASS** |
| Creditors (AP) | **PASS** — 2026-07-13 reversal fixes verified in place |
| Cross-module | **PASS** |
| IFRS compliance (AFS) | **PASS** — deferred tax (L3) **IMPLEMENTED this run** |
| Tax (company + payroll) | **PASS** — 2026/2027 tables re-verified against SARS |

No new defects found. Carried-over item L3 (deferred tax) closed by implementation under the section 5b authorization.

## 2. Reports

✓ No issues found.

- `total_revenue`: paid invoices only via `_to_zar()` (payroll.py:510–516) + bank-import income; `_to_zar` (payroll.py:17) prefers `paid_amount_zar`, falls back to amount × exchange_rate, ZAR passthrough.
- `total_outstanding`: sent + overdue via `_to_zar()` (payroll.py:518–522).
- Expenses ex-VAT, excluded from revenue (payroll.py:524–528); PO COGS uses delivered value only via `_po_delivered_net` (payroll.py:530–538) — no double-counting; depreciation included (payroll.py:540–544); payroll costs from all payslips incl. terminated employees (payroll.py:550–562).
- Management-accounts revenue trend applies `_to_zar()` + bank-import income per bucket (payroll.py:1447–1451); period revenue/COGS consistent (payroll.py:1355–1380).
- `/v1/summary` (main.py:290–331) imports and uses `_to_zar`, `_po_delivered_net`, `_bank_import_income` — intact.

## 3. Debtors

✓ No issues found.

- `/reports/debtors-aging` (payroll.py:1618–1678): status IN (sent, overdue) only (:1629); paid/draft excluded; `_to_zar()` per invoice (:1641); aging strictly from `due_date`, invoices without a due date bucketed as `not_due` (:1637–1653). Buckets not_due / current / 31–60 / 61–90 / 90+ with grand total.
- Import fixes intact: auto journal backfill after invoice/expense import (csv_import.py:124–143, 501, 563); non-ZAR imports without an exchange rate rejected (csv_import.py:458–463).

## 4. Creditors

✓ No issues found.

- `/reports/creditors-aging` (payroll.py:1681+): received/partial POs only (:1697–1700); fully paid POs excluded; per-PO AP balance from journal account 2000 (:1705–1725); aged from received date + supplier payment terms (:1744–1754); supplier bank details decrypted via `decrypt_field` (:1760–1762).
- Reversal-awareness (2026-07-13 fixes) verified at all four sites — each nets `credit − debit` and includes source `"purchase_order_reversal"`: creditors-aging (payroll.py:1709–1717), Rule 7 (payroll.py:1047–1055), pay_po (purchase_orders.py:438–445), backfill (journal.py:798).

## 5. Cross-module

✓ No issues found.

- Journal coverage complete (journal.py): `post_invoice_raised` (:186), `post_invoice_paid` (:226), `post_invoice_cogs` (:260), `post_expense` (:285), `post_payroll` (:360), `post_expense_paid` (:397), `post_po_received` (:426), `post_po_paid` (:478), plus bank-import income and the import backfill.
- Import-awareness fixes of 2026-07-11 intact: Rules 6/7 exclude `source="import"` lines on 1100/2000 (payroll.py:1013, 1089); balance sheet includes 3999 Opening Balance Equity and 3998 imported Retained Earnings (payroll.py:803–823; csv_import.py:726–733, 925–946); unbalanced journal import groups rejected (csv_import.py:1035–1064); non-ZAR invoice imports require an exchange rate (csv_import.py:458–463).
- Debtors Control (1100) / Creditors Control (2000) reconciliation logic unchanged.

## 6. IFRS compliance (AFS)

Framework: **IFRS for SMEs** (financial_statements.py docstring, meta basis, basis-of-preparation note citing Section 23) — correct for a SA private company under Companies Act 71 of 2008 regulations.

Standards status re-verified 14 July 2026 — **unchanged since the last audit**: IFRS for SMEs third edition effective for annual periods beginning on or after 1 January 2027 (first mandatory ZuZan FY: 1 Mar 2027 – 29 Feb 2028), earlier application permitted; IFRS 18 (effective 1 Jan 2027) binds full-IFRS preparers only, not an IFRS for SMEs entity. Current statements remain compliant on the 2015 second edition. Finance-costs fix of 2026-07-13 verified: interest lines (account 6700 or name-matched) presented below EBIT, with tax and net profit derived from `profit_before_tax` (financial_statements.py:203–232).

Sources: [IFRS Foundation — IFRS for SMEs](https://www.ifrs.org/issued-standards/ifrs-for-smes/), [IASB third-edition announcement](https://www.ifrs.org/news-and-events/news/2025/02/iasb-issues-major-update-smes-accounting-standard/), [PwC In brief — third edition](https://viewpoint.pwc.com/dt/gx/en/pwc/in_briefs/in_briefs_INT/in_briefs_INT/iasb-issues.html), [ICAEW IFRS for SMEs tracker](https://www.icaew.com/technical/corporate-reporting/ifrs/ifrs-accounting-standards-tracker/ifrs-for-smes), [EY — IFRS 18 roadmap (SA)](https://www.ey.com/en_za/services/ifrs/roadmap-to-enhanced-financial-statements), [SAICA — IFRS 18](https://www.saica.org.za/news/a-new-era-for-financial-reporting/).

### Deferred tax — IMPLEMENTED this run (section 5b, action item L3)

`financial_statements.py` still hard-coded `"deferred_tax": 0.0` in Note 9, so the one-time implementation was carried out:

1. **database.py** — nullable `wear_and_tear_rate` column (% p.a., s11(e)/IN47 override) added to `FixedAsset` (database.py:430) with the ALTER TABLE migration **inside** the migrations list literal (database.py:1296–1297), per the dead-code pitfall.
2. **Rate resolution** (financial_statements.py:96–121 `_wt_rate_pct`): explicit `wear_and_tear_rate` → the asset's `sars_category` via the existing IN47 table in fixed_assets.py (`SARS_WEAR_TEAR`, discovered during the audit — the Fixed Assets module already had a per-asset deferred-tax view at `/fixed-assets/deferred-tax`; the AFS simply never used it) → category-name heuristic (computers 33.33%, software/phones 50%, furniture 16.67%, vehicles 20%, trucks 25%, plant & machinery 20%, buildings 4%, general equipment 20%) → None, in which case tax base = carrying value so the temporary difference is exactly zero.
3. **Computation** (financial_statements.py:125–166 `_deferred_tax_balance`): per asset, tax base = cost − cumulative straight-line wear-and-tear at the SARS rate, apportioned monthly from purchase date, floored at 0; temporary difference = accounting carrying value − tax base; balance = difference × 27% (positive = DTL, negative = DTA). Accounting carrying value is computed analytically as at the statement date (straight-line or diminishing-balance), so historical financial years don't use today's accumulated depreciation. Assets disposed on/before the date are excluded. Deferred tax expense = closing balance − opening balance (financial_statements.py:230–236).
4. **Note 9** (financial_statements.py:529–543): `deferred_tax` = period movement, `total_tax` = current + deferred, effective rate now on total tax; opening/closing balances disclosed as additive fields. Balance sheet: closing balance presented as computed line 2600 Deferred Tax Liability (or 1900 Deferred Tax Asset) with the matching adjustment to retained earnings so Assets = Equity + Liabilities holds (financial_statements.py:279–301) — nothing posted to the journal. Opening retained earnings in the equity statement carry the opening adjustment, with the movement disclosed as `deferred_tax_movement` (financial_statements.py:313–317, 612). Income-statement `tax_expense`/`net_profit` unchanged (current tax only) for output-shape compatibility. Accounting-policies income-tax note updated to cite Section 29 / s11(e) / IN47.
5. **Frontend** (App_js_fixed.js:10651–10653): Note 9 renders the computed deferred-tax amount when non-zero, "Nil" otherwise. Note: `zuzan-app/src/App.js` contains a copy of the frontend — sync at next build as usual.
6. **Safety** verified by inspection: with no fixed assets both balances are exactly 0.0, no balance-sheet lines are added, retained earnings are unadjusted, and Note 9 reduces to its previous values; the only shape changes are additive keys. All edits verified with Read/Grep (not bash) per the stale-mount pitfall.

Remaining Lows: none in the AFS module.

## 7. Tax updates (company + payroll)

✓ No issues found. Current SARS tax year: **2026/2027** (1 Mar 2026 – 28 Feb 2027). Re-verified against SARS-sourced tables — all rates current:

- **PAYE 2026/2027** (payroll.py:127–139): brackets 18% ≤ R245,100 / 26% to R383,100 / 31% to R530,200 / 36% to R695,800 / 39% to R887,000 / 41% to R1,878,600 / 45% above ✓; primary rebate R17,820 ✓ (threshold R99,000 under 65). Secondary (R9,765) / tertiary (R3,249) rebates still not implemented — acceptable, no 65+ employees; noted as enhancement.
- **Tax-year selection**: `CURRENT_TAX_YEAR = "2026/2027"` (payroll.py:142); safe fallback in `calc_paye`/`calc_payroll` (:206, :240) ✓. Annual task flips it on 1 Mar 2027.
- **UIF**: ceiling R17,712/month (payroll.py:138) ✓; 1% employee + 1% employer (max R177.12 each) ✓. **SDL** 1% ✓.
- **CIT 27%** (`CORP_TAX_RATE`, payroll.py:1518, applied :1577) ✓ — also used by the new deferred-tax computation (financial_statements.py `_CIT_RATE = 0.27`). No announced change.
- **VAT 15%** (`VAT_RATE`, payroll.py:885, 1874) ✓ — no announced rate change.
- **EMP201 due-day**: 7th of following month ✓ (unchanged).
- Sources: [SARS — rates of tax for individuals](https://www.sars.gov.za/tax-rates/income-tax/rates-of-tax-for-individuals/), [Stip — SARS tax tables 2026/2027 employer guide](https://stip.co.za/blog/sars-tax-tables-2026-2027), [PAYE Calculator — 2026/2027 tables](https://www.payecalculator.co.za/resources/tax-tables.php), [Accounter — SARS tax tables 2026/2027](https://accounter.co.za/news/sars-tax-tables-2026-2027).

No edits made to tax tables (report-only; the 5b deferred-tax work was separately authorized).

## 8. Action items

1. **[Low — L3]** ~~Deferred tax from fixed-asset temporary differences~~ — **RESOLVED this run** (section 6 above). Post-deploy: restart backend once so the `wear_and_tear_rate` migration runs; optionally assign `sars_category` on existing assets for exact IN47 rates (heuristic covers common categories meanwhile).
2. **[Low — new]** Sync the Note 9 frontend change into `zuzan-app/src/App.js` at the next build/deploy (App_js_fixed.js is the edited master).
3. **[Low — planning]** Unify the two deferred-tax calculators eventually: `/fixed-assets/deferred-tax` (`_calc_tax_base`, uses live `accumulated_depreciation`) vs the new AFS computation (analytic as-at-date). Figures can differ slightly for historical FYs by design; consider having the register view call the shared AFS helper.
4. **[Low — planning]** IFRS for SMEs 3rd-edition transition review ahead of FY2028; secondary/tertiary rebates if 65+ employees onboarded; annual tax task flips `CURRENT_TAX_YEAR` on 1 Mar 2027.

## 9. Changes since last run (2026-07-13)

- Verified the 2026-07-13 same-day fixes in place: reversal-aware AP netting at all four sites; finance costs below EBIT with tax off `profit_before_tax`.
- **Implemented deferred tax (L3)** in database.py, financial_statements.py, and App_js_fixed.js as authorized by section 5b — the last open AFS action item.
- Standards and SARS rates re-verified externally — no changes.
