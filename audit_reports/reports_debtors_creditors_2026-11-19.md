# ZuZan Audit: Reports, Debtors & Creditors
**Date:** 19 November 2026 (scheduled run)
**Prior report:** 2026-11-18

**Method:** I reviewed the git changes since the last run, ran anchor greps across the backend and App_js_fixed.js, and did web checks for IFRS and SARS changes. There was no live DB and I did not re-run the tests. **No code was edited** this run: 5b is already implemented and the tax tables are report-only.

**Changes since the last report:** there is one new code commit, **c3083f3** (19 Nov 22:29), "smart bank allocation". It adds allocation.py, the `AllocationMemory` model (database.py), `COA_LEDGER_ALIAS`, `account_type_for_code`, `allocation_account` and `post_bank_transfer` (journal.py:304-360, 704), and a balance-sheet branch in the bank-statement import (companies.py:2282-2305). It also changes the bank-import UI (App_js_fixed.js ~9416-9860). The other new commit, cee4d99, only commits the 18-Nov report. financial_statements.py, purchase_orders.py, csv_import.py, suppliers.py, customers.py and fixed_assets.py are unchanged. App_js_fixed.js line numbers after ~9400 have shifted by about +188.

**This new feature affects the Debtors/Creditors control accounts and the AFS classification. I found 1 new High and 2 new Mediums.**

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | **PASS**. `_to_zar` (payroll.py:23), VAT 15% (payroll.py:20), main.py:533 imports and `revenue_basis` (payroll.py:4064) are intact |
| Debtors (AR) | **FAIL (High, new)**. A bank receipt allocated to "1100 – Customer paid what they owed" credits Debtors Control without settling any invoice |
| Creditors (AP) | **FAIL (High, same root cause)**. A payment allocated to "2110 – Paid a supplier we owed" debits 2000 without paying any PO or credit expense. Per-PO lookups are otherwise intact |
| Cross-module | **FAIL (High + Medium)**. Rules 6/7 do not know the new `bank_import_transfer` source. PPE bought through bank allocation bypasses the fixed-asset register |
| IFRS (AFS) | **PASS with 1 Medium (new)**. Standards unchanged and deferred tax still computed, but the new 1211-1214 / 2410 / 2420 ledger codes are misclassified as current, and their cash flows land in operating activities |
| Tax (SARS) | **PASS with 1 Low (carried)**. Tables current. The stale offline PAYE example is now at App_js_fixed.js:13667 |

**Overall: 0 Critical, 1 High, 2 Medium, 1 Low open in code (plus owner actions).**

## 2. Reports
✓ No issues found.
- The `/reports/dashboard`, `/reports/management` and `/v1/summary` logic is unchanged. Revenue is paid invoices only via `_to_zar`. Outstanding is pending + overdue via `_to_zar`. Expenses are excluded from revenue, payroll is in expenses, received-PO cost comes through `_po_cost_net` with no double count, and the tax provision is 27%. The revenue-basis label is still at payroll.py:4064-4065.
- Note: bank receipts now allocated to `4xxx` accounts go to the chosen revenue account via `revenue_account` → `allocation_account` (journal.py, 2026-11-19). Before this, they all landed in 4000. That is an improvement, and they remain `bank_import_income`, which the reports already count.

## 3. Debtors
**High (new): bank receipts allocated to Debtors Control bypass the invoice sub-ledger.**
- App_js_fixed.js:9422 offers `"1100":"Customer paid what they owed"` as an allocation. `is_balance_sheet_allocation` is true for 1xxx, so companies.py:2282 routes the line to `post_bank_transfer` (journal.py:704), which posts DR 1000 / CR 1100. It does this *before* the invoice-matching branch of the credit path (companies.py ~2395), so no invoice is marked paid or partial.
- Effect: `debtors_aging` (payroll.py:4292) and AFS Note 3 still show the invoice as outstanding, while the 1100 ledger balance has dropped. Rule 6 (payroll.py:3040-3075) then fails with an advice text ("run /journal/backfill") that cannot repair it. The allocation memory (allocation.learn_many, companies.py ~2448) also learns the mapping, so later statements repeat it automatically.
- Debtors otherwise ✓: sent/overdue/partial, aged from `due_date`, ZAR balances, paid excluded. Rule 6 still nets `import`/`import_reversal`.

## 4. Creditors
**High (new, same root cause): bank payments allocated to Creditors Control bypass the PO/expense sub-ledger.**
- App_js_fixed.js:9422 offers `"2110":"Paid a supplier we owed"`. `COA_LEDGER_ALIAS` (journal.py:307) maps 2110 to **2000**, and `post_bank_transfer` posts DR 2000 / CR 1000 with source `bank_import_transfer` and no `source_id`.
- Effect: `creditors_aging` (payroll.py:4355) and the per-PO lookups (payroll.py:3104, 3626, 4393; purchase_orders.py:505) only read `purchase_order`/`po_payment` sources, so the PO stays "received/unpaid". Rule 7 fails. If the user later also clicks "Pay" on the PO, `pay_po` posts a second payment: Bank is double-credited and 2000 goes into a debit balance.
- Creditors otherwise ✓: the reversal-aware netting (credit − debit, including `purchase_order_reversal`/`po_payment_reversal`) is intact at all five sites. Received-unpaid POs are outstanding, fully paid POs are excluded, and supplier bank-detail decryption is unchanged.

## 5. Cross-module
- **High:** see §3/§4. Rules 6/7 exclude only `import`/`import_reversal` on 1100/2000, so `bank_import_transfer` lines on those accounts guarantee a reconciliation failure. Recommended fix: in companies.py:2282 (or `post_bank_transfer`), refuse or redirect allocations whose resolved ledger code is 1100 or 2000. A credit to 1100 should go to the invoice-matching flow (or a "pick the invoice" prompt). A debit to 2000 should go to `pay_po` or expense-pay. Alternatively, remove 1100/2110 from `PLAIN_LABELS` and the allocation picker.
- **Medium (new): PPE bought via bank allocation bypasses the fixed-asset register.** "Bought a vehicle / computer equipment / furniture" (App_js_fixed.js:9421, codes 1212-1214) posts DR 1212/1213/1214, creating new asset accounts outside the 1500/1510 PPE ledger that fixed_assets.py uses (journal.py:109-110, 1217). No `FixedAsset` row is created, so there is no depreciation, no Note 2 line (financial_statements.py:501), no deferred-tax temporary difference (financial_statements.py:143-160), and no investing cash outflow (financial_statements.py:463-468). Recommend: route 12xx allocations to 1500 and prompt the user to create the fixed-asset record (or create it automatically).
- Low observation: 1130 → 1200 Inventory via bank allocation changes the stock ledger without touching InventoryItem quantities. Usually rare. Consider warning in the UI.
- Journal coverage (invoice payments, expense payments, PO receipts and payments, payroll runs) is unchanged ✓. Import-awareness is unchanged ✓: `_auto_backfill` (csv_import.py:126) runs at 575 and 788, unbalanced groups are rejected, non-ZAR imports need a rate, and 3998/3999 are handled on the balance sheet. The `bank_import_transfer` dedupe (companies.py:2285-2300) and the "banking" delete-category (companies.py:302) correctly include the new source ✓.

## 6. IFRS compliance (AFS)
- The framework is unchanged: IFRS for SMEs (2nd ed.) presentation. IFRS 18 and IFRS for SMEs 3rd edition are effective for annual periods beginning on or after 1 Jan 2027; the first affected ZuZan FY starts 1 Mar 2027. I found no deferral. **Standards are unchanged since the prior report.**
- **5b deferred tax: verified, still computed.** financial_statements.py is unchanged: `_deferred_tax_balance` at :143, Note 9 `deferred_tax` = movement at :690, opening/closing balances at :693-694, and the SFP line at :376-386. The `wear_and_tear_rate` column is at database.py:609 with its migration inside the list at :1638 (normalisation at :1642). `SA_CIT_RATE = 0.27` is at fixed_assets.py:84.
- Finance costs are below EBIT, and tax and net profit derive from `profit_before_tax = ebit − finance_costs` (financial_statements.py:288) ✓.
- **Medium (new): current/non-current classification of bank-allocation accounts (IFRS for SMEs s4.4-4.8 / IAS 1.66-76; cash flows s7 / IAS 7).** The SFP splits assets at code 1500 and liabilities at 2500 (financial_statements.py:309-310, 321-322). The cash flow puts codes below those thresholds in operating activities (:451-454) and only ≥1500 / ≥2500 in investing/financing (:479-485). The new feature creates PPE accounts 1211-1214 and accumulated depreciation 1221/1222 (both <1500), and it re-maps Long-term Loan → **2410** and Mortgage Bond → **2420** (journal.py:310, <2500), plus Directors Loan 2160 and Short-term Loan 2150. As a result:
  - long-term loans and bonds are shown as **current** liabilities;
  - vehicles and equipment are shown as **current** assets;
  - loan drawdowns and repayments and asset purchases are reported as **operating** cash flows instead of financing and investing.

  The total cash still reconciles, but classification is wrong. Fix options: (a) alias 1211-1214 → 1500, 1221/1222 → 1510, and 2210/2220 → codes ≥2500 (for example 2510/2520) instead of 2410/2420; or (b) give `Account` an explicit current/non-current flag and use it in financial_statements.py rather than code ranges. Also, 1221/1222 are created as plain `asset` with no contra handling.
- Sources: [IFRS 18 — IFRS Foundation](https://www.ifrs.org/issued-standards/list-of-standards/ifrs-18-presentation-and-disclosure-in-financial-statements/), [IASB technical update, Nov 2026 EEG](https://www.ifrs.org/content/dam/ifrs/meetings/2026/november/eeg/ap3-iasb-technical-update.pdf), [IASB update, Nov 2026 GPF](https://www.ifrs.org/content/dam/ifrs/meetings/2026/november/gpf/ap1a-iasb-update.pdf).

## 7. Tax updates (company + payroll)
- Tax year at run date: **2026/2027**. All of the following are unchanged:
  - `TAX_YEARS["2026/2027"]` (payroll.py:312): primary rebate R17,820, secondary R9,765, tertiary R3,249, UIF ceiling R17,712
  - provisional "2027/2028" entry (payroll.py:332)
  - `_current_tax_year` (payroll.py:350)
  - `SDL_RATE = 0.01` (payroll.py:370)
  - UIF 1%/1%
  - VAT 15% (payroll.py:20)
  - CIT 27% (fixed_assets.py:84)
  - `_SBC_TABLES` (payroll.py:3436)

  I found no new SARS or Treasury rate announcements since the Oct 2026 MTBPS.
- Note: bank lines allocated to 2121-2125 now clear the real PAYE/UIF/SDL/VAT ledgers (2200/2210/2220/2100) via `COA_LEDGER_ALIAS` ✓. 2126/2127 (income/provisional tax paid) create new liability accounts that go into debit balance when paid, which is acceptable but could be presented as an SFP asset. Low, no action needed now.
- **Low (carried): stale offline AI-fallback PAYE example.** It is now at App_js_fixed.js:13667 and zuzan-app/src/App.js:13667: "PAYE ≈ R4,673/month after the R17,235 primary rebate". On the 2026/27 tables it should be ≈ **R6,135/month** with a **R17,820** rebate.
- Sources: [SARS — Rates of tax for individuals](https://www.sars.gov.za/tax-rates/income-tax/rates-of-tax-for-individuals/), [SARS — What's new](https://www.sars.gov.za/whats-new-at-sars), [National Treasury — Budget 2026 Tax guide](https://www.treasury.gov.za/documents/national%20budget/2026/sars/Budget%202026%20Tax%20guide.pdf). I made no tax-table edits.

## 8. Action items
**High**
1. (New) companies.py:2282 / journal.py:704 / App_js_fixed.js:9422: stop bank allocations to Debtors Control (1100) and Creditors Control (2110→2000) from posting as `bank_import_transfer`. Route receipts to invoice matching and payments to `pay_po` or expense-pay, or remove these options from the picker. Also purge any `allocation_memory` rows that already point at 1100/2110.

**Medium**

2. (New) journal.py:304-312 / financial_statements.py:309-322, 451-485: fix the current/non-current and cash-flow classification of the new 1211-1222 and 2410/2420 (plus 2150/2160) accounts. Either use codes ≥1500/≥2500 or add an explicit classification flag.
3. (New) App_js_fixed.js:9421 / companies.py:2282: PPE allocations (1212-1214) should post to 1500 and create a `FixedAsset` record so that depreciation, Note 2, deferred tax and investing cash flows are complete.

**Low**

4. (Carried) App_js_fixed.js:13667 / zuzan-app/src/App.js:13667: update the offline PAYE example to ≈ R6,135/month with the R17,820 rebate, or remove the figure.
5. (New, observation) Allocations to 1130 → 1200 Inventory change the stock ledger without changing InventoryItem quantities. Add a UI warning.
6. (Owner, carried) Run the GL account-type review / `reclassify-gl-accounts` in prod for older imports.
7. (Owner, carried) POPIA privacy page: legal review and Netlify publish.
8. (Owner, carried) Run a `check_fixed_asset_useful_life.py` dry run in prod.

**Closed since last run:** none (no code fixes landed; c3083f3 is a new feature).

**Standing reminders:**
- After Budget Feb 2027, replace the provisional 2027/2028 `TAX_YEARS` entry and add the 2027/28 SBC table.
- Run the IFRS for SMEs 3rd ed. / IFRS 18 checklist in Jan–Feb 2027.
