# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 21 July 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-07-20 (full PASS, one Low cosmetic item logged).

**Change detection since last run (2026-07-20 00:09):** NO audit-scope file has been modified — latest mtime is main.py 2026-07-19 20:18, which the 07-20 report already re-verified line-by-line (content-neutral reordering). All files (payroll.py, database.py, financial_statements.py, journal.py, purchase_orders.py, csv_import.py, companies.py, suppliers.py, customers.py, main.py, App_js_fixed.js) are byte-unchanged since the prior verified PASS. Key checkpoints were still freshly re-read/grepped this run; line references below confirmed against today's files.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ✅ PASS — unchanged since verified 07-20 run |
| Debtors (AR) | ✅ PASS — aged from due_date, paid excluded, ZAR amounts |
| Creditors (AP) | ✅ PASS — reversal-aware, bank details decrypted |
| Cross-module consistency | ✅ PASS — full journal coverage, import-awareness intact |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) implemented 2026-07-14, re-verified fresh |
| Tax rates (SARS) | ✅ PASS — 2026/2027 tables current and web-verified today |

**Overall: PASS.** Zero code changes since yesterday's full PASS; spot re-verification found no regressions. One carried-over Low cosmetic item remains open (section 8).

---

## 2. Reports

✓ No issues found (code unchanged since 07-20 full verification).

Fresh spot-checks this run: `total_revenue` sums only paid invoices via `_to_zar()` (payroll.py:1237, helper :17); `total_outstanding` filters `status IN (sent, overdue)` with `_to_zar()` (payroll.py:1243-1245) — `sent` is the app's "pending" status; management-accounts period revenue and 6-month trend loop apply `_to_zar()` (payroll.py:2078, :2170); `/v1/summary` (main.py:443-488) unchanged since its 07-20 line-by-line re-read. Expense exclusion from revenue, payroll cost inclusion, delivered-value PO COGS without double-count, and PO input VAT in the dashboard VAT position all verified in detail on 07-20 with no intervening edits.

## 3. Debtors

✓ No issues found.

- Frontend `Debtors` renders backend `/reports/debtors-aging` (App_js_fixed.js:5930, :5936 — file unchanged since 07-18).
- Backend filters `status IN (sent, overdue)` — paid and draft excluded (payroll.py:2352, re-read today).
- ZAR equivalents via `_to_zar()` per invoice (payroll.py:2364).
- Aging strictly from `due_date` (no issue-date fallback); buckets not_due / current(0-30) / 31-60 / 61-90 / 90+ (payroll.py:2357-2400).

## 4. Creditors

✓ No issues found.

- Frontend `Creditors` renders backend `/reports/creditors-aging` (App_js_fixed.js:6057, :6063).
- Pulls received/partial POs plus unpaid on-credit expenses; fully paid POs and paid credit expenses excluded (payroll.py:2420-2423, :2515-2519).
- Supplier bank details decrypted with `decrypt_field` before display (payroll.py:2415, :2483-2485 — re-read today).
- Aging from received_date + supplier payment_terms (default 30); credit expenses from expense_date + 30 (payroll.py:2464-2477, :2521-2526).
- **Reversal-awareness (2026-07-13 fixes) re-confirmed:** `SUM(credit − debit)` netting with source `IN ("purchase_order", "purchase_order_reversal")` at payroll.py:1770-1778 (Rule 7), payroll.py:2433-2440 (creditors-aging per-PO), purchase_orders.py:438-445 (pay_po), journal.py:848 (backfill), financial_statements.py Note 7 (:541-554).

## 5. Cross-module consistency

✓ No issues found.

- Journal coverage complete (journal.py unchanged since 07-15, re-grepped today): `post_invoice_paid` (:234), `post_payroll` (:368), `post_expense_paid` (:447), `post_po_received` (:476), `post_po_paid` (:528), plus invoice-raised/COGS/expense/bank-income/stock-adjustment posters and idempotent `backfill_company`. Invoice payments, expense payments, PO receipts, PO payments and payroll runs all covered.
- Debtors Control (1100) / Creditors Control (2000) reconciliation rules compare journal balances to raw invoice/PO totals (payroll.py:1723-1812).
- **Import-awareness (2026-07-11 fixes)** intact — csv_import.py unchanged since 07-11: auto-backfill on invoice/expense import (:124, :501, :563), Rules 6/7 exclude `source="import"` on 1100/2000 (payroll.py:1727-1736), 3998/3999 equity offsets in the balance sheet, unbalanced journal import groups rejected (:1035-1064), non-ZAR invoice imports require a positive exchange rate (:458-475).
- Migration hygiene: all ALTER TABLE strings inside the migrations list literal (closes database.py:1418, loop :1419-1424); no dead-code migrations.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs, declared in AFS meta and rendered in the frontend (App_js_fixed.js:6241, :11786). Statements: income statement, statement of financial position, changes in equity, cash flow (indirect), notes 2–9.

**Standards status (web search 2026-07-21 — unchanged since prior audit, moving on per task rules):**
- IFRS 18 *Presentation and Disclosure in Financial Statements* — effective annual periods beginning on or after 1 Jan 2027; applies to full-IFRS preparers, not IFRS for SMEs preparers. No ZuZan change required yet.
- IFRS for SMEs **third edition** (Feb 2025) — effective 1 Jan 2027, early application permitted; IASB is publishing the remaining educational modules in Q3 2026. ZuZan's SA FY (1 March–28/29 Feb) is first caught by the FY beginning 1 March 2027. Transition plan on file (`audit_reports/ifrs_smes_3rd_edition_transition_plan.md`); early-2027 runs execute its checklist.

**Section 5b — deferred tax: ALREADY IMPLEMENTED (2026-07-14) — verified fresh this run, no code changes required or made.** financial_statements.py (unchanged since 07-19 10:02) re-read today:
- Note 9 does **not** hard-code `"deferred_tax": 0.0` — it reports the period movement `dt_closing − dt_opening` (financial_statements.py:266-268), `total_tax = current + deferred`, opening/closing balances and effective rate (:601-611).
- Computation `_deferred_tax_balance` (financial_statements.py:131-173): tax base = cost − straight-line SARS wear-and-tear apportioned monthly, floored at 0; temporary difference = carrying value − tax base, × `_CIT_RATE` (imported from fixed_assets `SA_CIT_RATE`, fallback 0.27, :81-84). Rate priority: explicit `wear_and_tear_rate` → IN47 `sars_category` → category-name heuristic (:89-124) → None ⇒ zero difference. Disposed assets reverse (:149-150); no assets / no rates ⇒ exactly 0.0; output shape backward-compatible.
- `wear_and_tear_rate` column on FixedAsset with its ALTER TABLE inside the migrations list literal (database.py:480, :1360) — not dead code.
- Balance sheet presents the closing DTL/DTA as a computed line with matching retained-earnings adjustment; nothing posted to the journal. Frontend renders the Note 9 deferred-tax row when non-zero (App_js_fixed.js:11724-11726).

**Finance costs (2026-07-13 fix) re-confirmed:** `profit_before_tax = ebit − finance_costs`; tax and net profit derive from profit_before_tax, not EBIT (financial_statements.py:257-261).

**Carried-over Low item still open:** financial_statements.py:260 computes current tax with literal `0.27` (and :604 hard-codes `27.0` for `tax_rate_pct`) instead of `_CIT_RATE`. Value identical today; cosmetic only.

✓ No new issues found.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date; `_current_tax_year()` derives it from today's date with newest-table fallback (payroll.py:169-182). Rates re-verified by web search 2026-07-21.

- **PAYE brackets 2026/2027** — TAX_YEARS entry present and matches SARS published tables exactly (payroll.py:131-145): 18% to R245,100; 26% to R383,100 (base R44,118); 31% to R530,200 (R79,998); 36% to R695,800 (R125,599); 39% to R887,000 (R185,215); 41% to R1,878,600 (R259,783); 45% above (R666,339). ✓
- **Rebates** — primary R17,820 ✓, secondary R9,765 ✓, tertiary R3,249 ✓ (payroll.py:141-143).
- **UIF** 1% employee + 1% employer ✓ (payroll.py:188), ceiling R17,712/month ✓ (payroll.py:144 — unchanged since June 2021, not adjusted in Budget 2026). **SDL** 1% ✓ (payroll.py:189).
- **Corporate income tax** 27% unchanged per Budget 2026 ✓ — dashboard (payroll.py:1289), management accounts (:2144), provisional tax (:2241), AFS via `SA_CIT_RATE`.
- **VAT** 15% unchanged ✓ — the previously proposed increase was withdrawn; Budget 2026 kept 15% (payroll.py:1608, :2597). Note: compulsory VAT registration threshold rose R1m → R2.3m effective 1 April 2026 — ZuZan does not currently gate on this threshold, so no code impact; worth a UX hint someday (not logged as a defect).
- **s11F** cap R430,000 (payroll.py:195-196) and **medical tax credits** R376/R254 (payroll.py:200-201) current for 2026/2027 ✓.
- **Provisional 2027/2028 entry** present and flagged `"provisional": True` (payroll.py:151-166) — standing annual task replaces it with actual Budget Feb 2027 rates, then restart the backend.
- Rates unchanged and current tax year present — no edits made (report-only per task rules; 5b needed no edits).

**Sources consulted:** [SARS Tax Tables 2026/2027 — Stip](https://stip.co.za/blog/sars-tax-tables-2026-2027) · [Tax Brackets South Africa 2026/2027](https://taxplanners.co.za/tax-brackets-south-africa/) · [TaxTim — Tax bracket calculator](https://www.taxtim.com/za/calculators/tax-bracket) · [vatcalc — SA 2026 Budget ducks VAT rise](https://www.vatcalc.com/south-africa/south-africa-vat-rise/) · [SAnews — VAT increase withdrawn](https://www.sanews.gov.za/south-africa/proposed-vat-increase-officially-withdrawn) · [BDO — Corporate tax unchanged (Budget 2026)](https://www.bdo.co.za/en-za/insights/2026/budget-speech/corporate-tax-remains-unchanged,-with-a-pinch-of-positivity) · [PwC Tax Summaries — South Africa](https://taxsummaries.pwc.com/south-africa/corporate/other-taxes) · [IFRS — IFRS for SMEs third edition](https://www.ifrs.org/news-and-events/news/2025/02/iasb-issues-major-update-smes-accounting-standard/) · [IFRS — June 2026 SMEs update](https://www.ifrs.org/supporting-implementation/2015-ifrs-for-smes-supporting-materials/sme-updates/2026/june-2026-ifrs-for-smes-accounting-standard-update/) · [IAS Plus — IFRS 18 effective date](https://www.iasplus.com/en/events/effective-dates/2027/ifrs-18)

## 8. Action items

| # | Severity | Item |
|---|---|---|
| 1 | Low | **Carried over (07-20):** financial_statements.py:260 computes current tax with literal `0.27` (and :604 `tax_rate_pct: 27.0`); use `_CIT_RATE` for single-source-of-truth consistency. No financial impact today. |

**Standing reminders (not defects):** (a) replace the provisional 2027/2028 TAX_YEARS entry after Budget Feb 2027 and restart the backend; (b) early-2027 runs execute the IFRS for SMEs 3rd-edition transition-plan checklist; (c) VAT registration threshold now R2.3m (1 Apr 2026) — informational only, no code gate exists.
