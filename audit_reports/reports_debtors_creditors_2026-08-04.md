# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 4 August 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-08-03 (full PASS, no open action items).

**Change detection since last run:** `git log 1eb36f5..HEAD` shows one new commit, `50c00b6` (2026-08-03 20:09, "fix: RecurringInvoices + CreditNotes useEffect Promise crash (Sentry #662ae44)"). `git diff 1eb36f5..50c00b6 -w` on the in-scope file list touches only:
- `App_js_fixed.js` (+2/-2): wraps two `useEffect` loader calls (`RecurringInvoicesTab`, `CreditNotesTab`) in a block body (`() => { api(...).then(...).catch(...); }`) instead of an implicit-return arrow, so the Promise isn't returned to `useEffect`'s cleanup slot (a React warning/crash fix). No change to invoice, debtor, creditor, or reporting logic.
- `zuzan-backend/main.py` (+1/-1): the disabled-middleware comment line duplicated itself again (cosmetic, `_SubscriptionGateMiddleware` still disabled either way). The `/v1/summary` block (lines 445-490) is untouched.

Working tree `git status` shows `auth.py`, `billing.py`, `companies.py`, `main.py`, `payroll.py` modified-but-uncommitted; `git diff -w` on the in-scope subset (`companies.py`, `main.py`, `payroll.py`) returns **empty** — line-ending/whitespace noise only, consistent with every prior run since 07-26.

**None of this run's changes touch the audited surface area.** Re-verified all core logic directly via Read/Grep (not bash, per the stale-mount-cache pitfall) rather than relying solely on the diff — see sections below.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ✅ PASS — logic unchanged, re-verified |
| Debtors (AR) | ✅ PASS — aged from due_date, paid excluded, ZAR amounts |
| Creditors (AP) | ✅ PASS — reversal-aware, bank details decrypted |
| Cross-module consistency | ✅ PASS — full journal coverage, import-awareness intact, migration hygiene intact |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) verified again, no regressions |
| Tax rates (SARS) | ✅ PASS — 2026/2027 tables current, no rate changes since 08-03 |

**Overall: PASS.** No functional code changes to the audited surface since the last audit; no new action items.

---

## 2. Reports

✓ No issues found. Re-confirmed via direct Read this run:
- Dashboard (`payroll.py:1233-1245`): `total_revenue = sum(_to_zar(i) for i in paid_invoices)` plus `_bank_import_income()` (`:1237-1239`); `total_outstanding = sum(_to_zar(i) for i in outstanding_invoices)` filtered to `sent`/`overdue` (`:1241-1245`). Expenses (`:1248-1251`) and PO COGS (`:1253-1261`, delivered-value-only for partials) are aggregated separately, ex-VAT, and never mixed into revenue.
- Payroll costs included in expenses via the payslip sum, applied after gross profit — confirmed unchanged.
- Depreciation (`:1263-1267`) added once, sourced from `DepreciationEntry`, no overlap with PO COGS or payroll.
- Management accounts (`payroll.py:2078-2153`): revenue and outstanding both route through `_to_zar()`; PO COGS (`:2095-2108`, delivered-value-only) and depreciation (`:2110-2118`) folded into `total_expenses` consistently with the dashboard; `ebit`/`tax_provision`/`net_profit` derived correctly (`:2142-2147`).
- `/v1/summary` (`main.py:445-490`): imports `_to_zar`, `_po_delivered_net`, `_bank_import_income` from `payroll.py` (`:448`); revenue (`:452-453`), expenses incl. PO COGS (`:460-467`), depreciation (`:468-472`), payroll (`:474-481`), outstanding (`:482`) — all mirror the dashboard formula 1:1.

## 3. Debtors

✓ No issues found.
- Invoice status filter confirmed at every debtors-relevant site (`payroll.py:1241-1243, 1625-1628, 2149-2151`): `Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])` — paid invoices excluded.
- Aging cutoffs keyed off `due_date`, not invoice date (`payroll.py:1624-1628`: `cutoff_90 = now - timedelta(days=90)`; `Invoice.due_date <= cutoff_90`).
- ZAR conversion via `_to_zar()` applied consistently, including per-item display amounts (`payroll.py:1630, 1642`).

## 4. Creditors

✓ No issues found.
- **Reversal-awareness (2026-07-13 fixes) re-confirmed present in all four code-level call sites this run:** `payroll.py:1778` (Rule 7 AP control check) and `payroll.py:2534` (creditors-aging), `purchase_orders.py:445` (`pay_po`), `journal.py:848` (backfill) — every site nets `source IN ("purchase_order", "purchase_order_reversal")`.
- AP control (Rule 7, `payroll.py:1753-1790`) computes per-PO expected credit from `credit − debit` journal lines, falling back to `po.total_amount` only when no journal entry exists yet.
- Supplier bank details decrypted via `decrypt_field` (`suppliers.py:7,48-50`) — unchanged.

## 5. Cross-module consistency

✓ No issues found.
- Journal coverage complete (`journal.py`): `post_invoice_raised` (`:194`), `post_invoice_paid` (`:234`), `post_invoice_cogs` (`:268`), `post_expense` (`:293`), `post_payroll` (`:368`), `post_expense_paid` (`:447`), `post_po_received` (`:476`), `post_po_paid` (`:528`) — no gaps.
- Import-awareness (2026-07-11 fixes) intact: Rules 6/7 exclude `source == "import"` on 1100/2000 (`payroll.py:1736,1812`); balance sheet retains imported equity offsets 3998/3999 (`payroll.py:1526-1546`, per the standing file-attribution note — this logic lives in `payroll.py`, not `financial_statements.py`). Non-ZAR invoice imports still require an Exchange Rate column and reject rows with rate ≤ 0 (`csv_import.py:458-475`). Unbalanced journal-import groups still rejected (`csv_import.py:1035,1064`). Both invoice and journal imports auto-run the backfill (`csv_import.py:124-143,501-502,563-564`).
- **Migration hygiene re-verified:** `wear_and_tear_rate` column (`database.py:483`) and its `ALTER TABLE` (`database.py:1363`) confirmed still positioned inside the migrations list literal (between other in-list `ALTER TABLE` strings), not after the loop.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (declared in AFS meta). Statements: income statement, statement of financial position, changes in equity, cash flow (indirect), notes 2-9.

**Standards status (fresh web search this run):**
- **IFRS 18** *Presentation and Disclosure in Financial Statements* — still effective for annual periods beginning on/after 1 January 2027, early adoption permitted; still does not apply to IFRS-for-SMEs preparers (ZuZan's basis). No change since 08-03.
- **IFRS for SMEs third edition** (issued 27 February 2025) — confirmed still effective 1 January 2027, early application permitted. Key content (Section 23 revenue aligned to IFRS 15, new Section 12 fair value measurement, updated consolidation/financial-instruments/business-combinations requirements, 2018 Conceptual Framework alignment) unchanged from prior reports and the existing transition plan (`ifrs_smes_3rd_edition_transition_plan.md`). No new IASB update found this run beyond what was already logged on 08-03 (March 2026 Accounting Standard Update on Section 9 consolidation — still not applicable, ZuZan is single-entity only).
- **VAT rate:** reconfirmed 15% standard rate, unchanged.
- **Corporate income tax:** reconfirmed 27%, unchanged, for years of assessment ending 1 Apr 2026 – 31 Mar 2027 per Budget 2026 (no change announced).

**Section 5b — deferred tax: already implemented, re-verified this run (financial_statements.py, read/grepped directly):**
- `_deferred_tax_balance()` (`financial_statements.py:131-173`) — no hard-coded `0.0` remains; confirmed via direct grep for `"deferred_tax": 0.0` (no matches).
- Per-asset tax base = cost − cumulative SARS wear-and-tear allowance (`_wt_rate_pct()`, `:105-120`, priority: explicit `wear_and_tear_rate` → `sars_category`/IN47 table → category-name heuristic → None/zero-difference fallback); temporary difference × 27% (`_CIT_RATE`, `:84`).
- `dt_opening`/`dt_closing` computed per period (`:266-267`); `deferred_tax_expense = dt_closing − dt_opening` (`:268`); `total_tax = tax_expense + deferred_tax_expense` (`:601`); note fields `deferred_tax`, `deferred_tax_opening_balance`, `deferred_tax_closing_balance` present (`:606,609-610`).
- Balance sheet carries the closing DTL (`:315-321`, account 2600) or DTA (`:322-328`, account 1900) with matching `deferred_tax_movement` retained-earnings adjustment (`:349,681`) — Assets = Equity + Liabilities preserved by construction.
- `wear_and_tear_rate` column (`database.py:483`) and migration (`database.py:1363`) confirmed present and correctly placed (see §5).
- Frontend renders the deferred tax row and DTL/DTA badge when non-zero (`App_js_fixed.js:10379-10403, 11835-11836`) — unchanged.
- **Finance costs (2026-07-13 fix) re-confirmed:** interest/finance-cost lines presented below EBIT (`financial_statements.py:211`); `profit_before_tax = ebit − finance_costs` (`:259`); `tax_expense`/`net_profit` derive from `profit_before_tax`, not EBIT (`:260-261`).

✓ No issues found.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date.

- No rate changes found since the 08-03 audit. Fresh search this run reconfirms: PIT brackets 18%/26%/31%/36%/39%/41%/45% at thresholds R245,100/R383,100/R530,200/R695,800/R887,000/R1,878,600; primary rebate R17,820, secondary R9,765, tertiary R3,249 (Budget 2026's 3.4% inflationary adjustment); UIF ceiling R17,712/month — all match `payroll.py:131-145` exactly.
- **UIF** 1%/1%, **SDL** 1% (`payroll.py:188-189`) — unchanged.
- **VAT** standard rate 15% (`payroll.py:1608,2691`) — unchanged.
- **Corporate income tax** 27% (`financial_statements.py:84`, `_CIT_RATE`) — unchanged, confirmed for years of assessment ending 1 Apr 2026 – 31 Mar 2027.
- One new item surfaced by this run's search, informational only: for years of assessment commencing on/after 1 March 2026, s20A loss ring-fencing now triggers at the 39% marginal bracket rather than the top 45% bracket. This affects individual provisional taxpayers with ring-fenced trade losses — it does not change any PAYE bracket, rebate, UIF/SDL rate, VAT rate, or CIT rate that ZuZan implements, and ZuZan's payroll/tax-provision code does not model loss ring-fencing, so no code change is indicated. Noting for awareness only.
- Provisional `2027/2028` `TAX_YEARS` entry (`payroll.py:151-166`) remains a placeholder copy of 2026/2027 pending the Feb 2027 Budget — standing reminder, not a defect.
- Rates unchanged and current tax year present — no edits made (report-only per task rules; section 5b already implemented, verification-only this run).

**Sources consulted:** [IASB issues third edition of IFRS for SMEs accounting standard — EY](https://www.ey.com/en_gl/technical/ifrs-technical-resources/iasb-issues-third-edition-of-ifrs-for-smes-accounting-standard) · [IASB publishes third edition of IFRS for SMEs — ICAEW](https://www.icaew.com/insights/viewpoints-on-the-news/2025/feb-2025/iasb-publishes-third-edition-of-ifrs-for-smes-accounting-standard) · [Third edition of the IFRS for SMEs Accounting Standard — ACCA](https://www.accaglobal.com/learning-and-events/corporate-reporting/third-edition-ifrs-for-smes.html) · [IASB issues third edition of the IFRS for SMEs — PwC Viewpoint](https://viewpoint.pwc.com/dt/gx/en/pwc/in_briefs/in_briefs_INT/in_briefs_INT/iasb-issues.html) · [Budget 2026 Frequently Asked Questions — SARS](https://www.sars.gov.za/about/sars-tax-and-customs-system/budget/budget-2026-frequently-asked-questions/) · [SARS tax season 2026: Here's what's changed — MSN](https://www.msn.com/en-za/news/other/sars-tax-season-2026-here-s-what-s-changed/ar-AA26eAey) · [South Africa's tax changes in 2026: What SARS is really watching — JoburgETC](https://www.joburgetc.com/business/south-africa-tax-changes-2026/) · [Income tax brackets, medical tax credits adjusted for inflation — Moonstone](https://www.moonstone.co.za/income-tax-brackets-medical-tax-credits-adjusted-for-inflation/) · [Changes for Filing Season 2026 — SARS](https://www.sars.gov.za/latest-news/changes-for-filing-season-2026/)

## 8. Action items

None open.

**Standing reminders (not defects, carried from prior reports):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry (`payroll.py:151+`) after Budget Feb 2027 and restart the backend;
(b) early-2027 runs should execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`) — Section 23 revenue and Section 19 business-combinations changes are most relevant to ZuZan; Section 9 (consolidation) confirmed not applicable since ZuZan is single-entity only;
(c) the AFS PayFast payment/ad-hoc tokenization feature and the `/reports/ai-insights` (AI management-pack) feature remain outside this audit's Reports/Debtors/Creditors/AFS-content/tax scope. Development continues here (this run's `RecurringInvoices`/`CreditNotes` Sentry crash fix is UI-only and unrelated) — worth folding PayFast/billing into scope once `/billing/subscribe` lands, since it will touch `main.py`;
(d) NBCPSS private security payroll mode (grades, allowances, BC levy, PSIRA fee) predates this audit's baseline and doesn't affect the audited totals, but isn't yet part of this checklist's explicit scope — consider adding it to the payroll section of future audits;
(e) file-attribution note (carried since 08-01): the imported-equity-offset (3998/3999) exclusion logic lives in `payroll.py`'s `balance_sheet()`, not `financial_statements.py`;
(f) new this run: an s20A loss-ring-fencing threshold change (39% vs. 45% marginal rate trigger, effective years of assessment from 1 March 2026) was found in the search — not applicable to any code ZuZan implements, logged for awareness only.
