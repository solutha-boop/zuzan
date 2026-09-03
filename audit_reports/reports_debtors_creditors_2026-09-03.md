# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 3 September 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-09-02 (PASS, no new findings; two carried-over High findings, one carried-over Critical security item).

**Change detection since last run:** `git log --since="2026-09-02 00:07"` returns **two new commits** (`f930c86`, `1450857`, both 2 September 2026 evening) — HEAD is now `1450857`. Both commits implement a new **accountant practice dashboard** feature: `billing_exempt` partner-tier flag on `Company`, a new `accountant.py` router, an `AccountantDashboard` React component + client-onboarding modal, and an admin toggle for partner status. Files touched: `App_js_fixed.js` / `zuzan-app/src/App.js` (+220 lines each), `zuzan-backend/accountant.py` (new, +213), `zuzan-backend/companies.py` (+20/-18), `zuzan-backend/database.py` (+2), `zuzan-backend/main.py` (+41/-18), `zuzan-backend/billing.py` (+2), `zuzan-backend/email_service.py` (+52/-19), plus `commit_and_push.bat`.

Reviewed the full diff for every file in this checklist's scope:
- `companies.py`: the only change is gating the monthly invoice-count limit behind `if not company.billing_exempt:` in `create_invoice` (companies.py:385-392). The VAT/total calculation itself (companies.py:395-399) is untouched.
- `database.py`: adds `billing_exempt` column + its migration string, correctly placed inside the migrations list literal, not after the `for` loop (database.py:1531, list-literal position confirmed).
- `main.py`: registers the new `/accountant` router and an admin billing-exempt toggle endpoint; also re-duplicates the existing disabled-middleware comment line (cosmetic, already tracked as a standing Low item).
- `payroll.py`, `journal.py`, `purchase_orders.py`, `financial_statements.py`, `suppliers.py`, `customers.py`, `csv_import.py` — **zero changes**, confirmed absent from the commit diffs.
- `App_js_fixed.js` changes are confined to login/settings/App-shell wiring for `billingExempt` and the new `AccountantDashboard`/onboarding-modal component (lines ~8163, 8768-9401, 9753, 14177-14449) — no overlap with the invoice line-items UI (899-1090) or account-dropdown code (2315/2390/2447/7789/7832/7839) implicated in the two carried-over High findings.

None of this touches Reports, Debtors, Creditors, journal posting, AFS, or tax-rate logic. Every anchor re-verified directly against current file contents this run (not inferred from diff alone): `vat_amount = round(data.amount * VAT_RATE, ...)` still at companies.py:398 (flat calc, `items_json` still unread for VAT purposes); `CATEGORY_TO_CODE`/`expense_account()` still at journal.py:88/143-149 unchanged; `deferred_tax`/`_deferred_tax_balance` still present at financial_statements.py (no `0.0` hard-code); `wear_and_tear_rate` column + migration still correctly placed in database.py; `TAX_YEARS` still has both `"2026/2027"` and `"2027/2028"` entries in payroll.py.

**Out-of-scope but flagged (Critical, security, carried over, still unresolved):** `C:\Zuzan\ghp_w0vWd0jgV1yFdHb9NODeqLMx5jlKOz3.txt` (a plaintext GitHub personal access token) is still present in the repo root, untracked, unchanged. Re-confirmed present and readable this run. Still unresolved — see Action Items.

Fresh web searches this run for IFRS standards and SARS tax law found no changes: IFRS 18 remains effective for annual periods beginning on/after 1 January 2027 (full-IFRS preparers only, not applicable to ZuZan's IFRS-for-SMEs basis). The IFRS for SMEs third edition (issued Feb 2025) remains effective 1 January 2027, with the IASB continuing to roll out implementation modules through Q3 2026 — no acceleration or change to the effective date. The 2026 draft TLAB/TALAB: public comment closed 28 August 2026 as scheduled; no evidence found of finalised bill text or Parliamentary introduction as of this run. Current PAYE brackets, primary rebate, UIF ceiling, and SDL rate independently confirmed via web search match the code exactly (see §7).

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ⚠️ PASS with two carried-over findings (unfixed) — expense-account mismatch + invoice line-item VAT bug |
| Debtors (AR) | ⚠️ PASS with carried-over finding — aging/status logic itself correct, but line-items feature can still misstate invoiced VAT/total feeding into AR balances |
| Creditors (AP) | ✅ PASS — reversal-aware, bank details decrypted, unchanged |
| Cross-module consistency | ✅ PASS — full journal coverage, unchanged |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) re-verified at code level, no regressions, no standards changes |
| Tax rates (SARS) | ✅ PASS — 2026/2027 tables current, no rate changes; TLAB/TALAB still in post-comment-period limbo |

**Overall: PASS. No new findings introduced by this run's two commits (both are an unrelated accountant-dashboard/billing-exempt feature). Two carried-over High-severity findings (invoice line-item VAT bug, expense-account mismatch) remain unfixed, plus one carried-over Critical security item (unfixed, out of scope).**

## 2. Reports

New commits this run add one behavioral change in scope: `create_invoice`'s monthly invoice-count limit is now skipped entirely when `company.billing_exempt` is true (companies.py:385-392, new `billing_exempt` column on `Company`). This only affects plan-limit enforcement, not revenue/expense/VAT calculation — no impact on Reports totals.

Both previously-identified bugs re-verified directly against current file contents (files unchanged since 09-02):

**Carried over (High) — multi-line invoice items don't respect per-line VAT flags** (`App_js_fixed.js:899-1090`, `companies.py:395-399`): `create_invoice` still computes `vat_amount = round(data.amount * VAT_RATE, 2) if data.vat_applicable else 0` purely from the top-level `amount`/`vat_applicable` fields — still never reads `items_json` for VAT/total calculation. Any invoice built with mixed VAT-exempt/standard-rated line items will still have its backend-recorded `vat_amount`/`total_amount` computed flat off the whole subtotal. Flows into `total_revenue`/`total_outstanding` (Reports) and AR aging balances (Debtors), unchanged.

**Carried over (High) — expense category/account mismatch still reroutes to 5900 "General Expenses"** (`journal.py:143-149`, `App_js_fixed.js:2315,2390,2447,7789,7832,7839`): `expense_account()` still looks up `CATEGORY_TO_CODE` by bare category name while the frontend's account dropdowns still submit `"{code} - {name}"` — a guaranteed miss, so every expense still falls through to account 5900. Aggregate revenue/expense/net-profit totals remain correct; expense-by-account reporting, COGS/opex/finance-cost classification, and AFS presentation-by-account remain wrong.

Confirmed unaffected (re-verified against current file contents, files unchanged):
- `total_revenue` sums only paid invoices via `_to_zar()` (`payroll.py:1238`), plus bank-import income (`:1240`).
- `total_outstanding` covers sent/overdue via `_to_zar()` (`payroll.py:1246`).
- Expenses excluded from revenue; PO costs added once via `_po_delivered_net()`, no double count (`payroll.py:1252-1259`).
- Depreciation and payroll costs correctly included (`payroll.py:1268`).
- Management-accounts revenue trend and `/v1/summary` apply `_to_zar()` consistently.

## 3. Debtors

No relevant code changes. Re-verified unchanged:
- `payroll.py:2555-2558` filters `Invoice.status.in_([sent, overdue])` — paid excluded.
- Aged from `due_date` only (`payroll.py:2560-2568`).
- Amounts converted via `_to_zar()` at the aging entry level.

**Relevant to this section (see §2):** the AR balance for any invoice built with the line-items feature is still only as correct as the backend-computed `total_amount`, per the unfixed §2 finding. Not a defect in the Debtors query itself.

## 4. Creditors

✓ No issues found. Unchanged.
- Outstanding = received/partial POs plus unpaid on-credit expenses; fully paid POs excluded (`payroll.py:2627`).
- Reversal-aware AP balance nets `credit − debit` and includes `source.in_(["purchase_order","purchase_order_reversal"])` at all expected call sites — confirmed present at `payroll.py:1779,2645`, `purchase_orders.py:445`, `journal.py:848`.
- Supplier bank details decrypted via `decrypt_field()` before display (`payroll.py:2688-2690`).

## 5. Cross-module consistency

✓ No new gaps.
- Journal coverage complete and unchanged: `post_invoice_raised`, `post_invoice_paid`, `post_invoice_cogs`, `post_expense`, `post_bank_income`, `post_payroll`, `post_expense_paid`, `post_po_received`, `post_po_paid`, `post_stock_adjustment`, `post_asset_acquisition`, `post_depreciation`, `post_asset_disposal` all present in `journal.py`.
- Migration hygiene re-confirmed for both the existing `wear_and_tear_rate` migration (`database.py:1445`) and the new `billing_exempt` migration added this run (`database.py:1531`) — both sit inside the migrations list literal, not after the `for` loop.
- Import-awareness (2026-07-11 fixes) intact and unchanged: `source == "import"` exclusions on 1100/2000, balance sheet retains 3998/3999 imported-equity offsets.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (declared in AFS meta, `financial_statements.py:623`). File unchanged since 08-26.

**Standards status (fresh web search this run, 3 September 2026):** no change.
- IFRS 18 *Presentation and Disclosure in Financial Statements* — confirmed still effective for annual periods beginning on/after 1 January 2027, early application permitted; not applicable to IFRS-for-SMEs preparers (ZuZan's basis).
- IFRS for SMEs third edition (issued 27 February 2025) — confirmed still effective 1 January 2027; IASB continuing to publish implementation modules through Q3 2026 (no effective-date acceleration); the 2015 edition may continue to be applied until then.

**Section 5b — deferred tax:** already implemented; re-verified this run at the code level (unchanged file, no `"deferred_tax": 0.0` hard-coding found). `_deferred_tax_balance()` (`financial_statements.py:131`) computes per-asset tax base via `wear_and_tear_rate`/SARS IN47 category mapping; opening/closing deferred tax balances (`:266-268`) drive `deferred_tax_expense`; `total_tax` combines current + deferred (`:601`); Note 9 (`deferred_tax`, `deferred_tax_opening_balance`, `deferred_tax_closing_balance`) populated (`:606-610`); balance-sheet closing balance carries matching retained-earnings adjustment so the statement still balances.

Finance costs (2026-07-13 fix): interest-below-EBIT split and tax/net-profit derivation from `profit_before_tax` (not EBIT) re-confirmed present and unchanged.

**Relevant to this section:** unchanged from prior runs — neither the §2 expense-account bug nor the invoice-VAT bug touches `financial_statements.py` directly; aggregate totals remain correct in total even when misclassified by account.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date, present at `payroll.py:132`. `payroll.py` unchanged since 08-29.

- Re-confirmed at code level (unchanged file) and independently cross-checked via fresh web search this run: PAYE brackets 18%–45% across seven brackets (18% to R245,100; 26% to R383,100; 31% to R530,200; 36% to R695,800; 39% to R887,000; 41% to R1,878,600; 45% above), primary rebate R17,820, UIF ceiling R17,712/month at 1% employee + 1% employer, SDL 1% employer-only (exempt below R500,000 annual payroll, matching the code's threshold logic) — all present at `payroll.py:132-146`, matches external SARS-tables sources exactly, no changes.
- CIT remains flat 27% (unchanged) — matches code used in dashboard/management/provisional-tax and `financial_statements.py`'s deferred-tax calc.
- VAT standard rate confirmed unchanged at 15% (`VAT_RATE = 0.15` in `companies.py:282`, `payroll.py:1609,2802`, `quotes.py:15`); no rate-change proposals found.
- 2026 draft TLAB/TALAB: public comment period closed 28 August 2026 as scheduled. No evidence this run of finalised bill text or Parliamentary introduction — still in post-comment review. None of the proposals found (living-annuity de minimis aggregation across multiple annuities, inter-spousal donations-tax exemption restricted to SA-resident recipient spouses, SEZ arm's-length pricing replacing the anti-profit-shifting rule) affect PAYE brackets, UIF, SDL, CIT, or VAT rates used in this codebase.
- No edits made to tax tables (report-only per task rules; §5b was verification-only this run, already implemented).

**Sources consulted:** [Draft Taxation Laws Amendment Bill, 2026 — SARS](https://www.sars.gov.za/wp-content/uploads/Legal/Drafts/Legal-LPrep-Draft-2026-31-Draft-Taxation-Laws-Amendment-Bill-2026-30-July-2026.pdf) · [Draft Tax Administration Laws Amendment Bill, 2026 — National Treasury](https://www.treasury.gov.za/comm_media/press/2026/Draft%20Tax%20Administration%20Laws%20Amendment%20Bill%2029%20July%202026%20pdf.pdf) · [Big tax changes proposed — The Mercury](https://themercury.co.za/business/2026-08-06-big-tax-changes-proposed-what-the-new-draft-bills-mean-for-taxpayers/) · [2026 Draft Tax Bills have been published for comment — GoLegal](https://www.golegal.co.za/2026-draft-tax-bills/) · [Treasury publishes 2026 draft tax bills for public comment — Nexia SAB&T](https://www.nexia-sabt.co.za/treasury-publishes-2026-draft-tax-bills-for-public-comment/) · [South Africa: Proposed tax amendments — Bowmans](https://bowmanslaw.com/insights/south-africa-proposed-tax-amendments-implications-for-preference-share-funding-structures/) · [IFRS - June 2026 IFRS for SMEs Accounting Standard Update](https://www.ifrs.org/supporting-implementation/2015-ifrs-for-smes-supporting-materials/sme-updates/2026/june-2026-ifrs-for-smes-accounting-standard-update/) · [Third edition of the IFRS for SMEs Accounting Standard — ACCA](https://www.accaglobal.com/learning-and-events/corporate-reporting/third-edition-ifrs-for-smes.html) · [IASB issues third edition of the IFRS for SMEs — PwC Viewpoint](https://viewpoint.pwc.com/dt/gx/en/pwc/in_briefs/in_briefs_INT/in_briefs_INT/iasb-issues.html) · [SARS Tax Tables 2026/2027 — Accounter](https://accounter.co.za/news/sars-tax-tables-2026-2027) · [How to calculate PAYE in South Africa (2026/2027 tax tables) — Govchain](https://www.govchain.co.za/blog/how-to-calculate-paye-in-south-africa)

## 8. Action items

1. **Critical (security, out-of-scope but urgent, carried over unresolved):** `C:\Zuzan\ghp_w0vWd0jgV1yFdHb9NODeqLMx5jlKOz3.txt` still contains what appears to be a live GitHub personal access token in plaintext in the project root, untracked. Recommend revoking it in GitHub settings and deleting the file; check git history in case it was ever committed.
2. **High (carried over, unfixed):** the multi-line invoice-items feature (`App_js_fixed.js:899-1090`, `companies.py:395-399`) still does not make the backend's VAT calculation respect per-line `vat_applicable` flags. Recommend either removing the per-line VAT checkbox until the backend honours it, or having `create_invoice`/`update_invoice` derive `vat_amount`/`total_amount` from `items_json` when present.
3. **High (carried over, unfixed):** expense "Account" dropdown value (`"{code} - {name}"`) doesn't match `CATEGORY_TO_CODE`'s bare-name keys in `journal.py:88-149`, so manually-entered and bank-import-categorised expenses both post to account 5900 regardless of the account selected. Recommend `expense_account()` parse the leading code from `category` and look up `Account` by code directly.
4. **Medium (carried over):** `/reports/cash-flow-13week` (`payroll.py:1991-2098`) still does not model outstanding creditor (PO) payments or VAT201 liabilities as distinct weekly outflows.
5. **Low (carried over):** the `/coa` custom-account feature lets users add accounts to `CompanyAccount` and select them in expense dropdowns, but `journal.py` never posts to a custom account by code. Remains decorative until item 3 is fixed.
6. **Low (observation, carried over):** cosmetic comment-duplication artifacts in `main.py` (disabled-middleware comment now duplicated across two lines by this run's commits) and `billing.py` — worth a cleanup pass whenever convenient.
7. **New — informational only, not a defect:** the accountant-practice-dashboard feature (`billing_exempt` on `Company`, `accountant.py` router, `AccountantDashboard` component) shipped this run is outside the Reports/Debtors/Creditors/AFS/tax checklist; reviewed in full and confirmed it does not touch any in-scope revenue, VAT, journal, or tax logic. No action required, awareness only.

**Standing reminders (not defects, carried from prior reports):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry (`payroll.py`) after Budget Feb 2027 and restart the backend;
(b) early-2027 runs should execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`);
(c) the AFS PayFast payment/ad-hoc tokenization feature and the `/reports/ai-insights` feature remain outside this audit's scope;
(d) NBCPSS private security payroll mode predates this audit's baseline, not yet part of this checklist's explicit scope;
(e) file-attribution note: the imported-equity-offset (3998/3999) exclusion logic lives in `payroll.py`'s `balance_sheet()`, not `financial_statements.py`;
(f) 2026 draft TLAB/TALAB comment period closed on schedule 28 August 2026 with no bill finalisation news yet as of this run — next run should keep checking for Treasury's review outcome or Parliamentary introduction;
(g) `parent_company_id`/`user_type` columns, bookkeeper-onboarding, consolidated-billing, accountant-fee-structure, and (as of this run) the accountant-practice-dashboard/`billing_exempt` features remain outside Reports/Debtors/Creditors/AFS/tax scope, awareness only;
(h) legacy unused constants `PAYROLL_PER_EMP = 34.00` / `PAYROLL_MIN = 99.00` in `payroll.py` — still worth a cleanup pass, not a compliance issue;
(i) the 13-week cash-flow forecast feature remains additive and outside the original checklist's endpoint list — tracked via action item 4;
(j) compulsory VAT-registration turnover threshold rose to R2,300,000 (from R1,000,000), voluntary to R120,000 (from R50,000), effective 1 April 2026 — not gated anywhere in-scope, awareness only;
(k) the persistent Chart of Accounts feature (`/coa` router, `CompanyAccount`, `ChartOfAccounts`/`Expenses` components) is additive and outside the original checklist's endpoint list — tracked via action items 3 and 5 until resolved;
(l) the invoice header-image upload, custom HTML invoice template, and service-item catalogue introduced 2026-08-29 remain additive presentation/picklist features outside the original checklist's endpoint list, tracked via action item 2 for the one defect found in them.
