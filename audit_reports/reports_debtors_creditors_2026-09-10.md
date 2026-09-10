# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 10 September 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-09-09 (PASS; codebase unchanged from 09-08; one carried-over Critical security item, out of scope).

**Addendum (same day, post-audit):** Action items 1–4 below (the `integrations.py` Critical/High/Medium findings) were fixed immediately following this audit, in `zuzan-backend/integrations.py`:
- Action item 1 (Critical): `_delete_existing_journals` now filters `source == "invoice"` (was `"invoice_raised"`), matching what `post_invoice_raised` actually writes — re-posts now correctly delete-then-repost instead of duplicating.
- Action item 2 (High): the update path now blocks amount/vat/total changes on invoices already `status == paid` (409), mirroring `companies.py`'s guard.
- Action item 3 (High): added a required `exchangeRate` field to `SMTInvoice`; non-ZAR payloads without one are rejected (422) via new `_resolve_currency_and_rate()`, instead of silently defaulting to 1.0.
- Action item 4 (Medium): journal-post failures are now logged (`logger.error(..., exc_info=True)`, logger `"zuzan.integrations"`) and surfaced as a `journal_posted: false` field + a warning message in the response, instead of being silently swallowed.
- Verified via `Read` (not `bash`, per the stale-mount pitfall) and a syntax check (`ast.parse`) — no functional/behavioral testing against a live SMT payload was performed since this endpoint has not yet processed production traffic. Recommend the next scheduled run re-verify these anchors and, if feasible, exercise a real create → re-post cycle (including a deliberate non-ZAR and a deliberate paid-invoice re-post) with test data.

**Change detection since last run:** `git log --since="2026-09-09 00:00"` shows **two new commits** on `main`:
- `0aa4941` (21:58) — adds `zuzan-backend/integrations.py` (new inbound-invoice endpoint `POST /integrations/invoice` for the Solid Matter Travel (SMT) back-office system), a new `Customer.external_code` column + migration, wiring in `main.py`, and a cosmetic no-op edit to `billing.py`.
- `53b9ac2` (22:07) — cosmetic-only: one more no-op `resp = None` line in `billing.py` and a comment-padding edit in `main.py` (the disabled-`_SubscriptionGateMiddleware` comment line, still disabled, functionally identical).

This is the first genuinely new feature surface since the 09-06 fixes, and it lands squarely in Debtors/cross-module journal scope (it creates and updates `Invoice` rows and posts to the journal), so this run treats it as a full first-time review rather than a re-verification. All previously-verified anchors in `payroll.py`, `journal.py`, `purchase_orders.py`, `financial_statements.py`, `companies.py` were spot-checked via `Grep` (not `bash cat`, per the stale-mount pitfall) and are byte-identical to 09-09 — those sections are re-verified, not re-derived, below.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ✅ PASS — unchanged, re-verified |
| Debtors (AR) | ⚠️ FAIL at audit time — ✅ **FIXED same day** (see Addendum) |
| Creditors (AP) | ✅ PASS — unchanged, re-verified |
| Cross-module consistency | ⚠️ FAIL at audit time — ✅ **FIXED same day** (see Addendum) |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) unchanged; no standards changes |
| Tax updates (SARS) | ✅ PASS — 2026/2027 tables current, no rate changes; VAT-Act case still reserved |

**Overall: FAIL at audit time, FIXED same day.** The new `POST /integrations/invoice` endpoint (added 2026-09-09, not yet exercised in production per its commit timestamp) contained a Critical duplicate-journal-entry bug and a High-severity foreign-currency misstatement bug that would have corrupted Debtors Control, Revenue, and VAT Output Payable the first time it processed a repeat or non-ZAR document. All four findings (action items 1–4) were fixed in `integrations.py` immediately following this audit — see Addendum above. Code-level verification only; no live SMT traffic has exercised this endpoint yet. One Critical security item (leaked GitHub token file) remains unresolved and out of this audit's technical scope — see Action Items.

## 2. Reports

✓ No issues found. Re-verified against current file contents (all line anchors unmoved):

- `total_revenue` sums only paid invoices via `_to_zar()` (`payroll.py:1238`), plus bank-import income.
- `total_outstanding` covers outstanding invoices via `_to_zar()` (`payroll.py:1246`).
- Expenses excluded from revenue — separate accumulator, `gross_profit = total_revenue - total_expenses`.
- PO costs added once via `_po_delivered_net()`, no double count. Payroll costs included in expense totals.
- Management-accounts revenue trend (`payroll.py:2281`) and `/v1/summary` (`main.py`) apply `_to_zar()` consistently.
- All 13 `_to_zar()` call sites in `payroll.py` (lines 1238, 1246, 1398, 1631, 1643, 1726, 1855, 1918, 2056, 2189, 2264, 2281, 2456, 2569) confirmed present and consistent with the prior report's anchors.

## 3. Debtors

**⚠️ New issue this run — see also §5 (cross-module) for the root cause.**

The new `POST /integrations/invoice` endpoint (`integrations.py`) creates and updates rows in the same `Invoice` table that every Debtors/AR query in `payroll.py` reads from, so any defect here flows directly into AR aging, outstanding balances, and revenue.

1. **[Critical] Foreign-currency invoices from the integration are misstated 1:1 in every ZAR report.** `integrations.py:234` hard-codes `exchange_rate = 1` on the create path regardless of `inv.currency` (line 233 sets `currency = inv.currency or "ZAR"`, so a non-ZAR `SMTInvoice.currency` value passes straight through). `_to_zar()` (`payroll.py:18-25`) multiplies `total_amount * exchange_rate` for any invoice whose `currency != "ZAR"` — with `exchange_rate` pinned at 1, a foreign-currency SMT invoice would be valued as if its face amount were already in ZAR everywhere it feeds Debtors/AR aging, revenue, and VAT201. This is the exact bug class that was fixed in `csv_import.py` on 2026-07-11 (`csv_import.py:458-475`, which now rejects non-ZAR rows without an explicit exchange rate rather than silently defaulting to 1.0) — it has been reintroduced in this new file. SMT invoices observed in the payload model default to `currency: "ZAR"`, so this is latent rather than actively firing today, but nothing prevents SMT posting a foreign-currency document.
   - **Fix:** mirror the `csv_import.py` pattern — require/parse an exchange rate for non-ZAR payloads (add an `exchangeRate` field to `SMTInvoice`/`SMTTotals`, or reject with 422 if `currency != "ZAR"` and no rate is supplied) instead of defaulting to 1.

2. **[High] The update path can silently corrupt a paid invoice's balances.** `integrations.py:191-220` (the `existing` branch) unconditionally overwrites `amount`, `vat_amount`, and `total_amount` on any invoice matched by `invoice_number`, with no check of `existing.status`. Compare `companies.py:519-549` (`update_invoice`), which explicitly blocks amount edits on `InvoiceStatus.paid` invoices ("Cannot change the amount of a paid invoice. Mark it as unpaid first, then edit the amount." — 2026-07-07 fix, see also `[[project_invoice_edit_journal]]`). The integration endpoint has no equivalent guard, so if SMT re-posts a document number for an invoice ZuZan has since marked paid, the invoice's amount changes but the existing `post_invoice_paid` journal entry (posted against the old total) is never reversed or repointed — Debtors Control and cash/bank reconciliation for that invoice go out of balance with no error surfaced anywhere.
   - **Fix:** apply the same `was_paid and amount_changed` guard as `companies.py:545-549` — either reject the update (502/409) or require an explicit unmark-paid step before accepting a changed total.

Paid-invoice exclusion, aging-by-`due_date`, and ZAR-equivalent display logic themselves are unchanged and still correct (re-verified, same anchors as 09-09) — the defect is specifically in how invoices arrive from this new inbound path, not in how Debtors reads them.

## 4. Creditors

✓ No issues found. Re-verified against current file contents (unrelated to this run's new commits):

- Outstanding = received/partial POs plus unpaid on-credit expenses; fully paid POs excluded.
- Reversal-aware AP balance nets `credit − debit` and includes `source.in_(["purchase_order","purchase_order_reversal"])` — confirmed present and unchanged at `payroll.py:1779`, `payroll.py:2645`, `purchase_orders.py:445`, `journal.py:868`, `financial_statements.py:558`.
- Supplier bank details decrypted via `decrypt_field()` before display — unchanged.

## 5. Cross-module consistency

**⚠️ New issue this run.**

1. **[Critical] The integration endpoint's own reverse-and-repost logic never fires, causing duplicate journal entries on every re-post.** `integrations.py:131-137` (`_delete_existing_journals`) deletes journal entries where `JournalEntry.source == "invoice_raised"`. But `post_invoice_raised` (`journal.py:214-251`) constructs its entry via `_make_entry(cid, ..., "invoice", invoice.id, db)` (`journal.py:230`) — the actual source string written to the database is `"invoice"`, not `"invoice_raised"`. This is confirmed by every other consumer of this source value: `companies.py:508` (`_has_active_raised_entry`) and `journal.py:742` (backfill) both filter on `source == "invoice"`. Because `_delete_existing_journals` filters on a source string that is never actually written, it deletes nothing, and the update path (`integrations.py:210-213`) then calls `post_invoice_raised(existing, db)` again — posting a **second** DR Accounts Receivable / CR Sales Revenue / CR VAT Output Payable entry for the same invoice on top of the first. Every time SMT re-posts the same `documentNo` (the endpoint's own docstring says this is expected behaviour — "updates + re-journals if the document number already exists"), Debtors Control (1100), Sales Revenue (4000), and VAT Output Payable (2100) all accumulate a duplicate posting. This will directly desync the balance sheet's Debtors Control from the raw invoice total the very first time any SMT document is amended and re-sent.
   - **Fix:** change the filter in `_delete_existing_journals` from `source == "invoice_raised"` to `source == "invoice"` (matching `journal.py:230`), or better, extract a shared constant so this can't drift again.

2. **[Medium] Journal-post failures are silently swallowed with no logging.** Both the create and update paths (`integrations.py:210-213`, `247-250`) wrap `post_invoice_raised(...)` in `try/except Exception: pass`, with the comment "journal failure must not block the invoice save." That design choice (favoring invoice durability over strict atomicity) is defensible, but the total silence is not — there is no log line, no flag on the invoice, and no field in the response indicating a journal-post failure occurred. An operator has no way to discover that an invoice exists with zero journal footprint short of manually reconciling Debtors Control against raw invoice totals. Every other journal-posting call site in the codebase (invoice raise/pay, PO receive/pay, payroll, imports) either lets the exception propagate inside a single commit/rollback unit or is covered by the existing import-backfill reconciliation tooling; this is the first "fire and forget" journal call in the codebase.
   - **Fix:** at minimum log the exception (`logger.error(...)`) with the invoice id, and consider surfacing `"journal_posted": false` in the response so the calling system (or a nightly reconciliation job) can detect and retry.

Everything else re-verified, unchanged since 09-09:
- Journal coverage complete: `post_invoice_raised`, `post_invoice_paid`, `post_invoice_cogs`, `post_expense`, `post_bank_income`, `post_payroll`, `post_expense_paid`, `post_po_received`, `post_po_paid`, `post_stock_adjustment`, `post_asset_acquisition`, `post_depreciation`, `post_asset_disposal` — all present in `journal.py` (confirmed via direct grep this run).
- Migration hygiene: the new `external_code` column migration (`database.py:1543`, `"ALTER TABLE customers ADD COLUMN IF NOT EXISTS external_code VARCHAR"`) sits correctly **inside** the migrations list literal (verified via `Read`, not `bash`, per the stale-mount pitfall), not after the `for` loop — no repeat of the dead-code migration defect.
- Import-awareness (2026-07-11 fixes) intact and unchanged in `csv_import.py`: non-ZAR rows still require an explicit exchange rate and are rejected without one (`csv_import.py:458-475`) — which makes finding #1 in §3 above a genuine regression of a previously-fixed bug class, just in a new file rather than the one that was patched.
- Balance sheet Debtors Control / Creditors Control reconciliation logic itself unchanged.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (`financial_statements.py` docstring; AFS meta `"basis": "IFRS for SMEs"`). File unchanged since 08-26; re-verified rather than re-derived.

**Standards status (fresh web search this run, 10 September 2026):**
- IFRS 18 *Presentation and Disclosure in Financial Statements* — still effective for annual periods beginning on/after 1 January 2027, early application permitted; not yet applicable to IFRS-for-SMEs preparers. No change.
- IFRS for SMEs third edition — still effective 1 January 2027, 2015 edition remains permitted until then. No change.
- IASB Exposure Draft *Consolidation Exception* — comment period closed 9 September 2026 as previously flagged; fresh search confirms **no final amendment or ballot outcome published yet**. IASB's stated plan remains to issue any amendment by end of 2026, effective 1 January 2027 if approved. Not relevant to ZuZan (no consolidation requirement in scope) but still being tracked for a post-close outcome.

**Section 5b — deferred tax:** already implemented (not hard-coded to `0.0`); re-verified this run at the code level (file unchanged, anchors unmoved):
- `_deferred_tax_balance()` (`financial_statements.py:131`) computes per-asset tax base via `wear_and_tear_rate` (SARS IN47 category mapping, `fixed_assets.py`).
- Opening/closing deferred tax balances drive `deferred_tax_expense` (`financial_statements.py:266-268`).
- `total_tax` combines current + deferred (`:601`); Note 9 fields (`deferred_tax`, `deferred_tax_opening_balance`, `deferred_tax_closing_balance`) populated (`:606-610`); `deferred_tax_movement` disclosed at `:681`.
- Balance-sheet closing balance carries the matching retained-earnings adjustment so Assets = Equity + Liabilities still holds.

Finance costs (2026-07-13 fix): interest-below-EBIT split and tax/net-profit derivation from `profit_before_tax`, not EBIT, re-confirmed present and unchanged.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date, present at `payroll.py:132`. `payroll.py` unchanged since 09-06.

- Re-confirmed at code level and cross-checked via fresh web search this run: PAYE brackets 18%–45% across seven brackets, primary rebate R17,820 (`payroll.py:142`), secondary rebate R9,765, tertiary R3,249, UIF ceiling R17,712/month (`payroll.py:145`) at 1% employee + 1% employer, SDL 1% employer-only — all match current published SARS 2026/2027 tables. No discrepancy found.
- CIT remains flat 27% — matches all in-code usages (`financial_statements.py`, `fixed_assets.py:78 SA_CIT_RATE`, `payroll.py:2446 CORP_TAX_RATE`). No CIT rate change found for the 2026/2027 year of assessment.
- VAT standard rate confirmed unchanged at 15% (`companies.py:289`, `payroll.py:1609`). The Constitutional Court case on Section 7(4) of the VAT Act **remains at "judgment reserved"** as at this run's date — heard 27 August 2026, no ruling issued yet per fresh web search. No rate change; no code impact. Continue monitoring.
- No edits made to tax tables (report-only per task rules; §5b was verification-only this run, already implemented in a prior run).

**Sources consulted:** [Accounter — SARS Tax Tables 2026/2027](https://accounter.co.za/news/sars-tax-tables-2026-2027) · [SARS Budget 2026 FAQ](https://www.sars.gov.za/about/sars-tax-and-customs-system/budget/budget-2026-frequently-asked-questions/) · [ConCourt reserves judgment on Finance Minister's power to change VAT rate — eNCA](https://www.enca.com/news-top-stories/concourt-reserves-judgment-finance-ministers-power-change-vat-rate) · [Sars and Treasury ask top court to overturn ruling — Business Day](https://www.businessday.co.za/news/2026-08-28-sars-and-treasury-ask-top-court-to-overturn-ruling-on-ministers-vat-powers/) · [Godongwana's lawyers urge ConCourt to uphold VAT Act provisions — EWN](https://www.ewn.co.za/2026/08/27/godongwanas-lawyers-urge-concourt-to-uphold-vat-act-provisions-for-sound-fiscal-administration) · [IFRS — IFRS for SMEs Accounting Standard—Consolidation Exception work plan](https://www.ifrs.org/projects/work-plan/ifrs-for-smes-accounting-standard-consolidation-exception/) · [IFRS — IASB proposes extending consolidation exception for eligible SMEs](https://www.ifrs.org/news-and-events/news/2026/05/iasb-proposes-extending-consolidation-exception-eligible-smes/)

## 8. Action items

1. ✅ **FIXED same day (was Critical):** Source-string mismatch in `_delete_existing_journals` (`_delete_existing_journals` filtered `source == "invoice_raised"`, but `post_invoice_raised` writes `source == "invoice"`) — every SMT re-post of an existing document number was double-posting to Debtors Control, Sales Revenue, and VAT Output Payable. Filter corrected to `source == "invoice"`. See §5.1 and Addendum.
2. ✅ **FIXED same day (was High):** Paid-invoice amount-edit guard added to `integrations.py`'s update path, mirroring `companies.py:545-549` — an SMT re-post for an invoice already marked paid in ZuZan now returns 409 instead of silently overwriting amount/vat/total with no reversal of the existing payment journal entry. See §3.2 and Addendum.
3. ✅ **FIXED same day (was High):** Non-ZAR SMT invoices now require an explicit `exchangeRate` field (422 if missing) instead of hard-coding `exchange_rate = 1` — closes the reintroduced regression of the `csv_import.py` 2026-07-11 fix. See §3.1 and Addendum.
4. ✅ **FIXED same day (was Medium):** Journal-post failures in `integrations.py` are now logged (`logger.error(..., exc_info=True)`) and surfaced as a `journal_posted` flag in the response, instead of being silently swallowed. See §5.2 and Addendum.
5. **Critical (security, out-of-scope but urgent, carried over unresolved):** `C:\Zuzan\ghp_w0vWd0jgV1yFdHb9NODeqLMx5jlKOz3.txt` still contains what appears to be a live GitHub personal access token in plaintext in the project root, untracked. Recommend revoking it in GitHub settings and deleting the file; check git history in case it was ever committed.
6. **Medium (carried over, unchanged):** `billing.py`'s `resp = None` duplicate-line pattern (now five lines deep as of this run's commits) and `main.py`'s disabled-middleware comment remain from repeated commit-generation tooling. Functionally harmless; worth a cleanup pass whenever that tooling is next touched.
7. **Medium (carried over):** `/reports/cash-flow-13week` (`payroll.py:1991-2098`, unchanged) still does not model outstanding creditor (PO) payments or VAT201 liabilities as distinct weekly outflows.
8. **Low (carried over):** with the expense-account routing fix in place (fixed 2026-09-06), custom `/coa` accounts should resolve correctly via the numeric-code path in `expense_account()` — still recommend a quick functional test adding one custom account and posting an expense against it to confirm end-to-end.
9. **Low (carried over, unchanged):** untracked stray file `C:\Zuzan\companies_py_fixed.py` (55KB, ~1,133 lines) sits alongside the active `zuzan-backend/companies.py` and diverges substantially — still unreferenced anywhere in the active codebase. Repo clutter worth deleting alongside other untracked residue (`cleanup_untracked.bat`, `.fuse_hidden*` files, `netlify-drop/`).

**Standing reminders (not defects, carried from prior reports):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry (`payroll.py`) after Budget Feb 2027 and restart the backend;
(b) early-2027 runs should execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`);
(c) the AFS PayFast payment/ad-hoc tokenization feature and the `/reports/ai-insights` feature remain outside this audit's scope;
(d) NBCPSS private security payroll mode predates this audit's baseline, not yet part of this checklist's explicit scope;
(e) file-attribution note: the imported-equity-offset (3998/3999) exclusion logic lives in `payroll.py`'s `balance_sheet()`, not `financial_statements.py`;
(f) next run should keep checking for Treasury's review outcome or Parliamentary introduction of the 2026 draft TLAB/TALAB (public comment closed 28 August 2026; under Treasury/SARS review);
(g) `parent_company_id`/`user_type` columns, bookkeeper-onboarding, consolidated-billing, accountant-fee-structure, and the accountant-practice-dashboard/`billing_exempt` features remain outside Reports/Debtors/Creditors/AFS/tax scope, awareness only;
(h) the 13-week cash-flow forecast feature remains additive and outside the original checklist's endpoint list — tracked via action item 7;
(i) compulsory VAT-registration turnover threshold is R2,300,000 (voluntary R120,000), effective 1 April 2026 — not gated anywhere in-scope, awareness only;
(j) the persistent Chart of Accounts feature (`/coa` router, `CompanyAccount`, `ChartOfAccounts`/`Expenses` components) is additive and outside the original checklist's endpoint list — tracked via action item 8;
(k) the invoice header-image upload, custom HTML invoice template, and service-item catalogue introduced 2026-08-29 remain additive presentation/picklist features outside the original checklist's endpoint list;
(l) the IASB's SME consolidation-exception Exposure Draft comment period closed 9 September 2026 — no final amendment or ballot outcome published yet as at this run; check the next run for a post-close update;
(m) the Constitutional Court has reserved judgment (heard 27 August 2026) on whether Section 7(4) of the VAT Act, 1991 is unconstitutional. No rate change and no ruling yet; monitor for the judgment and any resulting change to how a future VAT rate change would need to be legislated/timed;
(n) **new this run:** the `/integrations/invoice` (SMT) endpoint is a new, additive feature added 2026-09-09 that sits inside Debtors/journal scope — unlike other additive features it is now formally in-scope going forward given the Critical/High findings above; next run should re-verify items 1–4 are fixed and, once fixed, spot-check with a real create + re-post cycle if test data is available.
