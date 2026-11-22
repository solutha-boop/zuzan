# ZuZan Audit: Reports, Debtors & Creditors
**Date:** 22 November 2026 (scheduled run)
**Prior report:** 2026-11-21

**Method:** I checked git HEAD, the working-tree status and file mtimes against the 21 Nov run, then re-ran the anchor greps for every open finding. I also did web checks for IFRS and SARS changes. There was no live DB and I did not run the tests. **No code was edited:** 5b is already implemented and the tax tables are report-only.

**Changes since the last report:** none. HEAD is still **b7fff99** (20 Nov 17:24 SAST). The only untracked file is the 21 Nov report. No audited source file has an mtime later than 20 Nov 15:24 UTC, which is the commit time. All open findings carry over unchanged, and every file:line anchor below was re-confirmed today.

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | **PASS**. `_to_zar` (payroll.py:23), VAT 15% (payroll.py:20) and `/v1/summary` are unchanged |
| Debtors (AR) | **FAIL (High, carried)**. A bank allocation to 1100 bypasses invoice settlement (App_js_fixed.js:9422 → companies.py:2282) |
| Creditors (AP) | **FAIL (High, carried, same root cause)**. A bank allocation to 2110→2000 (journal.py:307) bypasses `pay_po`/expense-pay |
| Cross-module | **FAIL (High + Medium, carried)**. Rules 6/7 do not know `bank_import_transfer`. PPE bought through bank allocation bypasses the FixedAsset register |
| IFRS (AFS) | **PASS with 1 Medium (carried)**. Standards are unchanged and deferred tax is verified. 1211-1222 / 2410 / 2420 are misclassified as current |
| Tax (SARS) | **PASS with 1 Low (carried)**. Tables are current. The stale PAYE example is still at App_js_fixed.js:13667 |

**Overall: 0 Critical, 1 High, 2 Medium, 1 Low open in code (plus owner actions). Nothing new and nothing closed.**

## 2. Reports
✓ No issues found. The code is unchanged since 21 Nov:
- Revenue counts paid invoices only, via `_to_zar`.
- Outstanding is pending + overdue, via `_to_zar`.
- Payroll is included in expenses.
- Received-PO cost comes through `_po_cost_net`, with no double count.
- The tax provision is 27%.
- The management trend loop uses `_to_zar`.

## 3. Debtors
**High (carried): bank receipts allocated to Debtors Control bypass the invoice sub-ledger.**
- App_js_fixed.js:9422 still offers `"1100":"Customer paid what they owed"`.
- companies.py:2282 still sends it through `is_balance_sheet_allocation` → `post_bank_transfer` (DR 1000 / CR 1100) before invoice matching runs.
- As a result, the invoice still shows as outstanding in `debtors_aging` and AFS Note 3, and Rule 6 fails.
- Allocation memory learns this mapping, so the same allocation repeats on later statements.

Debtors otherwise ✓: sent/overdue/partial invoices are included, aging uses `due_date`, balances are in ZAR and paid invoices are excluded.

## 4. Creditors
**High (carried, same root cause): supplier payments allocated to 2110 bypass the PO sub-ledger.**
- App_js_fixed.js:9422 offers `"2110":"Paid a supplier we owed"`.
- journal.py:307 maps 2110 to 2000.
- The payment posts as `bank_import_transfer` with no `source_id`, so the PO stays received and unpaid.
- If the user later also runs `pay_po`, Bank is credited twice.

Creditors otherwise ✓:
- The reversal-aware netting (credit − debit, including `purchase_order_reversal`) is intact.
- Received-but-unpaid POs show as outstanding, and fully paid POs are excluded.
- Supplier bank details are decrypted with `decrypt_field`.

## 5. Cross-module
- **High (carried):** this is the same issue as §3/§4. Rules 6/7 exclude only `import`/`import_reversal` lines on 1100/2000.
- **Medium (carried):** PPE allocations to 1212-1214 skip the 1500/1510 ledger and the FixedAsset register. Those assets get no depreciation, no Note 2 line, no deferred-tax difference and no investing cash outflow.
- **Low observation (carried):** allocations to 1130→1200 change the stock ledger without changing inventory quantities.
- Journal coverage ✓: invoice payments, expense payments, PO receipts, PO payments and payroll runs all post to the journal.
- Import-awareness ✓ (unchanged):
  - invoice/expense imports still auto-run the backfill;
  - unbalanced journal import groups are still rejected;
  - non-ZAR invoice imports still require an exchange rate;
  - 3998/3999 are still included on the balance sheet.

## 6. IFRS compliance (AFS)
- **Framework:** unchanged, IFRS for SMEs (2nd ed.) presentation.
- **Upcoming standards:** IFRS 18 and IFRS for SMEs 3rd ed. apply to annual periods beginning on or after 1 Jan 2027. ZuZan's first affected FY starts 1 Mar 2027. Today's search found no deferral and no new pronouncement. **Standards are unchanged since the prior report.**
- **5b deferred tax: verified, still computed** (the hard-coded 0.0 is absent):
  - `_deferred_tax_balance` is at financial_statements.py:143.
  - Note 9 `deferred_tax` (the movement) is at :690.
  - The `wear_and_tear_rate` column is at database.py:609, and its migration sits inside the migrations list at :1638.
- **Finance costs ✓:** they sit below EBIT, and `profit_before_tax = ebit − finance_costs` is at financial_statements.py:288.
- **Medium (carried): wrong current/non-current split and cash-flow classification.**
  - The split uses code-range thresholds (financial_statements.py:309-322; cash flow :451-485).
  - As a result, 1211-1222 and the 2410/2420/2150/2160 loans are shown as current, and their cash flows land in operating activities.
  - The account aliases behind this are at journal.py:310.
- Sources: [IFRS 18 — IFRS Foundation](https://www.ifrs.org/issued-standards/list-of-standards/ifrs-18-presentation-and-disclosure-in-financial-statements/), [IASB technical update Nov 2026](https://www.ifrs.org/content/dam/ifrs/meetings/2026/november/eeg/ap3-iasb-technical-update.pdf), [IAS Plus — effective 2027](https://www.iasplus.com/en/events/effective-dates/2027).

## 7. Tax updates (company + payroll)
- **Tax year:** 2026/2027 (1 Mar 2026 – 28 Feb 2027).
- **Payroll and company rates: all unchanged.**
  - `TAX_YEARS["2026/2027"]` (payroll.py:312): rebates R17,820 / R9,765 / R3,249; UIF ceiling R17,712.
  - The provisional "2027/2028" entry is at payroll.py:332.
  - `_current_tax_year` is at payroll.py:350.
  - SDL is 1% (payroll.py:370).
  - UIF is 1% employee and 1% employer.
  - VAT is 15% (payroll.py:20).
  - CIT is 27%.
- **SARS/Treasury:** I found no new rate announcements.
- **Low (carried):** App_js_fixed.js:13667 still says "PAYE ≈ R4,673/month after the R17,235 primary rebate". On the 2026/27 tables it should be ≈ R6,135/month with a R17,820 rebate.
- Sources: [SARS — Rates of tax for individuals](https://www.sars.gov.za/tax-rates/income-tax/rates-of-tax-for-individuals/), [SARS — What's new](https://www.sars.gov.za/whats-new-at-sars), [SARS — Companies & SBC](https://www.sars.gov.za/tax-rates/income-tax/companies-trusts-and-small-business-corporations-sbc/), [Treasury — 2026 Draft Rates Bill media statement](https://www.treasury.gov.za/comm_media/press/2026/2026060401%20Media%20statement%20-%20Publication%20of%20the%202026%20Draft%20Rates%20and%20Monetary%20Amounts%20and%20Amendment%20of%20Revenue%20Laws%20Bill.pdf).

## 8. Action items
**High**
1. (Carried) companies.py:2282, journal.py:307 and App_js_fixed.js:9422: block or redirect bank allocations to 1100 and 2110→2000.
   - Send customer receipts to invoice matching.
   - Send supplier payments to `pay_po` or expense-pay.
   - Purge `allocation_memory` rows that point at 1100 or 2110.

**Medium**

2. (Carried) journal.py:304-312 and financial_statements.py:309-322, 451-485: fix the current/non-current and cash-flow classification of 1211-1222, 2410/2420 and 2150/2160.
3. (Carried) App_js_fixed.js:9421 and companies.py:2282: post PPE allocations to 1500 and create a FixedAsset record.

**Low**

4. (Carried) App_js_fixed.js:13667: update the offline PAYE example to ≈ R6,135/month with the R17,820 rebate.
5. (Carried) Add a UI warning that allocations to 1130→1200 do not change inventory quantities.
6. (Owner) Run the GL account-type review (`reclassify-gl-accounts`) in production.
7. (Owner) Get legal review of the POPIA privacy page, then publish it on Netlify.
8. (Owner) Do a dry run of `check_fixed_asset_useful_life.py` in production.

**Closed since last run:** none.

**Standing reminders:**
- After Budget Feb 2027, replace the provisional 2027/2028 `TAX_YEARS` entry.
- Run the IFRS 18 / IFRS for SMEs 3rd ed. checklist in Jan–Feb 2027.

---

## Remediation (22 Nov 2026, on request; uncommitted working-tree changes on top of 3066029)
Items 1–5 are fixed. Items 6–8 are owner actions and stay open.

1. **High — 1100 / 2110 bank allocations are fixed.**
   - **New routing.** A bank line allocated to Debtors Control (1100) or Creditors Control (2110/2000) no longer posts a loose `bank_import_transfer`. Instead, `companies._settle_bank_control_line` settles the matching document, using the same journal as Mark paid / `pay_po` / expense-pay, dated on the bank date:
     - a receipt allocated to 1100 settles the open invoice;
     - a payment allocated to 2110 settles the received PO (reversal-aware AP balance) or an unpaid on-credit expense.
     - A document named in the bank narrative is matched first. Otherwise a single document with the same amount is matched.
   - **No match:** the line is not posted. It is returned in `needs_matching` and shown in the import result.
   - **Re-imports** are detected as duplicates.
   - **Supporting changes:**
     - journal.py: `control_account_allocation()`; `post_po_paid(when=)`; `post_expense_paid` is now dated `paid_at`.
     - Rules 6/7 (payroll.py) now state how much of a difference comes from legacy `bank_import_transfer` lines on 1100/2000.
   - **Picker labels** updated (App_js_fixed.js PLAIN_LABELS).
   - **Allocation memory needs no purge:** learned 1100/2110 mappings now route to matching.
2. **Medium — current/non-current split and cash-flow classification are fixed** in financial_statements.py, through `_is_non_current_asset`, `_is_ppe_cost_code` and `_is_non_current_liab`:
   - 1210-1229 are non-current assets. Movements on 1210-1219 are investing; 1220-1229 stay in operating as the depreciation add-back.
   - 2410/2420 are non-current liabilities, and their movements are financing.
   - 2150/2160 stay current, but their movements are financing.
3. **Medium — PPE allocations are fixed.** A payment allocated to 1211-1219 or 1500 now goes through `_book_bank_asset_purchase`:
   - it creates a FixedAsset with the category from `journal.ppe_allocation_category` and the default useful life;
   - it posts DR 1500, DR 1300 (when VAT is claimable) and CR 1000 (`post_asset_acquisition(vat=)`);
   - it is deduplicated on re-import.
   - Receipts allocated to PPE are not posted and are directed to Dispose.
4. **Low — PAYE example is fixed** (App_js_fixed.js and zuzan-app/src/App.js): it now reads "≈ R6,135/month (2026/27 tables, after the R17,820 primary rebate)".
5. **Low — the inventory warning is added.** The 1130 picker label now says that stock quantities are not changed.

**Tests:**
- New: tests/test_bank_control_allocations.py (5 tests).
- Full suite: 320 passed, 1 skipped. One test was excluded: `test_payroll_journal_balance_runner`, which can't delete its scratch DB on the mounted folder. This is an environment limit, not a code issue.
- The JSX parses with @babel/parser.

**Data clean-up still needed in production:**
- Reverse any existing `bank_import_transfer` entries on 1100/2000 and settle those invoices/POs. Rules 6/7 now show the amount.
- Register any assets already booked to 1212-1214 if you want depreciation and deferred tax on them.
