# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 6 August 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-08-05 (full PASS, no open action items).

**Change detection since last run:** `git log 77737c0..b277cdc` shows one new commit, `b277cdc` (2026-08-05 22:01, same recurring message: "fix: RecurringInvoices + CreditNotes useEffect Promise crash"). `git diff 77737c0..b277cdc --stat` touches `audit_reports/emp201_2026-07.md` (new, out of scope — a separate EMP201 compliance check), the 08-05 audit report itself, `zuzan-backend/billing.py` (+1, out of audit scope — a further cosmetic duplication of a stray `resp = None` line), `zuzan-backend/main.py` (the recurring cosmetic duplication of the disabled-middleware comment; `_SubscriptionGateMiddleware` remains disabled either way), and `zuzan-landing.html` (out of scope). **None of the in-scope audit files changed in this commit.**

Working tree `git status` again shows `App_js_fixed.js`, `auth.py`, `billing.py`, `companies.py`, `main.py`, `payroll.py` modified-but-uncommitted; `git diff -w` on the in-scope subset (`companies.py`, `main.py`, `payroll.py`) is **empty** — line-ending/whitespace noise only, consistent with every run since 07-26.

**No functional changes to the audited surface area since 08-05.** Re-verified the highest-risk anchors directly via Grep this run rather than relying on the diff alone:
- `grep -n '"deferred_tax": 0.0'` on `financial_statements.py` → **no matches** (hard-coded zero still absent, confirming deferred tax remains computed).
- `wear_and_tear_rate` column (`database.py:483`) and its `ALTER TABLE` (`database.py:1363`) confirmed still inside the migrations list literal, not after the loop.
- `purchase_order_reversal` present at all four expected reversal-aware call sites (`financial_statements.py:558`, `journal.py:848`, `payroll.py:1778`, `payroll.py:2534`, `purchase_orders.py:445`).
- `decrypt_field` present in `suppliers.py:7,48-50`.
- `_CIT_RATE` constant present in `financial_statements.py:78-84` (sourced from `fixed_assets.SA_CIT_RATE`, fallback 0.27).
- Journal coverage functions all present in `journal.py`: `post_invoice_raised` (:194), `post_invoice_paid` (:234), `post_invoice_cogs` (:268), `post_expense` (:293), `post_payroll` (:368), `post_expense_paid` (:447), `post_po_received` (:476), `post_po_paid` (:528).
- `payroll.py` `TAX_YEARS["2026/2027"]` rebates (17820 / 9765 / 3249) and `VAT_RATE = 0.15` (:1608, :2691) confirmed unchanged.

All match the 08-05 report's line references exactly, as expected given the empty diff.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ✅ PASS — logic unchanged, re-verified |
| Debtors (AR) | ✅ PASS — aged from due_date, paid excluded, ZAR amounts |
| Creditors (AP) | ✅ PASS — reversal-aware, bank details decrypted |
| Cross-module consistency | ✅ PASS — full journal coverage, import-awareness intact, migration hygiene intact |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) verified again, no regressions |
| Tax rates (SARS) | ✅ PASS — 2026/2027 tables current, no rate changes since 08-05 |

**Overall: PASS.** No functional code changes to the audited surface since the last audit; no new action items.

---

## 2. Reports

✓ No issues found. File contents unchanged since 08-05 (confirmed via diff); prior verification stands:
- Dashboard (`payroll.py:1233-1245`): `total_revenue = sum(_to_zar(i) for i in paid_invoices)` plus `_bank_import_income()` (`:1237-1239`); `total_outstanding = sum(_to_zar(i) for i in outstanding_invoices)` filtered to `sent`/`overdue` (`:1241-1245`). Expenses (`:1248-1251`) and PO COGS (`:1253-1261`, delivered-value-only for partials) are aggregated separately, ex-VAT, and never mixed into revenue.
- Payroll costs included in expenses via the payslip sum, applied after gross profit.
- Depreciation (`:1263-1267`) added once, sourced from `DepreciationEntry`, no overlap with PO COGS or payroll.
- Management accounts (`payroll.py:2078-2153`): revenue and outstanding both route through `_to_zar()`; PO COGS (`:2095-2108`) and depreciation (`:2110-2118`) folded into `total_expenses` consistently with the dashboard; `ebit`/`tax_provision`/`net_profit` derived correctly (`:2142-2147`).
- `/v1/summary` (`main.py:445-490`): imports `_to_zar`, `_po_delivered_net`, `_bank_import_income` from `payroll.py` (`:448`); mirrors the dashboard formula 1:1 (`:452-482`).

## 3. Debtors

✓ No issues found.
- Invoice status filter confirmed at every debtors-relevant site (`payroll.py:1241-1243, 1625-1628, 2149-2151`): `Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])` — paid invoices excluded.
- Aging cutoffs keyed off `due_date`, not invoice date (`payroll.py:1624-1628`).
- ZAR conversion via `_to_zar()` applied consistently, including per-item display amounts (`payroll.py:1630, 1642`).

## 4. Creditors

✓ No issues found.
- **Reversal-awareness (2026-07-13 fixes) re-confirmed present at all call sites this run:** `payroll.py:1778` (Rule 7 AP control check), `payroll.py:2534` (creditors-aging), `purchase_orders.py:445` (`pay_po`), `journal.py:848` (backfill) — every site nets `source IN ("purchase_order", "purchase_order_reversal")`.
- AP control (Rule 7, `payroll.py:1753-1790`) computes per-PO expected credit from `credit − debit` journal lines, falling back to `po.total_amount` only when no journal entry exists yet.
- Supplier bank details decrypted via `decrypt_field` (`suppliers.py:7,48-50`) — unchanged.

## 5. Cross-module consistency

✓ No issues found.
- Journal coverage complete (`journal.py`): `post_invoice_raised` (`:194`), `post_invoice_paid` (`:234`), `post_invoice_cogs` (`:268`), `post_expense` (`:293`), `post_payroll` (`:368`), `post_expense_paid` (`:447`), `post_po_received` (`:476`), `post_po_paid` (`:528`) — no gaps.
- Import-awareness (2026-07-11 fixes) intact: Rules 6/7 exclude `source == "import"` on 1100/2000 (`payroll.py:1736,1812`); balance sheet retains imported equity offsets 3998/3999 (`payroll.py:1526-1546`). Non-ZAR invoice imports still require an Exchange Rate column and reject rows with rate ≤ 0 (`csv_import.py:458-475`). Unbalanced journal-import groups still rejected (`csv_import.py:1035,1064`). Both invoice and journal imports auto-run the backfill (`csv_import.py:124-143,501-502,563-564`).
- **Migration hygiene re-verified:** `wear_and_tear_rate` column (`database.py:483`) and its `ALTER TABLE` (`database.py:1363`) confirmed still positioned inside the migrations list literal (between the credit-notes and pension/medical-aid migration blocks), not after the loop.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (declared in AFS meta). Statements: income statement, statement of financial position, changes in equity, cash flow (indirect), notes 2-9.

**Standards status (fresh web search this run):**
- **IFRS 18** *Presentation and Disclosure in Financial Statements* — confirmed still effective for annual periods beginning on/after 1 January 2027, early adoption permitted, and still not applicable to IFRS-for-SMEs preparers (ZuZan's basis). Search results this run note 2026 is the comparative-period year for calendar-year IFRS-18 adopters, reinforcing that ZuZan (on IFRS for SMEs, not full IFRS) is unaffected until it migrates bases. No change to scope or effective date since 08-05.
- **IFRS for SMEs third edition** (issued 27 February 2025) — no new IASB update found this run; still effective 1 January 2027, early application permitted. Existing transition plan (`ifrs_smes_3rd_edition_transition_plan.md`) remains current.
- **VAT rate:** 15% standard rate, unchanged.
- **Corporate income tax:** reconfirmed 27%, unchanged, for years of assessment ending 1 Apr 2026 – 31 Mar 2027 per Budget 2026.

**Section 5b — deferred tax: already implemented, re-verified this run:**
- Grepped `financial_statements.py` for `"deferred_tax": 0.0` — **no matches**, confirming the hard-coded zero was not reintroduced.
- Per-asset tax base = cost − cumulative SARS wear-and-tear allowance; temporary difference × 27% (`_CIT_RATE`, confirmed present at `:78-84`).
- Reversal-aware AP logic and the `wear_and_tear_rate` migration (both prerequisites for this feature) confirmed intact (§4, §5).
- File unchanged since 08-05 per diff — full line-level detail (functions, note fields, balance-sheet DTL/DTA lines, retained-earnings adjustment, frontend rendering) carries over from the 08-05 report without modification.
- **Finance costs (2026-07-13 fix):** file unchanged since 08-05; presentation below EBIT and derivation of tax/net profit from `profit_before_tax` (not EBIT) stands.

✓ No issues found.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date.

- No rate changes found since the 08-05 audit. Fresh search this run reconfirms: personal income tax brackets were adjusted ~3.4% for bracket creep effective 1 March 2026 (already reflected in the 2026/2027 table); primary rebate R17,820, secondary R9,765, tertiary R3,249 (`payroll.py:141-143,161-163`) — all consistent with Budget 2026.
- One item surfaced in initial research this run — the retirement-annuity/pension/provident fund deduction cap (s11F) increased from R350,000 to **R430,000** per annum effective 1 March 2026 (first adjustment since 2016). Followed up with a targeted grep and confirmed it is **already correctly implemented**: `payroll.py:193-196` — `S11F_CAP = 430_000` with an explicit comment "Cap increased from R350,000 → R430,000 (first increase since 2016, Budget 2026)"; the 27.5% rate (`S11F_RATE = 0.275`) and the `min(contribution, 27.5% × remuneration, R430,000)` formula are applied at `:433-453`. No discrepancy — not previously logged in prior reports' tax section, so recording it here as a newly-verified-correct item.
- Medical tax credits (Section 6A) also increased in line with inflation: R376 (main member + first dependant, up from R364) and R254 (additional dependants, up from R246) — `payroll.py:198,297,392` already document "R376/month" for 2026/2027, consistent with this figure. No discrepancy found.
- UIF ceiling gives a max monthly contribution of R177.12 per party (1% employee / 1% employer) — consistent with `payroll.py`'s 2026/2027 table.
- **SDL** 1% of gross remuneration, with the usual R500,000 annual-payroll exemption threshold for small employers — unchanged from `payroll.py`.
- **VAT** standard rate 15% (`payroll.py:1608,2691`) — unchanged; no VAT rate news found this run.
- **Corporate income tax** 27% (`financial_statements.py:84`, `_CIT_RATE`) — unchanged, confirmed for years of assessment ending 1 Apr 2026 – 31 Mar 2027.
- Provisional `2027/2028` `TAX_YEARS` entry (`payroll.py:151-166`) remains a placeholder copy of 2026/2027 pending the Feb 2027 Budget — standing reminder, not a defect.
- Rates unchanged and current tax year present — no edits made (report-only per task rules; section 5b already implemented, verification-only this run). The R430,000 s11F cap above was verified already-correct, not an edit made under this audit's report-only restriction.

**Sources consulted:** [IFRS 18 — IFRS.org](https://www.ifrs.org/issued-standards/list-of-standards/ifrs-18-presentation-and-disclosure-in-financial-statements/) · [IFRS Standards Effective 2026: Compliance Guide — Prima Consulting](https://primaconsulting.org/ifrs-changes-2026-update/) · [IFRS 18 — KPMG International](https://kpmg.com/xx/en/what-we-do/services/audit/corporate-reporting-institute/ifrs/presentation-and-disclosure/ifrs18.html) · [IFRS 18 reshapes statement of profit or loss — RSM US](https://rsmus.com/insights/services/financial-management/ifrs-18-reshapes-statement-of-profit-or-loss.html) · [South Africa Introduces Updated Income Tax Thresholds in Budget 2026 — activpayroll](https://www.activpayroll.com/news-articles/south-africa-introduces-updated-income-tax-thresholds-in-budget-2026) · [SARS Tax Tables 2026/2027 — Accounter](https://accounter.co.za/news/sars-tax-tables-2026-2027) · [Budget 2026 Frequently Asked Questions — SARS](https://www.sars.gov.za/about/sars-tax-and-customs-system/budget/budget-2026-frequently-asked-questions/) · [Budget 2026: a small win for taxpayers — TaxTim](https://www.taxtim.com/za/blog/budget-2026) · [BUDGET 2026 TAX GUIDE — SARS](https://www.sars.gov.za/wp-content/uploads/Docs/Budget/Budget2026/Budget-tax-guide-2026-web-version.pdf)

## 8. Action items

None open.

**Standing reminders (not defects, carried from prior reports):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry (`payroll.py:151+`) after Budget Feb 2027 and restart the backend;
(b) early-2027 runs should execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`) — Section 23 revenue and Section 19 business-combinations changes are most relevant to ZuZan; Section 9 (consolidation) confirmed not applicable since ZuZan is single-entity only;
(c) the AFS PayFast payment/ad-hoc tokenization feature and the `/reports/ai-insights` (AI management-pack) feature remain outside this audit's Reports/Debtors/Creditors/AFS-content/tax scope — worth folding PayFast/billing into scope once `/billing/subscribe` lands, since it will touch `main.py`;
(d) NBCPSS private security payroll mode (grades, allowances, BC levy, PSIRA fee) predates this audit's baseline and doesn't affect the audited totals, but isn't yet part of this checklist's explicit scope — consider adding it to the payroll section of future audits;
(e) file-attribution note (carried since 08-01): the imported-equity-offset (3998/3999) exclusion logic lives in `payroll.py`'s `balance_sheet()`, not `financial_statements.py`;
(f) the s20A loss-ring-fencing threshold change (39% vs. 45% marginal rate trigger, effective years of assessment from 1 March 2026), logged 08-04, remains not applicable to any code ZuZan implements — awareness only, no action;
(g) **new this run:** a separate EMP201 compliance report (`audit_reports/emp201_2026-07.md`, generated 2026-08-05) flagged that Solutha (company 3) has not run payroll for June or July 2026, risking a missed EMP201 deadline (7 August 2026) — outside this audit's scope but worth relaying to the user given the imminent deadline.
