# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 5 September 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-09-04 (PASS, no new findings; two carried-over High findings, one carried-over Critical security item).

**Change detection since last run:** `git log --since="2026-09-04 06:39"` returns **eight new commits** (21:33–22:37 on 4 September 2026), all tagged "accountant practice dashboard — billing_exempt partner tier." HEAD is now `92b4bdac`. These commits touch `zuzan-backend/auth.py`, `zuzan-backend/billing.py`, `zuzan-backend/main.py`, `App_js_fixed.js` and `zuzan-app/src/App.js` only — none of the in-scope backend files (`payroll.py`, `companies.py`, `journal.py`, `financial_statements.py`, `database.py`, `purchase_orders.py`, `suppliers.py`, `customers.py`, `csv_import.py`) were touched.

Diff review of the eight commits:
- `auth.py` — `login`/`get_me`/`switch_company` responses now also return `billing_exempt`, `industry`, `invoice_header_url`, `invoice_template_html`, `trial_ends`. Additive fields only, outside Reports/Debtors/Creditors/AFS/tax scope (accountant practice dashboard feature, item (g)).
- `App_js_fixed.js` / `zuzan-app/src/App.js` — adds a "Practice Dashboard" nav button and routes `billing_exempt`/accountant-role users straight to `accountant-dashboard` on login/refresh. No changes to invoice, VAT, AR/AP, or AFS rendering code.
- `main.py` — the disabled-`_SubscriptionGateMiddleware` comment line was duplicated yet again by each of the eight commits (see escalated finding below); no functional change (middleware still commented out, as it has been since PayFast went inactive).
- `billing.py` — the `resp = None` duplicate-line pattern also grew every commit this run (see escalated finding below); still dead code, immediately overwritten by the `try` block two lines later.

Every anchor from the 09-04 report was independently re-verified directly against current file contents this run (not inferred from the diff, since these files weren't touched by the day's commits):
- `companies.py:395-399` — `vat_amount = round(data.amount * VAT_RATE, 2) if data.vat_applicable else 0` — unchanged, still ignores `items_json`.
- `journal.py:88-105` (`CATEGORY_TO_CODE`) / `:141-147` (`expense_account()`) — unchanged, still keyed on bare category name.
- `payroll.py:1230-1268` — `_to_zar()` for `total_revenue`/`total_outstanding`, PO COGS via `_po_delivered_net()`, depreciation and payroll cost inclusion — all unchanged, same logic and line range as prior run.
- `payroll.py:1624-1644` (Debtors ageing >90 days, `due_date`-based, `_to_zar()`-converted) — unchanged.
- `payroll.py:1771-1786`, `2638-2645`, `purchase_orders.py:445`, `journal.py:848`, `financial_statements.py:558` — all still include `source.in_(["purchase_order","purchase_order_reversal"])`.
- `payroll.py:2688-2690` — `decrypt_field()` still wraps supplier bank details before display.
- `payroll.py:1737,1813` — Rules 6/7 still exclude `source == "import"` on control accounts.
- `payroll.py:1538,1539,1545,1547` — balance sheet still carries 3998/3999 imported-equity offsets.
- `database.py:1445` (`wear_and_tear_rate`) and `:1531` (`billing_exempt`) — both migrations still sit inside the migrations list literal, not after the `for` loop.
- `financial_statements.py:130-141` (`_deferred_tax_balance()`), `:266-268` (opening/closing/expense), `:601,606-610` (Note 9 fields) — all present; no `"deferred_tax": 0.0` hard-coding.
- `payroll.py:132-146` — `TAX_YEARS["2026/2027"]` brackets, primary rebate R17,820, secondary R9,765, tertiary R3,249, UIF ceiling R17,712 unchanged.
- `payroll.py:1609,2802`, `companies.py:284` — `VAT_RATE = 0.15` unchanged in all three locations.
- `C:\Zuzan\ghp_w0vWd0jgV1yFdHb9NODeqLMx5jlKOz3.txt` — still present in the repo root, untracked, unchanged (last modified 24 Aug 2026).

Fresh web searches this run found no changes to IFRS or SARS positions since 09-04: IFRS for SMEs third edition (issued 27 Feb 2025) remains effective 1 January 2027; the IASB's Exposure Draft on the SME consolidation exception remains open for comment until 9 September 2026 (still open as at this run — not yet closed, contrary to what a prior report's note (m) implied; corrected below), not relevant to ZuZan since it has no consolidation requirement. No SARS 2026 TLAB/TALAB finalisation news found. SARS 2026/2027 PAYE brackets, primary rebate (R17,820), UIF ceiling (R17,712 at 1%/1%), SDL (1%, exempt below R500,000 payroll), CIT (27%), and VAT (15%) all independently re-confirmed via fresh web search and match the code exactly.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ⚠️ PASS with two carried-over findings (unfixed) — expense-account mismatch + invoice line-item VAT bug |
| Debtors (AR) | ⚠️ PASS with carried-over finding — aging/status logic itself correct, but line-items feature can still misstate invoiced VAT/total feeding into AR balances |
| Creditors (AP) | ✅ PASS — reversal-aware, bank details decrypted, unchanged |
| Cross-module consistency | ✅ PASS — full journal coverage, unchanged |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) re-verified at code level, no regressions, no standards changes |
| Tax rates (SARS) | ✅ PASS — 2026/2027 tables current, no rate changes |

**Overall: PASS. This run's eight commits implement an accountant-practice-dashboard feature entirely outside the audited files/endpoints (auth response fields + frontend routing only). No new findings in scope. Two carried-over High-severity findings (invoice line-item VAT bug, expense-account mismatch) remain unfixed, plus one carried-over Critical security item (unfixed, out of scope). One Low-severity item (cosmetic duplicate-line artifacts) is escalated to Medium this run due to a sharp increase in growth rate — see §8.**

## 2. Reports

No functional changes since 09-04. Both previously-identified bugs re-verified directly against current file contents:

**Carried over (High) — multi-line invoice items don't respect per-line VAT flags** (`App_js_fixed.js:899-1090`, `companies.py:395-399`): `create_invoice` still computes `vat_amount = round(data.amount * VAT_RATE, 2) if data.vat_applicable else 0` purely from the top-level `amount`/`vat_applicable` fields — never reads `items_json`. Any invoice built with mixed VAT-exempt/standard-rated line items still has its backend-recorded `vat_amount`/`total_amount` computed flat off the whole subtotal. Flows into `total_revenue`/`total_outstanding` (Reports) and AR aging balances (Debtors).

**Carried over (High) — expense category/account mismatch still reroutes to 5900 "General Expenses"** (`journal.py:141-147`, `App_js_fixed.js:2315,2390,2447,7789,7832,7839`): `expense_account()` still looks up `CATEGORY_TO_CODE` by bare category name while the frontend's account dropdowns still submit `"{code} - {name}"` — a guaranteed miss, so every expense still falls through to account 5900. Aggregate revenue/expense/net-profit totals remain correct; expense-by-account reporting, COGS/opex/finance-cost classification, and AFS presentation-by-account remain wrong.

Confirmed unaffected (re-verified against current file contents):
- `total_revenue` sums only paid invoices via `_to_zar()` (`payroll.py:1238`), plus bank-import income (`:1240`).
- `total_outstanding` covers sent/overdue via `_to_zar()` (`payroll.py:1246`).
- Expenses excluded from revenue; PO costs added once via `_po_delivered_net()`, no double count (`payroll.py:1252-1261`).
- Depreciation and payroll costs correctly included (`payroll.py:1268`).
- Management-accounts revenue trend and `/v1/summary` apply `_to_zar()` consistently.

## 3. Debtors

No relevant code changes. Re-verified unchanged:
- `payroll.py:2555-2558` (equivalent filter also at `:1244`) filters `Invoice.status.in_([sent, overdue])` — paid excluded.
- Aged from `due_date` only (`payroll.py:1628-1644, 2560-2569`).
- Amounts converted via `_to_zar()` at the aging entry level.

**Relevant to this section (see §2):** the AR balance for any invoice built with the line-items feature is still only as correct as the backend-computed `total_amount`, per the unfixed §2 finding. Not a defect in the Debtors query itself.

## 4. Creditors

✓ No issues found. Unchanged.
- Outstanding = received/partial POs plus unpaid on-credit expenses; fully paid POs excluded.
- Reversal-aware AP balance nets `credit − debit` and includes `source.in_(["purchase_order","purchase_order_reversal"])` at all expected call sites — confirmed present at `payroll.py:1779,2645`, `purchase_orders.py:445`, `journal.py:848`, `financial_statements.py:558`.
- Supplier bank details decrypted via `decrypt_field()` before display (`payroll.py:2688-2690`).

## 5. Cross-module consistency

✓ No new gaps.
- Journal coverage complete and unchanged: `post_invoice_raised`, `post_invoice_paid`, `post_invoice_cogs`, `post_expense`, `post_bank_income`, `post_payroll`, `post_expense_paid`, `post_po_received`, `post_po_paid`, `post_stock_adjustment`, `post_asset_acquisition`, `post_depreciation`, `post_asset_disposal` all present and wired into the backfill routine (`journal.py:194-702`).
- Migration hygiene re-confirmed for `wear_and_tear_rate` (`database.py:1445`) and `billing_exempt` (`database.py:1531`) — both inside the migrations list literal.
- Import-awareness (2026-07-11 fixes) intact: Rules 6/7 exclude `source=="import"` (`payroll.py:1737,1813`); balance sheet retains 3998/3999 imported-equity offsets (`payroll.py:1538-1547`).

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (declared in AFS meta, `financial_statements.py:623`). File unchanged since 08-26.

**Standards status (fresh web search this run, 5 September 2026):** no change since 09-04.
- IFRS 18 *Presentation and Disclosure in Financial Statements* — still effective for annual periods beginning on/after 1 January 2027, early application permitted; not applicable to IFRS-for-SMEs preparers (ZuZan's basis).
- IFRS for SMEs third edition (issued 27 February 2025) — still effective 1 January 2027; the 2015 edition may continue to be applied until then. The IASB's Exposure Draft *Consolidation Exception* remains open for comment until 9 September 2026 (i.e. still open as at this run's date) — a proposal only, not yet issued, and not relevant to ZuZan (no consolidation requirement in scope).

**Section 5b — deferred tax:** already implemented; re-verified this run at the code level (unchanged file, no `"deferred_tax": 0.0` hard-coding found). `_deferred_tax_balance()` (`financial_statements.py:130`) computes per-asset tax base via `wear_and_tear_rate`/SARS IN47 category mapping; opening/closing deferred tax balances (`:266-268`) drive `deferred_tax_expense`; `total_tax` combines current + deferred (`:601`); Note 9 (`deferred_tax`, `deferred_tax_opening_balance`, `deferred_tax_closing_balance`) populated (`:606-610`); balance-sheet closing balance carries matching retained-earnings adjustment so the statement still balances.

Finance costs (2026-07-13 fix): interest-below-EBIT split (`financial_statements.py:205-209`) and tax/net-profit derivation from `profit_before_tax` (not EBIT) (`:258-261`) re-confirmed present and unchanged.

**Relevant to this section:** unchanged from prior runs — neither the §2 expense-account bug nor the invoice-VAT bug touches `financial_statements.py` directly; aggregate totals remain correct in total even when misclassified by account.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date, present at `payroll.py:132`. `payroll.py` unchanged since 08-29 (not touched by this run's commits).

- Re-confirmed at code level (unchanged file) and independently cross-checked via fresh web search this run: PAYE brackets 18%–45% across seven brackets (18% to R245,100; 26% to R383,100; 31% to R530,200; 36% to R695,800; 39% to R887,000; 41% to R1,878,600; 45% above), primary rebate R17,820, secondary R9,765, tertiary R3,249, UIF ceiling R17,712/month at 1% employee + 1% employer, SDL 1% employer-only (exempt below R500,000 annual payroll) — all present at `payroll.py:132-146`, matches external SARS-tables sources exactly, no changes.
- CIT remains flat 27% (confirmed via fresh web search — unchanged for years of assessment ending 1 April 2026 to 31 March 2027) — matches code used in dashboard/management/provisional-tax and `financial_statements.py`'s deferred-tax calc.
- VAT standard rate confirmed unchanged at 15% (`VAT_RATE = 0.15` in `companies.py:284`, `payroll.py:1609,2802`) via fresh web search — the proposed 2025 increase to 16% remains withdrawn/reversed; no new rate-change proposals found.
- 2026 draft TLAB/TALAB: no finalisation or Parliamentary-introduction news found this run.
- No edits made to tax tables (report-only per task rules; §5b was verification-only this run, already implemented).

**Sources consulted:** [Draft Taxation Laws Amendment Bill, 2026 — SARS](https://www.sars.gov.za/wp-content/uploads/Legal/Drafts/Legal-LPrep-Draft-2026-31-Draft-Taxation-Laws-Amendment-Bill-2026-30-July-2026.pdf) · [Taxation Laws Amendment Bill B30-2025 — SARS](https://www.sars.gov.za/wp-content/uploads/Legal/Bills/Legal-LPrep-Bills-2025-04-Taxation-Laws-Amendment-Bill-B30%E2%80%942025-12-November-2025.pdf) · [IFRS - June 2026 IFRS for SMEs Accounting Standard Update](https://www.ifrs.org/supporting-implementation/2015-ifrs-for-smes-supporting-materials/sme-updates/2026/june-2026-ifrs-for-smes-accounting-standard-update/) · [IFRS - International Accounting Standards Board to issue third edition of the IFRS for SMEs Accounting Standard](https://www.ifrs.org/news-and-events/news/2025/02/iasb-to-issue-third-edition-ifrs-for-smes-accounting-standard/) · [Third edition of the IFRS for SMEs Accounting Standard — ACCA](https://www.accaglobal.com/learning-and-events/corporate-reporting/third-edition-ifrs-for-smes.html) · [IASB issues third edition of the IFRS for SMEs — PwC Viewpoint](https://viewpoint.pwc.com/dt/gx/en/pwc/in_briefs/in_briefs_INT/in_briefs_INT/iasb-issues.html) · [SARS Tax Tables 2026/2027 — Accounter](https://accounter.co.za/news/sars-tax-tables-2026-2027) · [How to calculate PAYE in South Africa (2026/2027 tax tables) — Govchain](https://www.govchain.co.za/blog/how-to-calculate-paye-in-south-africa) · [SARS Tax Tables 2026/2027 — Xero ZA](https://www.xero.com/za/guides/sars-tax-tables-2026/) · [South Africa - Corporate - Taxes on corporate income — PwC Tax Summaries](https://taxsummaries.pwc.com/south-africa/corporate/taxes-on-corporate-income) · [Corporate Tax remains unchanged — BDO](https://www.bdo.co.za/en-za/insights/2026/budget-speech/corporate-tax-remains-unchanged,-with-a-pinch-of-positivity) · [South Africa 2026 Budget ducks VAT rise — vatcalc.com](https://www.vatcalc.com/south-africa/south-africa-vat-rise/) · [South Africa VAT Rate 2026: 15% (SARS) — VatInfo.org](https://vatinfo.org/countries/za)

## 8. Action items

1. **Critical (security, out-of-scope but urgent, carried over unresolved):** `C:\Zuzan\ghp_w0vWd0jgV1yFdHb9NODeqLMx5jlKOz3.txt` still contains what appears to be a live GitHub personal access token in plaintext in the project root, untracked. Recommend revoking it in GitHub settings and deleting the file; check git history in case it was ever committed.
2. **High (carried over, unfixed):** the multi-line invoice-items feature (`App_js_fixed.js:899-1090`, `companies.py:395-399`) still does not make the backend's VAT calculation respect per-line `vat_applicable` flags. Recommend either removing the per-line VAT checkbox until the backend honours it, or having `create_invoice`/`update_invoice` derive `vat_amount`/`total_amount` from `items_json` when present.
3. **High (carried over, unfixed):** expense "Account" dropdown value (`"{code} - {name}"`) doesn't match `CATEGORY_TO_CODE`'s bare-name keys in `journal.py:88-147`, so manually-entered and bank-import-categorised expenses both post to account 5900 regardless of the account selected. Recommend `expense_account()` parse the leading code from `category` and look up `Account` by code directly.
4. **Medium (escalated this run):** cosmetic duplicate-line artifacts are growing sharply — `billing.py`'s `resp = None` (`:465-520`) went from 4 duplicates (09-04) to **56 duplicates** after eight commits on 4 September, and `main.py`'s disabled-middleware comment (`:321`) is now **5,552 characters** long on a single line, having been re-duplicated in every one of the eight commits. Both remain functionally harmless (the `resp = None` lines are overwritten immediately by the `try` block; the comment is inert), but the rate of growth (roughly +7 duplicate lines per commit) suggests whatever tooling is generating these commits is repeatedly re-appending instead of leaving the line alone or replacing it — worth investigating the commit-generation process itself before these files become unwieldy or a future edit collides with the growing block.
5. **Medium (carried over):** `/reports/cash-flow-13week` (`payroll.py:1991-2098`) still does not model outstanding creditor (PO) payments or VAT201 liabilities as distinct weekly outflows.
6. **Low (carried over):** the `/coa` custom-account feature lets users add accounts to `CompanyAccount` and select them in expense dropdowns, but `journal.py` never posts to a custom account by code. Remains decorative until item 3 is fixed.

**Standing reminders (not defects, carried from prior reports):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry (`payroll.py`) after Budget Feb 2027 and restart the backend;
(b) early-2027 runs should execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`);
(c) the AFS PayFast payment/ad-hoc tokenization feature and the `/reports/ai-insights` feature remain outside this audit's scope;
(d) NBCPSS private security payroll mode predates this audit's baseline, not yet part of this checklist's explicit scope;
(e) file-attribution note: the imported-equity-offset (3998/3999) exclusion logic lives in `payroll.py`'s `balance_sheet()`, not `financial_statements.py`;
(f) next run should keep checking for Treasury's review outcome or Parliamentary introduction of the 2026 draft TLAB/TALAB;
(g) `parent_company_id`/`user_type` columns, bookkeeper-onboarding, consolidated-billing, accountant-fee-structure, and the accountant-practice-dashboard/`billing_exempt` features (now including the auth-response field additions and dashboard routing added 4 September 2026) remain outside Reports/Debtors/Creditors/AFS/tax scope, awareness only;
(h) legacy unused constants `PAYROLL_PER_EMP = 34.00` / `PAYROLL_MIN = 99.00` in `payroll.py` — still worth a cleanup pass, not a compliance issue;
(i) the 13-week cash-flow forecast feature remains additive and outside the original checklist's endpoint list — tracked via action item 5;
(j) compulsory VAT-registration turnover threshold rose to R2,300,000 (from R1,000,000), voluntary to R120,000 (from R50,000), effective 1 April 2026 — not gated anywhere in-scope, awareness only;
(k) the persistent Chart of Accounts feature (`/coa` router, `CompanyAccount`, `ChartOfAccounts`/`Expenses` components) is additive and outside the original checklist's endpoint list — tracked via action items 3 and 6 until resolved;
(l) the invoice header-image upload, custom HTML invoice template, and service-item catalogue introduced 2026-08-29 remain additive presentation/picklist features outside the original checklist's endpoint list, tracked via action item 2 for the one defect found in them;
(m) **correction to prior report:** the IASB's SME consolidation-exception Exposure Draft comment period closes 9 September 2026, not "ended" as a prior report's wording implied — as at this run's date (5 September) it remains open. Not relevant to ZuZan (no consolidation in scope); monitor for final issuance after the window closes.
