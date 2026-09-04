# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 4 September 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-09-03 (PASS, no new findings; two carried-over High findings, one carried-over Critical security item).

**Change detection since last run:** `git log --since="2026-09-03 00:00"` returns **one new commit**, `1e6a7d4` (3 September 2026, 06:02) — HEAD is now `1e6a7d4`. This commit only adds the prior day's audit report file plus two purely cosmetic no-op diffs already tracked as a standing item: one more duplicate `resp = None` line in `billing.py` (now four consecutive duplicates) and one more duplication of the disabled-middleware comment line in `main.py`. No functional code changed. No other commits exist between then and this run (current time 4 September 2026, 00:06 SAST).

Every anchor from the 09-03 report was re-verified directly against current file contents this run (not inferred from the diff):
- `companies.py:398` — `vat_amount = round(data.amount * VAT_RATE, 2) if data.vat_applicable else 0` — unchanged, still ignores `items_json`.
- `payroll.py` — `_to_zar()`/`_po_delivered_net()` usage across dashboard (:1238-1261), management accounts (:2189-2290), `/v1/summary`, AR aging (:1628-1644, 2555-2569), AP/creditors (:1771-1779, 2638-2645) all unchanged, same line numbers as prior run.
- `journal.py:88-149` — `CATEGORY_TO_CODE`/`expense_account()` unchanged, still keyed on bare category name.
- `journal.py:848`, `purchase_orders.py:445`, `payroll.py:1779,2645`, `financial_statements.py:558` — all still include `source.in_(["purchase_order","purchase_order_reversal"])`.
- `payroll.py:2688-2690` — `decrypt_field()` still wraps supplier bank details before display.
- `database.py:1445,1531` — `wear_and_tear_rate` and `billing_exempt` migrations both still sit inside the migrations list literal, not after the `for` loop.
- `financial_statements.py:131,266-268,601,606-610` — `_deferred_tax_balance()`, `deferred_tax_expense`, `total_tax`, and Note 9 fields all present; no `"deferred_tax": 0.0` hard-coding.
- `payroll.py:132-146` — `TAX_YEARS["2026/2027"]` brackets, primary rebate R17,820, secondary R9,765, tertiary R3,249, UIF ceiling R17,712 unchanged; `"2027/2028"` provisional copy still flagged `"provisional": True`.
- `payroll.py:1609,2802` — `VAT_RATE = 0.15` unchanged in both locations.
- `App_js_fixed.js:899-1090` — per-line VAT checkbox (`vat_applicable`) still computes a correct-looking preview client-side but the backend still doesn't consume `items_json` for VAT/total.
- `C:\Zuzan\ghp_w0vWd0jgV1yFdHb9NODeqLMx5jlKOz3.txt` — still present in the repo root, untracked, unchanged (last modified 24 Aug 2026).

Fresh web searches this run found no changes to IFRS or SARS positions: IFRS for SMEs third edition (issued Feb 2025) remains effective for periods beginning on/after 1 January 2027, with a September 2026 consultation only proposing an SME consolidation-exception extension aligned to the same 1 Jan 2027 date — no acceleration. The 2026 draft TLAB/TALAB remain in the post-comment-period review phase (comment period closed 28 August 2026); no evidence of Parliamentary introduction yet. SARS 2026/2027 PAYE brackets, primary rebate (R17,820), UIF ceiling (R17,712 at 1%/1%), SDL (1%, exempt below R500,000 payroll), and VAT (15%) independently re-confirmed via web search and all match the code exactly.

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

**Overall: PASS. This run's single commit is a no-op (prior report file + cosmetic duplicate lines already tracked). No new findings. Two carried-over High-severity findings (invoice line-item VAT bug, expense-account mismatch) remain unfixed, plus one carried-over Critical security item (unfixed, out of scope).**

## 2. Reports

No functional changes since 09-03. Both previously-identified bugs re-verified directly against current file contents:

**Carried over (High) — multi-line invoice items don't respect per-line VAT flags** (`App_js_fixed.js:899-1090`, `companies.py:395-399`): `create_invoice` still computes `vat_amount = round(data.amount * VAT_RATE, 2) if data.vat_applicable else 0` purely from the top-level `amount`/`vat_applicable` fields — never reads `items_json`. Any invoice built with mixed VAT-exempt/standard-rated line items still has its backend-recorded `vat_amount`/`total_amount` computed flat off the whole subtotal. Flows into `total_revenue`/`total_outstanding` (Reports) and AR aging balances (Debtors).

**Carried over (High) — expense category/account mismatch still reroutes to 5900 "General Expenses"** (`journal.py:143-149`, `App_js_fixed.js:2315,2390,2447,7789,7832,7839`): `expense_account()` still looks up `CATEGORY_TO_CODE` by bare category name while the frontend's account dropdowns still submit `"{code} - {name}"` — a guaranteed miss, so every expense still falls through to account 5900. Aggregate revenue/expense/net-profit totals remain correct; expense-by-account reporting, COGS/opex/finance-cost classification, and AFS presentation-by-account remain wrong.

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
- Journal coverage complete and unchanged: `post_invoice_raised`, `post_invoice_paid`, `post_invoice_cogs`, `post_expense`, `post_bank_income`, `post_payroll`, `post_expense_paid`, `post_po_received`, `post_po_paid`, `post_stock_adjustment`, `post_asset_acquisition`, `post_depreciation`, `post_asset_disposal` all present and wired into the backfill routine (`journal.py:743-894`).
- Migration hygiene re-confirmed for `wear_and_tear_rate` (`database.py:1445`) and `billing_exempt` (`database.py:1531`) — both inside the migrations list literal.
- Import-awareness (2026-07-11 fixes) intact: balance sheet retains 3998/3999 imported-equity offsets (`payroll.py:1538-1547`).

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (declared in AFS meta, `financial_statements.py:623`). File unchanged since 08-26.

**Standards status (fresh web search this run, 4 September 2026):** no change.
- IFRS 18 *Presentation and Disclosure in Financial Statements* — still effective for annual periods beginning on/after 1 January 2027, early application permitted; not applicable to IFRS-for-SMEs preparers (ZuZan's basis).
- IFRS for SMEs third edition (issued 27 February 2025) — still effective 1 January 2027. A new item found this run: a September 2026 IASB consultation (comment period ending 9 September 2026) proposes extending the consolidation exception for eligible SMEs, aligned to the same 1 Jan 2027 effective date — a proposal, not yet issued, and not relevant to ZuZan (no consolidation requirement in scope). The 2015 edition may continue to be applied until the effective date.

**Section 5b — deferred tax:** already implemented; re-verified this run at the code level (unchanged file, no `"deferred_tax": 0.0` hard-coding found). `_deferred_tax_balance()` (`financial_statements.py:131`) computes per-asset tax base via `wear_and_tear_rate`/SARS IN47 category mapping; opening/closing deferred tax balances (`:266-268`) drive `deferred_tax_expense`; `total_tax` combines current + deferred (`:601`); Note 9 (`deferred_tax`, `deferred_tax_opening_balance`, `deferred_tax_closing_balance`) populated (`:606-610`); balance-sheet closing balance carries matching retained-earnings adjustment so the statement still balances.

Finance costs (2026-07-13 fix): interest-below-EBIT split and tax/net-profit derivation from `profit_before_tax` (not EBIT) re-confirmed present and unchanged.

**Relevant to this section:** unchanged from prior runs — neither the §2 expense-account bug nor the invoice-VAT bug touches `financial_statements.py` directly; aggregate totals remain correct in total even when misclassified by account.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date, present at `payroll.py:132`. `payroll.py` unchanged since 08-29.

- Re-confirmed at code level (unchanged file) and independently cross-checked via fresh web search this run: PAYE brackets 18%–45% across seven brackets (18% to R245,100; 26% to R383,100; 31% to R530,200; 36% to R695,800; 39% to R887,000; 41% to R1,878,600; 45% above), primary rebate R17,820, UIF ceiling R17,712/month at 1% employee + 1% employer, SDL 1% employer-only (exempt below R500,000 annual payroll) — all present at `payroll.py:132-146`, matches external SARS-tables sources exactly, no changes.
- CIT remains flat 27% (unchanged) — matches code used in dashboard/management/provisional-tax and `financial_statements.py`'s deferred-tax calc.
- VAT standard rate confirmed unchanged at 15% (`VAT_RATE = 0.15` in `companies.py:282`, `payroll.py:1609,2802`, `quotes.py:15`); no rate-change proposals found.
- 2026 draft TLAB/TALAB: still in post-comment-period review (comment period closed 28 August 2026); no evidence this run of finalised bill text or Parliamentary introduction. None of the proposals found affect PAYE brackets, UIF, SDL, CIT, or VAT rates used in this codebase.
- No edits made to tax tables (report-only per task rules; §5b was verification-only this run, already implemented).

**Sources consulted:** [IFRS - IASB proposes extending consolidation exception for eligible SMEs](https://www.ifrs.org/news-and-events/news/2026/05/iasb-proposes-extending-consolidation-exception-eligible-smes/) · [IFRS - June 2026 IFRS for SMEs Accounting Standard Update](https://www.ifrs.org/supporting-implementation/2015-ifrs-for-smes-supporting-materials/sme-updates/2026/june-2026-ifrs-for-smes-accounting-standard-update/) · [Third edition of the IFRS for SMEs Accounting Standard — ACCA](https://www.accaglobal.com/learning-and-events/corporate-reporting/third-edition-ifrs-for-smes.html) · [IASB issues third edition of the IFRS for SMEs — PwC Viewpoint](https://viewpoint.pwc.com/dt/gx/en/pwc/in_briefs/in_briefs_INT/in_briefs_INT/iasb-issues.html) · [Taxation Laws Amendment Bill (B30-2025) — Parliament of South Africa](https://www.parliament.gov.za/bill/2325971) · [Draft Taxation Laws Amendment Bill, 2026 — SARS](https://www.sars.gov.za/wp-content/uploads/Legal/Drafts/Legal-LPrep-Draft-2026-31-Draft-Taxation-Laws-Amendment-Bill-2026-30-July-2026.pdf) · [Draft Tax Administration Laws Amendment Bill, 2026 — National Treasury](https://www.treasury.gov.za/comm_media/press/2026/Draft%20Tax%20Administration%20Laws%20Amendment%20Bill%2029%20July%202026%20pdf.pdf) · [Big tax changes proposed — IOL](https://iol.co.za/business/2026-08-06-big-tax-changes-proposed-what-the-new-draft-bills-mean-for-taxpayers/) · [2026 Draft Tax Bills have been published for comment — GoLegal](https://www.golegal.co.za/2026-draft-tax-bills/) · [SARS Tax Tables 2026/2027 — Accounter](https://accounter.co.za/news/sars-tax-tables-2026-2027) · [How to calculate PAYE in South Africa (2026/2027 tax tables) — Govchain](https://www.govchain.co.za/blog/how-to-calculate-paye-in-south-africa)

## 8. Action items

1. **Critical (security, out-of-scope but urgent, carried over unresolved):** `C:\Zuzan\ghp_w0vWd0jgV1yFdHb9NODeqLMx5jlKOz3.txt` still contains what appears to be a live GitHub personal access token in plaintext in the project root, untracked. Recommend revoking it in GitHub settings and deleting the file; check git history in case it was ever committed.
2. **High (carried over, unfixed):** the multi-line invoice-items feature (`App_js_fixed.js:899-1090`, `companies.py:395-399`) still does not make the backend's VAT calculation respect per-line `vat_applicable` flags. Recommend either removing the per-line VAT checkbox until the backend honours it, or having `create_invoice`/`update_invoice` derive `vat_amount`/`total_amount` from `items_json` when present.
3. **High (carried over, unfixed):** expense "Account" dropdown value (`"{code} - {name}"`) doesn't match `CATEGORY_TO_CODE`'s bare-name keys in `journal.py:88-149`, so manually-entered and bank-import-categorised expenses both post to account 5900 regardless of the account selected. Recommend `expense_account()` parse the leading code from `category` and look up `Account` by code directly.
4. **Medium (carried over):** `/reports/cash-flow-13week` (`payroll.py:1991-2098`) still does not model outstanding creditor (PO) payments or VAT201 liabilities as distinct weekly outflows.
5. **Low (carried over):** the `/coa` custom-account feature lets users add accounts to `CompanyAccount` and select them in expense dropdowns, but `journal.py` never posts to a custom account by code. Remains decorative until item 3 is fixed.
6. **Low (observation, carried over, worsening slightly):** cosmetic comment/line-duplication artifacts in `main.py` (disabled-middleware comment, now duplicated a further time by this run's commit) and `billing.py` (`resp = None` now duplicated four times) — still harmless but worth a cleanup pass; each no-op commit adds one more duplicate line.

**Standing reminders (not defects, carried from prior reports):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry (`payroll.py`) after Budget Feb 2027 and restart the backend;
(b) early-2027 runs should execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`);
(c) the AFS PayFast payment/ad-hoc tokenization feature and the `/reports/ai-insights` feature remain outside this audit's scope;
(d) NBCPSS private security payroll mode predates this audit's baseline, not yet part of this checklist's explicit scope;
(e) file-attribution note: the imported-equity-offset (3998/3999) exclusion logic lives in `payroll.py`'s `balance_sheet()`, not `financial_statements.py`;
(f) 2026 draft TLAB/TALAB comment period closed on schedule 28 August 2026 with no bill finalisation news yet as of this run — next run should keep checking for Treasury's review outcome or Parliamentary introduction;
(g) `parent_company_id`/`user_type` columns, bookkeeper-onboarding, consolidated-billing, accountant-fee-structure, and the accountant-practice-dashboard/`billing_exempt` features remain outside Reports/Debtors/Creditors/AFS/tax scope, awareness only;
(h) legacy unused constants `PAYROLL_PER_EMP = 34.00` / `PAYROLL_MIN = 99.00` in `payroll.py` — still worth a cleanup pass, not a compliance issue;
(i) the 13-week cash-flow forecast feature remains additive and outside the original checklist's endpoint list — tracked via action item 4;
(j) compulsory VAT-registration turnover threshold rose to R2,300,000 (from R1,000,000), voluntary to R120,000 (from R50,000), effective 1 April 2026 — not gated anywhere in-scope, awareness only;
(k) the persistent Chart of Accounts feature (`/coa` router, `CompanyAccount`, `ChartOfAccounts`/`Expenses` components) is additive and outside the original checklist's endpoint list — tracked via action items 3 and 5 until resolved;
(l) the invoice header-image upload, custom HTML invoice template, and service-item catalogue introduced 2026-08-29 remain additive presentation/picklist features outside the original checklist's endpoint list, tracked via action item 2 for the one defect found in them;
(m) a September 2026 IASB consultation proposes extending the SME consolidation exception (comment period ended 9 Sept 2026, effective date aligned to 1 Jan 2027 if issued) — not relevant to ZuZan (no consolidation in scope), monitor for final issuance.
