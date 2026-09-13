# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 13 September 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-09-12 (PASS; one carried-over Critical security item, one Medium reporting correction, three other carried-over items).

**Change detection since last run:** `git log` on `main` shows **zero new commits** since `e44fb1b` (10 Sep 2026, 21:18) — same HEAD as 09-12. However, `git status --short` now shows **three tracked files with uncommitted working-tree edits**: `App_js_fixed.js`, `zuzan-backend/billing.py`, `zuzan-backend/payroll.py`. `git diff` (cross-checked against direct `Read` of the same line ranges, per the stale-mount pitfall — both agreed) shows these are targeted fixes for three of the 09-12 report's carried-over action items, applied after that report was written but not yet committed/pushed:

- **Action item 3 (13-week cash flow):** `payroll.py` gained a new `_vat_net_for_month()` helper and `cash_flow_13week()` now sources real `creditor_payments` (open POs + on-credit expenses, reversal-aware AP lookup on account 2000, supplier `payment_terms`-based due dates) and `vat_payment` (projected VAT201 net liability due on the 25th of the following month) instead of hard-coding both to `0.0`. `App_js_fixed.js`'s `Budgeting` component was updated to include `creditor_payments` in its running-balance calc, CSV export, and chart series.
- **Action item 2 (billing.py duplicate lines):** the 73 duplicate `resp = None` lines in `adhoc_charge()` (previously `billing.py:465-538`) have been removed; the function now has a single `resp = None` at line 465.
- **Action item 4 (linked-client badge):** `App_js_fixed.js`'s `Customers` component now renders a "🔗 Linked client" badge when `c.notes === "Auto-created from linked client company"`, matching the string `accountant.py:224` already writes for auto-created customers.

All three fixes were verified correct at the code level (see §2 and Action Items below). `financial_statements.py`, `journal.py`, `purchase_orders.py`, `companies.py`, `database.py`, `integrations.py`, `csv_import.py`, `accountant.py`, `main.py` are untouched and byte-identical to 09-12 (re-verified via `Grep`/`Read`, not `bash cat`).

Also since 09-12: the previously-flagged stray files are gone — `C:\Zuzan\ghp_w0vWd0jgV1yFdHb9NODeqLMx5jlKOz3.txt` (leaked GitHub token) and `C:\Zuzan\companies_py_fixed.py` no longer exist in the working tree. `cleanup_untracked.bat` and `netlify-drop/` are also gone. This resolves the Critical security item and the Low repo-clutter item from every prior report.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary / cash-flow-13week) | ✅ PASS — cash-flow-13week fix verified correct |
| Debtors (AR) | ✅ PASS — unchanged, re-verified |
| Creditors (AP) | ✅ PASS — unchanged, re-verified |
| Cross-module consistency | ✅ PASS — unchanged, re-verified |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) unchanged; no standards changes since 09-12 |
| Tax updates (SARS) | ✅ PASS — 2026/2027 tables current, no rate changes |

**Overall: PASS.** No defects found. The Critical security item (leaked token file) and the repo-clutter Low item are both **resolved** since 09-12. Three carried-over action items (billing.py duplication, 13-week forecast creditor/VAT gaps, linked-client badge) have been **fixed**, verified correct, but remain **uncommitted** — see Action Item 1.

## 2. Reports

✓ No issues found.

- `total_revenue` sums only paid invoices via `_to_zar()` (`payroll.py:1238`) plus `_bank_import_income()` (`:1240`, pre-existing, journal-sourced, explicitly documented to avoid double-counting with invoice revenue); `total_outstanding` covers outstanding invoices via `_to_zar()` (`:1246`).
- Expenses excluded from revenue; PO costs added once via `_po_delivered_net()`; payroll costs included in expense totals — unchanged (`payroll.py:1248-1290`).
- Management-accounts revenue trend loop (`payroll.py:2429-2433`) and `/v1/summary` (`main.py:461,491`) apply `_to_zar()` (and `_bank_import_income()` for the trend) consistently.
- **New this run — `/reports/cash-flow-13week` fix verified correct** (`payroll.py:1991-2246`): `creditor_payments` now sums open PO balances (reversal-aware: nets `credit − debit` on account 2000, includes `source in ("purchase_order", "purchase_order_reversal")` — mirrors `creditors-aging` exactly) plus unpaid on-credit expenses, bucketed by due date into the 13 weekly windows. `vat_payment` now projects each month's net VAT201 liability (output VAT from issued/paid invoices minus expense + delivered-PO input VAT, mirroring `/reports/vat201`'s own methodology) and places it in the week containing the 25th of the following month, floored at 0 (a projected refund is not shown as a negative outflow). Both fields are additive to the weekly totals; `App_js_fixed.js`'s `Budgeting` component was updated in lockstep (running balance, CSV export, chart legend) to include `creditor_payments` — confirmed no other consumer of this endpoint was missed via `Grep` for `cash-flow-13week` and `creditor_payments` across `App_js_fixed.js`.

## 3. Debtors

✓ No issues found. Re-verified against current file contents (unchanged since 09-10 fixes):

- `_resolve_currency_and_rate()` (`integrations.py:167-186`) still requires an explicit, positive `exchangeRate` for any `currency != "ZAR"` SMT invoice, raising 422 if missing.
- The update path (`integrations.py:232-256`) still blocks amount/vat/total changes on invoices already `status == paid`, raising 409.
- `/reports/debtors-aging` (`payroll.py:2694-2754`) ages strictly from `due_date` (no issue_date/created_at fallback — undated invoices land in a separate `not_due` bucket rather than falsely inflating overdue totals), buckets are current/31-60/61-90/over_90, amounts are `_to_zar()`-converted, and only `sent`/`overdue` invoices are queried (paid excluded).

## 4. Creditors

✓ No issues found. Re-verified against current file contents:

- `/reports/creditors-aging` (`payroll.py:2757-2833`+) pulls received/partial POs plus unpaid on-credit expenses; fully paid POs excluded by the status filter.
- Reversal-aware AP balance confirmed present and unchanged at all cited sites: `payroll.py:1779`, `payroll.py:2793` (creditors-aging; line shifted from 09-12's `:2645` due to the ~156-line insertion earlier in the file for the cash-flow-13week fix — same code, renumbered), the **new** `payroll.py:2122` (cash-flow-13week's own creditor-due lookup, built to the same pattern), `purchase_orders.py:445`, `journal.py:868`, `financial_statements.py:558` — all net `credit − debit` and include `source in ("purchase_order", "purchase_order_reversal")`.
- Supplier bank details decrypted via `decrypt_field()` before display (`payroll.py:2836-2838`, `suppliers.py:48-50`).

## 5. Cross-module consistency

✓ No issues found. Re-verified:

- Journal coverage complete in `journal.py`: `post_invoice_raised` (:214), `post_invoice_paid` (:254), `post_invoice_cogs` (:288), `post_expense` (:313), `post_bank_income` (:348), `post_payroll` (:388), `post_expense_paid` (:467), `post_po_received` (:496), `post_po_paid` (:548), `post_stock_adjustment` (:576), `post_asset_acquisition` (:617), `post_depreciation` (:643), `post_asset_disposal` (:670) — all present, no gaps.
- Import-awareness (2026-07-11 fixes) intact: non-ZAR rows in `csv_import.py`'s invoice import still require an explicit exchange rate (`csv_import.py:455-487`).
- `POST /accountant/sync-customers` (`accountant.py:199-243`) still only touches `Customer.name/email/phone` plus the new `notes="Auto-created from linked client company"` marker (`:224`, added to support the linked-client badge — see Action Item 3 below) — no `Invoice`/`PurchaseOrder`/`JournalEntry` impact.
- Balance sheet Debtors Control / Creditors Control reconciliation logic unchanged.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (`financial_statements.py` docstring; AFS meta `"basis": "IFRS for SMEs"`). File unchanged since 08-26.

**Standards status (fresh web search this run, 13 September 2026):**
- IFRS 18 *Presentation and Disclosure in Financial Statements* — still effective for annual periods beginning on/after 1 January 2027, early application permitted; not yet applicable to IFRS-for-SMEs preparers. No change.
- IFRS for SMEs third edition (issued Feb 2025) — still effective 1 January 2027; 2015 edition remains permitted until then; full retrospective application required under Section 10 with built-in transition reliefs. No change since 09-12.
- IASB Exposure Draft *Consolidation Exception* — comment period closed 9 September 2026 (confirmed by this run's fresh search). IASB's plan remains to issue any amendment by end of 2026, effective 1 January 2027 with early adoption permitted, if approved. No final amendment issued yet. Not relevant to ZuZan (no consolidation requirement in scope) — continuing to track per prior reports.

**Section 5b — deferred tax:** already implemented (not hard-coded to `0.0`); re-verified this run at the code level (file unchanged, anchors unmoved):
- `_deferred_tax_balance()` (`financial_statements.py:131`) computes per-asset tax base via `wear_and_tear_rate` (SARS IN47 category mapping, priority order documented at `:107-110`).
- Opening/closing deferred tax balances drive `deferred_tax_expense` (`:266-268`); `total_tax` combines current + deferred (`:601`); Note 9 fields populated (`:606,609-610`); `deferred_tax_movement` disclosed at `:681`.
- Balance-sheet closing balance carries the matching retained-earnings adjustment so Assets = Equity + Liabilities still holds.

Finance costs (2026-07-13 fix): interest lines (account 6700 or name-matched) confirmed presented below EBIT (`financial_statements.py:205-211`); `profit_before_tax = ebit - finance_costs` (`:259`) and tax/net-profit derive from `profit_before_tax`, not EBIT (`:260-261`) — unchanged.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date, present at `payroll.py:132-146`. `payroll.py`'s tax tables are unchanged by today's diff (only the cash-flow-13week section was touched).

- PAYE brackets 18%–45% across seven brackets (`payroll.py:133-141`) confirmed against a fresh web search this run: primary rebate R17,820 (`:142`) ✓, secondary rebate R9,765 (`:143`) ✓, tertiary rebate R3,249 (`:144`) ✓ — all match currently published SARS 2026/2027 tables. UIF ceiling R17,712/month (`:145`, `:130` for prior year) ✓ matches, at 1% employee + 1% employer (`UIF_RATE = 0.01`, `:189`) ✓. SDL 1% employer-only (`SDL_RATE = 0.01`, `:190`) — standard, unchanged. `_current_tax_year()` (`:170-181`) correctly resolves to `"2026/2027"` for the 13 Sept 2026 run date.
- CIT remains flat 27% — single source of truth `fixed_assets.SA_CIT_RATE` (`fixed_assets.py:78`), consumed by `financial_statements.py:82-84` and `payroll.py:2594` (`CORP_TAX_RATE`). No CIT rate change found for the 2026/2027 year of assessment.
- VAT standard rate confirmed unchanged at 15% across every hard-coded site checked: `companies.py:289`, `payroll.py:1609,2003,2950`, `quotes.py:15`. The Constitutional Court case on Section 7(4) of the VAT Act (Finance Minister's power to set the VAT rate without prior Parliamentary approval) **remains at "judgment reserved"** as at this run's date (heard 27 August 2026; fresh search on 13 September 2026 finds no ruling issued yet). No rate change; no code impact. Continue monitoring.
- 2026 draft TLAB/TALAB: public comment period closed 28 August 2026; still under Treasury/SARS review pending finalisation and introduction to Parliament as at this run. Proposals identified (living-annuity de minimis, donations-tax spousal exemption, SEZ transfer pricing, PAYE for foreign employers, provisional-tax penalties, VDP interest relief, second-hand-goods documentation) do not affect PAYE brackets, CIT, or the VAT rate. No code impact.
- No edits made to tax tables (report-only per task rules; §5b was verification-only this run).

**Sources consulted:** [VAT Act section declared invalid — The Citizen](https://www.citizen.co.za/news/south-africa/courts/vat-act-section-declared-invalid-unconstitutional/) · [Sars and Treasury ask top court to overturn ruling on minister's VAT powers — Business Day](https://www.businessday.co.za/news/2026-08-28-sars-and-treasury-ask-top-court-to-overturn-ruling-on-ministers-vat-powers/) · [ConCourt reserves judgment on Finance Minister's power to change VAT rate — eNCA](https://www.enca.com/news-top-stories/concourt-reserves-judgment-finance-ministers-power-change-vat-rate) · [Godongwana's lawyers urge ConCourt to uphold VAT Act provisions — EWN](https://www.ewn.co.za/2026/08/27/godongwanas-lawyers-urge-concourt-to-uphold-vat-act-provisions-for-sound-fiscal-administration) · [DA wins court challenge to affirm only Parliament can change VAT rate](https://www.da.org.za/2026/03/da-wins-court-challenge-to-affirm-only-parliament-can-change-vat-rate) · [List of judgments of the Constitutional Court of South Africa delivered in 2026 — Wikipedia](https://en.wikipedia.org/wiki/List_of_judgments_of_the_Constitutional_Court_of_South_Africa_delivered_in_2026) · [IFRS - IASB proposes extending consolidation exception for eligible SMEs](https://www.ifrs.org/news-and-events/news/2026/05/iasb-proposes-extending-consolidation-exception-eligible-smes/) · [IFRS for SMEs Accounting Standard—Consolidation Exception work plan](https://www.ifrs.org/projects/work-plan/ifrs-for-smes-accounting-standard-consolidation-exception/) · [IASB proposes narrow amendment to IFRS for SMEs standard — XBRL](https://www.xbrl.org/news/iasb-proposes-narrow-amendment-to-ifrs-for-smes-standard/) · [Third edition of the IFRS for SMEs Accounting Standard — ACCA](https://www.accaglobal.com/learning-and-events/corporate-reporting/third-edition-ifrs-for-smes.html) · [National Treasury Publishes 2026 Draft Tax Bills for Public Comment — Tax Consulting South Africa](https://www.taxconsulting.co.za/national-treasury-publishes-2026-draft-tax-bills-for-public-comment/) · [National Treasury on publication of the 2026 draft tax bills for comment — gov.za](https://www.gov.za/news/media-statements/national-treasury-publication-2026-draft-tax-bills-comment-30-jul-2026) · [SARS Tax Tables 2026/2027 — Accounter](https://accounter.co.za/news/sars-tax-tables-2026-2027) · [2026/2027 Tax Year: Key Payroll Changes for SA Employers — Talentide](https://talentide.co.za/blog/2026-2027-tax-year-payroll-changes-south-africa/)

## 8. Action items

1. **High (process, new this run):** three verified-correct fixes — `payroll.py`'s cash-flow-13week `creditor_payments`/`vat_payment` (action item 3), `billing.py`'s duplicate-line cleanup (action item 2), and `App_js_fixed.js`'s linked-client badge (action item 4) — are sitting as **uncommitted working-tree changes** (`git status --short` shows `M` on all three files). Per the deploy-pipeline pitfall, `commit_and_push.bat` runs autonomously outside this audit's sandbox, but as of this run these edits have not yet been picked up (`HEAD` is still `e44fb1b` from 10 Sep). Recommend running the commit/push step (or confirming why it hasn't fired) so these fixes actually reach production rather than sitting only on disk.
2. **Critical (security) — RESOLVED:** the leaked GitHub token file (`ghp_w0vWd0jgV1yFdHb9NODeqLMx5jlKOz3.txt`) no longer exists in the project root as of this run. No further action from this audit; if it was ever committed to git history, confirm separately that the token itself was revoked in GitHub settings (out of this audit's technical scope to verify).
3. **Low (repo clutter) — RESOLVED:** `companies_py_fixed.py`, `cleanup_untracked.bat`, and `netlify-drop/` are all gone from the working tree.
4. **Medium (carried over, unaffected by today's fix):** even with the 13-week forecast now modeling `creditor_payments` and `vat_payment`, the forecast still does not model provisional tax (IRP6) payments as a distinct weekly outflow — worth a follow-up if provisional tax becomes a tracked liability elsewhere in the app.
5. **Low (carried over):** with the expense-account routing fix in place (2026-09-06), custom `/coa` accounts should resolve correctly via the numeric-code path in `expense_account()` — still recommend a quick functional test adding one custom account and posting an expense against it to confirm end-to-end.

**Standing reminders (not defects, carried from prior reports):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry (`payroll.py`) after Budget Feb 2027 and restart the backend;
(b) early-2027 runs should execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`);
(c) the AFS PayFast payment/ad-hoc tokenization feature and the `/reports/ai-insights` feature remain outside this audit's scope;
(d) NBCPSS private security payroll mode predates this audit's baseline, not yet part of this checklist's explicit scope;
(e) file-attribution note: the imported-equity-offset (3998/3999) exclusion logic lives in `payroll.py`'s `balance_sheet()`, not `financial_statements.py`;
(f) next run should keep checking for Treasury's review outcome or Parliamentary introduction of the 2026 draft TLAB/TALAB (public comment closed 28 August 2026; under Treasury/SARS review as at this run);
(g) `parent_company_id`/`user_type` columns, bookkeeper-onboarding, consolidated-billing, accountant-fee-structure, and the accountant-practice-dashboard/`billing_exempt` features remain outside Reports/Debtors/Creditors/AFS/tax scope, awareness only;
(h) the 13-week cash-flow forecast feature's creditor/VAT modeling was completed this run (action item 4→now resolved per §2); provisional tax remains the only known gap (tracked via new action item 4 above);
(i) compulsory VAT-registration turnover threshold is R2,300,000 (voluntary R120,000), effective 1 April 2026 — not gated anywhere in-scope, awareness only;
(j) the persistent Chart of Accounts feature (`/coa` router, `CompanyAccount`, `ChartOfAccounts`/`Expenses` components) is additive and outside the original checklist's endpoint list — tracked via action item 5;
(k) the invoice header-image upload, custom HTML invoice template, and service-item catalogue introduced 2026-08-29 remain additive presentation/picklist features outside the original checklist's endpoint list;
(l) the IASB's SME consolidation-exception Exposure Draft comment period closed 9 September 2026 — no final amendment published yet as at this run; check the next run for a post-close update;
(m) the Constitutional Court has reserved judgment (heard 27 August 2026) on whether Section 7(4) of the VAT Act, 1991 is unconstitutional. No rate change and no ruling yet; monitor for the judgment and any resulting change to how a future VAT rate change would need to be legislated/timed;
(n) the `/integrations/invoice` (SMT) endpoint remains formally in-scope going forward — once real SMT traffic exists, spot-check with an actual create + re-post cycle (including a deliberate non-ZAR and a deliberate paid-invoice re-post) if test data is available;
(o) `POST /accountant/sync-customers` (`accountant.py`) remains tracked going forward given its proximity to Debtors scope — the "Linked client" badge (this run's fix) closes the prior UX-visibility gap noted here.
