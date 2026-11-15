# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 14 November 2026 (scheduled run)
**Prior report:** 2026-11-13

**Method:** static review (git status/diff vs HEAD 0315e76; grep anchor checks across backend; review of new file practice_mcp.py; web check for SARS / IFRS announcements). No live DB; pytest not installed in the local VM, so `tests/test_practice_mcp.py` was not run. **No code edited** (5b already implemented; tax tables report-only).

**Changes since last report:** no new commits. Uncommitted working-tree changes:
- **New `zuzan-backend/practice_mcp.py`** (+ `tests/test_practice_mcp.py`, untracked) — read-only MCP endpoint `POST /mcp` for a Claude practice connector; registered in main.py:421 and main.py:468.
- `commit_and_push.bat` — adds practice_mcp.py to the staged list and a new default commit message.
- The 2026-11-13 report is still untracked.
- No changes to payroll.py, financial_statements.py, journal.py, purchase_orders.py, csv_import.py or App_js_fixed.js since the last run.

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | **PASS** — unchanged; `_to_zar` (payroll.py:23), `VAT_RATE` (payroll.py:20), main.py:525 imports `_to_zar` |
| Debtors (AR) | **PASS** — unchanged; new MCP `debtors_aging` tool reuses the same function |
| Creditors (AP) | **PASS** — reversal-aware lookups intact |
| Cross-module | **PASS** — unchanged |
| IFRS (AFS) | **PASS** — no standards change; deferred tax verified |
| Tax (SARS) | **PASS** — 2026/2027 present; no new rate changes in force |

**Overall: 0 Critical, 0 High, 0 Medium. 1 new Low (informational) about the new MCP endpoint. Other open items are owner actions.**

## 2. Reports
✓ No issues found. Tax provision lines unchanged (payroll.py:2553, 3925 at 27%).

## 3. Debtors
✓ No issues found. `debtors_aging` (payroll.py:4230) still filters `sent/overdue/partial` (payroll.py:4240) and ages from `due_date` only (payroll.py:4246-4248).
- New: practice_mcp.py:135-137 calls `payroll.debtors_aging` directly with the practice user switched into the client company in memory only (practice_mcp.py:71-76, `db.expunge` first, so nothing is saved). Figures will match the in-app Debtors view.

## 4. Creditors
✓ No issues found. Per-PO AP lookups still net credit − debit and include `purchase_order_reversal` / `po_payment_reversal` (payroll.py:3085, 3559, 4331; purchase_orders.py:505; journal.py:1347).

## 5. Cross-module
✓ No issues found. Journal coverage and import-awareness unchanged since the last run.
- New MCP endpoint review (practice_mcp.py): read-only tools reuse `debtors_aging`, `vat201` (payroll.py:4488), `emp201` (payroll.py:3692) and `reconciliation` (payroll.py:2905) with matching signatures; `reconciliation` keeps its Professional-plan check because the check lives inside the function body (payroll.py:2910-2912). `_payroll_status` uses `Payslip.period` in YYYY-MM form, matching the rest of the app. Auth uses a constant-time compare and refuses tokens under 32 characters (practice_mcp.py:37-44); the session is rolled back and closed after every call (practice_mcp.py:227-229).
- **Low (informational):** `vat_registered` defaults to `True` when the attribute is missing (practice_mcp.py:194, 219, 226). That is harmless with the current Company model, but it could show VAT201 figures for a non-registered client if the field were ever renamed. Also, the new test file has not been run, so run `pytest tests/test_practice_mcp.py` before committing.

## 6. IFRS compliance (AFS)
- Framework unchanged: IFRS for SMEs (2nd ed.) presentation. IFRS 18 and IFRS for SMEs 3rd edition still take effect for periods beginning on or after 1 Jan 2027 (first affected ZuZan FY: 1 Mar 2027). No deferral or SA-specific change found. **Standards unchanged since the prior report.**
- **5b deferred tax: verified, still computed.** `"deferred_tax": deferred_tax_expense` (financial_statements.py:690); `wear_and_tear_rate` column (database.py:607) with its migration inside the list (database.py:1588); `SA_CIT_RATE = 0.27` (fixed_assets.py:84). financial_statements.py has not changed since 2026-11-11.
- Finance costs are still presented below EBIT, and tax is still derived from profit_before_tax ✓.
- Sources: [IFRS — IFRS 18](https://www.ifrs.org/issued-standards/list-of-standards/ifrs-18-presentation-and-disclosure-in-financial-statements/), [IFRS — Nov 2026 EEG technical update](https://www.ifrs.org/content/dam/ifrs/meetings/2026/november/eeg/ap3-iasb-technical-update.pdf), [KPMG — Q2 2026 new IFRS standards](https://kpmg.com/us/en/articles/2026/q2-2026-new-ifrs-accounting-standards-amendments-are-you-ready.html).

## 7. Tax updates (company + payroll)
- Tax year at run date: **2026/2027**. `TAX_YEARS["2026/2027"]` (payroll.py:298-313): brackets 18%–45%, rebates R17,820 / R9,765 / R3,249, UIF ceiling R17,712. Provisional "2027/2028" (payroll.py:318); `_current_tax_year` (payroll.py:336); `SDL_RATE = 0.01` (payroll.py:356); VAT 15% (payroll.py:20); CIT 27% (fixed_assets.py:84). All unchanged.
- MTBPS (21 Oct 2026): no rate changes are in force. Any tax proposals would come in Budget Feb 2027.
- Sources: [Deloitte — 2026 MTBPS](https://www.deloitte.com/za/en/services/tax/perspectives/2026-medium-term-budget-policy-statement.html), [gov.za — MTBPS 2026 speech](https://www.gov.za/news/speeches/minister-enoch-godongwana-medium-term-budget-policy-statement-2026-21-oct-2026), [Treasury — 2026 Budget Highlights](https://www.treasury.gov.za/documents/National%20Budget/2026/2026%20Budget%20Highlights.pdf). No tax-table edits made.

## 8. Action items
**Critical / High / Medium:** none open.

**Low**
1. (New) Run `tests/test_practice_mcp.py`, then commit practice_mcp.py with the test and the 2026-11-13 and 2026-11-14 reports. Consider defaulting `vat_registered` to `False` when the attribute is missing (practice_mcp.py:194, 219, 226). Set `PRACTICE_MCP_TOKEN` (32+ chars) and `PRACTICE_MCP_USER_EMAIL` in prod only when the connector should be live.
2. (Owner, carried) Run GL account-type review / `reclassify-gl-accounts` in production for pre-2026-11-05 imports and pre-0315e76 custom Cost of Sales accounts.
3. (Owner, carried) POPIA privacy page: legal review + Netlify publish.
4. (Owner, carried) Run `check_fixed_asset_useful_life.py` dry run in prod.

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS for SMEs 3rd ed. / IFRS 18 checklist Jan–Feb 2027.
