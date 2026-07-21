# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 22 July 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-07-21 (full PASS, one Low cosmetic item carried open).

**Change detection since last run (2026-07-21 00:08):** ONE audit-scope file changed — `main.py`, mtime **2026-07-22 00:17:34** (this run's window). The change is part of a large feature commit (debit-order mandate + PDF, once-off PayFast AFS payment, NBCPSS private-security payroll mode, plan-gating changes). Its `/v1/summary` endpoint was re-read line-by-line this run and is unchanged in logic — still correct. All other audit-scope files are **byte-unchanged** since the 07-21 PASS: payroll.py (07-19 10:01), database.py (07-19 10:01), financial_statements.py (07-19 10:02), fixed_assets.py (07-19 10:02), journal.py (07-15), purchase_orders.py (07-13), csv_import.py (07-11), companies.py (07-18), suppliers.py (06-15), customers.py (06-12), App_js_fixed.js (07-18). Key checkpoints across all files were freshly grepped/re-read this run; line references below are confirmed against today's files.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ✅ PASS — `/v1/summary` (main.py, changed today) re-verified; logic intact |
| Debtors (AR) | ✅ PASS — aged from due_date, paid excluded, ZAR amounts |
| Creditors (AP) | ✅ PASS — reversal-aware, bank details decrypted |
| Cross-module consistency | ✅ PASS — full journal coverage, import-awareness intact |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) implemented, re-verified; no code change required |
| Tax rates (SARS) | ✅ PASS — 2026/2027 tables current and web-verified today |

**Overall: PASS.** The only intervening change was a feature commit touching `main.py`; its revenue/outstanding/expense summary logic is unchanged and correct. Spot re-verification found no regressions. One carried-over Low cosmetic item remains open (section 8).

---

## 2. Reports

✓ No issues found.

`main.py` changed today, so `/v1/summary` (main.py:443-488) was re-read in full: `total_revenue` sums only paid invoices via `_to_zar()` (:450) plus `_bank_import_income` (:451); expenses are ex-VAT (:454), add delivered-net PO COGS via `_po_delivered_net` over received/partial/paid POs (:458-464, no double-count), depreciation (:467-470) and all payslip `total_cost` (:474-479); `outstanding` filters `status IN (sent, overdue)` with `_to_zar()` (:449, :480). Expenses are correctly excluded from revenue; net profit = revenue − expenses − payroll (:487).

Dashboard / management (payroll.py, unchanged) re-grepped this run and consistent with the last full verification: `total_revenue` paid-only via `_to_zar()` (payroll.py:1237, helper :17); `total_outstanding` filters `status IN (sent, overdue)` via `_to_zar()` (:1243-1245); management period revenue and the 6-month trend loop apply `_to_zar()` (:2078, :2170); received/partial/paid PO COGS feed expenses without double-count (:1258, :2098, :2181). `sent` is the app's "pending" status.

## 3. Debtors

✓ No issues found.

- Frontend `Debtors` renders backend `/reports/debtors-aging` (App_js_fixed.js:5930, :5936 — unchanged).
- Backend filters `status IN (sent, overdue)` — paid and draft excluded (payroll.py:2352).
- ZAR equivalents via `_to_zar()` per invoice (payroll.py:2364).
- Aging strictly from `due_date`; buckets not_due / current(0-30) / 31-60 / 61-90 / 90+ (payroll.py:2357-2400).

## 4. Creditors

✓ No issues found.

- Frontend `Creditors` renders backend `/reports/creditors-aging` (App_js_fixed.js:6057, :6063).
- Pulls received/partial POs plus unpaid on-credit expenses; fully paid POs and paid credit expenses excluded (payroll.py:2420-2423).
- Supplier bank details decrypted with `decrypt_field` before display (payroll.py:2415, :2483-2485).
- **Reversal-awareness (2026-07-13 fixes) re-confirmed:** `SUM(credit − debit)` netting with source `IN ("purchase_order", "purchase_order_reversal")` at payroll.py:1770-1778 (Rule 7) and :2433-2440 (creditors-aging per-PO); purchase_orders.py pay_po and journal.py backfill unchanged.

## 5. Cross-module consistency

✓ No issues found.

- Journal coverage complete (journal.py unchanged, re-grepped): invoice payments, expense payments, PO receipts, PO payments and payroll runs all covered.
- Debtors Control (1100) / Creditors Control (2000) reconciliation compares journal balances to raw invoice/PO totals (payroll.py:1723-1812).
- **Import-awareness (2026-07-11 fixes)** intact — csv_import.py unchanged: auto-backfill on invoice/expense import, Rules 6/7 exclude `source="import"` on 1100/2000 (payroll.py:1727-1736), balanced-group requirement, non-ZAR invoice imports require a positive exchange rate.
- Migration hygiene: all ALTER TABLE strings inside the migrations list literal; no dead-code migrations.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (declared in AFS meta, rendered in frontend). Statements: income statement, statement of financial position, changes in equity, cash flow (indirect), notes 2–9.

**Standards status (unchanged since prior audit — effective dates are annual, not daily; moving on per task rules):**
- IFRS 18 *Presentation and Disclosure in Financial Statements* — effective annual periods beginning on or after 1 Jan 2027; applies to full-IFRS preparers, not IFRS for SMEs. No ZuZan change required yet.
- IFRS for SMEs **third edition** — effective 1 Jan 2027, early application permitted. ZuZan's SA FY (1 March–28/29 Feb) is first caught by the FY beginning 1 March 2027. Transition plan on file (`ifrs_smes_3rd_edition_transition_plan.md`); early-2027 runs execute its checklist.

**Section 5b — deferred tax: ALREADY IMPLEMENTED — verified fresh, no code change required or made.** financial_statements.py (unchanged since 07-19) re-read:
- Note 9 does **not** hard-code `"deferred_tax": 0.0` — it reports the period movement `dt_closing − dt_opening` (financial_statements.py:266-268, :606), `total_tax = current + deferred` (:601), opening/closing balances and effective rate (:608-610).
- Computation `_deferred_tax_balance` (financial_statements.py:131-173): tax base = cost − straight-line SARS wear-and-tear apportioned monthly, floored at 0; temporary difference = carrying value − tax base, × `_CIT_RATE` (from fixed_assets `SA_CIT_RATE`, fallback 0.27, :81-84). No assets / no rates ⇒ exactly 0.0; output shape backward-compatible.
- `wear_and_tear_rate` column on FixedAsset with its ALTER TABLE inside the migrations list literal (not dead code).
- Balance sheet presents closing DTL/DTA as a computed line with matching retained-earnings adjustment; nothing posted to the journal. Frontend renders the Note 9 deferred-tax row when non-zero.

**Finance costs (2026-07-13 fix) re-confirmed:** `profit_before_tax = ebit − finance_costs`; tax and net profit derive from profit_before_tax, not EBIT (financial_statements.py:259-261).

**Carried-over Low item still open:** financial_statements.py:260 computes current tax with literal `0.27` (and :604/:641 hard-code `27.0` for `tax_rate_pct`) instead of `_CIT_RATE`. Value identical today; cosmetic only.

✓ No new issues found.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date; `_current_tax_year()` derives it from today's date with newest-table fallback (payroll.py:171-182). Rates re-verified by web search 2026-07-22.

- **PAYE brackets 2026/2027** — TAX_YEARS entry present (payroll.py:131-145); 7 brackets, 18% to R245,100 … 45% above R1,878,600. Web-confirmed. ✓
- **Rebates** — primary R17,820 ✓ (payroll.py:141), secondary R9,765 ✓ (:142), tertiary R3,249 ✓ (:143). Web search confirmed the 2026/2027 secondary rebate rose R9,444→**R9,765** and tertiary R3,145→**R3,249** in Budget 2026 (one aggregator returned the stale prior-year R9,444/R3,145; SARS/Nexia/PwC sources confirm the code's values are current).
- **UIF** 1% employee + 1% employer ✓ (payroll.py:188), ceiling R17,712/month ✓ (:144). **SDL** 1% ✓ (:189).
- **Corporate income tax** 27% unchanged per Budget 2026 ✓ — dashboard (payroll.py:1289), management accounts (:2144), provisional tax (:2241), AFS via `SA_CIT_RATE`.
- **VAT** 15% unchanged ✓ — the previously proposed increase was withdrawn; Budget 2026 kept 15% (payroll.py:1608). Compulsory registration threshold rose R1m→R2.3m and voluntary R50k→R120k effective 1 April 2026 — ZuZan does not gate on these thresholds, so no code impact (informational only).
- **s11F** cap and **medical tax credits** (R376/R254, effective 1 March 2026) current for 2026/2027 ✓ (payroll.py:195-201).
- **Provisional 2027/2028 entry** present and flagged `"provisional": True` (payroll.py:151-166) — a copy of 2026/2027 pending Budget Feb 2027; standing annual task replaces it, then restart the backend.
- Rates unchanged and current tax year present — no edits made (report-only per task rules; 5b needed no edits this run).

**Sources consulted:** [Govchain — PAYE 2026/2027](https://www.govchain.co.za/blog/how-to-calculate-paye-in-south-africa) · [Stip — SARS Tax Tables 2026/2027](https://stip.co.za/blog/sars-tax-tables-2026-2027) · [Tax Brackets South Africa 2026/2027](https://taxplanners.co.za/tax-brackets-south-africa/) · [SARS — Budget 2026 FAQ](https://www.sars.gov.za/about/sars-tax-and-customs-system/budget/budget-2026-frequently-asked-questions/) · [PwC — SA individual other tax credits](https://taxsummaries.pwc.com/south-africa/individual/other-tax-credits-and-incentives) · [Nexia SABT — Tax Guide 2026/2027](https://www.nexia-sabt.co.za/wp-content/uploads/2026/02/Nexia-SABT-Tax-Guide-2026-Digital.pdf) · [BDO — Corporate tax unchanged (Budget 2026)](https://www.bdo.co.za/en-za/insights/2026/budget-speech/corporate-tax-remains-unchanged,-with-a-pinch-of-positivity) · [vatcalc — SA 2026 Budget ducks VAT rise](https://www.vatcalc.com/south-africa/south-africa-vat-rise/) · [SAnews — VAT increase withdrawn](https://www.sanews.gov.za/south-africa/proposed-vat-increase-officially-withdrawn) · [IFRS — for SMEs third edition](https://www.ifrs.org/news-and-events/news/2025/02/iasb-issues-major-update-smes-accounting-standard/) · [IAS Plus — IFRS 18 effective date](https://www.iasplus.com/en/events/effective-dates/2027/ifrs-18)

## 8. Action items

| # | Severity | Item |
|---|---|---|
| 1 | Low | **Carried over (07-20 → 07-22):** financial_statements.py:260 computes current tax with literal `0.27` (and :604/:641 `tax_rate_pct: 27.0`); use `_CIT_RATE` for single-source-of-truth consistency. No financial impact today. |

**Standing reminders (not defects):** (a) replace the provisional 2027/2028 TAX_YEARS entry after Budget Feb 2027 and restart the backend; (b) early-2027 runs execute the IFRS for SMEs 3rd-edition transition-plan checklist; (c) VAT registration thresholds changed 1 Apr 2026 (compulsory R2.3m, voluntary R120k) — informational only, no code gate exists.

**Note for next run:** `main.py` was modified during this run's window (feature commit: debit orders, PayFast AFS payment, NBCPSS private-security payroll mode, plan gating). Only `/v1/summary` is in audit scope and was verified unchanged in logic. The new private-security payroll mode did not alter payroll.py's tax engine (byte-unchanged); if that mode later moves PAYE/UIF/SDL logic into main.py or companies.py, re-scope the payroll tax checks accordingly.
