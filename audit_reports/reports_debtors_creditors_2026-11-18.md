# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 18 November 2026 (scheduled run)
**Prior report:** 2026-11-17 (incl. its "Fixes applied (18 Nov)" addendum)

**Method:** git review of changes since the last run, anchor greps across the backend and App_js_fixed.js, and web checks for IFRS/SARS changes. No live DB; tests not re-run. **No code edited** this run (5b already implemented; tax tables are report-only).

**Changes since the last report:** working tree is clean. One new commit, 5baa204 (18 Nov 20:22), which commits the 18-Nov addendum fixes: `revenue_basis`/`revenue_basis_note` on `/reports/management` (payroll.py:4062-4067), the Management Pack basis caption (App_js_fixed.js:7091, zuzan-app/src/App.js), the accrual-basis note on the management report PDF (management_report.py:526), and the `_vat_registered` helper in practice_mcp.py with its test. The 17-Nov fixes were committed earlier in b04467a. financial_statements.py, database.py, journal.py, purchase_orders.py, csv_import.py, suppliers.py and customers.py are unchanged. payroll.py line numbers after ~4059 have shifted by +6 versus the last report.

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | **PASS** — `_to_zar` (payroll.py:23), VAT 15% (payroll.py:20), main.py:531 imports intact; revenue basis now labelled |
| Debtors (AR) | **PASS** — Rule 6 nets `import`/`import_reversal` (payroll.py:3062); `debtors_aging` (payroll.py:4292) unchanged |
| Creditors (AP) | **PASS** — reversal-aware per-PO lookups intact (payroll.py:3104, 3626, 4393; purchase_orders.py:505; journal.py:1347) |
| Cross-module | **PASS** — journal coverage and import-awareness intact |
| IFRS (AFS) | **PASS** — no standards change; deferred tax still computed |
| Tax (SARS) | **PASS with 1 Low (carried)** — tables current; stale offline AI-fallback PAYE example remains |

**Overall: 0 Critical, 0 High, 0 Medium, 1 Low open in code (carried) + owner actions. All earlier fixes are now committed.**

## 2. Reports
✓ No issues found.
- `/reports/dashboard`, `/reports/management`, `/v1/summary` logic unchanged (paid-only revenue via `_to_zar`, pending+overdue outstanding via `_to_zar`, expenses excluded from revenue, payroll in expenses, received-PO cost via `_po_cost_net` with no double count, 27% provision).
- **17-Nov Low 3 verified fixed and committed:** `/reports/management` returns `revenue_basis: "cash"` and a note (payroll.py:4062-4067); the Management Pack shows the caption next to the period (App_js_fixed.js:7091); the PDF note states accrual basis (management_report.py:526). The two bases are now clearly distinguished for users.
- 13-week cash-flow VAT dates still use `_vat_due_day` (payroll.py:4535).

## 3. Debtors
✓ No issues found.
- `debtors_aging` (payroll.py:4292): sent/overdue/partial invoices, aged from `due_date`, ZAR balances, paid excluded — unchanged.
- Rule 6 (payroll.py:3056-3064) excludes/nets `import` and `import_reversal` on 1100.

## 4. Creditors
✓ No issues found.
- Per-PO AP lookups net credit − debit and include `purchase_order_reversal`/`po_payment_reversal`: payroll.py:3104 (Rule 7), 3626 (cash-flow), 4393 (`creditors_aging`, payroll.py:4355); purchase_orders.py:505 (`pay_po`); journal.py:1347 (backfill). Rule 7 nets `import`/`import_reversal` on 2000 (payroll.py:3138). Received-unpaid POs outstanding, fully paid excluded; supplier bank-detail decryption unchanged.

## 5. Cross-module
✓ No issues found.
- Journal coverage (invoice payments, expense payments, PO receipts/payments, payroll runs) unchanged.
- Import-awareness: `_auto_backfill` (csv_import.py:126) still runs after invoice/expense imports (csv_import.py:575, 788); unbalanced journal groups rejected; non-ZAR invoice imports require an exchange rate; balance sheet handles 3998/3999 and other imported equity/asset/liability accounts — files unchanged.

## 6. IFRS compliance (AFS)
- Framework unchanged: IFRS for SMEs (2nd ed.) presentation. IFRS 18 and IFRS for SMEs 3rd edition remain effective for annual periods beginning on or after 1 Jan 2027 (first affected ZuZan FY: 1 Mar 2027); no deferral found. **Standards unchanged since the prior report.**
- **5b deferred tax: verified, still computed** — `_deferred_tax_balance` (financial_statements.py:143); Note 9 `"deferred_tax": deferred_tax_expense` (financial_statements.py:690); `wear_and_tear_rate` column (database.py:609), migration inside the list (database.py:1611, with % normalisation at 1615); `SA_CIT_RATE = 0.27` (fixed_assets.py:84, used at 179). No re-implementation needed.
- Finance costs below EBIT; `profit_before_tax = ebit − finance_costs`, tax and net profit derive from PBT (financial_statements.py:288-290) ✓.
- Sources: [IFRS — 2025 IFRS for SMEs supporting materials](https://www.ifrs.org/supporting-implementation/2025-ifrs-for-smes-supporting-materials/), [IASB technical update, Nov 2026 EEG](https://www.ifrs.org/content/dam/ifrs/meetings/2026/november/eeg/ap3-iasb-technical-update.pdf), [Forvis Mazars SA — new edition of IFRS for SMEs](https://www.forvismazars.com/za/en/services/audit-assurance/financial-reporting/ifrs-for-smes-R-accounting-standard).

## 7. Tax updates (company + payroll)
- Tax year at run date: **2026/2027**. `TAX_YEARS["2026/2027"]` (payroll.py:312; primary rebate R17,820, secondary R9,765, tertiary R3,249, UIF ceiling R17,712); provisional "2027/2028" copy (payroll.py:332); `_current_tax_year` (payroll.py:350); `SDL_RATE = 0.01` (payroll.py:370); UIF 1%/1%; VAT 15% (payroll.py:20); CIT 27% (fixed_assets.py:84); `_SBC_TABLES` (payroll.py:3436); 3rd provisional payment rule (payroll.py:4245). All unchanged; no new SARS/Treasury rate announcements found since the Oct 2026 MTBPS.
- **Low (carried from 17 Nov) — stale offline AI-fallback PAYE example:** App_js_fixed.js:13479 and zuzan-app/src/App.js:13479 still say "PAYE ≈ R4,673/month after the R17,235 primary rebate". On 2026/27 tables it is ≈ **R6,135/month** with a **R17,820** rebate. Offline fallback text only; payroll calculations unaffected.
- Sources: [SARS — Rates of tax for individuals](https://www.sars.gov.za/tax-rates/income-tax/rates-of-tax-for-individuals/), [SARS — What's new](https://www.sars.gov.za/whats-new-at-sars), [National Treasury — Budget 2026 Tax guide](https://www.treasury.gov.za/documents/national%20budget/2026/sars/Budget%202026%20Tax%20guide.pdf). No tax-table edits made.

## 8. Action items
**Critical / High / Medium:** none open.

**Low**
1. (Carried) App_js_fixed.js:13479 / zuzan-app/src/App.js:13479: update the offline PAYE example (≈ R6,135/month, R17,820 rebate) or remove the figure.
2. (Owner, carried) Run GL account-type review / `reclassify-gl-accounts` in prod for older imports.
3. (Owner, carried) POPIA privacy page: legal review + Netlify publish.
4. (Owner, carried) Run `check_fixed_asset_useful_life.py` dry run in prod.

**Closed since last run:** Housekeeping (commit 17-Nov fixes) — done in b04467a; revenue-basis labelling and `vat_registered` default — fixed and committed in 5baa204.

Standing reminders: replace the provisional 2027/2028 `TAX_YEARS` and add the 2027/28 SBC table after Budget Feb 2027; IFRS for SMEs 3rd ed. / IFRS 18 checklist Jan–Feb 2027.
