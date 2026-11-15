# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 13 November 2026 (scheduled run, 22:12 UTC)
**Prior report:** 2026-11-12 (incl. fixes addendum 2026-11-13)

**Method:** static review (git log/diff 2e159eb → HEAD 0315e76; grep anchor checks across backend + App_js_fixed.js; web check for SARS / IFRS announcements). Working tree clean; `main` in sync with `origin/main` (pushed). No live DB / pytest this run. **No code edited** (5b already implemented; tax tables report-only).

**Changes since last report:** 2 commits.
- **4003d8b** — CRLF→LF normalisation (whitespace only; `git diff -w` touches only `patch_backend.py`, whose writes now use `newline="\n"` at lines 47, 66, 77, 97, 126, 150). Backend files confirmed LF after the 21:15 UTC commit_and_push run.
- **0315e76** — ships addendum items 1–2: `xero_migrate.classify_account_type` types Direct Costs / Cost of Sales / COGS as `cogs` before the `sales` → revenue rule (xero_migrate.py:141-145); custom CoA group "Cost of Sales" → `AccountType.cogs` (journal.py:189); 2 new tests in tests/test_cogs_account_type.py. Also committed the 2026-11-12 report.

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | **PASS** — unchanged; `_to_zar` (payroll.py:23), `VAT_RATE` (payroll.py:20); main.py:523 imports `_to_zar` |
| Debtors (AR) | **PASS** — unchanged |
| Creditors (AP) | **PASS** — reversal-aware lookups intact (payroll.py:3085, 3559, 4331; purchase_orders.py:505; journal.py:1347) |
| Cross-module | **PASS** — both prior Lows resolved and pushed |
| IFRS (AFS) | **PASS** — no standards change; deferred tax verified |
| Tax (SARS) | **PASS** — 2026/2027 present; no new announcements |

**Overall: 0 Critical, 0 High, 0 Medium, 0 code Lows open. Remaining items are owner actions only.**

## 2. Reports
✓ No issues found. (No changes to payroll.py report logic since prior run beyond whitespace.)

## 3. Debtors
✓ No issues found.

## 4. Creditors
✓ No issues found. Per-PO AP lookups still net credit − debit and include `purchase_order_reversal` / `po_payment_reversal`.

## 5. Cross-module
✓ No issues found. Journal coverage (invoice/expense payments, PO receipts/payments, payroll) unchanged; import-awareness unchanged. COGS typing now consistent across CSV import, Xero migration and custom CoA.
- Residual note (unchanged from addendum, informational): custom accounts already synced before 0315e76 keep type `expense`; built-in picker codes 5010–5050 auto-created by `expense_account` are still `expense`. AFS still presents them under Cost of Sales by code/name, so no statement error. Covered by owner item 1 below.

## 6. IFRS compliance (AFS)
- Framework unchanged: IFRS for SMEs (2nd ed.) presentation (financial_statements.py:2, 707, 810). IFRS 18 and IFRS for SMEs 3rd edition remain effective for periods beginning on/after 1 Jan 2027 (first affected ZuZan FY: 1 Mar 2027). No new SA-specific change found this run — standards unchanged since prior report.
- **5b deferred tax — verified (still computed):** `"deferred_tax": deferred_tax_expense` (financial_statements.py:690); `wear_and_tear_rate` column + migration inside list (database.py:607, 1588); CIT `SA_CIT_RATE = 0.27` (fixed_assets.py:84). financial_statements.py unchanged.
- Finance costs below EBIT, tax from profit_before_tax — unchanged ✓.
- Sources: [Forvis Mazars SA — new edition IFRS for SMEs](https://www.forvismazars.com/za/en/services/audit-assurance/financial-reporting/ifrs-for-smes-R-accounting-standard), [Accounting Academy SA — IFRS for SMEs 3rd ed.](https://www.accountingacademy.co.za/news/read/updated-ifrs-for-smes-3rd-edition), [ACCA — third edition IFRS for SMEs](https://www.accaglobal.com/learning-and-events/corporate-reporting/third-edition-ifrs-for-smes).

## 7. Tax updates (company + payroll)
- Tax year at run date: **2026/2027**. `TAX_YEARS["2026/2027"]` payroll.py:298; provisional "2027/2028" payroll.py:318; `_current_tax_year` payroll.py:336; `SDL_RATE = 0.01` payroll.py:356; UIF 1%+1%, ceiling R17,712 (payroll.py:311); VAT 15% (payroll.py:20); CIT 27% (fixed_assets.py:84). Unchanged.
- No new rate announcements found; next change expected at Budget (Feb 2027).
- Sources: [SARS — What's new](https://www.sars.gov.za/whats-new-at-sars/2), [SARS — Budget](https://www.sars.gov.za/about/budget/), [TaxTim — Budget 2026](https://app.taxtim.com/blog/budget-2026). No tax-table edits made.

## 8. Action items
**Critical / High / Medium:** none open.

**Low (owner actions, carried)**
1. Run GL account-type review / `reclassify-gl-accounts` in production for pre-2026-11-05 imports and pre-0315e76 custom Cost of Sales accounts.
2. POPIA privacy page: legal review + Netlify publish.
3. Run `check_fixed_asset_useful_life.py` dry run in prod.

**Resolved since last run:** Xero migration COGS typing (incl. hidden "Cost of Sales"→revenue bug), custom CoA Cost of Sales → cogs, CRLF normalisation — all committed (4003d8b, 0315e76) and pushed.

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS for SMEs 3rd ed. / IFRS 18 checklist Jan–Feb 2027.
