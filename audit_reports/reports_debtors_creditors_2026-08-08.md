# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 8 August 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-08-07 (full PASS, no open action items).

**Change detection since last run:** `git log` shows no new commits since `b277cdc` (2026-08-05 22:01), already covered by both the 08-06 and 08-07 reports. Working tree `git status` again shows `App_js_fixed.js`, `auth.py`, `billing.py`, `companies.py`, `main.py`, `payroll.py` modified-but-uncommitted — identical file set to yesterday.

- `git diff -w` on `companies.py`, `main.py`, `payroll.py` — **empty** (whitespace/line-ending noise only), consistent with every run since 07-26.
- `git diff -w` on `auth.py`, `billing.py` — **empty** under whitespace-ignored diff, confirming (again) those are line-ending churn only, out of scope regardless.
- `App_js_fixed.js` diff is **byte-identical** to the one flagged in the 08-07 report: `BankFeedPanel` (line 6629) branches on `status?.configured` for a "Coming Soon" state on unconfigured banks. Still Pillar 3 (Bank Integration) UI, still out of scope for Reports/Debtors/Creditors/AFS/tax.

**No functional changes to the audited surface area since 08-07.** Re-verified the highest-risk anchors directly via Grep this run:
- `grep '"deferred_tax": 0.0'` on `financial_statements.py` → no matches (hard-coded zero still absent).
- `wear_and_tear_rate` column (`database.py:483`) and its `ALTER TABLE` (`database.py:1363`) confirmed still inside the migrations list literal, not after the loop.
- `purchase_order_reversal` present at all four expected reversal-aware call sites (`financial_statements.py:558`, `journal.py:848`, `payroll.py:1778,2534`, `purchase_orders.py:445`).
- `decrypt_field` present in `suppliers.py:7,48-50`.
- `_CIT_RATE` sourced from `fixed_assets.SA_CIT_RATE` with fallback 0.27 (`financial_statements.py:78-84`), used consistently in deferred-tax calc (`:172`), current tax expense (`:260`), and Note 9 (`:604,641`).
- Journal coverage functions all present in `journal.py`: `post_invoice_raised` (:194), `post_invoice_paid` (:234), `post_invoice_cogs` (:268), `post_expense` (:293), `post_payroll` (:368), `post_expense_paid` (:447), `post_po_received` (:476), `post_po_paid` (:528).
- Import-awareness: `source == "import"` exclusions at `payroll.py:1736,1812` confirmed present.
- `payroll.py` `TAX_YEARS["2026/2027"]` (:131), `"2027/2028"` placeholder (:151), `S11F_CAP = 430_000` (:196), `VAT_RATE = 0.15` (:1608, :2691) confirmed unchanged.

Fresh web search this run confirms no new SARS or IFRS developments affecting the current tax year/standards (see §7 for details).

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ✅ PASS — logic unchanged, re-verified |
| Debtors (AR) | ✅ PASS — aged from due_date, paid excluded, ZAR amounts |
| Creditors (AP) | ✅ PASS — reversal-aware, bank details decrypted |
| Cross-module consistency | ✅ PASS — full journal coverage, import-awareness intact, migration hygiene intact |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) verified again, no regressions |
| Tax rates (SARS) | ✅ PASS — 2026/2027 tables current, no rate changes since 08-07 |

**Overall: PASS.** No functional code changes to the audited surface since the last audit. One standing item has escalated in severity (see §8, item 1) — Solutha (company 3) still has not run payroll for June, July, or now August 2026.

---

## 2. Reports

✓ No issues found.
- Dashboard (`payroll.py:1225-1270`): `total_revenue` sums only paid invoices via `_to_zar()` plus `_bank_import_income()`; `total_outstanding` sums `sent`/`overdue` invoices via `_to_zar()`. Expenses summed ex-VAT, separate from revenue.
- PO COGS uses delivered-value-only for partials (`_po_delivered_net`), no double-counting with payroll or depreciation.
- Payroll costs included in expenses via the payslip sum, applied after gross profit.
- Management accounts (`payroll.py:2078-2153`) and `/v1/summary` (`main.py:445-490`) both route revenue/outstanding through `_to_zar()` and mirror the dashboard formula.

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
- Migration hygiene re-verified: `wear_and_tear_rate` column and `ALTER TABLE` still positioned inside the migrations list literal.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (declared in AFS meta). Statements: income statement, statement of financial position, changes in equity, cash flow (indirect), notes 2-9.

**Standards status (fresh web search this run):**
- **IFRS 18** *Presentation and Disclosure in Financial Statements* — still effective for annual periods beginning on/after 1 January 2027, not applicable to IFRS-for-SMEs preparers (ZuZan's basis). No change.
- **IFRS for SMEs third edition** (issued 27 February 2025, effective 1 January 2027, early adoption permitted) — search this run surfaced only recap/summary articles (Section 23 revenue realignment with IFRS 15, new Section 12 Fair Value Measurement, merged financial-instruments sections); no new IASB standard-text changes found. Existing transition plan (`ifrs_smes_3rd_edition_transition_plan.md`) remains current.
- VAT rate: 15% standard rate, unchanged. Corporate income tax: 27%, unchanged for years of assessment ending 1 Apr 2026 – 31 Mar 2027.

**Section 5b — deferred tax: already implemented, re-verified this run:**
- Grepped `financial_statements.py` for `"deferred_tax": 0.0` — no matches.
- Per-asset tax base = cost − cumulative SARS wear-and-tear allowance; temporary difference × `_CIT_RATE` (27%) drives the deferred tax balance (`:131,172`).
- Opening/closing balances drive `deferred_tax_expense` = closing − opening; Note 9 fields populated; `total_tax = tax_expense + deferred_tax_expense`; balance-sheet movement line present.
- Finance costs (2026-07-13 fix): interest presented below EBIT, tax/net profit derive from `profit_before_tax` — unchanged.

✓ No issues found.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date.

- No rate changes found since the 08-07 audit.
- **2026 draft TLAB / TALAB:** still in public comment (closes 28 August 2026, per fresh search of Treasury/SARS/GoLegal/IOL/Accounting Weekly sources) — **not yet enacted**. Draft proposals (living annuity de minimis, non-resident spouse donations-tax exemption, SEZ transfer pricing, leasehold improvements, carbon budget refunds) don't touch any rate currently hard-coded in ZuZan. No code impact.
- s11F retirement fund deduction cap R430,000 (`payroll.py:196`), rate 27.5% — unchanged.
- Medical tax credits (Section 6A): R376/month main + first dependant, R254/month additional — unchanged.
- UIF: 1% employee / 1% employer, ceiling gives max R177.12/month per party — unchanged.
- SDL 1% of gross remuneration, R500,000 annual-payroll small-employer exemption — unchanged.
- VAT 15%, CIT 27% — unchanged.
- Provisional `2027/2028` `TAX_YEARS` entry remains a placeholder copy of 2026/2027 pending the Feb 2027 Budget — standing reminder, not a defect.
- **EMP201 monthly deadline** reconfirmed as the 7th of the following month (moved to the prior business day if the 7th falls on a weekend/public holiday) — no change to the app's due-date logic needed.
- Rates unchanged and current tax year present — no edits made (report-only per task rules; section 5b already implemented, verification-only this run).

**Sources consulted:** [National Treasury Publishes 2026 Draft Tax Bills — Tax Consulting SA](https://www.taxconsulting.co.za/national-treasury-publishes-2026-draft-tax-bills-for-public-comment/) · [South Africa consults on 2026 draft tax legislation — RegFollower](https://regfollower.com/south-africa-consults-on-2026-draft-tax-legislation/) · [2026 Draft Tax Bills — GoLegal](https://www.golegal.co.za/2026-draft-tax-bills/) · [Big tax changes proposed — IOL](https://iol.co.za/business/2026-08-06-big-tax-changes-proposed-what-the-new-draft-bills-mean-for-taxpayers/) · [The 2026 Draft Tax Bills Are Out — Accounting Weekly](https://www.accountingweekly.com/sars-updates/2026-draft-tlab-and-talab-what-accountants-must-know) · [Treasury publishes 2026 draft tax bills — Nexia SAB&T](https://www.nexia-sabt.co.za/treasury-publishes-2026-draft-tax-bills-for-public-comment/) · [National Treasury media statement — gov.za](https://www.gov.za/news/media-statements/national-treasury-publication-2026-draft-tax-bills-comment-30-jul-2026) · [March 2026 IFRS for SMEs Accounting Standard Update — IFRS.org](https://www.ifrs.org/supporting-implementation/2015-ifrs-for-smes-supporting-materials/sme-updates/2026/march-2026-ifrs-for-smes-accounting-standard-update/) · [IASB issues third edition of IFRS for SMEs — EY](https://www.ey.com/en_gl/technical/ifrs-technical-resources/iasb-issues-third-edition-of-ifrs-for-smes-accounting-standard) · [Third edition of the IFRS for SMEs Accounting Standard — ACCA](https://www.accaglobal.com/learning-and-events/corporate-reporting/third-edition-ifrs-for-smes.html) · [SARS 2026 Tax Filing Dates & Deadlines — Accounter](https://accounter.co.za/guides/sars-tax-deadlines-south-africa) · [Pay As You Earn — SARS](https://www.sars.gov.za/types-of-tax/pay-as-you-earn/)

## 8. Action items

1. **[Medium, escalated]** Solutha (company id 3) still has **no payroll runs recorded for June, July, or August 2026** — the `payslips` table (joined via `employees.company_id=3`) shows the most recent period as `2026-05`. This means at least two EMP201 deadlines have now been missed (7 July and 7 August 2026), with a third (7 September, for August payroll) approaching. This was first flagged as a follow-up in the 08-07 report on the strength of `emp201_2026-07.md`; it is now confirmed directly against the payslips table. This is outside the Reports/Debtors/Creditors/AFS/tax code-correctness scope of this audit (it's a data/operations gap, not a bug), but it is a compliance risk worth surfacing to the user directly.

**Standing reminders (not defects, carried from prior reports):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry (`payroll.py:151+`) after Budget Feb 2027 and restart the backend;
(b) early-2027 runs should execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`);
(c) the AFS PayFast payment/ad-hoc tokenization feature and the `/reports/ai-insights` feature remain outside this audit's scope;
(d) NBCPSS private security payroll mode predates this audit's baseline, not yet part of this checklist's explicit scope;
(e) file-attribution note: the imported-equity-offset (3998/3999) exclusion logic lives in `payroll.py`'s `balance_sheet()`, not `financial_statements.py`;
(f) the s20A loss-ring-fencing threshold change is not applicable to any code ZuZan implements — awareness only;
(g) track the 2026 draft TLAB/TALAB (comment period closes 28 August 2026) — once enacted, re-check whether any finalized provisions require rate/table changes;
(h) `App_js_fixed.js` `BankFeedPanel`'s `status?.configured` "Coming Soon" branch remains uncommitted and out of scope, flagged for awareness only.
