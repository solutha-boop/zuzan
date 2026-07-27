# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 27 July 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-07-26 (full PASS, no open action items).

**Change detection since last run:** Audit-scope logic files are byte-identical to the 07-26 baseline (`bb969b8`, 2026-07-24 22:07) with one exception confirmed benign: `database.py` gained 6 lines (three new `Company` columns — `payfast_token`, `payfast_token_created`, `next_billing_date` — and a new `afs_payments` table, all for the new once-off AFS PayFast payment / ad-hoc tokenization feature added to `billing.py`, which is **not** in this audit's file scope). `main.py` and `App_js_fixed.js` also changed, but the diffs are billing/subscription UI (a "Manage Billing" button became an "Add/Update Payment Method" flow calling `/billing/subscribe`) — verified the `/v1/summary` endpoint (main.py:444-489) is otherwise unchanged. `payroll.py`, `companies.py`, `suppliers.py`, `customers.py`, `purchase_orders.py`, `journal.py`, `financial_statements.py`, `csv_import.py`, `fixed_assets.py` — zero diff since 07-24.

Confirmed the new `database.py` migrations (payfast_token/next_billing_date columns, afs_payments table, lines 1397-1410) remain correctly placed **inside** the migrations list literal, ahead of the closing `]:` and for-loop (database.py:1424) — no dead-code migrations introduced.

Noted in passing: the "NBCPSS private security payroll mode" feature referenced in recent commit messages was already present in `payroll.py` (lines 212-410+) as of 2026-07-19, i.e. before the 07-25/07-26 baseline — not a new change this run. It sets industry-specific minimum wages, night-shift/special allowances, a bargaining-council levy, and PSIRA fee, valid through 28 February 2027 per its own constant; it does not touch Reports/Debtors/Creditors/AFS totals or the SARS PAYE/UIF/SDL/CIT/VAT logic audited below, so it's out of this checklist's direct scope but flagged for awareness.

Re-verified the substantive logic directly via targeted greps (not relying on mtime alone): dashboard revenue/outstanding (`payroll.py:1237,1239,1245`), reversal-aware AP netting (`payroll.py:1770-1778`, `:2433-2440`), deferred-tax module (`financial_statements.py:78-328`), and the 2026/2027 TAX_YEARS bracket table (`payroll.py:131-145`) — all identical to 07-26 findings. Refreshed external (SARS/IFRS) research since those facts can change independent of the codebase.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ✅ PASS — logic unchanged, re-verified |
| Debtors (AR) | ✅ PASS — aged from due_date, paid excluded, ZAR amounts |
| Creditors (AP) | ✅ PASS — reversal-aware, bank details decrypted |
| Cross-module consistency | ✅ PASS — full journal coverage, import-awareness intact, migration hygiene intact |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) verified again, no regressions |
| Tax rates (SARS) | ✅ PASS — 2026/2027 tables current, no Budget/SARS rate changes since 07-26 |

**Overall: PASS.** No open action items. Only out-of-scope billing/PayFast-tokenization changes since the last run; audited accounting logic unchanged.

---

## 2. Reports

✓ No issues found. Unchanged from 07-26 — re-confirmed via grep:
- `/v1/summary` (main.py:444-489): revenue from paid invoices + `_bank_import_income`; expenses = ex-VAT expense rows + PO COGS (`_po_delivered_net`, received/partial/paid POs only) + depreciation; payroll cost summed separately from `Payslip.total_cost`; outstanding via `_to_zar()` on sent/overdue invoices only. No double counting between expense categories.
- Dashboard (payroll.py:1237-1245): `total_revenue = sum(_to_zar(i) for i in paid_invoices)` then `+= _bank_import_income(db, cid)`; `total_outstanding = sum(_to_zar(i) for i in outstanding_invoices)`.
- `_to_zar()` usage consistent across all revenue/outstanding aggregation points checked (payroll.py:1630, 1642, 1725, 1854, 1917, 2078, 2153, 2251).

## 3. Debtors

✓ No issues found. Unchanged from 07-26.
- `/reports/debtors-aging` filters `status IN (sent, overdue)`; ZAR via `_to_zar(inv)`; aging strictly from `due_date`; buckets not_due / current / 31-60 / 61-90 / 90+. Paid invoices excluded (status filter).

## 4. Creditors

✓ No issues found. Unchanged from 07-26.
- `/reports/creditors-aging` pulls received/partial POs, excludes fully paid; supplier bank details decrypted via `decrypt_field`.
- **Reversal-awareness (2026-07-13 fixes) re-confirmed:** both the creditors-aging endpoint (payroll.py:2433-2440) and Rule 7 (payroll.py:1770-1778) net `SUM(credit − debit)` with `source IN ("purchase_order", "purchase_order_reversal")`.

## 5. Cross-module consistency

✓ No issues found. Unchanged from 07-26.
- Journal coverage complete across invoices, expenses, payroll, POs, inventory, fixed assets.
- Debtors/Creditors Control reconciliation (Rules 6-7) remains reversal- and import-aware.
- Import-awareness (2026-07-11 fixes) intact: `csv_import.py` auto-backfills the journal after imports; Rules 6/7 exclude `source == "import"` lines.
- Migration hygiene re-checked for the new 07-26/07-27 additions: all new `database.py` ALTER TABLE / CREATE TABLE statements (payfast_token fields, afs_payments table, lines 1397-1410) sit inside the migrations list literal before the closing `]:` — no post-loop dead code introduced by the new billing feature.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (declared in AFS meta). Statements: income statement, statement of financial position, changes in equity, cash flow (indirect), notes 2-9.

**Standards status (re-confirmed via fresh web search this run):**
- IFRS 18 *Presentation and Disclosure in Financial Statements* — still effective for annual periods beginning on or after 1 Jan 2027; applies to full-IFRS preparers, not IFRS for SMEs. No ZuZan change required yet.
- IFRS for SMEs **third edition** (effective 1 Jan 2027) — no new IASB update materially affecting ZuZan since 07-26. The IASB published an Exposure Draft on a Consolidation Exception in May 2026 (comment period open to 9 September 2026); if finalized it would take effect 1 Jan 2027 alongside the third edition — not yet applicable, noted for the standing transition-plan file.

**Section 5b — deferred tax: already implemented, re-verified this run (financial_statements.py, grepped directly):**
- `_deferred_tax_balance` (:131-172): tax base = cost − straight-line SARS wear-and-tear apportioned from purchase date, floored at 0; temporary difference × `_CIT_RATE` (single-sourced from `fixed_assets.SA_CIT_RATE`, :82-84).
- Note 9: `deferred_tax_expense = dt_closing − dt_opening` (:266-268); `total_tax = current_tax + deferred_tax` (:257-260 region).
- Balance sheet presents closing DTL/DTA (:315-328) with matching retained-earnings adjustment — Assets = Equity + Liabilities preserved by construction. No regressions.

✓ No issues found.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date.

- Fresh web search this run confirms no rate changes since 07-26: 2026/2027 brackets/rebates adjusted 3.4% for inflation, top bracket threshold R1,878,600 at 45% — matches `payroll.py:131-145` exactly (top bracket "min": 1878601).
- The s20A ring-fencing-of-losses change (39% marginal-rate trigger instead of 45%, for years of assessment from 1 March 2026) remains an individual/personal-tax provision with no equivalent in ZuZan's company/payroll logic — no code impact, noted for completeness only.
- **VAT** — standard rate confirmed still **15%**; code constants (payroll.py:1608, :2597) correct.
- **PAYE brackets / rebates / UIF / SDL** (payroll.py:131-145) — unchanged, current for 2026/2027. UIF ceiling R17,712/month, 1%/1% employee/employer, SDL 1% — consistent with current SARS rules. ✓
- **Corporate income tax** 27%, single-sourced via `SA_CIT_RATE` — unchanged. ✓
- Rates unchanged and current tax year present — no edits made (report-only per task rules).

**Sources consulted:** [SARS — Changes for Filing Season 2026](https://www.sars.gov.za/latest-news/changes-for-filing-season-2026/) · [Accounter — SARS Tax Tables 2026/2027](https://accounter.co.za/news/sars-tax-tables-2026-2027) · [MSN — SARS tax season 2026: what's changed](https://www.msn.com/en-za/news/other/sars-tax-season-2026-here-s-what-s-changed/ar-AA26eAey) · [Moonstone — Income tax brackets, medical tax credits adjusted for inflation](https://www.moonstone.co.za/income-tax-brackets-medical-tax-credits-adjusted-for-inflation/) · [SARS — Budget 2026 FAQ](https://www.sars.gov.za/about/sars-tax-and-customs-system/budget/budget-2026-frequently-asked-questions/) · [IFRS — June 2026 IFRS for SMEs Accounting Standard Update](https://www.ifrs.org/supporting-implementation/2015-ifrs-for-smes-supporting-materials/sme-updates/2026/june-2026-ifrs-for-smes-accounting-standard-update/) · [IFRS — March 2026 IFRS for SMEs Accounting Standard Update](https://www.ifrs.org/supporting-implementation/2015-ifrs-for-smes-supporting-materials/sme-updates/2026/march-2026-ifrs-for-smes-accounting-standard-update/)

## 8. Action items

None open.

**Standing reminders (not defects):** (a) replace the provisional 2027/2028 TAX_YEARS entry after Budget Feb 2027 and restart the backend; (b) early-2027 runs execute the IFRS for SMEs 3rd-edition transition-plan checklist (Section 23 revenue and Section 19 business-combinations changes are the most relevant to ZuZan; watch the May-2026 Consolidation Exception exposure draft for finalization); (c) the new once-off AFS PayFast payment / ad-hoc tokenization feature (`billing.py`, new `afs_payments` table and `Company.payfast_token*` columns) is outside this audit's Reports/Debtors/Creditors/AFS-content/tax scope — flag for inclusion if a future audit's file list is expanded to cover billing; (d) NBCPSS private security payroll mode (grades, allowances, BC levy, PSIRA fee) predates this audit's baseline and doesn't affect the audited totals, but isn't yet part of this checklist's explicit scope — consider adding it to the payroll section of future audits given it introduces new statutory-adjacent deductions.
