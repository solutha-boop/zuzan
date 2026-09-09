# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 8 September 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-09-07 (PASS; both previously-carried High findings — invoice line-item VAT bug, expense-account mismatch — were fixed in that run; one carried-over Critical security item, out of scope).

**Change detection since last run:** `git log --since="2026-09-07 00:10"` shows **zero new commits**. HEAD is unchanged at `415306e93bddbd668afe24a30f65cb67a283881a` (2026-09-06 21:06:58 +0200). `git status` confirms no staged/unstaged changes to tracked files.

Because the codebase is byte-identical to the 2026-09-07 run, every in-scope file/line anchor from that report was spot-verified against current file contents rather than re-derived from scratch — all anchors matched exactly (confirmed via direct reads of `payroll.py`, `journal.py`, `purchase_orders.py`, `financial_statements.py`, `database.py`). This run's incremental work was: (a) confirming no drift in those anchors, and (b) fresh web searches for the two areas that can change independently of the code — IFRS standards status and SARS/VAT-Act legal status — since even an unchanged codebase can go stale against external rules.

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

✓ No issues found. Re-verified against current file contents (all line anchors unmoved from the 09-07 report):

- `total_revenue` sums only paid invoices via `_to_zar()`, plus bank-import income (`payroll.py:1234-1240`).
- `total_outstanding` covers `sent`/`overdue` invoices via `_to_zar()` (`payroll.py:1243-1246`).
- Expenses excluded from revenue; ex-VAT expense total (`payroll.py:1249-1252`).
- PO costs (`received`/`partial`/`paid`) added once via `_po_delivered_net()`, no double count (`payroll.py:1255-1261`).
- Depreciation included in expenses per IAS 16 (`payroll.py:1263-1266`).
- Payroll costs included in expense totals (unchanged since 08-29).
- Management-accounts revenue trend and `/v1/summary` (`main.py`) apply `_to_zar()` consistently — file unchanged.

## 3. Debtors

✓ No issues found.

- `payroll.py:2555-2558` filters `Invoice.status.in_([sent, overdue])` — paid excluded.
- Aged strictly from `due_date`; invoices without a due date go to a `not_due` bucket rather than inflating overdue totals (`payroll.py:2562-2589`).
- Amounts converted via `_to_zar()` at the aging-entry level (`payroll.py:2569`).

## 4. Creditors

✓ No issues found.

- Outstanding = received/partial POs plus unpaid on-credit expenses; fully paid POs excluded (`payroll.py:2609-2628`).
- Reversal-aware AP balance nets `credit − debit` and includes `source.in_(["purchase_order","purchase_order_reversal"])` — confirmed present and unchanged at `payroll.py:1779`, `payroll.py:2645`, `purchase_orders.py:445`, `journal.py:868`, `financial_statements.py:558`.
- Supplier bank details decrypted via `decrypt_field()` before display (`payroll.py:2688-2690`).

## 5. Cross-module consistency

✓ No new gaps.

- Journal coverage complete and unchanged: `post_invoice_raised`, `post_invoice_paid`, `post_invoice_cogs`, `post_expense`, `post_bank_income`, `post_payroll`, `post_expense_paid`, `post_po_received`, `post_po_paid`, `post_stock_adjustment`, `post_asset_acquisition`, `post_depreciation`, `post_asset_disposal` all present (`journal.py:214-670`).
- Migration hygiene confirmed: both `financial_year_end` (`database.py:1533`) and `wear_and_tear_rate` (`database.py:1446`) sit inside the migrations list literal, not after the `for` loop.
- Import-awareness (2026-07-11 fixes) intact and unchanged: Rules 6/7 exclude `source == "import"`; balance sheet carries 3998/3999 imported-equity offsets; non-ZAR invoice imports still require an exchange rate; unbalanced journal-import groups still rejected.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (`financial_statements.py:2` docstring, `:623` AFS meta `"basis": "IFRS for SMEs"`). File unchanged since 08-26; re-verified rather than re-derived.

**Standards status (fresh web search this run, 8 September 2026):** no change since 09-07.
- IFRS 18 *Presentation and Disclosure in Financial Statements* — effective for annual periods beginning on/after 1 January 2027, early application permitted; still not applicable to IFRS-for-SMEs preparers (ZuZan's basis).
- IFRS for SMEs third edition (issued 27 February 2025) — confirmed via fresh search still effective 1 January 2027; the 2015 edition remains permitted until then. It introduces a new IFRS-15-based revenue model and updated business-combination/consolidation/financial-instrument requirements aligned to the 2018 Conceptual Framework — noted for the transition-plan checklist referenced in prior reports' standing reminders, not yet due to apply.
- The IASB's Exposure Draft *Consolidation Exception* (published May 2026): comment period closed **9 September 2026** — as at this run's date (8 September) it is **1 day from closing**, still open. No final amendment issued yet. Still not relevant to ZuZan (no consolidation requirement in scope), but the closing date is now imminent — flagged for the next run to check for a post-close update.

**Section 5b — deferred tax:** already implemented (not hard-coded to `0.0`); re-verified this run at the code level (file unchanged, anchors unmoved):
- `_deferred_tax_balance()` (`financial_statements.py:131`) computes per-asset tax base via `wear_and_tear_rate` (SARS IN47 category mapping, `database.py:498`).
- Opening/closing deferred tax balances drive `deferred_tax_expense` (`financial_statements.py:266-268`).
- `total_tax` combines current + deferred (`:601`); Note 9 fields (`deferred_tax`, `deferred_tax_opening_balance`, `deferred_tax_closing_balance`) populated (`:604-610`).
- Balance-sheet closing balance carries the matching retained-earnings adjustment so Assets = Equity + Liabilities still holds.

Finance costs (2026-07-13 fix): interest-below-EBIT split (`financial_statements.py:204-211`) and tax/net-profit derivation from `profit_before_tax`, not EBIT (`:257-260`), re-confirmed present and unchanged.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date, present at `payroll.py:132`. `_current_tax_year()` (`payroll.py:170-183`) correctly resolves to `"2026/2027"`. `payroll.py` unchanged since 09-06.

- Re-confirmed at code level and cross-checked via fresh web search this run: PAYE brackets 18%–45% across seven brackets (18% to R245,100; 26% to R383,100; 31% to R530,200; 36% to R695,800; 39% to R887,000; 41% to R1,878,600; 45% above), primary rebate R17,820, secondary R9,765, tertiary R3,249, UIF ceiling R17,712/month at 1% employee + 1% employer (`payroll.py:189-190,477-478,132-146`), SDL 1% employer-only (`payroll.py:190,483`) — all match current published SARS 2026/2027 tables exactly. No discrepancy found.
- CIT remains flat 27% — matches all in-code usages: `financial_statements.py:84` (`_CIT_RATE`, sourced from `fixed_assets.SA_CIT_RATE`), `fixed_assets.py:78` (`SA_CIT_RATE = 0.27`), `payroll.py:1290,2255,2446` (`0.27` / `CORP_TAX_RATE = 0.27`). No CIT rate change found for the 2026/2027 year of assessment.
- VAT standard rate confirmed unchanged at 15% (`companies.py:289`, `payroll.py:1609,2802`, `quotes.py:15` — all `VAT_RATE = 0.15`). The Constitutional Court case on Section 7(4) of the VAT Act (the Finance Minister's power to change VAT rates by budget-speech announcement) **remains at "judgment reserved"** as at this run's date — heard 27 August 2026, no ruling issued yet per fresh web search. No rate change; no code impact. Continue monitoring.
- No edits made to tax tables (report-only per task rules; §5b was verification-only this run, already implemented in a prior run).

**Sources consulted:** [SARS Tax Tables 2026/2027 — Xero ZA](https://www.xero.com/za/guides/sars-tax-tables-2026/) · [Accounter — SARS Tax Tables 2026/2027](https://accounter.co.za/news/sars-tax-tables-2026-2027) · [DA v Minister of Finance: VAT Act Analysis — CMS Law](https://cms.law/en/zaf/legal-updates/no-more-value-added-tax-increases-by-decree) · [ConCourt reserves judgment on Finance Minister's power to change VAT rate — eNCA](https://www.enca.com/news-top-stories/concourt-reserves-judgment-finance-ministers-power-change-vat-rate) · [Sars and Treasury ask top court to overturn ruling — Business Day](https://www.businessday.co.za/news/2026-08-28-sars-and-treasury-ask-top-court-to-overturn-ruling-on-ministers-vat-powers/) · [Godongwana's lawyers urge ConCourt to uphold VAT Act provisions — EWN](https://www.ewn.co.za/2026/08/27/godongwanas-lawyers-urge-concourt-to-uphold-vat-act-provisions-for-sound-fiscal-administration) · [IFRS - IASB issues third edition of the IFRS for SMEs Accounting Standard](https://www.ifrs.org/news-and-events/news/2025/02/iasb-issues-major-update-smes-accounting-standard/) · [IFRS - IASB proposes extending consolidation exception for eligible SMEs](https://www.ifrs.org/news-and-events/news/2026/05/iasb-proposes-extending-consolidation-exception-eligible-smes/) · [IFRS - IFRS for SMEs Accounting Standard—Consolidation Exception work plan](https://www.ifrs.org/projects/work-plan/ifrs-for-smes-accounting-standard-consolidation-exception/)

## 8. Action items

1. **Critical (security, out-of-scope but urgent, carried over unresolved):** `C:\Zuzan\ghp_w0vWd0jgV1yFdHb9NODeqLMx5jlKOz3.txt` still contains what appears to be a live GitHub personal access token in plaintext in the project root, untracked (confirmed still present, unchanged, this run). Recommend revoking it in GitHub settings and deleting the file; check git history in case it was ever committed.
2. **Medium (carried over, unchanged):** `billing.py`'s `resp = None` duplicate-line pattern and `main.py`'s disabled-middleware comment remain from the repeated commit-generation tooling. Functionally harmless; worth a cleanup pass whenever that tooling is next touched.
3. **Medium (carried over):** `/reports/cash-flow-13week` (`payroll.py:1991-2098`, unchanged) still does not model outstanding creditor (PO) payments or VAT201 liabilities as distinct weekly outflows.
4. **Low (carried over):** with the expense-account routing fix now in place (fixed 2026-09-06), custom `/coa` accounts should resolve correctly via the numeric-code path in `expense_account()` — still recommend a quick functional test adding one custom account and posting an expense against it to confirm end-to-end, since this hasn't been explicitly exercised.
5. **Low (new, informational):** an untracked stray file `C:\Zuzan\companies_py_fixed.py` (dated 1 August, 55KB, ~1,133 lines) sits alongside the active `zuzan-backend/companies.py` (75KB, ~1,589 lines) and diverges substantially — it is not imported anywhere in the active codebase and appears to be a superseded/backup copy from an earlier fix. No functional risk since nothing references it, but it's repo clutter worth deleting in the next cleanup pass alongside the other untracked residue (`cleanup_untracked.bat`, `.fuse_hidden*` files, `netlify-drop/`).

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
(l) **updated this run:** the IASB's SME consolidation-exception Exposure Draft comment period closes 9 September 2026 — now 1 day away as at this run's date; check the next run for a post-close update or final amendment;
(m) the Constitutional Court has reserved judgment (heard 27 August 2026) on whether Section 7(4) of the VAT Act, 1991 is unconstitutional. No rate change and no ruling yet; monitor for the judgment and any resulting change to how a future VAT rate change would need to be legislated/timed;
(n) no code changes occurred between the 09-07 and 09-08 runs — this was a re-verification + external-rules-freshness run, not a re-derivation; the two High findings fixed 2026-09-06 remain fixed with no regressions.
