# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 9 August 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-08-08 (full PASS, no open action items besides the Solutha payroll gap).

**Change detection since last run:** `git log` shows three new commits since `b277cdc` — `fecf2ba`, `070df8b`, `edf8180` (all "bank interest requests — notify button + admin dashboard counts", 2026-08-08 06:41–06:53), landed *after* the 08-08 report was generated (06:34) but were not yet reflected in that report.

Reviewed `git diff b277cdc edf8180 --stat`: touches `App_js_fixed.js`, `zuzan-app/src/App.js`, `zuzan-backend/bank_direct_feeds.py`, `zuzan-backend/billing.py`, `zuzan-backend/database.py`, `zuzan-backend/main.py`.
- **`main.py`:** adds a `bank_interest_router`, a new `/admin/api/bank-interest` endpoint, and a new "Bank Interest" tab on the internal admin dashboard (client interest counts per unconnected bank, for partnership prioritisation). No change to `/v1/summary` or any revenue/outstanding logic.
- **`database.py`:** adds a new `BankInterestRequest` ORM class (new table, not a migration to an existing audited table) — unrelated to `FixedAsset`/`wear_and_tear_rate` or any AR/AP/journal table.
- **`App_js_fixed.js`:** extends the existing `BankFeedPanel` "Coming Soon" state (flagged out-of-scope since 08-07) with a "🔔 Notify me" button that POSTs to the new endpoint. Still Pillar 3 (Bank Integration) UI, still out of scope for Reports/Debtors/Creditors/AFS/tax.
- **`billing.py`:** three more duplicate `resp = None` lines added ahead of the existing duplicates (dead code, cosmetic, `git diff -w` shows this is the only change) — no logic change.

**No functional changes to the audited surface area (Reports/Debtors/Creditors/journal/AFS/tax) since 08-08.** Working tree `git status` still shows the same five modified-but-uncommitted files as prior runs (`auth.py`, `billing.py`, `companies.py`, `main.py`, `payroll.py`); `git diff -w` on `companies.py`/`main.py`/`payroll.py` is empty (whitespace/line-ending noise only), consistent with every run since 07-26.

Re-verified the highest-risk anchors directly via Grep this run:
- `grep '"deferred_tax": 0.0'` on `financial_statements.py` → no matches (hard-coded zero still absent).
- `wear_and_tear_rate` column (`database.py:483`) and its `ALTER TABLE` (`database.py:1373`) confirmed still inside the migrations list literal.
- `purchase_order_reversal` present at all four expected reversal-aware call sites (`financial_statements.py:558`, `journal.py:848`, `payroll.py:1778,2534`, `purchase_orders.py:445`).
- `decrypt_field` present in `suppliers.py:7,48-50`.
- `_CIT_RATE` sourced from `fixed_assets.SA_CIT_RATE` with fallback 0.27 (`financial_statements.py:78-84`), used in deferred-tax calc (`:172`), current tax expense (`:260`), and Note 9 (`:604,641`).
- Journal coverage functions all present and wired in `journal.py`: `post_invoice_raised` (:194), `post_invoice_paid` (:234), `post_invoice_cogs` (:268), `post_expense` (:293), `post_payroll` (:368), `post_expense_paid` (:447), `post_po_received` (:476), `post_po_paid` (:528), all called from the backfill loop (:743–856).
- Import-awareness: `source == "import"` exclusions at `payroll.py:1736,1812` confirmed present.
- `payroll.py` `TAX_YEARS["2026/2027"]` (:131), `"2027/2028"` placeholder (:151), `CURRENT_TAX_YEAR` resolved via `_current_tax_year()` (:182), `S11F_CAP = 430_000` (:196), `VAT_RATE = 0.15` (:1608, :2691) confirmed unchanged.

Fresh web search this run confirms no new SARS or IFRS developments affecting the current tax year/standards beyond what was already tracked (see §7 for details).

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ✅ PASS — logic unchanged, re-verified |
| Debtors (AR) | ✅ PASS — aged from due_date, paid excluded, ZAR amounts |
| Creditors (AP) | ✅ PASS — reversal-aware, bank details decrypted |
| Cross-module consistency | ✅ PASS — full journal coverage, import-awareness intact, migration hygiene intact |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) verified again, no regressions |
| Tax rates (SARS) | ✅ PASS — 2026/2027 tables current, no rate changes since 08-08 |

**Overall: PASS.** The only code changes since the last audit (bank-interest "notify me" feature) fall entirely outside Reports/Debtors/Creditors/AFS/tax scope. One standing item has escalated further (see §8, item 1) — Solutha (company 3) still has not run payroll for June, July, or August 2026; a third consecutive EMP201 deadline is now at risk.

---

## 2. Reports

✓ No issues found.
- Dashboard (`payroll.py:1225-1270`): `total_revenue` sums only paid invoices via `_to_zar()` plus `_bank_import_income()`; `total_outstanding` sums `sent`/`overdue` invoices via `_to_zar()`. Expenses summed ex-VAT, separate from revenue.
- PO COGS uses delivered-value-only for partials (`_po_delivered_net`), no double-counting with payroll or depreciation.
- Payroll costs included in expenses via the payslip sum, applied after gross profit.
- Management accounts (`payroll.py:2078-2153`) and `/v1/summary` (`main.py:445-490`) both route revenue/outstanding through `_to_zar()` and mirror the dashboard formula. Confirmed `/v1/summary` untouched by this run's new commits.

## 3. Debtors

✓ No issues found.
- Invoice status filter confirmed at every debtors-relevant site: `Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])` — paid invoices excluded.
- Aging cutoffs keyed off `due_date`, not invoice date (`payroll.py:1624-1628`).
- ZAR conversion via `_to_zar()` applied consistently, including per-item display amounts.

## 4. Creditors

✓ No issues found.
- Reversal-awareness (2026-07-13 fixes) confirmed present at all four call sites — every site nets `source IN ("purchase_order", "purchase_order_reversal")`.
- AP control (Rule 7, `payroll.py:1753-1790`) computes per-PO expected credit from `credit − debit` journal lines, falling back to `po.total_amount` only when no journal entry exists yet.
- Supplier bank details decrypted via `decrypt_field` (`suppliers.py:7,48-50`) — unchanged.

## 5. Cross-module consistency

✓ No issues found.
- Journal coverage complete: `post_invoice_raised`, `post_invoice_paid`, `post_invoice_cogs`, `post_expense`, `post_payroll`, `post_expense_paid`, `post_po_received`, `post_po_paid` — no gaps.
- Import-awareness (2026-07-11 fixes) intact: Rules 6/7 exclude `source == "import"` on 1100/2000 (`payroll.py:1736,1812`); balance sheet retains imported equity offsets 3998/3999. Non-ZAR invoice imports still require an exchange rate; unbalanced journal-import groups still rejected; both invoice and journal imports auto-run the backfill.
- Migration hygiene re-verified: `wear_and_tear_rate` column and `ALTER TABLE` still positioned inside the migrations list literal. The new `BankInterestRequest` table (added this run) is a fresh `Base` model, not an `ALTER TABLE` migration, so it doesn't touch this hygiene concern.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (declared in AFS meta). Statements: income statement, statement of financial position, changes in equity, cash flow (indirect), notes 2-9.

**Standards status (fresh web search this run):**
- **IFRS 18** *Presentation and Disclosure in Financial Statements* — still effective for annual periods beginning on/after 1 January 2027, not applicable to IFRS-for-SMEs preparers (ZuZan's basis). No change.
- **IFRS for SMEs third edition** (issued 27 February 2025, effective 1 January 2027, early adoption permitted) — this run's search surfaced the June 2026 IFRS.org update plus IASB Q1/Q3 2026 educational-resource rollout and a narrow-scope standard-setting item on paragraph 9.3 (an application question the IASB agreed needs a fix before the effective date). No changes to the substantive Section 23 revenue/Section 12 fair value/financial-instruments text used by the existing transition plan. `ifrs_smes_3rd_edition_transition_plan.md` remains current.
- VAT rate: confirmed 15% standard rate — the previously-flagged 2025 legislation for a phased rise to 16% by April 2026 was reversed by 2025 court order/legislative rollback and did not take effect. Corporate income tax: 27% flat rate, unchanged for years of assessment ending 1 Apr 2026 – 31 Mar 2027.

**Section 5b — deferred tax: already implemented, re-verified this run:**
- Grepped `financial_statements.py` for `"deferred_tax": 0.0` — no matches.
- Per-asset tax base = cost − cumulative SARS wear-and-tear allowance; temporary difference × `_CIT_RATE` (27%) drives the deferred tax balance (`:131,172`).
- Opening/closing balances drive `deferred_tax_expense` = closing − opening; Note 9 fields populated; `total_tax = tax_expense + deferred_tax_expense`; balance-sheet movement line present.
- Finance costs (2026-07-13 fix): interest presented below EBIT, tax/net profit derive from `profit_before_tax` — unchanged.

✓ No issues found.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date.

- No rate changes found since the 08-08 audit.
- **2026 draft TLAB / TALAB:** published 30 July 2026, still in public comment (closes 28 August 2026, per fresh search of Treasury/SARS/GoLegal/IOL/Accounting Weekly/Nexia/gov.za/SAIT sources) — **not yet enacted**. Draft proposals (living annuity de minimis, non-resident spouse donations-tax exemption, SEZ transfer pricing, leasehold improvements, carbon budget refunds) don't touch any rate currently hard-coded in ZuZan. No code impact.
- VAT confirmed 15% (2025 planned 16% escalation was legislatively reversed) — matches `VAT_RATE = 0.15` in code.
- CIT confirmed flat 27% for standard companies; SBC tiered rates (21%/27% bands, threshold up to R550,000) apply only to registered Small Business Corporations — ZuZan does not implement SBC-specific tiering, consistent with prior audits (not flagged as a defect; no evidence ZuZan's client base requires SBC treatment).
- VAT registration threshold increases (compulsory R1m→R2.3m, voluntary R50k→R120k, effective 1 April 2026) noted — these are registration thresholds, not rates, and don't affect any VAT calculation logic in the app.
- s11F retirement fund deduction cap R430,000 (`payroll.py:196`), rate 27.5% — unchanged.
- Medical tax credits (Section 6A): R376/month main + first dependant, R254/month additional — unchanged.
- UIF: 1% employee / 1% employer, ceiling gives max R177.12/month per party — unchanged.
- SDL 1% of gross remuneration, R500,000 annual-payroll small-employer exemption — unchanged.
- Provisional `2027/2028` `TAX_YEARS` entry remains a placeholder copy of 2026/2027 pending the Feb 2027 Budget — standing reminder, not a defect.
- EMP201 monthly deadline reconfirmed as the 7th of the following month (moved to the prior business day if the 7th falls on a weekend/public holiday) — no change to the app's due-date logic needed.
- Rates unchanged and current tax year present — no edits made (report-only per task rules; section 5b already implemented, verification-only this run).

**Sources consulted:** [Tax Practice Weekly Update — SAIT](https://thesait.org.za/tax-practice-weekly-update-issue-37-4-2-3-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-3-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2/) · [National Treasury Publishes 2026 Draft Tax Bills — Tax Consulting SA](https://www.taxconsulting.co.za/national-treasury-publishes-2026-draft-tax-bills-for-public-comment/) · [Big tax changes proposed — IOL](https://iol.co.za/business/2026-08-06-big-tax-changes-proposed-what-the-new-draft-bills-mean-for-taxpayers/) · [2026 Draft Tax Bills — GoLegal](https://www.golegal.co.za/2026-draft-tax-bills/) · [South Africa consults on 2026 draft tax legislation — RegFollower](https://regfollower.com/south-africa-consults-on-2026-draft-tax-legislation/) · [Treasury publishes 2026 draft tax bills — Nexia SAB&T](https://www.nexia-sabt.co.za/treasury-publishes-2026-draft-tax-bills-for-public-comment/) · [The 2026 Draft Tax Bills Are Out — Accounting Weekly](https://www.accountingweekly.com/sars-updates/2026-draft-tlab-and-talab-what-accountants-must-know) · [National Treasury media statement — gov.za](https://www.gov.za/news/media-statements/national-treasury-publication-2026-draft-tax-bills-comment-30-jul-2026) · [June 2026 IFRS for SMEs Accounting Standard Update — IFRS.org](https://www.ifrs.org/supporting-implementation/2015-ifrs-for-smes-supporting-materials/sme-updates/2026/june-2026-ifrs-for-smes-accounting-standard-update/) · [IASB issues third edition of IFRS for SMEs — EY](https://www.ey.com/en_gl/technical/ifrs-technical-resources/iasb-issues-third-edition-of-ifrs-for-smes-accounting-standard) · [South African VAT rate increase reversal — EY](https://www.ey.com/en_gl/technical/tax-alerts/south-african-vat-rate-set-to-increase-by-05-percent-from-1-may-2025-and-another-05-percent-from-1-april-2026) · [VAT in 2026: Navigating Stability — SAIT](https://thesait.org.za/vat-in-2026-navigating-stability-and-the-legacy-of-the-2025-reversals/) · [South Africa 2026 Budget ducks VAT rise — vatcalc.com](https://www.vatcalc.com/south-africa/south-africa-vat-rise/) · [Company Income Tax Calculator & Corporate Tax Rate 2026 Guide — Tax Planners](https://taxplanners.co.za/company-income-tax-calculator-south-africa/) · [Pay As You Earn — SARS](https://www.sars.gov.za/types-of-tax/pay-as-you-earn/)

## 8. Action items

1. **[Medium, escalated]** Solutha (company id 3) still has **no payroll runs recorded for June, July, or August 2026** — queried the `payslips` table directly this run (joined via `employees.company_id=3`): the most recent period is still `2026-05`. Two EMP201 deadlines have now definitively passed (7 July and 7 August 2026) with a third (7 September, for August payroll) approaching. This is outside the Reports/Debtors/Creditors/AFS/tax code-correctness scope of this audit (it's a data/operations gap, not a bug), but it continues to be a compliance risk worth surfacing to the user directly — this is now the third consecutive report flagging it.

**Standing reminders (not defects, carried from prior reports):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry (`payroll.py:151+`) after Budget Feb 2027 and restart the backend;
(b) early-2027 runs should execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`);
(c) the AFS PayFast payment/ad-hoc tokenization feature and the `/reports/ai-insights` feature remain outside this audit's scope;
(d) NBCPSS private security payroll mode predates this audit's baseline, not yet part of this checklist's explicit scope;
(e) file-attribution note: the imported-equity-offset (3998/3999) exclusion logic lives in `payroll.py`'s `balance_sheet()`, not `financial_statements.py`;
(f) the s20A loss-ring-fencing threshold change is not applicable to any code ZuZan implements — awareness only;
(g) track the 2026 draft TLAB/TALAB (comment period closes 28 August 2026) — once enacted, re-check whether any finalized provisions require rate/table changes;
(h) `App_js_fixed.js` `BankFeedPanel`'s "Coming Soon" state (now with a "Notify me" button, new this run) and the new `/admin/api/bank-interest` admin endpoint remain uncommitted and out of scope, flagged for awareness only;
(i) IASB paragraph 9.3 narrow-scope standard-setting item (IFRS for SMEs 3rd edition) noted this run for awareness — not yet resolved by the IASB, no action needed until finalized.
