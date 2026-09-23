# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 21 September 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-09-20 (PASS)

**Change detection since last run:** `git log`/`git status -sb` show local `main` == `origin/main`, still at **`795afc9`** (19 Sep 21:26) — **zero commits since the 09-20 report's baseline.** `git diff --stat 795afc9 HEAD` is empty (HEAD *is* 795afc9). All in-scope files (`App_js_fixed.js`, `payroll.py`, `main.py`, `journal.py`, `database.py`, `financial_statements.py`, `purchase_orders.py`, `csv_import.py`, `companies.py`, `suppliers.py`, `customers.py`) are byte-identical to the fully-verified 09-20 state.

Because there is no code drift, this run re-verified the checklist with fresh `Grep`/`Read` passes (not diff-trust, and not a copy of yesterday's conclusions) against every line reference cited in the 09-20 report, confirming each still resolves to the same logic at the same line numbers — see §2–§6. External inputs (IFRS standards status, SARS rates) were independently re-searched this run per §6–§7, since those can change without any code commit.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ✅ PASS |
| Debtors (AR) | ✅ PASS |
| Creditors (AP) | ✅ PASS |
| Cross-module consistency | ✅ PASS |
| IFRS compliance (AFS) | ✅ PASS — no standards changes since 09-20; deferred tax (5b) unchanged and re-verified |
| Tax updates (SARS) | ✅ PASS — 2026/2027 tables current, no rate changes |

**Overall: PASS.** No code changes since the 09-20 report; no regressions. Fresh web searches this run confirm no external change to IFRS effective dates, the VAT Act s7(4) Constitutional Court matter (still reserved judgment), or SARS rates. All action items carry over unchanged from 09-20 except where noted in §8.

## 2. Reports

✓ No issues found.

- `payroll.py` `/reports/dashboard` (`:1648-1739` region): `total_revenue` (`:1661`) sums only `InvoiceStatus.paid` invoices via `_to_zar()` plus bank-import income (`:1663`); `total_outstanding` (`:1669`) covers `sent`+`overdue` via `_to_zar()`; expenses and PO COGS (via `_po_delivered_net()`, delivered-value only — no double count) roll into `total_expenses`, not revenue; payroll cost (`Payslip.total_cost`) is a separate expense line, never omitted or double-counted.
- `/reports/management` (`:2894-3031` region): revenue trend loop applies `_to_zar()` on every iteration (`:2986`) — consistent methodology.
- `main.py` `/v1/summary` (`:469-503`): applies `_to_zar()` for both `total_revenue` (`:473-474`, including bank-import income) and `outstanding` (`:503`).
- `_to_zar()` usage re-grepped across `payroll.py` and `main.py` — all ~19 call sites (dashboard, management, debtors/creditors-aging, cash-flow, provisional-tax estimate, VAT201, YTD revenue, etc.) consistent, no bypass found.

## 3. Debtors

✓ No issues found.

- `/reports/debtors-aging` (`payroll.py:3251-3252`): filtered to `Invoice.status.in_([sent, overdue])` — paid invoices excluded.
- ZAR equivalents shown via `_to_zar()`.
- Aged from `due_date` only (explicit design choice, commented in code — invoices without a `due_date` fall into a `not_due` bucket).
- Buckets: `not_due`, `current`, `31_60`, `61_90`, `over_90` — correctly bounded.
- Frontend `Debtors` component consumes `/reports/debtors-aging` directly, no independent recomputation.

## 4. Creditors

✓ No issues found.

- `/reports/creditors-aging` (`payroll.py:3314-3315`): sources outstanding POs (fully paid POs excluded) and unpaid on-credit expenses.
- Reversal-awareness (2026-07-13 fix) confirmed present and unchanged: `payroll.py` Rule 7 (`:2187-2204`), `payroll.py` creditors-aging (`:3343-3352`), and the mirrored per-PO AP lookup (`:2656-2674`) — all net `credit − debit` and include `source.in_(["purchase_order", "purchase_order_reversal"])`.
- Supplier bank details decrypted via `decrypt_field()` before display.
- Per-PO AP amount uses actual journal-posted credits, falling back to `po.total_amount` only when no journal entry exists.

## 5. Cross-module consistency

✓ No issues found.

- Journal coverage confirmed for all required transaction types in `journal.py`: invoice payments, expense payments, PO receipts, PO payments, payroll runs — no gaps (unchanged from 09-20, re-spot-checked).
- Balance sheet control-account reconciliation: Rule 6 (AR/1100) and Rule 7 (AP/2000) both exclude `source == "import"` lines from the comparison.
- Import-awareness (2026-07-11 fixes) confirmed intact in `csv_import.py`: auto-backfill runs after invoice/expense imports; non-ZAR invoice imports without an exchange rate are rejected; unbalanced journal-import groups are rejected.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (per `financial_statements.py`'s `meta.basis` field). File is byte-identical to the 09-20 baseline (confirmed via `git diff`, zero changes).

**Standards status (fresh web search this run, 21 September 2026):** no change since 09-20.
- **IFRS 18** *Presentation and Disclosure in Financial Statements* — still effective for annual periods beginning on/after 1 January 2027, early application permitted. Not yet applicable to IFRS-for-SMEs preparers such as ZuZan's target companies.
- **IFRS for SMEs third edition** (issued Feb 2025) — still effective 1 January 2027; IASB modules continuing to be published through Q3 2026 on schedule.
- **VAT Act s7(4) Constitutional Court case** — still reserved judgment (heard 27 August 2026); no ruling issued as of this run (late September 2026). No code impact.

**Section 5b — deferred tax:** already implemented (not hard-coded to 0.0); re-verified at the code level this run with a fresh read of the computation:
- `_deferred_tax_balance()` (`financial_statements.py:131-173`): tax base = cost minus cumulative SARS wear-and-tear allowance (rate priority: explicit `wear_and_tear_rate` → `sars_category`/IN47 table → category-name heuristic → unmappable fallback to carrying value, giving zero temporary difference), apportioned monthly from purchase date, floored at 0; temporary difference × 27% (`_CIT_RATE`) gives the balance; disposed assets are excluded from the as-at balance.
- `FixedAsset.wear_and_tear_rate` column (`database.py:543`) and its `ALTER TABLE` migration (`database.py:1507`) confirmed present and correctly placed inside the migrations list literal (not dead code after the loop).
- Deferred tax expense = closing balance − opening balance (`:266-268`); Note 9 shows `deferred_tax` (period movement) and `total_tax` = current + deferred (`:601-608`).
- Balance sheet: closing balance added as a non-current liability (`Deferred Tax Liability`, code `2600`) or asset (`Deferred Tax Asset`, code `1900`) line (`:312-324`), with a matching equity offset — Assets = Equity + Liabilities still holds.
- Safety case unchanged: with no fixed assets, `_deferred_tax_balance()` returns exactly `0.0`.

Finance costs (2026-07-13 fix): confirmed unchanged — interest lines (account `6700` or name-matched) presented below EBIT (`:205-211`); `profit_before_tax = ebit - finance_costs` (`:259`); `tax_expense` and `net_profit` both derive from `profit_before_tax`, not EBIT.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date; `_current_tax_year()` (`payroll.py:170-181`) correctly derives and selects it.

**PAYE brackets, rebates, UIF ceiling** — fresh web search this run reconfirms all current code values (`payroll.py:132-146`):
- 7-bracket table (18% to R245,100 … 45% above R1,878,600) ✓ matches code — Budget 2026 applied a 3.4% inflationary adjustment to brackets, the first since 2023/24.
- Primary rebate R17,820, secondary R9,765, tertiary R3,249 ✓ matches code.
- UIF earnings ceiling R17,712/month ✓ matches code (`uif_ceil: 17712`).
- UIF 1%/1% (`UIF_RATE = 0.01`) and SDL 1% (`SDL_RATE = 0.01`) — no rate-change news found.

**Company tax:**
- CIT remains flat 27% for years of assessment 1 April 2026 – 31 March 2027 — confirmed unchanged, Budget 2026 announced no change. Code usage consistent (`CORP_TAX_RATE = 0.27`, `payroll.py:3151`; `financial_statements.py`'s `_CIT_RATE`, fallback 0.27).
- VAT standard rate confirmed unchanged at 15% through 2026 — the previously-legislated escalation to 15.5%/16% remains withdrawn (Budget 2026 dropped the proposed R20bn tax-increase package given improved fiscal metrics). Code usage consistent (`VAT_RATE = 0.15` at `payroll.py:2032, 2426, 3507`).
- Compulsory VAT registration threshold confirmed R2,300,000 (raised from R1m, voluntary R120,000), effective 1 April 2026 — not gated anywhere in-scope; awareness only, unchanged.
- CGT annual exclusion increased R40,000 → R50,000 (Budget 2026) — outside payroll/company-tax scope of this checklist (personal CGT), noted for awareness only; no code reference found or expected.

**Provisional tax (2027/2028 placeholder):** `TAX_YEARS["2027/2028"]` (`payroll.py:152-167`) remains a flagged (`"provisional": True`) copy of 2026/2027 — standing reminder to replace after Budget Feb 2027 remains valid.

No edits made to tax tables this run (report-only, as instructed; §5b remained verification-only since already implemented).

**Sources consulted:** [IFRS - June 2026 IFRS for SMEs Accounting Standard Update](https://www.ifrs.org/supporting-implementation/2015-ifrs-for-smes-supporting-materials/sme-updates/2026/june-2026-ifrs-for-smes-accounting-standard-update/) · [IASB issues third edition of the IFRS for SMEs — PwC Viewpoint](https://viewpoint.pwc.com/dt/gx/en/pwc/in_briefs/in_briefs_INT/in_briefs_INT/iasb-issues.html) · [IFRS 18 and the Updated IFRS for SMEs Standard — Grant Thornton](https://www.grantthornton-bq.com/publications/bonaire/ifrs-update/) · [VAT Act section declared invalid — The Citizen](https://www.citizen.co.za/news/south-africa/courts/vat-act-section-declared-invalid-unconstitutional/) · [Sars and Treasury ask top court to overturn ruling on minister's VAT powers — Business Day](https://www.businessday.co.za/news/2026-08-28-sars-and-treasury-ask-top-court-to-overturn-ruling-on-ministers-vat-powers/) · [Budget 2026 Frequently Asked Questions — SARS](https://www.sars.gov.za/about/sars-tax-and-customs-system/budget/budget-2026-frequently-asked-questions/) · [Budget Speech 2026/2027: Tax Overview — Werksmans Attorneys](https://werksmans.com/budget-speech-2026-2027-tax-overview/) · [Budget 2026: a small win for taxpayers — TaxTim](https://www.taxtim.com/za/blog/budget-2026) · [Income tax brackets, medical tax credits adjusted for inflation — Moonstone](https://www.moonstone.co.za/income-tax-brackets-medical-tax-credits-adjusted-for-inflation/)

## 8. Action items

1. **Medium (carried over unchanged from 09-20):** the frontend's `DEFAULT_COA`/`journal.py` code-mismatch is fixed for the collision component (renumbered to `5010`-`5050`) and mitigated by the auto-vivify fallback for new codes. Residual risk: `Expense.category` strings posted under the *old* routing (pre-2026-09-18) remain wrongly classified in the ledger and are not retroactively reposted — still recommend a one-off reconciliation pass over historical expense postings.
2. **Low (repo hygiene, carried over — user action needed):** `zuzan-backend/.fuse_hidden0000000c00000001` and `...02` are still present on disk (unchanged since 14 Sep). **User action:** delete manually via Windows Explorer, closing whatever process has them locked if deletion is refused there too.
3. **Low (repo clutter, carried over — decision needed):** `LAUNCH_READINESS_2026-07-14.md` remains untracked in the project root. Still a user judgment call (commit as historical record vs. delete).
4. **Low (process, carried over):** `zuzan-backend/test_payroll_journal_balance.py` (the audit's own regression test) remains untracked in git. Recommend committing it so the standing regression check survives a fresh checkout.
5. **Low (data freshness, standing):** MIBCO Sector 5 Year 2 employee health-scheme contribution remains officially "TBC" industry-wide — not re-searched this run since no payroll/MIBCO code changed; re-check on the next run that specifically touches payroll/MIBCO logic, or at minimum monthly.

**No new Critical/High findings this run. No severity changes from 09-20** — this was a zero-code-change day; all movement is in the standing reminders below (none required updating either).

**Standing reminders (carried from prior reports, unchanged unless noted):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry after Budget Feb 2027 and restart the backend;
(b) early-2027 runs should execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`);
(c) the AFS PayFast payment/ad-hoc tokenization feature and `/reports/ai-insights` remain outside this audit's scope;
(d) NBCPSS/MIBCO payroll calculation detail remains outside this checklist's explicit scope except where it produces an in-scope journal-integrity failure;
(e) the imported-equity-offset (3998/3999) exclusion logic lives in `payroll.py`'s `balance_sheet()`, not `financial_statements.py`;
(f) next run should keep checking for the outcome of Treasury/SARS's review of the 2026 draft TLAB/TALAB submissions and its introduction in Parliament;
(g) `parent_company_id`/`user_type`, bookkeeper-onboarding, consolidated-billing, accountant-fee-structure, and accountant-practice-dashboard/`billing_exempt` features remain outside scope, awareness only;
(h) provisional tax modelling (13-week cash flow) — implemented 09-20; monitor the estimate's accuracy against real company data once available;
(i) compulsory VAT-registration turnover threshold is R2,300,000 (voluntary R120,000), effective 1 April 2026 — not gated anywhere in-scope, awareness only;
(j) the persistent Chart of Accounts feature (`/coa` router) custom-account routing gap is closed; the broader DEFAULT_COA/journal code-mismatch is Medium per action item 1;
(k) the invoice header-image upload, custom HTML invoice template, and service-item catalogue remain additive presentation/picklist features outside scope;
(l) the IASB's SME consolidation-exception Exposure Draft comment period closed 9 September 2026 as scheduled; check for a post-close update on subsequent runs;
(m) the Constitutional Court has reserved judgment (heard 27 August 2026) on Section 7(4) of the VAT Act; still no ruling as of this run — monitor;
(n) the `/integrations/invoice` (SMT) endpoint remains formally in-scope going forward — spot-check with a real create + re-post cycle once real SMT traffic exists;
(o) `POST /accountant/sync-customers` remains tracked given its proximity to Debtors scope;
(p) the employee time-clock system (`clock.html`, `clocking.py`) remains additive with no journal/AR/AP/Reports touchpoints, awareness only unless a future OT-import path from clocking data feeds payroll without validation;
(q) mass payslip ZIP download remains a read-only export feature with no journal/AR/AP/Reports touchpoints — awareness only;
(r) new this run — the CGT annual exclusion increase (R40,000 → R50,000, Budget 2026) is a personal-tax item outside this checklist's company/payroll-tax scope; no code reference expected, awareness only.
