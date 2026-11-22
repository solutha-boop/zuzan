# ZuZan Audit: Reports, Debtors & Creditors
**Date:** 21 November 2026 (scheduled run)
**Prior report:** 2026-11-19 (there is no 2026-11-20 report)

**Method:** I compared the working tree against the commit the last report audited (c3083f3), re-ran the anchor greps on every finding, and did web checks for IFRS and SARS changes. There was no live DB and I did not re-run the tests. **No code was edited** this run: 5b is already implemented and the tax tables are report-only.

**Changes since the last report:** none in code. The only new commit, **b7fff99** (20 Nov 17:24), only adds the 2026-11-19 report. `git diff c3083f3` touches nothing except that report. The hash of each backend file with a newer mtime (auth.py, billing.py, companies.py, main.py, payroll.py) matches HEAD, and `git status` is clean. **All findings from 19 Nov carry over unchanged, and every file:line reference below was re-confirmed.**

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | **PASS**. `_to_zar` (payroll.py:23), VAT 15% (payroll.py:20) and the `/v1/summary` imports are unchanged |
| Debtors (AR) | **FAIL (High, carried)**. A bank allocation to 1100 credits Debtors Control without settling an invoice (App_js_fixed.js:9422 → companies.py:2282) |
| Creditors (AP) | **FAIL (High, carried, same root cause)**. A bank allocation to 2110→2000 (journal.py:307) bypasses `pay_po`/expense-pay |
| Cross-module | **FAIL (High + Medium, carried)**. Rules 6/7 do not know `bank_import_transfer`. PPE bought through bank allocation bypasses the fixed-asset register |
| IFRS (AFS) | **PASS with 1 Medium (carried)**. Standards unchanged and deferred tax verified. 1211-1222 / 2410 / 2420 are misclassified as current and their cash flows land in operating |
| Tax (SARS) | **PASS with 1 Low (carried)**. Tables current. The stale PAYE example is still at App_js_fixed.js:13667 |

**Overall: 0 Critical, 1 High, 2 Medium, 1 Low open in code (plus owner actions). Nothing new and nothing closed.**

## 2. Reports
✓ No issues found. The dashboard, management and `/v1/summary` logic is unchanged since the last report. Revenue is paid invoices only via `_to_zar`. Outstanding is pending + overdue via `_to_zar`. Payroll is in expenses, received-PO cost comes through `_po_cost_net` with no double count, the tax provision is 27%, and the management trend loop uses `_to_zar`.

## 3. Debtors
**High (carried from 19 Nov): bank receipts allocated to Debtors Control bypass the invoice sub-ledger.** App_js_fixed.js:9422 still offers `"1100":"Customer paid what they owed"`, and companies.py:2282 still routes it through `is_balance_sheet_allocation` → `post_bank_transfer` (DR 1000 / CR 1100) before invoice matching. As a result, `debtors_aging` and AFS Note 3 still show the invoice as outstanding, and Rule 6 fails. The allocation memory also learns the mapping, so it repeats on later statements.
Debtors otherwise ✓: sent/overdue/partial, aged from `due_date`, ZAR balances, paid excluded.

## 4. Creditors
**High (carried, same root cause):** App_js_fixed.js:9422 offers `"2110":"Paid a supplier we owed"`, and `COA_LEDGER_ALIAS` (journal.py:307) maps it to 2000. It posts as `bank_import_transfer` with no `source_id`, so the PO stays received/unpaid. If the user then also pays the PO with `pay_po`, Bank is double-credited.
Creditors otherwise ✓: the reversal-aware netting (credit − debit, including `purchase_order_reversal`) is intact at all sites. Received-unpaid POs are outstanding, fully paid POs are excluded, and supplier bank details are decrypted via `decrypt_field`.

## 5. Cross-module
- **High (carried):** see §3/§4. Rules 6/7 exclude only `import`/`import_reversal` on 1100/2000.
- **Medium (carried):** PPE allocations to 1212-1214 skip the 1500/1510 PPE ledger and the `FixedAsset` register. That means no depreciation, no Note 2 line, no deferred-tax temporary difference and no investing cash outflow.
- **Low observation (carried):** allocations to 1130→1200 change the stock ledger without changing InventoryItem quantities.
- Journal coverage (invoice payments, expense payments, PO receipt and payment, payroll runs) ✓. Import-awareness is unchanged ✓: auto backfill runs, unbalanced groups are rejected, non-ZAR imports need a rate, and 3998/3999 are handled on the balance sheet.

## 6. IFRS compliance (AFS)
- The framework is unchanged: IFRS for SMEs (2nd ed.) presentation. IFRS 18 and IFRS for SMEs 3rd ed. are effective for annual periods beginning on or after 1 Jan 2027; the first affected ZuZan FY starts 1 Mar 2027. Searches found no deferral and no new pronouncement. **Standards are unchanged since the prior report.**
- **5b deferred tax: verified, still computed.** `_deferred_tax_balance` is at financial_statements.py:143 and Note 9 `deferred_tax` (movement) at :690. The `wear_and_tear_rate` column is at database.py:609, with its migration inside the list at :1638 and normalisation at :1642. CIT is 27%.
- Finance costs are below EBIT, and `profit_before_tax = ebit − finance_costs` is at financial_statements.py:288 ✓.
- **Medium (carried):** the current/non-current split uses code thresholds (financial_statements.py:309-322; cash flow :451-485), so the bank-allocation accounts 1211-1222 and the 2410/2420/2150/2160 loans are presented as current, and their cash flows land in operating. The aliases are still at journal.py:310.
- Sources: [IFRS 18 — IFRS Foundation](https://www.ifrs.org/issued-standards/list-of-standards/ifrs-18-presentation-and-disclosure-in-financial-statements/), [IASB technical update, Nov 2026](https://www.ifrs.org/content/dam/ifrs/meetings/2026/november/eeg/ap3-iasb-technical-update.pdf), [IAS Plus — effective 2027](https://www.iasplus.com/en/events/effective-dates/2027).

## 7. Tax updates (company + payroll)
- Tax year at run date: **2026/2027**. All of the following are unchanged:
  - `TAX_YEARS["2026/2027"]` (payroll.py:312): rebates R17,820 / R9,765 / R3,249, UIF ceiling R17,712
  - provisional "2027/2028" entry (payroll.py:332)
  - `_current_tax_year` (payroll.py:350)
  - `SDL_RATE = 0.01` (payroll.py:370)
  - UIF 1%/1%
  - VAT 15% (payroll.py:20)
  - CIT 27%

  I found no new SARS or Treasury rate announcements.
- **Low (carried):** App_js_fixed.js:13667 still says "PAYE ≈ R4,673/month after the R17,235 primary rebate". On the 2026/27 tables it should be ≈ R6,135 with a R17,820 rebate.
- Sources: [SARS — Rates of tax for individuals](https://www.sars.gov.za/tax-rates/income-tax/rates-of-tax-for-individuals/), [SARS — What's new](https://www.sars.gov.za/whats-new-at-sars), [SARS — Companies & SBC](https://www.sars.gov.za/tax-rates/income-tax/companies-trusts-and-small-business-corporations-sbc/).

## 8. Action items
**High**
1. (Carried) companies.py:2282 / journal.py:704 / App_js_fixed.js:9422: block or redirect bank allocations to 1100 and 2110→2000. Route receipts to invoice matching and payments to `pay_po` or expense-pay, and purge `allocation_memory` rows that point at 1100/2110.

**Medium**

2. (Carried) journal.py:304-312 / financial_statements.py:309-322, 451-485: fix the current/non-current and cash-flow classification of 1211-1222, 2410/2420 and 2150/2160.
3. (Carried) App_js_fixed.js:9421 / companies.py:2282: PPE allocations should post to 1500 and create a `FixedAsset` record.

**Low**

4. (Carried) App_js_fixed.js:13667 / zuzan-app/src/App.js:13667: update the offline PAYE example.
5. (Carried, observation) Add a UI warning that 1130→1200 allocations do not change inventory quantities.
6. (Owner) Run the GL account-type review / `reclassify-gl-accounts` in prod.
7. (Owner) POPIA privacy page: legal review and Netlify publish.
8. (Owner) Run a `check_fixed_asset_useful_life.py` dry run in prod.

**Closed since last run:** none.

**Standing reminders:**
- After Budget Feb 2027, replace the provisional 2027/2028 `TAX_YEARS` entry and add the 2027/28 SBC table.
- Run the IFRS 18 / IFRS for SMEs 3rd ed. checklist in Jan–Feb 2027.
