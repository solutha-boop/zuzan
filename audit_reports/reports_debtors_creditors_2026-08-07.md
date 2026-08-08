# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 7 August 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-08-06 (full PASS, no open action items).

**Change detection since last run:** `git log` shows no new commits since `b277cdc` (2026-08-05 22:01), which was already covered by the 08-06 report. Working tree `git status` again shows `App_js_fixed.js`, `auth.py`, `billing.py`, `companies.py`, `main.py`, `payroll.py` modified-but-uncommitted.

- `git diff -w` on `companies.py`, `main.py`, `payroll.py` — **empty** (whitespace/line-ending noise only), consistent with every run since 07-26.
- `auth.py` and `billing.py` diffs are large but **whitespace-only** (line-ending churn across the whole file, no content change) — both out of audit scope regardless.
- `App_js_fixed.js` has one new **functional but out-of-scope** change: `BankFeedPanel` (around line 6629) now branches on `status?.configured` to show a "Coming Soon" state for banks not yet live, instead of always showing the Connect button. This is Pillar 3 (Bank Integration) UI, not Reports/Debtors/Creditors/AFS/tax — no audit impact.

**No functional changes to the audited surface area since 08-06.** Re-verified the highest-risk anchors directly via Grep this run:
- `grep -n '"deferred_tax": 0.0'` on `financial_statements.py` → no matches (hard-coded zero still absent; deferred tax logic present at `financial_statements.py:131,266-268,601-610,681`).
- `wear_and_tear_rate` column (`database.py:483`) and its `ALTER TABLE` (`database.py:1363`) confirmed still inside the migrations list literal, not after the loop.
- `purchase_order_reversal` present at all four expected reversal-aware call sites (`financial_statements.py:558`, `journal.py:848`, `payroll.py:1778,2534`, `purchase_orders.py:445`).
- `decrypt_field` present in `suppliers.py:7,48-50`.
- `_CIT_RATE` constant present in `financial_statements.py:78-84` (sourced from `fixed_assets.SA_CIT_RATE`, fallback 0.27).
- Journal coverage functions all present in `journal.py`: `post_invoice_raised` (:194), `post_invoice_paid` (:234), `post_invoice_cogs` (:268), `post_expense` (:293), `post_payroll` (:368), `post_expense_paid` (:447), `post_po_received` (:476), `post_po_paid` (:528).
- `payroll.py` `TAX_YEARS["2026/2027"]` (:131), `S11F_CAP = 430_000` (:196), `VAT_RATE = 0.15` (:1608, :2691) confirmed unchanged.
- `main.py` `/v1/summary` (:448-482) still imports and mirrors `_to_zar`/`_po_delivered_net`/`_bank_import_income` from `payroll.py`.
- Import-awareness: `source == "import"` exclusions at `payroll.py:1736,1812`; 3998/3999 offsets at `payroll.py:1526-1538`; `csv_import.py` exchange-rate requirement (:458-487) and unbalanced-group rejection (:1035,1064) all intact.

All match the 08-06 report's line references. Fresh web search this run confirms no new SARS or IFRS developments affecting the current tax year/standards.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ✅ PASS — logic unchanged, re-verified |
| Debtors (AR) | ✅ PASS — aged from due_date, paid excluded, ZAR amounts |
| Creditors (AP) | ✅ PASS — reversal-aware, bank details decrypted |
| Cross-module consistency | ✅ PASS — full journal coverage, import-awareness intact, migration hygiene intact |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) verified again, no regressions |
| Tax rates (SARS) | ✅ PASS — 2026/2027 tables current, no rate changes since 08-06 |

**Overall: PASS.** No functional code changes to the audited surface since the last audit; no new action items.

---

## 2. Reports

✓ No issues found.
- Dashboard (`payroll.py:1225-1270`): `total_revenue = sum(_to_zar(i) for i in paid_invoices)` (all-time paid invoices only) plus `_bank_import_income()` (:1237-1239); `total_outstanding = sum(_to_zar(i) for i in outstanding_invoices)` filtered to `sent`/`overdue` (:1241-1245). Expenses are summed ex-VAT (:1248-1251) and PO COGS uses delivered-value-only for partials (:1253-1261, `_po_delivered_net`), kept separate from revenue.
- Payroll costs included in expenses via the payslip sum, applied after gross profit.
- Depreciation (:1263-1267) added once, sourced from `DepreciationEntry`, no overlap with PO COGS or payroll.
- Management accounts (`payroll.py:2078-2153`): revenue and outstanding both route through `_to_zar()`; PO COGS and depreciation folded into `total_expenses` consistently with the dashboard; `ebit`/`tax_provision`/`net_profit` derived correctly.
- `/v1/summary` (`main.py:445-490`): imports `_to_zar`, `_po_delivered_net`, `_bank_import_income` from `payroll.py` (:448); mirrors the dashboard formula 1:1 (:452-482).

## 3. Debtors

✓ No issues found.
- Invoice status filter confirmed at every debtors-relevant site (`payroll.py:1241-1243, 1625-1628, 2149-2151`): `Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])` — paid invoices excluded.
- Aging cutoffs keyed off `due_date`, not invoice date (`payroll.py:1624-1628`).
- ZAR conversion via `_to_zar()` applied consistently, including per-item display amounts (`payroll.py:1630, 1642`).

## 4. Creditors

✓ No issues found.
- Reversal-awareness (2026-07-13 fixes) confirmed present at all call sites: `payroll.py:1778` (Rule 7 AP control check), `payroll.py:2534` (creditors-aging), `purchase_orders.py:445` (`pay_po`), `journal.py:848` (backfill) — every site nets `source IN ("purchase_order", "purchase_order_reversal")`.
- AP control (Rule 7, `payroll.py:1753-1790`) computes per-PO expected credit from `credit − debit` journal lines, falling back to `po.total_amount` only when no journal entry exists yet.
- Supplier bank details decrypted via `decrypt_field` (`suppliers.py:7,48-50`) — unchanged.

## 5. Cross-module consistency

✓ No issues found.
- Journal coverage complete (`journal.py`): `post_invoice_raised` (:194), `post_invoice_paid` (:234), `post_invoice_cogs` (:268), `post_expense` (:293), `post_payroll` (:368), `post_expense_paid` (:447), `post_po_received` (:476), `post_po_paid` (:528) — no gaps.
- Import-awareness (2026-07-11 fixes) intact: Rules 6/7 exclude `source == "import"` on 1100/2000 (`payroll.py:1736,1812`); balance sheet retains imported equity offsets 3998/3999 (`payroll.py:1526-1546`). Non-ZAR invoice imports still require an Exchange Rate column and reject rows with rate ≤ 0 (`csv_import.py:458-487`). Unbalanced journal-import groups still rejected (`csv_import.py:1035,1064`). Both invoice and journal imports auto-run the backfill (`csv_import.py:124-143,501-502,563-564`).
- Migration hygiene re-verified: `wear_and_tear_rate` column (`database.py:483`) and its `ALTER TABLE` (`database.py:1363`) confirmed still positioned inside the migrations list literal, not after the loop.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (declared in AFS meta). Statements: income statement, statement of financial position, changes in equity, cash flow (indirect), notes 2-9.

**Standards status (fresh web search this run):**
- **IFRS 18** *Presentation and Disclosure in Financial Statements* — confirmed still effective for annual periods beginning on/after 1 January 2027, early adoption permitted, and still not applicable to IFRS-for-SMEs preparers (ZuZan's basis). No change since 08-06.
- **IFRS for SMEs third edition** (issued 27 February 2025) — no new IASB update materially affecting ZuZan found this run; IASB has published additional educational webcasts on the revised Section 23 (Revenue) and Section 19 (Business Combinations) but no standard-text changes. Still effective 1 January 2027, early application permitted. Existing transition plan (`ifrs_smes_3rd_edition_transition_plan.md`) remains current.
- **VAT rate:** 15% standard rate, unchanged.
- **Corporate income tax:** reconfirmed 27%, unchanged, for years of assessment ending 1 Apr 2026 – 31 Mar 2027 per Budget 2026.

**Section 5b — deferred tax: already implemented, re-verified this run:**
- Grepped `financial_statements.py` for `"deferred_tax": 0.0` — no matches, confirming the hard-coded zero was not reintroduced.
- `_deferred_tax_balance()` (`financial_statements.py:131`) computes per-asset tax base = cost − cumulative SARS wear-and-tear allowance; temporary difference × `_CIT_RATE` (27%, `:78-84`).
- Opening/closing balances (`:266-268`) drive `deferred_tax_expense` = closing − opening; Note 9 fields `deferred_tax`, `deferred_tax_opening_balance`, `deferred_tax_closing_balance` populated (`:601-610`); `total_tax = tax_expense + deferred_tax_expense` (`:601`); balance-sheet movement line `deferred_tax_movement` present (`:681`).
- Reversal-aware AP logic and the `wear_and_tear_rate` migration (both prerequisites for this feature) confirmed intact (§4, §5).
- **Finance costs (2026-07-13 fix):** presentation below EBIT and derivation of tax/net profit from `profit_before_tax` (not EBIT) stands — file unchanged since 08-06.

✓ No issues found.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date.

- No rate changes found since the 08-06 audit. Personal income tax brackets were adjusted ~3.4% for bracket creep effective 1 March 2026 (already reflected in the 2026/2027 table); primary rebate R17,820, secondary R9,765, tertiary R3,249 (`payroll.py:141-143,161-163`) — consistent with Budget 2026.
- **New this run (informational only, no code impact):** National Treasury and SARS released the **2026 draft Taxation Laws Amendment Bill (TLAB)** and **draft Tax Administration Laws Amendment Bill (TALAB)** on 30 July 2026, giving legislative effect to Budget 2026 proposals; public comment closes 28 August 2026. These are draft bills, not yet enacted, and don't change any rate currently in the codebase. Worth a follow-up check once enacted (likely later in 2026/H1 2027).
- s11F retirement fund deduction cap confirmed correctly implemented at R430,000 (`payroll.py:196`, `S11F_CAP`), rate 27.5% (`S11F_RATE`), formula at `:433-453` — unchanged from 08-06.
- Medical tax credits (Section 6A): R376/month main member + first dependant, R254/month additional dependants (`payroll.py:198,297,392`) — unchanged, consistent with 2026/2027.
- UIF ceiling gives a max monthly contribution of R177.12 per party (1% employee / 1% employer) — consistent with the 2026/2027 table.
- SDL 1% of gross remuneration, R500,000 annual-payroll exemption threshold for small employers — unchanged.
- VAT standard rate 15% (`payroll.py:1608,2691`) — unchanged.
- Corporate income tax 27% (`financial_statements.py:84`, `_CIT_RATE`) — unchanged, confirmed for years of assessment ending 1 Apr 2026 – 31 Mar 2027.
- Small Business Corporation (SBC) graduated rates (0%/7%/21%/27% bands) surfaced in this run's search as part of Budget 2026, but ZuZan's CIT provisioning uses the flat 27% standard company rate, not an SBC election — this is the correct default for a general-purpose bookkeeping app (SBC is an elective regime with its own qualifying criteria) and is not a discrepancy; noting for awareness only, not an action item.
- Provisional `2027/2028` `TAX_YEARS` entry (`payroll.py:151-166`) remains a placeholder copy of 2026/2027 pending the Feb 2027 Budget — standing reminder, not a defect.
- Rates unchanged and current tax year present — no edits made (report-only per task rules; section 5b already implemented, verification-only this run).

**Sources consulted:** [Budget 2026 Frequently Asked Questions — SARS](https://www.sars.gov.za/about/sars-tax-and-customs-system/budget/budget-2026-frequently-asked-questions/) · [South Africa's tax changes in 2026 — JoburgETC](https://www.joburgetc.com/business/south-africa-tax-changes-2026/) · [Income tax brackets, medical tax credits adjusted for inflation — Moonstone](https://www.moonstone.co.za/income-tax-brackets-medical-tax-credits-adjusted-for-inflation/) · [Budget 2026: a small win for taxpayers — TaxTim](https://www.taxtim.com/za/blog/budget-2026) · [Budget Speech 2026/2027: Tax Overview — Werksmans Attorneys](https://werksmans.com/budget-speech-2026-2027-tax-overview/) · [BUDGET 2026 TAX GUIDE — SARS](https://www.sars.gov.za/wp-content/uploads/Docs/Budget/Budget2026/Budget-tax-guide-2026-web-version.pdf) · [The 2026 Draft Tax Bills Are Out — Accounting Weekly](https://www.accountingweekly.com/sars-updates/2026-draft-tlab-and-talab-what-accountants-must-know) · [IFRS 18 — IFRS.org](https://www.ifrs.org/issued-standards/list-of-standards/ifrs-18-presentation-and-disclosure-in-financial-statements/) · [March 2026 IFRS for SMEs Accounting Standard Update — IFRS.org](https://www.ifrs.org/supporting-implementation/2015-ifrs-for-smes-supporting-materials/sme-updates/2026/march-2026-ifrs-for-smes-accounting-standard-update/) · [IASB issues third edition of IFRS for SMEs — EY](https://www.ey.com/en_gl/technical/ifrs-technical-resources/iasb-issues-third-edition-of-ifrs-for-smes-accounting-standard)

## 8. Action items

None open.

**Standing reminders (not defects, carried from prior reports):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry (`payroll.py:151+`) after Budget Feb 2027 and restart the backend;
(b) early-2027 runs should execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`) — Section 23 revenue and Section 19 business-combinations changes are most relevant to ZuZan; Section 9 (consolidation) confirmed not applicable since ZuZan is single-entity only;
(c) the AFS PayFast payment/ad-hoc tokenization feature and the `/reports/ai-insights` (AI management-pack) feature remain outside this audit's Reports/Debtors/Creditors/AFS-content/tax scope;
(d) NBCPSS private security payroll mode (grades, allowances, BC levy, PSIRA fee) predates this audit's baseline and doesn't affect the audited totals, but isn't yet part of this checklist's explicit scope;
(e) file-attribution note: the imported-equity-offset (3998/3999) exclusion logic lives in `payroll.py`'s `balance_sheet()`, not `financial_statements.py`;
(f) the s20A loss-ring-fencing threshold change (39% vs. 45% marginal rate trigger, effective years of assessment from 1 March 2026) is not applicable to any code ZuZan implements — awareness only;
(g) a separate EMP201 compliance report (`audit_reports/emp201_2026-07.md`, generated 2026-08-05) flagged that Solutha (company 3) had not run payroll for June or July 2026 as of that report's date, risking a missed EMP201 deadline (7 August 2026) — outside this audit's scope; worth a follow-up EMP201 check now that the deadline has passed;
(h) **new this run:** track the 2026 draft TLAB/TALAB (comment period closes 28 August 2026) — once enacted, re-check whether any of the finalized provisions require rate/table changes in `payroll.py` or `financial_statements.py`;
(i) **new this run:** `App_js_fixed.js` `BankFeedPanel` gained a `status?.configured` branch for a "Coming Soon" state on unconfigured banks — Pillar 3 (Bank Integration) UI change, outside this audit's scope but flagged for awareness since it touches bank-feed UI that eventually feeds the Reports module.
