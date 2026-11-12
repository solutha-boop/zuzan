# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 11 November 2026 (scheduled run, 22:11 UTC)
**Prior report:** 2026-11-10 (incl. fixes addendum 2026-11-11)

**Method:** static review (git log/diff e3b85a4 → HEAD 6b071ac; `ast` parse of payroll, main, csv_import, journal, financial_statements, database, purchase_orders, quickbooks_migrate, fixed_assets — all OK; grep anchor checks). No live DB / pytest. **No code edited this run** (5b already implemented; tax tables report-only).

**Changes since last report:** 6 commits. (a) 2546493 / b8c4321 / 9a53ed7 — the 2026-11-10 audit fixes are now **committed** (FA useful-life months bug, QBO GL import, wear-and-tear unit, creditors error state, privacy draft, leftovers). (b) f655f88 / df02e76 — QB trial-balance blank first-column header fix. (c) **6b071ac — new `AccountType.cogs`** ("Revenue / Cost of Sales / Gross Profit" P&L). Item (c) is not wired through the whole ledger and introduces the new findings below.

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | **PASS (with Medium)** — `_to_zar` (payroll.py:23), `VAT_RATE` (payroll.py:20) intact; management P&L now splits Cost of Sales correctly |
| Debtors (AR) | **PASS** — unchanged |
| Creditors (AP) | **PASS** — reversal-aware sources + `decrypt_field` intact (payroll.py:4369-4371) |
| Cross-module | **FAIL (new High ×3)** — new `cogs` account type ignored by balance sheet, `account_balance` and import sign logic |
| IFRS (AFS) | **PASS** — AFS handles `cogs` correctly (P&L, retained earnings, opening RE); deferred tax verified; no standards change |
| Tax (SARS) | **PASS** — 2026/2027 present; no new rate announcements |

**Overall: 0 Critical, 3 High (new), 2 Medium (1 new), Lows. Prior run's High ×2 and Mediums 3/4 — RESOLVED and committed.**

## 2. Reports
✓ Revenue/outstanding/expense logic unchanged. Management accounts (payroll.py:3896-3897) add `total_cogs = po_cogs + gl cogs_total`; `total_expenses` already contains both, and the frontend shows Gross Profit = revenue − total_cogs and OpEx = total_expenses − total_cogs (App_js_fixed.js:6984-6988) — no double count ✓.
- Low (new): `_gl_import_expenses` early return when no expense/cogs accounts (payroll.py:221-222) omits `cogs_total` — harmless (callers use `.get`) but inconsistent shape.
- Medium (new): 6-month trend loop still reports `gross_profit = rev − exp` (payroll.py:3976) where `exp` includes all opex; label is misleading now that a real Gross Profit exists. Rename to operating profit or subtract only COGS.

## 3. Debtors
✓ No issues found.

## 4. Creditors
✓ No issues found. `purchase_order_reversal` refs unchanged: payroll.py 6, purchase_orders.py 2, journal.py 1, financial_statements.py 2.

## 5. Cross-module
Journal coverage (invoice payments, expense payments, PO receipts, PO payments, payroll) unchanged ✓. Import-awareness ✓ (unbalanced groups rejected; Rules 6/7 and 3998/3999 untouched; non-ZAR imports still require a rate).

**New `AccountType.cogs` (6b071ac) — accounts of this type are created by CSV/TB/GL imports (`_guess_account_type` "cost of sales"/"purchases"/…, csv_import.py:903-905), Xero code 3xx (csv_import.py:1026), Xero type "Direct Costs" (csv_import.py:992) and QBO GL. The seeded 5000 Cost of Sales stays `expense`, so native-only companies are unaffected; importing companies are.**

- **High (new) — Balance sheet omits COGS from retained income.** payroll.py:2836-2839 sums only `AccountType.revenue` and `AccountType.expense`. Every rand on a `cogs` account is left out of equity, so Assets ≠ Liabilities + Equity (Rule 1 fails) and the dashboard balance sheet disagrees with the AFS (financial_statements.py:335-341, which does include cogs). Fix: `Account.type.in_([AccountType.expense, AccountType.cogs])` at :2837.
- **High (new) — `account_balance` treats `cogs` as credit-normal.** journal.py:1537 `if account.type in (AccountType.asset, AccountType.expense)` → COGS balances come out negative on the Trial Balance "balance" column and anywhere else this helper is used (including the fix above, which relies on it). Fix: add `AccountType.cogs` to the debit-normal tuple.
- **High (new) — imports post COGS on the wrong side / reject it.**
  - `_signed_dr_cr` (csv_import.py:934) — Trial Balance / Balance Sheet imports using a single Balance column post a positive Cost of Sales balance as a **credit** (csv_import.py:1235, 1328). Before 6b071ac these rows typed as `expense` and posted as debits. Fix: add `AccountType.cogs` to the tuple.
  - P&L import (csv_import.py:1418) raises "Cannot tell whether '…' is income or an expense" for any Cost of Sales/Purchases row — a regression: standard P&L exports now lose their COGS lines. Fix: accept `cogs` and post it like `expense` (else-branch at :1425 already does the debit side).
  - `reclassify-gl-accounts` (csv_import.py:1654) `_debit_types` lacks `cogs`, so Xero 3xx code inference is never trusted for debit-balance accounts. Note the owner action from last run (run reclassify per company) **will now retag "Cost of Sales"/"Direct Costs" accounts as `cogs` via `_type_from_xero_name`** — do not run it until the three fixes above ship.
- Medium (new): no grep-visible frontend option for creating/editing a `cogs` account in the chart of accounts; confirm the account-type dropdown and CoA grouping display "Cost of Sales" rather than an unknown type.
- Tests: none of tests/ cover `cogs` in the balance sheet or TB — add one asserting Rule 1 holds with a cogs account.

## 6. IFRS compliance (AFS)
- Framework unchanged: IFRS for SMEs (2nd ed.). IFRS 18 and IFRS for SMEs 3rd edition effective for periods beginning on/after 1 Jan 2027 (first affected ZuZan FY starts 1 Mar 2027); no new SA-specific change found. `ifrs_smes_3rd_edition_transition_plan.md` stands.
- AFS COGS change verified: `cogs` accounts always in Cost of Sales (financial_statements.py:218-223, 269), included in closing (:335-341) and opening (:400-406) retained earnings ✓. Gross profit presentation (revenue − cost of sales) is consistent with IFRS for SMEs s5 function-of-expense analysis ✓.
- **5b deferred tax — verified (not hard-coded):** `deferred_tax` = period movement (financial_statements.py:690), CIT `fixed_assets.SA_CIT_RATE` = 0.27 (fixed_assets.py:84). Useful-life import bug that fed it wrong lives is fixed (csv_import.py:2288 `_life_header_is_years`); run `check_fixed_asset_useful_life.py` in prod (carried).
- Finance costs below EBIT; tax from `profit_before_tax` ✓.
- Sources: [Accounting Academy SA — IFRS for SMEs 3rd ed.](https://www.accountingacademy.co.za/news/read/updated-ifrs-for-smes-3rd-edition), [PKF SA — IFRS for SMEs 2026](https://www.pkf.co.za/news/2026/ifrs-for-sme-conceptual-framework/), [IFRS — 2025 IFRS for SMEs supporting materials](https://www.ifrs.org/content/ifrs/home/supporting-implementation/2025-ifrs-for-smes-supporting-materials.html).

## 7. Tax updates (company + payroll)
- Tax year at run date: **2026/2027**. `TAX_YEARS["2026/2027"]` payroll.py:298; provisional "2027/2028" payroll.py:318; `_current_tax_year` payroll.py:336; `SDL_RATE = 0.01` payroll.py:356; UIF 1%+1%, ceiling R17,712 (payroll.py:311); VAT 15% (payroll.py:20); CIT 27% (fixed_assets.py:84). Unchanged since last run.
- No new rate announcements since the 21 Oct 2026 MTBPS; rates next change at Budget (Feb 2027).
- Sources: [SARS — rates of tax for individuals](https://www.sars.gov.za/tax-rates/income-tax/rates-of-tax-for-individuals/), [Werksmans — Budget 2026/27 tax overview](https://werksmans.com/budget-speech-2026-2027-tax-overview/), [National Treasury — 2026 draft Rates Bill](https://www.gov.za/news/media-statements/national-treasury-publication-2026-draft-rates-and-monetary-amounts-and). No tax-table edits made.

## 8. Action items
**Critical:** none (escalate item 1 to Critical if any production company already holds `cogs`-typed accounts).

**High**
1. Balance sheet: include `AccountType.cogs` in the P&L-to-equity sum (payroll.py:2837).
2. `account_balance`: treat `cogs` as debit-normal (journal.py:1537).
3. Imports: add `cogs` to `_signed_dr_cr` (csv_import.py:934), accept it in the P&L import (csv_import.py:1418), and to `_debit_types` (csv_import.py:1654). Hold the owner's reclassify run until 1-3 ship.

**Medium**
4. Trend `gross_profit` label/calc now inconsistent with the real Gross Profit (payroll.py:3976).
5. Frontend CoA create/edit and grouping for the `cogs` type; add a Rule-1 test with a cogs account.
6. Owner: review GL account types for pre-2026-11-05 imports (carried — after items 1-3).

**Low**
7. `_gl_import_expenses` early-return shape (payroll.py:222).
8. POPIA privacy page: draft needs legal review and Netlify publishing (carried).
9. Run `check_fixed_asset_useful_life.py` dry run in prod (carried).
10. CRLF normalisation as a standalone commit (carried).

**Resolved since last run:** FA useful-life ×12; QBO GL 500; QBO sign/grouping; plan-gating/403; displaced docstrings; wear-and-tear unit; "loan" keyword; untracked leftovers — all committed (2546493 → 9a53ed7).

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS for SMEs 3rd ed. / IFRS 18 checklist Jan–Feb 2027.

---
## Fixes addendum — 2026-11-12 (owner-requested, uncommitted; run commit_and_push.bat to ship)
| # | Item | Status |
|---|---|---|
| 1 | Balance sheet omits COGS | **Fixed** — payroll.py balance sheet sums `expense` + `cogs` into retained income. |
| 2 | `account_balance` sign | **Fixed** — journal.py treats `cogs` as debit-normal (trial balance, balance sheet, AR/AP helpers). |
| 3 | Imports | **Fixed** — `_signed_dr_cr`, P&L import type check and reclassify `_debit_types` in csv_import.py all include `cogs`. The reclassify hold is lifted once this ships. |
| 4 | Trend gross profit | **Resolved by design** — "gross profit" across the app means revenue − expenses (excl. payroll) and the dashboard chart is captioned that way, so the key is kept; each trend month now also returns `cogs` (PO/stock cost + GL-imported cogs). |
| 5 | Frontend / tests | **Fixed** — Trial Balance view now has a "Cost of Sales" group (cogs accounts were previously dropped from the table); there is no account-type dropdown in the UI to update. New tests/test_cogs_account_type.py (4 tests; 3 fail on the old code, all pass now). |
| 6 | GL account-type review | **Open — owner action** (run after shipping). |
| 7 | `_gl_import_expenses` shape | **Fixed** — early return includes `cogs_total`. |

Verification: full pytest 242 passed, 1 skipped (run on a scratch copy because the payroll journal runner needs to delete its temp DB, which the connected folder doesn't allow); JSX parse of App_js_fixed.js OK; zuzan-app/src/App.js kept identical. Items 8–10 (privacy page legal review, FA useful-life prod check, CRLF) are owner/ops tasks and unchanged.
