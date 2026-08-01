# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 1 August 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-07-31 (full PASS, no open action items).

**Change detection since last run:** `git log 43084a7..HEAD` shows 4 deploy commits between 07-27 and 07-31, HEAD now `11d43fd` (2026-07-31 17:36). `git diff 43084a7..HEAD --stat` across all in-scope files shows exactly one changed file: `zuzan-backend/main.py` (+1/-1 line). Inspected the diff directly — it only appends more repeated `# disabled — re-enable when PayFast live` comment fragments onto an already fully-commented-out `# app.add_middleware(_SubscriptionGateMiddleware)` line (subscription-gate middleware, unrelated to Reports/Debtors/Creditors/AFS/tax). No functional change. Working tree matches HEAD exactly (`git diff HEAD` empty — no uncommitted edits). All other in-scope files (`App_js_fixed.js`, `payroll.py`, `companies.py`, `suppliers.py`, `customers.py`, `purchase_orders.py`, `journal.py`, `database.py`, `financial_statements.py`, `csv_import.py`, `fixed_assets.py`) last modified 07-27 or earlier — untouched since the 07-31 audit. **Effectively zero code changes since yesterday's audit**; this run re-verifies key logic directly (Grep/Read, not bash, per the stale-mount-cache pitfall) and refreshes external IFRS/SARS research.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ✅ PASS — logic unchanged, re-verified |
| Debtors (AR) | ✅ PASS — aged from due_date, paid excluded, ZAR amounts |
| Creditors (AP) | ✅ PASS — reversal-aware, bank details decrypted |
| Cross-module consistency | ✅ PASS — full journal coverage, import-awareness intact, migration hygiene intact |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) verified again, no regressions |
| Tax rates (SARS) | ✅ PASS — 2026/2027 tables current, no rate changes since 07-31 |

**Overall: PASS.** No functional code changes since the last audit; no new action items.

---

## 2. Reports

✓ No issues found. Re-confirmed via direct Grep this run:
- Dashboard (`payroll.py:1237,1245`): `total_revenue = sum(_to_zar(i) for i in paid_invoices)`; `total_outstanding = sum(_to_zar(i) for i in outstanding_invoices)`. Expenses excluded from revenue (separate aggregation).
- `_to_zar()` defined `payroll.py:17`, applied consistently across all revenue/outstanding aggregation sites verified this run (dashboard, debtors-aging, cash-flow, management accounts, YTD views).
- `/v1/summary` (`main.py:447-481`): imports `_to_zar`, `_po_delivered_net`, `_bank_import_income` from payroll.py; `total_revenue = sum(_to_zar(i) for i in paid_invs) + _bank_import_income(...)`; `outstanding = sum(_to_zar(i) for i in out_invs)`; PO costs folded in via `_po_delivered_net(po)` distinct from payroll costs — no double counting.

## 3. Debtors

✓ No issues found.
- Invoice status filter confirmed at every debtors-relevant site (`payroll.py:1243,1627-1628,1723,2151`): `Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])` — paid invoices excluded.
- Aging cutoffs keyed off `due_date` (e.g. `payroll.py:1627-1628`: `Invoice.due_date <= cutoff_90`), not invoice date.
- ZAR conversion via `_to_zar()` applied at debtors-aging call sites.

## 4. Creditors

✓ No issues found.
- **Reversal-awareness (2026-07-13 fixes) re-confirmed present in all five call sites this run:** `payroll.py:1778` (Rule 7) and `payroll.py:2534` (creditors-aging), `purchase_orders.py:445` (pay_po), `journal.py:848` (backfill), `financial_statements.py:558` (balance sheet PO liability) — every site nets `source IN ("purchase_order", "purchase_order_reversal")`.
- Supplier bank details decrypted via `decrypt_field` (unchanged from prior audits — file untouched since 06-15).

## 5. Cross-module consistency

✓ No issues found.
- Journal coverage complete across invoices, expenses, payroll, POs, inventory, fixed assets — no gaps found.
- Import-awareness (2026-07-11 fixes) intact: `payroll.py:1736,1812` exclude `JournalEntry.source == "import"` on the relevant rules; `financial_statements.py:1526-1546` explicitly retains imported equity offsets 3998 (retained earnings)/3999 (opening balance equity) via account-code match, alongside type-based Debtors/Creditors Control totals.
- **Migration hygiene re-verified:** `wear_and_tear_rate` ALTER TABLE (`database.py:1363`) confirmed still positioned inside the migrations list literal (between the credit_notes index and the pension/medical columns), not after the loop — read directly via the Read tool per the known dead-code pitfall.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (declared in AFS meta). Statements: income statement, statement of financial position, changes in equity, cash flow (indirect), notes 2-9.

**Standards status (fresh web search this run):**
- **IFRS 18** *Presentation and Disclosure in Financial Statements* — IASB confirmed (Jan 2026) the mandatory effective date remains annual periods beginning on/after 1 Jan 2027, early adoption permitted; comparative-period data capture recommended from 1 Jan 2026 for full-IFRS preparers. Still does not apply to IFRS-for-SMEs preparers (ZuZan's basis). No change since 07-31.
- **IFRS for SMEs third edition** (issued 27 Feb 2025, effective 1 Jan 2027, early adoption permitted) — unchanged; IASB has published incremental "SME Accounting Standard Update" notices (Dec 2025, Mar 2026) tracking alignment with full-IFRS changes since the 3rd edition's issuance, and Module 35 (Transition) educational material — none introduce new substantive requirements affecting ZuZan ahead of the 1 Jan 2027 effective date.
- **VAT rate:** reconfirmed no change — the previously-announced 2025/26 VAT increase to 15.5%/16% was withdrawn in April 2025; Budget 2026 (25 Feb 2026) again declined to raise VAT, instead raising the compulsory registration threshold to R2.3m (1 Apr 2026). Standard rate remains 15%, consistent with `VAT_RATE`.

**Section 5b — deferred tax: already implemented, re-verified this run (financial_statements.py, read/grepped directly, not via bash):**
- `_deferred_tax_balance` (`financial_statements.py:131`): tax base = cost − straight-line SARS wear-and-tear apportioned from purchase date, floored at 0; temporary difference × CIT rate; rate lookup priority `wear_and_tear_rate` override → `sars_category` IN47 table → accounting useful life fallback (`:107-110`).
- Note 9: `deferred_tax_expense = dt_closing − dt_opening` (`:266-268`); `total_tax = tax_expense + deferred_tax_expense` (`:601`); note fields `deferred_tax`, `deferred_tax_opening_balance`, `deferred_tax_closing_balance` all present (`:606,609-610`).
- Balance sheet presents closing DTL/DTA with matching retained-earnings adjustment (`deferred_tax_movement`, `:681`) — Assets = Equity + Liabilities preserved by construction. No regressions.
- `wear_and_tear_rate` column on FixedAsset (`database.py:483`) and its migration (`database.py:1363`) confirmed present and correctly placed (see §5 above).

✓ No issues found.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date.

- No rate changes found since the 07-31 audit. Fresh search this run reconfirms: PIT brackets/rebates for 2026/27 were adjusted 3.4% for inflation (first inflationary adjustment since 2023/24); maximum marginal rate unchanged at 45%; medical scheme fees tax credit R376/R254 (up from R364/R246); the previously-proposed ~R20bn 2026/27 tax increase package was withdrawn.
- **Brackets & rebates** (`payroll.py:132-143`) — unchanged, previously verified line-by-line against the official SARS Budget 2026 Tax Guide PDF.
- **UIF ceiling** R17,712/month (`payroll.py:144`), **UIF** 1%/1% (`payroll.py:188,476-477`), **SDL** 1% (`payroll.py:189,482`) — unchanged.
- **VAT** standard rate 15% (`payroll.py:1608,2691`) — unchanged; see §6 above for the registration-threshold nuance (no bearing on the rate constant).
- **Corporate income tax** 27% (`SA_CIT_RATE`) — unchanged, confirmed for years of assessment ending 1 Apr 2026 – 31 Mar 2027.
- Provisional `2027/2028` `TAX_YEARS` entry (`payroll.py:151-166`) remains a placeholder copy of 2026/2027 pending the Feb 2027 Budget — standing reminder, not a defect.
- Rates unchanged and current tax year present — no edits made (report-only per task rules).

**Sources consulted:** [IFRS 18 Presentation and Disclosure in Financial Statements — IFRS.org](https://www.ifrs.org/issued-standards/list-of-standards/ifrs-18-presentation-and-disclosure-in-financial-statements/) · [IFRS Standards Effective 2026: Compliance Guide — Prima Consulting](https://primaconsulting.org/ifrs-changes-2026-update/) · [March 2026 IFRS for SMEs Accounting Standard Update — IFRS.org](https://www.ifrs.org/supporting-implementation/2015-ifrs-for-smes-supporting-materials/sme-updates/2026/march-2026-ifrs-for-smes-accounting-standard-update/) · [Webcast series — third edition IFRS for SMEs — IFRS.org](https://www.ifrs.org/supporting-implementation/2025-ifrs-for-smes-supporting-materials/webcast-series-third-ed-ifrs-for-smes/) · [Budget 2026: a small win for taxpayers — TaxTim](https://www.taxtim.com/za/blog/budget-2026) · [Income tax brackets, medical tax credits adjusted for inflation — Moonstone](https://www.moonstone.co.za/income-tax-brackets-medical-tax-credits-adjusted-for-inflation/) · [Budget-tax-guide-2026-web-version.pdf — SARS](https://www.sars.gov.za/wp-content/uploads/Docs/Budget/Budget2026/Budget-tax-guide-2026-web-version.pdf) · [South Africa 2026 Budget ducks VAT rise — vatcalc.com](https://www.vatcalc.com/south-africa/south-africa-vat-rise/) · [Proposed VAT increase officially withdrawn — SAnews](https://www.sanews.gov.za/south-africa/proposed-vat-increase-officially-withdrawn) · [Budget 2026 Delivers SME Relief as VAT Threshold Increases to R2.3 Million — Standard Bank](https://www.standardbank.co.za/southafrica/news-and-media/newsroom/budget-2026-delivers-sme-relief-as-vat-threshold-increases-to-r2.3-million)

## 8. Action items

None open.

**Standing reminders (not defects, carried from prior reports):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry (`payroll.py:151+`) after Budget Feb 2027 and restart the backend;
(b) early-2027 runs should execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`) — Section 23 revenue and Section 19 business-combinations changes are most relevant to ZuZan; watch for any new Consolidation Exception exposure-draft developments;
(c) the AFS PayFast payment/ad-hoc tokenization feature and the `/reports/ai-insights` (AI management-pack) feature remain outside this audit's Reports/Debtors/Creditors/AFS-content/tax scope — flag for inclusion if a future audit's file list is expanded;
(d) NBCPSS private security payroll mode (grades, allowances, BC levy, PSIRA fee) predates this audit's baseline and doesn't affect the audited totals, but isn't yet part of this checklist's explicit scope — consider adding it to the payroll section of future audits;
(e) the 07-31 diff to `main.py` (cosmetic comment padding on the disabled `_SubscriptionGateMiddleware` line) is noise and outside audit scope, but if that middleware is ever re-enabled for PayFast go-live, add subscription-gate behavior to a future audit's scope since it affects request flow ahead of CORS.
