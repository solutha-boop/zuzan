# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 1 September 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-08-30 (PASS, one new High finding that run, one carried-over High finding, one carried-over Critical security item).

**Change detection since last run:** `git log --since="2026-08-30 00:10"` returns **zero new commits**. HEAD is unchanged at `cfb609c` (2026-08-29 15:22). `git status` shows only untracked scratch/output files (`LAUNCH_READINESS_2026-07-14.md`, `cleanup_untracked.bat`, `companies_py_fixed.py`, `netlify-drop/`, stray `.fuse_hidden*` temp files, and the flagged token file) — no tracked source file has changed. Every file in scope for this checklist is therefore byte-identical to the 08-30 baseline.

Given no code changes, this run re-verified the standing anchors directly (not just via `git diff`) and refreshed the IFRS/SARS web searches. All anchors and both outstanding bugs were reconfirmed unchanged: `"deferred_tax": 0.0` still absent from `financial_statements.py` (deferred tax remains implemented); `wear_and_tear_rate` / `purchase_order_reversal` / `TAX_YEARS` (2026/2027 and provisional 2027/2028) / `VAT_RATE = 0.15` all present and correct; the invoice line-item VAT bug (§2) and the expense-account-mismatch bug (§2) are both still present and unfixed in the code as of this run.

**Out-of-scope but flagged (Critical, security, carried over, still unresolved):** `C:\Zuzan\ghp_w0vWd0jgV1yFdHb9NODeqLMx5jlKOz3.txt` (a plaintext-looking GitHub personal access token, 40 bytes) is still present in the repo root, untracked, unchanged since 24 August. Still unresolved — see Action Items.

Fresh web searches this run for IFRS standards and SARS tax law found no changes: IFRS 18 and IFRS for SMEs third edition both remain confirmed for periods beginning 1 January 2027. The 2026 TLAB/TALAB public comment period closed 28 August 2026 as scheduled; as of this run (1 September) Treasury/SARS have not yet published finalised bill text or introduced it in Parliament — still in post-comment review, no change from the 08-30 finding.

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

**Overall: PASS, no new findings this run. Two carried-over High-severity findings (invoice line-item VAT bug, expense-account mismatch) remain unfixed, plus one carried-over Critical security item (unfixed, out of scope).**

## 2. Reports

No code changes since 08-30. Both previously-identified bugs were re-verified directly against the current file contents this run (not inferred from diff alone):

**Carried over (High) — multi-line invoice items don't respect per-line VAT flags** (`App_js_fixed.js:899-1090`, `companies.py:392-397`): `create_invoice` still computes `vat_amount = round(data.amount * VAT_RATE, 2) if data.vat_applicable else 0` (companies.py:396) purely from the top-level `amount`/`vat_applicable` fields — confirmed it still never reads `items_json` (the field is stored and returned, `companies.py:297,316,369,413,508-509`, but never parsed for VAT/total calculation). Any invoice built with mixed VAT-exempt/standard-rated line items will still have its backend-recorded `vat_amount`/`total_amount` computed flat off the whole subtotal, regardless of per-line flags. This flows into `total_revenue`/`total_outstanding` (Reports) and AR aging balances (Debtors) unchanged from the 08-30 description.

**Carried over (High) — expense category/account mismatch still reroutes to 5900 "General Expenses"** (`journal.py:143-149`, `App_js_fixed.js:2315,2390,2447,7789,7832,7839`): re-confirmed `expense_account()` looks up `CATEGORY_TO_CODE` by bare category name (`journal.py:88-98`, e.g. `"Cost of Sales": "5000"`), while the frontend's account dropdowns still submit `` `${a.code} - ${a.name}` `` (e.g. `"5000 - Cost of Sales"`) — a guaranteed miss on `CATEGORY_TO_CODE.get(category or "", "5900")`, so every expense still falls through to account 5900. Aggregate revenue/expense/net-profit totals remain correct (summed directly from `Expense.amount`); expense-by-account reporting, COGS/opex/finance-cost classification, and AFS presentation-by-account remain wrong.

Confirmed unaffected (unmodified since 08-26, re-verified this run):
- `total_revenue` sums only paid invoices via `_to_zar()` (`payroll.py:1238`), plus bank-import income (`:1240`).
- `total_outstanding` covers sent/overdue via `_to_zar()` (`payroll.py:1246`).
- Expenses excluded from revenue; PO costs added once, no double count (`payroll.py:1252,1259,2209`).
- Depreciation and payroll costs correctly included (`payroll.py:1268` + payslip cost lines).
- Management-accounts revenue trend and `/v1/summary` (`payroll.py:2189,2216,2228`; `main.py:455,485`) apply `_to_zar()` consistently.

## 3. Debtors

No code changes. Re-verified unchanged:
- `payroll.py:2557` filters `Invoice.status.in_([sent, overdue])` — paid excluded.
- Aged from `due_date` only (`payroll.py:2563-2565`), not issue/created date.
- Amounts converted via `_to_zar()` (`payroll.py:2569` area).

**Relevant to this section (see §2):** the AR balance for any invoice built with the line-items feature is still only as correct as the backend-computed `total_amount` — which can overstate VAT/total whenever mixed-VAT line items are used, per the unfixed §2 finding. Not a defect in the Debtors query itself.

## 4. Creditors

✓ No issues found. Unchanged since 08-26 baseline.
- Outstanding = received/partial POs plus unpaid on-credit expenses; fully paid POs excluded (`payroll.py:2627`).
- Reversal-aware AP balance nets `credit − debit` and includes `source.in_(["purchase_order","purchase_order_reversal"])` at all expected call sites (`payroll.py:1779,2645`, `purchase_orders.py:445`, `journal.py:848`).
- Supplier bank details decrypted via `decrypt_field()` before display (`payroll.py:2688-2690`).

## 5. Cross-module consistency

✓ No new gaps.
- Journal coverage complete and unchanged: `post_invoice_raised`, `post_invoice_paid`, `post_invoice_cogs`, `post_expense`, `post_bank_income`, `post_payroll`, `post_expense_paid`, `post_po_received`, `post_po_paid`, `post_stock_adjustment`, `post_asset_acquisition`, `post_depreciation`, `post_asset_disposal` all present in `journal.py`.
- `items_json`/travel-reference columns on `Invoice` remain display metadata only, not read by `journal.py`, which continues to post from `invoice.amount`/`vat_amount`/`total_amount` — journal entries themselves are not corrupted by the §2 VAT bug; the correctness problem is upstream in how those authoritative fields get computed.
- Migration hygiene re-confirmed: the `wear_and_tear_rate` ALTER TABLE (`database.py:1444`) and all other migrations for recent features sit inside the migrations list literal, not after the `for` loop.
- Import-awareness (2026-07-11 fixes) intact and unchanged: `source == "import"` exclusions on 1100/2000, balance sheet retains 3998/3999 imported-equity offsets.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (declared in AFS meta, `financial_statements.py:623`). File unchanged since 08-26.

**Standards status (fresh web search this run, 1 September 2026):** no change.
- IFRS 18 *Presentation and Disclosure in Financial Statements* — confirmed still effective for annual periods beginning on/after 1 January 2027, early application permitted; not applicable to IFRS-for-SMEs preparers (ZuZan's basis).
- IFRS for SMEs third edition (issued February 2025) — confirmed still effective 1 January 2027; the 2015 edition may continue to be applied until then.

**Section 5b — deferred tax:** already implemented; re-verified this run at the code level (unchanged file, no `"deferred_tax": 0.0` hard-coding found). `_deferred_tax_balance()` computes per-asset tax base via `wear_and_tear_rate`/SARS IN47 category mapping; opening/closing deferred tax balances drive `deferred_tax_expense`; the balance-sheet closing-balance line carries a matching retained-earnings adjustment so the statement still balances; Note 9 (`deferred_tax`, `total_tax`, opening/closing balances) is populated.

Finance costs (2026-07-13 fix): interest-below-EBIT split and tax/net-profit derivation from `profit_before_tax` (not EBIT) re-confirmed present and unchanged.

**Relevant to this section:** unchanged from 08-30 — neither the §2 expense-account bug nor the invoice-VAT bug touches `financial_statements.py` directly; aggregate totals remain correct in total even when misclassified by account or overstated by wrongly-applied VAT on a specific invoice. The VAT bug would still slightly overstate revenue/VAT payable for any affected invoice once one exists, flowing into the AFS income statement and Note 9 VAT reconciliation.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date, present at `payroll.py:132`. `payroll.py` unchanged since 08-29.

- Fresh web search this run confirmed 2026/2027 PAYE brackets (18%–45% across seven brackets, top bracket 45% above R1,878,600), primary rebate R17,820, secondary rebate (65-74) R9,765/total R27,585, tertiary (75+) R3,249/total R30,834, UIF ceiling R17,712/month at 1% employee + 1% employer, SDL 1% employer-only — all match `payroll.py:132-146` exactly, no changes.
- CIT remains flat 27% (unchanged) — matches code used in dashboard/management/provisional-tax and `financial_statements.py`'s deferred-tax calc.
- VAT standard rate confirmed unchanged at 15% (`VAT_RATE = 0.15` in `companies.py:282`, `payroll.py:1609,2802`, `quotes.py:15`); no rate-change proposals found in the 2026 TLAB/TALAB coverage.
- 2026 draft TLAB/TALAB: public comment period closed 28 August 2026 as scheduled. As of 1 September 2026, still no finalised bill text or Parliamentary introduction — Treasury/SARS remain in post-comment review. None of the proposals found (living-annuity de minimis aggregation across multiple annuities, inter-spousal donations-tax exemption restricted to SA-resident recipient spouses, and the previously-noted SEZ/ATA carnet/second-hand-goods/VDP items) affect PAYE brackets, UIF, SDL, CIT, or VAT rates used in this codebase.
- No edits made to tax tables (report-only per task rules; §5b was verification-only this run, already implemented).

**Sources consulted:** [2026 Draft Tax Bills have been published for comment — GoLegal](https://www.golegal.co.za/2026-draft-tax-bills/) · [Draft Taxation Laws Amendment Bill, 2026 — SARS](https://www.sars.gov.za/wp-content/uploads/Legal/Drafts/Legal-LPrep-Draft-2026-31-Draft-Taxation-Laws-Amendment-Bill-2026-30-July-2026.pdf) · [National Treasury Publishes 2026 Draft Tax Bills for Public Comment — Tax Consulting SA](https://www.taxconsulting.co.za/national-treasury-publishes-2026-draft-tax-bills-for-public-comment/) · [Big tax changes proposed — IOL](https://iol.co.za/business/2026-08-06-big-tax-changes-proposed-what-the-new-draft-bills-mean-for-taxpayers/) · [2026 draft TLAB: Key changes for businesses — PvdZ Consulting](https://tax.pvdz.co.za/tlab/) · [The 2026 Draft Tax Bills Are Out — Accounting Weekly](https://www.accountingweekly.com/sars-updates/2026-draft-tlab-and-talab-what-accountants-must-know) · [National Treasury on publication of the 2026 draft tax bills — gov.za](https://www.gov.za/news/media-statements/national-treasury-publication-2026-draft-tax-bills-comment-30-jul-2026) · [IFRS - The IFRS for SMEs Accounting Standard](https://www.ifrs.org/issued-standards/ifrs-for-smes/) · [IFRS - March 2026 IFRS for SMEs Accounting Standard Update](https://www.ifrs.org/supporting-implementation/2015-ifrs-for-smes-supporting-materials/sme-updates/2026/march-2026-ifrs-for-smes-accounting-standard-update/) · [Navigating IFRS for SMEs Accounting Standard, Third Edition (2025) — Uniqus](https://uniqus.com/wp-content/uploads/2026/05/Navigating-IFRS-for-SMEs-Accounting-Standard-Third-Edition-2025.pdf) · [IASB issues third edition of the IFRS for SMEs — PwC Viewpoint](https://viewpoint.pwc.com/dt/gx/en/pwc/in_briefs/in_briefs_INT/in_briefs_INT/iasb-issues.html) · [SARS Tax Tables 2026/2027 — Accounter](https://accounter.co.za/news/sars-tax-tables-2026-2027) · [How to calculate PAYE in South Africa (2026/2027 tax tables) — Govchain](https://www.govchain.co.za/blog/how-to-calculate-paye-in-south-africa)

## 8. Action items

1. **Critical (security, out-of-scope but urgent, carried over unresolved):** `C:\Zuzan\ghp_w0vWd0jgV1yFdHb9NODeqLMx5jlKOz3.txt` still contains what appears to be a live GitHub personal access token in plaintext in the project root, untracked. Recommend revoking it in GitHub settings and deleting the file; check git history in case it was ever committed.
2. **High (carried over, unfixed):** the multi-line invoice-items feature (`App_js_fixed.js:899-1090`, `companies.py:392-397`) still does not make the backend's VAT calculation respect per-line `vat_applicable` flags — every invoice is charged flat 15% (or the manual foreign-currency override) on the whole subtotal, regardless of which lines were marked VAT-exempt in the UI. Recommend either removing the per-line VAT checkbox until the backend honours it, or having `create_invoice`/`update_invoice` derive `vat_amount`/`total_amount` from `items_json` when present. The "Pick from Catalog" shortcut (`App_js_fixed.js:927-937`) can still silently overwrite `data.amount`/`vatApplicable` out from under an in-progress line-items table.
3. **High (carried over, unfixed):** expense "Account" dropdown value (`"{code} - {name}"`) doesn't match `CATEGORY_TO_CODE`'s bare-name keys in `journal.py:88-149`, so manually-entered expenses AND bank-import-categorised expenses both post to account 5900 "General Expenses" regardless of the account selected in the UI. Recommend `expense_account()` parse the leading code from `category` and look up `Account` by code directly.
4. **Medium (carried over):** `/reports/cash-flow-13week` (`payroll.py:1991-2098`) still does not model outstanding creditor (PO) payments or VAT201 liabilities as distinct weekly outflows (`other_payments`/`vat_payment` hard-coded `0.0`).
5. **Low (carried over):** the `/coa` custom-account feature lets users add accounts to the `CompanyAccount` table and select them in expense dropdowns, but nothing in `journal.py` posts to a custom account by code. Remains effectively decorative until item 3 is fixed the recommended way.
6. **Low (observation, carried over, not yet a defect):** cosmetic comment/statement-duplication artifacts (`main.py`'s disabled-middleware comment, `billing.py`'s repeated `resp = None` in `adhoc_charge()`) — no new growth this run since there were no commits; still worth a cleanup pass whenever convenient.

**Standing reminders (not defects, carried from prior reports):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry (`payroll.py`) after Budget Feb 2027 and restart the backend;
(b) early-2027 runs should execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`);
(c) the AFS PayFast payment/ad-hoc tokenization feature and the `/reports/ai-insights` feature remain outside this audit's scope;
(d) NBCPSS private security payroll mode predates this audit's baseline, not yet part of this checklist's explicit scope;
(e) file-attribution note: the imported-equity-offset (3998/3999) exclusion logic lives in `payroll.py`'s `balance_sheet()`, not `financial_statements.py`;
(f) 2026 draft TLAB/TALAB comment period closed on schedule 28 August 2026 with no bill finalisation news yet as of this run — next run should keep checking for Treasury's review outcome or Parliamentary introduction;
(g) `parent_company_id`/`user_type` columns and bookkeeper-onboarding/consolidated-billing/accountant-fee-structure features remain outside Reports/Debtors/Creditors/AFS/tax scope, awareness only;
(h) legacy unused constants `PAYROLL_PER_EMP = 34.00` / `PAYROLL_MIN = 99.00` in `payroll.py` — still worth a cleanup pass, not a compliance issue;
(i) the 13-week cash-flow forecast feature remains additive and outside the original checklist's endpoint list — tracked via action item 4;
(j) compulsory VAT-registration turnover threshold rises to R2,300,000 (from R1,000,000), voluntary to R120,000 (from R50,000), effective 1 April 2026 — not gated anywhere in-scope, awareness only;
(k) the persistent Chart of Accounts feature (`/coa` router, `CompanyAccount`, `ChartOfAccounts`/`Expenses` components) is additive and outside the original checklist's endpoint list — tracked via action items 3 and 5 until resolved;
(l) the invoice header-image upload, custom HTML invoice template (`Company.invoice_template_html`), and service-item catalogue (`ServiceItem`) introduced 2026-08-29 remain additive presentation/picklist features outside the original checklist's endpoint list, tracked via action item 2 for the one defect found in them; catalogue/template rendering themselves were reviewed and found correct in the 08-30 run and are unchanged.
