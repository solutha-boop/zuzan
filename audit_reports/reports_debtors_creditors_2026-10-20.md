# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 20 October 2026 (scheduled run)
**Prior report:** 2026-10-19 (+ `medium_items_check_2026-10-20.md`)

**Change detection:** HEAD `d7eb1bb` (20 Oct 22:54; five commits since `829ffc7`, all with the same auto-commit message). Real source changes since last report: `payroll.py` (+245/−35: new `_po_cost_net` / `_stock_pl_cost`, payslip PDF/HTML refactor), `main.py` (/v1/summary now uses them), `purchase_orders.py` (+1: accumulates `po.stock_received_net`), `database.py` (+6: `stock_received_net` column + migrations inside the list literal; credit-note VAT 2200→2100 one-off UPDATE), `companies.py` (+30: `_strip_line_vat` for non-VAT-registered / zero-rated / exempt invoices), `auth.py` (+3), `App_js_fixed.js` (+26). `py_compile` passes on payroll, journal, financial_statements, main, purchase_orders, database, companies, csv_import. 15 further files show working-tree modifications not yet committed (csv_import, portal, leave, recurring_invoices, quotes, documents, customers, suppliers, main…; ≈520 lines ignoring EOL) — not audited in depth beyond csv_import import-awareness. Local `zuzan.db` unchanged since 28 Sep (no fresh runtime data). No code edited by this run (5b already implemented).

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | PASS — inventory-aware COGS change verified consistent across all endpoints; 1 new Medium (journal dependency/tests) |
| Debtors (AR) | PASS |
| Creditors (AP) | PASS — reversal-awareness intact |
| Cross-module | PASS — import-awareness intact; open Mediums carried |
| IFRS (AFS) | PASS — no standards change; deferred tax (5b) verified present |
| Tax (SARS) | PASS for rates/tables; **High defect still open: IRP5/EasyFile codes 4005/7002** (EMP501 due 31 Oct) |

**Overall: PASS with 1 open High (IRP5 code mapping), 11 days before the EMP501 deadline.**

## 2. Reports
- Revenue = paid invoices only via `_to_zar` (`payroll.py:18`); outstanding = sent+overdue (`payroll.py:2285-2289`, "sent" = pending, see `database.py:41`); expenses excluded from revenue; `/v1/summary` (`main.py:515`) imports `_to_zar`. Management trend loop (`payroll.py:~2440-2470`) applies `_to_zar` ✓.
- **Changed since last run (verified):** POs for tracked-inventory lines are no longer expensed at receipt. `_po_cost_net` (`payroll.py:49-54`) = delivered net − `stock_received_net`; stock reaches P&L via `_stock_pl_cost` (`payroll.py:57-75`, ledger: 5000 `invoice_cogs`/`invoice_cogs_reversal` + 5950). Used consistently at `payroll.py:2304, 2462-2469, 3128, 3563, 3640, 3821`, `main.py:528-533`, `budgets.py:188-197`. No double counting found: PO cost and stock COGS are disjoint (stock lines excluded from the first, only 1200→5000 releases in the second). Payroll cost still included separately; VAT input still uses `_po_delivered_total − _po_delivered_net` (full delivered value, correct).
- **Medium (new):** `_stock_pl_cost` reads the journal, whereas everything else on the dashboard reads source tables. A company whose COGS/5950 entries haven't been backfilled shows lower expenses than before the change. Add a regression test (PO with a stock line → P&L expense 0 at receipt, expense appears on sale) and ensure backfill runs on deploy. `stock_received_net` is backfilled from ledger account 1200 (`database.py` migration) – idempotent but only for POs with no value yet.
- Carried Medium: revenue-trend loop filters raw `paid_date`/`expense_date` (`payroll.py:~2440-2455`) — NULL-dated legacy rows drop out of trend but are in period totals (management period query already uses COALESCE, `payroll.py:~3332`).
- Carried Low: `VAT_RATE = 0.15` redefined at `payroll.py:2653, 3047, 4167`, `companies.py:516`, `quotes.py:16`; VAT201 due-date label/regression tests.

## 3. Debtors
✓ No issues found. `debtors_aging` (`payroll.py:3897`): invoices `sent`/`overdue` only (paid, draft, written_off excluded), `_to_zar` amounts, ageing from `due_date` (no-due-date → not_due), buckets not_due/current(0-30)/31-60/61-90/90+. New `_strip_line_vat` (`companies.py`) zeroes line VAT for non-VAT-registered/zero-rated/exempt supplies so totals match printed invoice — consistent with AR.

## 4. Creditors
✓ No issues found. `creditors_aging` (`payroll.py:3960`): received/partial POs net `credit − debit` on 2000 with sources `purchase_order` + `purchase_order_reversal` (`payroll.py:2823, 3295, 3995`; also `financial_statements.py`, `purchase_orders.py` pay_po, `journal.py` backfill); fully paid POs excluded; supplier bank fields decrypted with `decrypt_field`. Stock-line receipts still credit 2000 in full (only the debit side moves to 1200), so AP is unaffected by the inventory change. Carried Low: PO-line→inventory matching by description is brittle (now more relevant since it decides expense vs asset) — add explicit `inventory_item_id`.

## 5. Cross-module
- Journal coverage (invoices, payments, expenses, PO receipts/payments, payroll): last integrity run 2026-10-19 = 0 gaps; local DB unchanged since.
- Import-awareness ✓: `_auto_backfill` after invoice (`csv_import.py:541`) and expense (`:623`) imports; Rules 6/7 exclude `source="import"` (`payroll.py:2781, 2857`); 3998/3999 handled (`csv_import.py:786, 1002`); unbalanced journal groups rejected (`:1095-1124`); non-ZAR invoices require rate (`:497-512`). Uncommitted csv_import edits (decimal-comma / bracketed-negative amount parsing, more date formats) don't touch these.
- Open Mediums unchanged: no EMP201-submitted guard on `DELETE /payslips/{period}` (no submission-status model exists); bank-import `db.rollback()` inside loop discards earlier uncommitted rows (`companies.py:~2062-2221`, use SAVEPOINTs); `fix_credit_note_vat_account.py` still untracked — note `database.py` now contains an equivalent idempotent migration moving credit-note lines 2200→2100, so the script may be redundant (historic entertainment VAT Input lines still not covered).

## 6. IFRS compliance (AFS)
- Framework: IFRS for SMEs (current edition). IFRS 18 and IFRS for SMEs 3rd edition remain effective for periods beginning on/after 1 Jan 2027 (early adoption permitted) — no change; `ifrs_smes_3rd_edition_transition_plan.md` stands. Sources: [Forvis Mazars SA](https://www.forvismazars.com/za/en/services/audit-assurance/financial-reporting/ifrs-for-smes-R-accounting-standard), [Accounting Academy](https://www.accountingacademy.co.za/news/read/updated-ifrs-for-smes-3rd-edition), [IFRS Foundation overview](https://ifrs.org/content/dam/ifrs/supporting-implementation/smes/2025-webcasts/overview-third-edition-ifrs-for-smes.pdf). (Search returned titles only; no contradicting information.)
- **5b deferred tax:** already implemented — `financial_statements.py:640` `"deferred_tax": deferred_tax_expense`, per-asset temporary difference × `_CIT_RATE` (`:172`), `wear_and_tear_rate` column present. Not hard-coded 0.0; no edits needed.
- Finance costs below EBIT; tax = `profit_before_tax × _CIT_RATE` (`financial_statements.py:258-261`) ✓. Inventory (1200) is on the balance sheet via account totals; no AFS change needed for the COGS change.
- Carried Medium: "Income Tax Payable (estimate)" must net against provisional-tax payments once those are journalled (none exist yet).

## 7. Tax updates (company + payroll)
- Tax year at run date: **2026/2027** (1 Mar 2026 – 28 Feb 2027). `TAX_YEARS["2026/2027"]` (`payroll.py:158`): 18% ≤ R245,100; 26% ≤ R383,100; 31% ≤ R530,200; 36% ≤ R695,800; 39% ≤ R887,000; 41% ≤ R1,878,600; 45% above; rebates R17,820 / R9,765 / R3,249; UIF ceiling R17,712. `_current_tax_year()` (`:196`) selects by date with latest-entry fallback; provisional `"2027/2028"` (`:178`, flagged) awaits Budget Feb 2027.
- UIF 1%+1%, SDL 1%, VAT 15% (no change announced), CIT 27% (`fixed_assets.SA_CIT_RATE`; literals `0.27` at `payroll.py:2334, 3605, 3796`) — no changes found. Sources: [SARS Employer Guide 2027](https://www.sars.gov.za/guide-for-employers-in-respect-of-employees-tax-2027/), [TaxTim Budget 2026](https://www.taxtim.com/blog/budget-2026), [Xero SARS tables 2026](https://www.xero.com/za/guides/sars-tax-tables-2026/), [Accounter tax tables](https://accounter.co.za/tax-tables). Search returned titles only; conclusion rests on previous source reads.
- **HIGH (still open):** EasyFile/IRP5 employer export `payroll.py:2168` writes pension/provident s11F as code `4005` (SARS 4005 = medical aid contributions; pension = 4001, provident = 4003, RA = 4006) and `payroll.py:2172` writes employer pension as `7002` (unverifiable code; employer pension/provident are 4472/4473). 4141/4142 (UIF/SDL) are correct. Also stale response labels `code_4005_pension` (`:1891`), `code_4474_sdl` (`:~1905`), `code_7002_pension_empr` (`:1906`) and `code_4001_paye` / `code_4002_uif_employee` / `code_4003_uif_employer` (these label codes with the wrong SARS meanings; PAYE is 4102, UIF 4141). Fix and validate against the SARS BRS before the 31 Oct 2026 EMP501 submission. Source: [SimplePay SARS codes](https://simplepay.co.za/help/filing-and-processes/sars-codes).
- No edits made to tax tables (report-only).

## 8. Action items
**Critical:** none.
**High**
1. Correct IRP5 codes in `payroll.py:2168` (4005→4001/4003/4006 by fund type) and `:2172` (7002→4472/4473), fix mislabelled response keys (`:1889-1906`), test one EasyFile export — before 31 Oct 2026.
**Medium**
2. Add regression tests for inventory-aware COGS (`_po_cost_net` / `_stock_pl_cost`); ensure journal backfill runs so ledger-derived stock cost is present.
3. EMP201-submitted guard on `DELETE /payslips/{period}` (needs a submission-status flag first).
4. Bank-import loop: use SAVEPOINTs rather than whole-session `rollback()` (`companies.py:~2062-2221`).
5. Decide fate of `fix_credit_note_vat_account.py` (now partly superseded by the `database.py` migration); handle historic entertainment VAT Input lines.
6. Net AFS "Income Tax Payable (estimate)" against future provisional-tax journals.
7. Revenue-trend loop: COALESCE `paid_date`/`expense_date` or backfill NULLs (`payroll.py:~2440`).
8. Review/commit the 15 files with uncommitted working-tree changes (csv_import, portal, leave, recurring_invoices, quotes…); commit history shows five identical auto-commit messages — use descriptive messages.
**Low**
9. Label VAT201 due-date rule; VAT201 tests; consolidate `VAT_RATE`; explicit `inventory_item_id` on PO lines.
10. Confirm NBCPSS clause-8 bonus formula; confirm `reclass_expenses_2026-09-28.py` run on production; purge `zuzan.db` from git history, delete stale `.bak`, set `SECRET_KEY` in Render.

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS-for-SMEs 3rd ed./IFRS 18 checklist early 2027.
