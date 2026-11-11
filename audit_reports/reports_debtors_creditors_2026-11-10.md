# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 10 November 2026 (scheduled run, 22:16 UTC)
**Prior report:** 2026-11-09

**Method:** static review (git log/diff a8c00fb → HEAD e3b85a4; `ast` parse of payroll, main, csv_import, journal, financial_statements, database, purchase_orders, fixed_assets, config, billing, quickbooks_migrate — all OK; grep anchor checks). No live DB / pytest. **No code edited this run** (5b already implemented).

**Changes since last report:** 6 commits (109af77 → e3b85a4). Relevant: (a) **plans.py now tracked** (109af77) — last run's High item resolved; (b) payroll add-on price single-sourced in `config.calc_payroll_monthly` (config.py:17; payroll.py:1140, 4774, 4815, 4939; billing.py:49) — `calculate_all` fee changed from flat R34/employee to the tiered formula; (c) csv_import.py: QuickBooks account-type strings in `_guess_account_type`/`_parse_account_type_exact` (csv_import.py:876-944), new `/import/fixed_assets/preview` (csv_import.py:2533); (d) new `/qbo/general-ledger` endpoint (quickbooks_migrate.py) + wizard step (App_js_fixed.js:15668); (e) fixed-asset import template now "Useful Life Years".

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | **PASS** — `_to_zar` (payroll.py:23), `VAT_RATE` (payroll.py:20) intact |
| Debtors (AR) | **PASS** — unchanged |
| Creditors (AP) | **PASS** — reversal-aware sources + `decrypt_field` intact (payroll.py:4361-4363) |
| Cross-module | **FAIL (new High ×2)** — fixed-asset useful-life ×12 bug; QBO GL endpoint crashes after commit |
| IFRS (AFS) | **PASS (data risk via item 1)** — deferred tax verified; no standards change |
| Tax (SARS) | **PASS** — 2026/2027 present; MTBPS (21 Oct 2026) announced no rate changes found |

**Overall: 0 Critical, 2 High (new), 3 Medium, Lows carried. Prior High (untracked plans.py) — RESOLVED.**

## 2. Reports
✓ No issues found. Payroll fee in `calculate_all` now uses tiered `calc_payroll_monthly` (payroll.py:1140) — this is ZuZan's subscription fee shown on the payroll run, not an employer cost; it does not flow into expense totals ✓.
- Low (carried): displaced docstrings after plan checks (`cash_flow_13week`, `creditors_aging`).

## 3. Debtors
✓ No issues found.

## 4. Creditors
✓ No issues found. `purchase_order_reversal` refs unchanged: payroll.py 6, purchase_orders.py 2, journal.py 1, financial_statements.py 2.
- Medium (carried): confirm intended plan gating on creditors-aging/reconciliation/13-week cash flow and frontend 403 handling.

## 5. Cross-module
- Journal coverage (invoice payments, expense payments, PO receipts, PO payments, payroll) unchanged ✓. Journal-integrity 2026-11-09: 0 gaps.
- Import-awareness: unbalanced groups still rejected (csv_import.py:1481-1527) ✓; Rules 6/7 / 3998-3999 untouched ✓.
- **High (new) — fixed-asset useful life inflated ×12.** csv_import.py:2416 (import) and :2603 (preview): `if "year" in hdr_text or "effective" in hdr_text or "life" in hdr_text:` treats the value as **years**. Every months header in `FIXED_ASSET_ALIASES` (csv_import.py:2283-2291: "useful_life_months", "Useful Life Months", "life (months)", "life_in_months") contains "life", so 60 months becomes 720 months (60 yrs). Introduced 33cbd44 (2026-11-09). ZuZan's own template used "Useful Life Months" until c329baf (2026-11-10), so any file built from it — and any Xero/other months export — is affected. Impact: depreciation understated, PPE carrying value overstated, deferred tax overstated in the AFS. Preview warns only above 480 months, so a 36-month life (→432) passes silently. Fix: test `"month" in hdr_text` first (→ months), then year/effective/life (→ years); re-check assets imported since 2026-11-09 (useful_life_months > 480 or multiples of 12×expected).
- **High (new) — `/qbo/general-ledger` returns 500 after importing.** quickbooks_migrate.py (end of `import_qbo_general_ledger`): `pick(r, "type", "accounttype") for r in actual_rows[:20]` — `actual_rows` are lists from `CI._read_csv` (csv_import.py `_read_csv` → `list[list[str]]`), but `pick` (xero_migrate.py:64) calls `row.get` → AttributeError. This runs **after** `CI.import_general_ledger` has committed, so data imports but the user sees an error and may retry (duplicate-signature check limits damage). Fix: check `hkeys` for "type"/"accounttype" instead.
- Medium (new) — QBO GL sign/grouping assumptions untested: amounts are negated only for credit-normal accounts identified by a type column or a 2/3/4 code prefix; QBO GL exports usually have neither, so income/liability lines stay debit-signed and groups will be rejected as unbalanced. Reference falls back to Transaction Type ("Invoice") when Num is blank, merging unrelated transactions into one group. Test with a real QBO export before release.
- Low (new): `_guess_account_type` keyword "loan" still classifies "Loan to director" (asset) as liability (pre-existing; QBO types now matched exactly first, which helps).
- Medium (carried): owner to review account types in companies that imported a GL before 2026-11-05.

## 6. IFRS compliance (AFS)
- Framework unchanged: IFRS for SMEs (2nd ed.). IFRS 18 and IFRS for SMEs 3rd edition effective for periods beginning on/after 1 Jan 2027 (first affected ZuZan FY starts 1 Mar 2027). No new SA-specific change found; `ifrs_smes_3rd_edition_transition_plan.md` stands.
- **5b deferred tax — verified (not hard-coded):** financial_statements.py:286-288 opening/closing `_deferred_tax_balance`, :672 `total_tax = current + deferred`, :113 `_wt_rate_pct` unit handling, CIT via `fixed_assets.SA_CIT_RATE` = 0.27 (fixed_assets.py:84). Note: correct computation, but the item-1 import bug feeds it wrong useful lives.
- Finance costs below EBIT; tax from `profit_before_tax` ✓ (unchanged file since 11-09).
- Sources: [Accounting Academy SA — IFRS for SMEs 3rd ed.](https://www.accountingacademy.co.za/news/read/updated-ifrs-for-smes-3rd-edition), [ACTS — IFRS 18 (Apr 2026)](https://acts.co.za/news/blog/2026/04/ifrs-18-financial-statement-presentation), [IFRS Foundation Nov 2026 IASB update](https://www.ifrs.org/content/dam/ifrs/meetings/2026/november/gpf/ap1a-iasb-update.pdf).

## 7. Tax updates (company + payroll)
- Tax year at run date: **2026/2027**. `TAX_YEARS["2026/2027"]` payroll.py:294; provisional "2027/2028" payroll.py:314; `_current_tax_year` payroll.py:332; `SDL_RATE=0.01` payroll.py:352; UIF 1%+1%, ceiling R17,712; VAT 15% (payroll.py:20); CIT 27% (fixed_assets.py:84). Unchanged.
- MTBPS delivered 21 Oct 2026: revenue projections revised up; search found no announced rate changes (rates are set in the Feb 2027 Budget).
- Sources: [Deloitte — 2026 MTBPS](https://www.deloitte.com/za/en/services/tax/perspectives/2026-medium-term-budget-policy-statement.html), [Gov.za — MTBPS 2026 speech](https://www.gov.za/news/budget/minister-enoch-godongwana-mtbps-speech), [TimesLive 21 Oct 2026](https://www.timeslive.co.za/news/2026-10-21-tax-revenue-projections-up-r171bn-for-2026-27/), [BDO — corporate tax unchanged (Budget 2026)](https://www.bdo.co.za/en-za/insights/2026/budget-speech/corporate-tax-remains-unchanged,-with-a-pinch-of-positivity). Search returned link lists only. No tax-table edits made.

## 8. Action items
**Critical:** none.

**High**
1. Fixed-asset import/preview useful-life unit bug (csv_import.py:2416, 2603) — check "month" before "life"; audit assets imported since 2026-11-09.
2. `/qbo/general-ledger` crashes after commit (`pick` on list rows) — quickbooks_migrate.py, final warning block.

**Medium**
3. Test QBO GL sign convention and Num-less grouping with a real export.
4. Confirm plan gating on creditors-aging/reconciliation/13-week cash flow + frontend 403 handling (carried).
5. Owner: review account types for GL imports before 2026-11-05 (carried).

**Low**
6. Docstrings displaced by plan checks (carried).
7. `_wt_rate_pct` unit heuristic — normalise storage (carried).
8. "loan" keyword misclassifies loan assets.
9. POPIA/Privacy Policy coverage of AI-context disclosure (carried).
10. Run full pytest locally, incl. test_payroll_price, test_plan_gates, test_import_payments (carried).
11. Untracked leftovers: commit_and_push.ps1, zuzan-app/public/sw.js, zuzan-backend/_to_delete/, find_default_password_accounts.py, fix_credit_note_vat_account.py (carried).
12. Normalise CRLF line endings (carried).

**Resolved since last run:** plans.py untracked (109af77).

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS-for-SMEs 3rd-ed. / IFRS 18 checklist Jan–Feb 2027.

---
## Fixes addendum — 2026-11-11 (owner-requested, uncommitted; run commit_and_push.bat to ship)
| # | Item | Status |
|---|---|---|
| 1 | FA useful-life ×12 | **Fixed** — new `csv_import._life_header_is_years` checks "month" first; used by import and preview. `zuzan-backend/check_fixed_asset_useful_life.py` (dry run by default; `--apply <ids>`) lists suspect assets in prod for review. |
| 2 | `/qbo/general-ledger` 500 after commit | **Fixed** — `pick()` on list rows removed. |
| 3 | QBO GL sign/grouping | **Fixed** — accounts resolved against the ZuZan chart by name (code passed through, so no duplicate asset-typed accounts); then by type column, then by account name (`_guess_account_type`), then by code prefix; unclassifiable accounts listed in warnings. Debit/Credit columns supported. Ref = "Type Num" (or Type when Num is blank) per date. Memo/Description column fixed. 10 MB upload limit added. |
| 4 | Plan gating / 403 | **Verified + hardened** — frontend gates match backend (creditors + recon = Professional, 13-week = Business). Creditors no longer shows sample vendors to real users when the request fails; it shows the error (App_js_fixed.js Creditors). |
| 5 | GL account-type review (pre-2026-11-05 imports) | **Open — owner action** (needs production DB; run `/import/reclassify-gl-accounts?dry_run=true` per company). |
| 6 | Displaced docstrings | **Fixed** (payroll.py `cash_flow_13week`, `creditors_aging`). |
| 7 | `wear_and_tear_rate` unit | **Fixed** — stored as % p.a.: CSV import uses `_parse_wt_rate_pct`; idempotent migration converts legacy decimals (≤1) ×100 (database.py, inside the migrations list); `_wt_rate_pct` reads ≤1 as legacy decimal (1.0 = 100%). |
| 8 | "loan" keyword | **Fixed** — "Loan to …" / "Loans receivable" classify as assets. |
| 9 | POPIA / AI disclosure | **Drafted** — `privacy.html` (DRAFT, placeholders, needs legal review). Note: netlify.toml publishes only index.html, so zuzan.co.za/privacy (linked from sign-up and landing) appears to have no page; publish steps are in the file header. |
| 10 | Full pytest | **Done** — 238 passed, 1 skipped (incl. new tests/test_audit_fixes_2026_11_11.py, 8 tests). JSX parse of App_js_fixed.js OK. |
| 11 | Untracked leftovers | **Fixed** — commit_and_push.bat now stages sw.js (registered by src/index.js), commit_and_push.ps1, privacy.html and the Render-shell scripts; `zuzan-backend/_to_delete/` added to .gitignore. |
| 12 | CRLF normalisation | **Not done (deliberate)** — renormalising would rewrite every line of payroll.py and other files in one diff; recommend a separate `.gitattributes` + `git add --renormalize .` commit when no other work is in flight. |
