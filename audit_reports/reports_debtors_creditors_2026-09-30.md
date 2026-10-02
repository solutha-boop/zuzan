# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 30 September 2026 (scheduled run)
**Prior report:** 2026-09-29 (incl. 22:07 follow-up and 30 Sep `Employee.notes` fix note)

**Change detection:** HEAD `e68546c` (was `798be6a`). `git diff 798be6a HEAD` touches only `database.py` (+2: `Employee.notes` column + `ALTER TABLE employees ADD COLUMN notes TEXT` inside the migrations list literal — the previously reported Medium fix) and the prior audit report. `payroll.py`, `financial_statements.py`, `journal.py`, `purchase_orders.py`, `csv_import.py`, `suppliers.py`, `customers.py`, `companies.py`, `main.py`, `App_js_fixed.js` are unchanged since the last fully verified baseline. `database.py` passes `py_compile`. No file edits were made this run.

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | ✅ PASS — unchanged |
| Debtors (AR) | ✅ PASS — unchanged |
| Creditors (AP) | ✅ PASS — unchanged, reversal-awareness intact |
| Cross-module | ✅ PASS — unchanged; import-awareness intact |
| IFRS (AFS) | ✅ PASS — no standards change; deferred tax (5b) present, no edit needed |
| Tax (SARS) | ✅ PASS — 2026/2027 tables current, no rate changes found |

**Overall: PASS.** No Critical/High/Medium findings open.

## 2. Reports
✓ No issues found. Anchors re-grepped in `payroll.py`: `dashboard()` `:1649`, `total_revenue = sum(_to_zar(i)…)` paid only `:1661`, `total_outstanding` `:1669`, `management_accounts()` `:2860`, outstanding `:2969` (`_to_zar`). `/v1/summary` (main.py) unchanged.

## 3. Debtors
✓ No issues found. `debtors_aging()` `payroll.py:3252` unchanged (`_to_zar`, aged from `due_date`, paid excluded).

## 4. Creditors
✓ No issues found. `creditors_aging()` `payroll.py:3315` unchanged (received/partial POs, paid excluded, `decrypt_field` on bank details, `credit − debit` with `purchase_order` + `purchase_order_reversal`).

## 5. Cross-module
✓ No issues found. Journal coverage (invoice/expense payments, PO receipt/payment, payroll) and import-awareness (auto backfill, Rules 6/7 excluding `source="import"`, 3998/3999, unbalanced import groups rejected, non-ZAR import requires rate) are in byte-identical files.
- Verified: `Employee.notes` fix (`database.py`) removes the seed/cleanup mismatch reported 29 Sep.

## 6. IFRS compliance (AFS)
- Framework: IFRS for SMEs (`financial_statements.py` `meta.basis`); file unchanged.
- Web check: IFRS 18 and IFRS for SMEs 3rd edition both still effective for periods beginning on/after 1 Jan 2027 (PKF SA, Forvis Mazars, PwC, ACCA, Moore SA). No change since prior audit; transition plan stands.
- **5b deferred tax:** already implemented — `_deferred_tax_balance()` `financial_statements.py:131`; Note 9 `"deferred_tax"` `:606`; `FixedAsset.wear_and_tear_rate` `database.py:544`; migration in list literal `database.py:1509`. No edits.
- Finance costs below EBIT / tax from profit_before_tax: unchanged.

## 7. Tax updates (company + payroll)
- Tax year: 2026/2027 (1 Mar 2026 – 28 Feb 2027). `TAX_YEARS["2026/2027"]` `payroll.py:132`; provisional `"2027/2028"` `:152`; `UIF_RATE=0.01` `:189`; `SDL_RATE=0.01` `:190`; `VAT_RATE=0.15` `:2032, :2426, :3507`; `CORP_TAX_RATE=0.27` `:3151`.
- Web search: no new rate/bracket/rebate/VAT changes found. No edits (report-only).
- Sources: [SARS Budget 2026 FAQ](https://www.sars.gov.za/about/sars-tax-and-customs-system/budget/budget-2026-frequently-asked-questions/), [Treasury Budget 2026 Tax Guide](https://www.treasury.gov.za/documents/national%20budget/2026/sars/Budget%202026%20Tax%20guide.pdf), [SARS Companies/SBC rates](https://www.sars.gov.za/tax-rates/income-tax/companies-trusts-and-small-business-corporations-sbc/), [Xero SARS tax tables 2026/27](https://www.xero.com/za/guides/sars-tax-tables-2026/), [Werksmans Budget 2026](https://werksmans.com/budget-speech-2026-2027-tax-overview/), [PKF SA IFRS for SMEs](https://www.pkf.co.za/news/2026/ifrs-for-sme-conceptual-framework/), [Forvis Mazars IFRS for SMEs](https://www.forvismazars.com/za/en/services/audit-assurance/financial-reporting/ifrs-for-smes-R-accounting-standard), [PwC IASB 3rd edition](https://viewpoint.pwc.com/dt/gx/en/pwc/in_briefs/in_briefs_INT/in_briefs_INT/iasb-issues.html).

## 8. Action items
No Critical / High / Medium items.
1. **Low (carried)** — seeded example employee is `is_active=True` (R10,000 gross) and would be picked up by trial accounts' payroll runs/EMP201 until activation; consider `is_active=False` or excluding `[zuzan-example]`.
2. **Low (carried)** — confirm `reclass_expenses_2026-09-28.py` was run against production; history purge decision for `zuzan.db` in origin; delete `zuzan.db.bak-20260928-184955`.
3. **Info** — `.git/index.lock` cannot be unlinked from the audit shell (delete-restricted); harmless.

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS-for-SMEs 3rd edition / IFRS 18 checklist early 2027; ConCourt VAT s7(4) ruling pending; MIBCO Sector 5 Year 2 contributions TBC.
