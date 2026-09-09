# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 9 September 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-09-08 (PASS; unchanged from 09-07; one carried-over Critical security item, out of scope).

**Change detection since last run:** `git log --since="2026-09-08 00:00"` shows **zero new commits**. HEAD is unchanged at `415306e93bddbd668afe24a30f65cb67a283881a` (2026-09-06 21:06:58 +0200). `git status` confirms no staged/unstaged changes to tracked files.

Because the codebase is byte-identical to the 2026-09-08 run, every in-scope file/line anchor from that report was spot-verified against current file contents (via `Grep`, not `bash cat`, per the stale-mount pitfall) rather than re-derived from scratch — all anchors matched exactly (`payroll.py`, `journal.py`, `purchase_orders.py`, `financial_statements.py`, `database.py`, `companies.py`, `fixed_assets.py`). This run's incremental work was: (a) confirming no drift in those anchors, and (b) fresh web searches for the two areas that can change independently of the code — IFRS standards status and SARS/VAT-Act legal status — since even an unchanged codebase can go stale against external rules.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ✅ PASS — unchanged, re-verified |
| Debtors (AR) | ✅ PASS — unchanged, re-verified |
| Creditors (AP) | ✅ PASS — unchanged, re-verified |
| Cross-module consistency | ✅ PASS — unchanged, re-verified |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) unchanged; no standards changes |
| Tax updates (SARS) | ✅ PASS — 2026/2027 tables current, no rate changes; VAT-Act constitutional case still reserved |

**Overall: PASS. No code changes since the last run; no external rule changes found either.** One Critical security item (leaked GitHub token file) remains unresolved and out of this audit's technical scope — see Action Items.

## 2. Reports

✓ No issues found. Re-verified against current file contents (all line anchors unmoved):

- `total_revenue` sums only paid invoices via `_to_zar()`, plus bank-import income (`payroll.py:1238-1240`).
- `total_outstanding` covers outstanding invoices via `_to_zar()` (`payroll.py:1246`).
- Expenses excluded from revenue (`payroll.py:1288` computes `gross_profit = total_revenue - total_expenses` — expenses are a separate accumulator, never folded into revenue).
- PO costs (`received`/`partial`/`paid`) added once via `_po_delivered_net()`, no double count — unchanged since 08-29.
- Payroll costs included in expense totals — unchanged since 07-15 fix.
- Management-accounts revenue trend and `/v1/summary` (`main.py`) apply `_to_zar()` consistently — both files unchanged.

## 3. Debtors

✓ No issues found.

- AR aging and outstanding-invoice queries consistently use `_to_zar(inv)` (`payroll.py:1398,1631,1643,1726,2569` — all confirmed present).
- Aging is computed from `due_date`, invoices without a due date routed to a `not_due` bucket rather than inflating overdue totals — unchanged since 09-08.
- Paid invoices excluded from outstanding/AR balances — status filter unchanged.

## 4. Creditors

✓ No issues found.

- Outstanding = received/partial POs plus unpaid on-credit expenses; fully paid POs excluded — unchanged.
- Reversal-aware AP balance nets `credit − debit` and includes `source.in_(["purchase_order","purchase_order_reversal"])` — confirmed present and unchanged at `payroll.py:1779`, `payroll.py:2645`, `purchase_orders.py:445`, `journal.py:868`, `financial_statements.py:558`.
- Supplier bank details decrypted via `decrypt_field()` before display — unchanged.

## 5. Cross-module consistency

✓ No new gaps.

- Journal coverage complete and unchanged: `post_invoice_raised` (journal.py:214), `post_invoice_paid` (:254), `post_invoice_cogs` (:288), `post_expense` (:313), `post_bank_income` (:348), `post_payroll` (:388), `post_expense_paid` (:467), `post_po_received` (:496), `post_po_paid` (:548), `post_stock_adjustment` (:576), `post_asset_acquisition` (:617), `post_depreciation` (:643), `post_asset_disposal` (:670) — all present, all confirmed via direct grep this run.
- Migration hygiene confirmed: `wear_and_tear_rate` migration sits inside the migrations list literal, not after the `for` loop (`database.py`).
- Import-awareness (2026-07-11 fixes) intact and unchanged: Rules 6/7 exclude `source == "import"`; balance sheet carries 3998/3999 imported-equity offsets; non-ZAR invoice imports still require an exchange rate; unbalanced journal-import groups still rejected.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (`financial_statements.py` docstring; AFS meta `"basis": "IFRS for SMEs"`). File unchanged since 08-26; re-verified rather than re-derived.

**Standards status (fresh web search this run, 9 September 2026):**
- IFRS 18 *Presentation and Disclosure in Financial Statements* — effective for annual periods beginning on/after 1 January 2027, early application permitted; still not applicable to IFRS-for-SMEs preparers (ZuZan's basis). No change.
- IFRS for SMEs third edition (issued 27 February 2025) — still effective 1 January 2027; the 2015 edition remains permitted until then. No change to ZuZan's basis obligations yet.
- IASB's Exposure Draft *Consolidation Exception* (published May 2026, 120-day comment window): the comment period **closed today, 9 September 2026**. Fresh search found no final amendment or outcome published yet — the IASB's stated plan is to issue any resulting amendment by end of 2026, effective 1 January 2027 if approved. Still not relevant to ZuZan (no consolidation requirement in scope). Flagged for the next run to check for a post-close outcome or ballot result.

**Section 5b — deferred tax:** already implemented (not hard-coded to `0.0`); re-verified this run at the code level (file unchanged, anchors unmoved):
- `_deferred_tax_balance()` (`financial_statements.py:131`) computes per-asset tax base via `wear_and_tear_rate` (SARS IN47 category mapping, `fixed_assets.py`).
- Opening/closing deferred tax balances drive `deferred_tax_expense` (`financial_statements.py:266-268`).
- `total_tax` combines current + deferred (`:601`); Note 9 fields (`deferred_tax`, `deferred_tax_opening_balance`, `deferred_tax_closing_balance`) populated (`:606-610`).
- Balance-sheet closing balance carries the matching retained-earnings adjustment so Assets = Equity + Liabilities still holds.

Finance costs (2026-07-13 fix): interest-below-EBIT split and tax/net-profit derivation from `profit_before_tax`, not EBIT, re-confirmed present and unchanged.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date, present at `payroll.py:132`. `payroll.py` unchanged since 09-06.

- Re-confirmed at code level and cross-checked via fresh web search this run: PAYE brackets 18%–45% across seven brackets, primary rebate R17,820, secondary R9,765, tertiary R3,249, UIF ceiling R17,712/month at 1% employee + 1% employer, SDL 1% employer-only — all match current published SARS 2026/2027 tables. No discrepancy found. Fresh search also surfaced downstream Budget 2026 changes (higher tax-free threshold, retirement contribution cap, TFSA limit, CGT exclusions, fuel levy, excise duties) — none of these fall within this audit's in-scope endpoints (PAYE brackets/rebates/UIF/SDL, CIT, VAT), so no code impact; noted for awareness only.
- CIT remains flat 27% — matches all in-code usages (`financial_statements.py`, `fixed_assets.py:78 SA_CIT_RATE`, `payroll.py:2446 CORP_TAX_RATE`). No CIT rate change found for the 2026/2027 year of assessment.
- VAT standard rate confirmed unchanged at 15% (`companies.py:289`, `payroll.py:1609`, all `VAT_RATE = 0.15`). The Constitutional Court case on Section 7(4) of the VAT Act **remains at "judgment reserved"** as at this run's date — heard 27 August 2026, no ruling issued yet per fresh web search. No rate change; no code impact. Continue monitoring.
- No edits made to tax tables (report-only per task rules; §5b was verification-only this run, already implemented in a prior run).

**Sources consulted:** [SARS Tax Tables 2026/2027 — Xero ZA](https://www.xero.com/za/guides/sars-tax-tables-2026/) · [Accounter — SARS Tax Tables 2026/2027](https://accounter.co.za/news/sars-tax-tables-2026-2027) · [Budget Speech 2026/2027: Tax Overview — Werksmans](https://werksmans.com/budget-speech-2026-2027-tax-overview/) · [SARS Rates of Tax for Individuals](https://www.sars.gov.za/tax-rates/income-tax/rates-of-tax-for-individuals/) · [SARS Budget 2026 Tax Guide (PDF)](https://www.sars.gov.za/wp-content/uploads/Docs/Budget/Budget2026/Budget-tax-guide-2026-web-version.pdf) · [ConCourt reserves judgment on Finance Minister's power to change VAT rate — eNCA](https://www.enca.com/news-top-stories/concourt-reserves-judgment-finance-ministers-power-change-vat-rate) · [Sars and Treasury ask top court to overturn ruling — Business Day](https://www.businessday.co.za/news/2026-08-28-sars-and-treasury-ask-top-court-to-overturn-ruling-on-ministers-vat-powers/) · [IFRS — IASB proposes extending consolidation exception for eligible SMEs](https://www.ifrs.org/news-and-events/news/2026/05/iasb-proposes-extending-consolidation-exception-eligible-smes/) · [IFRS for SMEs Accounting Standard—Consolidation Exception work plan](https://www.ifrs.org/projects/work-plan/ifrs-for-smes-accounting-standard-consolidation-exception/)

## 8. Action items

1. **Critical (security, out-of-scope but urgent, carried over unresolved):** `C:\Zuzan\ghp_w0vWd0jgV1yFdHb9NODeqLMx5jlKOz3.txt` still contains what appears to be a live GitHub personal access token in plaintext in the project root, untracked (confirmed still present, unchanged, this run — 40 bytes, dated 24 Aug). Recommend revoking it in GitHub settings and deleting the file; check git history in case it was ever committed.
2. **Medium (carried over, unchanged):** `billing.py`'s `resp = None` duplicate-line pattern and `main.py`'s disabled-middleware comment remain from the repeated commit-generation tooling. Functionally harmless; worth a cleanup pass whenever that tooling is next touched.
3. **Medium (carried over):** `/reports/cash-flow-13week` (`payroll.py:1991-2098`, unchanged) still does not model outstanding creditor (PO) payments or VAT201 liabilities as distinct weekly outflows.
4. **Low (carried over):** with the expense-account routing fix in place (fixed 2026-09-06), custom `/coa` accounts should resolve correctly via the numeric-code path in `expense_account()` — still recommend a quick functional test adding one custom account and posting an expense against it to confirm end-to-end, since this hasn't been explicitly exercised.
5. **Low (carried over, unchanged):** untracked stray file `C:\Zuzan\companies_py_fixed.py` (dated 1 August, 55KB, ~1,133 lines) sits alongside the active `zuzan-backend/companies.py` and diverges substantially — confirmed still present, still unreferenced anywhere in the active codebase. Repo clutter worth deleting in the next cleanup pass alongside other untracked residue (`cleanup_untracked.bat`, `.fuse_hidden*` files, `netlify-drop/`).

**Standing reminders (not defects, carried from prior reports):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry (`payroll.py`) after Budget Feb 2027 and restart the backend;
(b) early-2027 runs should execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`);
(c) the AFS PayFast payment/ad-hoc tokenization feature and the `/reports/ai-insights` feature remain outside this audit's scope;
(d) NBCPSS private security payroll mode predates this audit's baseline, not yet part of this checklist's explicit scope;
(e) file-attribution note: the imported-equity-offset (3998/3999) exclusion logic lives in `payroll.py`'s `balance_sheet()`, not `financial_statements.py`;
(f) next run should keep checking for Treasury's review outcome or Parliamentary introduction of the 2026 draft TLAB/TALAB (public comment closed 28 August 2026; under Treasury/SARS review);
(g) `parent_company_id`/`user_type` columns, bookkeeper-onboarding, consolidated-billing, accountant-fee-structure, and the accountant-practice-dashboard/`billing_exempt` features remain outside Reports/Debtors/Creditors/AFS/tax scope, awareness only;
(h) the 13-week cash-flow forecast feature remains additive and outside the original checklist's endpoint list — tracked via action item 3;
(i) compulsory VAT-registration turnover threshold is R2,300,000 (voluntary R120,000), effective 1 April 2026 — not gated anywhere in-scope, awareness only;
(j) the persistent Chart of Accounts feature (`/coa` router, `CompanyAccount`, `ChartOfAccounts`/`Expenses` components) is additive and outside the original checklist's endpoint list — tracked via action item 4;
(k) the invoice header-image upload, custom HTML invoice template, and service-item catalogue introduced 2026-08-29 remain additive presentation/picklist features outside the original checklist's endpoint list;
(l) **updated this run:** the IASB's SME consolidation-exception Exposure Draft comment period closed today, 9 September 2026 — no final amendment or ballot outcome published yet as at this run; check the next run for a post-close update;
(m) the Constitutional Court has reserved judgment (heard 27 August 2026) on whether Section 7(4) of the VAT Act, 1991 is unconstitutional. No rate change and no ruling yet; monitor for the judgment and any resulting change to how a future VAT rate change would need to be legislated/timed;
(n) no code changes occurred between the 09-08 and 09-09 runs — this was a re-verification + external-rules-freshness run, not a re-derivation; the two High findings fixed 2026-09-06 remain fixed with no regressions.
