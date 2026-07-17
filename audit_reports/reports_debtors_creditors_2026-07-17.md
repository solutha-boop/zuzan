# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 17 July 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-07-15. All four of its findings (C1, C1a, T1, T2 — pension/medical payroll journal + PAYE/UIF treatment) were fixed same-day and re-verified intact this run via the 2026-07-15 fix descriptions (journal.py `post_payroll` rework, accounts 5120/5130/2230/2240). The 2026-07-16 AFS COGS-split fix (F1) also verified intact. Carried-over low items from 07-15 §8.5 are restated in section 8 below.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ✅ PASS — all totals ZAR-converted and mutually consistent |
| Debtors (AR) | ✅ PASS — aged from due_date, paid excluded, ZAR amounts |
| Creditors (AP) | ✅ PASS — reversal-aware in all four locations, bank details decrypted |
| Cross-module consistency | ✅ PASS — full journal coverage, import-awareness intact |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) already implemented and verified; 2 minor Note 7 findings |
| Tax rates (SARS) | ✅ PASS — 2026/2027 tables current; 1 stale text string in AI prompt |

**Overall: PASS.** No critical or high-severity issues. 2 medium/low code findings and 2 informational items — **all fixed same-day (user-authorized); see section 9.**

---

## 2. Reports

✓ No issues found.

- `total_revenue` sums only paid invoices via `_to_zar()` (payroll.py:1000-1004); `_to_zar()` correctly prefers `paid_amount_zar`, falls back to `total_amount × exchange_rate`, ZAR passthrough (payroll.py:17-24). Bank-import income added separately without double-count (payroll.py:1006).
- `total_outstanding` covers `sent` + `overdue` with `_to_zar()` (payroll.py:1008-1012). Note: `sent` is the app's "pending" status per database.py:38 — checklist's "pending + overdue" is satisfied.
- Expenses excluded from revenue; expenses taken ex-VAT (payroll.py:1018).
- Payroll included via all-company payslip sum incl. terminated employees, with estimate fallback (payroll.py:1042-1052).
- PO COGS: received/partial/paid POs at delivered-value ex-VAT via `_po_delivered_net` (payroll.py:1023-1028); structural double-count warning against matching expenses (payroll.py:1079-1113). Not double-counted.
- PO input VAT included in dashboard VAT position (payroll.py:1070-1073) — 2026-07-07 fix intact.
- Management accounts revenue trend loop applies `_to_zar()` + bank-import income each month (payroll.py:1937-1941).
- `/v1/summary` uses `_to_zar()`, `_po_delivered_net`, depreciation and payroll consistently with dashboard (main.py:446-487).

## 3. Debtors

✓ No issues found.

- Frontend `Debtors` component (App_js_fixed.js:5741) renders backend `/reports/debtors-aging` verbatim; refreshes on invoice payment (App_js_fixed.js:5751-5755).
- Backend filters `status IN (sent, overdue)` — paid and draft excluded (payroll.py:2117-2120).
- ZAR equivalents via `_to_zar()` per invoice (payroll.py:2131).
- Aging strictly from `due_date`; invoices without one go to `not_due` rather than a fallback date (payroll.py:2124-2151). Buckets: not_due / 0-30 / 31-60 / 61-90 / 90+.
- Reconciliation Rule 2 (>90 days) also ages from `due_date` and shows ZAR item amounts (payroll.py:1391-1410).

## 4. Creditors

✓ No issues found.

- Frontend `Creditors` (App_js_fixed.js:5867) renders backend `/reports/creditors-aging`.
- Pulls received/partial POs + unpaid on-credit expenses; fully paid POs and paid credit expenses excluded (payroll.py:2187-2190, 2282-2286).
- Supplier bank details decrypted with `decrypt_field` before display (payroll.py:2250-2252).
- Aging from due date = received_date + supplier payment_terms (default 30) (payroll.py:2234-2244).
- **Reversal-awareness (2026-07-13 fixes) verified in all four locations:**
  - payroll.py Rule 7: nets `credit − debit`, includes `purchase_order_reversal` (payroll.py:1540-1553)
  - creditors-aging lookup (payroll.py:2202-2215)
  - purchase_orders.py `pay_po` AP-balance clear (purchase_orders.py:440-453)
  - journal.py backfill (journal.py:844-848)
- `pay_po` single-commit rollback safety intact (purchase_orders.py:455-472).

## 5. Cross-module consistency

✓ No issues found.

- Journal coverage complete in journal.py: `post_invoice_raised` (:194), `post_invoice_paid` (:234), `post_invoice_cogs` (:268), `post_expense` (:293), `post_expense_paid` (:447), `post_bank_income` (:328), `post_payroll` (:368), `post_po_received` (:476), `post_po_paid` (:528), `post_stock_adjustment` (:556), asset acquisition/depreciation/disposal (:597/:623/:650).
- AR control (1100) and AP control (2000) reconciliation rules compare journal balances to raw invoice/PO totals with <R1 tolerance (payroll.py:1481-1597).
- **Import-awareness (2026-07-11 fixes) all verified:**
  - Invoice/expense imports auto-run journal backfill (csv_import.py:124-143, :501, :563)
  - Rules 6/7 exclude `source="import"` lines on 1100/2000 and report them as opening balances (payroll.py:1498-1510, 1574-1586)
  - Balance sheet includes 3998/3999 imported equity offsets (payroll.py:1304-1321)
  - Unbalanced journal import groups rejected (csv_import.py:1035-1064)
  - Non-ZAR invoice imports require an exchange rate or the row is rejected (csv_import.py:458-470)

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (declared in meta and accounting policies — financial_statements.py:580, :671-699). Statements produced: income statement, statement of financial position, statement of changes in equity, cash flow (indirect), notes 2-9.

**Standards status verified by web search (July 2026):**
- IFRS 18 *Presentation and Disclosure in Financial Statements* — effective for annual periods beginning on or after 1 Jan 2027; applies to full-IFRS preparers, **not** IFRS for SMEs preparers, so no ZuZan changes required.
- IFRS for SMEs **third edition** (issued Feb 2025) — effective annual periods beginning on or after 1 Jan 2027. ZuZan's FY runs 1 March–28/29 Feb, so the first FY caught is the one beginning **1 March 2027** (FY2028). Not yet mandatory; monitor (action item L4).
- No change in applicable standards since the fixes recorded 2026-07-13/16 — moving on.

**Prior-fix verification:**
- Finance costs (2026-07-13): interest lines (6700 or name-matched) presented below EBIT; tax and net profit derive from `profit_before_tax`, not EBIT (financial_statements.py:198-205, :251-255). ✓
- COGS split F1 (2026-07-16): name-aware staff-cost/COGS classifier intact (financial_statements.py:207-235). ✓

**Section 5b — deferred tax: ALREADY IMPLEMENTED (2026-07-14 run) — verified, no code changes made this run:**
- `Note 9` no longer hard-codes `"deferred_tax": 0.0`; it reports the period movement, `total_tax = current + deferred`, effective rate, and opening/closing balances (financial_statements.py:556-568).
- `wear_and_tear_rate` column exists on FixedAsset (database.py:454) and its ALTER TABLE migration is **inside** the migrations list literal (database.py:1321, list closes at :1342) — not dead code.
- Computation (financial_statements.py:125-167): per asset tax base = cost − straight-line SARS wear-and-tear apportioned monthly, floored at 0; temporary difference = carrying value − tax base; balance × 27%. Rate priority: explicit override → SARS IN47 category → category-name heuristic → None (fallback tax base = carrying value ⇒ zero difference). Disposed assets excluded. Safety: no assets / no rates ⇒ exactly 0.0.
- Balance sheet presents closing balance as computed non-current line (2600 DTL / 1900 DTA) with matching retained-earnings adjustment so the statement balances (financial_statements.py:306-322); equity statement discloses the movement (financial_statements.py:638). Nothing posted to the journal. ✓
- Frontend renders the deferred tax row in Note 9 when non-zero (App_js_fixed.js:11353-11354) and DTL/DTA badges in the asset register (App_js_fixed.js:9963-9987). ✓

**Findings:**
- **M1 — Note 7 trade payables not reversal-aware/delivered-aware.** `payables_summary` sums `po.total_amount` for open POs (financial_statements.py:534, :537-540), while the balance-sheet 2000 line, Rule 7 and the creditors book all use journal-netted (reversal-aware, delivered-value) amounts. For a partially delivered or partially reversed PO, Note 7 overstates payables and won't reconcile to the statement of financial position line it supports.
- **L1 — Note 7 not as-at period end.** The open-PO query has no `received_date <= end` filter (financial_statements.py:523-526), so POs received after the FY end appear in that year's note. (The unpaid credit expenses part is correctly filtered, :531.)

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027). Sources: SARS rates pages, Treasury Budget 2026 tax guide, KPMG/Werksmans budget summaries (via web search 2026-07-17).

- **PAYE brackets 2026/2027** — code matches the Budget 2026 tables exactly (payroll.py:127-139): 18% to R245,100; 26% to R383,100; 31% to R530,200; 36% to R695,800; 39% to R887,000; 41% to R1,878,600; 45% above. Base amounts verified arithmetically consistent. ✓
- **Primary rebate** R17,820 ✓ (payroll.py:137). Secondary/tertiary rebates (R9,444 / R3,145) are not implemented — engine applies primary only; acceptable for the current feature set, noted for completeness.
- **UIF**: 1% employee + 1% employer ✓ (payroll.py:148); earnings ceiling R17,712/month ✓ (payroll.py:138).
- **SDL**: 1% ✓ (payroll.py:149).
- **Engine selects correct year**: `CURRENT_TAX_YEAR = "2026/2027"` (payroll.py:142) is correct for the run date. It is a hard-coded constant, not date-derived — must be bumped by the annual update task before 1 March 2027 (L3).
- **Corporate income tax**: 27% unchanged per Budget 2026 ✓ — matches dashboard (payroll.py:1056), management accounts (:1911), provisional tax (:2008), AFS (financial_statements.py:254, `_CIT_RATE` in deferred tax).
- **VAT**: 15% unchanged ✓ — the previously proposed increase was formally withdrawn in Budget 2026 (payroll.py:1375, :2364). Informational: the compulsory VAT **registration threshold** rises R1m → R2.3m from 1 April 2026; ZuZan doesn't gate VAT registration so no code change needed.
- **EMP201 due-day**: 7th of following month ✓ (payroll.py:1446). IRP6 two-installment logic present ✓ (payroll.py:1994-2008).
- **L2 — Stale rate in AI assistant prompt**: `ZUZAN_SYSTEM_PROMPT` still tells users "2025/2026 primary rebate R17,235" and the old UIF framing (main.py:515-516). The prompt text should say 2026/2027 / R17,820. Not a calculation bug — payroll math is unaffected — but the in-app assistant will quote an outdated rebate.

No tax-table edits made (report-only per task rules; section 5b needed no edits this run).

## 8. Action items

| # | Severity | Item | Status |
|---|---|---|---|
| 1 | **Medium** | **M1:** Make Note 7 `payables_summary` reversal-/delivered-aware — reuse the journal-netted per-PO AP lookup instead of `po.total_amount`, so the note reconciles to the balance-sheet 2000 line. | **FIXED** (§9) |
| 2 | **Low** | **L1:** Filter Note 7 open POs to as-at FY end. | **FIXED** (§9) |
| 3 | **Low** | **L2:** Update the hard-coded 2025/2026 rebate figure in `ZUZAN_SYSTEM_PROMPT`. | **FIXED** (§9) |
| 4 | **Low** | **L3:** `CURRENT_TAX_YEAR` static constant needing a manual annual bump. | **FIXED** (§9 — now date-derived) |
| 5 | **Low** | **L4:** Plan IFRS for SMEs third-edition transition for the FY beginning 1 March 2027 (Section 23 revenue rewrite, updated disclosures); revisit in early-2027 runs. | Open (carried) |
| 6 | **Low** | Carried from 07-15: sync App_js_fixed.js → zuzan-app/src/App.js at next build; unify the two deferred-tax calculators (`/fixed-assets/deferred-tax` vs AFS helper); s11F excess carry-forward on annual reconciliation; secondary/tertiary rebates if 65+ employees onboarded. | Open (carried) |

## 9. Fixes applied 2026-07-17 (same-day, user-authorized)

- **M1 — financial_statements.py Note 7** (:534-563): `payables_summary.open_pos` now uses journal-netted per-PO AP amounts — `SUM(credit − debit)` on account 2000 across `purchase_order` **and** `purchase_order_reversal` entries dated ≤ FY end, grouped by `source_id` (same lookup as `/reports/creditors-aging`), with `po.total_amount` fallback when no journal entry exists. Note 7 now reconciles with the balance-sheet 2000 line for partial/reversed POs.
- **L1 — financial_statements.py Note 7** (:523-531): open POs filtered to `(received_date or order_date or created_at) <= end` — NULL-safe Python filter using the same fallback chain as creditors-aging, so legacy POs without `received_date` are retained rather than dropped.
- **L2 — main.py:515**: `ZUZAN_SYSTEM_PROMPT` PAYE line updated to "2026/2027 primary rebate R17,820".
- **L3 — payroll.py:142-155**: `CURRENT_TAX_YEAR` now computed by `_current_tax_year()` — derives the SA tax-year label from today's date (month ≥ March ⇒ `Y/Y+1`), falling back to the newest `TAX_YEARS` entry if the derived year's table hasn't been added yet, so payroll never KeyErrors on 1 March. Note: evaluated at import — a backend restart after 1 March (or after adding the new year's table) picks up the new year; the annual tax task still adds the 2027/2028 brackets.
- Backward compatibility: AFS output shape unchanged (same `payables_summary` keys); `calc_payroll(tax_year=...)` overrides unaffected. All edits verified with Read/Grep per the stale-mount pitfall — no bash verification used.

**Sources consulted:** [SARS — Rates of Tax for Individuals](https://www.sars.gov.za/tax-rates/income-tax/rates-of-tax-for-individuals/) · [Treasury Budget 2026 Tax Guide](https://www.treasury.gov.za/documents/national%20budget/2026/sars/Budget%202026%20Tax%20guide.pdf) · [SARS — UIF](https://www.sars.gov.za/types-of-tax/unemployment-insurance-fund/) · [Werksmans — Budget Speech 2026/2027 Tax Overview](https://werksmans.com/budget-speech-2026-2027-tax-overview/) · [vatcalc — SA 2026 Budget VAT](https://www.vatcalc.com/south-africa/south-africa-vat-rise/) · [PwC Tax Summaries — South Africa](https://taxsummaries.pwc.com/south-africa/corporate/significant-developments) · [IFRS — IFRS for SMEs Standard](https://www.ifrs.org/issued-standards/ifrs-for-smes/) · [IAS Plus — Third edition IFRS for SMEs](https://www.iasplus.com/en/news/2025/02/third-ifrs-for-smes) · [Grant Thornton — Get ready for IFRS 18](https://www.grantthornton.global/en/insights/articles/get-ready-for-ifrs-18/)
