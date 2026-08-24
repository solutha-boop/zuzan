# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 21 August 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-08-20 (full PASS).

**Change detection since last run:** `git log -8` shows HEAD still at `0b53049` (22:31, 08-13) — **no new commits** (unchanged for the ninth consecutive day). `git status` shows the same recurring working-tree "modified" flags on `auth.py`, `billing.py`, `companies.py`, `main.py`, `payroll.py`, but `git diff --stat -w` (ignoring whitespace) is **empty** — the known CRLF-only-diff artifact of the deploy pipeline, unchanged since prior audits. No logic changes anywhere in the codebase since the 08-20 audit.

Re-verified all high-risk anchors directly via Grep this run — all unchanged from 08-20:
- `"deferred_tax": 0.0"` search on `financial_statements.py` → no matches (deferred tax remains fully computed, not hard-coded).
- `wear_and_tear_rate` column (`database.py:485`) and its `ALTER TABLE` (`database.py:1399`) confirmed still inside the migrations list literal.
- `purchase_order_reversal` present at all expected reversal-aware call sites: `payroll.py:1770,1778,2527,2534`, `financial_statements.py:542,558`, `journal.py:848`, `purchase_orders.py:438,445`.
- `decrypt_field` present in `suppliers.py:7,48-50`.
- Journal coverage functions all present in `journal.py`: `post_invoice_raised` (:194), `post_invoice_paid` (:234), `post_invoice_cogs` (:268), `post_expense` (:293), `post_payroll` (:368), `post_expense_paid` (:447), `post_po_received` (:476), `post_po_paid` (:528).
- Import-awareness: `source == "import"` exclusions at `payroll.py:1736,1812` confirmed present.
- `payroll.py`: `TAX_YEARS` dict (:100), `CURRENT_TAX_YEAR` (:182), `S11F_CAP = 430_000` (:196), `VAT_RATE = 0.15` (:1608, :2691) confirmed unchanged.
- Debtors filter (`Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])`) confirmed at all outstanding-balance sites (`payroll.py:1243,1627,1723,2151,2446`); the three sites additionally including `InvoiceStatus.paid` (`payroll.py:1295,1649,2718`) are invoice-listing/export endpoints, not the AR outstanding calc — consistent with prior audits, not a defect.
- `main.py` `/v1/summary` (:453,483) still routes `total_revenue`/`outstanding` through `_to_zar()`.
- Finance costs (`financial_statements.py:205-211`) still isolated below EBIT via account 6700 / name match; `profit_before_tax` (:259) drives `tax_expense`/`net_profit` (:260-261), not EBIT.

Fresh web search this run (SARS TLAB/TALAB, PAYE/UIF/SDL tables, IFRS 18 / IFRS for SMEs) confirms no material change since 08-20 — see §6 and §7.

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

**Overall: PASS.** No code changes landed since the 08-20 audit (no new commits; the perpetual CRLF-only working-tree diff remains a no-op). No open action items.

---

## 2. Reports

✓ No issues found.
- Dashboard (`payroll.py` `total_revenue`/`total_outstanding`): revenue sums only paid invoices via `_to_zar()`; outstanding sums `sent`/`overdue` invoices via `_to_zar()`. Expenses summed ex-VAT, kept separate from revenue.
- PO costs feed expenses/COGS via delivered-value-only for partials (`_po_delivered_net`), no double-counting with payroll or depreciation.
- Payroll costs included in expenses via the payslip sum, applied after gross profit.
- Management accounts and `/v1/summary` (`main.py:453,483`) both route revenue/outstanding through `_to_zar()` and mirror the dashboard formula.

## 3. Debtors

✓ No issues found.
- Invoice status filter confirmed: `Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])` — paid invoices excluded from all outstanding-balance calculations.
- Aging cutoffs keyed off `due_date`, not invoice date.
- ZAR conversion via `_to_zar()` applied consistently, including per-item display amounts.

## 4. Creditors

✓ No issues found.
- Reversal-awareness (2026-07-13 fixes) confirmed present at all call sites — every site nets `source IN ("purchase_order", "purchase_order_reversal")`, including `purchase_orders.py:445`.
- AP control (payroll.py Rule 7) computes per-PO expected credit from `credit − debit` journal lines, falling back to `po.total_amount` only when no journal entry exists yet.
- Supplier bank details decrypted via `decrypt_field` (`suppliers.py:7,48-50`) — unchanged.

## 5. Cross-module consistency

✓ No issues found.
- Journal coverage complete: `post_invoice_raised`, `post_invoice_paid`, `post_invoice_cogs`, `post_expense`, `post_payroll`, `post_expense_paid`, `post_po_received`, `post_po_paid` — no gaps.
- Import-awareness (2026-07-11 fixes) intact: Rules 6/7 exclude `source == "import"` on 1100/2000 (`payroll.py:1736,1812`); balance sheet retains imported equity offsets 3998/3999. Non-ZAR invoice imports still require an exchange rate; unbalanced journal-import groups still rejected; both invoice and journal imports auto-run the backfill.
- Migration hygiene re-verified: `wear_and_tear_rate` column and `ALTER TABLE` still positioned inside the migrations list literal — no schema-adjacent commits landed this run.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (declared in AFS meta). Statements: income statement, statement of financial position, changes in equity, cash flow (indirect), notes 2-9.

**Standards status (fresh web search this run):**
- **IFRS 18** *Presentation and Disclosure in Financial Statements* — still effective for annual periods beginning on/after 1 January 2027, not applicable to IFRS-for-SMEs preparers (ZuZan's basis). No change found this run.
- **IFRS for SMEs third edition** (issued February 2025, effective 1 January 2027, early adoption permitted) — reconfirmed same scope: updated requirements on business combinations, financial instruments, and consolidated financial statements, plus alignment with the 2018 Conceptual Framework. Nothing new that alters ZuZan's Jan–Feb 2027 implementation checklist (`ifrs_smes_3rd_edition_transition_plan.md`).
- VAT rate: reconfirmed 15% standard rate. Corporate income tax: 27% flat rate, unchanged.

**Section 5b — deferred tax: already implemented, re-verified this run:**
- Grepped `financial_statements.py` for `"deferred_tax": 0.0` — no matches.
- Per-asset tax base = cost − cumulative SARS wear-and-tear allowance; temporary difference × CIT rate (27%) drives the deferred tax balance via `_deferred_tax_balance()` (`financial_statements.py:131`). Opening/closing balances drive `deferred_tax_expense` = closing − opening; Note 9 fields populated; `total_tax = tax_expense + deferred_tax_expense`; balance-sheet movement line present.
- Finance costs (2026-07-13 fix): interest presented below EBIT (`financial_statements.py:205-211`), `profit_before_tax` (:259) drives tax/net profit — unchanged.

✓ No issues found.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date.

- Fresh web search this run: the **2026 draft TLAB/TALAB** remains in public comment (published 30 July 2026, comment period closes 28 August 2026 — 7 days away). Content unchanged from prior runs: donations tax exemption limited to SA-resident spouses, living annuity de minimis calculated cumulatively across funds, ATA Carnet provisions, second-hand goods documentation, refund pre/post-deposit screening, voluntary-disclosure interest relief. None of these are PAYE bracket, rebate, UIF, SDL, CIT, or VAT-rate changes — no code change warranted.
- PAYE brackets for 2026/2027 (`payroll.py:100-150`) reconfirmed against fresh search: 18% to R245,100; 26% to R383,100; 31% to R530,200; 36% to R695,800; 39% to R887,000; 41% (note: search phrased the 41% band boundary as R1,878,600) to R1,878,600; 45% above — consistent with the code's existing 7-band structure and prior audits. Primary rebate R17,820, secondary R9,765 (65+), tertiary R3,249 (75+) confirmed unchanged.
- UIF: 1% employee / 1% employer (2% combined), ceiling R17,712/month → max R177.12/month per party — reconfirmed via fresh search, unchanged.
- SDL 1% of gross remuneration, R500,000 annual-payroll small-employer exemption — reconfirmed unchanged.
- s11F retirement fund deduction cap R430,000 (`payroll.py:196`) — unchanged.
- VAT confirmed 15% — matches `VAT_RATE = 0.15` in code (`payroll.py:1608, 2691`).
- CIT confirmed flat 27% — matches usage in dashboard/management/provisional-tax and `financial_statements.py`.
- Provisional `2027/2028` `TAX_YEARS` entry (`payroll.py`) remains a placeholder copy of 2026/2027 pending the Feb 2027 Budget — standing reminder, not a defect.
- Rates unchanged and current tax year present — no edits made (report-only per task rules; section 5b already implemented, verification-only this run).

**Sources consulted:** [National Treasury Publishes 2026 Draft Tax Bills for Public Comment — Tax Consulting SA](https://www.taxconsulting.co.za/national-treasury-publishes-2026-draft-tax-bills-for-public-comment/) · [2026 Draft Tax Bills have been published for comment — GoLegal](https://www.golegal.co.za/2026-draft-tax-bills/) · [South Africa consults on 2026 draft tax legislation — RegFollower](https://regfollower.com/south-africa-consults-on-2026-draft-tax-legislation/) · [Big tax changes proposed: What the new draft bills mean for taxpayers — IOL](https://iol.co.za/business/2026-08-06-big-tax-changes-proposed-what-the-new-draft-bills-mean-for-taxpayers/) · [Tax Practice Weekly Update, Issue 30 — SAIT](https://thesait.org.za/tax-practice-weekly-update-issue-37-4-2-3-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-3-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2/) · [Draft tax law changes could affect donations, VAT, medical tax credits and SARS refunds — IOL](https://iol.co.za/business/advice/2026-08-08-draft-tax-law-changes-could-affect-donations-vat-medical-tax-credits-and-sars-refunds/) · [The 2026 Draft Tax Bills Are Out. Comment Closes 28 August — Accounting Weekly](https://www.accountingweekly.com/sars-updates/2026-draft-tlab-and-talab-what-accountants-must-know) · [2026 draft TLAB: Key changes for businesses — PvdZ Consulting](https://tax.pvdz.co.za/tlab/) · [National Treasury on publication of the 2026 draft tax bills for comment — gov.za](https://www.gov.za/news/media-statements/national-treasury-publication-2026-draft-tax-bills-comment-30-jul-2026) · [SARS Tax Tables 2026/2027 — Income Tax Brackets, Rebates & Thresholds — Accounter](https://accounter.co.za/news/sars-tax-tables-2026-2027) · [SARS Payroll Tax Calculator 2027 (PAYE, UIF, SDL) — TaxTim](https://www.taxtim.com/za/calculators/payroll-tax) · [PAYE Calculator South Africa | Salary, UIF & Net Pay 2026/2027 — Govchain](https://www.govchain.co.za/salary-tax-calculator) · [IFRS for SMEs Accounting Standard Third Edition — IFRS.org](https://www.ifrs.org/issued-standards/ifrs-for-smes/) · [Third edition of the IFRS for SMEs Accounting Standard — ACCA](https://www.accaglobal.com/learning-and-events/corporate-reporting/third-edition-ifrs-for-smes.html) · [IFRS for SMEs — ICAEW](https://www.icaew.com/technical/corporate-reporting/ifrs/ifrs-accounting-standards-tracker/ifrs-for-smes)

## 8. Action items

None. No open action items.

**Standing reminders (not defects, carried from prior reports):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry (`payroll.py`) after Budget Feb 2027 and restart the backend;
(b) early-2027 runs should execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`);
(c) the AFS PayFast payment/ad-hoc tokenization feature and the `/reports/ai-insights` feature remain outside this audit's scope;
(d) NBCPSS private security payroll mode predates this audit's baseline, not yet part of this checklist's explicit scope;
(e) file-attribution note: the imported-equity-offset (3998/3999) exclusion logic lives in `payroll.py`'s `balance_sheet()`, not `financial_statements.py`;
(f) track the **2026 draft TLAB/TALAB** (comment period closes 28 August 2026, now 7 days away) — proposed changes touch donations tax, living annuities, and SARS administrative processes; once enacted, re-check whether any finalized provisions require rate/table changes in `payroll.py` or `financial_statements.py`;
(g) the IASB's May 2026 consolidation-exception exposure draft (comment period closed 9 September 2026) remains not applicable to ZuZan (single-entity AFS only) — awareness only;
(h) `parent_company_id`/`user_type` columns and the bookkeeper-onboarding/consolidated-billing/add-client features remain outside Reports/Debtors/Creditors/AFS/tax scope, flagged for awareness only;
(i) payroll subscription pricing (`max(65, employees×18.25)`, `payroll.py`) — billing/pricing only, not a SARS rate, no action needed for this checklist; legacy unused constants `PAYROLL_PER_EMP = 34.00` / `PAYROLL_MIN = 99.00` remain defined in `payroll.py`, still worth a future cleanup pass to confirm they're dead code, not a compliance issue;
(j) `billing.py`'s redundant `resp = None` line-duplication and `main.py`'s comment-duplication pattern (no new commits this run to re-check) — cosmetic and out of this audit's scope, but flagged for awareness in case the pattern points to an unreviewed auto-generation step in the commit pipeline.
