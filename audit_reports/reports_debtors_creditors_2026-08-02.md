# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 2 August 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-08-01 (full PASS, no open action items).

**Change detection since last run:** `git log 11d43fd..HEAD` shows HEAD now `94550db` (2026-08-01 23:00), four commits (`62b46ee`, `902977c`, `837ac21`, `94550db`) all under the message "fix: plan upgrade for trial users + AI assistant keyword handlers". `git diff 11d43fd..HEAD --stat -w` (whitespace-ignored) touches `App_js_fixed.js`, `zuzan-app/src/App.js`, `zuzan-backend/companies.py`, `zuzan-backend/main.py`, `zuzan-backend/payroll.py` plus non-scope files (`main_py_fixed.py`, `patch_backend.py`, `commit_and_push.bat`). Inspected every in-scope diff directly:
- `payroll.py` (1 line): Claude model string pin `claude-haiku-4-5` → `claude-haiku-4-5-20251001` in the AI insights call — no financial logic touched.
- `companies.py` (+13): adds `plan`/`billing_cycle` fields to `CompanyUpdate` with validation — subscription/billing feature, not Reports/Debtors/Creditors/AFS/tax.
- `main.py` (+61 non-whitespace): AI chat model string pin (same as above) plus a large expansion of `_keyword_fallback()` (the AI assistant's canned-reply keyword matcher covering employees, payslips, EMP201, leave, provisional tax, inventory, budgets, fixed assets, bank feeds, reconciliation, customers, suppliers, documents, plans/settings) — all above/unrelated to the `/v1/summary` block (still at the same lines, unaffected). No change to any Reports/AR/AP/journal/AFS/tax logic.
- `App_js_fixed.js` / `zuzan-app/src/App.js` (+18 each): frontend plan-upgrade flow now redirects to PayFast subscription checkout instead of a no-op PUT; default plan fallback label corrected from "professional" to "starter". Settings/billing UI, not Reports/Debtors/Creditors/AFS.
- Working-tree `git status` also showed `auth.py`, `companies.py`, `main.py`, `payroll.py` as modified-but-uncommitted; `git diff -w` on all four returns **empty** — line-ending/whitespace noise only, no functional diff.

**None of this run's changes touch the audited surface area.** Re-verified all core logic directly via Read/Grep (not bash, per the stale-mount-cache pitfall) rather than relying solely on the diff.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ✅ PASS — logic unchanged, re-verified |
| Debtors (AR) | ✅ PASS — aged from due_date, paid excluded, ZAR amounts |
| Creditors (AP) | ✅ PASS — reversal-aware, bank details decrypted |
| Cross-module consistency | ✅ PASS — full journal coverage, import-awareness intact, migration hygiene intact |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) verified again, no regressions |
| Tax rates (SARS) | ✅ PASS — 2026/2027 tables current, no rate changes since 08-01 |

**Overall: PASS.** No functional code changes to the audited surface since the last audit; no new action items.

---

## 2. Reports

✓ No issues found. Re-confirmed via direct Read/Grep this run:
- Dashboard (`payroll.py:1237,1245`): `total_revenue = sum(_to_zar(i) for i in paid_invoices)` (plus `_bank_import_income`, `:1239`); `total_outstanding = sum(_to_zar(i) for i in outstanding_invoices)`. Expenses aggregated separately (`:1248-1251`, ex-VAT) — never mixed into revenue.
- Payroll costs correctly included in expenses via `total_payroll` (all-time payslip sum, `:1275-1285`), applied after gross profit (`:1287-1288`).
- PO costs: `po_cogs = sum(_po_delivered_net(po) for po in received_pos)` (`:1256-1261`) — delivered-value-only for partials, added once to `total_expenses`, no double counting with payroll or straight expenses.
- Management accounts (`payroll.py:2044-2153`): revenue (`:2078`), outstanding (`:2153`) both route through `_to_zar()`; PO COGS (`:2095-2108`) and depreciation (`:2110-2118`) folded into `total_expenses` consistently with the dashboard.
- `/v1/summary` (`main.py:444-489`): imports `_to_zar`, `_po_delivered_net`, `_bank_import_income` from payroll.py (`:447`); `total_revenue` (`:451-452`), `total_expenses` (incl. PO COGS `:459-466`, depreciation `:467-471`, payroll `:472-480`), `outstanding` (`:481`) — all mirror the dashboard formula 1:1.

## 3. Debtors

✓ No issues found.
- Invoice status filter confirmed at every debtors-relevant site (`payroll.py:1243,1627-1628,1723,2151`): `Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])` — paid invoices excluded.
- Aging cutoffs keyed off `due_date`, not invoice date (`payroll.py:1628`: `Invoice.due_date <= cutoff_90`).
- ZAR conversion via `_to_zar()` applied at every debtors amount (`payroll.py:1630,1642`).

## 4. Creditors

✓ No issues found.
- **Reversal-awareness (2026-07-13 fixes) re-confirmed present in all five call sites this run:** `payroll.py:1778` (Rule 7 AP control check) and `payroll.py:2534` (creditors-aging), `purchase_orders.py:445` (pay_po), `journal.py:848` (backfill), `financial_statements.py:558` (balance sheet PO liability) — every site nets `source IN ("purchase_order", "purchase_order_reversal")`.
- AP control (Rule 7, `payroll.py:1753-1789`) computes per-PO expected credit from `credit − debit` journal lines, falling back to `po.total_amount` only when no journal entry exists yet.
- Supplier bank details decrypted via `decrypt_field` (unchanged from prior audits — file untouched since 06-15).

## 5. Cross-module consistency

✓ No issues found.
- Journal coverage complete: `post_invoice_raised`, `post_invoice_paid`, `post_invoice_cogs` (`journal.py:194,234,268`); `post_expense`, `post_expense_paid` (`:293,447`); `post_payroll` (`:368`, invoked at `:771`); `post_po_received`, `post_po_paid` (`:476,528`). No gaps.
- Import-awareness (2026-07-11 fixes) intact: `payroll.py:1736,1812` exclude `JournalEntry.source == "import"` on Rules 6/7; balance sheet retains imported equity offsets 3999 (Opening Balance Equity) / 3998 (Retained Earnings) via account-code match (`payroll.py:1526-1546` — note: this logic lives in `payroll.py`'s `balance_sheet()`, not `financial_statements.py`; correcting the file attribution carried in earlier reports). Non-ZAR invoice imports still require an Exchange Rate column and reject rows without one (`csv_import.py:458-476`). Unbalanced journal-import groups are still rejected with a per-row error (`csv_import.py:1017,1035-1067`). Both invoice and journal imports auto-run the backfill (`csv_import.py:124-143,501,563`).
- **Migration hygiene re-verified:** `wear_and_tear_rate` column (`database.py:483`) and its `ALTER TABLE` (`database.py:1363`) confirmed still positioned inside the migrations list literal, not after the loop — read directly via the Read/Grep tools per the known dead-code pitfall.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (declared in AFS meta). Statements: income statement, statement of financial position, changes in equity, cash flow (indirect), notes 2-9.

**Standards status (fresh web search this run):**
- **IFRS 18** *Presentation and Disclosure in Financial Statements* — confirmed effective for annual periods beginning on/after 1 January 2027 (issued April 2024), early adoption permitted. Still does not apply to IFRS-for-SMEs preparers (ZuZan's basis). No change since 08-01.
- **IFRS for SMEs third edition** (issued February 2025) — confirmed effective 1 January 2027; entities may early-adopt or continue applying the 2015 edition until then. New revenue model (IFRS 15-aligned), expanded fair value/financial instruments/business combinations requirements. No change since 08-01.
- **VAT rate:** reconfirmed 15% standard rate, unchanged; compulsory registration threshold raised to R2.3m (1 Apr 2026, already reflected in prior reports) — no bearing on the rate constant.
- **Corporate income tax:** reconfirmed 27%, unchanged per Budget 2026.

**Section 5b — deferred tax: already implemented, re-verified this run (financial_statements.py, read/grepped directly):**
- `_deferred_tax_balance()` (`financial_statements.py:131`) — no hard-coded `0.0` remains.
- `dt_opening`/`dt_closing` computed per period (`:266-267`); `deferred_tax_expense = dt_closing − dt_opening` (`:268`); `total_tax = tax_expense + deferred_tax_expense` (`:601`); note fields `deferred_tax`, `deferred_tax_opening_balance`, `deferred_tax_closing_balance` present (`:606,609-610`).
- Balance sheet carries the closing DTL/DTA with matching `deferred_tax_movement` retained-earnings adjustment (`:681`) — Assets = Equity + Liabilities preserved by construction.
- `wear_and_tear_rate` column (`database.py:483`) and migration (`database.py:1363`) confirmed present and correctly placed (see §5).
- Frontend renders the deferred tax row/type badge when non-zero (`App_js_fixed.js:10361-10362,10382,10385,11817-11818`).
- **Finance costs (2026-07-13 fix) re-confirmed:** interest/finance-cost lines (account 6700 or name-matched) presented below EBIT (`financial_statements.py:205-209`); `profit_before_tax = ebit − finance_costs` (`:259`), `tax_expense`/`net_profit` derive from `profit_before_tax`, not EBIT (`:260-261`).

✓ No issues found.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date, and correctly selected by `_current_tax_year()` (`payroll.py:170-182`).

- No rate changes found since the 08-01 audit. Fresh search this run reconfirms: PIT brackets 18%/26%/31%/36%/39%/41%/45% at thresholds R245,100/R383,100/R530,200/R695,800/R887,000/R1,878,600; primary rebate R17,820, secondary R9,765, tertiary R3,249; UIF ceiling R17,712/month — all match `payroll.py:132-144` exactly (`TAX_YEARS["2026/2027"]`).
- **UIF** 1%/1% (`payroll.py:188`), **SDL** 1% (`payroll.py:189`) — unchanged, consistent with current SARS rules.
- **VAT** standard rate 15% (`companies.py:191`, `payroll.py:1608,2691`, `quotes.py:15`) — unchanged.
- **Corporate income tax** 27% (`financial_statements.py:84` `_CIT_RATE`, `fixed_assets.py:78` `SA_CIT_RATE`) — unchanged, confirmed for years of assessment ending 1 Apr 2026 – 31 Mar 2027.
- Provisional `2027/2028` `TAX_YEARS` entry (`payroll.py:146-166`) remains a placeholder copy of 2026/2027 pending the Feb 2027 Budget — standing reminder, not a defect.
- Rates unchanged and current tax year present — no edits made (report-only per task rules; section 5b already implemented, verification-only this run).

**Sources consulted:** [IFRS - 2025 IFRS for SMEs supporting materials — IFRS.org](https://www.ifrs.org/supporting-implementation/2025-ifrs-for-smes-supporting-materials/) · [IFRS Standards Effective 2026: Compliance Guide — Prima Consulting](https://primaconsulting.org/ifrs-changes-2026-update/) · [IFRS for SMEs — ICAEW](https://www.icaew.com/technical/corporate-reporting/ifrs/ifrs-accounting-standards-tracker/ifrs-for-smes) · [IASB issues third edition of the IFRS for SMEs — PwC Viewpoint](https://viewpoint.pwc.com/dt/gx/en/pwc/in_briefs/in_briefs_INT/in_briefs_INT/iasb-issues.html) · [IFRS for SMEs Accounting Standard Third Edition, Feb 2025 — IFRS.org](https://www.ifrs.org/content/dam/ifrs/publications/ifrs-for-smes/english/2025/ifrs-for-smes.pdf) · [IFRS 18 and the Updated IFRS for SMEs Standard — Grant Thornton](https://www.grantthornton-bq.com/publications/bonaire/ifrs-update/) · [Company Income Tax Calculator & Corporate Tax Rate 2026 Guide — Tax Planners](https://taxplanners.co.za/company-income-tax-calculator-south-africa/) · [Budget 2026 Frequently Asked Questions — SARS](https://www.sars.gov.za/about/sars-tax-and-customs-system/budget/budget-2026-frequently-asked-questions/) · [Corporate Tax remains unchanged, with a pinch of positivity — BDO](https://www.bdo.co.za/en-za/insights/2026/budget-speech/corporate-tax-remains-unchanged,-with-a-pinch-of-positivity) · [PAYE Tax Tables 2026 South Africa — E2E Financial](https://e2efinancial.co.za/resources/paye-tax-tables-2026) · [SA Tax Brackets 2026/2027 — taxed.co.za](https://taxed.co.za/tax-brackets/2026-2027) · [SARS Tax Tables 2026/2027 — Accounter](https://accounter.co.za/news/sars-tax-tables-2026-2027)

## 8. Action items

None open.

**Standing reminders (not defects, carried from prior reports):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry (`payroll.py:146+`) after Budget Feb 2027 and restart the backend;
(b) early-2027 runs should execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`) — Section 23 revenue and Section 19 business-combinations changes are most relevant to ZuZan; watch for any new Consolidation Exception exposure-draft developments;
(c) the AFS PayFast payment/ad-hoc tokenization feature and the `/reports/ai-insights` (AI management-pack) feature remain outside this audit's Reports/Debtors/Creditors/AFS-content/tax scope — flag for inclusion if a future audit's file list is expanded. Note: this run's diff shows active development on PayFast subscription checkout (`App_js_fixed.js` `handleUpgrade`, `companies.py` plan/billing_cycle fields) — worth folding into scope once a `/billing/subscribe` endpoint lands, since it will touch `main.py`;
(d) NBCPSS private security payroll mode (grades, allowances, BC levy, PSIRA fee) predates this audit's baseline and doesn't affect the audited totals, but isn't yet part of this checklist's explicit scope — consider adding it to the payroll section of future audits;
(e) corrected file attribution this run: the imported-equity-offset (3998/3999) exclusion logic lives in `payroll.py`'s `balance_sheet()` (`:1526-1546`), not `financial_statements.py` as stated in the 07-31/08-01 reports — update future report templates accordingly.
