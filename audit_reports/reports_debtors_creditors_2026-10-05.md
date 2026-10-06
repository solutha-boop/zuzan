# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 5 October 2026 (scheduled run, ~22:20 UTC)
**Prior report:** 2026-10-04 (incl. addendum)

**Change detection:** HEAD `f2f08d3` (unchanged since the prior report). Working tree has uncommitted edits only in `App_js_fixed.js` / `zuzan-app/src/App.js` (+28/-2 each): `InvoiceDocument` now renders company address / VAT no. / reg no. / phone / email under the logo on the built-in invoice layouts (`App_js_fixed.js` ~:1325-1347, :1394, :1435, :1479, :1527). This is presentation only — no change to Reports, Debtors, Creditors or AFS data flow. No backend file changed (`payroll.py` mtime 4 Oct 07:42; `financial_statements.py` 21 Jul; `journal.py` 19 Sep; `purchase_orders.py` 13 Jul). `py_compile` passes on `payroll.py`, `financial_statements.py`, `database.py`, `journal.py`, `purchase_orders.py`. No code edits made this run.

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | ✅ PASS — unchanged |
| Debtors (AR) | ✅ PASS — unchanged |
| Creditors (AP) | ✅ PASS — reversal-awareness intact |
| Cross-module | ✅ PASS — import-awareness intact |
| IFRS (AFS) | ✅ PASS — no standards change; deferred tax (5b) already implemented |
| Tax (SARS) | ✅ PASS — 2026/2027 tables present; no rate changes found |

**Overall: PASS.** No Critical/High/Medium findings.

## 2. Reports
✓ No issues found. `dashboard()` `payroll.py:1658`, `management_accounts()` `:2870` unchanged. `/v1/summary` in `main.py` still imports and applies `_to_zar` (`main.py:469, :473, :503`).

## 3. Debtors
✓ No issues found. `debtors_aging()` `payroll.py:3268` unchanged (`_to_zar`, aged from `due_date`, paid excluded).

## 4. Creditors
✓ No issues found. `creditors_aging()` `payroll.py:3331` unchanged. Reversal-aware (`purchase_order` + `purchase_order_reversal`) lookups re-grepped at `payroll.py:2212, :2684, :3366`, `journal.py:1158`, `purchase_orders.py:445`.

## 5. Cross-module
✓ No issues found. `journal.py`, `csv_import.py`, `purchase_orders.py`, `database.py` unchanged since the last full verification, so journal coverage and import-awareness checks stand.

## 6. IFRS compliance (AFS)
- Framework: IFRS for SMEs (`financial_statements.py`, unchanged since 21 Jul). IFRS 18 and IFRS for SMEs 3rd edition remain effective for periods beginning on/after 1 Jan 2027; no change since last audit. Transition plan `ifrs_smes_3rd_edition_transition_plan.md` stands.
- **5b deferred tax:** already computed (no `"deferred_tax": 0.0` hard-code). `_deferred_tax_balance()` `financial_statements.py:131`; `FixedAsset.wear_and_tear_rate` `database.py:544`; migration inside list literal `database.py:1509`. No edits needed.
- Finance costs below EBIT / tax from profit_before_tax: unchanged.

## 7. Tax updates (company + payroll)
- Tax year: 2026/2027 (1 Mar 2026 – 28 Feb 2027). `TAX_YEARS["2026/2027"]` `payroll.py:132`; provisional `"2027/2028"` `:152`; UIF/SDL 1% `:189-190`; `VAT_RATE=0.15`; `CORP_TAX_RATE=0.27`.
- Web search this run returned only the same aggregator / Treasury Budget 2026 tax guide results as before, with no signal of a rate change. Previously verified figures stand: CIT 27%, VAT 15%, primary rebate R17,820, UIF ceiling R17,712/month. No edits (report-only).
- Sources: [Budget 2026 Tax guide (Treasury)](https://www.treasury.gov.za/documents/national%20budget/2026/sars/Budget%202026%20Tax%20guide.pdf), [accounter.co.za SARS tax tables 2026/27](https://accounter.co.za/news/sars-tax-tables-2026-2027), [Xero SA tax tables 2026](https://www.xero.com/za/guides/sars-tax-tables-2026/), [ourpower tax brackets 2026](https://www.ourpower.co.za/sars/tax-brackets-2026).

## 8. Action items
No Critical / High / Medium items.
1. **Low (carried)** — confirm `reclass_expenses_2026-09-28.py` was run against production; decide on history purge of `zuzan.db` in origin; delete `zuzan.db.bak-20260928-184955`.
2. **Low (carried)** — backfill NULL `paid_date` / `expense_date` so the COALESCE period filters in `management_accounts()` can use indexes.
3. **Info (carried)** — `.git/index.lock` cannot be unlinked from the audit shell; harmless. Uncommitted frontend edits (invoice company details) await commit.

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS-for-SMEs 3rd edition / IFRS 18 checklist early 2027; ConCourt VAT s7(4) ruling pending; MIBCO Sector 5 Year 2 contributions TBC.
