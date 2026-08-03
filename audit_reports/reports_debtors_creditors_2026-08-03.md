# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 3 August 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-08-02 (full PASS, no open action items).

**Change detection since last run:** `git log 94550db..HEAD` shows HEAD now `1eb36f5` (2026-08-02 21:45), five commits (`f1245f8`, `ad74275`, `f6504f3`, `1474ea7`, `1eb36f5`) messaged "fix: plan upgrade for trial users + AI assistant keyword handlers" / "fix: billing bugs — adhoc_charge NameError, AFS decrypt, daily charges loop + PayFast UI warnings". `git diff 94550db..HEAD --stat -w` touches only `App_js_fixed.js`, `zuzan-app/src/App.js`, `zuzan-backend/billing.py`, `zuzan-backend/main.py`, plus non-scope files (the 08-02 report itself, `commit_and_push.bat`, `netlify.toml`, `patch_backend.py`). Inspected every in-scope diff directly:
- `main.py` (+5/-1): daily billing-check loop now also calls `run_monthly_charges()`; a disabled-middleware comment line got re-duplicated (cosmetic). The `/v1/summary` block (lines 448-489) is untouched.
- `billing.py` (not in this audit's file list, but skimmed since the commit message says "AFS decrypt"): fixes an `adhoc_charge` `NameError` when the PayFast request throws (added `resp = None` guard) and switches the **AFS-purchase PayFast checkout** (`afs_initiate`, a paid-download feature for the AFS PDF) to decrypt `payfast_merchant_id/key/passphrase` via `decrypt_field` before use. This is the billing/paywall for downloading the AFS document, not the AFS accounting content — confirmed out of scope per the standing reminder in the 08-02 report, item (c).
- `App_js_fixed.js` / `App.js` (+18 each): adds a `hasPayfast` prop to `SendInvoicePanel` and PayFast-not-configured warning banners (Bank Feeds tab, Settings). UI/UX only — no change to invoice status, amount, or ZAR-conversion logic.
- Working tree `git status` shows `auth.py`, `billing.py`, `companies.py`, `main.py`, `payroll.py` as modified-but-uncommitted; `git diff -w` on the in-scope subset (`companies.py`, `main.py`, `payroll.py`) returns **empty** — line-ending/whitespace noise only, no functional diff.

**None of this run's changes touch the audited surface area.** Re-verified all core logic directly via Read/Grep (not bash, per the stale-mount-cache pitfall) rather than relying solely on the diff — see sections below, all line references unchanged from 08-02.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ✅ PASS — logic unchanged, re-verified |
| Debtors (AR) | ✅ PASS — aged from due_date, paid excluded, ZAR amounts |
| Creditors (AP) | ✅ PASS — reversal-aware, bank details decrypted |
| Cross-module consistency | ✅ PASS — full journal coverage, import-awareness intact, migration hygiene intact |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) verified again, no regressions |
| Tax rates (SARS) | ✅ PASS — 2026/2027 tables current, no rate changes since 08-02 |

**Overall: PASS.** No functional code changes to the audited surface since the last audit; no new action items.

---

## 2. Reports

✓ No issues found. Re-confirmed via direct Read/Grep this run:
- Dashboard (`payroll.py:1237,1245`): `total_revenue = sum(_to_zar(i) for i in paid_invoices)` (plus `_bank_import_income`, `:1239`); `total_outstanding = sum(_to_zar(i) for i in outstanding_invoices)`. Expenses aggregated separately, ex-VAT — never mixed into revenue.
- Payroll costs correctly included in expenses via `total_payroll`, applied after gross profit.
- PO costs: `po_cogs = sum(_po_delivered_net(po) for po in received_pos)` (`:1260`) — delivered-value-only for partials, added once to `total_expenses`, no double counting with payroll or straight expenses.
- Management accounts (`payroll.py:2078,2151-2153`): revenue and outstanding both route through `_to_zar()`; PO COGS folded into `total_expenses` consistently with the dashboard.
- `/v1/summary` (`main.py:448-489`): imports `_to_zar`, `_po_delivered_net`, `_bank_import_income` from payroll.py (`:448`); `total_revenue` (`:452-453`), `total_expenses` (incl. PO COGS `:467`, payroll, depreciation `:472`), `outstanding` (`:482`) — all mirror the dashboard formula 1:1. Confirmed this block is outside the diff touching the daily-billing-loop change at `:171-173`.

## 3. Debtors

✓ No issues found.
- Invoice status filter confirmed at every debtors-relevant site (`payroll.py:1243,1627-1628,1723,2151`): `Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])` — paid invoices excluded.
- Aging cutoffs keyed off `due_date`, not invoice date (`payroll.py:1628`: `Invoice.due_date <= cutoff_90`).
- ZAR conversion via `_to_zar()` applied at every debtors amount (`payroll.py:1630,1642`).

## 4. Creditors

✓ No issues found.
- **Reversal-awareness (2026-07-13 fixes) re-confirmed present in all five call sites this run:** `payroll.py:1778` (Rule 7 AP control check) and `payroll.py:2534` (creditors-aging), `purchase_orders.py:445` (pay_po), `journal.py:848` (backfill), `financial_statements.py:558` (balance sheet PO liability) — every site nets `source IN ("purchase_order", "purchase_order_reversal")`.
- AP control (Rule 7, `payroll.py:1753-1789`) computes per-PO expected credit from `credit − debit` journal lines, falling back to `po.total_amount` only when no journal entry exists yet.
- Supplier bank details decrypted via `decrypt_field` (`suppliers.py:48-50`) — unchanged from prior audits.

## 5. Cross-module consistency

✓ No issues found.
- Journal coverage complete: `post_invoice_raised`, `post_invoice_paid`, `post_invoice_cogs`; `post_expense`, `post_expense_paid`; `post_payroll`; `post_po_received`, `post_po_paid` — all present in `journal.py`, no gaps.
- Import-awareness (2026-07-11 fixes) intact: Rules 6/7 exclude `JournalEntry.source == "import"` on 1100/2000; balance sheet retains imported equity offsets 3998/3999 (this logic lives in `payroll.py`'s `balance_sheet()`, per the file-attribution correction noted in the 08-02 report). Non-ZAR invoice imports still require an Exchange Rate column (`csv_import.py:458-476`). Unbalanced journal-import groups still rejected (`csv_import.py:1017,1035-1067`). Both invoice and journal imports auto-run the backfill (`csv_import.py:124-143,501,563`).
- **Migration hygiene re-verified:** `wear_and_tear_rate` column (`database.py:483`) and its `ALTER TABLE` (`database.py:1363`) confirmed still positioned inside the migrations list literal, not after the loop — read directly via the Read/Grep tools per the known dead-code pitfall.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (declared in AFS meta). Statements: income statement, statement of financial position, changes in equity, cash flow (indirect), notes 2-9.

**Standards status (fresh web search this run):**
- **IFRS 18** *Presentation and Disclosure in Financial Statements* — still effective for annual periods beginning on/after 1 January 2027, early adoption permitted. Still does not apply to IFRS-for-SMEs preparers (ZuZan's basis). No change since 08-02.
- **IFRS for SMEs third edition** (issued February 2025) — still effective 1 January 2027. Checked the IASB's March 2026 *Accounting Standard Update* (fresh, not seen in prior reports): this quarter's spotlight is **Section 9 Consolidated and Separate Financial Statements** (new IFRS 10-style single control model, replacing the old IAS 27/SIC-12 basis) plus an open SME Implementation Group question on the paragraph 9.3 consolidation exemption for intermediate parents of investment entities. **Not applicable to ZuZan** — it produces single-entity AFS only, consistent with the existing transition plan (`ifrs_smes_3rd_edition_transition_plan.md` §2.3). No action needed.
- **VAT rate:** reconfirmed 15% standard rate, unchanged; compulsory registration threshold R2.3m (1 Apr 2026) and voluntary threshold R120,000, both already reflected in prior reports — no bearing on the rate constant.
- **Corporate income tax:** reconfirmed 27%, unchanged per Budget 2026 (years of assessment ending 1 Apr 2026 – 31 Mar 2027).

**Section 5b — deferred tax: already implemented, re-verified this run (financial_statements.py, read/grepped directly):**
- `_deferred_tax_balance()` (`financial_statements.py:131`) — no hard-coded `0.0` remains.
- `dt_opening`/`dt_closing` computed per period (`:266-267`); `deferred_tax_expense = dt_closing − dt_opening` (`:268`); `total_tax = tax_expense + deferred_tax_expense` (`:601`); note fields `deferred_tax`, `deferred_tax_opening_balance`, `deferred_tax_closing_balance` present (`:606,609-610`).
- Balance sheet carries the closing DTL/DTA with matching `deferred_tax_movement` retained-earnings adjustment (`:681`) — Assets = Equity + Liabilities preserved by construction.
- `wear_and_tear_rate` column (`database.py:483`) and migration (`database.py:1363`) confirmed present and correctly placed (see §5).
- Frontend renders the deferred tax row when non-zero (unchanged, per prior audit's `App_js_fixed.js` line references — not touched by this run's diff).
- **Finance costs (2026-07-13 fix) re-confirmed:** interest/finance-cost lines presented below EBIT (`financial_statements.py:211`); `profit_before_tax = ebit − finance_costs` (`:259`), `tax_expense`/`net_profit` derive from `profit_before_tax`, not EBIT (`:260-261`).

✓ No issues found.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date, and correctly selected by `_current_tax_year()` (`payroll.py:169-182`).

- No rate changes found since the 08-02 audit. Fresh search this run reconfirms: PIT brackets 18%/26%/31%/36%/39%/41%/45% at thresholds R245,100/R383,100/R530,200/R695,800/R887,000/R1,878,600; primary rebate R17,820, secondary R9,765, tertiary R3,249 (Budget 2026's inflationary 3.4% bracket/rebate adjustment already baked in); UIF ceiling R17,712/month — all match `payroll.py:131-145` (`TAX_YEARS["2026/2027"]`) exactly.
- **UIF** 1%/1%, **SDL** 1% (`payroll.py:188-189`) — unchanged, consistent with current SARS rules.
- **VAT** standard rate 15% (`payroll.py:1608,2691`) — unchanged; searches also reconfirm the R20bn in previously-flagged 2026 tax increases were formally withdrawn (fiscal metrics improved) — no bearing on any rate ZuZan implements.
- **Corporate income tax** 27% (`fixed_assets.py:78` `SA_CIT_RATE`, referenced by `financial_statements.py:82`) — unchanged, confirmed for years of assessment ending 1 Apr 2026 – 31 Mar 2027.
- Provisional `2027/2028` `TAX_YEARS` entry (`payroll.py:151-166`) remains a placeholder copy of 2026/2027 pending the Feb 2027 Budget — standing reminder, not a defect.
- Rates unchanged and current tax year present — no edits made (report-only per task rules; section 5b already implemented, verification-only this run).

**Sources consulted:** [Budget 2026 Frequently Asked Questions — SARS](https://www.sars.gov.za/about/sars-tax-and-customs-system/budget/budget-2026-frequently-asked-questions/) · [South Africa Introduces Updated Income Tax Thresholds in Budget 2026 — activpayroll](https://www.activpayroll.com/news-articles/south-africa-introduces-updated-income-tax-thresholds-in-budget-2026) · [Budget 2026: a small win for taxpayers — TaxTim](https://www.taxtim.com/za/blog/budget-2026) · [Beefed-up SARS might stave off R20bn in tax increases in 2026 — Moonstone](https://www.moonstone.co.za/beefed-up-sars-might-stave-off-r20bn-in-tax-increases-in-2026/) · [Income tax brackets, medical tax credits adjusted for inflation — Moonstone](https://www.moonstone.co.za/income-tax-brackets-medical-tax-credits-adjusted-for-inflation/) · [Budget Speech 2026/2027: Tax Overview — Werksmans Attorneys](https://werksmans.com/budget-speech-2026-2027-tax-overview/) · [National Budget Speech 2026 — SimplePay](https://www.simplepay.co.za/blog/2026/02/27/national-budget-speech-2026/) · [IFRS for SMEs third edition — ACCA](https://www.accaglobal.com/learning-and-events/corporate-reporting/third-edition-ifrs-for-smes.html) · [March 2026 IFRS for SMEs Accounting Standard Update — IFRS.org](https://www.ifrs.org/supporting-implementation/2015-ifrs-for-smes-supporting-materials/sme-updates/2026/march-2026-ifrs-for-smes-accounting-standard-update/) · [IASB issues third edition of the IFRS for SMEs — PwC Viewpoint](https://viewpoint.pwc.com/dt/gx/en/pwc/in_briefs/in_briefs_INT/in_briefs_INT/iasb-issues.html)

## 8. Action items

None open.

**Standing reminders (not defects, carried from prior reports):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry (`payroll.py:151+`) after Budget Feb 2027 and restart the backend;
(b) early-2027 runs should execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`) — Section 23 revenue and Section 19 business-combinations changes are most relevant to ZuZan; Section 9 (consolidation) confirmed not applicable this run since ZuZan is single-entity only;
(c) the AFS PayFast payment/ad-hoc tokenization feature and the `/reports/ai-insights` (AI management-pack) feature remain outside this audit's Reports/Debtors/Creditors/AFS-content/tax scope. This run's diff shows continued active development here (`billing.py` `adhoc_charge`/`afs_initiate` NameError + decrypt fixes, PayFast setup-warning banners in `App_js_fixed.js`) — worth folding into scope once the `/billing/subscribe` endpoint lands, since it will touch `main.py`;
(d) NBCPSS private security payroll mode (grades, allowances, BC levy, PSIRA fee) predates this audit's baseline and doesn't affect the audited totals, but isn't yet part of this checklist's explicit scope — consider adding it to the payroll section of future audits;
(e) file-attribution note (carried from 08-01/08-02): the imported-equity-offset (3998/3999) exclusion logic lives in `payroll.py`'s `balance_sheet()`, not `financial_statements.py`.
