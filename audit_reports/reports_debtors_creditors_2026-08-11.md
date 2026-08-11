# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 11 August 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-08-10 (full PASS).

**Change detection since last run:** `git log` shows the 08-10 report only covered up through commit `669598f` (20:50 on 08-09). Nine further commits landed later on 2026-08-10 (18:27–21:05), ending at `35d654c`: `16aef76` (profile name edit), `0064f9a`/`726a0a0`/`fa5cd2b`/`59b2188` (add-client flow, re-committed several times), `547a311` (bookkeeper user type), `da1355a` (consolidated billing + bookkeeper onboarding), `7ddd3fa`/`35d654c` (payroll price-parity with SimplePay).

Reviewed `git diff 669598f 35d654c --stat` (13 files, +733/−40) and read the diffs for every file touching the audited surface area:
- **`payroll.py`** (+4/−4, `:2864-2867`, `:2982-2985`): only change is the payroll pricing constant in `initiate_payment` and `subscription_status` — `max(99, employees × 34.00)` → `max(65, employees × 18.25)`. This is subscription/billing pricing, not `TAX_YEARS`, `VAT_RATE`, or any tax/journal calculation. No effect on Reports/Debtors/Creditors/AFS/tax logic.
- **`database.py`** (+4): adds `parent_company_id` on `Company` and `user_type` on `User`, both with their `ALTER TABLE` statements correctly placed inside the migrations list literal (`:1465-1466`) — not appended after the loop. Not a change to `FixedAsset`/`wear_and_tear_rate` or any AR/AP/journal table.
- **`main.py`** (+2/−1): more repeated `# disabled` comment noise on the already-disabled `_SubscriptionGateMiddleware` line — cosmetic, no logic change, `/v1/summary` untouched (confirmed by reading `main.py:446-491` in full this run).
- **`auth.py`, `billing.py`, `companies.py`, `config.py`, `email_service.py`, `App_js_fixed.js`/`App.js`**: bookkeeper onboarding, consolidated billing rollup, add-client flow, welcome emails — all outside Reports/Debtors/Creditors/AFS/tax scope.

Working tree `git diff --stat -w` (ignoring whitespace) returns **empty** — the five modified-but-uncommitted files (`auth.py`, `billing.py`, `companies.py`, `main.py`, `payroll.py`) are pure CRLF/line-ending noise, consistent with every prior run since 07-26.

Re-verified the highest-risk anchors directly via Grep this run — all unchanged from 08-10:
- `grep '"deferred_tax": 0.0'` on `financial_statements.py` → no matches (hard-coded zero still absent).
- `wear_and_tear_rate` column (`database.py:485`) and its `ALTER TABLE` (`database.py:1399`) confirmed still inside the migrations list literal.
- `purchase_order_reversal` present at all four expected reversal-aware call sites (`financial_statements.py:558`, `journal.py:848`, `payroll.py:1778,2534`, `purchase_orders.py:445`).
- `decrypt_field` present in `suppliers.py:7,48-50`.
- Journal coverage functions all present and wired in `journal.py`: `post_invoice_raised` (:194), `post_invoice_paid` (:234), `post_invoice_cogs` (:268), `post_expense` (:293), `post_payroll` (:368), `post_expense_paid` (:447), `post_po_received` (:476), `post_po_paid` (:528).
- Import-awareness: `source == "import"` exclusions at `payroll.py:1736,1812` confirmed present.
- `payroll.py` `TAX_YEARS["2026/2027"]` (:131), `"2027/2028"` placeholder (:151), `CURRENT_TAX_YEAR` (:182), `S11F_CAP = 430_000` (:196), `VAT_RATE = 0.15` (:1608, :2691) confirmed unchanged.
- Read the full text of `dashboard()` (`payroll.py:1225-1274`), Rule 7 AP netting (`payroll.py:1753-1799`), `_deferred_tax_balance()` (`financial_statements.py:131-173`), and `/v1/summary` (`main.py:446-491`) directly — logic identical to what was captured in the 08-10 report.

Fresh web search this run (SARS news, IASB update) surfaced nothing that affects ZuZan's code — see §7 and §6 for details.

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

**Overall: PASS.** The only code changes since the last audit (payroll price-parity with SimplePay, bookkeeper onboarding, consolidated billing, add-client flow) fall entirely outside Reports/Debtors/Creditors/AFS/tax scope. No open action items.

---

## 2. Reports

✓ No issues found.
- Dashboard (`payroll.py:1225-1274`): `total_revenue` sums only paid invoices via `_to_zar()` plus `_bank_import_income()`; `total_outstanding` sums `sent`/`overdue` invoices via `_to_zar()`. Expenses summed ex-VAT, separate from revenue.
- PO COGS uses delivered-value-only for partials (`_po_delivered_net`), no double-counting with payroll or depreciation.
- Payroll costs included in expenses via the payslip sum, applied after gross profit.
- Management accounts and `/v1/summary` (`main.py:446-491`) both route revenue/outstanding through `_to_zar()` and mirror the dashboard formula.

## 3. Debtors

✓ No issues found.
- Invoice status filter confirmed: `Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])` — paid invoices excluded.
- Aging cutoffs keyed off `due_date`, not invoice date (`payroll.py:1623-1643`, Rule 2 shown as example — same pattern used across all aging buckets).
- ZAR conversion via `_to_zar()` applied consistently, including per-item display amounts.

## 4. Creditors

✓ No issues found.
- Reversal-awareness (2026-07-13 fixes) confirmed present at all four call sites — every site nets `source IN ("purchase_order", "purchase_order_reversal")`.
- AP control (Rule 7, `payroll.py:1753-1799`) computes per-PO expected credit from `credit − debit` journal lines, falling back to `po.total_amount` only when no journal entry exists yet.
- Supplier bank details decrypted via `decrypt_field` (`suppliers.py:7,48-50`) — unchanged.

## 5. Cross-module consistency

✓ No issues found.
- Journal coverage complete: `post_invoice_raised`, `post_invoice_paid`, `post_invoice_cogs`, `post_expense`, `post_payroll`, `post_expense_paid`, `post_po_received`, `post_po_paid` — no gaps.
- Import-awareness (2026-07-11 fixes) intact: Rules 6/7 exclude `source == "import"` on 1100/2000 (`payroll.py:1736,1812`); balance sheet retains imported equity offsets 3998/3999. Non-ZAR invoice imports still require an exchange rate; unbalanced journal-import groups still rejected; both invoice and journal imports auto-run the backfill.
- Migration hygiene re-verified: `wear_and_tear_rate` column and `ALTER TABLE` still positioned inside the migrations list literal. The new `parent_company_id` (Company) and `user_type` (User) columns added this run are likewise correctly placed inside the same migrations list, not appended after the loop.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (declared in AFS meta). Statements: income statement, statement of financial position, changes in equity, cash flow (indirect), notes 2-9.

**Standards status (fresh web search this run):**
- **IFRS 18** *Presentation and Disclosure in Financial Statements* — still effective for annual periods beginning on/after 1 January 2027, not applicable to IFRS-for-SMEs preparers (ZuZan's basis). No change.
- **IFRS for SMEs third edition** (issued 27 February 2025, effective 1 January 2027, early adoption permitted) — no change to the substantive sections used by the existing transition plan. One new item surfaced this run: the IASB's May 2026 exposure draft proposing to **extend the consolidation exception for eligible SMEs**, open for comment until 9 September 2026 — not applicable to ZuZan, which produces single-entity AFS only (per `ifrs_smes_3rd_edition_transition_plan.md` §2.3). No code impact. `ifrs_smes_3rd_edition_transition_plan.md` remains current.
- VAT rate: reconfirmed 15% standard rate. Corporate income tax: 27% flat rate, unchanged.

**Section 5b — deferred tax: already implemented, re-verified this run:**
- Grepped `financial_statements.py` for `"deferred_tax": 0.0"` — no matches.
- Per-asset tax base = cost − cumulative SARS wear-and-tear allowance; temporary difference × `_CIT_RATE` (27%) drives the deferred tax balance (`_deferred_tax_balance()`, `financial_statements.py:131-173`). Read the full function body this run — logic unchanged: analytic carrying-value calc mirrors the fixed-asset register's own depreciation methods (straight-line and diminishing-balance), disposed assets excluded, unmappable categories floor the temporary difference at zero.
- Opening/closing balances drive `deferred_tax_expense` = closing − opening; Note 9 fields populated; `total_tax = tax_expense + deferred_tax_expense`; balance-sheet movement line present.
- Finance costs (2026-07-13 fix): interest presented below EBIT, tax/net profit derive from `profit_before_tax` — unchanged.

✓ No issues found.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date.

- Fresh web search this run: SARS's most recent public activity (7 August 2026 onward) is a draft Crypto Assets taxation guide (comment period to 31 Aug 2026, not applicable — ZuZan has no crypto handling), a VAT-deregistration call for school VAT vendors (not applicable), and Customs & Excise rule amendments under ss64E/120 (not applicable — no customs/excise logic in ZuZan). None affect PAYE brackets, rebates, UIF, SDL, VAT, or CIT.
- **2026 draft TLAB / TALAB:** comment period still runs to 28 August 2026, **not yet enacted** — same standing item as prior reports, no code impact yet.
- VAT confirmed 15% — matches `VAT_RATE = 0.15` in code (`payroll.py:1608, 2691`).
- CIT confirmed flat 27% — matches `_CIT_RATE` (`financial_statements.py:84`, fallback) and dashboard/management/provisional-tax usage.
- s11F retirement fund deduction cap R430,000 (`payroll.py:196`) — unchanged.
- UIF: 1% employee / 1% employer, ceiling R17,712 → max R177.12/month per party (`payroll.py:144`) — unchanged.
- SDL 1% of gross remuneration, R500,000 annual-payroll small-employer exemption — unchanged.
- Provisional `2027/2028` `TAX_YEARS` entry remains a placeholder copy of 2026/2027 pending the Feb 2027 Budget — standing reminder, not a defect.
- Rates unchanged and current tax year present — no edits made (report-only per task rules; section 5b already implemented, verification-only this run).
- **Note (unrelated to tax tables):** payroll pricing constants changed this run (`payroll.py:2866,2984`, `max(99, employees×34.00)` → `max(65, employees×18.25)`) — this is subscription pricing (SimplePay price-parity), not a SARS rate, and is out of scope for this checklist's tax-rate review; flagged for awareness only.

**Sources consulted:** [SARS Home](https://www.sars.gov.za/) · [SARS is coming after these taxpayers in 2026 — BusinessTech](https://businesstech.co.za/news/finance/865308/sars-is-coming-after-these-taxpayers-in-south-africa-in-2026/) · [SARS Tax Calendar 2026 — TaxTim](https://www.taxtim.com/za/tax-deadlines) · [SARS announces 2026 tax filing dates — IOL](https://iol.co.za/business/2026-06-03-sars-announces-2026-tax-filing-dates-and-here-is-what-is-different-this-time/) · [Changes for Filing Season 2026 — SARS](https://www.sars.gov.za/latest-news/changes-for-filing-season-2026/) · [Media Releases — SARS](https://www.sars.gov.za/media/media-releases/) · [IASB issues third edition of IFRS for SMEs — PwC Viewpoint](https://viewpoint.pwc.com/dt/gx/en/pwc/in_briefs/in_briefs_INT/in_briefs_INT/iasb-issues.html) · [IASB proposes extending consolidation exception for eligible SMEs — IFRS.org](https://www.ifrs.org/news-and-events/news/2026/05/iasb-proposes-extending-consolidation-exception-eligible-smes/) · [IFRS Standards Effective 2026 — Prima Consulting](https://primaconsulting.org/ifrs-changes-2026-update/) · [The IFRS for SMEs Accounting Standard — IFRS.org](https://www.ifrs.org/issued-standards/ifrs-for-smes/)

## 8. Action items

None. No open action items.

**Standing reminders (not defects, carried from prior reports):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry (`payroll.py:151+`) after Budget Feb 2027 and restart the backend;
(b) early-2027 runs should execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`);
(c) the AFS PayFast payment/ad-hoc tokenization feature and the `/reports/ai-insights` feature remain outside this audit's scope;
(d) NBCPSS private security payroll mode predates this audit's baseline, not yet part of this checklist's explicit scope;
(e) file-attribution note: the imported-equity-offset (3998/3999) exclusion logic lives in `payroll.py`'s `balance_sheet()`, not `financial_statements.py`;
(f) track the 2026 draft TLAB/TALAB (comment period closes 28 August 2026) — once enacted, re-check whether any finalized provisions require rate/table changes;
(g) the IASB's May 2026 consolidation-exception exposure draft (comment period closes 9 September 2026) is not applicable to ZuZan (single-entity AFS only) — awareness only, no action needed unless ZuZan later adds multi-entity consolidation;
(h) `parent_company_id`/`user_type` columns and the bookkeeper-onboarding/consolidated-billing/add-client features (new this run) remain outside Reports/Debtors/Creditors/AFS/tax scope, flagged for awareness only;
(i) payroll subscription pricing changed this run (`max(99,×34.00)` → `max(65,×18.25)`, `payroll.py:2866,2984`) — billing/pricing only, not a SARS rate, no action needed for this checklist.
