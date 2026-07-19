# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 19 July 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-07-18 (full PASS). **Note:** payroll.py, main.py, database.py, companies.py and App_js_fixed.js were modified on 18 July *after* that report ran (15:55–16:59), so all audit-scope code in those files was re-verified with fresh reads this run; line numbers below reflect today's files (payroll.py refs shifted ~+120 vs yesterday). financial_statements.py, journal.py, purchase_orders.py and csv_import.py are byte-identical to the last verified versions.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ✅ PASS — all totals ZAR-converted and mutually consistent |
| Debtors (AR) | ✅ PASS — aged from due_date, paid excluded, ZAR amounts |
| Creditors (AP) | ✅ PASS — reversal-aware in all locations, bank details decrypted |
| Cross-module consistency | ✅ PASS — full journal coverage, import-awareness intact |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) implemented 2026-07-14, re-verified |
| Tax rates (SARS) | ✅ PASS — 2026/2027 tables current and web-verified |

**Overall: PASS.** The 18 July afternoon code changes did not touch or regress any audited logic. No new findings; only previously carried low items remain open (section 8).

---

## 2. Reports

✓ No issues found (re-verified after 18 July payroll.py/main.py edits).

- `total_revenue` sums only paid invoices via `_to_zar()` (payroll.py:1130-1134); `_to_zar()` prefers `paid_amount_zar` for paid foreign-currency invoices, falls back to `total_amount × exchange_rate`, ZAR passthrough (payroll.py:17-24). Bank-import income added separately without double-count (payroll.py:1136; `_bank_import_income` reads only journal `bank_import_income` entries, payroll.py:59-86).
- `total_outstanding` covers `sent` + `overdue` with `_to_zar()` (payroll.py:1138-1142). `sent` is the app's "pending" status, so pending + overdue is satisfied.
- Expenses excluded from revenue; taken ex-VAT (payroll.py:1148).
- Payroll included via all-company payslip sum incl. terminated employees, active-employee estimate fallback (payroll.py:1172-1182).
- PO COGS: received/partial/paid POs at delivered-value ex-VAT via `_po_delivered_net` (payroll.py:1153-1158); structural double-count warning against matching expenses (payroll.py:1209-1243). Not double-counted.
- PO input VAT in dashboard VAT position (payroll.py:1200-1203) — 2026-07-07 fix intact.
- Management accounts: period revenue uses `_to_zar()` + bank-import income (payroll.py:1975-1977), delivered-value PO COGS (:2000); the 6-month trend loop applies `_to_zar()`, bank-import income and PO delivered net each month (payroll.py:2067-2076).
- `/v1/summary` imports and uses `_to_zar`, `_po_delivered_net`, `_bank_import_income` consistently with the dashboard (main.py:443-480).

## 3. Debtors

✓ No issues found (re-verified).

- Frontend `Debtors` renders backend `/reports/debtors-aging` verbatim and refreshes on invoice payment (App_js_fixed.js:5930, :5936).
- Backend filters `status IN (sent, overdue)` — paid and draft excluded (payroll.py:2247-2250).
- ZAR equivalents via `_to_zar()` per invoice (payroll.py:2261).
- Aging strictly from `due_date`; invoices without one go to `not_due` — no issue-date fallback (payroll.py:2254-2281). Buckets not_due / 0-30 / 31-60 / 61-90 / 90+ with per-bucket and grand totals (payroll.py:2283-2297).

## 4. Creditors

✓ No issues found (re-verified).

- Frontend `Creditors` renders backend `/reports/creditors-aging` and refreshes on PO payment (App_js_fixed.js:6057, :6063).
- Pulls received/partial POs (payroll.py:2317-2320) + unpaid on-credit expenses; fully paid POs and paid credit expenses excluded (status filter excludes `paid`; `paid_at == None` on credit expenses).
- Supplier bank details decrypted with `decrypt_field` before display (payroll.py:2380-2382).
- Aging from due date = received_date (fallback order_date/created_at) + supplier payment_terms, default 30 (payroll.py:2361-2374).
- **Reversal-awareness (2026-07-13 fixes) verified in all locations** — each nets `SUM(credit − debit)` on account 2000 and includes source `purchase_order_reversal`:
  - payroll.py Rule 7 reconciliation (payroll.py:1664-1687)
  - creditors-aging per-PO lookup (payroll.py:2329-2345), `po.total_amount` fallback when no journal entry exists (payroll.py:2392)
  - purchase_orders.py `pay_po` AP-balance clear (file unchanged since verification of 2026-07-18)
  - journal.py backfill (journal.py:848)
  - financial_statements.py Note 7 (financial_statements.py:552 region — file unchanged since 07-17)

## 5. Cross-module consistency

✓ No issues found.

- Journal coverage complete in journal.py (unchanged since 07-15, freshly re-grepped): `post_invoice_raised` (:194), `post_invoice_paid` (:234), `post_invoice_cogs` (:268), `post_expense` (:293), `post_bank_income` (:328), `post_payroll` (:368), `post_expense_paid` (:447), `post_po_received` (:476), `post_po_paid` (:528), `post_stock_adjustment` (:556), plus idempotent `backfill_company` (:702).
- Debtors Control (1100) and Creditors Control (2000) reconciliation rules compare journal balances to raw invoice/PO totals (payroll.py Rules 6/7, :1622-1699).
- **Import-awareness (2026-07-11 fixes) all re-verified in today's payroll.py:**
  - Invoice/expense imports auto-run journal backfill via `_auto_backfill`; backfill failure never fails the import (csv_import.py:124, :501, :563 — file unchanged)
  - Rules 6/7 exclude `source="import"` lines on 1100/2000, reported as opening balances (payroll.py:1624-1633, :1702-1709)
  - Balance sheet includes 3998 (imported retained earnings) and 3999 (opening balance equity) offsets (payroll.py:1423-1443)
  - Unbalanced journal import groups rejected (csv_import.py:1035-1064)
  - Non-ZAR invoice imports without a positive exchange rate rejected row-by-row (csv_import.py, unchanged)
- database.py was modified 18 July (new company mandate/PSIRA columns); migration hygiene re-checked: all ALTER TABLE strings are inside the migrations list literal, which closes at database.py:1413 and executes in the try/except loop (:1414-1418). Code after the loop is only data backfills (paid_date, portal_token — :1420-1445). No dead-code migrations.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs, declared in the AFS meta and rendered in the frontend (App_js_fixed.js:6241, :11786 — re-verified after yesterday's frontend edits). Statements: income statement, statement of financial position, changes in equity, cash flow (indirect), notes 2–9.

**Standards status (web search 2026-07-19 — unchanged since prior audits):**
- IFRS 18 *Presentation and Disclosure in Financial Statements* — effective annual periods beginning on or after 1 Jan 2027; applies to full-IFRS preparers, not IFRS for SMEs preparers. No ZuZan change required.
- IFRS for SMEs **third edition** (Feb 2025) — confirmed still effective for annual periods beginning on or after 1 Jan 2027, early application permitted. ZuZan's SA FY (1 March–28/29 Feb) first caught by FY beginning 1 March 2027. Not yet mandatory — carried action item L4.
- Standards unchanged since the last audit — moving on per task rules.

**Section 5b — deferred tax: ALREADY IMPLEMENTED (2026-07-14 run) — verified this run, no code changes required or made.** financial_statements.py is unchanged since 2026-07-17; fresh greps confirm:
- Note 9 does **not** hard-code `"deferred_tax": 0.0` — reports period movement `dt_closing − dt_opening`, `total_tax = current + deferred`, opening/closing balances (financial_statements.py:260-262, :595-604).
- `wear_and_tear_rate` column on FixedAsset (database.py:478, alongside `sars_category` :477); ALTER TABLE migration inside the list literal (database.py:1358; list closes :1413; loop :1414-1418) — not dead code, re-confirmed after yesterday's database.py edits.
- Computation (financial_statements.py:78-166): tax base = cost − straight-line SARS wear-and-tear apportioned from purchase date, floor 0; temporary difference × `_CIT_RATE` 27%; rate priority explicit → IN47 category → name heuristic → None (zero difference). No assets / no rates ⇒ exactly 0.0.
- Balance sheet presents closing DTL/DTA as a computed line with matching retained-earnings adjustment (financial_statements.py:342 region, :675); nothing posted to the journal.
- Frontend renders the Note 9 deferred tax row when non-zero, "Nil" otherwise (App_js_fixed.js:11724-11726) and DTL/DTA badges in the asset register (App_js_fixed.js:10255-10292) — re-verified in yesterday's edited frontend.

**Prior fixes re-confirmed via unchanged file + spot greps:** finance costs below EBIT with tax off `profit_before_tax` (financial_statements.py:199-255 region), F1 COGS classifier (2026-07-16), M1/L1 Note 7 fixes (2026-07-17).

✓ No new issues found.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date; `_current_tax_year()` derives it from today's date with newest-table fallback (payroll.py:142-155, resolves to 2026/2027). Rates verified by web search 2026-07-19.

- **PAYE brackets 2026/2027** — TAX_YEARS entry present and matches published tables exactly (payroll.py:127-139): 18% to R245,100; 26% to R383,100; 31% to R530,200; 36% to R695,800; 39% to R887,000; 41% to R1,878,600; 45% above. ✓
- **Primary rebate** R17,820 ✓ (payroll.py:137). Secondary R9,765 / tertiary R3,249 not implemented (carried note — relevant only if 65+ employees onboarded).
- **UIF** 1% + 1% ✓ (payroll.py:161), ceiling R17,712/month ✓ (payroll.py:138, max R177.12 per party). **SDL** 1% ✓ (payroll.py:162).
- **Corporate income tax** 27% unchanged ✓ — dashboard (payroll.py:1186), AFS `_CIT_RATE` (financial_statements.py:78).
- **VAT** 15% unchanged ✓ — Budget 2026 kept the rate (proposed rise ducked). VAT201 constants (payroll.py:1505, :2494). s11F cap R430,000 and 2026/2027 medical tax credits R376/R254 present (payroll.py:166-174).
- **EMP201 due-day** 7th of following month ✓ (payroll.py:1575-1586); IRP6 two-installment logic present ✓; turnover-tax note references the (still-correct) R1,000,000 threshold (payroll.py:2233).
- **New (informational, no code impact):** Budget 2026 raises the compulsory VAT registration threshold R1m → R2.3m and voluntary R50k → R120k from 1 April 2026. Grep confirms ZuZan hard-codes no VAT registration threshold, so nothing to change.

✓ No new issues found. No tax-table edits made (report-only per task rules; 5b needed no edits).

**Sources consulted:** [SARS — Rates of Tax for Individuals](https://www.sars.gov.za/tax-rates/income-tax/rates-of-tax-for-individuals/) · [SARS — Budget 2026 FAQ](https://www.sars.gov.za/about/sars-tax-and-customs-system/budget/budget-2026-frequently-asked-questions/) · [TaxTim — Tax rate tables](https://www.taxtim.com/za/blog/tax-rate-tables) · [PwC Tax Summaries — SA corporate](https://taxsummaries.pwc.com/south-africa/corporate/taxes-on-corporate-income) · [PwC Tax Summaries — SA other taxes](https://taxsummaries.pwc.com/south-africa/corporate/other-taxes) · [vatcalc — SA 2026 Budget VAT](https://www.vatcalc.com/south-africa/south-africa-vat-rise/) · [BDO — Budget 2026 corporate tax](https://www.bdo.co.za/en-za/insights/2026/budget-speech/corporate-tax-remains-unchanged,-with-a-pinch-of-positivity) · [IFRS — IFRS for SMEs](https://www.ifrs.org/issued-standards/ifrs-for-smes/) · [IAS Plus — third IFRS for SMEs](https://www.iasplus.com/en/news/2025/02/third-ifrs-for-smes) · [Nexia SAB&T — IFRS for SMEs 3rd edition](https://www.nexia-sabt.co.za/ifrs-for-smes-accounting-standard-third-edition-2025/)

## 8. Action items

**All three carried low-severity items were CLOSED by same-day fixes (user-requested, 2026-07-19 afternoon):**

| # | Severity | Item | Status |
|---|---|---|---|
| 1 | Low | **L4:** IFRS for SMEs third-edition transition | **Closed** — transition plan written to `audit_reports/ifrs_smes_3rd_edition_transition_plan.md`; no code change needed before FY beginning 1 March 2027; early-2027 runs verify the implementation checklist |
| 2 | Low | Frontend sync; unify deferred-tax calculators; s11F carry-forward; secondary/tertiary rebates | **Closed** — see fix log below |
| 3 | Low | 2027/2028 TAX_YEARS entry | **Closed (provisional)** — entry added flagged `"provisional": True`; annual task must replace with actual Budget Feb 2027 rates and restart the backend |

### Same-day fix log (2026-07-19)

1. **Frontend sync** — already in sync: App_js_fixed.js and zuzan-app/src/App.js are byte-identical (867,343 bytes, both 18 Jul 16:27). No action needed.
2. **Deferred-tax calculators unified** — `/fixed-assets/deferred-tax` now uses the AFS rate resolver `financial_statements._wt_rate_pct` (explicit `wear_and_tear_rate` → IN47 category → name heuristic → None) instead of its category-only logic, so assets with an explicit rate override are no longer silently excluded and the register agrees with AFS Note 9 (fixed_assets.py:102-131; endpoint filter widened, fixed_assets.py:568-584). Rows gain `wt_rate_pct` + `rate_source`; output shape otherwise backward-compatible. CIT rate now has a single source of truth: financial_statements imports `SA_CIT_RATE` from fixed_assets (financial_statements.py:78-84).
3. **s11F excess carry-forward (s11F(3))** — new payslip columns `s11f_excess` / `s11f_carry_used` (database.py:231-232; migrations inside the list literal, database.py:1371-1373). `calc_payroll` accepts `s11f_carry_forward_annual`: deductible pool = current contributions + unclaimed prior-year excess, capped at min(pool, 27.5% × remuneration, R430,000) (payroll.py:448-460). Pool balance computed per employee by `s11f_carry_forward_balance` (payroll.py:524-539) and wired into `/payroll/run` and `/payroll/calculate`. IRP5 annual reconciliation now discloses `s11f_excess_this_year`, `s11f_carry_used_this_year`, `s11f_carry_forward_balance` (payroll.py:833-872). Consumption is annualised monthly (≤ pool/12 per month) so it can never over-deduct; SARS finalises exact relief on assessment.
4. **Secondary/tertiary age rebates** — `secondary_rebate`/`tertiary_rebate` added to all TAX_YEARS entries (2024/2025 & 2025/2026: R9,444/R3,145; 2026/2027: R9,765/R3,249). `calc_paye` takes `age` (cumulative rebates at 65+/75+, payroll.py:328-346); `age_at_tax_year_end` computes age at the last day of the tax year from `Employee.date_of_birth` (payroll.py:311-325); wired into both payroll call sites. Employees without a DOB get the primary rebate only (unchanged behavior).
5. **Provisional 2027/2028 TAX_YEARS entry** — copy of 2026/2027 flagged `"provisional": True` (payroll.py:145-168) so the date-derived selector finds an explicit entry on 1 March 2027. The standing annual task still must load the real Budget 2027 rates.

**Deployment note:** restart the backend to run the two new payslip migrations and load the new tax tables. New payslips created after the restart pick up the rebates/carry-forward automatically; existing payslips are unchanged.

**Remaining open items:** none carried. New standing reminders: (a) replace the provisional 2027/2028 rates after Budget Feb 2027; (b) early-2027 runs execute the IFRS transition-plan checklist.
