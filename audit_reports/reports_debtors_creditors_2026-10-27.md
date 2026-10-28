# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 27 October 2026 (scheduled run)
**Prior report:** 2026-10-26

**Change detection:** HEAD is now `742a9a0` (auto-sync, 27 Oct 21:47) — the 59 files staged on 26 Oct are now committed (prior Medium #1 resolved). Since the last audit `payroll.py` (+48), `main.py`, `companies.py` and `App_js_fixed.js` (+393) changed (diff 4954751..HEAD); journal.py, csv_import.py, purchase_orders.py, financial_statements.py, suppliers.py, customers.py are unchanged. `py_compile` passes for all ten backend modules. No live DB / pytest in this environment (static review only). No code edited (5b already implemented).

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | **PASS** — `_to_zar`/`_received_net_zar`/`_balance_zar` intact (payroll.py:23/33/45), VAT_RATE=0.15 (payroll.py:20) |
| Debtors (AR) | **PASS** — unchanged |
| Creditors (AP) | **PASS** — reversal-aware sources intact (payroll.py:2972, 3443, 4192); `decrypt_field` applied (payroll.py:4167, 4235-4237) |
| Cross-module | **FAIL (High)** — new Benefit Schemes feature changes payslip net_pay/total_cost but the payroll journal does not post it |
| IFRS (AFS) | **PASS** — standards unchanged; deferred tax verified |
| Tax (SARS) | **PASS** — 2026/2027 table unchanged |

**Overall: 1 High, 1 Low (0 Critical).**

## 2. Reports
✓ No issues found. Revenue = paid/partial received ex-VAT via `_received_net_zar`; outstanding via `_balance_zar`/`_to_zar`; expenses excluded from revenue. companies.py now imports `VAT_RATE` from payroll (single source) — correct.

## 3. Debtors
✓ No issues found (`debtors_aging`, payroll.py ~4094: sent/overdue/partial, `due_date` buckets, ZAR balances, paid excluded).

## 4. Creditors
✓ No issues found (`creditors_aging`, payroll.py ~4157: received/partial POs, per-PO AP nets credit−debit over `purchase_order`, `purchase_order_reversal`, `po_payment`, `po_payment_reversal`; supplier bank fields decrypted).

## 5. Cross-module
- ✓ Journal coverage for invoices, expenses, PO receipt/payment and import-awareness (backfill, Rules 6/7, 3998/3999, unbalanced-group rejection, non-ZAR rate) unchanged — journal.py/csv_import.py/purchase_orders.py not modified since 24–25 Oct.
- **HIGH (new): benefit scheme contributions are not journalled.** payroll.py:1240-1282 (new, uncommitted-then-synced in 742a9a0) subtracts `benefit_employee_total` from `c["net_pay"]` and adds `benefit_employer_total` to `c["total_cost"]`; payroll.py:1312-1313 persist them on the Payslip. The payroll journal builder (journal.py ~712-880) has no line for benefits (grep: no `benefit` reference in journal.py; only `benefit_contributions_json` is stored, database.py:367). Consequences for any employee enrolled in an active scheme: the entry credits Bank for the *reduced* net pay with no offsetting credit (Benefits payable) → debits exceed credits by the employee deduction → `_assert_balanced` raises (residue > 5c) and **the payroll run aborts**; employer benefit cost is never expensed; `total_cost` (used by reports/AFS) diverges from the journal. This is the same class of gap as the 2026-09/10 MIBCO/NBCPSS/garnishee fixes. Fix: add DR 5xxx Employer benefit contribution (employer) / CR a new Benefits payable liability (employee + employer), mirroring the pension/medical blocks; add a regression case to `test_payroll_journal_balance.py`.
- Live control-account reconciliation not executed here; see `reconciliation_2026-10-26.md` / `journal_integrity_2026-10-26.md`.
- Resolved since last run: staged remediation committed (HEAD 742a9a0). main.py clear-data now deletes the bank-feed transaction models and `CompanyDocument` (valid imports, compiles).
- Carried Low: untracked `commit_and_push.ps1`, `zuzan-app/public/sw.js`, `zuzan-backend/_to_delete/`, `find_default_password_accounts.py`, `fix_credit_note_vat_account.py`.

## 6. IFRS compliance (AFS)
- Framework unchanged: IFRS for SMEs (2nd ed.). IFRS 18 and IFRS for SMEs 3rd ed. both effective for periods beginning on/after 1 Jan 2027 (first ZuZan FY starting 1 Mar 2027). Searches this run returned no new announcements ([Accounting Academy](https://www.accountingacademy.co.za/news/read/updated-ifrs-for-smes-3rd-edition), [Forvis Mazars SA](https://www.forvismazars.com/za/en/services/audit-assurance/financial-reporting/ifrs-for-smes-R-accounting-standard), [IFRS Foundation news](https://www.ifrs.org/news-and-events/news/2025/02/iasb-issues-major-update-smes-accounting-standard/)). Transition plan `ifrs_smes_3rd_edition_transition_plan.md` stands.
- **5b deferred tax — verified, not hard-coded:** `_deferred_tax_balance` (financial_statements.py:139), opening/closing (:283-284), `total_tax = tax_expense + deferred_tax_expense` (:669), Note 9 (:674-677). financial_statements.py unchanged since 24 Oct. No edits.
- Finance costs below EBIT / tax from PBT: unchanged ✓.
- Note: the new benefit-scheme accounting gap (section 5) will also understate employee-benefit expense in Note 6 until journalled.

## 7. Tax updates (company + payroll)
- Tax year: **2026/2027** (1 Mar 2026 – 28 Feb 2027); `_current_tax_year()` (payroll.py:228) selects it by date. `TAX_YEARS["2026/2027"]` (payroll.py:190-203): 18% ≤R245,100 … 45% > R1,878,600; rebates R17,820 / R9,765 / R3,249; UIF ceiling R17,712 — unchanged and consistent with [SARS rates of tax](https://www.sars.gov.za/tax-rates/income-tax/rates-of-tax-for-individuals/) and [Budget 2026 Tax Guide](https://www.treasury.gov.za/documents/national%20budget/2026/sars/Budget%202026%20Tax%20guide.pdf) as verified 25 Oct (search this run returned titles only, no changes: [Employer Guide 2027](https://www.sars.gov.za/guide-for-employers-in-respect-of-employees-tax-2027/), [Xero SARS tax tables 2026](https://www.xero.com/za/guides/sars-tax-tables-2026/)).
- UIF 1%+1%, SDL 1%, VAT 15%, CIT 27%: no announced changes found. Provisional `2027/2028` entry (payroll.py:210, flagged `provisional`) must be replaced after Budget Feb 2027. No tax-table edits made.

## 9. Remediation (28 Oct 2026)
**High #1 FIXED.** journal.py: added accounts 2330 Benefit Schemes Payable and 5190 Employer Benefit Scheme Contributions (upserted by `init_accounts`), `import json`, and `post_payroll` now reads `benefit_contributions_json` and posts DR 5190 (employer share) / CR 2330 (employee + employer). New regression scenario in `test_payroll_journal_balance.py` — all 18 scenarios balance.

## 8. Action items
**High**
1. Journal benefit-scheme contributions in the payroll posting (journal.py ~800-850): DR employer benefit expense, CR benefits payable (employee + employer); add test in `test_payroll_journal_balance.py`. Until fixed, avoid enrolling employees in benefit schemes (payroll run will abort with an unbalanced journal).
**Low**
2. Commit or delete untracked helper files / `_to_delete/`; run full pytest suite locally.

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS-for-SMEs 3rd-ed. checklist Jan–Feb 2027; EMP501 annual reconciliation due 31 Oct 2026.
