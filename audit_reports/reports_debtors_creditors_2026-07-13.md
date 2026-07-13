# Reports / Debtors / Creditors Audit — 2026-07-13

Scope: `/reports/dashboard`, `/reports/management`, `/v1/summary`, Debtors (AR), Creditors (AP), cross-module journal coverage, IFRS compliance (AFS), SARS tax rates.
Files reviewed: payroll.py, main.py, journal.py, purchase_orders.py, companies.py, csv_import.py, financial_statements.py, database.py, App_js_fixed.js.

Prior report: 2026-07-12. Change detection: **no source files have changed since the last audit run.** Latest backend mtime is main.py (2026-07-11 12:59); App_js_fixed.js's mtime (2026-07-12 08:11) falls within the last audit run window, when the L5 drill-down fix was applied. This run therefore spot-verified the prior report's key claims against the code rather than re-deriving every finding.

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | **PASS** |
| Debtors (AR) | **PASS** |
| Creditors (AP) | **PASS** |
| Cross-module | **PASS** — L1 (Low) carried over |
| IFRS compliance (AFS) | **PASS** — standards unchanged |
| Tax (company + payroll) | **PASS** — 2026/2027 tables re-verified against SARS |

No new findings this run. No regressions. Codebase static since 2026-07-12.

## 2. Reports

✓ No issues found.

- `total_revenue`: paid invoices only via `_to_zar()` (payroll.py:510–514) + bank-import income (:516). `_to_zar` (payroll.py:17–22) prefers `paid_amount_zar`, falls back to amount × exchange_rate, ZAR passthrough — verified.
- `total_outstanding`: sent + overdue via `_to_zar()` (payroll.py:518–522) — verified.
- Expenses ex-VAT, excluded from revenue (payroll.py:524–528); PO COGS uses delivered value only (`_po_delivered_net`, comment at :530–533) — no double-counting.
- `/v1/summary` (main.py:269–303) imports and uses `_to_zar`, `_po_delivered_net`, `_bank_import_income` — verified intact.
- Frontend drills: dashboard (App_js_fixed.js:579) and management accounts (:4007) both filter `["sent","overdue"]` — **yesterday's L5 fix confirmed in place**; bank-match modal (:5810–5812) consistent.

## 3. Debtors

✓ No issues found.

- `/reports/debtors-aging` (payroll.py:1614–1674): status IN (sent, overdue) only (:1625); paid/draft excluded; `_to_zar()` per invoice (:1637); aging strictly from `due_date` with no-due-date invoices in `not_due` (:1631–1649). Buckets not_due / 0–30 / 31–60 / 61–90 / 90+ with grand total.
- Frontend `Debtors` backend-driven — unchanged since last audit.
- Import fixes: auto-backfill after invoice/expense import (csv_import.py:124–143, 501, 563); non-ZAR rows without an exchange rate rejected (csv_import.py:458–463) — verified intact.

## 4. Creditors

✓ No issues found.

- `/reports/creditors-aging` (payroll.py:1677+): received/partial POs only (:1695); fully-paid excluded; AP balance from journal credits on account 2000 (:1701–1718); aged from received date + supplier payment terms; supplier bank details decrypted via `decrypt_field` (:1753–1755) — all verified.
- L1 remains visible: the per-PO AP lookup sums credits only (payroll.py:1706) without netting reversal debits — still unreachable in practice (see §8).

## 5. Cross-module

✓ No issues found beyond the carried-over Low.

- Journal posting coverage unchanged: invoice raised/payment, expense + expense payment (companies.py), PO receipt/payment (purchase_orders.py), payroll run (payroll.py), bank-import income (journal.py:317–338), import backfill (csv_import.py).
- Import-awareness fixes of 2026-07-11 all verified intact:
  - Rules 6/7 exclude `source="import"` lines on 1100/2000 (payroll.py:1004–1013, 1077–1085).
  - Balance sheet includes 3999 Opening Balance Equity and 3998 imported Retained Earnings (payroll.py:803–823); csv_import.py creates/offsets them (:726–733, 925–946).
  - Unbalanced journal import groups rejected with per-row error (csv_import.py:1035–1064).
  - Non-ZAR invoice imports require an exchange rate (csv_import.py:458–463).
- Debtors Control (1100) / Creditors Control (2000) reconciliation logic unchanged; no schema changes since last audit.

## 6. IFRS compliance (AFS)

✓ No issues found. Standards unchanged since last audit.

- Framework: **IFRS for SMEs** (financial_statements.py:2 docstring, :410 meta basis, :499–502 basis-of-preparation note citing Section 23) — correct for a SA private company under Companies Act 71 of 2008 regulations.
- M4 accrual fix of 2026-07-11 verified intact: Note 3 receivables aging via `_inv_total_zar` (:64, 275–286); Note 4 revenue by customer over all issued invoices — sent/overdue/paid (:297–304).
- Standards status re-verified 13 July 2026 — unchanged: IFRS for SMEs 3rd edition effective for periods beginning on/after 1 Jan 2027 (first mandatory ZuZan FY: 1 Mar 2027 – 29 Feb 2028), earlier application permitted; IFRS 18 (effective 1 Jan 2027) applies to full-IFRS preparers only and does not bind an IFRS for SMEs entity. Current statements remain compliant on the 2015 second edition.
- Sources: [IFRS Foundation — IFRS for SMEs](https://www.ifrs.org/issued-standards/ifrs-for-smes/), [IASB third edition announcement](https://www.ifrs.org/news-and-events/news/2025/02/iasb-issues-major-update-smes-accounting-standard/), [PwC Viewpoint — third edition In brief](https://viewpoint.pwc.com/dt/gx/en/pwc/in_briefs/in_briefs_INT/in_briefs_INT/iasb-issues.html), [ICAEW — IFRS for SMEs tracker](https://www.icaew.com/technical/corporate-reporting/ifrs/ifrs-accounting-standards-tracker/ifrs-for-smes).
- Carried-over Lows: `deferred_tax` hard-coded 0.0 (financial_statements.py:395); `finance_costs` hard-coded 0.0 (:424).

## 7. Tax updates (company + payroll)

✓ No issues found. Current SARS tax year: **2026/2027** (1 Mar 2026 – 28 Feb 2027). Re-verified against SARS-sourced tables — all rates current:

- **PAYE 2026/2027** (payroll.py:127–139): brackets 18% ≤ R245,100 / 26% to R383,100 / 31% to R530,200 / 36% to R695,800 / 39% to R887,000 / 41% to R1,878,600 / 45% above ✓ — match published 2026/2027 tables. Primary rebate R17,820 ✓ (tax-free threshold R99,000 under 65). Secondary/tertiary rebates still not implemented — acceptable; noted as future enhancement.
- **Tax-year selection**: `CURRENT_TAX_YEAR = "2026/2027"` (payroll.py:142); safe fallback in `calc_paye`/`calc_payroll` (:206, 240) ✓. Annual task must flip on 1 Mar 2027.
- **UIF**: ceiling R17,712/month (payroll.py:138) ✓, 1% employee + 1% employer (max R177.12 each) ✓ — confirmed unchanged. **SDL** 1% ✓.
- **CIT 27%** (`CORP_TAX_RATE`, payroll.py:1514, applied :1573) ✓ — no announced change.
- **VAT 15%** (`VAT_RATE`, payroll.py:885, 1867) ✓ — no announced rate change.
- **EMP201 due-day**: 7th of following month ✓ (unchanged).
- Sources: [SARS — rates of tax for individuals](https://www.sars.gov.za/tax-rates/income-tax/rates-of-tax-for-individuals/), [SARS — Budget 2026 FAQ](https://www.sars.gov.za/about/sars-tax-and-customs-system/budget/budget-2026-frequently-asked-questions/), [Stip — SARS tax tables 2026/2027 employer guide](https://stip.co.za/blog/sars-tax-tables-2026-2027), [TaxTim — 2027 PAYE calculator](https://www.taxtim.com/za/calculators/income-tax).

No edits made to tax tables (report-only per task instructions).

## 8. Action items

All carried over from prior runs; nothing new:

1. **[Low — L1]** ~~Make per-PO AP-credit lookups reversal-aware~~ — **RESOLVED same day**: all four sites now net `credit − debit` and include `source="purchase_order_reversal"` (payroll.py Rule 7 + creditors-aging, purchase_orders.py pay_po, journal.py backfill).
2. **[Low — L3]** Revisit deferred-tax disclosure once fixed-asset temporary differences are material (financial_statements.py).
3. **[Low — L4]** ~~Wire `finance_costs` to journal interest accounts~~ — **RESOLVED same day**: new default account 6700 Finance Costs (Interest Paid) + "Interest"/"Finance Costs" category mappings (journal.py); AFS now presents interest lines below EBIT with true `profit_before_tax` driving tax and net profit (financial_statements.py); AFS frontend shows Finance Costs / Profit Before Tax rows when non-zero (App_js_fixed.js).
4. **[Low — planning]** IFRS for SMEs 3rd-edition transition review ahead of FY2028; secondary/tertiary rebates if 65+ employees onboarded; annual tax task flips `CURRENT_TAX_YEAR` on 1 Mar 2027.

## 9. Changes since last run (2026-07-12)

None. No source file has been modified since the last audit. All prior fixes (M4 accrual basis, L5 drill-down filter, 2026-07-11 import-awareness set) verified intact by spot-check. Standards and tax rates re-verified externally — no changes.
