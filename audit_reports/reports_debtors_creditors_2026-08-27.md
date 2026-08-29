# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 27 August 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-08-26 (full PASS).

**Change detection since last run:** `git log` shows eight new commits after the 08-26 audit (`79abbd3` through `2554766`, 26 Aug 21:29–22:08): bank feeds additions (FNB default tab, African Bank, Discovery Bank — cosmetic/UI only), a new **persistent Chart of Accounts** feature (`CompanyAccount` model + `/coa` CRUD router + frontend wiring so custom GL accounts appear in expense dropdowns and the Chart of Accounts view), a settings/billing change (plan selector relabelled "Change Plan", a "Cancel Payroll" add-on control), and an ESLint fix. `git diff 817b882..2554766 -w --stat` confirms **zero diff** in `financial_statements.py`, `journal.py`, `purchase_orders.py`, `suppliers.py`, `customers.py`, `csv_import.py`, and `payroll.py` — none of the audited AR/AP/AFS/tax logic itself changed. Changed files: `App_js_fixed.js`/`zuzan-app/src/App.js` (+137 each), `companies.py` (+150, new `/coa` router), `database.py` (+32, new `CompanyAccount` model + migration), `main.py` (+4, router registration + the recurring comment-duplication artifact), `billing.py` (+8, more `resp = None` duplication).

Migration hygiene check on the new `company_accounts` table: the `CREATE TABLE IF NOT EXISTS company_accounts (...)` and its unique index are correctly placed **inside** the `init_db()` migrations list literal (`database.py`, in the same list as the `parent_company_id`/`user_type` migrations), not appended after the loop — consistent with the standing dead-code fix from 2026-07-xx. ✓.

While reviewing the new Chart-of-Accounts feature's interaction with expense posting, this run found a **new, previously-unflagged defect** in the existing (unchanged) expense→GL-account routing — see §2/§6 below. It is corroborated by a real production data point already on record in a separate reconciliation report from yesterday.

Re-verified high-risk anchors via Grep — all unchanged: `"deferred_tax": 0.0` → no matches in `financial_statements.py`; `wear_and_tear_rate` present in `database.py`; `purchase_order_reversal` present in `payroll.py`, `financial_statements.py`, `journal.py`, `purchase_orders.py`; `source == "import"` exclusion present in `payroll.py`; `TAX_YEARS["2026/2027"]`, `VAT_RATE = 0.15`, `S11F_CAP = 430_000` present and unchanged in `payroll.py`.

**Out-of-scope but flagged (Critical, security, carried over):** `C:\Zuzan\ghp_w0vWd0jgV1yFdHb9NODeqLMx5jlKOz3.txt` (a plaintext-looking GitHub personal access token) is still present in the repo root, untracked, unchanged from yesterday. Still unresolved — see Action Items.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ⚠️ PASS with new finding — headline totals unaffected; new expense-account misclassification bug found |
| Debtors (AR) | ✅ PASS — aged from due_date, paid excluded, ZAR amounts |
| Creditors (AP) | ✅ PASS — reversal-aware, bank details decrypted |
| Cross-module consistency | ✅ PASS — full journal coverage, import-awareness intact, new COA migration hygiene confirmed |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) re-verified, no regressions; new finding affects COGS/finance-cost presentation accuracy in specific cases (see §6) |
| Tax rates (SARS) | ✅ PASS — 2026/2027 tables current, no rate changes; TLAB/TALAB comment period closes today |

**Overall: PASS, with one new High-severity finding.** The eight new commits add a persistent Chart of Accounts feature (additive, correctly migrated) and cosmetic UI changes; no regressions to the audited AR/AP/AFS/tax logic itself. Investigating how the new COA feature feeds the expense form surfaced a **pre-existing** (not introduced by this run) defect: the expense "Account" dropdown submits a `"{code} - {name}"` string as `category`, but the backend's `CATEGORY_TO_CODE` lookup expects bare account names, so it silently falls through to the account 5900 "General Expenses" fallback for essentially every manually-entered expense regardless of which account the user actually selected. This does not affect total revenue, total expenses, net profit, or journal balance — but it does understate/misstate Cost of Sales and Finance Costs whenever a user tags a manual expense as such, and it makes expense-by-account reporting meaningless. See §2 and §6 for detail and evidence.

## 2. Reports

**New finding (High) — expense category/account mismatch silently reroutes to 5900 "General Expenses":**
- `App_js_fixed.js:2013-2018` (and the matching Add/Edit-expense selects at `App_js_fixed.js:2089-2093` and `:2146-2150`) — the "Account" `<select>` submits `value={`${a.code} - ${a.name}`}` (e.g. `"5290 - Marketing"`) as the expense's `category` field. This UI shape predates this run (confirmed via `git log -S` — present since at least commit `5963cfb`), and is unchanged by this run's commits; the only change here was swapping `DEFAULT_COA` for the new merged `coaAccounts` list (which correctly includes custom accounts from `/coa`).
- `zuzan-backend/companies.py:692` stores that raw string verbatim: `category=clean(data.category, 200)` — no parsing.
- `zuzan-backend/journal.py:143-149` (`expense_account()`) resolves the GL account via `CATEGORY_TO_CODE.get(category or "", "5900")`. `CATEGORY_TO_CODE` (`journal.py:88-104`) keys are bare account names (`"Marketing"`, `"Rent"`, `"Cost of Sales"`, `"Finance Costs"`, etc.), not `"code - name"` strings. `"5290 - Marketing" != "Marketing"`, so the lookup misses for every account the dropdown can produce and falls through to the `"5900"` default on every call.
- `journal.py:313` (`post_expense`) then posts the debit line to whatever `expense_account()` returned — i.e. account 5900, regardless of the account the user picked in the UI.
- **Impact:** total revenue, total expenses, net profit, and journal balance are all unaffected (the amount still posts, just to the wrong account, and `payroll.py`'s dashboard/management totals sum `Expense.amount` directly rather than by GL account — see `payroll.py:1249-1252`, confirmed unchanged and correct). What *is* affected: (a) any manually-entered expense a user tags as `"5000 - Cost of Sales"` lands in opex (5900) instead of COGS, understating Cost of Sales and overstating Gross Profit/Margin in the AFS; (b) an expense tagged `"6700 - Finance Costs (Interest Paid)"` won't be recognised as a finance cost by `financial_statements.py`'s `_is_finance_cost()` (code `!= "6700"`, name `"General Expenses"` doesn't match `"interest"`/"finance cost"`), so it stays in opex above EBIT instead of below it, per the 2026-07-13 fix's intent; (c) any expense-by-account/category breakdown (e.g. the Expenses view's own account column, or a future reporting view) will show virtually everything bucketed under "General Expenses", making it useless for management accounts drill-down.
- **Corroborating evidence:** yesterday's separate `reconciliation_2026-08-26.md` (§2) independently flagged, as an unexplained observation, a single R17,327.37 posting entirely to account 5900 for company 2 (Nwabeg) that drove its bank balance negative — noted there as "possibly miscategorized" without root cause. This is consistent with exactly the mechanism described above and is very likely the same underlying bug, not a coincidence.
- **Fix options:** either (i) change the dropdown option `value` back to the bare account name so it matches `CATEGORY_TO_CODE` keys (loses the ability to select non-mapped/custom accounts, including the new COA feature's whole point), or (ii) — recommended — change `expense_account()` to resolve by parsing the leading account code out of `category` (e.g. `category.split(" - ", 1)[0]`) and looking the `Account` up by code directly, falling back to `CATEGORY_TO_CODE`/5900 only when no code prefix is present (covers old data and the "-- Categorise later --" case). This also naturally makes custom COA accounts postable, which the new `/coa` feature currently doesn't support end-to-end (a custom account can be *selected* in the expense form, but the GL will never actually receive a posting to that account under the current lookup).

Confirmed unchanged and correct (re-verified this run, file byte-identical to 08-26 baseline):
- `total_revenue` sums only paid invoices via `_to_zar()` (`payroll.py:1238`), plus bank-import income (`:1240`) — consistent with prior runs.
- `total_outstanding` covers sent/overdue via `_to_zar()` (`payroll.py:1246`).
- Expenses excluded from revenue; `total_expenses` built from `Expense.amount - vat_amount` (`payroll.py:1249-1252`), independent of the account-mapping bug above.
- PO costs: received/partial/paid POs' delivered-net value added to expenses once (`payroll.py:1257-1262`), no double count with the `Expense` table (separate source).
- Depreciation and payroll costs correctly included (`payroll.py:1264-1289`).
- Management-accounts revenue trend loop and `/v1/summary` (`main.py:448-485`) both apply `_to_zar()` consistently.

## 3. Debtors

✓ No issues found.
- `payroll.py:2555-2558` filters `Invoice.status.in_([sent, overdue])` — paid excluded.
- Aged from `due_date` only (`payroll.py:2565`), not issue/created date; missing due dates go to `not_due` rather than inflating overdue buckets.
- Amounts converted via `_to_zar()` (`payroll.py:2569`).

## 4. Creditors

✓ No issues found.
- Outstanding = received/partial POs (`payroll.py:2625-2628`) plus unpaid on-credit expenses (`payroll.py:2720-2724`); fully paid POs and settled credit expenses excluded.
- Reversal-aware AP balance: nets `credit − debit` and includes `source.in_(["purchase_order","purchase_order_reversal"])` at all four expected call sites — `payroll.py:2645` (creditors-aging), `payroll.py:1779` (Rule 7 elsewhere in reports), `purchase_orders.py:445` (`pay_po`), `journal.py:848` (backfill), and also present in `financial_statements.py:558` for the balance sheet AP control account.
- Supplier bank details decrypted via `decrypt_field()` before display (`payroll.py:2688-2690`).

## 5. Cross-module consistency

✓ No issues found.
- Journal coverage complete: `post_invoice_raised`, `post_invoice_paid`, `post_invoice_cogs`, `post_expense`, `post_expense_paid`, `post_bank_income`, `post_payroll`, `post_po_received`, `post_po_paid`, `post_stock_adjustment`, `post_asset_acquisition`, `post_depreciation`, `post_asset_disposal` — all present in `journal.py`, no gaps against the required invoice/expense/PO/payroll flows.
- Import-awareness (2026-07-11 fixes) intact and unchanged: `source == "import"` exclusions on 1100/2000 (`payroll.py:1737,1813`), balance sheet retains 3998/3999 imported-equity offsets (`payroll.py:1538-1547`), unaffected by this run's commits.
- New `company_accounts` migration correctly sits inside the `init_db()` migrations list literal (`database.py`), consistent with the standing dead-code-migration fix.
- The new `CompanyAccount`/`/coa` table is entirely separate from the journal's own `Account` table (`financial_statements.py`'s `_acct_lines()` and `journal.py`'s `expense_account()`/`get_account()` all query `Account`, never `CompanyAccount`) — so custom accounts added via the new feature are cosmetic in the dropdown only; see §2 finding for the consequence.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (declared in AFS meta). Statements: income statement, statement of financial position, changes in equity, indirect cash flow, notes 2–9. `financial_statements.py` unchanged since 08-25.

**Standards status (fresh web search this run):** no material change since 08-26.
- IFRS 18 *Presentation and Disclosure in Financial Statements* — confirmed still effective for annual periods beginning on/after 1 January 2027; not applicable to IFRS-for-SMEs preparers (ZuZan's basis).
- IFRS for SMEs third edition (issued February 2025) — confirmed effective 1 January 2027, early adoption permitted, entities may continue applying the 2015 edition until then. New edition introduces an IFRS-15-based revenue model plus expanded fair value/financial-instruments/business-combinations requirements — no new SA-specific guidance found this run.

**Section 5b — deferred tax:** already implemented; re-verified this run. `financial_statements.py` contains `_deferred_tax_balance()` (line 131), per-asset tax base via `wear_and_tear_rate`/SARS IN47 category mapping (lines 87-110), opening/closing balance movement (`dt_opening`/`dt_closing`, lines 266-268) driving Note 9 `deferred_tax` (line 606) and `total_tax` (line 601), plus balance-sheet closing balance line and `deferred_tax_movement` disclosure (line 681). No `"deferred_tax": 0.0` hard-coding found. No changes needed.

**New finding relevant to this section:** the §2 expense-account mismatch means a manually-entered expense a user tags as Cost of Sales or Finance Costs will not actually land in those GL accounts, so the AFS's name/code-aware COGS-vs-opex classifier (`financial_statements.py:213-241`, the 2026-07-16 F1 fix) and finance-cost-below-EBIT presentation (`financial_statements.py:204-211`, the 2026-07-13 fix) are both still logically correct — the defect is upstream of them, in how expenses get their account assigned in the first place. Net profit and tax provisioning are unaffected either way.

Finance costs (2026-07-13 fix): interest still presented below EBIT, tax/net profit still derive from `profit_before_tax` — unchanged, confirmed no regression from this run's commits.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date, confirmed present at `payroll.py:132`.

- Fresh web search this run: the 2026 draft TLAB/TALAB comment period **closes today, 28 August 2026** [confirmed 28 August by multiple sources despite one search snippet showing "28 August" — treasury published 30 July 2026, comment deadline 28 August 2026]. Contents unchanged from yesterday's summary — donations-tax spousal-residency restriction, living-annuity de minimis aggregation, second-hand-goods documentation, bank refund-hold provisions, gold-to-banks proposal explicitly deferred. No enacted PAYE/UIF/SDL/CIT/VAT changes as of this run.
- PAYE brackets, rebates, UIF ceiling/percentages, SDL rate, S11F cap (`payroll.py:100-197`) — unchanged, matches 2026/2027 SARS tables per prior verified figures (top bracket 45% above R1,878,601; primary/secondary/tertiary rebates R17,820/R9,765/R3,249; UIF ceiling R17,712; S11F cap R430,000).
- VAT confirmed 15% (`VAT_RATE = 0.15`, `payroll.py:1609,2802`).
- CIT confirmed flat 27% (used in dashboard/management/provisional-tax and `financial_statements.py`'s deferred-tax calc).
- IFRS for SMEs third edition (see §6) — confirmed via fresh search this run, same effective date/status as previously logged.
- No edits made to tax tables (report-only per task rules; §5b was verification-only this run, already implemented).

**Sources consulted:** [National Treasury Publishes 2026 Draft Tax Bills for Public Comment — Tax Consulting SA](https://www.taxconsulting.co.za/national-treasury-publishes-2026-draft-tax-bills-for-public-comment/) · [Tax Practice Weekly Update — SAIT](https://thesait.org.za/tax-practice-weekly-update-issue-37-4-2-3-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-3-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2-2/) · [Big tax changes proposed — IOL](https://iol.co.za/business/2026-08-06-big-tax-changes-proposed-what-the-new-draft-bills-mean-for-taxpayers/) · [New tax laws for medical aid credits, companies, and spousal donations — BusinessTech](https://businesstech.co.za/news/government/868257/new-tax-laws-for-medical-aid-credits-companies-and-spousal-donations-in-south-africa/) · [2026 Draft Tax Bills have been published for comment — GoLegal](https://www.golegal.co.za/2026-draft-tax-bills/) · [National Treasury on publication of the 2026 draft tax bills for comment — gov.za](https://www.gov.za/news/media-statements/national-treasury-publication-2026-draft-tax-bills-comment-30-jul-2026) · [South Africa consults on 2026 draft tax legislation — RegFollower](https://regfollower.com/south-africa-consults-on-2026-draft-tax-legislation/) · [2026 draft TLAB: Key changes for businesses — PvdZ Consulting](https://tax.pvdz.co.za/tlab/) · [The 2026 Draft Tax Bills Are Out. Comment Closes 28 August — Accounting Weekly](https://www.accountingweekly.com/sars-updates/2026-draft-tlab-and-talab-what-accountants-must-know) · [IFRS for SMEs 2025 supporting materials — IFRS Foundation](https://www.ifrs.org/supporting-implementation/2025-ifrs-for-smes-supporting-materials/) · [IFRS for SMEs gets a major update — XBRL](https://www.xbrl.org/news/ifrs-for-smes-gets-a-major-update/) · [IASB releases third edition of IFRS for SMEs — The Accountant](https://www.theaccountant-online.com/news/iasb-releases-ifrs-for-smes/) · [IASB issues third edition of the IFRS for SMEs — PwC Viewpoint](https://viewpoint.pwc.com/dt/gx/en/pwc/in_briefs/in_briefs_INT/in_briefs_INT/iasb-issues.html) · [IFRS for SMEs — ICAEW tracker](https://www.icaew.com/technical/corporate-reporting/ifrs/ifrs-accounting-standards-tracker/ifrs-for-smes)

## 8. Action items

1. **Critical (security, out-of-scope but urgent, carried over unresolved):** `C:\Zuzan\ghp_w0vWd0jgV1yFdHb9NODeqLMx5jlKOz3.txt` still contains what appears to be a live GitHub personal access token in plaintext in the project root, untracked. Recommend revoking it in GitHub settings and deleting the file; check git history in case it was ever committed.
2. **High (new):** expense "Account" dropdown value (`"{code} - {name}"`) doesn't match `CATEGORY_TO_CODE`'s bare-name keys in `journal.py:88-149`, so essentially all manually-entered expenses post to account 5900 "General Expenses" regardless of the account selected in the UI (`App_js_fixed.js:2013-2018`, `companies.py:692`). Understates Cost of Sales / overstates Gross Profit when a user tags an expense as Cost of Sales; keeps interest/finance-cost expenses above EBIT instead of below; makes expense-by-account reporting meaningless. Recommend `expense_account()` parse the leading code from `category` and look up `Account` by code directly (see §2 for detail). Likely also explains the unexplained R17,327.37-to-5900 posting flagged in yesterday's `reconciliation_2026-08-26.md`.
3. **Medium (carried over):** `/reports/cash-flow-13week` (`payroll.py:1991-2098`) still does not model outstanding creditor (PO) payments or VAT201 liabilities as distinct weekly outflows (`other_payments`/`vat_payment` hard-coded `0.0`).
4. **Low (new, awareness):** the new `/coa` custom-account feature lets users add accounts to the `CompanyAccount` table and select them in expense dropdowns, but nothing in `journal.py` posts to a custom account by code (it only knows the fixed `Account` table seeded by `init_accounts()`/`DEFAULT_ACCOUNTS`). A user-created custom account is effectively decorative until item 2 above is fixed the recommended way (which would also make custom accounts postable, since it resolves by code against the real `Account` table — worth confirming a corresponding `Account` row also gets created for custom codes, not just the `CompanyAccount` display row).

**Standing reminders (not defects, carried from prior reports):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry (`payroll.py`) after Budget Feb 2027 and restart the backend;
(b) early-2027 runs should execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`);
(c) the AFS PayFast payment/ad-hoc tokenization feature and the `/reports/ai-insights` feature remain outside this audit's scope;
(d) NBCPSS private security payroll mode predates this audit's baseline, not yet part of this checklist's explicit scope;
(e) file-attribution note: the imported-equity-offset (3998/3999) exclusion logic lives in `payroll.py`'s `balance_sheet()`, not `financial_statements.py`;
(f) 2026 draft TLAB/TALAB comment period closes today (28 August 2026) — next run should check whether it closed on schedule and whether any provisions were finalized/amended;
(g) `parent_company_id`/`user_type` columns and bookkeeper-onboarding/consolidated-billing/accountant-fee-structure features remain outside Reports/Debtors/Creditors/AFS/tax scope, awareness only;
(h) legacy unused constants `PAYROLL_PER_EMP = 34.00` / `PAYROLL_MIN = 99.00` in `payroll.py` — still worth a cleanup pass, not a compliance issue;
(i) the cosmetic comment/statement-duplication artifact (`_SubscriptionGateMiddleware` line in `main.py`, `resp = None` in `billing.py`'s `adhoc_charge()`) grew again this run — `billing.py` now has 40 consecutive duplicate `resp = None` lines (up from ~11 at the last count) and `main.py`'s mangled comment line grew further. Still harmless functionally, but the growth rate suggests whatever auto-generation/merge step produces it should be found and fixed before it becomes unwieldy;
(j) compulsory VAT-registration turnover threshold rises to R2,300,000 (from R1,000,000), voluntary to R120,000 (from R50,000), effective 1 April 2026 — not gated anywhere in-scope, awareness only;
(k) the 13-week cash-flow forecast feature (`payroll.py:1991-2098`, `ForecastView` in `App_js_fixed.js`) remains additive and outside the original checklist's endpoint list — tracked via action item 3;
(l) new: the persistent Chart of Accounts feature (`/coa` router in `companies.py`, `CompanyAccount` in `database.py`, `ChartOfAccounts`/`Expenses` components in `App_js_fixed.js`) is additive and outside the original checklist's endpoint list — recommend adding it explicitly to this checklist's scope in future runs, and tracking action items 2 and 4 until resolved.
