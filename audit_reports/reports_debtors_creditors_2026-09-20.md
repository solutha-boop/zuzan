# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 20 September 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-09-19 (PASS)

**Change detection since last run:** `git log`/`git status -sb` show local `main` == `origin/main`, now at **`795afc9`** (19 Sep 21:26), four commits ahead of the 09-19 report's baseline (`f6415e7`, 17 Sep 20:41). `git diff --stat f6415e7 HEAD` confirms the only in-scope files touched are `App_js_fixed.js`, `zuzan-backend/database.py`, `zuzan-backend/journal.py`, and `zuzan-backend/payroll.py`; `financial_statements.py`, `purchase_orders.py`, `main.py`, `csv_import.py`, `companies.py`, `suppliers.py`, and `customers.py` are byte-identical to 09-19.

Reviewed each diff line-by-line rather than diff-trusting the commit messages (which are stale copy-paste text describing a larger feature landed earlier):

1. **`journal.py` (+88 lines) and `App_js_fixed.js` (COA section, +6/-5):** the custom-`/coa`-account journal sync described as "uncommitted" in the 09-18/09-19 reports is now committed, plus a **new** fix (dated 2026-09-19 in-code): the frontend's `DEFAULT_COA` codes `5110`–`5150` ("Purchases", "Freight and Delivery", "Import Duties", "Direct Labour", "Direct Materials") silently collided with unrelated `journal.py` `DEFAULT_ACCOUNTS` entries of the same codes (Payroll Levies, Pension, Medical Aid, NBCPSS, MIBCO employer contributions) — e.g. selecting "5110 - Purchases" posted to "Payroll Levies (UIF/SDL)". Fixed by renumbering the DEFAULT_COA entries to the free `5010`–`5050` range (`App_js_fixed.js`) and by auto-vivifying any other unmatched code+name pair as a new expense account on first posting instead of silently falling back to 5900 (`journal.py:237-286`). Verified: `journal.py`'s `DEFAULT_ACCOUNTS` has no `5010`–`5050` entries, so the new range is collision-free. This **resolves the collision component** of the standing High-severity action item (DEFAULT_COA/journal mismatch) from 09-18/09-19; the broader "codes mostly disjoint from the ledger" issue is now also mitigated by the auto-vivify fallback (a selected account is created and used as named, rather than silently miscategorised) — downgrading, not fully closing, that action item (see §8).
2. **`payroll.py` (+139 lines), `App_js_fixed.js` (Budgeting section, +3 lines):** new `_annual_tax_estimate()` / `_provisional_tax_due()` helpers add a projected provisional tax (IRP6) line to the existing `/reports/cash-flow-13week` 13-week forecast, plus a matching frontend row/CSV column. This is the "action item 6" cash-flow enhancement flagged as pending in earlier reports (now implemented). It is **outside the Reports dashboard/management/AR/AP checklist** (a forward-looking liquidity projection, not a ledger or AR/AP figure) — confirmed it does not touch `total_revenue`, `total_outstanding`, `total_expenses`, debtors/creditors-aging, or any `_to_zar()` call site. One cosmetic comment update to the MIBCO Year-2 employee-scheme-rate TBC note, no functional change.
3. **`database.py` (+7 lines):** retrofits `ON DELETE CASCADE` onto the `journal_lines.entry_id` foreign key via an `ALTER TABLE ... DROP CONSTRAINT` / `ADD CONSTRAINT` pair, fixing a Sentry-reported `ForeignKeyViolation` when deleting a `JournalEntry` before its lines. Correctly placed inside the migrations list literal. No impact on Reports/Debtors/Creditors/AFS logic — a referential-integrity hardening fix only.

Because these changes are additive/adjacent rather than modifications to the audited totals, this run re-verified the full checklist directly against current source (fresh `Read`/`Grep`, not diff-trust) rather than assuming no regression.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ✅ PASS |
| Debtors (AR) | ✅ PASS |
| Creditors (AP) | ✅ PASS |
| Cross-module consistency | ✅ PASS |
| IFRS compliance (AFS) | ✅ PASS — no standards changes since 09-19; deferred tax (5b) unchanged and re-verified |
| Tax updates (SARS) | ✅ PASS — 2026/2027 tables current, no rate changes |

**Overall: PASS.** No regressions. Two new in-scope-adjacent fixes landed since 09-19 (COA collision renumbering + auto-vivify fallback; provisional-tax cash-flow projection) — both reviewed and confirmed correct. The DEFAULT_COA/journal mismatch action item is downgraded from High to Medium (collision resolved; broader reconciliation still recommended). Other carried-over items (repo hygiene, uncommitted-file risk — now reduced since three of the four previously-uncommitted files are committed) are updated below.

## 2. Reports

✓ No issues found.

- `payroll.py` `/reports/dashboard` (`:1648-1739` region): `total_revenue` (`:1661`) sums only `InvoiceStatus.paid` invoices via `_to_zar()` plus bank-import income (`:1663`); `total_outstanding` (`:1669`) covers `sent`+`overdue` via `_to_zar()`; expenses and PO COGS (via `_po_delivered_net()`, delivered-value only — no double count) roll into `total_expenses`, not revenue; payroll cost (`Payslip.total_cost`) is a separate line reducing gross profit to net profit — correctly included as an expense, never omitted or double-counted.
- `/reports/management` (`:2894-3031` region): revenue trend loop applies `_to_zar()` on every iteration (`:2986`) — consistent methodology.
- `main.py` `/v1/summary` (`:469-503`): imports and applies `_to_zar()` for both `total_revenue` (`:473`) and `outstanding` (`:503`).
- `_to_zar()` is used consistently at all 17 call sites across `payroll.py` and `main.py` (dashboard, management, debtors/creditors-aging, cash-flow, provisional-tax estimate, VAT201, etc.) — grepped and spot-checked, no bypass found.

## 3. Debtors

✓ No issues found.

- `/reports/debtors-aging` (`payroll.py:3252+`): filtered to `Invoice.status.in_([sent, overdue])` (`:3262`) — paid invoices excluded.
- ZAR equivalents shown via `_to_zar()`.
- Aged from `due_date` only (`:3268-3275`, explicit design choice, commented in code — invoices without a `due_date` fall into a `not_due` bucket rather than being aged from `issue_date`).
- Buckets: `not_due`, `current`, `31_60`, `61_90`, `over_90` — correctly bounded.
- Frontend `Debtors` component consumes `/reports/debtors-aging` directly, no independent recomputation.

## 4. Creditors

✓ No issues found.

- `/reports/creditors-aging` (`payroll.py:3315+`): sources outstanding POs (`status in (received, partial)`, `:3332` — fully paid POs excluded) and unpaid on-credit expenses.
- Reversal-awareness (2026-07-13 fix) confirmed present and unchanged in all locations the checklist calls out: `payroll.py` Rule 7 (`:2192-2204`), `payroll.py` creditors-aging (`:3341-3352`), `purchase_orders.py` `pay_po` (`:436-447`), and `financial_statements.py`'s balance-sheet AP lookup (`:540-560`, present in this repo's `journal.py` backfill equivalent at `:1156-1160`) — all net `credit − debit` and include `source.in_(["purchase_order", "purchase_order_reversal"])`.
- Supplier bank details decrypted via `decrypt_field()` (`crypto.py`) before display for `bank_name`, `account_number`, `branch_code` (`:3393-3395`).
- Per-PO AP amount uses actual journal-posted credits, falling back to `po.total_amount` only when no journal entry exists — correctly reflects partial deliveries.

## 5. Cross-module consistency

✓ No issues found.

- Journal coverage confirmed for all required transaction types in `journal.py`: invoice payments (`post_invoice_paid`, `:371`), expense payments (`post_expense` `:430` / `post_expense_paid` `:757`), PO receipts (`post_po_received` `:786`) and PO payments (`post_po_paid` `:838`), payroll runs (`post_payroll` `:505`). No gaps.
- Balance sheet control-account reconciliation: Rule 6 (AR/1100) and Rule 7 (AP/2000) both exclude `source == "import"` lines from the comparison (`payroll.py:2160, 2236`) and report them separately.
- Import-awareness (2026-07-11 fixes) confirmed intact in `csv_import.py`: `_auto_backfill()` (`:124`) runs after both invoice (`:501`) and expense (`:563`) imports; non-ZAR invoice imports without an `Exchange Rate` value are rejected per-row (`:460-472`); unbalanced journal-import groups are rejected (`:1035-1064`).
- The two most-recently-committed in-scope changes (COA sync/renumbering, provisional-tax cash-flow) were traced end-to-end and don't introduce any new journal-coverage gap or reconciliation break.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (per `financial_statements.py`'s `meta.basis` field). `financial_statements.py` is byte-identical to the 09-19 baseline — confirmed via `git diff` (zero changes) and a fresh non-diff-trusting `Read`/`Grep` pass this run.

**Standards status (fresh web search this run, 20 September 2026):** no change since 09-19.
- **IFRS 18** *Presentation and Disclosure in Financial Statements* — still effective for annual periods beginning on/after 1 January 2027, early application permitted. Not yet applicable to IFRS-for-SMEs preparers such as ZuZan's target companies.
- **IFRS for SMEs third edition** (issued Feb 2025) — still effective 1 January 2027; IASB continuing to publish supporting implementation modules through Q3 2026 on schedule.
- **VAT Act s7(4) Constitutional Court case** — still reserved judgment (heard 27 August 2026); no ruling issued as of this run. No code impact.

**Section 5b — deferred tax:** already implemented (not hard-coded to 0.0); re-verified at the code level this run:
- No hard-coded `"deferred_tax": 0.0` found (grep of the whole file).
- `_deferred_tax_balance()` (`financial_statements.py:131-173`) correctly computes tax base as cost minus cumulative SARS wear-and-tear allowance (rate priority: explicit `wear_and_tear_rate` → IN47 category lookup → unmappable fallback to carrying value, giving zero temporary difference), apportioned monthly from purchase date, floored at 0; temporary difference × 27% gives the balance.
- `FixedAsset.wear_and_tear_rate` column (`database.py:543`) and its `ALTER TABLE` migration (`database.py:1507`) confirmed present, correctly placed inside the migrations list literal (not dead code after the loop).
- Deferred tax expense = closing balance − opening balance (`:266-268`); Note 9 shows `deferred_tax` (period movement) and `total_tax` = current + deferred (`:601-611`).
- Balance sheet: deferred tax closing balance added as a non-current liability/asset with a matching offset to retained earnings, so Assets = Equity + Liabilities still holds.
- Safety case unchanged: with no fixed assets, `_deferred_tax_balance()` returns exactly `0.0`.

Finance costs (2026-07-13 fix): confirmed unchanged — interest lines (account `6700` or name-matched) are presented below EBIT (`:636-639`); `profit_before_tax = ebit - finance_costs` (`:259`); `tax_expense` and `net_profit` both derive from `profit_before_tax`, not EBIT.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date; `_current_tax_year()` (`payroll.py:170-181`) correctly derives and selects it.

**PAYE brackets, rebates, UIF ceiling** — fresh web search this run reconfirms all current code values (`payroll.py:132-146`):
- 7-bracket table (18% to R245,100 … 45% above R1,878,600) ✓ matches code.
- Primary rebate R17,820, secondary R9,765, tertiary R3,249 ✓ matches code.
- UIF earnings ceiling R17,712/month (max monthly contribution R177.12/party) ✓ matches code (`uif_ceil: 17712`).
- UIF 1%/1% (`UIF_RATE = 0.01`, `:189`) and SDL 1% (`SDL_RATE = 0.01`, `:190`) — no rate-change news found.
- Section 11F retirement fund deduction cap R430,000 (`S11F_CAP`, `:197`) — confirmed current for 2026/2027.

**Company tax:**
- CIT remains flat 27% for years of assessment 1 April 2026 – 31 March 2027 — confirmed unchanged. Code usage consistent (`CORP_TAX_RATE = 0.27`, `payroll.py:3151`; `financial_statements.py`'s `_CIT_RATE`, fallback 0.27).
- VAT standard rate confirmed unchanged at 15% (Budget 2026 dropped the previously-legislated escalation to 15.5%/16%; SARS and multiple independent trackers confirm 15% through 2026). Code usage consistent (`VAT_RATE = 0.15` at `payroll.py:2032, 2426, 3507`).
- Compulsory VAT registration threshold R2,300,000 (voluntary R120,000), effective 1 April 2026 — not gated anywhere in-scope; awareness only, unchanged.

**Provisional tax (2027/2028 placeholder):** `TAX_YEARS["2027/2028"]` (`payroll.py:152-167`) remains a flagged (`"provisional": True`) copy of 2026/2027 — standing reminder to replace after Budget Feb 2027 remains valid.

**Provisional tax cash-flow modelling (new this run):** `_provisional_tax_due()`/`_annual_tax_estimate()` (`payroll.py:2503-2590`) now project the two compulsory IRP6 instalment dates (50% of a trailing-12-month CIT estimate each) into `/reports/cash-flow-13week`, closing the previously-flagged gap where provisional tax wasn't modelled as a cash outflow. Correctly excludes the optional third "top-up" payment (depends on final assessment, not projectable) and correctly derives financial-year-end dynamically (leap-year-aware) from `Company.financial_year_end`, defaulting to the standard 28/29 February year end used by `financial_statements.py`. This is a forecasting estimate only, not the company's actual IRP6 filing — documented as such in the code.

No edits made to tax tables this run (report-only, as instructed; §5b remained verification-only since already implemented).

**Sources consulted:** [SARS Tax Tables 2026/2027 — Accounter](https://accounter.co.za/news/sars-tax-tables-2026-2027) · [PAYE Calculator South Africa 2026/2027 — Govchain](https://www.govchain.co.za/salary-tax-calculator) · [TaxTim Income Tax Calculator 2027](https://www.taxtim.com/za/calculators/income-tax) · [South Africa Corporate — Taxes on corporate income — PwC](https://taxsummaries.pwc.com/south-africa/corporate/taxes-on-corporate-income) · [Company Tax Rate South Africa 2026/27 — Smartbook](https://www.smartbookie.co.za/blog/company-tax-rate-south-africa) · [South Africa 2026 Budget ducks VAT rise — vatcalc.com](https://www.vatcalc.com/south-africa/south-africa-vat-rise/) · [VAT in 2026: Navigating Stability — SAIT](https://thesait.org.za/vat-in-2026-navigating-stability-and-the-legacy-of-the-2025-reversals/) · [South Africa VAT Rate 2026 — VatInfo.org](https://vatinfo.org/countries/za) · [Sars and Treasury ask top court to overturn ruling on minister's VAT powers — Business Day](https://www.businessday.co.za/news/2026-08-28-sars-and-treasury-ask-top-court-to-overturn-ruling-on-ministers-vat-powers/) · [IASB to issue third edition of the IFRS for SMEs Accounting Standard — IFRS.org](https://www.ifrs.org/news-and-events/news/2025/02/iasb-to-issue-third-edition-ifrs-for-smes-accounting-standard/) · [June 2026 IFRS for SMEs Accounting Standard Update — IFRS.org](https://www.ifrs.org/supporting-implementation/2015-ifrs-for-smes-supporting-materials/sme-updates/2026/june-2026-ifrs-for-smes-accounting-standard-update/)

## 8. Action items

1. **Medium (downgraded from High — carried over from 09-18/09-19, partially fixed this cycle):** the frontend's presentational Chart of Accounts (`App_js_fixed.js` `DEFAULT_COA`) previously collided with `journal.py`'s real posting accounts at codes `5110`-`5150`; this is now **fixed** (renumbered to `5010`-`5050`, verified collision-free). The broader issue — most DEFAULT_COA codes still don't correspond to a real ledger `Account` until first used — is now **mitigated** by `journal.py`'s auto-vivify fallback (`:237-286`): an unmatched code+name is created and posted to exactly as selected, rather than silently miscategorised as General Expenses. Residual risk: `Expense.category` strings written under the *old* routing (pre-2026-09-18) remain wrongly classified in the ledger and are not retroactively reposted — still recommend a one-off reconciliation pass over historical expense postings as a follow-up task, but the live/forward-looking risk that motivated the High severity is resolved.
2. **Low (repo hygiene, carried over from 09-14/.../09-19 — user action needed):** `zuzan-backend/.fuse_hidden0000000c00000001` and `...02` are still present on disk, unchanged in size/timestamp since prior checks. **User action:** delete manually via Windows Explorer, closing whatever process has them locked if deletion is refused there too.
3. **Low (repo clutter, carried over — decision needed):** `LAUNCH_READINESS_2026-07-14.md` remains untracked in the project root. Still a user judgment call (commit as historical record vs. delete).
4. **Low (process, improved from Medium — three of four previously-uncommitted files are now committed):** `zuzan-backend/journal.py`, `payroll.py`, `App_js_fixed.js`, and `.gitignore` — flagged uncommitted since 09-18 — are now committed as of `795afc9`. Only `zuzan-backend/test_payroll_journal_balance.py` (the audit's own regression test) remains untracked; recommend committing it too so the standing regression check survives a fresh checkout.
5. **Low (data freshness, standing):** MIBCO Sector 5 Year 2 employee health-scheme contribution remains officially "TBC" industry-wide (last independently checked 2026-09-18, not re-searched this run since nothing suggested a publication in the intervening day) — re-check on the next run that specifically touches payroll/MIBCO logic, or at minimum monthly.

**No new Critical/High findings this run.** Item 1 improved (High → Medium); item 4 improved (Medium → Low). No other severity changes.

**Standing reminders (carried from prior reports, unchanged unless noted):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry after Budget Feb 2027 and restart the backend;
(b) early-2027 runs should execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`);
(c) the AFS PayFast payment/ad-hoc tokenization feature and `/reports/ai-insights` remain outside this audit's scope;
(d) NBCPSS/MIBCO payroll calculation detail remains outside this checklist's explicit scope except where it produces an in-scope journal-integrity failure;
(e) the imported-equity-offset (3998/3999) exclusion logic lives in `payroll.py`'s `balance_sheet()`, not `financial_statements.py`;
(f) next run should keep checking for the outcome of Treasury/SARS's review of the 2026 draft TLAB/TALAB submissions and its introduction in Parliament;
(g) `parent_company_id`/`user_type`, bookkeeper-onboarding, consolidated-billing, accountant-fee-structure, and accountant-practice-dashboard/`billing_exempt` features remain outside scope, awareness only;
(h) provisional tax modelling (13-week cash flow) — **now implemented (this run)**; monitor the estimate's accuracy against real company data once available, since it's a trailing-run-rate projection, not the company's actual IRP6 "basic amount" computation;
(i) compulsory VAT-registration turnover threshold is R2,300,000 (voluntary R120,000), effective 1 April 2026 — not gated anywhere in-scope, awareness only;
(j) the persistent Chart of Accounts feature (`/coa` router) custom-account routing gap is closed; the broader DEFAULT_COA/journal code-mismatch is now downgraded to Medium per action item 1;
(k) the invoice header-image upload, custom HTML invoice template, and service-item catalogue remain additive presentation/picklist features outside scope;
(l) the IASB's SME consolidation-exception Exposure Draft comment period closed 9 September 2026 as scheduled; check for a post-close update on subsequent runs;
(m) the Constitutional Court has reserved judgment (heard 27 August 2026) on Section 7(4) of the VAT Act; no ruling yet — monitor;
(n) the `/integrations/invoice` (SMT) endpoint remains formally in-scope going forward — spot-check with a real create + re-post cycle once real SMT traffic exists;
(o) `POST /accountant/sync-customers` remains tracked given its proximity to Debtors scope;
(p) the employee time-clock system (`clock.html`, `clocking.py`) remains additive with no journal/AR/AP/Reports touchpoints, awareness only unless a future OT-import path from clocking data feeds payroll without validation;
(q) mass payslip ZIP download remains a read-only export feature with no journal/AR/AP/Reports touchpoints — awareness only.
