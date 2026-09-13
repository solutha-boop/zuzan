# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 12 September 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-09-11 (PASS; no defects found in-scope; one carried-over Critical security item, out of scope).

**Change detection since last run:** `git log --since="2026-09-11 00:00"` on `main` shows **zero new commits** — `HEAD` is still `e44fb1b` (10 Sep 2026, 21:18), same as the 09-11 audit's baseline. `git status --short` confirms no changes to any tracked file; only the same set of pre-existing untracked residue is present (`ghp_w0vWd0jgV1yFdHb9NODeqLMx5jlKOz3.txt`, `companies_py_fixed.py`, `cleanup_untracked.bat`, `netlify-drop/`, `LAUNCH_READINESS_2026-07-14.md`, `zuzan-backend/.fuse_hidden*` temp-editor artifacts). `payroll.py`, `journal.py`, `purchase_orders.py`, `companies.py`, `database.py`, `financial_statements.py`, `integrations.py`, `csv_import.py`, `accountant.py`, `main.py`, `billing.py` are all byte-identical to 09-11.

Because the codebase is genuinely unchanged, this run re-verified every in-scope anchor directly via `Grep`/`Read` (not `bash cat`, per the stale-mount pitfall) rather than re-deriving each section from scratch, and re-ran the tax/IFRS web searches fresh. One correction to the prior report surfaced during re-verification: see Action Item 2.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ✅ PASS — unchanged, re-verified |
| Debtors (AR) | ✅ PASS — unchanged, re-verified |
| Creditors (AP) | ✅ PASS — unchanged, re-verified |
| Cross-module consistency | ✅ PASS — unchanged, re-verified |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) unchanged; no standards changes since 09-11 |
| Tax updates (SARS) | ✅ PASS — 2026/2027 tables current, no rate changes |

**Overall: PASS.** No new defects found. No commits landed since the last audit, so all previously-fixed items remain fixed. One reporting correction: the `billing.py` `resp = None` duplicate-line pattern flagged as "nine lines deep" in the 09-11 report is actually **74 lines** (`billing.py:465-538`) — an undercount in that prior report, not a regression since then (the file itself has not changed). See Action Item 2. One Critical security item (leaked GitHub token file) remains unresolved and out of this audit's technical scope.

## 2. Reports

✓ No issues found. Re-verified against current file contents (all line anchors unmoved since 09-06):

- `total_revenue` sums only paid invoices via `_to_zar()` (`payroll.py:1238`); `total_outstanding` covers outstanding invoices via `_to_zar()` (`payroll.py:1246`).
- Expenses excluded from revenue — separate accumulator; `gross_profit = total_revenue - total_expenses` (`payroll.py:1288`, unchanged).
- PO costs added once via `_po_delivered_net()`, no double count. Payroll costs included in expense totals.
- Management-accounts revenue trend (`payroll.py:2281`) and `/v1/summary` (`main.py:461,491`) apply `_to_zar()` consistently.
- 14 `_to_zar()` call sites confirmed present in `payroll.py` at lines 18 (def), 1238, 1246, 1398, 1631, 1643, 1726, 1855, 1918, 2056, 2189, 2264, 2281, 2456, 2569 — matches 09-11 exactly.

## 3. Debtors

✓ No issues found. Re-verified against current file contents (unchanged since 09-10 fixes):

- `_resolve_currency_and_rate()` (`integrations.py:167-186`) still requires an explicit, positive `exchangeRate` for any `currency != "ZAR"` SMT invoice, raising 422 if missing — mirrors `csv_import.py:455-487`.
- The update path (`integrations.py:232-256`) still blocks amount/vat/total changes on invoices already `status == paid`, raising 409 — mirrors `companies.py:545-549`.
- Paid-invoice exclusion, aging-by-`due_date` (`payroll.py:1629,1644,2053-2054`), and ZAR-equivalent display logic are unchanged and correct.

## 4. Creditors

✓ No issues found. Re-verified against current file contents (unchanged since 09-09):

- Outstanding = received/partial POs plus unpaid on-credit expenses; fully paid POs excluded.
- Reversal-aware AP balance nets `credit − debit` and includes `source == "purchase_order"` / `"purchase_order_reversal"` — confirmed present and unchanged at `payroll.py:1779`, `payroll.py:2645`, `purchase_orders.py:445`, `journal.py:868`, `financial_statements.py:558`.
- Supplier bank details decrypted via `decrypt_field()` before display — unchanged.

## 5. Cross-module consistency

✓ No issues found. Re-verified — unchanged since 09-10/09-11:

- `_delete_existing_journals` (`integrations.py:135-148`) still filters `JournalEntry.source == "invoice"`, matching `post_invoice_raised` (`journal.py:230,742`) and `companies.py:508` — re-posts correctly delete-then-repost, no duplication.
- Journal coverage complete: `post_invoice_raised`, `post_invoice_paid`, `post_invoice_cogs`, `post_expense`, `post_bank_income`, `post_payroll`, `post_expense_paid`, `post_po_received`, `post_po_paid`, `post_stock_adjustment`, `post_asset_acquisition`, `post_depreciation`, `post_asset_disposal` — all present in `journal.py`.
- Import-awareness (2026-07-11 fixes) intact: non-ZAR rows in `csv_import.py`'s invoice import still require an explicit exchange rate and are rejected without one (`csv_import.py:455-487`).
- `POST /accountant/sync-customers` (`accountant.py:199-243`) re-confirmed to only touch `Customer.name/email/phone`, no `Invoice`/`PurchaseOrder`/`JournalEntry` impact.
- Balance sheet Debtors Control / Creditors Control reconciliation logic unchanged.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (`financial_statements.py` docstring; AFS meta `"basis": "IFRS for SMEs"`). File unchanged since 08-26; re-verified rather than re-derived.

**Standards status (fresh web search this run, 12 September 2026):**
- IFRS 18 *Presentation and Disclosure in Financial Statements* — still effective for annual periods beginning on/after 1 January 2027, early application permitted; not yet applicable to IFRS-for-SMEs preparers. No change.
- IFRS for SMEs third edition — still effective 1 January 2027 (issued 27 Feb 2025); 2015 edition remains permitted until then. No change.
- IASB Exposure Draft *Consolidation Exception* — comment period closed 9 September 2026. Fresh search confirms **no final amendment issued yet**; IASB's stated plan remains to issue any amendment by end of 2026, effective 1 January 2027 if approved, aligned with the SME 3rd-edition effective date. No change since 09-11. Not relevant to ZuZan (no consolidation requirement in scope) — continuing to track.

**Section 5b — deferred tax:** already implemented (not hard-coded to `0.0`); re-verified this run at the code level (file unchanged, anchors unmoved):
- `_deferred_tax_balance()` (`financial_statements.py:131`) computes per-asset tax base via `wear_and_tear_rate` (SARS IN47 category mapping, priority order documented at `:107-110`).
- Opening/closing deferred tax balances drive `deferred_tax_expense` (`financial_statements.py:266-268`).
- `total_tax` combines current + deferred (`:601`); Note 9 fields (`deferred_tax`, `deferred_tax_opening_balance`, `deferred_tax_closing_balance`) populated (`:606,609-610`); `deferred_tax_movement` disclosed at `:681`.
- Balance-sheet closing balance carries the matching retained-earnings adjustment so Assets = Equity + Liabilities still holds (unchanged).

Finance costs (2026-07-13 fix): interest-below-EBIT split and tax/net-profit derivation from `profit_before_tax`, not EBIT, re-confirmed present and unchanged.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date, present at `payroll.py:132-146`. `payroll.py` unchanged since 09-06.

- Re-confirmed at code level: PAYE brackets 18%–45% across seven brackets (`payroll.py:133-141`), primary rebate R17,820 (`:142`), secondary rebate R9,765 (`:143`), tertiary rebate R3,249 (`:144`), UIF ceiling R17,712/month (`:145`) at 1% employee + 1% employer (`UIF_RATE = 0.01`, `:189`), SDL 1% employer-only. Selector `_current_tax_year()` (`:170-181`) correctly resolves to `"2026/2027"` for the 12 Sept 2026 run date. No discrepancy found against currently published SARS 2026/2027 tables.
- CIT remains flat 27% — matches all in-code usages (`financial_statements.py`, `payroll.py:2446 CORP_TAX_RATE`). No CIT rate change found for the 2026/2027 year of assessment.
- VAT standard rate confirmed unchanged at 15% (`payroll.py:1609,2802`). The Constitutional Court case on Section 7(4) of the VAT Act (whether the Finance Minister's power to set the VAT rate without prior Parliamentary approval is unconstitutional) **remains at "judgment reserved"** as at this run's date — heard 27 August 2026, no ruling issued yet per fresh web search (12 September 2026). No rate change; no code impact. Continue monitoring.
- 2026 draft TLAB/TALAB: public comment period closed 28 August 2026; still under Treasury/SARS review, not yet introduced to Parliament as at this run. No provisions affecting PAYE brackets, CIT, or VAT rate identified in the published drafts. No code impact.
- No edits made to tax tables (report-only per task rules; §5b was verification-only this run, already implemented in a prior run).

**Sources consulted:** [VAT Act section declared invalid — The Citizen](https://www.citizen.co.za/news/south-africa/courts/vat-act-section-declared-invalid-unconstitutional/) · [Sars and Treasury ask top court to overturn ruling on minister's VAT powers — Business Day](https://www.businessday.co.za/news/2026-08-28-sars-and-treasury-ask-top-court-to-overturn-ruling-on-ministers-vat-powers/) · [ConCourt reserves judgment on Finance Minister's power to change VAT rate — eNCA](https://www.enca.com/news-top-stories/concourt-reserves-judgment-finance-ministers-power-change-vat-rate) · [List of judgments of the Constitutional Court of South Africa delivered in 2026 — Wikipedia](https://en.wikipedia.org/wiki/List_of_judgments_of_the_Constitutional_Court_of_South_Africa_delivered_in_2026) · [IFRS - IASB proposes extending consolidation exception for eligible SMEs](https://www.ifrs.org/news-and-events/news/2026/05/iasb-proposes-extending-consolidation-exception-eligible-smes/) · [IFRS for SMEs Accounting Standard—Consolidation Exception work plan](https://www.ifrs.org/projects/work-plan/ifrs-for-smes-accounting-standard-consolidation-exception/) · [National Treasury Publishes 2026 Draft Tax Bills for Public Comment — Tax Consulting South Africa](https://www.taxconsulting.co.za/national-treasury-publishes-2026-draft-tax-bills-for-public-comment/) · [National Treasury on publication of the 2026 draft tax bills for comment — gov.za](https://www.gov.za/news/media-statements/national-treasury-publication-2026-draft-tax-bills-comment-30-jul-2026)

## 8. Action items

1. **Critical (security, out-of-scope but urgent, carried over unresolved):** `C:\Zuzan\ghp_w0vWd0jgV1yFdHb9NODeqLMx5jlKOz3.txt` still contains what appears to be a live GitHub personal access token in plaintext in the project root, untracked. Recommend revoking it in GitHub settings and deleting the file; check git history in case it was ever committed.
2. **Medium (correction to prior report, not a new regression):** `billing.py`'s `resp = None` duplicate-line pattern (`billing.py:465-538`, inside the PayFast ad-hoc charge function, immediately before the real assignment at `:540`) is **74 lines**, not the "nine lines" stated in the 09-11 report — that was an undercount in that report, confirmed this run via direct `Grep`/`Read` against the actual committed file (`git show HEAD:zuzan-backend/billing.py`, unchanged since the 09-10 21:18 commit). Functionally harmless (all no-ops overwritten before use), but worth a cleanup pass, and worth checking whether the commit-generation tooling itself has a bug producing this duplication — the magnitude (74 lines) suggests the bug may be worse than previously tracked.
3. **Medium (carried over):** `/reports/cash-flow-13week` (`payroll.py:1991-2098`, unchanged) still does not model outstanding creditor (PO) payments or VAT201 liabilities as distinct weekly outflows.
4. **Low (carried over):** `POST /accountant/sync-customers` (`accountant.py:199-243`) auto-creates `Customer` rows for linked client companies with no user-facing indication in the Debtors/Customers UI that a given customer was auto-created vs. manually added — worth a UX follow-up (e.g. a "linked client" badge).
5. **Low (carried over):** with the expense-account routing fix in place (fixed 2026-09-06), custom `/coa` accounts should resolve correctly via the numeric-code path in `expense_account()` — still recommend a quick functional test adding one custom account and posting an expense against it to confirm end-to-end.
6. **Low (carried over, unchanged):** untracked stray file `C:\Zuzan\companies_py_fixed.py` (55KB, ~1,133 lines) sits alongside the active `zuzan-backend/companies.py` and diverges substantially — still unreferenced anywhere in the active codebase. Repo clutter worth deleting alongside other untracked residue (`cleanup_untracked.bat`, `.fuse_hidden*` files, `netlify-drop/`).

**Standing reminders (not defects, carried from prior reports):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry (`payroll.py`) after Budget Feb 2027 and restart the backend;
(b) early-2027 runs should execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`);
(c) the AFS PayFast payment/ad-hoc tokenization feature and the `/reports/ai-insights` feature remain outside this audit's scope;
(d) NBCPSS private security payroll mode predates this audit's baseline, not yet part of this checklist's explicit scope;
(e) file-attribution note: the imported-equity-offset (3998/3999) exclusion logic lives in `payroll.py`'s `balance_sheet()`, not `financial_statements.py`;
(f) next run should keep checking for Treasury's review outcome or Parliamentary introduction of the 2026 draft TLAB/TALAB (public comment closed 28 August 2026; under Treasury/SARS review as at this run);
(g) `parent_company_id`/`user_type` columns, bookkeeper-onboarding, consolidated-billing, accountant-fee-structure, and the accountant-practice-dashboard/`billing_exempt` features remain outside Reports/Debtors/Creditors/AFS/tax scope, awareness only;
(h) the 13-week cash-flow forecast feature remains additive and outside the original checklist's endpoint list — tracked via action item 3;
(i) compulsory VAT-registration turnover threshold is R2,300,000 (voluntary R120,000), effective 1 April 2026 — not gated anywhere in-scope, awareness only;
(j) the persistent Chart of Accounts feature (`/coa` router, `CompanyAccount`, `ChartOfAccounts`/`Expenses` components) is additive and outside the original checklist's endpoint list — tracked via action item 5;
(k) the invoice header-image upload, custom HTML invoice template, and service-item catalogue introduced 2026-08-29 remain additive presentation/picklist features outside the original checklist's endpoint list;
(l) the IASB's SME consolidation-exception Exposure Draft comment period closed 9 September 2026 — no final amendment published yet as at this run; check the next run for a post-close update;
(m) the Constitutional Court has reserved judgment (heard 27 August 2026) on whether Section 7(4) of the VAT Act, 1991 is unconstitutional. No rate change and no ruling yet; monitor for the judgment and any resulting change to how a future VAT rate change would need to be legislated/timed;
(n) the `/integrations/invoice` (SMT) endpoint remains formally in-scope going forward — once real SMT traffic exists, spot-check with an actual create + re-post cycle (including a deliberate non-ZAR and a deliberate paid-invoice re-post) if test data is available;
(o) `POST /accountant/sync-customers` (`accountant.py`) remains tracked going forward given its proximity to Debtors scope (see action item 4).
