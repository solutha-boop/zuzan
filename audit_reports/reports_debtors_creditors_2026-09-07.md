# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 7 September 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-09-06 (PASS; two carried-over High findings — invoice line-item VAT bug, expense-account mismatch — plus one carried-over Critical security item, out of scope).

**Change detection since last run:** `git log --since="2026-09-06 00:08"` shows **10 new commits**, all titled "feat: accountant practice dashboard — billing_exempt partner tier, AccountantDashboard component, client onboarding modal, admin toggle" (same recurring commit-message pattern noted in prior reports), spanning 2026-09-06 09:03 through 21:06. HEAD is now `415306e` (up from `92b4bdac`).

`git diff --name-only 92b4bdac 415306e` shows in-scope files touched: `App_js_fixed.js`, `zuzan-app/src/App.js`, `zuzan-backend/companies.py`, `zuzan-backend/csv_import.py`, `zuzan-backend/database.py`, `zuzan-backend/journal.py`, `zuzan-backend/main.py`. **Not touched** (and therefore re-verified only, not re-derived): `payroll.py`, `purchase_orders.py`, `suppliers.py`, `customers.py`, `financial_statements.py`.

**Headline result: both carried-over High findings from every prior report back to 2026-08-27 have been fixed in this commit batch.** Details in §2.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ✅ PASS — both carried-over High findings fixed this run |
| Debtors (AR) | ✅ PASS — aging/status logic correct; line-item VAT bug (the one caveat noted since 08-27) is now fixed |
| Creditors (AP) | ✅ PASS — reversal-aware, bank details decrypted, unchanged |
| Cross-module consistency | ✅ PASS — full journal coverage; new employee/payroll-adjustment CSV imports don't touch invoice/expense/journal import logic |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) re-verified at code level, no regressions, no standards changes |
| Tax updates (SARS) | ✅ PASS — 2026/2027 tables current, no rate changes; VAT-Act constitutional case still reserved, no ruling |

**Overall: PASS, with a positive change since last run.** The two High-severity findings carried over unfixed since 2026-08-27 (multi-line invoice VAT calculation, expense-account misrouting to 5900) were both fixed in the 2026-09-06 commit batch and independently verified against current file contents in this run. One Critical security item (leaked GitHub token file) remains unresolved and out of this audit's technical scope — see Action Items.

## 2. Reports

**Fixed this run — invoice line-item VAT bug** (`companies.py:332-377`, new `_vat_from_line_items()`; wired into `create_invoice` at `:445-455` and `update_invoice` at `:531-576`): previously, `create_invoice` computed `vat_amount = round(data.amount * VAT_RATE, 2) if data.vat_applicable else 0` off the whole subtotal regardless of per-line `vat_applicable` flags in `items_json`. The new code parses `items_json` (when present and valid) and sums each line's own VAT — trusting a line's explicit `vat_amount` if supplied, else deriving `quantity * unit_price * VAT_RATE` when that line's `vat_applicable` isn't `False`. Falls back safely to the flat calculation if `items_json` is absent, malformed, or not a non-empty list, so a bad payload can't zero out an invoice. `update_invoice` mirrors this and additionally treats a line-only VAT-flag toggle (no subtotal change) as an "amount changed" event, which the old `data.amount` comparison would have missed. Verified the frontend line-item editor (`App_js_fixed.js:906-921`, `syncLines()`) already emits the exact shape the parser expects (`quantity`, `unit_price`, `vat_applicable`, `vat_amount`, `total`) — the fix closes a backend/frontend format mismatch that existed since the multi-line-items feature shipped in August, it did not require a frontend change.

**Fixed this run — expense category/account mismatch** (`journal.py:143-166`, `expense_account()`): previously looked up `CATEGORY_TO_CODE` by bare category name while all six frontend "Account" dropdowns (`App_js_fixed.js:2315,2390,2447,7789,7832,7839`) submit `"{code} - {name}"`, so every expense silently posted to account 5900 "General Expenses" regardless of the account selected. The function now splits on `" - "`, and if the leading token is numeric, looks up the `Account` by that code directly; only falls back to the bare-name `CATEGORY_TO_CODE` lookup (then 5900) if the input isn't in `"{code} - {name}"` form. This also makes custom accounts added via `/coa` (which have no `CATEGORY_TO_CODE` entry) resolve correctly instead of falling back to 5900. Verified all six frontend dropdown sites use the matching `"{code} - {name}"` format, so the fix closes the gap end-to-end.

Confirmed unaffected / still correct (re-verified against current file contents):
- `total_revenue` sums only paid invoices via `_to_zar()` (`payroll.py:1238`); `total_outstanding` covers sent/overdue via `_to_zar()` (`payroll.py:1246`) — file unchanged since 08-29, anchors unmoved.
- Expenses excluded from revenue; PO costs added once via `_po_delivered_net()`, no double count (`payroll.py:1252-1261`, and consistently at `:2214`, `:2290`, `:2472`).
- Payroll costs correctly included in expense totals (`payroll.py:1268`).
- Management-accounts revenue trend and `/v1/summary` (`main.py`) apply `_to_zar()` consistently — `main.py`'s only change this run was one more repeated `#` character appended to the already-noted disabled-middleware comment line (cosmetic, not functional; see Action Item 4).

New in this batch, out of Reports/Debtors/Creditors scope but noted for completeness: `companies.py` and `database.py` gained a `financial_year_end` field (company settings) and a CIPC Annual Return deadline reminder banner in Settings/Registration (`App_js_fixed.js`); `csv_import.py` gained two new bulk-import endpoints (`/import/employees`, `/import/payroll_adjustments`) that create/update `Employee` records only — they do not touch `Invoice`, `Expense`, `PurchaseOrder`, or `JournalEntry` tables and have no bearing on Reports/Debtors/Creditors/journal correctness.

## 3. Debtors

✓ No issues found — the one caveat carried since 08-27 (AR balances only as correct as the backend's VAT computation for line-item invoices) is resolved by the §2 fix.

- `payroll.py:2555-2558` (and the equivalent filter at `:1244`) filters `Invoice.status.in_([sent, overdue])` — paid excluded. Unchanged, re-verified.
- Aged from `due_date` only, never `date`/`issue_date` (`payroll.py:2562-2589`, and the >90-day check at `:1624-1644`) — invoices with no due date go to a separate `not_due` bucket rather than falsely inflating overdue totals. Unchanged, re-verified.
- Amounts converted via `_to_zar()` at the aging-entry level (`payroll.py:2569`, `:1631`, `:1643`).

## 4. Creditors

✓ No issues found. `purchase_orders.py`, `suppliers.py` unchanged since 08-27; `journal.py`'s only change this run was the unrelated `expense_account()` fix in §2.

- Outstanding = received/partial POs plus unpaid on-credit expenses; fully paid POs excluded (`payroll.py:2609-2628`).
- Reversal-aware AP balance nets `credit − debit` and includes `source.in_(["purchase_order","purchase_order_reversal"])` at all expected call sites — confirmed present at `payroll.py:1779`, `payroll.py:2645`, `purchase_orders.py:445`, `journal.py:868` (line number shifted slightly from the prior report's `:848` due to the unrelated `expense_account()` edit above it — same code, confirmed via diff), `financial_statements.py:558`.
- Supplier bank details decrypted via `decrypt_field()` before display (`payroll.py:2688-2690`).

## 5. Cross-module consistency

✓ No new gaps.
- Journal coverage complete and unchanged: `post_invoice_raised`, `post_invoice_paid`, `post_invoice_cogs`, `post_expense`, `post_bank_income`, `post_payroll`, `post_expense_paid`, `post_po_received`, `post_po_paid`, `post_stock_adjustment`, `post_asset_acquisition`, `post_depreciation`, `post_asset_disposal` all present (`journal.py:214-670`) and wired into the backfill routine.
- Migration hygiene confirmed for both new columns this run: `financial_year_end` (`database.py:1533`) and the previously-added `wear_and_tear_rate` (`database.py:1446`) both sit inside the migrations list literal, not after the `for` loop.
- Import-awareness (2026-07-11 fixes) intact: Rules 6/7 still exclude `source == "import"` (`payroll.py:1737,1813`); balance sheet still carries 3998/3999 imported-equity offsets (`payroll.py:1538-1547`). The two new CSV-import endpoints (`/import/employees`, `/import/payroll_adjustments`) added this run operate only on the `Employee` table and never touch `Invoice`, `Expense`, `JournalEntry`, or `Account` — they do not run (and have no need to run) the journal backfill, and don't interact with Rules 6/7 or the 3998/3999 offsets at all.
- Non-ZAR invoice imports still require an exchange rate and unbalanced journal-import groups are still rejected — this logic lives in the unchanged, pre-existing invoice/journal import paths in `csv_import.py`, which the new employee-import code was appended after rather than modified.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (declared at `financial_statements.py:2` module docstring and `:623` AFS meta `"basis": "IFRS for SMEs"`). File unchanged since 08-26; re-verified rather than re-derived.

**Standards status (fresh web search this run, 7 September 2026):** no change since 09-06.
- IFRS 18 *Presentation and Disclosure in Financial Statements* — still effective for annual periods beginning on/after 1 January 2027, early application permitted; still not applicable to IFRS-for-SMEs preparers (ZuZan's basis).
- IFRS for SMEs third edition (issued 27 February 2025) — still effective 1 January 2027; the 2015 edition remains permitted until then. The IASB's Exposure Draft *Consolidation Exception* (published May 2026) has its comment period closing **9 September 2026 — still 2 days away** as at this run's date; not yet closed, no final amendment issued. Still not relevant to ZuZan (no consolidation requirement in scope).

**Section 5b — deferred tax:** already implemented (not hard-coded to `0.0`); re-verified this run at the code level (file unchanged, anchors unmoved):
- `_deferred_tax_balance()` (`financial_statements.py:131`) computes per-asset tax base via `wear_and_tear_rate` (SARS IN47 category mapping, `database.py:498`).
- Opening/closing deferred tax balances (`:266-268`) drive `deferred_tax_expense`.
- `total_tax` combines current + deferred (`:601`); Note 9 fields (`deferred_tax`, `deferred_tax_opening_balance`, `deferred_tax_closing_balance`) populated (`:606-610`).
- Balance-sheet closing balance carries the matching retained-earnings adjustment so Assets = Equity + Liabilities still holds.

Finance costs (2026-07-13 fix): interest-below-EBIT split (`financial_statements.py:204-211`) and tax/net-profit derivation from `profit_before_tax`, not EBIT (`:258-261`), re-confirmed present and unchanged.

**Relevant to this section:** the §2 fixes (invoice VAT, expense-account routing) don't touch `financial_statements.py` directly and don't change AFS aggregate totals (those were already correct in total; only the account-level split and per-invoice VAT split were wrong before). No AFS-side follow-up needed.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date, present at `payroll.py:132`. `_current_tax_year()` (`payroll.py:170-183`) correctly resolves to `"2026/2027"` for 7 September 2026 (month ≥ 3 → year starts 2026). `payroll.py` unchanged this run (not among the 7 touched files).

- Re-confirmed at code level and cross-checked via fresh web search this run: PAYE brackets 18%–45% across seven brackets (18% to R245,100; 26% to R383,100; 31% to R530,200; 36% to R695,800; 39% to R887,000; 41% to R1,878,600; 45% above), primary rebate R17,820, secondary R9,765, tertiary R3,249, UIF ceiling R17,712/month at 1% employee + 1% employer, SDL 1% employer-only — all present at `payroll.py:132-146`. Web search confirms Budget 2026 adjusted PIT brackets/rebates by 3.4% for inflation for 2026/27, and the code's figures match published SARS 2026/2027 tables exactly — no discrepancy found.
- CIT remains flat 27% (unchanged for years of assessment ending 1 April 2026 to 31 March 2027, per Budget 2026 — confirmed via web search: "no change" to the CIT rate). Matches all four in-code usages: `financial_statements.py:84` (`_CIT_RATE = 0.27`), `fixed_assets.py:78` (`SA_CIT_RATE = 0.27`), `payroll.py:1290,2255,2446` (`0.27` / `CORP_TAX_RATE = 0.27`).
- VAT standard rate confirmed unchanged at 15% (`companies.py:289`, `payroll.py:1609,2802`, `quotes.py:15` — all `VAT_RATE = 0.15`). The Constitutional Court case on Section 7(4) of the VAT Act (the Finance Minister's power to change VAT rates by budget-speech announcement) remains at "judgment reserved" as at this run's date — heard 27 August 2026, no ruling issued yet per fresh web search (SARS/Treasury are asking the court to overturn the Western Cape High Court's finding of unconstitutionality; the DA/EFF sought to have the underlying VAT hike halted). No rate change; the 2025 proposed increase to 15.5%/16% remains suspended/withdrawn. Awareness/monitoring only — no code impact.
- No edits made to tax tables (report-only per task rules; §5b was verification-only this run, already implemented in a prior run).

**Sources consulted:** [VAT Act section declared invalid — The Citizen](https://www.citizen.co.za/news/south-africa/courts/vat-act-section-declared-invalid-unconstitutional/) · [ConCourt reserves judgment on Finance Minister's power to change VAT rate — eNCA](https://www.enca.com/news-top-stories/concourt-reserves-judgment-finance-ministers-power-change-vat-rate) · [Sars and Treasury ask top court to overturn ruling — Business Day](https://www.businessday.co.za/news/2026-08-28-sars-and-treasury-ask-top-court-to-overturn-ruling-on-ministers-vat-powers/) · [SARS Tax Tables 2026/2027 — Xero ZA](https://www.xero.com/za/guides/sars-tax-tables-2026/) · [Budget 2026 Frequently Asked Questions — SARS](https://www.sars.gov.za/about/sars-tax-and-customs-system/budget/budget-2026-frequently-asked-questions/) · [Income tax brackets, medical tax credits adjusted for inflation — Moonstone](https://www.moonstone.co.za/income-tax-brackets-medical-tax-credits-adjusted-for-inflation/) · [IFRS - IASB proposes extending consolidation exception for eligible SMEs](https://www.ifrs.org/news-and-events/news/2026/05/iasb-proposes-extending-consolidation-exception-eligible-smes/) · [IFRS - IFRS for SMEs Accounting Standard—Consolidation Exception work plan](https://www.ifrs.org/projects/work-plan/ifrs-for-smes-accounting-standard-consolidation-exception/)

## 8. Action items

1. **Critical (security, out-of-scope but urgent, carried over unresolved):** `C:\Zuzan\ghp_w0vWd0jgV1yFdHb9NODeqLMx5jlKOz3.txt` still contains what appears to be a live GitHub personal access token in plaintext in the project root, untracked. Recommend revoking it in GitHub settings and deleting the file; check git history in case it was ever committed.
2. **Resolved this run (was High):** the multi-line invoice-items VAT calculation now respects per-line `vat_applicable` flags (`companies.py:332-377`, wired into `create_invoice`/`update_invoice`). No further action required; recommend regression-testing a few historical mixed-VAT invoices to confirm the fix doesn't retroactively alter already-posted amounts (it only affects new creates/edits, not existing rows).
3. **Resolved this run (was High):** the expense "Account" dropdown value now correctly resolves to its selected account instead of always posting to 5900 (`journal.py:143-166`). No further action required; recommend spot-checking a handful of expenses entered between the feature's original ship date and this fix to see whether any should be manually reclassified off 5900 onto their intended accounts (historical postings are not auto-corrected by this fix).
4. **Medium (carried over, largely unchanged):** `billing.py`'s `resp = None` duplicate-line pattern and `main.py`'s disabled-middleware comment (now one character longer than 09-06, functionally identical) remain from the repeated commit-generation tooling. Still functionally harmless; worth a cleanup pass whenever that tooling is next touched.
5. **Medium (carried over):** `/reports/cash-flow-13week` (`payroll.py:1991-2098`, unchanged) still does not model outstanding creditor (PO) payments or VAT201 liabilities as distinct weekly outflows.
6. **Low (carried over):** the `/coa` custom-account feature lets users add accounts to `CompanyAccount` and select them in expense dropdowns; with item 3 now fixed, custom accounts should resolve correctly via the numeric-code path in `expense_account()` — recommend a quick functional test adding one custom account and posting an expense against it to confirm end-to-end, since this hadn't been explicitly exercised before the fix landed.
7. **Low (new, informational):** frontend payroll pricing display was corrected this run from a stale "R65/month minimum" (Settings, Registration) to "R99/month minimum" (`App_js_fixed.js`), now consistent with the `Math.max(99, ...)` calculation logic already in place. Backend's `PAYROLL_PER_EMP = 34.00` / `PAYROLL_MIN = 99.00` constants in `payroll.py:191-192` remain unused/legacy (billing pricing is computed independently in the frontend and billing.py) — still just a cleanup item, not a compliance issue.

**Standing reminders (not defects, carried from prior reports):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry (`payroll.py`) after Budget Feb 2027 and restart the backend;
(b) early-2027 runs should execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`);
(c) the AFS PayFast payment/ad-hoc tokenization feature and the `/reports/ai-insights` feature remain outside this audit's scope;
(d) NBCPSS private security payroll mode predates this audit's baseline, not yet part of this checklist's explicit scope;
(e) file-attribution note: the imported-equity-offset (3998/3999) exclusion logic lives in `payroll.py`'s `balance_sheet()`, not `financial_statements.py`;
(f) next run should keep checking for Treasury's review outcome or Parliamentary introduction of the 2026 draft TLAB/TALAB (public comment closed 28 August 2026; under Treasury/SARS review);
(g) `parent_company_id`/`user_type` columns, bookkeeper-onboarding, consolidated-billing, accountant-fee-structure, and the accountant-practice-dashboard/`billing_exempt` features (including this run's `financial_year_end`/CIPC-deadline-reminder additions) remain outside Reports/Debtors/Creditors/AFS/tax scope, awareness only;
(h) the 13-week cash-flow forecast feature remains additive and outside the original checklist's endpoint list — tracked via action item 5;
(i) compulsory VAT-registration turnover threshold is R2,300,000 (voluntary R120,000), effective 1 April 2026 — not gated anywhere in-scope, awareness only;
(j) the persistent Chart of Accounts feature (`/coa` router, `CompanyAccount`, `ChartOfAccounts`/`Expenses` components) is additive and outside the original checklist's endpoint list — tracked via action items 3 and 6;
(k) the invoice header-image upload, custom HTML invoice template, and service-item catalogue introduced 2026-08-29 remain additive presentation/picklist features outside the original checklist's endpoint list;
(l) the IASB's SME consolidation-exception Exposure Draft comment period closes 9 September 2026 (2 days from this run) — monitor for final issuance after the window closes;
(m) the Constitutional Court has reserved judgment (heard 27 August 2026) on whether Section 7(4) of the VAT Act, 1991 is unconstitutional. No rate change and no ruling yet; monitor for the judgment and any resulting change to how a future VAT rate change would need to be legislated/timed;
(n) **new this run:** the two carried-over High findings tracked since 2026-08-27 (action items 2 and 3 in prior reports) were fixed in the 2026-09-06 commit batch — this is the first PASS-with-fixes run since that baseline; the two new employee/payroll-adjustment CSV import endpoints (`/import/employees`, `/import/payroll_adjustments`) are additive and outside the original checklist's endpoint list, noted for awareness only (they don't touch Reports/Debtors/Creditors/journal logic).
