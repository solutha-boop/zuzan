# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 19 September 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-09-18 (PASS — first clean run since 2026-07-15)

**Change detection since last run:** `git log`/`git status -sb` show local `main` == `origin/main` at commit **`f6415e7`** (17 Sep 20:41) — no new commits since the 09-18 report. The working tree carries the same uncommitted changes the 09-18 report's post-report addendum described and left uncommitted: `.gitignore`, `App_js_fixed.js`, `zuzan-backend/journal.py`, `zuzan-backend/payroll.py` modified; `LAUNCH_READINESS_2026-07-14.md`, `zuzan-backend/test_payroll_journal_balance.py`, and the 09-18 report itself remain untracked. `git diff` against `f6415e7` confirms these are exactly the same edits described in the 09-18 addendum (custom-`/coa`-account journal sync in `journal.py`, provisional tax IRP6 modelling in `payroll.py`'s 13-week cash flow, the matching frontend row/CSV column in `App_js_fixed.js`, and the `.fuse_hidden*` `.gitignore` entry) — nothing new has been added or changed. `financial_statements.py`, `csv_import.py`, `purchase_orders.py`, `customers.py`, `suppliers.py`, `companies.py`, `database.py` (except the already-verified `wear_and_tear_rate` migration), and `main.py` are all unchanged from the 09-18 baseline.

Because no source changed, this run re-verifies the full checklist directly against the current code (not by diff-trust alone) and additionally re-ran the standing regression test.

**Independent re-run of `test_payroll_journal_balance.py`:** executed in a clean sandbox copy of `zuzan-backend/` (the working tree's own copy is on a cloud-synced mount that fails SQLite's file-locking model in this run's execution environment — a sandbox/mount quirk, not an app defect). All **16/16 scenarios passed**, debit=credit to the cent, including the "kitchen sink" scenario exercising every optional payslip field simultaneously. The payroll↔journal integrity fix from 09-17 remains solid.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ✅ PASS |
| Debtors (AR) | ✅ PASS |
| Creditors (AP) | ✅ PASS |
| Cross-module consistency | ✅ PASS |
| IFRS compliance (AFS) | ✅ PASS — no standards changes since 09-18; deferred tax (5b) unchanged and re-verified |
| Tax updates (SARS) | ✅ PASS — 2026/2027 tables current, no rate changes |

**Overall: PASS.** No code regressions since 09-18. No new Critical/High/Medium findings this run. Two Low-severity hygiene items and one High data-quality item (DEFAULT_COA/journal code mismatch) remain carried over from 09-18, unresolved and unchanged.

## 2. Reports

✓ No issues found.

- `payroll.py` `/reports/dashboard` (`:1648-1739`): `total_revenue` sums only `InvoiceStatus.paid` invoices via `_to_zar()` plus bank-import income (`:1657-1663`); `total_outstanding` covers `sent`+`overdue` via `_to_zar()` (`:1665-1669`); expenses (`:1672-1675`) and PO COGS (`:1677-1685`, via `_po_delivered_net()` — delivered-value only, no double count) are excluded from revenue and instead roll into `total_expenses`; payroll cost (`:1693-1709`, `Payslip.total_cost`) is a separate line subtracted from gross profit to reach `net_profit` — correctly included in the P&L, not omitted.
- `/reports/management` (`:2894-3010` region): revenue trend loop applies `_to_zar()` on every iteration (`:2986, 2990`) — consistent across all 6 months, matches the dashboard's methodology.
- `main.py` `/v1/summary` (`:466-503`): imports and uses `_to_zar()` for both `total_revenue` (`:473`) and `outstanding` (`:503`) — consistent with the reports engine.
- PO-cost-once via `_po_delivered_net()` (`payroll.py:28-47`) is used identically across `/reports/dashboard`, `/reports/management`, `/v1/summary`, and `/reports/cash-flow-13week` — no evidence of double-counting between expenses and PO receipts (the dashboard's `duplicate_expense_warning` check, `:1733-1739`, additionally flags likely double-entries by amount/date/supplier heuristics).

## 3. Debtors

✓ No issues found.

- `/reports/debtors-aging` (`payroll.py:3251-3311`): filtered to `Invoice.status.in_([sent, overdue])` (`:3260-3263`) — paid invoices excluded.
- ZAR equivalents shown via `_to_zar()` (`:3274`) — foreign-currency invoices are converted, not shown raw.
- Aged strictly from `due_date` (`:3270-3294`); invoices with no `due_date` fall into a separate `not_due` bucket rather than being aged from `issue_date`/`created_at` (explicit design choice, commented in code, to avoid overstating overdue balances).
- Buckets: `not_due`, `current` (0-30), `31_60`, `61_90`, `over_90` — correctly bounded.
- Frontend `Debtors` component (`App_js_fixed.js:7091-7141`) consumes `/reports/debtors-aging` directly with no independent recomputation — single source of truth.

## 4. Creditors

✓ No issues found.

- `/reports/creditors-aging` (`payroll.py:3314-3489`): sources both outstanding POs (`status in (received, partial)`, `:3330-3333` — fully paid POs excluded) and unpaid on-credit expenses (`is_on_credit == True and paid_at is None`, `:3425-3429`).
- Reversal-awareness (2026-07-13 fix) confirmed present and unchanged in **all four** locations the checklist calls out: `payroll.py` Rule 7 balance-sheet reconciliation (`:2192-2210`), `payroll.py` creditors-aging itself (`:3342-3358`), `purchase_orders.py` `pay_po` (`:405-445`), and `journal.py`'s backfill (`:1130`) — every one nets `credit − debit` and includes `source.in_(["purchase_order", "purchase_order_reversal"])`.
- Supplier bank details decrypted via `decrypt_field()` (from `crypto.py`) before display for `bank_name`, `account_number`, `branch_code` (`:3393-3395`).
- Per-PO AP amount uses actual journal-posted credits (`po_ap_amounts`, falling back to `po.total_amount` only when no journal entry exists yet), not `po.total_amount` directly — correctly reflects partial deliveries.

## 5. Cross-module consistency

✓ No issues found.

- Journal coverage confirmed for all five required transaction types in `journal.py`: invoice payments (`post_invoice_paid`, `:343`), expense payments (`post_expense` `:402` / `post_expense_paid` `:729`), PO receipts (`post_po_received` `:758`) and PO payments (`post_po_paid` `:810`), and payroll runs (`post_payroll` `:477`). No gaps found (also covers stock adjustment, asset acquisition/depreciation/disposal — additional coverage beyond the minimum checklist).
- Balance sheet control-account reconciliation: `payroll.py`'s Rule 6 (AR/1100, `:2140-2175`) and Rule 7 (AP/2000, `:2177-2250`) both reconcile the journal balance against raw invoice/PO totals, both correctly excluding `source == "import"` lines from the comparison and reporting them separately as opening balances (`:2150-2166`, `:2228-2249`).
- Import-awareness (2026-07-11 fixes), all confirmed intact in `csv_import.py`: `_auto_backfill()` (`:124-143`) runs automatically after both invoice and expense imports (`:501, 563`); non-ZAR invoice imports without an `Exchange Rate` value are rejected per-row rather than defaulting to 1.0 (`:458-475`); unbalanced journal-import groups are rejected with a per-row error (`:1035-1064`), not silently imported. Rule 6/7 `source == "import"` exclusion and the 3998 (Retained Earnings)/3999 (Opening Balance Equity) imported-equity offset logic (`payroll.py:1950-1970`, `csv_import.py:726-946`) are all unchanged and present.
- The two uncommitted working-tree changes (custom-`/coa`-account journal sync in `journal.py:178-262`, provisional tax IRP6 modelling in `payroll.py`) were re-read line-by-line against the 09-18 report's description and match exactly — no drift, no partial application.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (as stated in `financial_statements.py`'s `meta.basis` field, `:623`). `financial_statements.py` is byte-identical to the 09-18 baseline (confirmed via `git diff` — zero changes) — no code changes to re-verify, but a fresh, non-diff-trusting read was performed this run.

**Standards status (fresh web search this run, 19 September 2026):** no change since 09-18.
- **IFRS 18** *Presentation and Disclosure in Financial Statements* — confirmed still effective for annual periods beginning on/after 1 January 2027 (early application permitted). Not yet applicable to IFRS-for-SMEs preparers such as ZuZan's target companies.
- **IFRS for SMEs third edition** (issued Feb 2025) — confirmed still effective 1 January 2027; IASB continuing to publish supporting implementation modules through Q3 2026 on schedule. No change to the effective date or scope.
- **VAT Act s7(4) Constitutional Court case** — still reserved judgment as of the last confirmed hearing (27 August 2026, SARS/Treasury seeking to overturn the Western Cape High Court's finding that the Minister's unilateral VAT-rate-setting power under s7(4) is unconstitutional). No ruling issued yet; no code impact. Continue monitoring — if the High Court finding is upheld, Parliament has a 24-month suspension window to amend the Act, so no immediate rate-setting-mechanism change is expected even then.

**Section 5b — deferred tax:** already implemented (not hard-coded to 0.0); re-verified at the code level this run by direct read (not diff-trust):
- No hard-coded `"deferred_tax": 0.0` found (confirmed via grep of the whole file).
- `_deferred_tax_balance()` (`financial_statements.py:131-173`): correctly computes tax base as cost minus cumulative SARS wear-and-tear allowance (rate priority: explicit `wear_and_tear_rate` → `sars_category` IN47 lookup → category-name heuristic → unmappable-fallback to carrying value, giving a zero temporary difference), apportioned monthly from purchase date and floored at 0; temporary difference × 27% (`_CIT_RATE`) gives the balance (liability if positive, asset if negative); disposed assets are excluded once their disposal date has passed.
- `FixedAsset.wear_and_tear_rate` column (`database.py:543`) and its `ALTER TABLE` migration (`database.py:1507`) confirmed present and correctly placed **inside** the migrations list literal (not dead code after a loop).
- Category-to-rate mapping present and matches common IN47 write-off periods: computers/laptops 3 yrs (33.33%), software/phones 2 yrs (50%), furniture/fittings 6 yrs (16.67%), vehicles/plant/machinery/equipment 5 yrs (20%), trucks 4 yrs (25%), buildings 25 yrs (4%) — `financial_statements.py:89-102`.
- Deferred tax expense = closing balance − opening balance (`:266-268`); Note 9 shows `deferred_tax` (period movement) and `total_tax` = current + deferred (`:601-611`); effective-rate calc unchanged.
- Balance sheet: deferred tax closing balance added as a non-current liability (code 2600, when positive) or non-current asset (code 1900, when negative) with the matching offset to retained earnings so Assets = Equity + Liabilities still holds (`:315-328`) — confirmed algebraically consistent (the same `dt_closing` adjusts both the balance-sheet side and retained earnings by the same amount).
- Safety case: with no fixed assets, `_deferred_tax_balance()` returns exactly `0.0` (empty `assets` query short-circuits the loop) — output shape unaffected.
- Frontend `App_js_fixed.js` (`:13730-13740`) renders the Note 9 taxation table with a conditional `deferred_tax` row (`n.tax_note.deferred_tax ? <tr>...` — only shown when non-zero) — confirmed present, no changes needed.

Finance costs (2026-07-13 fix): confirmed unchanged — interest lines (account `6700` or name-matched `"interest"`/`"finance cost"`, `financial_statements.py:207-211`) are excluded from opex and presented as a separate `finance_costs` line below EBIT (`:636-639`); `profit_before_tax = ebit - finance_costs` (`:259`); `tax_expense` and `net_profit` both derive from `profit_before_tax`, not EBIT (`:260-261`).

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date (19 September 2026 falls within this year; `_current_tax_year()` at `payroll.py:170-181` correctly derives and selects it, with safe fallback logic for future dates before the next annual update lands).

**PAYE brackets, rebates, UIF ceiling** — fresh web search this run confirms all current code values are correct for 2026/2027 (`payroll.py:132-146`):
- 7-bracket table: 18% to R245,100; 26% to R383,100; 31% to R530,200; 36% to R695,800; 39% to R887,000; 41% to R1,878,600; 45% above — matches Budget 2026's 3.3% inflation adjustment from 1 March 2026. ✓ matches code exactly.
- Primary rebate R17,820, secondary rebate R9,765, tertiary rebate R3,249. ✓ matches code exactly.
- UIF earnings ceiling R17,712/month (max monthly UIF contribution R177.12 per party). ✓ matches code (`uif_ceil: 17712`, used consistently at `:115,130,145,165`).
- UIF 1%/1% employee/employer (`UIF_RATE = 0.01`, `:189`) and SDL 1% (`SDL_RATE = 0.01`, `:190`) — unchanged, no rate-change news found this run.

**Section 11F retirement fund deduction cap:** R430,000 confirmed current for 2026/2027 (`payroll.py:195-197`, `S11F_CAP = 430_000`) — matches Budget 2026's increase from R350,000 (first increase since 2016).

**Company tax:**
- CIT remains flat 27% — confirmed current for years of assessment 1 April 2026 to 31 March 2027, no change announced. Code usage consistent across `payroll.py:1713, 2960, 3151` (`CORP_TAX_RATE = 0.27` at `:3151`) and `financial_statements.py`'s `_CIT_RATE` (imported from `fixed_assets.SA_CIT_RATE`, fallback 0.27).
- VAT standard rate unchanged at 15% — confirmed current (Ministry of Finance confirmed 15% effective 1 May 2025, no further change through 2026/2027). Code usage consistent across `payroll.py:2032, 2426, 3507` (all `VAT_RATE = 0.15`).
- Compulsory VAT registration threshold R2,300,000 (voluntary R120,000), effective 1 April 2026 — not gated anywhere in-scope; awareness only (standing note, unchanged).

**Provisional tax (2027/2028 placeholder):** `TAX_YEARS["2027/2028"]` (`payroll.py:152-167`) remains a flagged (`"provisional": True`) copy of the 2026/2027 table, correctly positioned to prevent a `KeyError` on 1 March 2027 rather than an accurate forecast — standing reminder to replace after Budget Feb 2027 remains valid, no action needed yet.

No edits made to tax tables this run (report-only, as instructed; §5b remained verification-only since already implemented).

**Sources consulted:** [SARS Tax Tables 2026/2027 — Accounter](https://accounter.co.za/news/sars-tax-tables-2026-2027) · [PAYE Calculator South Africa 2026/2027 — Govchain](https://www.govchain.co.za/salary-tax-calculator) · [2026/2027 Tax Year: Key Payroll Changes — Talentide](https://talentide.co.za/blog/2026-2027-tax-year-payroll-changes-south-africa/) · [Budget 2026 FAQ — SARS](https://www.sars.gov.za/about/sars-tax-and-customs-system/budget/budget-2026-frequently-asked-questions/) · [Corporate Tax remains unchanged — BDO](https://www.bdo.co.za/en-za/insights/2026/budget-speech/corporate-tax-remains-unchanged,-with-a-pinch-of-positivity) · [South Africa Corporate — Taxes on corporate income — PwC](https://taxsummaries.pwc.com/south-africa/corporate/taxes-on-corporate-income) · [SARS and Treasury ask top court to overturn ruling on minister's VAT powers — Business Day](https://www.businessday.co.za/news/2026-08-28-sars-and-treasury-ask-top-court-to-overturn-ruling-on-ministers-vat-powers/) · [Godongwana's lawyers urge ConCourt to uphold VAT Act provisions — EWN](https://www.ewn.co.za/2026/08/27/godongwanas-lawyers-urge-concourt-to-uphold-vat-act-provisions-for-sound-fiscal-administration) · [IFRS for SMEs third edition — ACCA](https://www.accaglobal.com/learning-and-events/corporate-reporting/third-edition-ifrs-for-smes.html) · [June 2026 IFRS for SMEs Accounting Standard Update — IFRS.org](https://www.ifrs.org/supporting-implementation/2015-ifrs-for-smes-supporting-materials/sme-updates/2026/june-2026-ifrs-for-smes-accounting-standard-update/)

## 8. Action items

1. **Low (repo hygiene, carried over from 09-17/09-18 — user action needed):** `zuzan-backend/.fuse_hidden0000000c00000001` and `...02` are still present on disk. `.gitignore` already has `.fuse_hidden*` added (uncommitted). This session's shell still cannot delete them (would need to test — not attempted again this run since the 09-18 report already documented the OS-level lock; no indication the lock has cleared). **User action:** delete manually via Windows Explorer, closing whatever process has them open if deletion is refused there too.
2. **Low (repo clutter, carried over — decision needed):** `LAUNCH_READINESS_2026-07-14.md` remains untracked in the project root, unchanged. Still a user judgment call (commit as historical record vs. delete) — not resolved unilaterally.
3. **High (data quality, carried over from 09-18, unfixed):** the frontend's ~90-item presentational Chart of Accounts (`App_js_fixed.js` `DEFAULT_COA`) still uses account codes largely disjoint from `journal.py`'s actual posting `DEFAULT_ACCOUNTS`, with a handful of collisions in the `5110`-`5150` range that post to a real but wrongly-named account (e.g. "5110 - Purchases" in the picker posts to the ledger account actually named "Payroll Levies (UIF/SDL)"). Does not affect aggregate P&L totals but corrupts per-account expense breakdowns and AFS note-level disclosure. Needs a deliberate reconciliation/migration plan (existing `Expense.category` strings reference the old codes) — still recommended as a dedicated follow-up task, not a quick fix. No progress since 09-18; not in this run's scope to fix unilaterally.
4. **Medium (process, carried over — recommend committing to source control soon):** `zuzan-backend/journal.py`, `payroll.py`, `App_js_fixed.js`, `.gitignore`, and the new `test_payroll_journal_balance.py` remain uncommitted in the working tree, two days after being written (09-18). This session independently re-verified the test still passes (16/16) and the diffs still match their documented intent, so the risk is process-only (uncommitted work can be lost or diverge), not a functional defect. Recommend committing before further changes accumulate.
5. **Low (data freshness, standing):** MIBCO Sector 5 Year 2 employee health-scheme contribution remains officially "TBC" industry-wide (last independently checked 2026-09-18) — not re-searched this run since nothing suggested a publication in the intervening day; re-check on the next run that specifically touches payroll/MIBCO logic, or at minimum monthly.

**No new findings this run.** All five items above are carried over from 09-18, unchanged in severity or status.

**Standing reminders (carried from prior reports, unchanged):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry after Budget Feb 2027 and restart the backend;
(b) early-2027 runs should execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`);
(c) the AFS PayFast payment/ad-hoc tokenization feature and `/reports/ai-insights` remain outside this audit's scope;
(d) NBCPSS/MIBCO payroll calculation detail (minimum wage checks, allowance rates, area/role rate tables) remains outside this checklist's explicit scope except where it produces an in-scope journal-integrity failure;
(e) the imported-equity-offset (3998/3999) exclusion logic lives in `payroll.py`'s `balance_sheet()`, not `financial_statements.py`;
(f) next run should keep checking for the outcome of Treasury/SARS's review of the 2026 draft TLAB/TALAB submissions and its introduction in Parliament;
(g) `parent_company_id`/`user_type`, bookkeeper-onboarding, consolidated-billing, accountant-fee-structure, and accountant-practice-dashboard/`billing_exempt` features remain outside Reports/Debtors/Creditors/AFS/tax scope, awareness only;
(h) provisional tax modelling (13-week cash flow) — monitor the estimate's accuracy against real company data once available, since it's a trailing-run-rate projection, not the company's actual IRP6 "basic amount" computation;
(i) compulsory VAT-registration turnover threshold is R2,300,000 (voluntary R120,000), effective 1 April 2026 — not gated anywhere in-scope, awareness only;
(j) the persistent Chart of Accounts feature (`/coa` router) custom-account routing gap is closed (fixed 09-18); the broader DEFAULT_COA/journal code-mismatch is tracked as action item 3 above;
(k) the invoice header-image upload, custom HTML invoice template, and service-item catalogue remain additive presentation/picklist features outside the original checklist's endpoint list;
(l) the IASB's SME consolidation-exception Exposure Draft comment period closed 9 September 2026 as scheduled; check for a post-close update on subsequent runs;
(m) the Constitutional Court has reserved judgment (heard 27 August 2026) on Section 7(4) of the VAT Act; no ruling yet — monitor;
(n) the `/integrations/invoice` (SMT) endpoint remains formally in-scope going forward — spot-check with a real create + re-post cycle once real SMT traffic exists;
(o) `POST /accountant/sync-customers` remains tracked given its proximity to Debtors scope;
(p) the employee time-clock system (`clock.html`, `clocking.py`) remains additive with no journal/AR/AP/Reports touchpoints, awareness only unless a future OT-import path from clocking data feeds payroll without validation;
(q) mass payslip ZIP download remains a read-only export feature with no journal/AR/AP/Reports touchpoints — awareness only.
