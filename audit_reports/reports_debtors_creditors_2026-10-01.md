# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 1 October 2026 (scheduled run)
**Prior report:** 2026-09-30

**Change detection:** HEAD `e68546c` (unchanged since the 30 Sep run). Working tree is clean apart from the untracked 30 Sep report. No source changes since the last verified baseline, so the previous line-anchored verification stands. This run re-grepped the key anchors, ran `py_compile` on `payroll.py`, `financial_statements.py` and `database.py` (all pass), and re-checked SARS 2026/27 figures online. No code edits were made.

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
✓ No issues found. Anchors: `dashboard()` `payroll.py:1649`, `management_accounts()` `:2860`; both unchanged (paid-only revenue and pending+overdue outstanding via `_to_zar()`, expenses excluded, payroll and received POs not double-counted). `/v1/summary` in `main.py` unchanged.

## 3. Debtors
✓ No issues found. `debtors_aging()` `payroll.py:3252` unchanged (invoice statuses, `_to_zar`, `due_date` aging, paid excluded).

## 4. Creditors
✓ No issues found. `creditors_aging()` `payroll.py:3315` unchanged. Reversal-aware lookups still present at `payroll.py:2202`, `:2674`, `:3350`, `journal.py:1158`, `purchase_orders.py:438` (`purchase_order` + `purchase_order_reversal`, credit − debit). `decrypt_field` on supplier bank details unchanged.

## 5. Cross-module
✓ No issues found. Journal coverage (invoice/expense payments, PO receipt/payment, payroll) and import-awareness (auto backfill, Rules 6/7 excluding `source="import"`, 3998/3999, unbalanced import groups rejected, non-ZAR import requires rate) are in unchanged files.

## 6. IFRS compliance (AFS)
- Framework: IFRS for SMEs (`financial_statements.py`, unchanged since 21 Jul).
- Standards: no change since the previous audit. IFRS 18 and IFRS for SMEs 3rd edition remain effective for periods beginning on/after 1 Jan 2027, so the transition plan (`ifrs_smes_3rd_edition_transition_plan.md`) stands.
- **5b deferred tax:** already computed, so no implementation was needed. `_deferred_tax_balance()` `financial_statements.py:131`, opening/closing `:266-267`, Note 9 `"deferred_tax"` `:606`. `FixedAsset.wear_and_tear_rate` `database.py:544`, migration inside the list literal `database.py:1509`.
- Finance costs below EBIT and tax derived from profit_before_tax: unchanged.

## 7. Tax updates (company + payroll)
- Tax year: 2026/2027 (1 Mar 2026 – 28 Feb 2027). `TAX_YEARS["2026/2027"]` `payroll.py:132`.
- Verified against an online SARS 2026/27 summary: brackets 18%–45% (top base R666,339 above R1,878,600), primary R17,820, secondary R9,765, tertiary R3,249, UIF 1%+1% (ceiling R17,712/month, R177.12 cap), SDL 1%. All match code.
- `VAT_RATE=0.15` (`payroll.py:2032, :2426, :3507`) and `CORP_TAX_RATE=0.27` (`:3151`): no announced change found. The source consulted this run did not cover VAT or CIT, so this relies on the 30 Sep verification of SARS/Treasury Budget 2026 material.
- Provisional `2027/2028` entry present (`payroll.py:152`). It must be replaced after Budget Feb 2027.
- Sources: [Accounter SARS tax tables 2026/27](https://accounter.co.za/news/sars-tax-tables-2026-2027), [Treasury Budget 2026 Tax Guide](https://www.treasury.gov.za/documents/national%20budget/2026/sars/Budget%202026%20Tax%20guide.pdf), plus the 30 Sep sources (SARS Budget 2026 FAQ, SARS company rates).

## 8. Action items
No Critical / High / Medium items.
1. **Low (carried)** — seeded example employee is `is_active=True` (R10,000 gross) and would be picked up by trial accounts' payroll runs/EMP201 until activation; consider `is_active=False` or excluding `[zuzan-example]`.
2. **Low (carried)** — confirm `reclass_expenses_2026-09-28.py` was run against production; decide on history purge of `zuzan.db` in origin; delete `zuzan.db.bak-20260928-184955`.
3. **Info (carried)** — `.git/index.lock` cannot be unlinked from the audit shell (delete-restricted); harmless.

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS-for-SMEs 3rd edition / IFRS 18 checklist early 2027; ConCourt VAT s7(4) ruling pending; MIBCO Sector 5 Year 2 contributions TBC.
