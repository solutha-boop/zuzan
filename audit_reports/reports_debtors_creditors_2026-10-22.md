# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 22 October 2026 (scheduled run)
**Prior report:** 2026-10-21

**Change detection:** commits `dff7a43` / `980053a` (22 Oct 18:59–19:00, "partial invoice payments + invoice error message fix") landed after the last report. They address the 21 Oct High/Medium items: `partial` added to outstanding filters, new `_balance_zar` (`payroll.py:27-32`) and `_inv_balance_zar` (`financial_statements.py:70`), `update_invoice` partial logic rewritten (`companies.py:~923-945, ~1081-1092`), backfill/repair made partial-aware (`journal.py:1192`, `recurring_invoices.py:311-317`), write-off of part-paid invoices blocked (`companies.py:860`). `py_compile` passes for payroll, main, companies, journal, financial_statements, database, purchase_orders, csv_import. `tests/test_part_payment.py` now exists. Local `zuzan.db` not queried (no runtime data checked). No code edited this run (5b already implemented).

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | **PASS with Medium** — partial status now handled in dashboard/summary/aging/AFS; monthly trend, management accounts and cash-flow revenue still ignore part-paid cash |
| Debtors (AR) | **PASS** — partial invoices included, balance (total − paid) shown in ZAR, aging from due_date |
| Creditors (AP) | **PASS** — reversal-awareness and decryption intact |
| Cross-module | **PASS with Medium** — FX partial issue closed by design (foreign invoices cannot be part-paid); backfill only re-posts first payment |
| IFRS (AFS) | **PASS** — no standards change; deferred tax verified |
| Tax (SARS) | **PASS** — 2026/2027 tables present; no announced changes found |

**Overall: PASS (no Critical/High). Both 21 Oct Highs are resolved; 2 new Medium, 1 new Low.**

## 2. Reports
- Verified: revenue = paid invoices via `_to_zar` (`payroll.py:2298`) **plus** received portion of part-paid invoices (`payroll.py:2300`, `main.py:520`); outstanding = sent+overdue+partial via `_balance_zar` (`payroll.py:2306-2308`, `main.py:518,550`); expenses excluded; payroll/PO cost (`_po_cost_net`/`_stock_pl_cost`) unchanged; `/v1/summary` uses `_to_zar`/`_balance_zar`. Invoice-set filters now include partial (`payroll.py:2359, 2713, 3074, 4219`; `financial_statements.py:513`).
- **MEDIUM (new): part-paid cash omitted from other revenue calculations.** Monthly trend (`payroll.py:2461-2466`), management revenue (`payroll.py:2918, 3131, 3555, 3825`), cash receipts (`payroll.py:2981`) and the dashboard-period variants filter `Invoice.status == paid` only, so a part-paid invoice's received amount appears in the headline `total_revenue` (`2300`) but not in these views — figures will not agree until the invoice is fully settled. Apply the same `+ paid_amount_zar of partial` treatment (date by `paid_date`).
- Carried Medium: trend loop uses raw `paid_date`/`expense_date` (NULL-dated legacy rows drop from trend). Carried Low: `VAT_RATE = 0.15` redefined at `payroll.py:2672, 3066, 4186`, `companies.py`, `quotes.py`.

## 3. Debtors
- `debtors_aging` (`payroll.py:3926-3975`): filter sent/overdue/partial ✓; amount = `_balance_zar` (ZAR, net of part payment) ✓; aging from `due_date` ✓ (no due date → not_due); paid excluded ✓. Overdue count includes partial past due (`payroll.py:3634`) ✓. Frontend Debtors view consumes this endpoint (`App_js_fixed.js` ~7806).
- Note (Low): `_balance_zar` for partial uses `total_amount` (ZAR-correct because foreign invoices cannot be part-paid, `companies.py:~927`). If foreign part-payments are ever enabled, it must use `total×rate`.
- Note (Low): nothing auto-transitions `partial` → `overdue` (only `csv_import.py:226` assigns overdue); display relies on due_date logic above.

## 4. Creditors
✓ No issues found. `creditors_aging` (`payroll.py:~3989-4065`) nets `credit − debit` on 2000 with sources `purchase_order` + `purchase_order_reversal` (counts: payroll 6, purchase_orders 2, journal 1, financial_statements 2); received/partial POs outstanding, paid excluded; supplier bank name/account/branch decrypted via `decrypt_field` (`payroll.py:4057-4059`).

## 5. Cross-module
- Journal coverage code paths intact for invoice raise/payment, expense, PO receipt/payment, payroll. Last integrity run (2026-10-19) 0 gaps; DB not re-run today.
- Partial payments: only the incremental delta is posted (`companies.py:~1081-1092`) — resolves 21 Oct FX Medium (foreign invoices settled in full, FX on full carried AR). Reconciliation 1100 vs invoices should now hold since AR reports include partials.
- **MEDIUM (new/refined): backfill idempotency.** `journal.py:1192-1195` keys on `("invoice_payment", inv.id)`; if the first payment's entry exists but a later top-up entry is missing, it will never be re-posted; and if all entries are missing it re-posts only the cumulative amount once (acceptable). Compare 1100 credits to `paid_amount_zar` in `journal_check` for partial invoices.
- Import-awareness ✓ (`csv_import.py:541, 623` auto-backfill; Rules 6/7 exclude `source="import"`; 3998/3999 included; unbalanced journal groups rejected; non-ZAR imports need rate).
- Carried Mediums: EMP201-submitted guard on `DELETE /payslips/{period}`; bank-import loop `db.rollback()` (use SAVEPOINTs); untracked `fix_credit_note_vat_account.py`, `tests/`, `pytest.ini`, `_to_delete/`.

## 6. IFRS compliance (AFS)
- Framework: IFRS for SMEs (2nd edition); IFRS 18 not applicable (full-IFRS only). IFRS for SMEs 3rd edition effective for periods beginning ≥ 1 Jan 2027 — unchanged since last audit; `ifrs_smes_3rd_edition_transition_plan.md` stands (first ZuZan FY affected begins 1 Mar 2027). Sources: [Accounting Academy](https://www.accountingacademy.co.za/news/read/updated-ifrs-for-smes-3rd-edition), [Forvis Mazars SA](https://www.forvismazars.com/za/en/services/audit-assurance/financial-reporting/ifrs-for-smes-R-accounting-standard), [ACCA](https://www.accaglobal.com/learning-and-events/corporate-reporting/third-edition-ifrs-for-smes). (Search returned titles only; no contradicting information.)
- **5b deferred tax — verified, not hard-coded:** `_deferred_tax_balance` (`financial_statements.py:139-180`, temporary difference × `_CIT_RATE`), opening/closing balances (`275-277`), Note 9 `deferred_tax` = movement and `total_tax` = current + deferred (`643-652`), equity adjustment `deferred_tax_movement` (`723`). No edits needed.
- Finance costs below EBIT; tax from profit_before_tax (`financial_statements.py:266-269`) ✓. Trade receivables note net of part payments, ZAR (`470-500`) ✓.
- Carried Medium: Income Tax Payable estimate should net provisional-tax payments once journalled.

## 7. Tax updates (company + payroll)
- Tax year at run date: **2026/2027** (1 Mar 2026–28 Feb 2027). `TAX_YEARS["2026/2027"]` present (`payroll.py:165`): brackets 18% to R245,100 … 45% above R1,878,600; rebates R17,820 / R9,765 / R3,249; UIF ceiling R17,712. Provisional `2027/2028` at `payroll.py:185` (flagged `provisional`) awaits Budget Feb 2027. Selector uses `CURRENT_TAX_YEAR` (`payroll.py:219-221`, `.get(tax_year or CURRENT)`).
- UIF 1%+1%, SDL 1%, VAT 15% (`payroll.py:2672, 3066, 4186`), CIT 27% (`financial_statements.py:90`, `payroll.py:2353, 3624, 3815`) — no announced changes found. Sources: [SARS company rates](https://www.sars.gov.za/tax-rates/income-tax/companies-trusts-and-small-business-corporations-sbc/), [Grant Thornton Budget 2026 analysis](https://www.grantthornton.co.za/contentassets/334ab82b24354cfa91de433a7de8ed56/2026-budget-analysis-and-commentary_fa.pdf). (Search returned titles only; conclusion rests on prior source reads.)
- Low (carried): mislabelled IRP5 response keys (`payroll.py:1889-1906`); hard-coded `0.27` literals (`payroll.py:2353, 3624, 3815`) should use `SA_CIT_RATE`. Validate an EasyFile export before the EMP501 deadline of 31 Oct 2026.
- No edits to tax tables (report-only).

## 8. Action items
**Critical:** none. **High:** none (both 21 Oct Highs fixed).
**Medium**
1. Include part-paid received cash in revenue trend, management accounts, cash-flow receipts (`payroll.py:2461, 2918, 2981, 3131, 3555, 3825`) so all views agree with the dashboard.
2. Make payment backfill detect missing top-up entries for partial invoices (`journal.py:1192`); add a journal_check comparing 1100 credits to `paid_amount_zar`.
3. Carried: EMP201-submitted guard on payslip delete; SAVEPOINTs in bank import; regression tests for inventory-aware COGS; net AFS Income Tax Payable vs provisional tax; COALESCE trend-loop dates; commit/review untracked tests/scripts with descriptive commit messages.
**Low**
4. Use `SA_CIT_RATE` instead of `0.27` literals; consolidate `VAT_RATE`; rename IRP5 response keys; guard `_balance_zar` for future foreign part-payments; consider auto-flagging partial invoices overdue.

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS-for-SMEs 3rd-ed. checklist Jan–Feb 2027; EMP501 due 31 Oct 2026.
