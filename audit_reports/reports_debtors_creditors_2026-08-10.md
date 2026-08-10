# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 10 August 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-08-09 (full PASS; one escalated action item re: Solutha payroll — now resolved, see below).

**Change detection since last run:** `git log` shows three new commits since `edf8180` — `c93ad01`, `7b6d6ae`, `669598f` (all "accountant multi-client — CompanyMembership, client picker, company switcher", 2026-08-09 20:45–20:50).

Reviewed `git diff edf8180 669598f --stat`: touches `App_js_fixed.js`, `zuzan-app/src/App.js`, `zuzan-backend/auth.py`, `zuzan-backend/billing.py`, `zuzan-backend/database.py`, `zuzan-backend/main.py`, `commit_and_push.bat`.
- **`database.py`:** adds a new `CompanyMembership` ORM class (new table, links users to companies they can access with a per-company role) plus a `CREATE TABLE IF NOT EXISTS company_memberships` / `CREATE UNIQUE INDEX` pair correctly positioned inside the migrations list literal (`:1461-1463`). Not a modification to `FixedAsset`/`wear_and_tear_rate` or any AR/AP/journal table.
- **`auth.py`:** adds `/auth/my-companies` and `/auth/switch-company/{id}` endpoints (184 lines) — authentication/authorization scope, not Reports/Debtors/Creditors/AFS/tax logic.
- **`App_js_fixed.js` / `App.js`:** adds a `ClientPicker` component and a sidebar company-switcher dropdown. Confirmed by reading the diff directly — purely UI for selecting which company an accountant is working in; does not touch the Debtors, Creditors, Reports, or AFS views.
- **`main.py`:** one-line diff, purely cosmetic — more repeated `# disabled` comment noise appended to the already-disabled `_SubscriptionGateMiddleware` line (pre-existing dead code, unrelated to `/v1/summary`).
- **`billing.py`:** three more duplicate `resp = None` lines added ahead of existing duplicates in `adhoc_charge` — dead code, cosmetic, no logic change (same pattern flagged in prior reports).

**No functional changes to the audited surface area (Reports/Debtors/Creditors/journal/AFS/tax) since 08-09.** Working tree `git status` still shows the same five modified-but-uncommitted files as prior runs (`auth.py`, `billing.py`, `companies.py`, `main.py`, `payroll.py`) — consistent with the ongoing whitespace/line-ending noise tracked since 07-26.

Re-verified the highest-risk anchors directly via Grep this run — all line numbers unchanged from 08-09:
- `grep '"deferred_tax": 0.0'` on `financial_statements.py` → no matches (hard-coded zero still absent).
- `wear_and_tear_rate` column (`database.py:483`) and its `ALTER TABLE` (`database.py:1397`) confirmed still inside the migrations list literal.
- `purchase_order_reversal` present at all four expected reversal-aware call sites (`financial_statements.py:558`, `journal.py:848`, `payroll.py:1778,2534`, `purchase_orders.py:445`).
- `decrypt_field` present in `suppliers.py:7,48-50`.
- Journal coverage functions all present and wired in `journal.py`: `post_invoice_raised` (:194), `post_invoice_paid` (:234), `post_invoice_cogs` (:268), `post_expense` (:293), `post_payroll` (:368), `post_expense_paid` (:447), `post_po_received` (:476), `post_po_paid` (:528).
- Import-awareness: `source == "import"` exclusions at `payroll.py:1736,1812` confirmed present.
- `payroll.py` `TAX_YEARS["2026/2027"]` (:131), `"2027/2028"` placeholder (:151), `CURRENT_TAX_YEAR` (:182), `S11F_CAP = 430_000` (:196), `VAT_RATE = 0.15` (:1608, :2691) confirmed unchanged.
- Read the full text of `dashboard()` (`payroll.py:1225-1267`), Rule 7 AP netting (`payroll.py:1753-1794`), `_deferred_tax_balance()` (`financial_statements.py:131-173`), and `/v1/summary` (`main.py:446-491`) directly — logic identical to what was captured in the 08-09 report.

**Resolved since last run:** the Solutha (company id 3) missing-payroll item escalated across the 08-07/08-08/08-09 reports was confirmed by Soso on 2026-08-09 to be a false alarm — those 3 employees are test data, not a live payroll client. Per updated guidance, this run does not query or flag Solutha's payslip recency.

Fresh web search this run confirms no new SARS or IFRS developments since 08-09 (see §7 for details).

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ✅ PASS — logic unchanged, re-verified |
| Debtors (AR) | ✅ PASS — aged from due_date, paid excluded, ZAR amounts |
| Creditors (AP) | ✅ PASS — reversal-aware, bank details decrypted |
| Cross-module consistency | ✅ PASS — full journal coverage, import-awareness intact, migration hygiene intact |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) verified again, no regressions |
| Tax rates (SARS) | ✅ PASS — 2026/2027 tables current, no rate changes since 08-09 |

**Overall: PASS.** The only code changes since the last audit (accountant multi-client / company switcher feature) fall entirely outside Reports/Debtors/Creditors/AFS/tax scope. No open action items — the Solutha payroll item that had escalated for three consecutive reports is resolved (confirmed test data, not a compliance gap).

---

## 2. Reports

✓ No issues found.
- Dashboard (`payroll.py:1225-1270`): `total_revenue` sums only paid invoices via `_to_zar()` plus `_bank_import_income()`; `total_outstanding` sums `sent`/`overdue` invoices via `_to_zar()`. Expenses summed ex-VAT, separate from revenue.
- PO COGS uses delivered-value-only for partials (`_po_delivered_net`), no double-counting with payroll or depreciation.
- Payroll costs included in expenses via the payslip sum, applied after gross profit.
- Management accounts and `/v1/summary` (`main.py:446-491`) both route revenue/outstanding through `_to_zar()` and mirror the dashboard formula. Confirmed `/v1/summary` untouched by this run's new commits.

## 3. Debtors

✓ No issues found.
- Invoice status filter confirmed: `Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])` — paid invoices excluded.
- Aging cutoffs keyed off `due_date`, not invoice date (`payroll.py:1623-1630`, Rule 2 shown as an example — same pattern used across all aging buckets).
- ZAR conversion via `_to_zar()` applied consistently, including per-item display amounts.

## 4. Creditors

✓ No issues found.
- Reversal-awareness (2026-07-13 fixes) confirmed present at all four call sites — every site nets `source IN ("purchase_order", "purchase_order_reversal")`.
- AP control (Rule 7, `payroll.py:1753-1794`) computes per-PO expected credit from `credit − debit` journal lines, falling back to `po.total_amount` only when no journal entry exists yet.
- Supplier bank details decrypted via `decrypt_field` (`suppliers.py:7,48-50`) — unchanged.

## 5. Cross-module consistency

✓ No issues found.
- Journal coverage complete: `post_invoice_raised`, `post_invoice_paid`, `post_invoice_cogs`, `post_expense`, `post_payroll`, `post_expense_paid`, `post_po_received`, `post_po_paid` — no gaps.
- Import-awareness (2026-07-11 fixes) intact: Rules 6/7 exclude `source == "import"` on 1100/2000 (`payroll.py:1736,1812`); balance sheet retains imported equity offsets 3998/3999. Non-ZAR invoice imports still require an exchange rate; unbalanced journal-import groups still rejected; both invoice and journal imports auto-run the backfill.
- Migration hygiene re-verified: `wear_and_tear_rate` column and `ALTER TABLE` still positioned inside the migrations list literal. The new `CompanyMembership` table (added this run) is a fresh `Base` model with its own belt-and-braces `CREATE TABLE IF NOT EXISTS` inside the same migrations list — correctly placed, not appended after the loop.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (declared in AFS meta). Statements: income statement, statement of financial position, changes in equity, cash flow (indirect), notes 2-9.

**Standards status (fresh web search this run):**
- **IFRS 18** *Presentation and Disclosure in Financial Statements* — still effective for annual periods beginning on/after 1 January 2027, not applicable to IFRS-for-SMEs preparers (ZuZan's basis). No change.
- **IFRS for SMEs third edition** (issued 27 February 2025, effective 1 January 2027, early adoption permitted) — this run's search surfaced the June 2026 IFRS.org update and confirmed Q1 2026 educational-resource modules are out with more due Q3 2026. The narrow-scope standard-setting item on paragraph 9.3 remains open/unresolved by the IASB, no change from 08-09. No changes to the substantive Section 23 revenue/Section 12 fair value/financial-instruments text used by the existing transition plan. `ifrs_smes_3rd_edition_transition_plan.md` remains current.
- VAT rate: reconfirmed 15% standard rate — the 2025 legislation for a phased rise to 16% by April 2026 remains reversed. Corporate income tax: 27% flat rate, unchanged for years of assessment ending 1 Apr 2026 – 31 Mar 2027.

**Section 5b — deferred tax: already implemented, re-verified this run:**
- Grepped `financial_statements.py` for `"deferred_tax": 0.0"` — no matches.
- Per-asset tax base = cost − cumulative SARS wear-and-tear allowance; temporary difference × `_CIT_RATE` (27%) drives the deferred tax balance (`_deferred_tax_balance()`, `financial_statements.py:131-173`). Read the full function body this run — logic unchanged: analytic carrying-value calc mirrors the fixed-asset register's own depreciation methods (straight-line and diminishing-balance), disposed assets excluded, unmappable categories floor the temporary difference at zero.
- Opening/closing balances drive `deferred_tax_expense` = closing − opening; Note 9 fields populated; `total_tax = tax_expense + deferred_tax_expense`; balance-sheet movement line present.
- Finance costs (2026-07-13 fix): interest presented below EBIT, tax/net profit derive from `profit_before_tax` — unchanged.

✓ No issues found.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date.

- No rate changes found since the 08-09 audit.
- **2026 draft TLAB / TALAB:** published 30 July 2026, still in public comment (closes 28 August 2026, per fresh search of Treasury/SARS/GoLegal/IOL/RegFollower/Nexia/gov.za/Accounting Weekly/SAIT sources) — **not yet enacted**. Same proposal set as 08-09 (living annuity de minimis, non-resident spouse donations-tax exemption, SEZ transfer pricing, leasehold improvements, carbon budget refunds). No code impact.
- VAT confirmed 15% (2025 planned 16% escalation remains legislatively reversed) — matches `VAT_RATE = 0.15` in code (`payroll.py:1608, 2691`).
- CIT confirmed flat 27% for standard companies; SBC tiered rates apply only to registered Small Business Corporations — ZuZan does not implement SBC-specific tiering, consistent with prior audits (not a defect).
- VAT registration threshold increases (compulsory R1m→R2.3m, voluntary R50k→R120k, effective 1 April 2026) — registration thresholds, not rates, no effect on VAT calculation logic.
- s11F retirement fund deduction cap R430,000 (`payroll.py:196`), rate 27.5% — unchanged.
- UIF: 1% employee / 1% employer, ceiling R17,712 → max R177.12/month per party (`TAX_YEARS["2026/2027"]["uif_ceil"]`, `payroll.py:144`) — unchanged.
- SDL 1% of gross remuneration, R500,000 annual-payroll small-employer exemption — unchanged.
- Provisional `2027/2028` `TAX_YEARS` entry remains a placeholder copy of 2026/2027 pending the Feb 2027 Budget — standing reminder, not a defect.
- EMP201 monthly deadline reconfirmed as the 7th of the following month (moved to the prior business day if the 7th falls on a weekend/public holiday) — no change to the app's due-date logic needed.
- Rates unchanged and current tax year present — no edits made (report-only per task rules; section 5b already implemented, verification-only this run).

**Sources consulted:** [National Treasury Publishes 2026 Draft Tax Bills — Tax Consulting SA](https://www.taxconsulting.co.za/national-treasury-publishes-2026-draft-tax-bills-for-public-comment/) · [2026 Draft Tax Bills — GoLegal](https://www.golegal.co.za/2026-draft-tax-bills/) · [South Africa consults on 2026 draft tax legislation — RegFollower](https://regfollower.com/south-africa-consults-on-2026-draft-tax-legislation/) · [Tax Practice Weekly Update — SAIT](https://thesait.org.za/tax-practice-weekly-update-issue-37-4-2-3-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-3-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2/) · [Treasury publishes 2026 draft tax bills — Nexia SAB&T](https://www.nexia-sabt.co.za/treasury-publishes-2026-draft-tax-bills-for-public-comment/) · [Big tax changes proposed — IOL](https://iol.co.za/business/2026-08-06-big-tax-changes-proposed-what-the-new-draft-bills-mean-for-taxpayers/) · [The 2026 Draft Tax Bills Are Out — Accounting Weekly](https://www.accountingweekly.com/sars-updates/2026-draft-tlab-and-talab-what-accountants-must-know) · [National Treasury media statement — gov.za](https://www.gov.za/news/media-statements/national-treasury-publication-2026-draft-tax-bills-comment-30-jul-2026) · [June 2026 IFRS for SMEs Accounting Standard Update — IFRS.org](https://www.ifrs.org/supporting-implementation/2015-ifrs-for-smes-supporting-materials/sme-updates/2026/june-2026-ifrs-for-smes-accounting-standard-update/) · [January 2026 IASB Update — IFRS.org](https://www.ifrs.org/news-and-events/news/2026/02/iasb-update-january-2026-ifric-addendum-november-2025-available/) · [VAT in 2026: Navigating Stability — SAIT](https://thesait.org.za/vat-in-2026-navigating-stability-and-the-legacy-of-the-2025-reversals/) · [VAT Rate in South Africa 2026 — VAT Calculator SA](https://vatcalculator.co.za/vat-rate-south-africa/) · [South Africa 2026 Budget ducks VAT rise — vatcalc.com](https://www.vatcalc.com/south-africa/south-africa-vat-rise/) · [Value-Added Tax — SARS](https://www.sars.gov.za/types-of-tax/value-added-tax/)

## 8. Action items

None. No open action items — the Solutha payroll item that had escalated across the three prior reports (08-07 → 08-09) is resolved: confirmed by Soso on 2026-08-09 to be test data, not a live payroll client, and no longer flagged per updated guidance.

**Standing reminders (not defects, carried from prior reports):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry (`payroll.py:151+`) after Budget Feb 2027 and restart the backend;
(b) early-2027 runs should execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`);
(c) the AFS PayFast payment/ad-hoc tokenization feature and the `/reports/ai-insights` feature remain outside this audit's scope;
(d) NBCPSS private security payroll mode predates this audit's baseline, not yet part of this checklist's explicit scope;
(e) file-attribution note: the imported-equity-offset (3998/3999) exclusion logic lives in `payroll.py`'s `balance_sheet()`, not `financial_statements.py`;
(f) the s20A loss-ring-fencing threshold change is not applicable to any code ZuZan implements — awareness only;
(g) track the 2026 draft TLAB/TALAB (comment period closes 28 August 2026) — once enacted, re-check whether any finalized provisions require rate/table changes;
(h) `App_js_fixed.js`'s new `ClientPicker` component and `/auth/my-companies` / `/auth/switch-company/{id}` endpoints (accountant multi-client feature, new this run) remain outside Reports/Debtors/Creditors/AFS/tax scope, flagged for awareness only;
(i) IASB paragraph 9.3 narrow-scope standard-setting item (IFRS for SMEs 3rd edition) still open — not yet resolved by the IASB, no action needed until finalized.
