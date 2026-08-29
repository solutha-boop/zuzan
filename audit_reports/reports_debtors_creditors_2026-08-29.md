# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 29 August 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-08-28 (PASS, one carried-over High finding, one carried-over Critical security item).

**Change detection since last run:** `git log --since="2026-08-28 00:10"` returns **zero commits** — HEAD is unchanged at `2554766` (26 Aug 22:08), the same commit audited on 08-27 and 08-28. This is the third consecutive byte-identical re-verification. Re-checked all standing high-risk anchors via Grep rather than trusting the prior report — all present and unchanged: `"deferred_tax": 0.0"` → no matches in `financial_statements.py`; `wear_and_tear_rate` present in `database.py`/`financial_statements.py`/`fixed_assets.py`; `purchase_order_reversal` present in `payroll.py`, `financial_statements.py`, `journal.py`, `purchase_orders.py`; `source == "import"` exclusions present in `payroll.py:1737,1813`; `TAX_YEARS`/`VAT_RATE = 0.15`/`S11F_CAP = 430_000` present and unchanged in `payroll.py`; `expense_account()` still keys on bare `CATEGORY_TO_CODE` names (`journal.py:143-145`) while the frontend still submits `"{code} - {name}"` (`App_js_fixed.js:2018,2093,2150,7492,7535,7542`) — the carried-over High finding is unchanged.

**Out-of-scope but flagged (Critical, security, carried over, still unresolved):** `C:\Zuzan\ghp_w0vWd0jgV1yFdHb9NODeqLMx5jlKOz3.txt` (a plaintext-looking GitHub personal access token) is still present in the repo root, untracked, unchanged since 24 August. Still unresolved — see Action Items.

Fresh web searches this run for the two sections that can move independently of the code (IFRS standards, SARS tax law) found no changes: IFRS 18 and IFRS for SMEs 3rd edition both remain confirmed for 1 January 2027; the 2026 draft TLAB/TALAB public comment period closed 28 August 2026 as scheduled, and no bill text, Parliamentary introduction, or rate changes have followed yet (one Parliamentary Monitoring Group link surfaced in this run's search results, "TLAB, TALAB, Rates Bill and Revenue Laws Amendment Bill: National Treasury briefing" — checked and found to be an archived 2023-cycle committee meeting, not new 2026 activity).

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ⚠️ PASS with carried-over finding — headline totals unaffected; expense-account misclassification bug still present, unfixed |
| Debtors (AR) | ✅ PASS — aged from due_date, paid excluded, ZAR amounts |
| Creditors (AP) | ✅ PASS — reversal-aware, bank details decrypted |
| Cross-module consistency | ✅ PASS — full journal coverage, import-awareness intact |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) re-verified at code level, no regressions, no standards changes |
| Tax rates (SARS) | ✅ PASS — 2026/2027 tables current, no rate changes; TLAB/TALAB still in post-comment-period limbo |

**Overall: PASS, with one carried-over High-severity finding (unfixed) and one carried-over Critical security item (unfixed, out of scope).** No code has changed since the 08-27 baseline, so all AR/AP/journal/AFS/tax logic re-verified byte-identical and correct except for the standing expense-account-mapping defect.

## 2. Reports

**Carried over (High) — expense category/account mismatch still reroutes to 5900 "General Expenses":**
- `App_js_fixed.js:2018,2093,2150` (manual add/edit-expense "Account" selects) and `App_js_fixed.js:7492,7535,7542` (the bank-statement-import categorisation step) all submit `value={`${a.code} - ${a.name}`}` (e.g. `"5290 - Marketing"`) as the transaction's `category`.
- `journal.py:145` (`expense_account()`) resolves via `CATEGORY_TO_CODE.get(category or "", "5900")`, whose keys (`journal.py:88-104`) are bare names (`"Marketing"`, `"Cost of Sales"`, `"Finance Costs"`, etc.) — `"5290 - Marketing" != "Marketing"`, so the lookup misses and falls through to account 5900 every time, for both manual and bank-imported expenses.
- `companies.py:1252-1319` (`POST /banking/import`) still stores `category=txn.category` verbatim on the `Expense` row (line 1308) and calls `journal_engine.post_expense()` (line 1316) — same `expense_account()` path as manual expenses.
- Income side unaffected: `INCOME_TO_CODE` (`journal.py:79-85`) resolves every key to the single code `"4000"`, so the same string-format mismatch is harmless there.
- **Impact (unchanged):** total revenue, total expenses, net profit, and journal balance remain correct in aggregate (`payroll.py:1249-1252` sums `Expense.amount` directly, not by GL account). What's still wrong: any expense tagged Cost of Sales or Finance Costs lands in opex/5900 instead, understating COGS/overstating gross margin, and keeping mis-tagged interest above EBIT instead of below; expense-by-account reporting remains meaningless.
- **Fix (unchanged recommendation):** change `expense_account()` to parse the leading account code out of `category` (`category.split(" - ", 1)[0]`) and look up `Account` by code directly, falling back to `CATEGORY_TO_CODE`/5900 only when no code prefix is present.

Confirmed unchanged and correct (re-verified this run):
- `total_revenue` sums only paid invoices via `_to_zar()` (`payroll.py:1238`), plus bank-import income (`:1240`).
- `total_outstanding` covers sent/overdue via `_to_zar()` (`payroll.py:1246`).
- Expenses excluded from revenue; `total_expenses` built from `Expense.amount - vat_amount` (`payroll.py:1252`), independent of the account-mapping bug above.
- PO costs: received/partial/paid POs' delivered-net value added to expenses once (`payroll.py:1259,2209`), no double count with the `Expense` table.
- Depreciation and payroll costs correctly included (`payroll.py:1268` and payslip-driven cost lines).
- Management-accounts revenue trend loop (`payroll.py:2189,2216,2228`) and `/v1/summary` (`main.py:455,485`) both apply `_to_zar()` consistently.

## 3. Debtors

✓ No issues found.
- `payroll.py:2557` filters `Invoice.status.in_([sent, overdue])` — paid excluded.
- Aged from `due_date` only (`payroll.py:2563-2565`), not issue/created date; missing due dates go to `not_due` rather than inflating overdue buckets.
- Amounts converted via `_to_zar()` (`payroll.py:2569` area).

## 4. Creditors

✓ No issues found.
- Outstanding = received/partial POs (`payroll.py:2627`) plus unpaid on-credit expenses; fully paid POs excluded.
- Reversal-aware AP balance: nets `credit − debit` and includes `source.in_(["purchase_order","purchase_order_reversal"])` at all expected call sites — `payroll.py:1779` (Rule 7), `payroll.py:2645` (creditors-aging), `purchase_orders.py:445` (`pay_po`), `journal.py:848` (backfill).
- Supplier bank details decrypted via `decrypt_field()` before display (`payroll.py:2688-2690`).

## 5. Cross-module consistency

✓ No issues found.
- Journal coverage complete: `post_invoice_raised`, `post_invoice_paid`, `post_invoice_cogs`, `post_expense`, `post_bank_income`, `post_payroll`, `post_expense_paid`, `post_po_received`, `post_po_paid`, `post_stock_adjustment`, `post_asset_acquisition`, `post_depreciation`, `post_asset_disposal` — all present in `journal.py`, no gaps against the required invoice/expense/PO/payroll flows.
- Import-awareness (2026-07-11 fixes) intact and unchanged: `source == "import"` exclusions on 1100/2000 (`payroll.py:1737,1813`), balance sheet retains 3998/3999 imported-equity offsets (`payroll.py:1538-1547`).
- Bank-statement import (`companies.py:1252-1359`) correctly dedupes both debit and credit legs before posting and correctly splits VAT on import — the only defect in this flow is the account-mapping issue in §2, which is a misclassification, not a missing/duplicated/unbalanced journal entry.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (declared in AFS meta, `financial_statements.py:623`). Statements: income statement, statement of financial position, changes in equity, indirect cash flow, notes 2–9. File byte-identical to the 08-27/08-28 baseline.

**Standards status (fresh web search this run):** no change.
- IFRS 18 *Presentation and Disclosure in Financial Statements* — confirmed still effective for annual periods beginning on/after 1 January 2027, earlier application permitted; not applicable to IFRS-for-SMEs preparers (ZuZan's basis).
- IFRS for SMEs third edition (issued 27 February 2025) — confirmed still effective 1 January 2027, early adoption permitted, current 2015 edition may continue to be applied until then.

**Section 5b — deferred tax:** already implemented; re-verified this run at the code level. `_deferred_tax_balance()` (`financial_statements.py:131`) computes per-asset tax base via `wear_and_tear_rate`/SARS IN47 category mapping; `dt_opening`/`dt_closing` (lines 266-268) drive `deferred_tax_expense`; the balance-sheet closing-balance line (2600 Deferred Tax Liability / 1900 Deferred Tax Asset, lines 315-328) carries a matching retained-earnings adjustment (lines 321,327,349) so the statement still balances; Note 9 (`deferred_tax` line 606, `total_tax` line 601, opening/closing balances lines 609-610, movement line 681) is populated. No `"deferred_tax": 0.0` hard-coding found anywhere in the file. No changes needed.

Finance costs (2026-07-13 fix): interest-below-EBIT split and tax/net-profit derivation from `profit_before_tax` (not EBIT) re-confirmed present and unchanged — no regression.

**Relevant to this section, carried over:** the §2 expense-account mismatch means an expense tagged Cost of Sales or Finance Costs won't actually land in those GL accounts, so the AFS's COGS-vs-opex classifier and finance-cost-below-EBIT presentation remain logically correct in themselves — the defect is upstream, in how expenses get their account assigned. Net profit and tax provisioning are unaffected either way.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date, present at `payroll.py:132`.

- Fresh web search this run: the 2026 draft TLAB/TALAB public comment period closed 28 August 2026 as scheduled (previous run's forward-looking note). No finalised bill text, enacted amendments, or Parliamentary introduction found this run. One PMG link surfaced ("TLAB, TALAB, Rates Bill and Revenue Laws Amendment Bill: National Treasury briefing") but on inspection it is an archived committee-meeting record from the **2023** legislative cycle (two-pot retirement system briefing, Practice Note 31, APA programme) — not related to the 2026 bills. No new 2026-cycle Parliamentary activity found.
- PAYE brackets, rebates, UIF ceiling/percentages, SDL rate, S11F cap (`payroll.py:100-197`) — re-confirmed via fresh search: top bracket 45% above R1,878,600/601; primary rebate R17,820; UIF ceiling R17,712/month (1% employee + 1% employer); SDL 1% (payroll >R500,000 exempt); tax threshold ≈R99,000 (under 65). Matches code, no discrepancy.
- VAT confirmed 15% via fresh search — standard rate unchanged — matches `VAT_RATE = 0.15` (`payroll.py:1609,2802`).
- CIT confirmed flat 27% via fresh search for years of assessment ending 1 April 2026–31 March 2027 — unchanged — matches code used in dashboard/management/provisional-tax and `financial_statements.py`'s deferred-tax calc.
- No edits made to tax tables (report-only per task rules; §5b was verification-only this run, already implemented).

**Sources consulted:** [IFRS - IFRS 18 Presentation and Disclosure in Financial Statements](https://www.ifrs.org/issued-standards/list-of-standards/ifrs-18-presentation-and-disclosure-in-financial-statements/) · [Effective date of IFRS 18 — IAS Plus](https://www.iasplus.com/en/events/effective-dates/2027/ifrs-18) · [IASB issues third edition of the IFRS for SMEs — IAS Plus](https://www.iasplus.com/en/news/2025/02/third-ifrs-for-smes) · [IFRS - The IFRS for SMEs Accounting Standard](https://www.ifrs.org/issued-standards/ifrs-for-smes/) · [National Treasury Publishes 2026 Draft Tax Bills for Public Comment — Tax Consulting SA](https://www.taxconsulting.co.za/national-treasury-publishes-2026-draft-tax-bills-for-public-comment/) · [The 2026 Draft Tax Bills Are Out. Comment Closes 28 August — Accounting Weekly](https://www.accountingweekly.com/sars-updates/2026-draft-tlab-and-talab-what-accountants-must-know) · [National Treasury on publication of the 2026 draft tax bills for comment — gov.za](https://www.gov.za/news/media-statements/national-treasury-publication-2026-draft-tax-bills-comment-30-jul-2026) · [TLAB, TALAB, Rates Bill and Revenue Laws Amendment Bill: National Treasury briefing — PMG](https://pmg.org.za/committee-meeting/38022/) (archived 2023-cycle record, checked and ruled not applicable) · [SARS Tax Tables 2026/2027: Brackets, Rates and Rebates — Xero ZA](https://www.xero.com/za/guides/sars-tax-tables-2026/) · [SARS Tax Tables 2026/2027 — Accounter](https://accounter.co.za/news/sars-tax-tables-2026-2027) · [PAYE Calculator South Africa 2026/2027](https://www.payecalculator.co.za/paye-information.php)

## 8. Action items

1. **Critical (security, out-of-scope but urgent, carried over unresolved):** `C:\Zuzan\ghp_w0vWd0jgV1yFdHb9NODeqLMx5jlKOz3.txt` still contains what appears to be a live GitHub personal access token in plaintext in the project root, untracked. Recommend revoking it in GitHub settings and deleting the file; check git history in case it was ever committed.
2. **High (carried over, unfixed):** expense "Account" dropdown value (`"{code} - {name}"`) doesn't match `CATEGORY_TO_CODE`'s bare-name keys in `journal.py:88-149`, so manually-entered expenses AND bank-import-categorised expenses (`companies.py:1252-1319`) both post to account 5900 "General Expenses" regardless of the account selected in the UI. Understates Cost of Sales / overstates Gross Profit when a user tags an expense as Cost of Sales; keeps interest/finance-cost expenses above EBIT instead of below; makes expense-by-account reporting meaningless for both manual and imported expenses. Recommend `expense_account()` parse the leading code from `category` and look up `Account` by code directly (see §2).
3. **Medium (carried over):** `/reports/cash-flow-13week` (`payroll.py:1991-2098`) still does not model outstanding creditor (PO) payments or VAT201 liabilities as distinct weekly outflows (`other_payments`/`vat_payment` hard-coded `0.0`).
4. **Low (carried over):** the `/coa` custom-account feature lets users add accounts to the `CompanyAccount` table and select them in expense dropdowns, but nothing in `journal.py` posts to a custom account by code (it only knows the fixed `Account` table seeded by `init_accounts()`/`DEFAULT_ACCOUNTS`). A user-created custom account remains effectively decorative until item 2 is fixed the recommended way (which would also make custom accounts postable, since it resolves by code against the real `Account` table).

**Standing reminders (not defects, carried from prior reports):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry (`payroll.py`) after Budget Feb 2027 and restart the backend;
(b) early-2027 runs should execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`);
(c) the AFS PayFast payment/ad-hoc tokenization feature and the `/reports/ai-insights` feature remain outside this audit's scope;
(d) NBCPSS private security payroll mode predates this audit's baseline, not yet part of this checklist's explicit scope;
(e) file-attribution note: the imported-equity-offset (3998/3999) exclusion logic lives in `payroll.py`'s `balance_sheet()`, not `financial_statements.py`;
(f) 2026 draft TLAB/TALAB comment period closed on schedule 28 August 2026 with no bill finalisation news yet as of this run — next run should keep checking for Treasury's review outcome or Parliamentary introduction;
(g) `parent_company_id`/`user_type` columns and bookkeeper-onboarding/consolidated-billing/accountant-fee-structure features remain outside Reports/Debtors/Creditors/AFS/tax scope, awareness only;
(h) legacy unused constants `PAYROLL_PER_EMP = 34.00` / `PAYROLL_MIN = 99.00` in `payroll.py` — still worth a cleanup pass, not a compliance issue;
(i) the cosmetic comment/statement-duplication artifact (`_SubscriptionGateMiddleware` line in `main.py`, `resp = None` in `billing.py`'s `adhoc_charge()`) — no new commits since 08-26, so no further growth to report; worth checking again once new commits land;
(j) compulsory VAT-registration turnover threshold rises to R2,300,000 (from R1,000,000), voluntary to R120,000 (from R50,000), effective 1 April 2026 — not gated anywhere in-scope, awareness only;
(k) the 13-week cash-flow forecast feature (`payroll.py:1991-2098`, `ForecastView` in `App_js_fixed.js`) remains additive and outside the original checklist's endpoint list — tracked via action item 3;
(l) the persistent Chart of Accounts feature (`/coa` router in `companies.py`, `CompanyAccount` in `database.py`, `ChartOfAccounts`/`Expenses` components in `App_js_fixed.js`) is additive and outside the original checklist's endpoint list — tracked via action items 2 and 4 until resolved.
