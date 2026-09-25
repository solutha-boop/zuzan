# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 25 September 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-09-23 (PASS)

**Change detection since last run:** `git log` shows one new commit since the 09-23 baseline (`795afc9`, 19 Sep 21:26): **`f480d17`** (23 Sep 12:52). `git diff --stat 795afc9 HEAD` shows this commit touched only `LAUNCH_READINESS_2026-07-14.md`, three prior audit-report markdown files, and `zuzan-backend/test_payroll_journal_balance.py` — i.e. it committed previously-untracked documentation/test files into git. **Zero changes to any in-scope application file** (`App_js_fixed.js`, `payroll.py`, `main.py`, `journal.py`, `database.py`, `financial_statements.py`, `purchase_orders.py`, `csv_import.py`, `companies.py`, `suppliers.py`, `customers.py`).

Because in-scope code is byte-identical to the fully-verified 09-23 state, this run re-verified the checklist with fresh `Grep`/`Read` passes against every line reference cited in the 09-23 report (not diff-trust), confirming each still resolves to the same logic at the same line numbers — see §2–§6. External inputs (IFRS standards status, VAT Act litigation, SARS rates) were independently re-searched this run per §6–§7, since those can change without any code commit.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ✅ PASS |
| Debtors (AR) | ✅ PASS |
| Creditors (AP) | ✅ PASS |
| Cross-module consistency | ✅ PASS |
| IFRS compliance (AFS) | ✅ PASS — no standards changes since 09-23; deferred tax (5b) unchanged and re-verified |
| Tax updates (SARS) | ✅ PASS — 2026/2027 tables current, no rate changes |

**Overall: PASS.** No application-code changes since the 09-23 report; no regressions. Fresh web searches this run confirm no external change to IFRS effective dates, the VAT Act s7(4) Constitutional Court matter (still no judgment issued), or SARS rates. Two repo-hygiene action items from 09-23 are now resolved (see §8).

## 2. Reports

✓ No issues found.

- `payroll.py` `/reports/dashboard` (`:1648-1739`): `total_revenue` (`:1661`) sums only `InvoiceStatus.paid` invoices via `_to_zar()` plus bank-import income (`:1663`); `total_outstanding` (`:1669`) covers `sent`+`overdue` via `_to_zar()`; expenses (ex-VAT, `:1675`) and PO COGS (`:1684`, via `_po_delivered_net()` — delivered-value only, no double count) roll into `total_expenses`, never into revenue; payroll cost (`Payslip.total_cost`, `:1699-1709`) is a separate expense line added after gross profit (`:1712`), never omitted or double-counted; a structural duplicate-expense/PO warning (`:1736+`) further guards against double-posting.
- `/reports/management` revenue trend loop applies `_to_zar()` on every iteration (`:2986`) — consistent methodology.
- `main.py` `/v1/summary` (`:466-511`): applies `_to_zar()` for both `total_revenue` (`:473-474`, including bank-import income) and `outstanding` (`:503`); expense/PO/depreciation/payroll treatment mirrors `/reports/dashboard` exactly (`:475-502`).
- `_to_zar()` usage re-grepped across `payroll.py` and `main.py` (18+ call sites: dashboard, management, debtors/creditors-aging, cash-flow, provisional-tax estimate, VAT201, YTD revenue) — all consistent, no bypass found.

## 3. Debtors

✓ No issues found.

- `/reports/debtors-aging` (`payroll.py:3251-3311`): filtered to `Invoice.status.in_([sent, overdue])` (`:3262`) — paid invoices excluded.
- ZAR equivalents shown via `_to_zar()` (`:3274`).
- Aged from `due_date` only (`:3270`, explicit design — invoices without a `due_date` fall into a `not_due` bucket, `:3279-3281`, avoiding false overstatement of overdue balances).
- Buckets: `not_due`, `current`, `31_60`, `61_90`, `over_90` — correctly bounded (`:3286-3294`).
- Frontend Debtors component consumes `/reports/debtors-aging` directly (file unchanged since 09-23), no independent recomputation.

## 4. Creditors

✓ No issues found.

- `/reports/creditors-aging` (`payroll.py:3314-3421`): sources outstanding POs (`status IN (received, partial)`, `:3332`; fully paid POs excluded) aged from `received_date + supplier.payment_terms` (`:3378-3379`).
- Reversal-awareness (2026-07-13 fix) confirmed present and unchanged, now verified at **five** independent call sites, one more than previously spot-checked: `payroll.py` Rule 7 (`:2202`), `payroll.py` creditors-aging (`:3350`), the per-PO AP lookup (`:2674`), `purchase_orders.py` `pay_po` (`:445`), and `financial_statements.py`'s AP-reconciliation query (`:558`) — all net `credit − debit` and include `source.in_(["purchase_order", "purchase_order_reversal"])`. `journal.py`'s backfill also carries the same filter (`:1158`).
- Supplier bank details decrypted via `decrypt_field()` (`payroll.py:3393-3395`, `bank_name`/`account_number`/`branch_code`) before display.
- Per-PO AP amount uses actual journal-posted credits (`po_ap_amounts`, `:3339-3358`), falling back to `po.total_amount` only when no journal entry exists yet (`:3405`).

## 5. Cross-module consistency

✓ No issues found.

- Journal coverage confirmed for all required transaction types in `journal.py`: `post_invoice_paid` (`:371`), `post_payroll` (`:505`), `post_expense_paid` (`:757`), `post_po_received` (`:786`), `post_po_paid` (`:838`) — no gaps.
- Balance sheet control-account reconciliation: Rule 6 (AR/1100, `payroll.py:2160`) and Rule 7 (AP/2000, `payroll.py:2236`) both exclude `source == "import"` lines from the comparison.
- Import-awareness (2026-07-11 fixes) confirmed intact in `csv_import.py`: exchange rate is read from the import row rather than hard-coded (`:458-487`); unbalanced journal-import groups are rejected with an explicit error (`:1035-1077`); imported lines are tagged `source="import"` consistently (`:791, 869, 957, 1077`).
- Imported equity/asset/liability offsets (3998/3999) confirmed still present in `payroll.py`'s `balance_sheet()` (`:1961-1970`), not in `financial_statements.py` (standing note (e) from prior reports).

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (per `financial_statements.py`'s `meta.basis` field). File is byte-identical to the 09-23 baseline (confirmed via `git diff`, zero changes).

**Standards status (fresh web search this run, 25 September 2026):** no change since 09-23.
- **IFRS 18** *Presentation and Disclosure in Financial Statements* — still effective for annual periods beginning on/after 1 January 2027, early application permitted. Not yet applicable to IFRS-for-SMEs preparers such as ZuZan's target companies.
- **IFRS for SMEs third edition** (issued Feb 2025) — still effective 1 January 2027. The related consolidation-exception consultation closed for comment 9 September 2026 as scheduled; a September 2026 IFRS for SMEs Accounting Standard Update is now published (IASB decisions/agenda items) but contains no new effective-date or ZuZan-relevant scope change. No immediate code impact — remains flagged for the early-2027 transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`).
- **VAT Act s7(4) Constitutional Court case** — still no judgment issued as of this run (heard 27 August 2026, reserved judgment). No code impact.

**Section 5b — deferred tax:** already implemented (not hard-coded to 0.0); re-verified at the code level this run, including the balance-sheet offset mechanics not previously walked line-by-line:
- `_deferred_tax_balance()` (`financial_statements.py:131-173`, unchanged): tax base = cost minus cumulative SARS wear-and-tear allowance (rate priority: explicit `wear_and_tear_rate` → `sars_category`/IN47 table → category-name heuristic → unmappable fallback to carrying value, giving zero temporary difference), apportioned monthly from purchase date, floored at 0; temporary difference × 27% (`_CIT_RATE`) gives the balance.
- `FixedAsset.wear_and_tear_rate` column (`database.py:543`) and its `ALTER TABLE` migration (`database.py:1507`) confirmed present and correctly placed inside the migrations list literal alongside ~20 other `ALTER TABLE` strings (not dead code after a loop).
- Deferred tax expense = closing balance − opening balance (`financial_statements.py:266-268`); Note 9 shows `deferred_tax` (period movement) and `total_tax` = current + deferred (`:601, 606`).
- Balance sheet presentation (`financial_statements.py:312-328`): a positive closing balance adds a "Deferred Tax Liability" (code `2600`) non-current-liability line and reduces retained earnings by the same amount (`:315-321`); a negative balance instead adds a "Deferred Tax Asset" (code `1900`) non-current-asset line with the same retained-earnings offset (`:322-328`) — Assets = Equity + Liabilities holds in both cases, confirmed algebraically from the code (no journal posting is made, consistent with the "computed AFS line" design). The statement of changes in equity also carries the opening deferred-tax adjustment (`:346-349`) so opening/closing equity reconcile against the balance sheet.
- Safety case unchanged: with no fixed assets, `_deferred_tax_balance()` returns exactly `0.0` and neither balance-sheet branch fires.

Finance costs (2026-07-13 fix): confirmed unchanged — interest lines (account `6700` or name-matched) presented below EBIT (`financial_statements.py:204-211`); `profit_before_tax = ebit - finance_costs` (`:259`); `tax_expense` and `net_profit` both derive from `profit_before_tax`, not EBIT.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date.

**PAYE brackets, rebates, UIF ceiling** — fresh web search this run finds no rate-change news since 09-23; code re-confirmed (`payroll.py:101-190`):
- `TAX_YEARS["2026/2027"]` (`:132-151`) present with the 7-bracket table (18% to R245,100 … 45% above R1,878,600), reflecting the Budget 2026 3.4% inflationary adjustment.
- Primary/secondary/tertiary rebates and UIF earnings ceiling (R17,712/month) unchanged in code.
- UIF 1%/1% (`UIF_RATE = 0.01`, `:189`) and SDL 1% (`SDL_RATE = 0.01`, `:190`) — no rate-change news found.

**Company tax:**
- CIT remains flat 27% — `CORP_TAX_RATE = 0.27` (`payroll.py:3151`, used in the provisional-tax estimate `:3210`) and `financial_statements.py`'s `_CIT_RATE` both confirmed unchanged.
- VAT standard rate confirmed unchanged at 15% across all three code sites (`payroll.py:2032, 2426, 3507`) — the previously-legislated escalation to 15.5%/16% remains withdrawn; fresh search confirms Treasury withdrew the proposed R20bn 2026/27 tax increase package due to improved fiscal metrics, with no VAT-rate change enacted.
- No new SARS threshold or rate change found this run.

**Provisional tax (2027/2028 placeholder):** `TAX_YEARS["2027/2028"]` (`payroll.py:152-167`) remains a flagged (`"provisional": True`) copy of 2026/2027 — standing reminder to replace after Budget Feb 2027 remains valid.

No edits made to tax tables this run (report-only, as instructed; §5b remained verification-only since already implemented).

**Sources consulted:** [Big VAT changes on the cards for South Africa – BusinessTech](https://businesstech.co.za/news/government/872697/big-vat-changes-on-the-cards-for-south-africa/) · [DA's ConCourt hearing against VAT Act underway — Polity](https://www.polity.org.za/article/das-concourt-hearing-against-vat-act-underway-2026-08-27) · [High Court: Minister's power to set VAT rate is unconstitutional — Moonstone](https://www.moonstone.co.za/high-court-ministers-power-to-set-vat-rate-is-unconstitutional/) · [List of judgments of the Constitutional Court of South Africa delivered in 2026 — Wikipedia](https://en.wikipedia.org/wiki/List_of_judgments_of_the_Constitutional_Court_of_South_Africa_delivered_in_2026) · [IASB proposes extending consolidation exception for eligible SMEs — IFRS.org](https://www.ifrs.org/news-and-events/news/2026/05/iasb-proposes-extending-consolidation-exception-eligible-smes/) · [September 2026 IFRS for SMEs Accounting Standard Update available — BDO](https://www.bdo.global/en-gb/news/ifrs-news/september-2026-ifrs-for-smes-accounting-standard-update-available) · [South Africa's tax changes in 2026: What SARS is really watching — Joburg ETC](https://www.joburgetc.com/business/south-africa-tax-changes-2026/) · [Income tax brackets, medical tax credits adjusted for inflation — Moonstone](https://www.moonstone.co.za/income-tax-brackets-medical-tax-credits-adjusted-for-inflation/) · [Budget 2026 Frequently Asked Questions — SARS](https://www.sars.gov.za/about/sars-tax-and-customs-system/budget/budget-2026-frequently-asked-questions/)

## 8. Action items

1. **Medium (carried over unchanged from 09-23):** the frontend's `DEFAULT_COA`/`journal.py` code-mismatch is fixed for the collision component (renumbered to `5010`-`5050`) and mitigated by the auto-vivify fallback for new codes. Residual risk: `Expense.category` strings posted under the *old* routing (pre-2026-09-18) remain wrongly classified in the ledger and are not retroactively reposted — still recommend a one-off reconciliation pass over historical expense postings.
2. **Low (repo hygiene, unchanged this run — user action still needed):** `zuzan-backend/` still has the same **four** `.fuse_hidden*` files (`0000000c00000001`–`...04`, dated 14 & 21 Sep — no new ones since 09-23). These are stale FUSE mount artifacts, not application data. **User action:** delete manually via Windows Explorer, closing whatever process has them locked if deletion is refused there too.
3. **Resolved this run:** `LAUNCH_READINESS_2026-07-14.md` is now tracked in git (committed in `f480d17`, 23 Sep). Closes the prior "repo clutter" action item — no further action needed.
4. **Resolved this run:** `zuzan-backend/test_payroll_journal_balance.py` (the audit's own regression test) is now tracked in git (committed in `f480d17`, 23 Sep). Closes the prior "process" action item — the regression check now survives a fresh checkout.
5. **Low (data freshness, standing):** MIBCO Sector 5 Year 2 employee health-scheme contribution remains officially "TBC" industry-wide — not re-searched this run since no payroll/MIBCO code changed; re-check on the next run that specifically touches payroll/MIBCO logic, or at minimum monthly.

**No new Critical/High findings this run.** Two Low items closed (repo hygiene items 3 and 4 above); no severity changes otherwise.

**Standing reminders (carried from prior reports, unchanged unless noted):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry after Budget Feb 2027 and restart the backend;
(b) early-2027 runs should execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`), including the amendments-consultation that closed 9 September 2026;
(c) the AFS PayFast payment/ad-hoc tokenization feature and `/reports/ai-insights` remain outside this audit's scope;
(d) NBCPSS/MIBCO payroll calculation detail remains outside this checklist's explicit scope except where it produces an in-scope journal-integrity failure;
(e) the imported-equity-offset (3998/3999) exclusion logic lives in `payroll.py`'s `balance_sheet()`, not `financial_statements.py`;
(f) next run should keep checking for the outcome of Treasury/SARS's review of the 2026 draft TLAB/TALAB submissions and its introduction in Parliament;
(g) `parent_company_id`/`user_type`, bookkeeper-onboarding, consolidated-billing, accountant-fee-structure, and accountant-practice-dashboard/`billing_exempt` features remain outside scope, awareness only;
(h) provisional tax modelling (13-week cash flow) — implemented 09-20; monitor the estimate's accuracy against real company data once available;
(i) compulsory VAT-registration turnover threshold is R2,300,000 (voluntary R120,000), effective 1 April 2026 — not gated anywhere in-scope, awareness only;
(j) the persistent Chart of Accounts feature (`/coa` router) custom-account routing gap is closed; the broader DEFAULT_COA/journal code-mismatch is Medium per action item 1;
(k) the invoice header-image upload, custom HTML invoice template, and service-item catalogue remain additive presentation/picklist features outside scope;
(l) the IASB's SME consolidation-exception Exposure Draft comment period closed 9 September 2026 as scheduled; a September 2026 IFRS for SMEs Standard Update has since been published with no new ZuZan-relevant change — check again next run for the IASB's post-consultation decision;
(m) the Constitutional Court has reserved judgment (heard 27 August 2026) on Section 7(4) of the VAT Act; still no ruling as of this run — monitor;
(n) the `/integrations/invoice` (SMT) endpoint remains formally in-scope going forward — spot-check with a real create + re-post cycle once real SMT traffic exists;
(o) `POST /accountant/sync-customers` remains tracked given its proximity to Debtors scope;
(p) the employee time-clock system (`clock.html`, `clocking.py`) remains additive with no journal/AR/AP/Reports touchpoints, awareness only unless a future OT-import path from clocking data feeds payroll without validation;
(q) mass payslip ZIP download remains a read-only export feature with no journal/AR/AP/Reports touchpoints — awareness only;
(r) the CGT annual exclusion increase (R40,000 → R50,000, Budget 2026) is a personal-tax item outside this checklist's company/payroll-tax scope; no code reference expected, awareness only.
