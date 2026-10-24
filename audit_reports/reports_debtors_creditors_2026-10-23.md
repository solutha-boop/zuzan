# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 23 October 2026 (scheduled run)
**Prior report:** 2026-10-22

**Change detection:** commits `0bd0fd6`, `cb19f83`, `ff2321f`, `d95007a` (23 Oct) landed since the last report: `payroll.py` `_partial_received` (new, line 35), `companies.py` foreign-currency part payments + `/invoices/payments-this-month`, `journal.py` backfill top-up repair (~1192-1224), `journal_check.py` check 2b, frontend "paid this month" cash view. `py_compile` passes for payroll, main, companies, journal, financial_statements, database, purchase_orders, csv_import. **py_compile does not catch the Critical below.** Local `zuzan.db` is stale (28 Sep) and was not queried. No code edited this run (5b already implemented).

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | **PASS with Medium** — 22 Oct Medium (part-paid cash in trend/management/cash-flow/provisional tax) fixed; foreign part-paid balance wrong in `_balance_zar` |
| Debtors (AR) | **FAIL (Medium)** — foreign-currency part-paid balance now wrong in aging/outstanding |
| Creditors (AP) | **PASS** — reversal-awareness and decryption intact |
| Cross-module | **FAIL (Critical)** — `companies.py` calls journal functions that do not exist; marking invoices paid will 500 |
| IFRS (AFS) | **PASS** — no standards change; deferred tax verified |
| Tax (SARS) | **PASS** — 2026/2027 tables match SARS; CIT 27%, VAT 15% |

**Overall: FAIL — 1 Critical (payment posting broken), 1 High, 3 Medium.**

## 2. Reports
- Verified unchanged: `total_revenue` = paid via `_to_zar` + part-paid received cash (`payroll.py:2311-2318`); `total_outstanding` = sent/overdue/partial via `_balance_zar` (`payroll.py:2320-2325`); expenses excluded; payroll and PO costs (net, not double-counted) unchanged; `/v1/summary` (`main.py:517-550`) uses `_to_zar`/`_balance_zar`.
- ✓ **22 Oct Medium resolved:** `_partial_received()` (`payroll.py:35`) now added to monthly trend (`2483`), reconciliation Rule 8 (`2938`), cash flow (`3000`), annual tax estimate (`3151`), management accounts (`3576`), provisional tax (`3847`). Management-accounts `_eff_paid` now correctly uses `issue_date` (the prior `Invoice.invoice_date` attribute did not exist; `database.py:1067` confirms `issue_date`).
- **MEDIUM (new): `_balance_zar` wrong for foreign-currency part-paid invoices** — `payroll.py:30-31` computes `total_amount − paid_amount_zar`, mixing foreign-currency total with a ZAR payment. Foreign part payments were enabled on 23 Oct (`final_payment=false`, `companies.py:~960`), so this is now reachable. Should be `total_amount × exchange_rate − paid_amount_zar` (as `financial_statements.py:_inv_balance_zar` already does). Affects dashboard `total_outstanding`, `/v1/summary`, debtors aging.
- **MEDIUM: `_partial_received` / dashboard use cumulative `paid_amount_zar` dated by `paid_date`**, so part-paid cash for a prior month can land in the wrong period (the frontend now uses journal-based `/payments-this-month`; backend period reports still don't). Consider sourcing from 1000 payment journal lines.
- Carried: trend loop raw `paid_date`/`expense_date` (NULL legacy rows drop out); `VAT_RATE = 0.15` redefined at `payroll.py:2689, 3085, 4208`, `companies.py:516`, `quotes.py:16`.

## 3. Debtors
- `debtors_aging` (`payroll.py` ~3945-3995): filter sent/overdue/partial ✓; aging from `due_date` ✓; paid excluded ✓; ZAR via `_balance_zar` (**see foreign part-pay Medium above**). Frontend (`App_js_fixed.js:788-792`) already computes `toZarD(i) − paid_amount_zar` correctly for partial, so backend and frontend now disagree for foreign part-paid invoices.
- Frontend "paid this month" KPI now uses `/invoices/payments-this-month` (`companies.py:644`, journal-based, reversals net) ✓ (falls back to paid_date for older invoices).

## 4. Creditors
✓ No issues found. `creditors_aging` nets `credit − debit` on 2000 with sources `purchase_order` + `purchase_order_reversal` (counts: payroll 6, purchase_orders 2, journal 1, financial_statements 2); received/partial POs outstanding, paid excluded; supplier bank name/account/branch decrypted with `decrypt_field` (`payroll.py:4079-4081`).

## 5. Cross-module
- **CRITICAL (new): `companies.py` references journal APIs that do not exist.** `companies.py:1126` calls `journal_engine.post_invoice_paid(invoice, db, ar_zar=_ar)` but `journal.py:431` defines `post_invoice_paid(invoice, db)` with no `ar_zar` parameter; `companies.py:912` calls `journal_engine._open_zar_parts(inv)` which is not defined anywhere (grep across all `*.py`). Effect: every ZAR (and foreign non-legacy) payment/part-payment through `PUT /invoices/{id}` raises `TypeError` → caught at `companies.py:1130-1138` → rollback + HTTP 500 "Invoice update failed"; bad-debt recovery (`POST .../recover`) raises `AttributeError`. The journal.py half of the 23 Oct change (ar_zar clearing for foreign part payments, `_open_zar_parts`, partial-aware bad-debt write-off posting) was never committed (HEAD `journal.py` last touched in `0bd0fd6`). The bank-statement auto-match path (`companies.py:~2300`) still uses the old signature, so only the manual mark-paid/partial path and recovery are broken. `py_compile` passes because these are runtime lookups. Verified via `git grep` on HEAD (`d95007a`).
- **HIGH (new): bad-debt write-off of part-paid invoices unverified.** `companies.py:880` now allows `partial` status, but `journal.py` has no partial-aware write-off posting (no `_open_zar_parts`), so the write-off entry would clear the full invoice rather than the open balance, overstating the credit to 1100 by the amount already received.
- ✓ Backfill top-up repair (`journal.py:1192-1224`) and `journal_check.py` check 2b added — resolves 22 Oct Medium #2 (ZAR only; foreign part-pays excluded). Not run (DB stale).
- Journal coverage code paths otherwise intact (invoice raise/payment, expense, PO receipt/payment, payroll). Import-awareness ✓ (`csv_import.py` auto-backfill, Rules 6/7 exclude `source="import"`, 3998/3999 included, unbalanced groups rejected, non-ZAR imports need a rate).
- Carried Mediums: EMP201-submitted guard on `DELETE /payslips/{period}`; bank-import loop `db.rollback()` (use SAVEPOINTs); untracked `fix_credit_note_vat_account.py`, `find_default_password_accounts.py`, `tests/`, `pytest.ini`, `requirements-test.txt`, `_to_delete/`; commit messages are all the same stale "partial invoice payments" text.

## 6. IFRS compliance (AFS)
- Framework: IFRS for SMEs (2nd ed.); IFRS 18 applies to full IFRS only (effective 1 Jan 2027). IFRS for SMEs 3rd edition effective for periods beginning ≥ 1 Jan 2027 — unchanged; `ifrs_smes_3rd_edition_transition_plan.md` stands (first ZuZan FY affected starts 1 Mar 2027). Sources: [Accounting Academy](https://www.accountingacademy.co.za/news/read/updated-ifrs-for-smes-3rd-edition), [Forvis Mazars SA](https://www.forvismazars.com/za/en/services/audit-assurance/financial-reporting/ifrs-for-smes-R-accounting-standard), [IFRS Foundation overview](https://ifrs.org/content/dam/ifrs/supporting-implementation/smes/2025-webcasts/overview-third-edition-ifrs-for-smes.pdf) (search returned titles only).
- **5b deferred tax — verified, not hard-coded** (no `"deferred_tax": 0.0` literal): `_deferred_tax_balance` in `financial_statements.py` (~139-180, temporary difference × `_CIT_RATE`), Note 9 `deferred_tax` = movement, `total_tax` = current + deferred, equity adjustment. No edits needed.
- Finance costs below EBIT; tax from profit_before_tax ✓. AFS trade receivables use `_inv_balance_zar` (`financial_statements.py:70`) and are correct for foreign part-paid (unlike `payroll._balance_zar`).
- Carried Medium: Income Tax Payable estimate should net provisional-tax payments.

## 7. Tax updates (company + payroll)
- Tax year at run date: **2026/2027** (1 Mar 2026 – 28 Feb 2027). `TAX_YEARS["2026/2027"]` present (`payroll.py:~182`) and matches [SARS individual rates](https://www.sars.gov.za/tax-rates/income-tax/rates-of-tax-for-individuals/) exactly: brackets 18% to R245,100 … 45% above R1,878,600 with bases 44,118 / 79,998 / 125,599 / 185,215 / 259,783 / 666,339; rebates R17,820 / R9,765 / R3,249. UIF ceiling R17,712. Provisional `2027/2028` (flagged) at `payroll.py:~203`. Selector `_current_tax_year` (date-derived, falls back to newest).
- UIF 1%+1%, SDL 1%, VAT 15%, CIT 27% (confirmed by [SARS company rates](https://www.sars.gov.za/tax-rates/income-tax/companies-trusts-and-small-business-corporations-sbc/): 27% for years ending 1 Apr 2026–31 Mar 2027, no change). No announced changes found.
- Low (carried): `CORP_TAX_RATE = 0.27` literal at `payroll.py:3836`; `S11F_RATE` etc. fine. Mislabelled IRP5 response keys. EMP501 reconciliation due 31 Oct 2026 — validate an EasyFile export.
- No edits to tax tables (report-only).

## 8. Action items
**Critical**
1. Restore the missing journal.py changes (or revert the companies.py calls): add `ar_zar=None` param to `post_invoice_paid` (`journal.py:431`; use it as `ar_carried` when provided) and define `_open_zar_parts(inv)` (returns open ZAR balance after part payment, first tuple element used at `companies.py:912`). Add a regression test that PUTs an invoice to paid and partial and asserts 200 + balanced journal; run `tests/test_part_payment.py`. Until fixed, manual mark-paid/part-paid and bad-debt recovery return HTTP 500.
**High**
2. Make bad-debt write-off posting (`journal.py`) partial-aware (clear open balance only) now that `companies.py:880` allows partial; add a test.
**Medium**
3. Fix `_balance_zar` for foreign part-paid invoices (`payroll.py:30-31`: use `total_amount × exchange_rate`); align with `_inv_balance_zar`.
4. Backend period reports date part-paid cash by `paid_date` (cumulative); source from payment journal lines (cf. `/payments-this-month`). Extend `journal_check` 2b to foreign part-payments.
5. Carried: EMP201-submitted guard on payslip delete; SAVEPOINTs in bank import; net AFS Income Tax Payable vs provisional tax; COALESCE trend-loop dates; commit untracked tests/scripts with descriptive commit messages (auto-commit message is stale).
**Low**
6. Replace `0.27` literal (`payroll.py:3836`) with `SA_CIT_RATE`; consolidate `VAT_RATE`; rename IRP5 response keys; auto-flag partial invoices overdue.

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS-for-SMEs 3rd-ed. checklist Jan–Feb 2027; EMP501 due 31 Oct 2026.

## 9. Remediation (24 Oct 2026)
Fixed (uncommitted working-tree edits; 86/87 tests pass, incl. `test_part_payment.py` which covers the Critical path):
1. **Critical** — `journal.py`: added `_open_zar_parts()`; `post_invoice_paid(..., ar_zar=None)`; backfill passes `ar_zar` for foreign part-pays.
2. **High** — `post_bad_debt_writeoff` / `post_bad_debt_recovery` now use the open balance of a part-paid invoice.
3. **Medium** — `payroll._balance_zar` uses `total × exchange_rate` for foreign part-paid; added missing `payroll._received_zar` (imported by `budgets.py`, was an ImportError); `_partial_received` now dates each instalment from its payment journal entry; `journal_check` 2b covers foreign invoices; backfill top-up covers foreign part-paid.
4. **Carried Medium/Low** — trend loop uses COALESCE dates; `CORP_TAX_RATE` uses `SA_CIT_RATE`; `VAT_RATE` defined once in `payroll.py`.
Not fixed (need a product decision/design): EMP201-submitted guard (no submission flag exists), SAVEPOINTs in bank import, AFS tax payable net of provisional tax, IRP5 key renames, auto-flagging partial invoices overdue. New finding: `main.py:865` admin clear-data imports non-existent models `StockMovement`, `BankTransaction`, `Document` (runtime ImportError). `test_payroll_journal_balance_runner` fails only because this sandbox cannot delete its temp DB file.
