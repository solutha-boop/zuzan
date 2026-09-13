# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 11 September 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-09-10 (FAIL at audit time on Debtors/cross-module, FIXED same day post-audit; one carried-over Critical security item, out of scope).

**Change detection since last run:** `git log --since="2026-09-10 00:00"` shows **6 new commits** on `main` (all dated 2026-09-10, 19:37–21:18), net diff `53b9ac2..e44fb1b` touching 5 backend files:

- `zuzan-backend/integrations.py` (+102/-… lines) — this is the same-day fix set described in the 09-10 report's Addendum (action items 1–4). Confirmed by direct diff this run: `_delete_existing_journals` now filters `source == "invoice"` (was `"invoice_raised"`); a `_resolve_currency_and_rate()` helper now requires an explicit `exchangeRate` for non-ZAR SMT invoices (422 if missing) instead of defaulting to 1.0; the update path now blocks amount/vat/total changes on invoices already `status == paid` (409); journal-post failures are now logged and surfaced as a `journal_posted` response field. All four fixes are present and match the addendum exactly — no drift.
- `zuzan-backend/accountant.py` (+83 lines) — new additive feature: `POST /accountant/sync-customers` and an `_upsert_client_as_customer()` helper that auto-creates a `Customer` row in the accountant's practice company for each linked client company (matched by name, idempotent). Reviewed: this only inserts/updates `Customer` name/email/phone — it never creates or touches `Invoice`, `JournalEntry`, or PO rows, so it has no effect on AR/AP balances, aging, or journal integrity. Outside Reports/Debtors/Creditors/AFS/tax scope; noted for awareness only, no defect found.
- `zuzan-backend/csv_import.py` (70 lines changed) — pure refactor of the **employee/payroll-adjustment** CSV import (`import_employees`, `import_payroll_adjustments`) to route field reads through the existing `_get(row, m, field)` helper (`csv_import.py:160-164`, itself unchanged) instead of inline `row.get(m.get(k,""),"").strip()`. Confirmed behaviorally equivalent (same strip/default semantics). The invoice/expense import exchange-rate guard (`csv_import.py:455-487`, the 2026-07-11 fix) is untouched by this diff — re-verified present and unchanged. Out of Debtors/Creditors scope (employee import, not invoice/PO).
- `zuzan-backend/main.py`, `zuzan-backend/billing.py` — cosmetic-only, continuing the pre-existing no-op `resp = None` duplication and disabled-middleware comment padding pattern (carried-over item, see Action Items).
- `commit_and_push.bat` — tooling, no code impact.

`payroll.py`, `journal.py`, `purchase_orders.py`, `companies.py`, `database.py`, `financial_statements.py` are **byte-identical** to 09-10 (absent from the diff). All anchors previously verified in those files were re-confirmed this run via direct `Grep`/`Read` against current file contents (not `bash cat`, per the stale-mount pitfall) rather than re-derived from scratch.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ✅ PASS — unchanged, re-verified |
| Debtors (AR) | ✅ PASS — 09-10 fixes confirmed intact, re-verified against current file |
| Creditors (AP) | ✅ PASS — unchanged, re-verified |
| Cross-module consistency | ✅ PASS — 09-10 fix confirmed intact; new `sync-customers` feature reviewed, no AR/journal impact |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) unchanged; no standards changes since 09-10 |
| Tax updates (SARS) | ✅ PASS — 2026/2027 tables current, no rate changes; VAT-Act case still reserved |

**Overall: PASS.** No new defects found. All four Critical/High/Medium findings from the 09-10 audit (duplicate journal postings, unguarded non-ZAR exchange rate, unguarded paid-invoice amount edits, silent journal-post failures — all in `integrations.py`) were fixed same-day as reported, and this run confirms those fixes landed correctly in the actual commit history and remain in place, byte-for-byte matching the addendum. The one new feature this run (`POST /accountant/sync-customers`) was reviewed and found to have no effect on Debtors, Creditors, journal integrity, or Reports — it only manages `Customer` contact records. One Critical security item (leaked GitHub token file) remains unresolved and out of this audit's technical scope.

## 2. Reports

✓ No issues found. Re-verified against current file contents (all line anchors unmoved since 09-06):

- `total_revenue` sums only paid invoices via `_to_zar()` (`payroll.py:1238`) plus bank-import income (`payroll.py:1240`); `total_outstanding` covers outstanding invoices via `_to_zar()` (`payroll.py:1246`).
- Expenses excluded from revenue — separate accumulator; `gross_profit = total_revenue - total_expenses` (`payroll.py:1288`).
- PO costs added once via `_po_delivered_net()`, no double count. Payroll costs included in expense totals.
- Management-accounts revenue trend (`payroll.py:2281`) and `/v1/summary` (`main.py:461,491`) apply `_to_zar()` consistently.
- 14 `_to_zar()` call sites confirmed present across `payroll.py` (lines 1238, 1246, 1398, 1631, 1643, 1726, 1855, 1918, 2056, 2189, 2264, 2281, 2456, 2569), matching the 09-10 report's anchor list exactly (that report's text said "13" but listed 14 line numbers — a minor wording slip in that report, not a code discrepancy; this run's count matches its own line list).

## 3. Debtors

✓ No issues found this run. The Critical/High findings from 09-10 (foreign-currency invoices misstated 1:1, paid-invoice amounts silently overwritten) were fixed same-day in `integrations.py` and are confirmed present in the actual commit (`bd6f987`/`e44fb1b`) by direct diff this run:

- `_resolve_currency_and_rate()` (`integrations.py:167-186`) requires an explicit, positive `exchangeRate` for any `currency != "ZAR"` SMT invoice, raising 422 if missing — mirrors `csv_import.py:455-487`.
- The update path (`integrations.py:232-256`) blocks amount/vat/total changes on invoices already `status == paid`, raising 409 — mirrors `companies.py:545-549`.
- Paid-invoice exclusion, aging-by-`due_date` (`payroll.py:1629,1644,2053-2054`), and ZAR-equivalent display logic are unchanged and correct.

## 4. Creditors

✓ No issues found. Re-verified against current file contents (unchanged since 09-09):

- Outstanding = received/partial POs plus unpaid on-credit expenses; fully paid POs excluded.
- Reversal-aware AP balance nets `credit − debit` and includes `source.in_(["purchase_order","purchase_order_reversal"])` — confirmed present and unchanged at `payroll.py:1779`, `payroll.py:2645`, `purchase_orders.py:445`, `journal.py:868`, `financial_statements.py:558`.
- Supplier bank details decrypted via `decrypt_field()` before display — unchanged.

## 5. Cross-module consistency

✓ No issues found. The Critical duplicate-journal-entry bug from 09-10 is confirmed fixed and unchanged:

- `_delete_existing_journals` (`integrations.py:135-148`) now filters `JournalEntry.source == "invoice"`, matching what `post_invoice_raised` (`journal.py:230`) actually writes — re-posts now correctly delete-then-repost instead of duplicating. Comment block at `integrations.py:135-142` documents the original bug and fix date for future reference.
- Journal-post failures on the create/update paths now log via `logger.error(..., exc_info=True)` and surface a `journal_posted` bool in the response (`integrations.py:238-244, 322-327`).

New this run: `POST /accountant/sync-customers` (`accountant.py:199-243`) only creates/updates `Customer.name/email/phone` rows keyed on name-match against linked client companies — it never touches `Invoice`, `PurchaseOrder`, or `JournalEntry`. No cross-module consistency impact.

Everything else re-verified, unchanged since 09-09/09-10:
- Journal coverage complete: `post_invoice_raised`, `post_invoice_paid`, `post_invoice_cogs`, `post_expense`, `post_bank_income`, `post_payroll`, `post_expense_paid`, `post_po_received`, `post_po_paid`, `post_stock_adjustment`, `post_asset_acquisition`, `post_depreciation`, `post_asset_disposal` — all present in `journal.py` (confirmed via direct grep this run).
- Import-awareness (2026-07-11 fixes) intact: non-ZAR rows in `csv_import.py`'s invoice import still require an explicit exchange rate and are rejected without one (`csv_import.py:455-487`) — untouched by this run's employee-import refactor.
- Balance sheet Debtors Control / Creditors Control reconciliation logic unchanged.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (`financial_statements.py` docstring; AFS meta `"basis": "IFRS for SMEs"`). File unchanged since 08-26; re-verified rather than re-derived.

**Standards status (fresh web search this run, 11 September 2026):**
- IFRS 18 *Presentation and Disclosure in Financial Statements* — still effective for annual periods beginning on/after 1 January 2027, early application permitted; not yet applicable to IFRS-for-SMEs preparers. No change since 09-10.
- IFRS for SMEs third edition — still effective 1 January 2027 (issued 27 Feb 2025); 2015 edition remains permitted until then. No change.
- IASB Exposure Draft *Consolidation Exception* — comment period closed 9 September 2026 as previously flagged. Fresh search confirms **no final amendment or ballot outcome published yet**; IASB's stated plan remains to issue any amendment by end of 2026, effective 1 January 2027 if approved. Not relevant to ZuZan (no consolidation requirement in scope) — continuing to track for a post-close outcome.

**Section 5b — deferred tax:** already implemented (not hard-coded to `0.0`); re-verified this run at the code level (file unchanged, anchors unmoved):
- `_deferred_tax_balance()` (`financial_statements.py:131`) computes per-asset tax base via `wear_and_tear_rate` (SARS IN47 category mapping).
- Opening/closing deferred tax balances drive `deferred_tax_expense` (`financial_statements.py:266-268`).
- `total_tax` combines current + deferred (`:601`); Note 9 fields (`deferred_tax`, `deferred_tax_opening_balance`, `deferred_tax_closing_balance`) populated (`:606-610`); `deferred_tax_movement` disclosed at `:681`.
- Balance-sheet closing balance carries the matching retained-earnings adjustment so Assets = Equity + Liabilities still holds.

Finance costs (2026-07-13 fix): interest-below-EBIT split and tax/net-profit derivation from `profit_before_tax`, not EBIT, re-confirmed present and unchanged.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date, present at `payroll.py:132`. `payroll.py` unchanged since 09-06.

- Re-confirmed at code level and cross-checked via fresh web search this run: PAYE brackets 18%–45% across seven brackets, primary rebate R17,820 (`payroll.py:142`), secondary rebate R9,765, tertiary R3,249, UIF ceiling R17,712/month (`payroll.py:145`) at 1% employee + 1% employer, SDL 1% employer-only — all match currently published SARS 2026/2027 tables. No discrepancy found.
- CIT remains flat 27% — matches all in-code usages (`financial_statements.py`, `payroll.py:2446 CORP_TAX_RATE`). No CIT rate change found for the 2026/2027 year of assessment.
- VAT standard rate confirmed unchanged at 15% (`payroll.py:1609,2802`). The Constitutional Court case on Section 7(4) of the VAT Act **remains at "judgment reserved"** as at this run's date — heard 27 August 2026, no ruling issued yet per fresh web search (11 September 2026). No rate change; no code impact. Continue monitoring.
- No edits made to tax tables (report-only per task rules; §5b was verification-only this run, already implemented in a prior run).

**Sources consulted:** [VAT Act section declared invalid — The Citizen](https://www.citizen.co.za/news/south-africa/courts/vat-act-section-declared-invalid-unconstitutional/) · [ConCourt reserves judgment on Finance Minister's power to change VAT rate — eNCA](https://www.enca.com/news-top-stories/concourt-reserves-judgment-finance-ministers-power-change-vat-rate) · [List of Constitutional Court judgments 2026 — Wikipedia](https://en.wikipedia.org/wiki/List_of_judgments_of_the_Constitutional_Court_of_South_Africa_delivered_in_2026) · [IFRS for SMEs Accounting Standard Third Edition (Feb 2025) — IFRS.org](https://www.ifrs.org/content/dam/ifrs/publications/ifrs-for-smes/english/2025/ifrs-for-smes.pdf) · [June 2026 IFRS for SMEs Update — IFRS.org](https://www.ifrs.org/supporting-implementation/2015-ifrs-for-smes-supporting-materials/sme-updates/2026/june-2026-ifrs-for-smes-accounting-standard-update/) · [IASB proposes extending consolidation exception for eligible SMEs — IFRS.org](https://www.ifrs.org/news-and-events/news/2026/05/iasb-proposes-extending-consolidation-exception-eligible-smes/) · [IFRS for SMEs Accounting Standard—Consolidation Exception work plan — IFRS.org](https://www.ifrs.org/projects/work-plan/ifrs-for-smes-accounting-standard-consolidation-exception/)

## 8. Action items

1. **Critical (security, out-of-scope but urgent, carried over unresolved):** `C:\Zuzan\ghp_w0vWd0jgV1yFdHb9NODeqLMx5jlKOz3.txt` still contains what appears to be a live GitHub personal access token in plaintext in the project root, untracked. Recommend revoking it in GitHub settings and deleting the file; check git history in case it was ever committed.
2. **Medium (carried over, worse this run):** `billing.py`'s `resp = None` duplicate-line pattern is now **nine lines deep** (was five as of 09-10) and `main.py`'s disabled-middleware comment padding continues to grow from repeated commit-generation tooling. Still functionally harmless, but the pattern is actively getting worse each run — worth a cleanup pass, and worth checking whether the commit tooling itself has a bug causing this repeated duplication.
3. **Medium (carried over):** `/reports/cash-flow-13week` (`payroll.py:1991-2098`, unchanged) still does not model outstanding creditor (PO) payments or VAT201 liabilities as distinct weekly outflows.
4. **Low (new, informational):** the new `POST /accountant/sync-customers` endpoint (`accountant.py:199-243`) auto-creates `Customer` rows for linked client companies with no user-facing indication in the Debtors/Customers UI that a given customer was auto-created vs. manually added — not a correctness defect, but worth a UX follow-up (e.g. a "linked client" badge) so accountants aren't confused by customers they didn't add themselves. Outside this audit's technical scope.
5. **Low (carried over):** with the expense-account routing fix in place (fixed 2026-09-06), custom `/coa` accounts should resolve correctly via the numeric-code path in `expense_account()` — still recommend a quick functional test adding one custom account and posting an expense against it to confirm end-to-end.
6. **Low (carried over, unchanged):** untracked stray file `C:\Zuzan\companies_py_fixed.py` (55KB, ~1,133 lines) sits alongside the active `zuzan-backend/companies.py` and diverges substantially — still unreferenced anywhere in the active codebase. Repo clutter worth deleting alongside other untracked residue (`cleanup_untracked.bat`, `.fuse_hidden*` files, `netlify-drop/`).

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
(j) the persistent Chart of Accounts feature (`/coa` router, `CompanyAccount`, `ChartOfAccounts`/`Expenses` components) is additive and outside the original checklist's endpoint list — tracked via action item 5;
(k) the invoice header-image upload, custom HTML invoice template, and service-item catalogue introduced 2026-08-29 remain additive presentation/picklist features outside the original checklist's endpoint list;
(l) the IASB's SME consolidation-exception Exposure Draft comment period closed 9 September 2026 — no final amendment or ballot outcome published yet as at this run; check the next run for a post-close update;
(m) the Constitutional Court has reserved judgment (heard 27 August 2026) on whether Section 7(4) of the VAT Act, 1991 is unconstitutional. No rate change and no ruling yet; monitor for the judgment and any resulting change to how a future VAT rate change would need to be legislated/timed;
(n) the `/integrations/invoice` (SMT) endpoint is now formally in-scope going forward (added 2026-09-09, fixed 2026-09-10, re-verified fixed 2026-09-11) — once real SMT traffic exists, spot-check with an actual create + re-post cycle (including a deliberate non-ZAR and a deliberate paid-invoice re-post) if test data is available;
(o) **new this run:** `POST /accountant/sync-customers` (`accountant.py`) is a new, additive feature added 2026-09-10 that touches the `Customer` table read by Debtors — reviewed and found to have no AR/journal impact, but it is now tracked going forward given its proximity to Debtors scope (see action item 4).
