# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 25 August 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-08-24 (full PASS).

**Change detection since last run:** `git log -8` shows HEAD now at `c132a93` (24 Aug, 20:57) — three new commits landed *after* the 08-24 audit was written (`8426631`, `8999604`, `c132a93`, all same day, titled "accountant fee structure — R20/client discount... SimplePay payroll parity; bookkeeper onboarding; profile edit"). `git diff 0b53049..c132a93 -w` for the audited backend files shows the only substantive change is a cosmetic comment-duplication in `main.py` (already flagged as item (i) in the prior report — the `_SubscriptionGateMiddleware` disabled-comment line got a few more `#` characters appended); `billing.py` gained 3 lines outside audit scope; the rest of the diff is new files being added under `audit_reports/` itself. `payroll.py`, `companies.py`, `database.py`, `financial_statements.py`, `journal.py`, `purchase_orders.py`, `suppliers.py`, `customers.py`, `csv_import.py` show **zero diff** between the two commits. Working tree shows the same recurring `auth.py`/`billing.py`/`companies.py`/`main.py`/`payroll.py` "modified" flags, confirmed CRLF-only (`git diff -w` → 0 lines) — the known deploy-pipeline artifact, unchanged.

Re-verified all high-risk anchors directly via Grep this run — all unchanged from 08-24:
- `"deferred_tax": 0.0` search on `financial_statements.py` → no matches (deferred tax remains fully computed, not hard-coded).
- `wear_and_tear_rate` column (`database.py:485`) and its `ALTER TABLE` (`database.py:1399`) confirmed still inside the migrations list literal.
- `purchase_order_reversal` present at all expected reversal-aware call sites: `payroll.py:1770,1778,2527,2534`, `financial_statements.py:542,558`, `journal.py:848`, `purchase_orders.py:438,445`.
- `decrypt_field` present in `suppliers.py:7,48-50`.
- Import-awareness: `source == "import"` exclusions at `payroll.py:1736,1812` confirmed present.
- `payroll.py`: `TAX_YEARS` dict (:100), `CURRENT_TAX_YEAR` (:182), `S11F_CAP = 430_000` (:196), `VAT_RATE = 0.15` (:1608, :2691) confirmed unchanged.
- Dashboard revenue/outstanding formula (`payroll.py:1233-1246`), `main.py` `/v1/summary` `_to_zar()` usage (:449-483), and full `journal.py` post_* coverage (12 functions, `post_invoice_raised` through `post_asset_disposal`) all re-verified present and unchanged.

Fresh web search this run (SARS TLAB/TALAB, IFRS 18 / IFRS for SMEs, VAT/UIF/SDL/CIT) confirms no material change since 08-24 — see §6 and §7.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ✅ PASS — logic unchanged, re-verified |
| Debtors (AR) | ✅ PASS — aged from due_date, paid excluded, ZAR amounts |
| Creditors (AP) | ✅ PASS — reversal-aware, bank details decrypted |
| Cross-module consistency | ✅ PASS — full journal coverage, import-awareness intact, migration hygiene intact |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) verified again, no regressions |
| Tax rates (SARS) | ✅ PASS — 2026/2027 tables current, no rate changes |

**Overall: PASS.** Three commits landed since the 08-24 audit (bookkeeper onboarding / accountant fee structure feature work) but none touch Reports/Debtors/Creditors/AFS/tax logic — the only in-scope-file change is a cosmetic comment-duplication artifact in `main.py`. No open action items.

---

## 2. Reports

✓ No issues found.
- Dashboard (`payroll.py` `total_revenue`/`total_outstanding`): revenue sums only paid invoices via `_to_zar()` (`payroll.py:1233-1237`, plus bank-import income added separately at :1239); outstanding sums `sent`/`overdue` invoices via `_to_zar()` (`payroll.py:1241-1245`). Expenses summed ex-VAT, kept separate from revenue.
- PO costs feed expenses/COGS via delivered-value-only for partials, no double-counting with payroll or depreciation.
- Payroll costs included in expenses via the payslip sum, applied after gross profit.
- Management accounts revenue trend loop and `/v1/summary` (`main.py:449-483`) both route revenue/outstanding through `_to_zar()` and mirror the dashboard formula.

## 3. Debtors

✓ No issues found.
- Invoice status filter confirmed: `Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])` — paid invoices excluded from all outstanding-balance calculations (`payroll.py:1243,1627,1723,2151,2446`).
- Aging cutoffs keyed off `due_date`, not invoice date (`payroll.py:1630` uses `overdue_90` bucketed by due date).
- ZAR conversion via `_to_zar()` applied consistently, including per-item display amounts (`payroll.py:1642`).

## 4. Creditors

✓ No issues found.
- Reversal-awareness (2026-07-13 fixes) confirmed present at all call sites — every site nets `source IN ("purchase_order", "purchase_order_reversal")`, including `purchase_orders.py:445`.
- AP control (payroll.py Rule 7) computes per-PO expected credit from `credit − debit` journal lines, falling back to `po.total_amount` only when no journal entry exists yet.
- Supplier bank details decrypted via `decrypt_field` (`suppliers.py:7,48-50`) — unchanged.

## 5. Cross-module consistency

✓ No issues found.
- Journal coverage complete: `post_invoice_raised`, `post_invoice_paid`, `post_invoice_cogs`, `post_expense`, `post_bank_income`, `post_payroll`, `post_expense_paid`, `post_po_received`, `post_po_paid`, `post_stock_adjustment`, `post_asset_acquisition`, `post_depreciation`, `post_asset_disposal` — no gaps (`journal.py`).
- Import-awareness (2026-07-11 fixes) intact: Rules 6/7 exclude `source == "import"` on 1100/2000 (`payroll.py:1736,1812`); balance sheet retains imported equity offsets 3998/3999. Non-ZAR invoice imports still require an exchange rate; unbalanced journal-import groups still rejected; both invoice and journal imports auto-run the backfill.
- Migration hygiene re-verified: `wear_and_tear_rate` column and `ALTER TABLE` still positioned inside the migrations list literal — the three new commits this run touched billing/onboarding/fee-structure code, not the migrations list.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (declared in AFS meta). Statements: income statement, statement of financial position, changes in equity, cash flow (indirect), notes 2-9.

**Standards status (fresh web search this run):**
- **IFRS 18** *Presentation and Disclosure in Financial Statements* — confirmed effective for annual periods beginning on/after 1 January 2027, not applicable to IFRS-for-SMEs preparers (ZuZan's basis). No change found this run.
- **IFRS for SMEs third edition** (issued February 2025, effective 1 January 2027, early adoption permitted) — reconfirmed: entities may early-adopt or continue applying the 2015 edition until the effective date; retrospective application applies under Section 10, with some transition reliefs. Major changes: business combinations, financial instruments, consolidated financial statements, revenue Section 23 rewritten to the IFRS 15 five-step model, 2018 Conceptual Framework alignment. Nothing new that alters ZuZan's Jan–Feb 2027 implementation checklist (`ifrs_smes_3rd_edition_transition_plan.md`).
- VAT rate: reconfirmed 15% standard rate (2025 proposed increases to 15.5%/16% were reversed; Budget 2026 held the rate at 15%). Corporate income tax: 27% flat rate for years of assessment ending 1 April 2026 – 31 March 2027, unchanged.

**Section 5b — deferred tax: already implemented, re-verified this run:**
- Grepped `financial_statements.py` for `"deferred_tax": 0.0` — no matches.
- Per-asset tax base = cost − cumulative SARS wear-and-tear allowance; temporary difference × CIT rate (27%) drives the deferred tax balance. Opening/closing balances drive `deferred_tax_expense` = closing − opening; Note 9 fields populated; `total_tax = tax_expense + deferred_tax_expense`; balance-sheet movement line present.
- Finance costs (2026-07-13 fix): interest presented below EBIT, `profit_before_tax` drives tax/net profit — unchanged, no regression from this run's commits.

✓ No issues found.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date.

- Fresh web search this run: the **2026 draft TLAB/TALAB** remains in public comment (published 30 July 2026, comment period closes 28 August 2026 — now **3 days away**). Content unchanged from prior runs: TLAB proposals include limiting the multiple-living-annuity de minimis application and restricting the donations tax spousal exemption to SA-resident spouses plus applying arm's-length principle to Special Economic Zones; TALAB proposals cover Temporary Admission carnets, second-hand goods documentation, refund pre/post-deposit screening, and voluntary-disclosure interest relief. None of these are enacted PAYE bracket, rebate, UIF, SDL, CIT, or VAT-rate changes — no code change warranted. Treasury/SARS will review submissions post-comment-period before introducing the bills in Parliament.
- PAYE brackets, rebates, UIF ceiling and percentages, SDL rate, and s11F cap (`payroll.py:100-196`) — unchanged from the 08-24 verification, re-read in full this run (2026/2027: brackets up to 45% above R1,878,601, primary rebate R17,820, secondary R9,765, tertiary R3,249, UIF ceiling R17,712; S11F cap R430,000 effective 1 March 2026).
- UIF reconfirmed 1%/1% (R17,712 monthly ceiling, R177.12/side max contribution) and SDL reconfirmed 1% of payroll (employer-only, exempt for employers with annual payroll < R500,000) — both match code (`UIF_RATE = 0.01`, `SDL_RATE = 0.01`, `payroll.py:187-188`).
- VAT confirmed 15% — matches `VAT_RATE = 0.15` in code (`payroll.py:1608, 2691`). 2025 proposed rate increases (15.5%/16%) remain reversed; no change signalled for the current tax year.
- CIT confirmed flat 27% — matches usage in dashboard/management/provisional-tax and `financial_statements.py`.
- Note (not a defect): fresh search flagged the compulsory VAT-registration turnover threshold rising to R2,300,000 (from R1,000,000) effective 1 April 2026, and the voluntary-registration threshold rising to R120,000 (from R50,000). ZuZan does not appear to gate VAT registration/vendor-status logic on a turnover threshold in the audited files — flagged for awareness only, not an in-scope AR/AP/Reports/AFS defect.
- Provisional `2027/2028` `TAX_YEARS` entry (`payroll.py`) remains a placeholder copy of 2026/2027 pending the Feb 2027 Budget — standing reminder, not a defect.
- Rates unchanged and current tax year present — no edits made (report-only per task rules; section 5b already implemented, verification-only this run).

**Sources consulted:** [National Treasury Publishes 2026 Draft Tax Bills for Public Comment — Tax Consulting SA](https://www.taxconsulting.co.za/national-treasury-publishes-2026-draft-tax-bills-for-public-comment/) · [New tax laws for medical aid credits, companies, and spousal donations in South Africa — BusinessTech](https://businesstech.co.za/news/government/868257/new-tax-laws-for-medical-aid-credits-companies-and-spousal-donations-in-south-africa/) · [2026 Draft Tax Bills have been published for comment — GoLegal](https://www.golegal.co.za/2026-draft-tax-bills/) · [Big tax changes proposed: What the new draft bills mean for taxpayers — IOL](https://iol.co.za/business/2026-08-06-big-tax-changes-proposed-what-the-new-draft-bills-mean-for-taxpayers/) · [Draft tax law changes could affect donations, VAT, medical tax credits and SARS refunds — IOL](https://iol.co.za/business/advice/2026-08-08-draft-tax-law-changes-could-affect-donations-vat-medical-tax-credits-and-sars-refunds/) · [South Africa consults on 2026 draft tax legislation — RegFollower](https://regfollower.com/south-africa-consults-on-2026-draft-tax-legislation/) · [2026 draft TLAB: Key changes for businesses — PvdZ Consulting](https://tax.pvdz.co.za/tlab/) · [National Treasury on publication of the 2026 draft tax bills for comment — gov.za](https://www.gov.za/news/media-statements/national-treasury-publication-2026-draft-tax-bills-comment-30-jul-2026) · [The 2026 Draft Tax Bills Are Out. Comment Closes 28 August — Accounting Weekly](https://www.accountingweekly.com/sars-updates/2026-draft-tlab-and-talab-what-accountants-must-know) · [IFRS - 2025 IFRS for SMEs supporting materials](https://www.ifrs.org/supporting-implementation/2025-ifrs-for-smes-supporting-materials/) · [Third edition of the IFRS for SMEs Accounting Standard — ACCA](https://www.accaglobal.com/learning-and-events/corporate-reporting/third-edition-ifrs-for-smes.html) · [IASB issues third edition of the IFRS for SMEs — PwC Viewpoint](https://viewpoint.pwc.com/dt/gx/en/pwc/in_briefs/in_briefs_INT/in_briefs_INT/iasb-issues.html) · [Budget 2026 Frequently Asked Questions — SARS](https://www.sars.gov.za/about/sars-tax-and-customs-system/budget/budget-2026-frequently-asked-questions/) · [SARS Tax Tables 2026/2027 — Accounter](https://accounter.co.za/news/sars-tax-tables-2026-2027) · [South Africa Suspends VAT Rate Increase — Marosa](https://marosavat.com/vat-news/south-africa-vat-rate-increase-suspended) · [VAT in 2026: Navigating Stability — SAIT](https://thesait.org.za/vat-in-2026-navigating-stability-and-the-legacy-of-the-2025-reversals/) · [VAT Rate in South Africa 2026 — Current 15% Rate Explained](https://vatcalculator.co.za/vat-rate-south-africa/)

## 8. Action items

None. No open action items.

**Standing reminders (not defects, carried from prior reports):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry (`payroll.py`) after Budget Feb 2027 and restart the backend;
(b) early-2027 runs should execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`);
(c) the AFS PayFast payment/ad-hoc tokenization feature and the `/reports/ai-insights` feature remain outside this audit's scope;
(d) NBCPSS private security payroll mode predates this audit's baseline, not yet part of this checklist's explicit scope;
(e) file-attribution note: the imported-equity-offset (3998/3999) exclusion logic lives in `payroll.py`'s `balance_sheet()`, not `financial_statements.py`;
(f) track the **2026 draft TLAB/TALAB** (comment period closes 28 August 2026, now 3 days away) — once enacted, re-check whether any finalized provisions require rate/table changes in `payroll.py` or `financial_statements.py`;
(g) `parent_company_id`/`user_type` columns and the bookkeeper-onboarding/consolidated-billing/add-client/accountant-fee-structure features (latest commits `8426631`/`8999604`/`c132a93`, 24 Aug) remain outside Reports/Debtors/Creditors/AFS/tax scope, flagged for awareness only;
(h) payroll subscription pricing (`max(65, employees×18.25)`, `payroll.py`) — billing/pricing only, not a SARS rate, no action needed for this checklist; legacy unused constants `PAYROLL_PER_EMP = 34.00` / `PAYROLL_MIN = 99.00` remain defined in `payroll.py`, still worth a future cleanup pass to confirm they're dead code, not a compliance issue;
(i) `main.py`'s `_SubscriptionGateMiddleware` disabled-comment duplication grew again this run (three more commits appended more `#`/repeated-comment text at the same line) — cosmetic and out of this audit's scope, but the recurrence across multiple commits continues to suggest an unreviewed auto-generation step in the commit pipeline worth a maintainer look;
(j) new: compulsory VAT-registration turnover threshold rises to R2,300,000 (from R1,000,000) and voluntary threshold to R120,000 (from R50,000), effective 1 April 2026 — ZuZan doesn't appear to gate any in-scope logic on this threshold, flagged for awareness only.
