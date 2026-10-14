# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 13 October 2026 (scheduled run)
**Prior report:** 2026-10-12

**Change detection:** HEAD `4f228ba` (prior audit HEAD `5f21fa9`; 17 commits). Changed since: `payroll.py` (+239/-?: NBCPSS payslip/provident/BC levy fixes, all-or-nothing payroll run, DELETE payroll period endpoint, Sunday-ordinary 1.5x flag), `companies.py`/`database.py`/`csv_import.py` (new `sunday_ordinary` employee field), `auth.py` (case-insensitive email), URL/email tweaks, frontend. `py_compile` passes on payroll, journal, financial_statements, database, purchase_orders, main, companies, csv_import, suppliers. `journal.py`, `financial_statements.py`, `purchase_orders.py`, `suppliers.py` unchanged. Line numbers in payroll.py shifted ~+150 vs. prior report. No code edits made by this audit. (No live DB data re-queried; local zuzan.db unchanged since 28 Sep.)

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | PASS |
| Debtors (AR) | PASS |
| Creditors (AP) | PASS — reversal-awareness intact |
| Cross-module | PASS (journal/import code unchanged) |
| IFRS (AFS) | PASS — no standards change; deferred tax (5b) already implemented |
| Tax (SARS) | PASS on rates/tables; **carried Medium now CONFIRMED: EMP501 IRP5 code 4142** |

**Overall: PASS with one confirmed defect (EMP501 export code), deadline 31 Oct 2026.**

## 2. Reports
✓ No issues found. `_to_zar()` `payroll.py:18`; dashboard revenue/outstanding `:2090, :2098`; trend loop `:2251`, management accounts `:3327, :3405, :3422`; cash receipts `:2771`. Tax provision 27% `:2143, :3396, :3587`. `/v1/summary` in `main.py:469-503` imports and uses `_to_zar`, `_po_delivered_net` (received POs as COGS, ex-VAT). Revenue sums paid invoices only; expenses excluded.

## 3. Debtors
✓ No issues found. `debtors_aging` `payroll.py:3688`: statuses sent+overdue (no distinct "pending" state in this path — unchanged since earlier passing audits), ageing from `due_date` (no-due-date → `not_due`), ZAR via `_to_zar` `:3710`, paid excluded.

## 4. Creditors
✓ No issues found. `creditors_aging` `payroll.py:3751`. Reversal-aware `purchase_order` + `purchase_order_reversal` lookups: `payroll.py:2632, :3104, :3786`, `journal.py:1166`, `purchase_orders.py:445`. Supplier bank details decrypted via `decrypt_field` `payroll.py:3829-3831`.

## 5. Cross-module
✓ No issues found. Latest journal integrity (`journal_integrity_2026-10-12.md`): 0 gaps. Import-awareness: `_auto_backfill` still called in `csv_import.py:125-137`; journal.py unchanged; `csv_import.py` diff is limited to the `sunday_ordinary` employee alias. Note: new all-or-nothing payroll run and DELETE payroll period endpoint should be re-verified for journal reversal of deleted periods (Low, see action items).

## 6. IFRS compliance (AFS)
- Framework: IFRS for SMEs (`financial_statements.py` unchanged since 21 Jul). No change in standards: IFRS 18 and IFRS for SMEs 3rd edition both effective for periods beginning on/after 1 Jan 2027 (early application permitted). Transition plan `ifrs_smes_3rd_edition_transition_plan.md` stands. Sources: [Forvis Mazars SA](https://www.forvismazars.com/za/en/services/audit-assurance/financial-reporting/ifrs-for-smes-R-accounting-standard), [Accounting Academy](https://www.accountingacademy.co.za/news/read/updated-ifrs-for-smes-3rd-edition).
- **5b deferred tax:** already implemented — `_deferred_tax_balance` `financial_statements.py:131`, opening/closing movement `:266-268`, `total_tax` incl. deferred `:601`, `wear_and_tear_rate` resolution `:107-110`. Verified; no edits.
- Finance costs below EBIT; tax from profit_before_tax: unchanged ✓.

## 7. Tax updates (company + payroll)
- Tax year: 2026/2027 (1 Mar 2026 – 28 Feb 2027). `TAX_YEARS["2026/2027"]` `payroll.py:132-148`: 18% to R245,100 … 45% > R1,878,600; rebates R17,820 / R9,765 / R3,249; UIF ceiling R17,712 — unchanged, match Budget 2026. Provisional `"2027/2028"` `:152` flagged. `_current_tax_year()` `:171` selects by date.
- UIF 1%+1% `:189`, SDL 1% `:190` (R500k threshold `:739`), VAT 15% (`:2462, :2856, :3943`), CIT 27% — no announced changes found. Sources: [SARS Guide for Employers 2027](https://www.sars.gov.za/guide-for-employers-in-respect-of-employees-tax-2027/), [Grant Thornton Budget 2026](https://www.grantthornton.co.za/contentassets/334ab82b24354cfa91de433a7de8ed56/2026-budget-analysis-and-commentary_fa.pdf).
- **CONFIRMED (Medium→High given deadline) — `payroll.py:1975` interim EMP501 export** emits employee UIF as IRP5 code `4142`. Per [TaxTim IRP5 guide](https://www.taxtim.com/blog/finding-your-way-around-an-irp5-2): 4141 = employee+employer UIF; 4142 = SDL; 4149 = total PAYE+SDL+UIF. So the file reports UIF under the SDL code. Also verify `4005` (`:1977`) and `4474` (`:1979`; not on the cited list — SDL belongs in 4142) against the current SARS BRS code list. Same codes mirrored in the JSON summary at `:1700, :1714`.

## 8. Action items
**Critical:** none.
**High**
1. `payroll.py:1975-1979` — emit UIF (employee+employer) as 4141 and SDL as 4142; validate 4005/4474 against the SARS BRS; fix before the 31 Oct 2026 interim EMP501 submission.
**Medium**
2. Verify the new DELETE payroll period endpoint reverses/removes the corresponding payroll journal entries (avoid orphaned 2xxx/6xxx postings).
**Low**
3. Confirm NBCPSS clause-8 bonus formula with the Council.
4. (carried) Confirm `reclass_expenses_2026-09-28.py` run on production; decide `zuzan.db` history purge; delete `zuzan.db.bak-20260928-184955`.
5. (carried) Backfill NULL `paid_date`/`expense_date` for `management_accounts()`.
6. (carried, Info) Clean untracked `zuzan-backend/_to_delete/`, `commit_and_push.ps1`.

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS-for-SMEs 3rd ed./IFRS 18 checklist early 2027.
