# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 2 October 2026 (scheduled run)
**Prior report:** 2026-10-01

**Change detection:** HEAD `d0d844c` (was `e68546c`). `git diff e68546c HEAD` touches only `App_js_fixed.js` / `zuzan-app/src/App.js` (auto-logout inactivity timeout 10 → 30 minutes, `App_js_fixed.js` ~:15223-15235) and prior audit reports. No backend file changed (`payroll.py`, `financial_statements.py`, `journal.py`, `purchase_orders.py`, `csv_import.py`, `suppliers.py`, `customers.py`, `companies.py`, `main.py`, `database.py`), so the previous line-anchored verification stands. `py_compile` passes on `payroll.py`, `financial_statements.py`, `database.py`. No code edits made this run. The timeout change is not relevant to reports/AR/AP.

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | ✅ PASS — unchanged |
| Debtors (AR) | ✅ PASS — unchanged |
| Creditors (AP) | ✅ PASS — unchanged, reversal-awareness intact |
| Cross-module | ✅ PASS — unchanged; import-awareness intact |
| IFRS (AFS) | ✅ PASS — no standards change; deferred tax (5b) already implemented |
| Tax (SARS) | ✅ PASS — 2026/2027 tables current |

**Overall: PASS.** No Critical/High/Medium findings open.

## 2. Reports
✓ No issues found. `dashboard()` `payroll.py:1649`, `management_accounts()` `:2860` unchanged. `/v1/summary` in `main.py` unchanged.

## 3. Debtors
✓ No issues found. `debtors_aging()` `payroll.py:3252` unchanged.

## 4. Creditors
✓ No issues found. `creditors_aging()` `payroll.py:3315` unchanged. Reversal-aware lookups (`purchase_order` + `purchase_order_reversal`) re-grepped at `payroll.py:2202, :2674, :3350`, `journal.py:1158`, `purchase_orders.py:445`.

## 5. Cross-module
✓ No issues found. Files that implement journal coverage and import-awareness are unchanged since the last full verification.

## 6. IFRS compliance (AFS)
- Framework: IFRS for SMEs (`financial_statements.py`, unchanged since 21 Jul).
- Web check: IFRS 18 and the IFRS for SMEs 3rd edition remain effective for periods beginning on/after 1 Jan 2027; no change since last audit. Transition plan (`ifrs_smes_3rd_edition_transition_plan.md`) stands.
- **5b deferred tax:** already computed (no `"deferred_tax": 0.0` hard-code remains). `_deferred_tax_balance()` `financial_statements.py:131`, opening/closing `:266-267`, Note 9 `:606`; `FixedAsset.wear_and_tear_rate` `database.py:544`; migration inside list literal `database.py:1509`. No edits needed.
- Finance costs below EBIT / tax from profit_before_tax: unchanged.

## 7. Tax updates (company + payroll)
- Tax year: 2026/2027 (1 Mar 2026 – 28 Feb 2027). `TAX_YEARS["2026/2027"]` `payroll.py:132`; provisional `"2027/2028"` `:152`; `UIF_RATE=0.01` `:189`; `SDL_RATE=0.01` `:190`; `VAT_RATE=0.15` `:2032, :2426, :3507`; `CORP_TAX_RATE=0.27` `:3151`.
- Web search: Budget 2026 material (SARS FAQ, Treasury tax guide, BDO) shows corporate tax unchanged at 27%; no VAT rate change announced. Bracket/rebate/UIF figures verified in prior runs (primary R17,820, secondary R9,765, tertiary R3,249, UIF ceiling R17,712/month) and unchanged. No edits (report-only).
- Sources: [SARS Budget 2026 FAQ](https://www.sars.gov.za/about/sars-tax-and-customs-system/budget/budget-2026-frequently-asked-questions/), [Treasury Budget 2026 Tax Guide](https://www.treasury.gov.za/documents/national%20budget/2026/sars/Budget%202026%20Tax%20guide.pdf), [BDO corporate tax unchanged](https://www.bdo.co.za/en-za/insights/2026/budget-speech/corporate-tax-remains-unchanged,-with-a-pinch-of-positivity), [Werksmans Budget 2026](https://werksmans.com/budget-speech-2026-2027-tax-overview/), [PKF SA IFRS for SMEs](https://www.pkf.co.za/news/2026/ifrs-for-sme-conceptual-framework/), [Forvis Mazars IFRS for SMEs](https://www.forvismazars.com/za/en/services/audit-assurance/financial-reporting/ifrs-for-smes-R-accounting-standard), [PwC IASB 3rd edition](https://viewpoint.pwc.com/dt/gx/en/pwc/in_briefs/in_briefs_INT/in_briefs_INT/iasb-issues.html).

## 8. Action items
No Critical / High / Medium items.
1. **Low (carried)** — seeded example employee is `is_active=True` (R10,000 gross) and would be picked up by trial accounts' payroll runs/EMP201 until activation; consider `is_active=False` or excluding `[zuzan-example]`.
2. **Low (carried)** — confirm `reclass_expenses_2026-09-28.py` was run against production; decide on history purge of `zuzan.db` in origin; delete `zuzan.db.bak-20260928-184955`.
3. **Info (carried)** — `.git/index.lock` cannot be unlinked from the audit shell (delete-restricted); harmless.

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS-for-SMEs 3rd edition / IFRS 18 checklist early 2027; ConCourt VAT s7(4) ruling pending; MIBCO Sector 5 Year 2 contributions TBC.
