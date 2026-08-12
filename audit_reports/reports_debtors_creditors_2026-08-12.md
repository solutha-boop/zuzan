# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 12 August 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-08-11 (full PASS).

**Change detection since last run:** `git log` shows one further commit landed after the 08-11 baseline (`35d654c`): `d4c1e9d` (22:24 on 08-11, same "price parity with SimplePay" feat message as the surrounding commits). `git diff 35d654c d4c1e9d --stat -w` touches only two files outside the report itself:
- **`billing.py`** (+1 line, `:458`): adds a fourth redundant `resp = None` line before the PayFast ad-hoc-charge `try` block (joining three that were already there). Pure no-op — `resp` is reassigned inside the `try` regardless. Not in Reports/Debtors/Creditors/AFS/tax scope.
- **`main.py`** (+2/−1): adds more repeated `# disabled — re-enable when PayFast live` comment noise to the already-disabled `_SubscriptionGateMiddleware` line. Cosmetic only — confirmed `/v1/summary` (`main.py:446-491`, unchanged line range) untouched.

Working tree `git diff --stat -w` (ignoring whitespace) returns **empty** — no uncommitted logic changes.

Re-verified all high-risk anchors directly via Grep this run — all unchanged from 08-11:
- `"deferred_tax": 0.0` search on `financial_statements.py` → no matches (hard-coded zero still absent; deferred tax remains computed).
- `wear_and_tear_rate` column (`database.py:485`) and its `ALTER TABLE` (`database.py:1399`) confirmed still inside the migrations list literal.
- `purchase_order_reversal` present at all expected reversal-aware call sites: `financial_statements.py:558`, `journal.py:848`, `payroll.py:1778,2534`, `purchase_orders.py:445`.
- `decrypt_field` present in `suppliers.py:7,48-50`.
- Journal coverage functions all present in `journal.py`: `post_invoice_raised` (:194), `post_invoice_paid` (:234), `post_invoice_cogs` (:268), `post_expense` (:293), `post_payroll` (:368), `post_expense_paid` (:447), `post_po_received` (:476), `post_po_paid` (:528).
- Import-awareness: `source == "import"` exclusions at `payroll.py:1736,1812` confirmed present.
- `payroll.py`: `CURRENT_TAX_YEAR` (:182) resolves via `TAX_YEARS["2026/2027"]` (:185-187), `S11F_CAP = 430_000` (:196), `VAT_RATE = 0.15` (:1608, :2691) confirmed unchanged.

Fresh web search this run (SARS news, IASB update, TLAB/TALAB) surfaced nothing that changes ZuZan's code — see §6 and §7 for details.

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

**Overall: PASS.** The only code change since the last audit (a redundant `resp = None` line in `billing.py` and cosmetic comment noise in `main.py`) falls entirely outside Reports/Debtors/Creditors/AFS/tax scope. No open action items.

---

## 2. Reports

✓ No issues found.
- Dashboard (`payroll.py` `total_revenue`/`total_outstanding` logic, unchanged): revenue sums only paid invoices via `_to_zar()` plus `_bank_import_income()`; outstanding sums `sent`/`overdue` invoices via `_to_zar()`. Expenses summed ex-VAT, kept separate from revenue.
- PO COGS uses delivered-value-only for partials (`_po_delivered_net`, `payroll.py:27-46`), no double-counting with payroll or depreciation.
- Payroll costs included in expenses via the payslip sum, applied after gross profit.
- Management accounts and `/v1/summary` (`main.py:446-491`, confirmed byte-range unchanged this run) both route revenue/outstanding through `_to_zar()` and mirror the dashboard formula.

## 3. Debtors

✓ No issues found.
- Invoice status filter confirmed: `Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])` — paid invoices excluded.
- Aging cutoffs keyed off `due_date`, not invoice date.
- ZAR conversion via `_to_zar()` applied consistently, including per-item display amounts.

## 4. Creditors

✓ No issues found.
- Reversal-awareness (2026-07-13 fixes) confirmed present at all call sites — every site nets `source IN ("purchase_order", "purchase_order_reversal")`.
- AP control (Rule 7, `payroll.py:1753-1799` range) computes per-PO expected credit from `credit − debit` journal lines, falling back to `po.total_amount` only when no journal entry exists yet.
- Supplier bank details decrypted via `decrypt_field` (`suppliers.py:7,48-50`) — unchanged.

## 5. Cross-module consistency

✓ No issues found.
- Journal coverage complete: `post_invoice_raised`, `post_invoice_paid`, `post_invoice_cogs`, `post_expense`, `post_payroll`, `post_expense_paid`, `post_po_received`, `post_po_paid` — no gaps.
- Import-awareness (2026-07-11 fixes) intact: Rules 6/7 exclude `source == "import"` on 1100/2000 (`payroll.py:1736,1812`); balance sheet retains imported equity offsets 3998/3999. Non-ZAR invoice imports still require an exchange rate; unbalanced journal-import groups still rejected; both invoice and journal imports auto-run the backfill.
- Migration hygiene re-verified: `wear_and_tear_rate` column and `ALTER TABLE` still positioned inside the migrations list literal — this run's only schema-adjacent commit (`billing.py`'s redundant `resp = None`) touches no table/migration.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (declared in AFS meta). Statements: income statement, statement of financial position, changes in equity, cash flow (indirect), notes 2-9.

**Standards status (fresh web search this run):**
- **IFRS 18** *Presentation and Disclosure in Financial Statements* — still effective for annual periods beginning on/after 1 January 2027, not applicable to IFRS-for-SMEs preparers (ZuZan's basis). No change.
- **IFRS for SMEs third edition** (issued 27 February 2025, effective 1 January 2027, early adoption permitted) — no change to the substantive sections used by the existing transition plan (`ifrs_smes_3rd_edition_transition_plan.md`). Supporting/educational materials from the IASB continue rolling out through 2026 but nothing that alters ZuZan's Jan–Feb 2027 implementation checklist.
- VAT rate: reconfirmed 15% standard rate. Corporate income tax: 27% flat rate, unchanged.

**Section 5b — deferred tax: already implemented, re-verified this run:**
- Grepped `financial_statements.py` for `"deferred_tax": 0.0"` — no matches.
- Per-asset tax base = cost − cumulative SARS wear-and-tear allowance; temporary difference × CIT rate (27%) drives the deferred tax balance. Opening/closing balances drive `deferred_tax_expense` = closing − opening; Note 9 fields populated; `total_tax = tax_expense + deferred_tax_expense`; balance-sheet movement line present.
- Finance costs (2026-07-13 fix): interest presented below EBIT, tax/net profit derive from `profit_before_tax` — unchanged.

✓ No issues found.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date.

- Fresh web search this run: SARS's public activity in the last few days centres on the **2026 draft TLAB/TALAB**, published 30 July 2026 for comment (closes 28 August 2026, same standing item as prior reports — still not enacted). Coverage (BusinessTech, IOL) mentions proposed changes touching medical tax credits, company donations rules, and spousal donation exemptions — these are **proposed, not law**, and the comment period hasn't closed. No code change is warranted; flagged as a standing watch item.
- SARS crypto-assets taxation guide (comment period to 31 Aug 2026) — still not applicable, ZuZan has no crypto handling.
- SARS Saturday branch-hours and mobile-unit-schedule news — operational only, no rate impact.
- VAT confirmed 15% — matches `VAT_RATE = 0.15` in code (`payroll.py:1608, 2691`).
- CIT confirmed flat 27% — matches usage in dashboard/management/provisional-tax and `financial_statements.py`.
- s11F retirement fund deduction cap R430,000 (`payroll.py:196`) — unchanged.
- UIF: 1% employee / 1% employer, ceiling R17,712 → max R177.12/month per party (`payroll.py:187`) — unchanged.
- SDL 1% of gross remuneration, R500,000 annual-payroll small-employer exemption — unchanged.
- Provisional `2027/2028` `TAX_YEARS` entry remains a placeholder copy of 2026/2027 pending the Feb 2027 Budget — standing reminder, not a defect.
- Rates unchanged and current tax year present — no edits made (report-only per task rules; section 5b already implemented, verification-only this run).

**Sources consulted:** [SARS Home](https://www.sars.gov.za/) · [Updated SARS Mobile Unit Schedule for August 2026 — Overstrand Municipality](https://www.overstrand.gov.za/updated-sars-mobile-unit-schedule-for-august-2026/) · [SARS is coming after these taxpayers in 2026 — BusinessTech](https://businesstech.co.za/news/finance/865308/sars-is-coming-after-these-taxpayers-in-south-africa-in-2026/) · [SARS Tax Calendar 2026 — TaxTim](https://www.taxtim.com/za/tax-deadlines) · [National Treasury Publishes 2026 Draft Tax Bills for Public Comment — Tax Consulting SA](https://www.taxconsulting.co.za/national-treasury-publishes-2026-draft-tax-bills-for-public-comment/) · [Draft tax law changes could affect donations, VAT, medical tax credits and SARS refunds — IOL](https://iol.co.za/mercury/news/2026-08-11-draft-tax-law-changes-could-affect-donations-vat-medical-tax-credits-and-sars-refunds/) · [New tax laws for medical aid credits, companies, and spousal donations — BusinessTech](https://businesstech.co.za/news/government/868257/new-tax-laws-for-medical-aid-credits-companies-and-spousal-donations-in-south-africa/) · [National Treasury on publication of the 2026 draft tax bills for comment — gov.za](https://www.gov.za/news/media-statements/national-treasury-publication-2026-draft-tax-bills-comment-30-jul-2026) · [IFRS — March 2026 IFRS for SMEs Accounting Standard Update](https://www.ifrs.org/supporting-implementation/2015-ifrs-for-smes-supporting-materials/sme-updates/2026/march-2026-ifrs-for-smes-accounting-standard-update/) · [The IFRS for SMEs Accounting Standard — IFRS.org](https://www.ifrs.org/issued-standards/ifrs-for-smes/)

## 8. Action items

None. No open action items.

**Standing reminders (not defects, carried from prior reports):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry (`payroll.py:151+`) after Budget Feb 2027 and restart the backend;
(b) early-2027 runs should execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`);
(c) the AFS PayFast payment/ad-hoc tokenization feature and the `/reports/ai-insights` feature remain outside this audit's scope;
(d) NBCPSS private security payroll mode predates this audit's baseline, not yet part of this checklist's explicit scope;
(e) file-attribution note: the imported-equity-offset (3998/3999) exclusion logic lives in `payroll.py`'s `balance_sheet()`, not `financial_statements.py`;
(f) track the **2026 draft TLAB/TALAB** (comment period closes 28 August 2026) — press coverage this run flags proposed changes to medical tax credits, company donations rules, and spousal donation exemptions; once enacted, re-check whether any finalized provisions require rate/table changes in `payroll.py` or `financial_statements.py`;
(g) the IASB's May 2026 consolidation-exception exposure draft (comment period closed 9 September 2026) remains not applicable to ZuZan (single-entity AFS only) — awareness only;
(h) `parent_company_id`/`user_type` columns and the bookkeeper-onboarding/consolidated-billing/add-client features remain outside Reports/Debtors/Creditors/AFS/tax scope, flagged for awareness only;
(i) payroll subscription pricing (`max(65, employees×18.25)`, `payroll.py:2866,2984`) — billing/pricing only, not a SARS rate, no action needed for this checklist.
