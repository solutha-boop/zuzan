# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 11 October 2026 (scheduled run; fired late, originally due 10 Oct 22:18 UTC)
**Prior report:** 2026-10-09

**Change detection:** HEAD `e31144c` (was `c17962b`). Since last run: five "dual pay schedule" commits (payroll payslip layout, PAYROLL_PER_EMP/MIN pricing via `config.py`, frontend) plus **staged, uncommitted** edits adding `employment_category` (UIF/SDL exemption logic) and employee terminate/reinstate endpoints. `py_compile` passes on payroll, financial_statements, database, journal, purchase_orders, main, companies, csv_import. No code edits made by this audit. Targeted re-check of the invariants below; full re-read not repeated because the Reports/AR/AP/journal/AFS code paths are unchanged.

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | PASS |
| Debtors (AR) | PASS |
| Creditors (AP) | PASS — reversal-awareness intact |
| Cross-module | PASS |
| IFRS (AFS) | PASS — no standards change; deferred tax (5b) already implemented |
| Tax (SARS) | PASS for rates/tables; **new payroll finding (UIF exemption categories)** |

**Overall: PASS with one new Medium finding** (staged `employment_category` UIF exemptions look non-compliant).

## 2. Reports
✓ No issues found. `_to_zar()` at `payroll.py:18`; report logic not modified since last audit.

## 3. Debtors
✓ No issues found. `debtors_aging()` `payroll.py:3324` (line shifted +26 from payslip edits; logic unchanged).

## 4. Creditors
✓ No issues found. `creditors_aging()` `payroll.py:3387`. Reversal-aware lookups present (`purchase_order` + `purchase_order_reversal`): `payroll.py:2268, :2740, :3422`, `journal.py:1158`, `purchase_orders.py:445`.

## 5. Cross-module
✓ No issues found. `journal.py`, `csv_import.py`, `purchase_orders.py` unchanged since last audit.

## 6. IFRS compliance (AFS)
- Framework: IFRS for SMEs (`financial_statements.py:2`). IFRS 18 and IFRS for SMEs 3rd edition remain effective for periods beginning on/after 1 Jan 2027; no change found. Transition plan stands.
- **5b deferred tax:** already computed — `_deferred_tax_balance()` `financial_statements.py:131`, expense = closing − opening (`:266-268`), `total_tax` `:601`, `"deferred_tax"` `:606`, opening/closing balances `:609-610`. `FixedAsset.wear_and_tear_rate` `database.py:551`; migration inside the list at `database.py:1516`. Verified; no edits needed.
- Finance costs below EBIT / tax from profit_before_tax: `financial_statements.py` unchanged.

## 7. Tax updates (company + payroll)
- Tax year: 2026/2027 (SARS "2027 tax year", 1 Mar 2026 – 28 Feb 2027). `TAX_YEARS["2026/2027"]` `payroll.py:132`: brackets, primary R17,820, secondary R9,765, tertiary R3,249 — **match SARS page fetched this run**. UIF ceiling 17,712 unchanged. Provisional `"2027/2028"` `:152`; `_current_tax_year()` `:170`.
- `UIF_RATE=0.01`, `SDL_RATE=0.01` (`:189-190`), `VAT_RATE=0.15` (`:2098, :2492, :3579`), `CORP_TAX_RATE=0.27` (`:3223`): no announced changes found.
- **NEW (Medium) — `payroll.py:626` (staged, uncommitted):** `_uif_exempt` treats `learnership` and `foreign_national` as UIF-exempt. Per SimplePay's note on the UIF amendments, learners (Skills Development Act s18(2)) and employees who intend to repatriate were brought *into* UIF coverage from 1 Mar 2018; a blanket "foreign_national" exemption therefore under-deducts UIF and risks EMP201/UI-19 non-compliance. Only genuine exclusions (e.g. public servants covered by GEPF, workers <24h/month, SA-employed-abroad cases) should be exempt. `public_servant` exemption is reasonable. Recommend limiting exemptions or making them per-employee override with a legal-basis note before committing.
- **NEW (Low) — `payroll.py:633`:** `temp_labour` SDL exemption. Labour-broker workers are normally the broker's employees (broker pays SDL/UIF); if the category is used for a company's own casual staff, SDL/UIF should apply. Clarify label/help text.
- **Info — `payroll.py:3744, :3862` / `config.py`:** payroll add-on pricing now R15.50/employee, min R99 (was R18.25 / R65); pricing is consistent between initiate_payment and subscription_status. Business decision, noted only.
- **Info — `companies.py` terminate/reinstate:** `termination_date` uses `datetime.fromisoformat(data.date)`; invalid input would 500 — wrap in try/except returning 400. Migration lines at `database.py:1693-1695` are inside the list literal ✓.
- Sources: [SARS rates of tax for individuals](https://www.sars.gov.za/tax-rates/income-tax/rates-of-tax-for-individuals/), [SimplePay – UIF exclusion update](https://www.simplepay.co.za/blog/2018/03/01/uif-exclusion-update-for-learners-and-employees-who-repatriate/), [Budget 2026 Tax guide](https://www.treasury.gov.za/documents/national%20budget/2026/sars/Budget%202026%20Tax%20guide.pdf).

## 8. Action items
**Critical / High:** none.
**Medium**
1. Review/fix UIF exemption categories `payroll.py:626` (learnership, foreign_national) before committing the staged change.
**Low**
2. Clarify `temp_labour` SDL/UIF exemption semantics (`payroll.py:626,633`).
3. Validate `data.date` in `terminate_employee` (`companies.py`, ~line 1765) → 400 on bad input.
4. (carried) Confirm `reclass_expenses_2026-09-28.py` run on production; decide on `zuzan.db` history purge; delete `zuzan.db.bak-20260928-184955`.
5. (carried) Backfill NULL `paid_date`/`expense_date` for `management_accounts()`.
6. (carried, Info) Clean up untracked `zuzan-backend/_to_delete/`; verify split-schedule payroll runs (now live via dual pay schedule tabs) both post journals and feed dashboard payroll cost for the same period.

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS-for-SMEs 3rd edition / IFRS 18 checklist early 2027; ConCourt VAT s7(4) ruling pending.
