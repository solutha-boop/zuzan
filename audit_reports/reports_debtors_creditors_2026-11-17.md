# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 17 November 2026 (scheduled run)
**Prior report:** 2026-11-16 (incl. its "Fixes applied (17 Nov)" addendum)

**Method:** static review of the uncommitted working-tree diff since HEAD 4fd92ee (no new commits since the last run), anchor greps across the backend and App_js_fixed.js, and web checks for IFRS/SARS changes. No live DB; tests not re-run. **No code edited** this run (5b already implemented; tax tables are report-only).

**Changes since the last report (uncommitted, 17 Nov):** payroll.py (+56/−22), main.py (1 line), App_js_fixed.js and zuzan-app/src/App.js (1 line each), two test files. These are the fixes for the three Medium items and Low item 4 raised on 16 Nov, plus the VAT due-date helper. financial_statements.py, database.py, journal.py, purchase_orders.py and csv_import.py are unchanged.

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | **PASS** — `_to_zar` (payroll.py:23), VAT 15% (payroll.py:20), main.py:531 imports unchanged |
| Debtors (AR) | **PASS** — Rule 6 now nets `import_reversal` (payroll.py:3062); aging unchanged |
| Creditors (AP) | **PASS** — Rule 7 now nets `import_reversal` (payroll.py:3138); reversal-aware PO lookups intact |
| Cross-module | **PASS** — journal coverage and import-awareness intact |
| IFRS (AFS) | **PASS** — no standards change; deferred tax still computed |
| Tax (SARS) | **PASS with 1 Low** — SBC table and 3rd provisional date now correct; stale offline AI-fallback PAYE example |

**Overall: 0 Critical, 0 High, 0 Medium, 2 Low (1 new). All three 16-Nov Mediums verified fixed — but not yet committed.**

## 2. Reports
✓ No issues found.
- `/reports/dashboard`, `/reports/management`, `/v1/summary` unchanged since 16 Nov (paid-only revenue via `_to_zar`, pending+overdue outstanding, payroll in expenses, received-PO cost via `_po_cost_net`, tax provision 27%).
- 13-week cash-flow forecast now dates VAT201 payments with `_vat_due_day` (payroll.py:3679, helper at payroll.py:4529), the same rule as `/reports/vat201` (25th of following month, earlier business day on weekend/public holiday). The helper is defined later in the module but is resolved at call time, so this is fine. `_vat_due_date` (string wrapper) retained for existing callers ✓.
- Carried Low (informational): state the revenue basis (ledger/accrual vs cash-received) on the monthly management report PDF and in-app management accounts.

## 3. Debtors
✓ No issues found.
- **16-Nov Medium 1 (AR) verified fixed:** payroll.py:3056-3064 now filters `JournalEntry.source.in_(["import", "import_reversal"])` on 1100; sum is debit − credit, so a replaced opening balance nets to zero. Test `test_ar_ap_control_checks_net_out_a_replaced_opening_balance` added.
- `debtors_aging` (payroll.py:4286) unchanged: sent/overdue/partial, aged from `due_date`, ZAR balances, paid excluded ✓.

## 4. Creditors
✓ No issues found.
- **16-Nov Medium 1 (AP) verified fixed:** payroll.py:3132-3140 includes `import_reversal` on 2000 (credit − debit).
- Per-PO AP lookups net credit − debit and include `purchase_order_reversal`/`po_payment_reversal`: payroll.py:3104 (Rule 7), 3626 (cash-flow), 4387 (creditors-aging); purchase_orders.py:505 (pay_po); journal.py backfill unchanged ✓. Supplier bank-detail decryption unchanged.

## 5. Cross-module
✓ No issues found.
- Journal coverage (invoice payments, expense payments, PO receipts/payments, payroll runs) unchanged.
- Import-awareness: `_auto_backfill` after invoice/expense imports (csv_import.py:575, 788); unbalanced journal groups rejected; non-ZAR invoice imports require an exchange rate; balance sheet still handles 3998/3999 and other equity accounts — all files unchanged since 16 Nov.

## 6. IFRS compliance (AFS)
- Framework unchanged: IFRS for SMEs (2nd ed.) presentation. IFRS 18 and IFRS for SMEs 3rd edition remain effective for periods beginning on or after 1 Jan 2027 (first affected ZuZan FY: 1 Mar 2027); no deferral found. **Standards unchanged since the prior report.**
- **5b deferred tax: verified, still computed** — `_deferred_tax_balance` (financial_statements.py:143); Note 9 `"deferred_tax": deferred_tax_expense` (financial_statements.py:690); `wear_and_tear_rate` column (database.py:609) with migration inside the list (database.py:1611); `SA_CIT_RATE = 0.27` (fixed_assets.py:84); frontend DTL/DTA rendering (App_js_fixed.js:13972-13993).
- Finance costs (6700 / "interest"/"finance cost") below EBIT; tax and net profit from `profit_before_tax` (financial_statements.py:233-290) ✓.
- Sources: [IFRS — IFRS 18](https://www.ifrs.org/content/ifrs/home/issued-standards/list-of-standards/ifrs-18-presentation-and-disclosure-in-financial-statements.html), [BDO — IFRS 18 is here](https://bdo.com.au/en-au/blogs/corporate-reporting/ifrs-18-is-here).

## 7. Tax updates (company + payroll)
- Tax year at run date: **2026/2027**. `TAX_YEARS["2026/2027"]` (payroll.py:312: brackets to R245,100/…, primary R17,820, secondary R9,765, tertiary R3,249, UIF ceiling R17,712); provisional "2027/2028" copy (payroll.py:332); `_current_tax_year` (payroll.py:350); `SDL_RATE = 0.01` (payroll.py:370); VAT 15% (payroll.py:20); CIT 27% (fixed_assets.py:84). Unchanged; no new announcements since the Oct 2026 MTBPS.
- **16-Nov Medium 3 verified fixed — SBC table:** `_SBC_TABLES` (payroll.py:3434-3442) keyed by year-of-assessment end; 2027 table checks out arithmetically (7% × (365,000 − 99,000) = R18,620; 18,620 + 21% × 185,000 = R57,470). `_sbc_tax(…, fy_end)` (payroll.py:4226) is the only caller.
- **16-Nov Medium 2 verified fixed — 3rd provisional payment:** payroll.py:4239 `7 if fy_end.month == 2 else 6` → 28 Feb year-end gives 30 Sep; 30 Apr year-end gives 31 Oct ✓. Docstring now cites Fourth Schedule para 20 (Low 4 fixed).
- **Low (new) — stale offline AI-fallback PAYE example.** App_js_fixed.js:13479 (and zuzan-app/src/App.js:13479) says R35,000/month → "PAYE ≈ R4,673/month after the R17,235 primary rebate". On 2026/27 tables PAYE is ≈ **R6,135/month** (R79,998 + 31% × (420,000 − 383,100) − R17,820 = R73,617 p.a.), and the rebate is R17,820. Only shown when the AI service is offline; payroll calculations are unaffected. Fix: update the text or drop the hard-coded figure and point to the Payroll tab.
- Sources: [SARS — Rates of tax for individuals](https://www.sars.gov.za/tax-rates/income-tax/rates-of-tax-for-individuals/), [National Treasury — Budget 2026 Tax guide](https://www.treasury.gov.za/documents/national%20budget/2026/sars/Budget%202026%20Tax%20guide.pdf), [SARS — Employer tax deduction tables guide](https://www.sars.gov.za/guide-for-employers-in-respect-of-tax-deduction-tables/). No tax-table edits made.

## 8. Action items
**Critical / High / Medium:** none open.

**Housekeeping (important)**
1. Commit the 17-Nov fixes (payroll.py, main.py, App_js_fixed.js, zuzan-app/src/App.js, two test files) and the 2026-11-16 report — they are in the working tree only, not deployed.

**Low**
2. (New) App_js_fixed.js:13479 / zuzan-app/src/App.js:13479: update the offline PAYE example (≈ R6,135/month, R17,820 rebate) or remove the figure.
3. (Carried, informational) State the revenue basis on the management report PDF / in-app management accounts.
4. (Carried) Run `tests/test_practice_mcp.py`; consider defaulting `vat_registered` to False in practice_mcp.py when missing.
5. (Owner, carried) Run GL account-type review / `reclassify-gl-accounts` in prod for older imports.
6. (Owner, carried) POPIA privacy page: legal review + Netlify publish.
7. (Owner, carried) Run `check_fixed_asset_useful_life.py` dry run in prod.

Standing reminders: replace the provisional 2027/2028 `TAX_YEARS` and add the 2027/28 SBC table after Budget Feb 2027; IFRS for SMEs 3rd ed. / IFRS 18 checklist Jan–Feb 2027.

---
## Fixes applied (18 Nov 2026, on request: older Low items)
- The 17-Nov fixes were committed in b04467a (18 Nov 06:40), so Housekeeping item 1 is done.
- **Low 3 (fixed), revenue basis:** `/reports/management` now returns `revenue_basis: "cash"` and `revenue_basis_note` (payroll.py). The Management Pack shows "Revenue on a cash-received basis (paid invoices); unpaid invoices are under Debtors" next to the period, in both App_js_fixed.js and zuzan-app/src/App.js. The monthly management report PDF note now says it is prepared "on the accrual basis: revenue is recognised when invoiced, whether or not it has been paid" (management_report.py).
- **Low 4 (fixed):** practice_mcp.py has a new `_vat_registered(co)` helper. It treats a missing or NULL VAT status as not registered, and is used in list_clients, vat201 and client_snapshot. New test `test_vat_status_unknown_counts_as_not_registered`. `tests/test_practice_mcp.py` (6) and `tests/test_management_report.py` pass.
- **Low 5–7 (not done, owner actions):** the production GL reclassify run, the POPIA legal review with Netlify publish, and the production dry run of `check_fixed_asset_useful_life.py` all need production access or a lawyer.
- Still open: Low 2, the offline PAYE example at App_js_fixed.js:13479.
- None of today's changes are committed yet.
