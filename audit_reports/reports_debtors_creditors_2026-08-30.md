# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 30 August 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-08-29 (PASS, one carried-over High finding, one carried-over Critical security item).

**Change detection since last run:** `git log --since="2026-08-29 00:04"` returns **4 new commits**, all dated 2026-08-29 afternoon (`d4214ae` "invoice header image upload + service item catalogue + pick-from-catalog", `f0d5ea6`/`a9e8f0c`/`cfb609c` "custom HTML invoice template + line items + reference fields (tour/pax/travel)"). HEAD moved from `2554766` to `cfb609c`. This ends the four-day run of byte-identical re-verifications. `git diff --stat` confirms `payroll.py`, `journal.py`, `financial_statements.py`, `purchase_orders.py`, `customers.py`, `suppliers.py`, `csv_import.py` are **unchanged** — the new commits touch only `App_js_fixed.js`, `zuzan-backend/companies.py`, `database.py`, `main.py`, `billing.py` (invoicing feature work: multi-line invoice items, a service/product catalogue, an invoice header-image upload, a custom HTML invoice template, and travel/reference fields for tour bookings). All previously-verified standing anchors were re-confirmed unaffected by empty diff on the untouched files: `"deferred_tax": 0.0"` still absent from `financial_statements.py`, `wear_and_tear_rate` / `purchase_order_reversal` / `TAX_YEARS` / `VAT_RATE = 0.15` / `S11F_CAP` all present and unchanged.

This run's code review of the new commits surfaced **one new High-severity finding**: the new multi-line invoice-items feature has a VAT-calculation bug (§2, "New finding"). Full detail below.

**Out-of-scope but flagged (Critical, security, carried over, still unresolved):** `C:\Zuzan\ghp_w0vWd0jgV1yFdHb9NODeqLMx5jlKOz3.txt` (a plaintext-looking GitHub personal access token) is still present in the repo root, untracked, unchanged since 24 August. Still unresolved — see Action Items.

Fresh web searches this run for IFRS standards and SARS tax law found no changes: IFRS 18 and IFRS for SMEs 3rd edition both remain confirmed for periods beginning 1 January 2027. The 2026 TLAB/TALAB public comment period closed 28 August 2026 as scheduled; Treasury's post-comment review/finalisation has not yet produced bill text or Parliamentary introduction as of this run.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ⚠️ PASS with two findings — carried-over expense-account bug (unfixed) + new invoice-VAT bug from 08-29 commits |
| Debtors (AR) | ⚠️ PASS with new finding — aging/status logic itself unaffected, but new line-items feature can misstate invoiced VAT/total feeding into AR balances |
| Creditors (AP) | ✅ PASS — reversal-aware, bank details decrypted; untouched by this run's commits |
| Cross-module consistency | ✅ PASS — full journal coverage; new invoice fields are additive metadata only, no new journal gap |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) re-verified at code level, no regressions, no standards changes |
| Tax rates (SARS) | ✅ PASS — 2026/2027 tables current, no rate changes; TLAB/TALAB still in post-comment-period limbo |

**Overall: PASS, with one new High-severity finding (invoice line-item VAT bug), one carried-over High-severity finding (unfixed expense-account mismatch), and one carried-over Critical security item (unfixed, out of scope).**

## 2. Reports

**NEW (High) — multi-line invoice items don't respect per-line VAT flags; actual VAT charged can diverge from what the line-item table displays:**

The 2026-08-29 commits added an optional "line-item breakdown" to the invoice form (`App_js_fixed.js:1034-1090`) plus a service/product catalogue "Pick from Catalog" shortcut (`:927-937`). Three independent code paths all write to the single top-level `data.amount` / `data.vatApplicable` fields that are actually submitted to the backend, and none of them stay in sync:

- Per-line VAT: each line item has its own `vat_applicable` checkbox (`:1069`) and `syncLines()` (`:906-921`) computes a correct per-line VAT/total from it — but only writes the aggregated ex-VAT `amount` and `items_json` back to the parent form (`:916-920`). It never touches `data.vatApplicable`.
- Top-level VAT: a separate "Apply VAT @ 15%" checkbox (`:982-988`, default checked) is the *only* VAT flag actually sent to the backend (`:1847`, `invBody.vat_applicable:form.vatApplicable`).
- Catalog pick: selecting an item from "Pick from Catalog" (`:930-934`) overwrites `data.amount`/`data.vatApplicable` directly and independently of whatever is in the line-items table, even while line-item mode is active — desyncing the displayed line-item subtotal from what actually gets submitted.
- Backend: `create_invoice` (`companies.py:392-396`) computes `vat_amount = amount * VAT_RATE` (flat 15%, or a manual override for foreign currency) purely from the top-level `amount`/`vat_applicable` fields — it never parses `items_json`, so per-line VAT-exempt marking has no effect on the amount actually invoiced/recorded.

**Impact:** if a user builds an invoice with mixed lines (e.g. a tour package with a zero-rated international leg alongside standard-rated local services — plausible given this app's travel/tour-focused fields: `tour_ref`, `pax_count`, `passenger_name`), the printed invoice's line-items table (`App_js_fixed.js:1106-1120`, using each line's own `vat_amount`/`total`) will show a different total than the invoice's actual header `total`/`vat_amount` (`:1145-1147`, from backend-authoritative `doc.total_amount`/`doc.vat_amount`) — because the backend charged/recorded 15% VAT on the *entire* subtotal, ignoring which lines were flagged VAT-exempt. This both misstates the amount actually invoiced to the client and overstates SARS output tax (VAT201) on what may be a genuinely zero-rated or exempt supply — a VAT Act compliance risk, not just a cosmetic one. It also flows straight through into `total_revenue`/`total_outstanding` in Reports and into Debtors aging balances, since those all read `invoice.total_amount`/`vat_amount` as stored.

**Fix recommended:** either (a) remove the per-line VAT checkbox until the backend can honour it — compute VAT invoice-wide only — or (b) make `create_invoice`/`update_invoice` parse `items_json` when present and sum `vat_amount`/`total` from the lines (respecting each line's flag) instead of the flat top-level calculation, and drop the separate top-level "Apply VAT" checkbox once line items are in use.

Confirmed unaffected (files not touched by this run's commits, byte-identical to the 08-26 baseline, re-verified via `git diff`):
- `total_revenue` sums only paid invoices via `_to_zar()` (`payroll.py:1238`), plus bank-import income (`:1240`).
- `total_outstanding` covers sent/overdue via `_to_zar()` (`payroll.py:1246`).
- Expenses excluded from revenue; PO costs added once, no double count (`payroll.py:1252,1259,2209`).
- Depreciation and payroll costs correctly included (`payroll.py:1268` + payslip cost lines).
- Management-accounts revenue trend and `/v1/summary` (`payroll.py:2189,2216,2228`; `main.py:455,485`) apply `_to_zar()` consistently.

**Carried over (High) — expense category/account mismatch still reroutes to 5900 "General Expenses"** (unchanged, unfixed, `journal.py:88-149`, `App_js_fixed.js:2018,2093,2150,7492,7535,7542`, `companies.py:1252-1319`): the expense "Account" dropdown submits `"{code} - {name}"` but `expense_account()` looks up bare names, so every manual and bank-imported expense falls through to account 5900 regardless of the account chosen. Aggregate revenue/expense/net-profit totals remain correct (summed directly from `Expense.amount`); expense-by-account reporting, COGS/opex/finance-cost classification, and AFS presentation-by-account remain wrong. Same recommendation as prior reports: parse the leading account code out of `category` in `expense_account()`.

## 3. Debtors

New commits are additive metadata on the `Invoice` model (`items_json`, `tour_ref`, `quote_ref`, `tax_ref`, `travel_date`, `pax_count`, `passenger_name`) — they don't touch the AR query, status filter, or aging logic, all of which live in unmodified `payroll.py`. Re-verified unchanged:
- `payroll.py:2557` filters `Invoice.status.in_([sent, overdue])` — paid excluded.
- Aged from `due_date` only (`payroll.py:2563-2565`), not issue/created date.
- Amounts converted via `_to_zar()` (`payroll.py:2569` area).

**Relevant to this section (see §2 new finding):** the AR balance for any invoice built with the new line-items feature is only as correct as the `total_amount` the backend computed — which, per §2, can be too high (VAT charged on lines the user intended as VAT-exempt) whenever mixed-VAT line items are used on a ZAR invoice. This is a data-accuracy risk flowing into Debtors, not a defect in the Debtors query itself.

## 4. Creditors

✓ No issues found. Untouched by this run's commits (`purchase_orders.py`, `payroll.py`'s creditors-aging, `journal.py` all byte-identical to the 08-26 baseline).
- Outstanding = received/partial POs plus unpaid on-credit expenses; fully paid POs excluded (`payroll.py:2627`).
- Reversal-aware AP balance nets `credit − debit` and includes `source.in_(["purchase_order","purchase_order_reversal"])` at all expected call sites (`payroll.py:1779,2645`, `purchase_orders.py:445`, `journal.py:848`).
- Supplier bank details decrypted via `decrypt_field()` before display (`payroll.py:2688-2690`).

## 5. Cross-module consistency

✓ No new gaps.
- Journal coverage complete and unchanged: `post_invoice_raised`, `post_invoice_paid`, `post_invoice_cogs`, `post_expense`, `post_bank_income`, `post_payroll`, `post_expense_paid`, `post_po_received`, `post_po_paid`, `post_stock_adjustment`, `post_asset_acquisition`, `post_depreciation`, `post_asset_disposal` all present in unmodified `journal.py`.
- The new `ServiceItem` catalogue (`database.py:1030-1046`, `companies.py` `service_router`) is a pure picklist for pre-filling invoice description/price — it posts nothing to the journal itself and needs nothing to, since the resulting invoice is journaled the normal way via existing invoice-posting logic. No gap.
- The new `items_json`/travel-reference columns on `Invoice` are display metadata only (not used by `journal.py`, which continues to post from `invoice.amount`/`vat_amount`/`total_amount`) — so journal entries themselves are not double-counted or corrupted by this feature; the correctness problem is upstream, in how those authoritative fields get computed (§2).
- Migration hygiene confirmed correct: all seven new `ALTER TABLE`/`CREATE TABLE` statements for this feature (`database.py:1527-1548`) sit **inside** the migrations list literal, not after the `for` loop — no dead-code migration risk (the pitfall flagged in earlier audits).
- Import-awareness (2026-07-11 fixes) intact and unchanged: `source == "import"` exclusions on 1100/2000 (`payroll.py:1737,1813`), balance sheet retains 3998/3999 imported-equity offsets (`payroll.py:1538-1547`) — none of this touched by the invoicing commits.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (declared in AFS meta, `financial_statements.py:623`). `financial_statements.py` is byte-identical to the 08-26 baseline audited on 08-27/28/29 — untouched by this run's commits.

**Standards status (fresh web search this run):** no change.
- IFRS 18 *Presentation and Disclosure in Financial Statements* — confirmed still effective for annual periods beginning on/after 1 January 2027; not applicable to IFRS-for-SMEs preparers (ZuZan's basis).
- IFRS for SMEs third edition (issued 27 February 2025) — confirmed still effective 1 January 2027, early adoption permitted, current 2015 edition may continue to be applied until then.

**Section 5b — deferred tax:** already implemented; re-verified this run at the code level (unchanged file). `_deferred_tax_balance()` (`financial_statements.py:131`) computes per-asset tax base via `wear_and_tear_rate`/SARS IN47 category mapping; `dt_opening`/`dt_closing` (lines 266-268) drive `deferred_tax_expense`; the balance-sheet closing-balance line (2600 Deferred Tax Liability / 1900 Deferred Tax Asset, lines 315-328) carries a matching retained-earnings adjustment so the statement still balances; Note 9 (`deferred_tax` line 606, `total_tax` line 601, opening/closing balances lines 609-610) is populated. No `"deferred_tax": 0.0` hard-coding found anywhere in the file.

Finance costs (2026-07-13 fix): interest-below-EBIT split and tax/net-profit derivation from `profit_before_tax` (not EBIT) re-confirmed present and unchanged.

**Relevant to this section:** neither the §2 expense-account bug nor the new invoice-VAT bug touches `financial_statements.py` directly — net profit and tax provisioning derive from aggregate totals (`Expense.amount`, `Invoice.total_amount`) that are correct in total even when misclassified by account or (per the new bug) inflated by wrongly-applied VAT on a specific invoice. The new VAT bug would, however, slightly overstate revenue/VAT payable for any affected invoice, which does flow into the AFS income statement and Note 9 VAT reconciliation once such an invoice exists — worth fixing before it's used on a real tour-package invoice with a zero-rated leg.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date, present at `payroll.py:132`. `payroll.py` untouched by this run's commits.

- Fresh web search this run: PAYE brackets, rebates, and UIF figures for 2026/2027 confirmed unchanged — 18%–45% across seven brackets (top bracket 45% above R1,878,600), primary rebate R17,820, secondary rebate (65-74) R9,765, tertiary (75+) R3,249, UIF ceiling R17,712/month at 1% employee + 1% employer. Matches `payroll.py:100-197`.
- CIT confirmed flat 27% via fresh search — unchanged, matches code used in dashboard/management/provisional-tax and `financial_statements.py`'s deferred-tax calc.
- VAT: this run's targeted VAT-rate search did not return a fresh explicit confirmation, but nothing in the 2026 TLAB/TALAB draft-bill coverage (donations tax, living-annuity de minimis, SEZ transfer pricing, ATA carnets, second-hand-goods documentation, VDP interest relief) mentions a VAT rate change, and the standard rate has been unchanged at 15% since April 2018. Treated as unchanged, consistent with the last four runs' explicit 15% confirmations; matches `VAT_RATE = 0.15` (`payroll.py:1609,2802`).
- 2026 draft TLAB/TALAB: public comment period closed 28 August 2026 as scheduled. No finalised bill text, enacted amendments, or Parliamentary introduction found this run — Treasury/SARS are still in the post-comment review stage. None of the proposals found (donations tax exemption for non-resident spouses, living-annuity de minimis limits, SEZ domestic transfer pricing, ATA carnet provisions, second-hand-goods documentation, bank refund pre/post-deposit screening, VDP interest relief) affect PAYE brackets, UIF, SDL, CIT, or VAT rates used in this codebase.
- No edits made to tax tables (report-only per task rules; §5b was verification-only this run, already implemented).

**Sources consulted:** [IFRS - The IFRS for SMEs Accounting Standard](https://www.ifrs.org/issued-standards/ifrs-for-smes/) · [IFRS - IASB issues a major update to the IFRS for SMEs Accounting Standard](https://www.ifrs.org/news-and-events/news/2025/02/iasb-issues-major-update-smes-accounting-standard/) · [IASB releases third edition of IFRS for SMEs — The Accountant](https://www.theaccountant-online.com/news/iasb-releases-ifrs-for-smes/) · [Third edition of the IFRS for SMEs Accounting Standard — ACCA](https://www.accaglobal.com/learning-and-events/corporate-reporting/third-edition-ifrs-for-smes.html) · [National Treasury Publishes 2026 Draft Tax Bills for Public Comment — Tax Consulting SA](https://www.taxconsulting.co.za/national-treasury-publishes-2026-draft-tax-bills-for-public-comment/) · [National Treasury on publication of the 2026 draft tax bills for comment — gov.za](https://www.gov.za/news/media-statements/national-treasury-publication-2026-draft-tax-bills-comment-30-jul-2026) · [The 2026 Draft Tax Bills Are Out. Comment Closes 28 August — Accounting Weekly](https://www.accountingweekly.com/sars-updates/2026-draft-tlab-and-talab-what-accountants-must-know) · [2026 draft TLAB: Key changes for businesses — PvdZ Consulting](https://tax.pvdz.co.za/tlab/) · [SARS Tax Tables 2026/2027: Brackets, Rates and Rebates — Xero ZA](https://www.xero.com/za/guides/sars-tax-tables-2026/) · [SARS Tax Tables 2026/2027 — Accounter](https://accounter.co.za/news/sars-tax-tables-2026-2027) · [Tax Brackets South Africa 2026/2027 — Tax Planners](https://taxplanners.co.za/tax-brackets-south-africa/)

## 8. Action items

1. **Critical (security, out-of-scope but urgent, carried over unresolved):** `C:\Zuzan\ghp_w0vWd0jgV1yFdHb9NODeqLMx5jlKOz3.txt` still contains what appears to be a live GitHub personal access token in plaintext in the project root, untracked. Recommend revoking it in GitHub settings and deleting the file; check git history in case it was ever committed.
2. **High (NEW this run):** the multi-line invoice-items feature (`App_js_fixed.js:899-1090`, `companies.py:392-396`) does not make the backend's VAT calculation respect per-line `vat_applicable` flags — every invoice is charged flat 15% (or the manual foreign-currency override) on the whole subtotal, regardless of which lines were marked VAT-exempt in the UI. Recommend either removing the per-line VAT checkbox until the backend honours it, or having `create_invoice`/`update_invoice` derive `vat_amount`/`total_amount` from `items_json` when present. Also note the "Pick from Catalog" shortcut (`:927-937`) can silently overwrite `data.amount`/`vatApplicable` out from under an in-progress line-items table — the two entry modes should be mutually exclusive or reconciled.
3. **High (carried over, unfixed):** expense "Account" dropdown value (`"{code} - {name}"`) doesn't match `CATEGORY_TO_CODE`'s bare-name keys in `journal.py:88-149`, so manually-entered expenses AND bank-import-categorised expenses (`companies.py:1252-1319`) both post to account 5900 "General Expenses" regardless of the account selected in the UI. Recommend `expense_account()` parse the leading code from `category` and look up `Account` by code directly (see §2).
4. **Medium (carried over):** `/reports/cash-flow-13week` (`payroll.py:1991-2098`) still does not model outstanding creditor (PO) payments or VAT201 liabilities as distinct weekly outflows (`other_payments`/`vat_payment` hard-coded `0.0`).
5. **Low (carried over):** the `/coa` custom-account feature lets users add accounts to the `CompanyAccount` table and select them in expense dropdowns, but nothing in `journal.py` posts to a custom account by code. Remains effectively decorative until item 3 is fixed the recommended way.
6. **Low (observation, not yet a defect):** the cosmetic comment/statement-duplication artifact continued to grow with this run's commits — `main.py`'s disabled-middleware comment line and `billing.py`'s repeated `resp = None` (`adhoc_charge()`) both grew by one more duplicated line/comment segment per commit. Still harmless (dead code / redundant assignment), but worth a cleanup pass given it's now actively accumulating again.

**Standing reminders (not defects, carried from prior reports):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry (`payroll.py`) after Budget Feb 2027 and restart the backend;
(b) early-2027 runs should execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`);
(c) the AFS PayFast payment/ad-hoc tokenization feature and the `/reports/ai-insights` feature remain outside this audit's scope;
(d) NBCPSS private security payroll mode predates this audit's baseline, not yet part of this checklist's explicit scope;
(e) file-attribution note: the imported-equity-offset (3998/3999) exclusion logic lives in `payroll.py`'s `balance_sheet()`, not `financial_statements.py`;
(f) 2026 draft TLAB/TALAB comment period closed on schedule 28 August 2026 with no bill finalisation news yet as of this run — next run should keep checking for Treasury's review outcome or Parliamentary introduction;
(g) `parent_company_id`/`user_type` columns and bookkeeper-onboarding/consolidated-billing/accountant-fee-structure features remain outside Reports/Debtors/Creditors/AFS/tax scope, awareness only;
(h) legacy unused constants `PAYROLL_PER_EMP = 34.00` / `PAYROLL_MIN = 99.00` in `payroll.py` — still worth a cleanup pass, not a compliance issue;
(i) the 13-week cash-flow forecast feature (`payroll.py:1991-2098`, `ForecastView` in `App_js_fixed.js`) remains additive and outside the original checklist's endpoint list — tracked via action item 4;
(j) compulsory VAT-registration turnover threshold rises to R2,300,000 (from R1,000,000), voluntary to R120,000 (from R50,000), effective 1 April 2026 — not gated anywhere in-scope, awareness only;
(k) the persistent Chart of Accounts feature (`/coa` router in `companies.py`, `CompanyAccount` in `database.py`, `ChartOfAccounts`/`Expenses` components in `App_js_fixed.js`) is additive and outside the original checklist's endpoint list — tracked via action items 3 and 5 until resolved;
(l) NEW — the invoice header-image upload, custom HTML invoice template (`Company.invoice_template_html`), and service-item catalogue (`ServiceItem`) introduced 2026-08-29 are additive presentation/picklist features outside the original checklist's endpoint list, tracked via action item 2 for the one defect found in them; the catalogue and template rendering themselves (picklist CRUD, `{{placeholder}}` substitution) were reviewed and found correct.
