# Reports / Debtors / Creditors Audit — 2026-07-11 (run 2, evening)

Scope: `/reports/dashboard`, `/reports/management`, `/v1/summary`, Debtors (AR), Creditors (AP), cross-module journal coverage, **IFRS compliance of the AFS module (new checklist section)**, **SARS tax rates (new checklist section)**.
Files reviewed: payroll.py, main.py, journal.py, purchase_orders.py, companies.py, suppliers.py, csv_import.py, financial_statements.py, App_js_fixed.js.

This run supersedes the 09:41 report of the same date. Primary purpose: verify the six same-day fixes from the morning run (H1, H2, M1, M2, M3, L2) are intact in code, and perform the first audit under the expanded checklist (IFRS + SARS tax verification).

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | **PASS** — all checklist items verified |
| Debtors (AR) | **PASS** — morning fixes H1/M3 verified in code |
| Creditors (AP) | **PASS** — no issues |
| Cross-module | **PASS** — morning fixes H2/M1/M2/L2 verified; only L1 (Low) carried over |
| IFRS compliance (AFS) | **PASS with findings** — correct framework (IFRS for SMEs); one Medium policy issue (cash-basis revenue), 3rd-edition transition due FY2028 |
| Tax (company + payroll) | **PASS** — 2026/2027 PAYE tables, rebate, UIF, SDL, CIT 27%, VAT 15% all current per Budget 2026 |

## 2. Reports

✓ No issues found.

- `total_revenue` sums only `InvoiceStatus.paid` via `_to_zar()` (payroll.py:510–516); `_to_zar` (payroll.py:17–23) prefers `paid_amount_zar`, falls back to `amount × exchange_rate`, ZAR passthrough.
- `total_outstanding` = sent + overdue via `_to_zar()` (payroll.py:518–522). Note: the status enum has no separate "pending" — `sent` is "pending".
- Expenses excluded from revenue; ex-VAT in P&L (payroll.py:524–528).
- Payroll from all payslips incl. terminated employees, estimate fallback (payroll.py:552–562).
- PO COGS at delivered value `_po_delivered_net` for received/partial/paid (payroll.py:530–538); journal posts on receipt instead of Expense rows — no structural double-count.
- Management trend loop applies `_to_zar()` + bank-import income per month (payroll.py:1443–1447); PO COGS and depreciation per period (1452–1465).
- `/v1/summary` mirrors dashboard: `_to_zar`, `_po_delivered_net`, `_bank_import_income` (main.py:264–309).

## 3. Debtors

✓ No issues found.

- `/reports/debtors-aging` (payroll.py:1614–1674): filters `status IN (sent, overdue)` — paid and draft excluded (1623–1626); `_to_zar()` per invoice (1637); aged strictly from `due_date`, no-due-date invoices parked in `not_due` (1631–1649); buckets not_due / 0–30 / 31–60 / 61–90 / 90+ with correct totals.
- Frontend `Debtors` (App_js_fixed.js:4744–4750) renders backend data only, refreshes on invoice changes.
- **Morning fix H1 verified intact:** `/import/invoices` and `/import/expenses` auto-run the idempotent journal backfill after commit (`_auto_backfill`, csv_import.py:124–136; called at 501, 563); backfill errors surface without failing the import.
- **Morning fix M3 verified intact:** non-ZAR imported invoices without a positive `exchange_rate` are rejected with a clear error; ZAR rows forced to rate 1.0; `paid_amount_zar = total × rate` (csv_import.py:458–492).

## 4. Creditors

✓ No issues found.

- `/reports/creditors-aging` (payroll.py:1677–1830): received/partial POs only — fully paid excluded (1693–1696); per-PO AP from actual journal credits on account 2000 with fallback (1698–1718); unpaid on-credit expenses included; aged from `received_date + supplier payment_terms` (1739–1740).
- Supplier bank details decrypted via `decrypt_field` before display (payroll.py:1688, 1753–1755).
- `pay_po` clears the true journal AP balance, not `total_amount` (purchase_orders.py:427–461).
- Frontend `Creditors` (App_js_fixed.js:4871–4877) backend-driven.

## 5. Cross-module

Journal event coverage — all wired:

| Event | Posting fn | Called from |
|---|---|---|
| Invoice raised | journal.py:181 | companies.py:251, 367, 381, 455 |
| Invoice payment | journal.py:221 | companies.py:383, portal.py:205 |
| Expense (cash/credit) | journal.py:280 | companies.py:554, 644, 961 |
| Expense payment | journal.py:392 | companies.py:699 |
| PO receipt (incremental) | post_po_received | purchase_orders.py:355 |
| PO payment | post_po_paid | purchase_orders.py:461 |
| Payroll run | journal.py:355 | payroll.py:407 |
| Bank-import income | journal.py:315 | companies.py:996 |
| Import backfill | journal.py:688–729 | csv_import.py:501, 563 (auto) |

Import-awareness fixes of 2026-07-11 (morning run) — **all verified intact**:

- Rules 6/7 exclude source `"import"` lines on 1100/2000 (`ar_import_bal` payroll.py:1008–1027; `ap_import_bal` 1080–1102) and report them as imported opening balances.
- Balance sheet includes 3999 Opening Balance Equity, 3998 imported Retained Earnings, `other_equity`, `other_assets`, `other_liabilities` (payroll.py:762–870).
- Unbalanced journal import groups are DR/CR-validated before entry creation and rejected with "group NOT imported" (csv_import.py:1034–1070).
- `_find_or_create_account` matches names case-insensitively/trimmed (csv_import.py:699–708).

Carried over: **[L1]** per-PO AP-credit lookups (payroll.py:1698–1718; purchase_orders.py:427–448) sum credits under source `"purchase_order"` only and ignore reversal debits. Still unreachable in practice (2026-07-09).

## 6. IFRS compliance (AFS)

Framework implemented: **IFRS for SMEs** — stated in the module docstring (financial_statements.py:2), meta `basis` (386), and the basis-of-preparation note (473–475). Appropriate for a SA private company under Companies Act 71 of 2008 regulations.

Standards status as at 11 July 2026 (web-verified):

- **IFRS for SMEs 3rd edition** (issued Feb 2025): effective for annual periods beginning **on or after 1 Jan 2027**, early application permitted. Under the app's SA FY convention (1 Mar – 28/29 Feb, financial_statements.py:24–29), the first mandatory FY is **1 Mar 2027 – 29 Feb 2028 (FY2028)**. Current statements may continue on the 2015 second edition — compliant today, transition work needed before FY2028.
- **IFRS 18** (replacing IAS 1, effective 1 Jan 2027): applies to **full-IFRS** preparers only — **not applicable** to an IFRS for SMEs entity. No action needed unless a client elects full IFRS.
- Sources: [IFRS Foundation — IFRS for SMEs](https://www.ifrs.org/issued-standards/ifrs-for-smes/), [IAS Plus — third edition](https://www.iasplus.com/en/news/2025/02/third-ifrs-for-smes), [IAS Plus — IFRS 18 effective date](https://www.iasplus.com/en/events/effective-dates/2027/ifrs-18), [PKF SA — SMEs framework changes](https://www.pkf.co.za/news/2026/ifrs-for-sme-conceptual-framework/).

Statement completeness (Section 3.17 of IFRS for SMEs): income statement ✓ (389–405), balance sheet ✓ (406–429), statement of changes in equity ✓ (430–440), cash flow — indirect method ✓ (441–461), notes incl. accounting policies ✓ (462–496). Titles "Income Statement"/"Balance Sheet" are permitted alternatives under para 3.22 (not misleading) — cosmetic only.

Findings:

- **[M4 — Medium] Cash-basis revenue recognition is not IFRS for SMEs-compliant.** The policy note states "Revenue is recognised when invoices are settled by customers (cash basis)" (financial_statements.py:476–478) and the income statement is built accordingly. Section 23 (3rd ed: Section 23 revised) requires accrual recognition — revenue when the performance obligation is satisfied (normally on invoice/delivery), not on receipt. The disclosure is honest, but statements prepared this way cannot claim IFRS for SMEs compliance in the basis note. Fix: recognise revenue on issued (sent/overdue/paid) invoices with a trade-receivables movement, or soften the basis wording to "prepared on the entity's accounting policies, which approximate IFRS for SMEs except for revenue recognition".
- **[L3 — Low] `deferred_tax` hard-coded 0.0** (financial_statements.py:371) while the policy note says deferred tax "is not separately disclosed" (494). Acceptable for condensed statements; note if fixed-asset temporary differences grow.
- **[L4 — Low] `finance_costs` hard-coded 0.0** (financial_statements.py:400). Correct while the app has no loan module; will silently misstate once bank feeds bring interest expense in.

## 7. Tax updates (company + payroll)

Current SARS tax year at run date: **2026/2027** (1 Mar 2026 – 28 Feb 2027).

All rates verified against Budget 2026 (25 Feb 2026) sources — **all current, no changes required**:

- **PAYE brackets 2026/2027** (payroll.py:127–139): match the gazetted tables exactly — 18% to R245,100; 26% to R383,100 (base R44,118); 31% to R530,200 (R79,998); 36% to R695,800 (R125,599); 39% to R887,000 (R185,215); 41% to R1,878,600 (R259,783); 45% above (R666,339). Bracket bases arithmetically re-verified. Budget 2026 adjusted brackets upward 3.4% — correctly reflected.
- **Primary rebate** R17,820 (payroll.py:137) ✓. Secondary/tertiary rebates (R9,765 / R3,249) are not implemented — acceptable while the payroll module has no employee date-of-birth-driven rebate logic; note as future enhancement.
- **UIF**: ceiling R17,712/month (payroll.py:138) ✓ (unchanged since June 2021); employee/employer 1% each (148) ✓; overtime excluded from UIF base (253–255) ✓.
- **SDL**: 1% (149) with R500,000 annual-payroll exemption threshold (259–260) ✓.
- **Tax-year selection**: `CURRENT_TAX_YEAR = "2026/2027"` (payroll.py:142) — correct for the run date. It is a hard-coded constant, not date-derived; the separate annual update task must flip it each 1 March. `calc_paye`/`calc_payroll` fall back to it safely (206, 240).
- **CIT 27%**: dashboard provision (payroll.py:566), management accounts (1417), provisional tax `CORP_TAX_RATE` (1514), AFS tax note (financial_statements.py:403, 493) — all 27%, unchanged in Budget 2026 ✓.
- **VAT 15%**: `VAT_RATE` (payroll.py:885, 1867) and VAT201 fraction 15/115 (1917, 1941) ✓. The 2025-era proposed VAT increase was withdrawn; Budget 2026 kept 15%. No announced future rate change. (Note: the compulsory VAT **registration** threshold rose R1m → R2.3m from 1 Apr 2026 — the app hard-codes no registration threshold, so nothing to update.)
- **EMP201 due-day**: 7th of the following month (payroll.py:1273–1275) ✓ per SARS rule.

Sources: [SARS — rates of tax for individuals](https://www.sars.gov.za/tax-rates/income-tax/rates-of-tax-for-individuals/), [Treasury — Budget 2026 Tax Guide](https://www.treasury.gov.za/documents/national%20budget/2026/sars/Budget%202026%20Tax%20guide.pdf), [SARS — Budget 2026 FAQ](https://www.sars.gov.za/about/sars-tax-and-customs-system/budget/budget-2026-frequently-asked-questions/), [SARS — UIF](https://www.sars.gov.za/types-of-tax/unemployment-insurance-fund/), [Werksmans — Budget 2026/27 tax overview](https://werksmans.com/budget-speech-2026-2027-tax-overview/).

## 8. Action items

1. **[Medium — M4]** ~~Align AFS revenue recognition with IFRS for SMEs Section 23~~ — **RESOLVED same day**, see §9 Resolution log.
2. **[Low — L1]** Make per-PO AP-credit lookups reversal-aware (carried over from 2026-07-09; payroll.py:1698–1718, purchase_orders.py:427–448).
3. **[Low — L3]** Revisit deferred-tax disclosure once fixed-asset temporary differences are material (financial_statements.py:371, 494).
4. **[Low — L4]** Wire `finance_costs` to journal interest accounts before bank-feed interest lands (financial_statements.py:400).
5. **[Low — planning]** Schedule IFRS for SMEs 3rd-edition transition review ahead of FY2028 (first period beginning 1 Mar 2027); add secondary/tertiary rebates if employees over 65 are onboarded; ensure the annual tax task flips `CURRENT_TAX_YEAR` on 1 Mar 2027.

## 9. Resolution log (2026-07-11 evening, same day)

**M4 ✅ fixed on request.** Investigation showed the income statement was **already accrual** — it aggregates journal revenue accounts (financial_statements.py:69–74), and `post_invoice_raised` credits revenue at issue date (journal.py:181–218). The defects were the policy note and two notes prepared on a different basis than the statements:

- Basis-of-preparation note rewritten: accrual recognition at invoice issue per Section 23 of IFRS for SMEs, consideration receivable net of VAT, FX translated at transaction-date rate (financial_statements.py:500–505).
- Note 4 (Revenue by customer) now uses all **issued** invoices (sent/overdue/paid) by issue date, ex-VAT, ZAR at the raised-basis exchange rate — previously paid-only, VAT-inclusive, raw FX, so it reconciled to nothing on the face of the statements (financial_statements.py:290–306).
- Note 3 (Receivables aging) now converts to ZAR at the raised-basis rate via new `_inv_total_zar` helper, matching the 1100 AR control postings — previously raw foreign-currency totals (financial_statements.py:55–67, 275–286).
- Frontend unchanged: the AFS view renders the policy text from the API, and its "Revenue (ZAR)" column label is now accurate.

## 10. Changes since last run (2026-07-11 morning)

All six same-day fixes from the morning run (H1, H2, M1, M2, M3, L2) are **verified intact in code** — no regressions. No new code changes detected in the audited reporting paths since. The IFRS and SARS-tax sections were audited for the first time under the expanded checklist: tax tables fully current; one Medium IFRS finding (M4, cash-basis revenue) plus three Low items.
