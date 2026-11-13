# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 12 November 2026 (scheduled run, 22:10 UTC)
**Prior report:** 2026-11-11 (incl. fixes addendum 2026-11-12)

**Method:** static review (git log/diff 6b071ac → HEAD 2e159eb; grep anchor checks across backend + App_js_fixed.js). Working tree clean. No live DB / pytest this run. **No code edited** (5b already implemented; tax tables report-only).

**Changes since last report:** 1 commit — **2e159eb** (12 Nov 22:24 SAST) ships the whole 2026-11-12 fixes addendum: balance-sheet COGS (payroll.py:2838), `account_balance` debit-normal COGS (journal.py:1537), import fixes (csv_import.py:934, 1418, 1654), trend `cogs` field (payroll.py:3976-3981), `_gl_import_expenses` shape (payroll.py:222), Trial Balance "Cost of Sales" group (App_js_fixed.js:6491-6493, 6563), tests/test_cogs_account_type.py. `App_js_fixed.js` and `zuzan-app/src/App.js` are byte-identical. Other backend files with new mtimes (auth, companies, billing, main) have no content diff vs HEAD.

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | **PASS** — `_to_zar` (payroll.py:23), `VAT_RATE` (payroll.py:20) intact; trend now exposes `cogs` |
| Debtors (AR) | **PASS** — unchanged |
| Creditors (AP) | **PASS** — unchanged; reversal-aware |
| Cross-module | **PASS (Lows)** — prior High ×3 resolved & committed; two minor COGS-type consistency notes |
| IFRS (AFS) | **PASS** — no standards change; deferred tax verified |
| Tax (SARS) | **PASS** — 2026/2027 present; no new announcements |

**Overall: 0 Critical, 0 High, 0 Medium open in code. Prior High ×3 and Medium ×2 (items 1–5, 7) RESOLVED and committed.**

## 2. Reports
✓ No issues found. Trend loop (payroll.py:3973-3981) computes `cogs_m = po_c + GL cogs_total`; `po_c` is defined in-loop and already included in `exp`, so `cogs` is a subset, not an addition — no double count. `gross_profit` key kept with its documented app-wide meaning.

## 3. Debtors
✓ No issues found.

## 4. Creditors
✓ No issues found.

## 5. Cross-module
Journal coverage (invoice/expense payments, PO receipts/payments, payroll) unchanged ✓. Import-awareness unchanged ✓.
`AccountType.cogs` wiring re-checked: every debit-normal tuple and P&L-type filter now includes `cogs` (payroll.py:219, 2838; journal.py:1537; csv_import.py:934, 1418, 1654); AFS handles it (financial_statements.py:218-223). Remaining notes:
- Low (new): `xero_migrate.py:142` still maps "direct cost / cost of sales / cogs" names to `AccountType.expense`, while csv_import maps the same names to `cogs` (csv_import.py:903-905, 992, 1026). Not a balance error (both are debit-normal P&L), but the same Xero data lands in Cost of Sales via CSV and in operating expenses via API migration unless the AFS name/code matching catches it. Align to `cogs`.
- Low (new): custom CoA group "Cost of Sales" maps to `AccountType.expense` (journal.py:189). Same consistency point — user-created Cost of Sales accounts don't get the `cogs` type.
- Owner action (carried): run `reclassify-gl-accounts` / review GL account types for pre-2026-11-05 imports — the hold is now lifted since the fixes shipped.

## 6. IFRS compliance (AFS)
- Framework unchanged: IFRS for SMEs (2nd ed.) presentation. IFRS 18 and IFRS for SMEs 3rd edition remain effective for periods beginning on/after 1 Jan 2027 (first affected ZuZan FY: 1 Mar 2027); no new SA-specific change found this run. Transition plan stands.
- **5b deferred tax — verified (still computed, not hard-coded):** `"deferred_tax": deferred_tax_expense` (financial_statements.py:690); CIT `SA_CIT_RATE = 0.27` (fixed_assets.py:84). financial_statements.py unchanged since prior run.
- Finance costs below EBIT (financial_statements.py:232-238); tax from profit_before_tax ✓.
- Sources: [Accounting Academy SA — IFRS for SMEs 3rd ed.](https://www.accountingacademy.co.za/news/read/updated-ifrs-for-smes-3rd-edition), [Forvis Mazars SA — new edition IFRS for SMEs](https://www.forvismazars.com/za/en/services/audit-assurance/financial-reporting/ifrs-for-smes-R-accounting-standard), [IFRS — June 2026 SME update](https://www.ifrs.org/content/ifrs/home/supporting-implementation/2015-ifrs-for-smes-supporting-materials/sme-updates/2026/june-2026-ifrs-for-smes-accounting-standard-update.html).

## 7. Tax updates (company + payroll)
- Tax year at run date: **2026/2027**. `TAX_YEARS["2026/2027"]` payroll.py:298; provisional "2027/2028" payroll.py:318; `_current_tax_year` payroll.py:336; `SDL_RATE = 0.01` payroll.py:356; UIF 1%+1%, ceiling R17,712; VAT 15% (payroll.py:20); CIT 27% (fixed_assets.py:84). Unchanged.
- No new rate announcements since the Oct 2026 MTBPS; next change expected at Budget (Feb 2027).
- Sources: [Moonstone — MTBPS revenue outlook](https://www.moonstone.co.za/?p=62356), [TaxTim — Budget 2026](https://www.taxtim.com/za/blog/budget-2026), [SARS — What's new](https://www.sars.gov.za/whats-new-at-sars/2). No tax-table edits made.

## 8. Action items
**Critical / High / Medium:** none open.

**Low**
1. Align `xero_migrate.py:142` Cost-of-Sales name mapping to `AccountType.cogs` (consistency with CSV import).
2. Consider mapping custom CoA group "Cost of Sales" to `AccountType.cogs` (journal.py:189).
3. Owner: run GL account-type review / reclassify for pre-2026-11-05 imports (carried; now unblocked).
4. POPIA privacy page: legal review + Netlify publish (carried).
5. Run `check_fixed_asset_useful_life.py` dry run in prod (carried).
6. CRLF normalisation as a standalone commit (carried).

**Resolved since last run:** balance-sheet COGS, `account_balance` sign, import COGS handling, trend cogs, `_gl_import_expenses` shape, Trial Balance Cost of Sales group + tests — all committed in 2e159eb.

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS for SMEs 3rd ed. / IFRS 18 checklist Jan–Feb 2027.

---
## Fixes addendum — 2026-11-13 (owner-requested)
| # | Item | Status |
|---|---|---|
| 1 | Xero migration Cost-of-Sales type | **Fixed (uncommitted)** — `xero_migrate.classify_account_type` now types "Direct Costs / Cost of Sales / Cost of Goods Sold / COGS" as `cogs`. Also fixes a hidden bug found while editing: "Cost of Sales" matched the "sales" keyword first and was typed as **revenue**. |
| 2 | Custom CoA "Cost of Sales" group | **Fixed (uncommitted)** — journal.py `_COA_GROUP_TO_ACCOUNT_TYPE` maps it to `cogs`. Forward-looking: custom accounts already synced to the ledger keep their `expense` type (the AFS still shows them under Cost of Sales by name/code). Built-in picker codes 5010–5050 auto-created by `expense_account` are still `expense` (backend doesn't know the group). |
| 3 | GL account-type review / reclassify | **Open — owner action** (production). |
| 4 | POPIA privacy page | **Open — owner action** (legal review, Netlify). |
| 5 | `check_fixed_asset_useful_life.py` in prod | **Open — owner action**. |
| 6 | CRLF normalisation | **Done — local commit 4003d8b (not pushed)**, whitespace-only (`git diff -w` empty): .gitignore, README.md, main_py_fixed*.py, auth/billing/companies/main/payroll/test_reg.py. Root cause fixed: `patch_backend.py` rewrote five backend files in Windows text mode on every commit_and_push run; its writes now use `newline="\n"`. |

Verification: 2 new tests in tests/test_cogs_account_type.py; full pytest 244 passed, 1 skipped (scratch copy). Run commit_and_push.bat to commit items 1–2 and push both commits.
