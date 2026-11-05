# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 4 November 2026 (scheduled run)
**Prior report:** 2026-11-03

**Change detection:** HEAD moved from `aa1b13f` to `a1db4d1` (many "sync working copy" commits). Ignoring CRLF-only churn (payroll.py / companies.py show whole-file diffs), real changes are in: `csv_import.py` (+222), `payroll.py` (+100), `journal.py` (+21), `App_js_fixed.js` / `zuzan-app/src/App.js` (+96 each). Static review only (no live DB / pytest). **No code edited** (5b already implemented).

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | **PASS with Medium issues** — core `_to_zar`/revenue logic unchanged; NEW GL-import revenue/expense feed only management accounts (inconsistent with dashboard, double-count risk) |
| Debtors (AR) | **PASS** — unchanged |
| Creditors (AP) | **PASS** — reversal-aware sources intact (payroll.py:3058, 3529, 4290; purchase_orders.py:505; journal.py:1347; financial_statements.py:610); `decrypt_field` payroll.py:4333-4335 |
| Cross-module | **FAIL (Critical)** — new Xero account-type inference can retype ZuZan system accounts (2000/2100→revenue, 3xxx/4000→expense) |
| IFRS (AFS) | **PASS** — no change; deferred tax verified |
| Tax (SARS) | **PASS** — 2026/2027 table present; no rate changes |

**Overall: 1 Critical, 2 High, 3 Medium, Low items carried.**

## 2. Reports
- `VAT_RATE = 0.15` payroll.py:20; `_to_zar` payroll.py:23; revenue uses `_received_net_zar`; `/v1/summary` main.py:519 still imports/uses `_to_zar`. ✓
- **Medium (NEW):** `_gl_import_income` / `_gl_import_expenses` (payroll.py:159, 195) are added only in `management_accounts` (payroll.py:3818, 3861, 3923, 3943). `/reports/dashboard` (payroll.py:2479 `_bank_import_income` only) and `/v1/summary` (main.py:524) do not include them → dashboard and management accounts will disagree for any company with a GL import.
- **Medium (NEW):** Double-count risk — GL import (source `import`) revenue/expense lines are added on top of invoice/expense/payroll/depreciation totals. If the same company imports both invoices/expenses CSVs AND a full GL (or the GL contains payroll/depreciation), revenue/expenses are counted twice. No guard (e.g. restrict to accounts without a matching ZuZan module source, or opening-balance-only). Also depends on the account type being right (see Cross-module Critical).
- Carried Low: `_build_company_context` main.py hard-coded 1.15.

## 3. Debtors
✓ No issues found.

## 4. Creditors
✓ No issues found.

## 5. Cross-module
- **CRITICAL (NEW): account types overwritten with Xero code-range logic.**
  - csv_import.py:853-871 `_infer_type_from_xero_code` maps 2xx→revenue, 3xx/4xx→expense. ZuZan's own chart uses GAAP ranges (journal.py:28-116: 1100 asset, 2000/2100 liability, 3xxx equity, 4000 revenue).
  - It is applied first for **every** GL/journal import (csv_import.py:1401-1404) and `_find_or_create_account` now **overwrites** the type of any existing account found by code, system accounts included (csv_import.py:927-928, no `is_system` guard).
  - `POST /import/reclassify-gl-accounts` (csv_import.py:1450-1481) does the same across the whole company chart in one call: Accounts Payable 2000 and VAT Output 2100 → revenue; equity 3xxx (incl. 3998/3999) and Sales Revenue 4000 → expense. This corrupts the balance sheet, P&L, AFS, Rules 6/7 and every report that filters by `Account.type`.
  - Fix: skip `is_system` accounts and only retype accounts created by import; make Xero logic opt-in (only when the file has the Xero `Name` type column), never from code range alone; never retype accounts that already have non-import journal lines.
- **High (NEW): `DELETE /import/all`** (csv_import.py:2016) uses `get_current_user` instead of `require_role("owner","admin","accountant")` — any user (incl. read-only/staff roles) can bulk-delete all import journal entries. It also deletes every non-system account with no journal lines (csv_import.py:2043-2053), which removes custom COA accounts the user created manually but hasn't used yet. Restrict by role; limit orphan deletion to accounts created by import.
- **High (NEW): frontend/back-end route mismatch** — App_js_fixed.js:6526 calls `/csv-import/reclassify-gl-accounts`; router prefix is `/import` (main.py:451), so the "Fix Account Types" button 404s (error shown as "Error: …"). Good news it cannot trigger the Critical bug from the UI today; fixing the path *without* fixing the Critical item would enable it. (`/import/all` call at App_js_fixed.js:16089 is correct.)
- Medium (NEW): `journal.py` list endpoint now defaults `limit=200` and accepts `date_from/date_to` (journal.py:1568-1592); the UI requests `limit=500` + date range. Fine functionally; note ledger tab silently truncates at 500 entries with no pagination indicator. Null-safe account access added ✓.
- Journal coverage (invoice payments, expense payments, PO receipts, PO payments, payroll) unchanged ✓. Import-awareness (backfill after invoice/expense import, Rules 6/7 excluding `import`, 3998/3999 on balance sheet, unbalanced group rejection) — no change to those code paths; the new `net_amount` single-column support still goes through the balance check. Not re-run live.
- Carried Low: journal.py:824-825 benefit JSON parse.

## 6. IFRS compliance (AFS)
- Framework unchanged: IFRS for SMEs (2nd ed.), financial_statements.py:2, 691, 794, 819. IFRS 18 and IFRS for SMEs 3rd ed. both effective for periods beginning on/after 1 Jan 2027; first affected ZuZan FY starts 1 Mar 2027. Searched again (Forvis Mazars, IFRS Foundation 2026 SMEs session, accountingacademy.co.za) — no change to the dates. Transition plan (`ifrs_smes_3rd_edition_transition_plan.md`) stands.
- **5b deferred tax — verified, not hard-coded:** financial_statements.py:674 `"deferred_tax": deferred_tax_expense`; `wear_and_tear_rate` database.py:606, migration database.py:1587 inside the list. No edits.
- Finance costs below EBIT / tax from PBT unchanged ✓.
- Note: AFS depends on `Account.type`; the Critical item above would misstate the AFS for affected companies.

## 7. Tax updates (company + payroll)
- Tax year **2026/2027** (run date 4 Nov 2026): `TAX_YEARS["2026/2027"]` payroll.py:276 (brackets to R245,100 … R1,878,600+; rebates R17,820 / R9,765 / R3,249; UIF ceiling R17,712); provisional `2027/2028` payroll.py:296; `_current_tax_year()` payroll.py:314. UIF 1%+1%, SDL 1% (payroll.py:333-334), VAT 15% (payroll.py:20), CIT 27% (payroll.py:2530, 3892) — all current. 
- Sources: [TaxTim Budget 2026](https://www.taxtim.com/za/blog/budget-2026), [EWN: R20bn tax hike withdrawn](https://www.ewn.co.za/2026/02/25/budget-2026-godongwana-withdraws-r20-billion-tax-hike), [Times Live: brackets adjusted](https://www.timeslive.co.za/politics/2026-02-25-budget-2026-godongwana-adjusts-tax-brackets-medical-credits-in-line-with-inflation/). No VAT/CIT rate change announced. No tax-table edits made.

## 8. Action items
**Critical**
1. csv_import.py:853-871, 927-928, 1401-1404, 1450-1481 — stop Xero code-range inference from retyping system/existing accounts; add `is_system` guard; restrict reclassify to import-created accounts. Check any company that already ran a GL import after 2026-11-03 for mis-typed 2000/2100/3xxx/4000 accounts.

**High**
2. csv_import.py:2016 — add `require_role(...)` to `DELETE /import/all`; don't delete unused custom COA accounts.
3. App_js_fixed.js:6526 — correct path to `/import/reclassify-gl-accounts` only AFTER item 1 is fixed (also sync `zuzan-app/src/App.js`).

**Medium**
4. Add `_gl_import_income/_expenses` to `/reports/dashboard` and `/v1/summary`, or remove from management accounts, so figures agree.
5. Guard GL-import revenue/expense against double counting with invoice/expense/payroll/depreciation modules.
6. Ledger tab: show "showing latest 500" / pagination.

**Low** (carried)
7. main.py `_build_company_context`: use `VAT_RATE`, fix "last payroll" query.
8. POPIA/Privacy Policy coverage of AI-context disclosure.
9. Run full pytest locally.
10. Untracked leftovers: `commit_and_push.ps1`, `zuzan-app/public/sw.js`, `zuzan-backend/_to_delete/`, `find_default_password_accounts.py`, `fix_credit_note_vat_account.py`.
11. Normalise line endings (payroll.py / companies.py show whole-file CRLF diffs, hiding real changes in review).

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS-for-SMEs 3rd-ed. checklist Jan–Feb 2027.

## 9. Fixes applied 2026-11-05 (follow-up)
1. **Critical** csv_import.py — Xero code-range inference removed from GL/journal import; `_find_or_create_account` retypes only with `retype=True` (Xero `Name` column) and never system accounts; `/import/reclassify-gl-accounts` limited to non-system, import-only accounts outside ZuZan's default chart codes with no native journal lines. **Action for owner:** any company that ran a GL import or reclassify before this fix should have accounts 2000/2100/3xxx/4000 types checked.
2. **High** `DELETE /import/all` now `require_role("owner","admin","accountant")`; orphan-account cleanup limited to accounts touched by the deleted import entries.
3. **High** App_js_fixed.js + zuzan-app/src/App.js — reclassify call now `/import/reclassify-gl-accounts`.
4. **Medium** GL-import income/expenses added to `/reports/dashboard` (payroll.py) and `/v1/summary` (main.py).
5. **Medium** `_gl_import_cutover` (payroll.py): GL-import P&L lines dated on/after the earliest native invoice/expense are ignored (no double-count). Payroll/depreciation accounts inside a pre-cutover GL are still counted — acceptable for historic data.
6. **Medium** journal tab shows a "latest 500" notice.
Syntax-checked only (ast); not run against a database or pytest.
