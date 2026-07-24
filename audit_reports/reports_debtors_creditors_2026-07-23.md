# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 23 July 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-07-22 (full PASS, one Low cosmetic item carried open: `financial_statements.py` used literal `0.27`/`27.0` instead of `_CIT_RATE`).

**Change detection since last run (2026-07-22 00:22):** Two audit-scope files changed, both **after** the prior report was generated:
- `financial_statements.py`, mtime **2026-07-22 00:28** — functional fix: replaced literal `0.27` (line 260, current-tax calc) and literal `27.0` (lines 604, 641, `tax_rate_pct`) with `_CIT_RATE` / `round(_CIT_RATE * 100, 2)`. This is exactly the carried-over Low item from the last three reports — **now resolved**, no code change required from this audit.
- `main.py`, mtime **2026-07-22 01:05** — part of the same large feature commit (debit-order mandate, once-off PayFast AFS payment, NBCPSS private-security payroll mode, plan-gating changes). Diffed line-by-line: the only change is to a comment string on an already-disabled `# app.add_middleware(_SubscriptionGateMiddleware)` line (subscription gating remains off, pending PayFast go-live — unrelated to audit scope). `/v1/summary` logic is byte-identical to the version verified 07-22.

All other audit-scope files are byte-unchanged since the 07-22 PASS: payroll.py (07-19), database.py (07-19), fixed_assets.py (07-19), journal.py (07-15), purchase_orders.py (07-13), csv_import.py (07-11), companies.py (07-18), suppliers.py (06-15), customers.py (06-12), App_js_fixed.js (07-18).

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ✅ PASS — logic unchanged, re-verified |
| Debtors (AR) | ✅ PASS — aged from due_date, paid excluded, ZAR amounts |
| Creditors (AP) | ✅ PASS — reversal-aware, bank details decrypted |
| Cross-module consistency | ✅ PASS — full journal coverage, import-awareness intact |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) verified; carried-over CIT-rate cosmetic item **fixed** |
| Tax rates (SARS) | ✅ PASS — 2026/2027 tables current, no Budget/SARS changes since 07-22 |

**Overall: PASS.** No open action items — the sole carried-over Low item was resolved by the developer in the intervening feature commit.

---

## 2. Reports

✓ No issues found.

- `/v1/summary` (main.py:443-488) unchanged in logic since 07-22: `total_revenue` sums only paid invoices via `_to_zar()` (:450) plus `_bank_import_income` (:451); expenses ex-VAT (:454), PO COGS via `_po_delivered_net` over received/partial/paid POs (:458-464, no double-count), depreciation (:467-470), all payslip `total_cost` (:474-479); `outstanding` filters `status IN (sent, overdue)` with `_to_zar()` (:449, :480).
- Dashboard (payroll.py:1225-1260, re-read this run): `total_revenue` = paid invoices via `_to_zar()` + `_bank_import_income`; expenses ex-VAT; PO COGS via delivered-net over received/partial/paid POs, no double-count; `total_outstanding` filters sent/overdue via `_to_zar()`.
- Management accounts revenue trend and payroll-cost inclusion unchanged (payroll.py, byte-identical to 07-22 verification).

## 3. Debtors

✓ No issues found.

- Frontend `Debtors` renders backend `/reports/debtors-aging` (App_js_fixed.js:5930, :5936).
- Backend filters `status IN (sent, overdue)` — paid and draft excluded (payroll.py:2350-2354).
- ZAR equivalents via `_to_zar()` per invoice (payroll.py:2365).
- Aging strictly from `due_date` (no issue_date/created_at fallback); buckets not_due / current(0-30) / 31-60 / 61-90 / 90+ (payroll.py:2357-2400).

## 4. Creditors

✓ No issues found.

- Frontend `Creditors` renders backend `/reports/creditors-aging` (App_js_fixed.js:6057, :6063).
- Pulls received/partial POs plus unpaid on-credit expenses; fully paid POs and paid credit expenses excluded (payroll.py:2419-2422).
- Supplier bank details decrypted with `decrypt_field` before display (payroll.py:2416, :2483-2485).
- **Reversal-awareness (2026-07-13 fixes) re-confirmed:** `SUM(credit − debit)` netting with source `IN ("purchase_order", "purchase_order_reversal")` at payroll.py:1770-1778 (Rule 7) and :2432-2440 (creditors-aging per-PO); same pattern applied in financial_statements.py Note 7 payables (:519-560, unchanged from 07-17 fix).

## 5. Cross-module consistency

✓ No issues found.

- Journal coverage complete (journal.py, unchanged, re-grepped): `post_invoice_raised`, `post_invoice_paid`, `post_invoice_cogs`, `post_expense`, `post_bank_income`, `post_payroll`, `post_expense_paid`, `post_po_received`, `post_po_paid`, plus asset acquisition/depreciation/disposal — all source types covered.
- Debtors Control (1100) / Creditors Control (2000) reconciliation compares journal balances to raw invoice/PO totals, reversal- and import-aware (payroll.py Rules 6-7, :1720-1815).
- **Import-awareness (2026-07-11 fixes)** intact — csv_import.py unchanged: auto-backfill on invoice/expense import, Rules 6/7 exclude `source="import"` lines on 1100/2000, balanced-group requirement, non-ZAR invoice imports require a positive exchange rate (17 matches for backfill/exchange_rate/source=="import" logic, consistent with prior counts).
- Migration hygiene: 89 `ALTER TABLE` statements, all inside the migrations list literal — no dead-code migrations after the for loop.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (declared in AFS meta, rendered in frontend). Statements: income statement, statement of financial position, changes in equity, cash flow (indirect), notes 2-9.

**Standards status (unchanged since prior audit):**
- IFRS 18 *Presentation and Disclosure in Financial Statements* — effective annual periods beginning on or after 1 Jan 2027; applies to full-IFRS preparers, not IFRS for SMEs. No ZuZan change required yet.
- IFRS for SMEs **third edition** — effective 1 Jan 2027, early application permitted. ZuZan's SA FY (1 March-28/29 Feb) is first caught by the FY beginning 1 March 2027. Transition plan on file (`ifrs_smes_3rd_edition_transition_plan.md`).

**Section 5b — deferred tax: already implemented, verified fresh this run.** financial_statements.py:
- Note 9 reports the period movement `dt_closing − dt_opening` (:266-268, :606), `total_tax = current + deferred` (:601), opening/closing balances and effective rate (:608-610).
- `_deferred_tax_balance` (:131-173, read in full this run): tax base = cost − straight-line SARS wear-and-tear apportioned monthly, floored at 0; temporary difference = carrying value − tax base, × `_CIT_RATE`. No assets / no rates ⇒ exactly 0.0; output shape backward-compatible.
- `wear_and_tear_rate` column on FixedAsset with its ALTER TABLE inside the migrations list literal.
- Balance sheet presents closing DTL/DTA as a computed line with matching retained-earnings adjustment; nothing posted to the journal. Frontend renders the Note 9 deferred-tax row when non-zero.

**Carried-over item RESOLVED this run:** financial_statements.py:260, :604, :641 previously used literal `0.27`/`27.0` for current-tax calc and `tax_rate_pct`; commit `381a9d5` (2026-07-22 00:28) replaced these with `_CIT_RATE` / `round(_CIT_RATE * 100, 2)`, sourced from `fixed_assets.SA_CIT_RATE` (single source of truth, unified 2026-07-19). Verified fresh: `_CIT_RATE` import at :78-84 with a `0.27` fallback if `fixed_assets` is unavailable, so the AFS module stays importable standalone. No further action needed.

**Finance costs (2026-07-13 fix) re-confirmed:** `profit_before_tax = ebit − finance_costs`; tax and net profit derive from `profit_before_tax`, not EBIT (financial_statements.py:257-261).

✓ No issues found.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date; `_current_tax_year()` derives it from today's date with newest-table fallback (payroll.py:171-182). Files unchanged since 07-19; rates cross-checked against a fresh web search today for any Budget/SARS announcement since the 07-22 verification.

- No new Budget speech, SARS rate change, or tax-year update found between 07-22 and 07-23. Filing Season 2026 news (auto-assessments, refund payouts) is administrative and does not affect PAYE brackets, rebates, UIF, SDL, CIT, or VAT rates.
- **PAYE brackets 2026/2027** — TAX_YEARS entry present (payroll.py:131-145); unchanged, previously web-confirmed. ✓
- **Rebates** — primary R17,820 (:141), secondary R9,765 (:142), tertiary R3,249 (:143) — previously web-confirmed as the correct 2026/2027 Budget figures. ✓
- **UIF** 1% employee + 1% employer (:188), ceiling R17,712/month (:144). **SDL** 1% (:189). ✓
- **Corporate income tax** 27% unchanged — dashboard (payroll.py:1289), management accounts (:2144), provisional tax (:2241), AFS via `SA_CIT_RATE` (now single-sourced end-to-end per section 6). ✓
- **VAT** 15% unchanged (payroll.py:1608) — no VAT rate change reported; registration thresholds (compulsory R2.3m, voluntary R120k, effective 1 Apr 2026) remain informational only, no code gate exists. ✓
- **s11F cap and medical tax credits** (R376/R254, effective 1 March 2026) current for 2026/2027 (:195-201). ✓
- **Provisional 2027/2028 entry** present, flagged `"provisional": True` (:151-166) — pending Budget Feb 2027. No change needed yet.
- Rates unchanged and current tax year present — no edits made (report-only per task rules; section 5b needed no new edits this run, only verification).

**Sources consulted:** [Werksmans — Budget Speech 2026/2027 Tax Overview](https://werksmans.com/budget-speech-2026-2027-tax-overview/) · [IOL — SARS 2026 tax season](https://iol.co.za/business/2026-07-05-everything-you-need-to-know-about-sars-2026-tax-season-as-billions-flow-out-in-first-days/) · [SARS — Changes for Filing Season 2026](https://www.sars.gov.za/latest-news/changes-for-filing-season-2026/) · [SARS — Budget 2026 FAQ](https://www.sars.gov.za/about/sars-tax-and-customs-system/budget/budget-2026-frequently-asked-questions/)

## 8. Action items

None open. All carried-over items resolved.

**Standing reminders (not defects):** (a) replace the provisional 2027/2028 TAX_YEARS entry after Budget Feb 2027 and restart the backend; (b) early-2027 runs execute the IFRS for SMEs 3rd-edition transition-plan checklist; (c) VAT registration thresholds changed 1 Apr 2026 (compulsory R2.3m, voluntary R120k) — informational only, no code gate exists.

**Note for next run:** the intervening feature commit (`381a9d5`…`1c40b1c`) appears **11 times in git log with an identical commit message**, each incrementally appending more `#` characters and repeated "disabled — re-enable when PayFast live" text to a single comment line in main.py (the disabled `_SubscriptionGateMiddleware` line). This looks like a runaway auto-commit/formatting loop rather than intentional history — cosmetic and outside audit scope (the line stays a no-op comment either way, and PayFast gating remains correctly disabled), but worth the dev team's attention if it keeps growing, since it will eventually bloat that line indefinitely. Not raised as an audit action item as it has no effect on reports, debtors, creditors, IFRS, or tax correctness.
