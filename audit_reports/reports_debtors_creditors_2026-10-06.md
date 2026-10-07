# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 6 October 2026 (scheduled run)
**Prior report:** 2026-10-05

**Change detection:** HEAD `9629530` (was `f2f08d3`). Commits since last report touched `zuzan-backend/payroll.py` (+52/-… NBCPSS payroll-engine rules: Sunday 1.5x, PH 1.0x, s11F/PSSPF, UIF base includes employer provident, bargaining-council levy; payslip earnings lines), `companies.py` (`list_employees` gained `include_inactive` flag) and frontend `App_js_fixed.js` / `zuzan-app/src/App.js` (payroll upload UI, terminate/reinstate, invoice company details). The diff did NOT touch `_to_zar`, `dashboard()`, `management_accounts()`, `debtors_aging()`, `creditors_aging()`, `TAX_YEARS`, `VAT_RATE`, `CORP_TAX_RATE`, `journal.py`, `purchase_orders.py`, `csv_import.py`, `financial_statements.py` or `database.py`. `py_compile` passes on `payroll.py, financial_statements.py, database.py, journal.py, purchase_orders.py, main.py, companies.py, csv_import.py`. No code edits made this run.

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | ✅ PASS |
| Debtors (AR) | ✅ PASS |
| Creditors (AP) | ✅ PASS — reversal-awareness intact |
| Cross-module | ✅ PASS — import-awareness intact (backend files unchanged) |
| IFRS (AFS) | ✅ PASS — no standards change; deferred tax (5b) already implemented |
| Tax (SARS) | ✅ PASS — 2026/2027 table present; no rate changes found |

**Overall: PASS.** No Critical/High/Medium findings.

## 2. Reports
✓ No issues found. `_to_zar()` `payroll.py:18` (non-ZAR: `paid_amount_zar` else amount × exchange_rate; ZAR as-is). `dashboard()` `payroll.py:1674`: revenue = paid invoices via `_to_zar`; outstanding = sent+overdue via `_to_zar`; received/partial/paid POs feed COGS ex-VAT via `_po_delivered_net`; payroll from actual payslips. `management_accounts()` `:2886`. `/v1/summary` `main.py:469-503` still imports/applies `_to_zar`.
Note (Info): the NBCPSS payroll-engine changes this week alter payroll cost inputs (UIF base now includes employer provident; BC levy) — recommend a spot-check that payslip totals feeding `dashboard()` payroll cost still equal the payroll journal postings (`test_payroll_journal_balance.py`).

## 3. Debtors
✓ No issues found. `debtors_aging()` `payroll.py:3284` unchanged: filters sent+overdue (status enum has no separate pending in the code path), amounts via `_to_zar`, aged from `due_date` (no due date → not_due), paid excluded.

## 4. Creditors
✓ No issues found. `creditors_aging()` `payroll.py:3347` unchanged. Reversal-aware lookups (`purchase_order` + `purchase_order_reversal`) re-grepped: `payroll.py:2228, :2700, :3382`, `journal.py:1158`, `purchase_orders.py:445`.

## 5. Cross-module
✓ No issues found. `journal.py`, `csv_import.py`, `purchase_orders.py`, `database.py` unchanged since last full verification.

## 6. IFRS compliance (AFS)
- Framework: IFRS for SMEs (`financial_statements.py:2, :623, :717`), unchanged since 21 Jul. IFRS 18 and IFRS for SMEs 3rd edition remain effective for periods beginning on/after 1 Jan 2027; search this run found no change. Transition plan `ifrs_smes_3rd_edition_transition_plan.md` stands.
- **5b deferred tax:** already computed (no `"deferred_tax": 0.0` hard-code). `_deferred_tax_balance()` `financial_statements.py:131`; Note 9 `deferred_tax` `:606`; `FixedAsset.wear_and_tear_rate` `database.py:544`; migration inside list literal `database.py:1509`. No edits needed.
- Finance costs below EBIT / tax from profit_before_tax: unchanged.
- Sources: [Accounting Academy SA – IFRS for SMEs 3rd ed.](https://www.accountingacademy.co.za/news/read/updated-ifrs-for-smes-3rd-edition), [Forvis Mazars SA](https://www.forvismazars.com/za/en/services/audit-assurance/financial-reporting/ifrs-for-smes-R-accounting-standard), [IFRS Foundation overview](https://ifrs.org/content/dam/ifrs/supporting-implementation/smes/2025-webcasts/overview-third-edition-ifrs-for-smes.pdf).

## 7. Tax updates (company + payroll)
- Tax year: 2026/2027 (1 Mar 2026 – 28 Feb 2027). `TAX_YEARS["2026/2027"]` `payroll.py:132` (brackets to 45% above R1,878,600; primary R17,820, secondary R9,765, tertiary R3,249; UIF ceiling R17,712); provisional `"2027/2028"` `:152`; UIF/SDL 1% `:189-190`; SDL threshold R500k `:623`; `VAT_RATE=0.15` (`:2058, :2452, :3539`); `CORP_TAX_RATE=0.27` `:3183`.
- Web search returned the same sources as prior runs (SARS employer guide 2027, Treasury Budget 2026 tax guide, aggregators) with no signal of a rate change. CIT 27%, VAT 15%, UIF ceiling R17,712 stand. Report-only; no edits.
- Sources: [SARS Guide for Employers 2027](https://www.sars.gov.za/guide-for-employers-in-respect-of-employees-tax-2027/), [Budget 2026 Tax guide](https://www.treasury.gov.za/documents/national%20budget/2026/sars/Budget%202026%20Tax%20guide.pdf), [Xero SA tax tables 2026](https://www.xero.com/za/guides/sars-tax-tables-2026/), [ourpower tax brackets](https://www.ourpower.co.za/sars/tax-brackets-2026).

## 8. Action items
No Critical / High / Medium items.
1. **Low (carried)** — confirm `reclass_expenses_2026-09-28.py` was run on production; decide on history purge of `zuzan.db` in origin; delete `zuzan.db.bak-20260928-184955`.
2. **Low (carried)** — backfill NULL `paid_date`/`expense_date` for index use in `management_accounts()`.
3. **Info** — untracked `zuzan-backend/_to_delete/` and uncommitted `App_js_fixed.js` edits await commit/cleanup.
4. **Info (new)** — spot-check payroll journal vs payslip totals after the NBCPSS engine changes (see §2).

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS-for-SMEs 3rd edition / IFRS 18 checklist early 2027; ConCourt VAT s7(4) ruling pending; MIBCO Sector 5 Year 2 contributions TBC.
