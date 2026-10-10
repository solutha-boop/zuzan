# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 9 October 2026 (scheduled run)
**Prior report:** 2026-10-08

**Change detection:** HEAD `c17962b` (unchanged since last run). `git status` shows no modified tracked files (only the untracked prior audit report and `zuzan-backend/_to_delete/`). `py_compile` passes on payroll, financial_statements, database, journal, purchase_orders, main, companies, csv_import. No code edits made this run. Light spot-check run.

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | PASS |
| Debtors (AR) | PASS |
| Creditors (AP) | PASS — reversal-awareness intact |
| Cross-module | PASS |
| IFRS (AFS) | PASS — no standards change; deferred tax (5b) already implemented |
| Tax (SARS) | PASS — 2026/2027 table present; no rate changes found |

**Overall: PASS.** No Critical/High/Medium findings.

## 2. Reports
✓ No issues found. `_to_zar()` at `payroll.py:18`; sources unchanged since last audit.

## 3. Debtors
✓ No issues found. `debtors_aging()` `payroll.py:3298` unchanged.

## 4. Creditors
✓ No issues found. `creditors_aging()` `payroll.py:3361`. Reversal-aware lookups (`purchase_order` + `purchase_order_reversal`) re-grepped: `payroll.py:2242, :2714, :3396`, `journal.py:1158`, `purchase_orders.py:445`.

## 5. Cross-module
✓ No issues found. `journal.py`, `csv_import.py`, `purchase_orders.py` unchanged.

## 6. IFRS compliance (AFS)
- Framework: IFRS for SMEs (`financial_statements.py`), unchanged. IFRS 18 and IFRS for SMEs 3rd edition remain effective for periods beginning on/after 1 Jan 2027; no change found. Transition plan `ifrs_smes_3rd_edition_transition_plan.md` stands.
- **5b deferred tax:** already computed (`"deferred_tax": deferred_tax_expense` `financial_statements.py:606`); `FixedAsset.wear_and_tear_rate` at `database.py:545`, migration inside list at `database.py:1510`. Verified, no edits needed.
- Finance costs below EBIT / tax from profit_before_tax: unchanged.
- Sources: [Forvis Mazars – IFRS for SMEs new edition](https://www.forvismazars.com/za/en/services/audit-assurance/financial-reporting/ifrs-for-smes-R-accounting-standard), [IFRS Foundation 3rd edition overview](https://ifrs.org/content/dam/ifrs/supporting-implementation/smes/2025-webcasts/overview-third-edition-ifrs-for-smes.pdf).

## 7. Tax updates (company + payroll)
- Tax year: 2026/2027 (1 Mar 2026 – 28 Feb 2027). `TAX_YEARS["2026/2027"]` `payroll.py:132`; provisional `"2027/2028"` `:152`; `_current_tax_year()` `:170`. `VAT_RATE=0.15` (`:2072, :2466, :3553`); `CORP_TAX_RATE=0.27` `:3197`.
- Web search this run surfaced no announced change to the 15% VAT or 27% CIT rates. Report-only; no edits.
- Sources: [Grant Thornton Budget 2026 analysis](https://www.grantthornton.co.za/insights2/2026-budget-analysis-and-commentary/), [PwC SA corporate taxes](https://taxsummaries.pwc.com/south-africa/corporate/taxes-on-corporate-income).

## 8. Action items
No Critical / High / Medium items.
1. **Low (carried)** — confirm `reclass_expenses_2026-09-28.py` was run on production; decide on history purge of `zuzan.db` in origin; delete `zuzan.db.bak-20260928-184955`.
2. **Low (carried)** — backfill NULL `paid_date`/`expense_date` for index use in `management_accounts()`.
3. **Info (carried)** — untracked `zuzan-backend/_to_delete/` awaits cleanup.
4. **Info (carried)** — verify split-schedule payroll runs (security vs salaried) both post journals and feed dashboard payroll cost for the same period.

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS-for-SMEs 3rd edition / IFRS 18 checklist early 2027; ConCourt VAT s7(4) ruling pending.
