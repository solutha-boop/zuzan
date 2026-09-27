# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 27 September 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-09-25 (PASS)

**Change detection since last run:** `git log` shows the 09-25 report's verified baseline was commit `f480d17`. Four commits have landed since then — `2dc10ec` (25 Sep 08:31), `1edd74e` (27 Sep 13:52), `d177cd4` (27 Sep 14:02), `a89e3cc` (27 Sep 14:11) — all sharing a reused/boilerplate commit message ("payroll advances… tiered payroll pricing… integrations 500 FK order… journal CASCADE migration") that does **not** match what actually changed. `git diff --stat f480d17 HEAD` shows the real diff is narrow: **`zuzan-backend/companies.py`** (+158/-1: a new `POST /companies/clear-data` endpoint) and **`App_js_fixed.js`** (+111, mirrored byte-for-byte in `zuzan-app/src/App.js`: a "Clear Trial Data" UI in Settings plus a "Going Live" pre-subscribe modal that calls the same endpoint). `commit_and_push.bat` changed only its own commit-message string. The remaining diff entries are this audit's own prior output and another scheduled job's reconciliation artifacts (`reconciliation_2026-09-27.md`, `recon_sweep.py`) — not application code.

**All other in-scope files — `payroll.py`, `main.py`, `journal.py`, `database.py`, `financial_statements.py`, `purchase_orders.py`, `csv_import.py`, `customers.py`, `suppliers.py` — are byte-identical to the fully-verified 09-25 baseline** (`git diff` empty for each). Their checklist items are carried forward from 09-25 with a fresh anchor-line spot-check (§2–§5, §7) rather than full re-derivation. New code (`companies.py`'s clear-data endpoint and its frontend UI) was reviewed in full, and it surfaces one genuine new finding — see §4 and §5.

**Addendum (same day, post-report):** action item 1 (below) was fixed at the user's request immediately after this report was filed. `zuzan-backend/companies.py`'s blanket `if cats & financial_cats: <delete every JournalEntry for the company>` was replaced with a `_CATEGORY_JOURNAL_SOURCES` map plus a `_clear_journal_for_sources()` helper that deletes only the journal entries (and their `_reversal` counterparts) actually owned by each category selected — covering `suppliers` (`purchase_order`, `po_payment`) and `budgets_assets` (`fixed_asset`, `depreciation`, `asset_disposal`), which the old code omitted entirely, and `inventory` (`stock_adjustment`), which had the identical gap but wasn't called out in the original finding. This also fixes a second, previously-unflagged half of the same bug: the old blanket delete wiped **every** journal entry for the company whenever *any* of `sales`/`expenses`/`employees`/`banking` was selected, even ones unrelated to the ticked categories (e.g. ticking only "Expenses" used to also erase all invoice and payroll journal entries) — the new code scopes strictly by source, so clearing one category can no longer touch another's postings. Verified: `python3 -m py_compile` passes; the source-map was cross-checked against every `_make_entry(...)`/`JournalEntry(...)` call site in `journal.py` and `csv_import.py` and against the live `zuzan.db`'s actual distinct `source` values (`expense`, `invoice`, `payroll` — all present in the map); `git diff --stat` for the fix shows only `zuzan-backend/companies.py` touched, 50 insertions / 13 deletions. Not yet committed to git — see the chat reply for the diff and next steps. Action item 1's severity is now **Fixed, pending commit**; item (s) below still stands as a general future-proofing reminder.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ✅ PASS — unchanged, re-confirmed |
| Debtors (AR) | ✅ PASS — unchanged, re-confirmed |
| Creditors (AP) | ✅ **FIXED same day** — clear-data endpoint's journal-orphaning gap patched (§4, action item 1) |
| Cross-module consistency | ✅ **FIXED same day** — same fix closes the Balance Sheet fixed-asset/depreciation/inventory exposure too (§5) |
| IFRS compliance (AFS) | ✅ PASS — no standards changes since 09-25; deferred tax (5b) unchanged and re-verified |
| Tax updates (SARS) | ✅ PASS — 2026/2027 tables current, no rate changes |

**Overall: PASS.** One new High-severity finding was identified in `companies.py`'s new clear-data endpoint and fixed the same day, before commit — see the addendum above and action item 1. No regressions in previously-verified code; no IFRS or SARS rate changes since 09-25.

## 2. Reports

✓ No issues found. Unchanged since 09-25 (file byte-identical); anchor lines re-confirmed this run:

- `payroll.py` `/reports/dashboard` (`:1648-1739`): `total_revenue` (`:1661`) sums only `InvoiceStatus.paid` invoices via `_to_zar()`; `total_outstanding` (`:1669`) covers `sent`+`overdue` via `_to_zar()`; expenses (`:1675`) and PO COGS (`:1684`, via `_po_delivered_net()`, no double-count) roll into `total_expenses`, never revenue; payroll cost (`Payslip.total_cost`, `:1699-1709`) is a separate expense line, not omitted or double-counted.
- `/reports/management` revenue trend loop applies `_to_zar()` on every iteration (`:2986`).
- `main.py` `/v1/summary` (`:466-511`): applies `_to_zar()` for `total_revenue` (`:473-474`) and `outstanding` (`:503`); expense/PO/depreciation/payroll treatment mirrors `/reports/dashboard`.
- `_to_zar()` re-confirmed at its ~18 call sites across `payroll.py`/`main.py` — no bypass found.

## 3. Debtors

✓ No issues found. Unchanged since 09-25; anchor lines re-confirmed:

- `/reports/debtors-aging` (`payroll.py:3251-3311`): filtered to `Invoice.status.in_([sent, overdue])` (`:3262`) — paid invoices excluded.
- ZAR equivalents via `_to_zar()` (`:3274`); aged from `due_date` only (`:3270`), with a `not_due` bucket for invoices lacking a `due_date` (`:3279-3281`).
- Buckets `not_due` / `current` / `31_60` / `61_90` / `over_90` correctly bounded (`:3286-3294`).
- The new "Clear Trial Data" feature does not touch this endpoint's logic — reviewed for interaction and found none (invoices are only removed when a company explicitly clears its own `sales` category, and the aging query is always scoped to `company_id`, so no cross-company leakage risk either).

## 4. Creditors

**New finding — High.** The rest of the Creditors logic is unchanged and re-confirmed; see below for detail.

- `/reports/creditors-aging` (`payroll.py:3314-3421`) itself is unchanged: sources outstanding POs (`status IN (received, partial)`, `:3332`), aged from `received_date + supplier.payment_terms` (`:3378-3379`), fully paid POs excluded, supplier bank details decrypted via `decrypt_field()` (`:3393-3395`) before display, per-PO AP uses journal-posted credits with a `total_amount` fallback only when no journal entry exists (`:3339-3358`, `:3405`).
- Reversal-awareness (2026-07-13 fix) re-confirmed unchanged at all five call sites: `payroll.py` Rule 7 (`:2202`), creditors-aging (`:3350`), per-PO AP lookup (`:2674`), `purchase_orders.py` `pay_po` (`:445`), `financial_statements.py` AP-reconciliation query (`:558`); `journal.py` backfill carries the same filter (`:1158`).
- **New issue:** `zuzan-backend/companies.py`'s new `POST /companies/clear-data` endpoint (added this run's diff window, function starts `:215`) lets a company owner selectively wipe data by category (`sales`, `expenses`, `customers`, `suppliers`, `employees`, `inventory`, `banking`, `budgets_assets`, `documents` — `_CLEARABLE`, `:212-213`). Journal entries are only purged when the selection intersects `financial_cats = {"sales", "expenses", "employees", "banking"}` (`:246`, gate at `:250`). **`suppliers` is not a member of `financial_cats`.** If a user ticks only "Suppliers & Purchases" (exposed identically in both UI surfaces — Settings' "Clear Trial Data" panel, `App_js_fixed.js:9540` `OPTS` array, and the pre-subscribe "Going Live" modal, `App_js_fixed.js:14992` checkbox list), the endpoint deletes every `Supplier` and `PurchaseOrder`/`PurchaseOrderItem` row (`:276-286`) but leaves every journal entry with `source IN ("purchase_order", "purchase_order_reversal")` in place, since those are only posted by `journal.post_po_received`/`post_po_paid` (`journal.py:786, 838`) and nothing in the clear-data path reverses or deletes them.
  - **Effect on this audit's Creditors/Balance-Sheet reconciliation:** the Creditors Aging report (built live from `PurchaseOrder` rows) would correctly show **zero** outstanding creditors, while the Balance Sheet's Creditors Control account (2000) — built from the AP-reconciliation journal query at `financial_statements.py:558` and Rule 7 at `payroll.py:2236` — would still carry the balance from the now-deleted POs, since those checks sum `JournalLine` rows, not `PurchaseOrder` rows. This is exactly the AR/AP-vs-ledger mismatch this checklist's §5 (cross-module consistency) exists to catch.
  - `journal.backfill_company` (`journal.py:1012` onward) cannot self-heal this: it only **adds** missing entries for records that still exist in the DB (iterates live `Invoice`/`Expense`/etc. rows); it has no logic to reverse or remove entries whose source record has been deleted, so the orphaned AP balance is permanent until manually journaled out.
  - The same gap applies to `budgets_assets` (also excluded from `financial_cats`, `:328`): `fixed_assets.py` posts acquisition (`:347-352`), disposal (`:424-429`) and depreciation (`:646-650`) journal entries, all of which would be orphaned the same way if a user clears "Budgets & Fixed Assets" alone — corrupting the Balance Sheet's fixed-asset/accumulated-depreciation lines and (via depreciation) the Reports expense/EBIT figures, without a corresponding `FixedAsset` record left to reconcile against.
- **Not an issue:** the `Payment` model imported for this endpoint (`companies.py` new import block) is the PayFast subscription-billing payment record (`database.py:464`), unrelated to invoice/AR payments — its import is simply unused by the new function, a harmless dead import, not a data-integrity risk.

## 5. Cross-module consistency

**Same root cause as §4 — restated here because it's a cross-module (journal vs. sub-ledger) reconciliation gap, which is this section's explicit remit.**

- Journal coverage for the five required transaction types is unchanged and confirmed present: `post_invoice_paid` (`journal.py:371`), `post_payroll` (`:505`), `post_expense_paid` (`:757`), `post_po_received` (`:786`), `post_po_paid` (`:838`).
- Balance sheet control-account reconciliation (Rule 6 / AR / `payroll.py:2160`, Rule 7 / AP / `:2236`) still correctly excludes `source == "import"` lines — unchanged.
- Import-awareness (2026-07-11 fixes) unchanged and confirmed intact in `csv_import.py`: exchange rate read from the import row (`:458-487`), unbalanced import groups rejected (`:1035-1077`), `source="import"` tagging consistent (`:791, 869, 957, 1077`); imported equity/asset/liability offsets (3998/3999) still present in `payroll.py`'s `balance_sheet()` (`:1961-1970`).
- **New gap:** the `clear-data` endpoint (§4) is a **sixth way data can leave the sub-ledgers** that this checklist's existing reconciliation logic was never designed to detect, because it assumes sub-ledger rows and their journal entries are only ever added or reversed via the normal invoice/expense/PO/payroll flows (which always keep the two in step) — not bulk-deleted independently of the journal. Rule 6/7 and the AP-reconciliation query would report a **mismatch** (ledger balance with no supporting sub-ledger rows) after a partial clear-data run touching `suppliers` or `budgets_assets` without also touching a `financial_cats` category — which is a detectable symptom, but only after the fact, and nothing currently surfaces it to the user at the point they trigger the clear.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (per `financial_statements.py`'s `meta.basis` field). File is byte-identical to the 09-25 baseline (`git diff` empty) — no code changes to verify.

**Standards status (fresh web search this run, 27 September 2026):** no change since 09-25.
- **IFRS 18** *Presentation and Disclosure in Financial Statements* — still effective for annual periods beginning on/after 1 January 2027, early application permitted; not yet applicable to IFRS-for-SMEs preparers such as ZuZan's target companies. (KPMG, IAS Plus, EY ZA and others all still cite the 1 Jan 2027 date as of this run.)
- **IFRS for SMEs third edition** — still effective 1 January 2027; no new ZuZan-relevant scope change found this run beyond what was already noted 09-25.
- **VAT Act s7(4) Constitutional Court case** — still no judgment issued as of this run. Fresh search confirms the Constitutional Court hearing (27 August 2026) remains in "reserved judgment" status; no ruling reported. No code impact.

**Section 5b — deferred tax:** already implemented (not hard-coded to 0.0); re-confirmed present and unchanged this run:
- `_deferred_tax_balance()` (`financial_statements.py:131`) still defined; opening/closing balances still computed at `:266-267`.
- `FixedAsset.wear_and_tear_rate` column (`database.py:543`) and its `ALTER TABLE` migration (`database.py:1507`, inside the migrations list literal) both still present.
- No changes to `financial_statements.py` or `database.py` this run (`git diff` empty), so the full mechanics verified line-by-line on 09-25 (tax-base computation, Note 9 `deferred_tax`/`total_tax`, balance-sheet Deferred Tax Liability/Asset lines with matching retained-earnings offset, statement-of-changes-in-equity opening adjustment, zero-fixed-assets safety case) stand without re-derivation.

Finance costs (2026-07-13 fix): confirmed unchanged — interest lines (account `6700` or name-matched) presented below EBIT (`financial_statements.py:204-211`); `profit_before_tax = ebit - finance_costs` (`:259`); `tax_expense`/`net_profit` derive from `profit_before_tax`, not EBIT.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date.

**PAYE brackets, rebates, UIF ceiling** — fresh web search this run finds no rate-change news since 09-25; code re-confirmed unchanged (`payroll.py`):
- `TAX_YEARS["2026/2027"]` present at `:132`; `TAX_YEARS["2027/2028"]` (flagged `"provisional": True`) at `:152` — standing placeholder, unchanged.
- `UIF_RATE = 0.01` (`:189`) and `SDL_RATE = 0.01` (`:190`) — no rate-change news found; both remain correct (1%/1% employee-employer UIF, 1% SDL).

**Company tax:**
- `CORP_TAX_RATE = 0.27` (`:3151`) — CIT remains flat 27%, unchanged and correct.
- `VAT_RATE = 0.15` confirmed unchanged at all three sites (`:2032, 2426, 3507`) — standard VAT rate remains 15%; the Constitutional Court matter (§6) has not produced a rate change.
- No new SARS threshold or rate change found this run.

**Sources consulted this run:** [IAS Plus — Effective date of IFRS 18](https://www.iasplus.com/en/events/effective-dates/2027/ifrs-18) · [KPMG — IFRS 18](https://kpmg.com/xx/en/what-we-do/services/audit/corporate-reporting-institute/ifrs/presentation-and-disclosure/ifrs18.html) · [EY South Africa — IFRS 18 practical application insights, June 2026](https://www.ey.com/en_za/media/webcasts/2026/06/fru-june-2026) · [eNCA — ConCourt reserves judgment, Finance Minister's power to change VAT rate](https://www.enca.com/news-top-stories/concourt-reserves-judgment-finance-ministers-power-change-vat-rate) · [Polity — DA's ConCourt hearing against VAT Act underway](https://www.polity.org.za/article/das-concourt-hearing-against-vat-act-underway-2026-08-27) · [BusinessDay — SARS and Treasury ask top court to overturn ruling on minister's VAT powers](https://www.businessday.co.za/news/2026-08-28-sars-and-treasury-ask-top-court-to-overturn-ruling-on-ministers-vat-powers/) · [SARS — Rates of Tax for Individuals](https://www.sars.gov.za/tax-rates/income-tax/rates-of-tax-for-individuals/) · [SARS — Budget 2026 Frequently Asked Questions](https://www.sars.gov.za/about/sars-tax-and-customs-system/budget/budget-2026-frequently-asked-questions/) · [Joburg ETC — South Africa's tax changes in 2026](https://www.joburgetc.com/business/south-africa-tax-changes-2026/)

## 8. Action items

1. **✅ FIXED (same day, post-report):** `zuzan-backend/companies.py` — the blanket `financial_cats` journal wipe was replaced with source-scoped clearing (`_CATEGORY_JOURNAL_SOURCES` / `_clear_journal_for_sources()`) covering every clearable category that can post to the journal, including `suppliers`, `budgets_assets` and `inventory`. See the addendum at the top of this report for detail and verification. **Not yet committed to git** — recommend committing before the "Clear Trial Data" / "Going Live" feature is used by any live/converting trial company.
2. **Medium (carried over unchanged from 09-25):** the frontend's `DEFAULT_COA`/`journal.py` code-mismatch — collision component renumbered (`5010`-`5050`) and mitigated by auto-vivify fallback; `Expense.category` strings posted under the *old* routing pre-2026-09-18 remain wrongly classified and not retroactively reposted. Still recommend a one-off reconciliation pass over historical expense postings.
3. **Low (repo hygiene, unchanged this run):** `zuzan-backend/` still has the same four `.fuse_hidden*` files (dated 14 & 21 Sep, no new ones since 09-25). **User action:** delete manually via Windows Explorer.
4. **Low (data freshness, standing):** MIBCO Sector 5 Year 2 employee health-scheme contribution remains officially "TBC" industry-wide — re-check on the next run that specifically touches payroll/MIBCO logic, or at minimum monthly.
5. **Informational, not an action item:** the four commits since 09-25 (`2dc10ec`, `1edd74e`, `d177cd4`, `a89e3cc`) all carry the same reused/inaccurate commit message describing unrelated older work ("payroll advances… tiered payroll pricing… integrations 500 FK order… journal CASCADE migration") when the actual diff only touched `companies.py` and the frontend clear-data UI. This doesn't affect application behaviour but makes `git log` unreliable for change-detection audits like this one going forward — worth tightening the commit script's message generation if this is scripted.

**No other new Critical/High/Medium findings this run.**

**Standing reminders (carried from prior reports, unchanged unless noted):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry after Budget Feb 2027 and restart the backend;
(b) early-2027 runs should execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`);
(c) the AFS PayFast payment/ad-hoc tokenization feature and `/reports/ai-insights` remain outside this audit's scope;
(d) NBCPSS/MIBCO payroll calculation detail remains outside this checklist's explicit scope except where it produces an in-scope journal-integrity failure;
(e) the imported-equity-offset (3998/3999) exclusion logic lives in `payroll.py`'s `balance_sheet()`, not `financial_statements.py`;
(f) next run should keep checking for the outcome of Treasury/SARS's review of the 2026 draft TLAB/TALAB submissions;
(g) `parent_company_id`/`user_type`, bookkeeper-onboarding, consolidated-billing, accountant-fee-structure, and accountant-practice-dashboard/`billing_exempt` features remain outside scope, awareness only;
(h) provisional tax modelling (13-week cash flow) — monitor accuracy against real company data once available;
(i) compulsory VAT-registration turnover threshold is R2,300,000 (voluntary R120,000), effective 1 April 2026 — not gated anywhere in-scope, awareness only;
(j) the persistent Chart of Accounts feature (`/coa` router) custom-account routing gap is closed; broader DEFAULT_COA/journal code-mismatch is Medium per action item 2;
(k) the invoice header-image upload, custom HTML invoice template, and service-item catalogue remain additive presentation/picklist features outside scope;
(l) the IASB's SME consolidation-exception Exposure Draft comment period closed 9 September 2026; check next run for the IASB's post-consultation decision;
(m) the Constitutional Court has reserved judgment (heard 27 August 2026) on Section 7(4) of the VAT Act; still no ruling as of this run — monitor;
(n) the `/integrations/invoice` (SMT) endpoint remains formally in-scope going forward — spot-check with a real create + re-post cycle once real SMT traffic exists;
(o) `POST /accountant/sync-customers` remains tracked given its proximity to Debtors scope;
(p) the employee time-clock system (`clock.html`, `clocking.py`) remains additive with no journal/AR/AP/Reports touchpoints, awareness only;
(q) mass payslip ZIP download remains a read-only export feature with no journal/AR/AP/Reports touchpoints — awareness only;
(r) the CGT annual exclusion increase (R40,000 → R50,000, Budget 2026) is a personal-tax item outside this checklist's company/payroll-tax scope, awareness only;
(s) **new standing item:** `zuzan-backend/companies.py`'s `/companies/clear-data` endpoint (and its two frontend entry points) is now in-scope for future runs given its ability to affect AR/AP/Balance-Sheet data — re-verify action item 1 is fixed on the next run, and check for any further categories added to `_CLEARABLE` that might carry the same journal-orphaning risk.
