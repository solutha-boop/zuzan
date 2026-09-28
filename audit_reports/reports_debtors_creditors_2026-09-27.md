# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 27 September 2026 (follow-up run, 22:19 UTC)
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-09-27, filed 13:24 UTC (PASS, one High finding + same-day addendum noting an uncommitted fix)

**Why this run exists:** this is a second firing of the scheduled audit on the same calendar day. Between the 13:24 report and now, the repo moved from `a89e3cc` (HEAD at report time) to `f5cf4e1` across 13 more commits. This run's job is to (1) confirm the addendum's uncommitted fix actually landed correctly, and (2) check whether anything else that shipped in those 13 commits touches this checklist's scope.

**Change detection:** `git diff --stat a89e3cc HEAD` (report-time HEAD → now) touches exactly three files: `App_js_fixed.js` (+107/-16), `zuzan-backend/companies.py` (+83/-16), `zuzan-backend/main.py` (+28). `git diff --stat f480d17 HEAD` (last fully-verified baseline → now) confirms **every other in-scope file — `payroll.py`, `suppliers.py`, `customers.py`, `purchase_orders.py`, `journal.py`, `database.py`, `financial_statements.py`, `csv_import.py` — remains byte-identical** to the state fully verified on 09-25. All anchor line numbers cited below were spot-checked with fresh `grep`/line-range reads this run and match exactly.

Of the three touched files:
- **`companies.py`**: this is the addendum's fix landing for real. Reviewed in full — see §4/§5 (now resolved).
- **`main.py`** (+28): a new `POST /admin/api/clients/{id}/activate` endpoint and matching admin-dashboard button, to manually flip `subscription_status` to `active` when a PayFast ITN webhook is missed. Pure billing/admin — does not touch invoices, expenses, payroll, POs, journal, or any Reports/AR/AP/AFS/tax code path. Out of this checklist's scope; no issues found in what was reviewed.
- **`App_js_fixed.js`** (+107/-16): the "Clear Trial Data" Settings panel (calls the same `/companies/clear-data` endpoint reviewed in §4) plus a `cancel-subscription` flow rework (`/companies/me` PUT → `/companies/cancel-subscription` POST) and a hooks-ordering bugfix (`09b7c4a`). None of this touches Debtors/Creditors/Reports display logic — reviewed and confirmed no interaction beyond the already-audited clear-data endpoint.

The other 13 commits since `a89e3cc` (`cce6145`, `fba5e3d`, `2f8d520`, `7af4ccf`, `c6bb4d0`, `d18dded`, `09b7c4a`, `ea90e8a`, `a49d679`, `d30c260`, `869a5f0`, `f5cf4e1`) net out to that same three-file diff — several of them are superseding re-commits of work-in-progress (identical reused commit-message blocks, noted again in action item 5) rather than thirteen independent changes.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ✅ PASS — unchanged, re-confirmed |
| Debtors (AR) | ✅ PASS — unchanged, re-confirmed |
| Creditors (AP) | ✅ **RESOLVED** — the 13:24 report's High finding is now committed (`d30c260`+) and independently re-verified correct |
| Cross-module consistency | ✅ **RESOLVED** — same fix closes the Balance Sheet reconciliation gap |
| IFRS compliance (AFS) | ✅ PASS — no standards changes; deferred tax (5b) unchanged and re-confirmed present |
| Tax updates (SARS) | ✅ PASS — 2026/2027 tables current, no rate changes |

**Overall: PASS.** The one open item carried from this morning's report — the `clear-data` journal-orphaning gap — is now fixed, committed, and independently re-verified against the actual `journal.py` source-string conventions (not just re-read). No new Critical/High findings this run. Two unrelated billing/admin features shipped in the same commit range; reviewed and found out of scope with no interaction with audited logic.

## 2. Reports

✓ No issues found. `payroll.py` and `main.py`'s report/summary code is byte-identical to the 09-25 baseline; anchors re-confirmed this run:

- `payroll.py` `dashboard()` (`:1649`): `total_revenue = sum(_to_zar(i) for i in paid_invoices)` (`:1661`); `total_outstanding = sum(_to_zar(i) for i in outstanding_invoices)` (`:1669`) — both route every invoice through `_to_zar()`, so non-ZAR invoices convert via `paid_amount_zar`/`exchange_rate` rather than being summed in foreign-currency units.
- Expenses and PO-received COGS are separate expense-side aggregates in the same function; payroll cost is pulled from `Payslip.total_cost`. None of the three overlap with the revenue sum.
- `management_accounts()` (`:2860`): `total_outstanding` (`:2969`) also uses `_to_zar()`; the revenue-trend loop applies the same conversion on every iteration (unchanged from 09-25's verified `:2986`).
- `main.py` `/v1/summary`: unaffected by this run's diff (diff was confined to the admin-activate endpoint, elsewhere in the file); `_to_zar()` usage there is unchanged from the 09-25 baseline.

## 3. Debtors

✓ No issues found. Unchanged since 09-25; anchors re-confirmed:

- `debtors_aging()` (`payroll.py:3252`): filters to `Invoice.status.in_([sent, overdue])`, excludes `paid`; ZAR equivalents via `_to_zar()`; aged from `due_date` (with a `not_due` bucket for invoices lacking one); buckets `not_due`/`current`/`31_60`/`61_90`/`over_90` correctly bounded.
- The "Clear Trial Data" UI (new this run, `App_js_fixed.js`) only reaches this data through the already-reviewed `/companies/clear-data` endpoint. With today's fix, ticking "Sales" now correctly clears the `invoice`/`invoice_payment`/`invoice_cogs` journal postings alongside the invoice rows themselves — no orphaned AR journal balance can result from this path any more (see §4).

## 4. Creditors — finding from this morning, now resolved

**Recap of the finding (filed 13:24 today):** `companies.py`'s new `/companies/clear-data` endpoint only purged journal entries when the selected categories intersected a hard-coded `financial_cats = {"sales","expenses","employees","banking"}` set. `suppliers` and `budgets_assets` were excluded from that set, so clearing either one deleted the underlying `Supplier`/`PurchaseOrder` or `FixedAsset` rows while leaving their journal postings (`purchase_order`, `po_payment`, `fixed_asset`, `depreciation`, `asset_disposal`) permanently orphaned — the Creditors Aging report would correctly show zero, while the Balance Sheet's Creditors Control (2000) and fixed-asset/accumulated-depreciation lines would still carry the deleted records' balances.

**Fix, as committed (`companies.py`, landed in commit `d30c260` and confirmed present at HEAD `f5cf4e1`):**
- A `_CATEGORY_JOURNAL_SOURCES` dict (`companies.py:224-234`) maps every one of the 9 `_CLEARABLE` categories (`companies.py:212-213`) to the journal `source` value(s) it owns.
- `_clear_journal_for_sources()` (`companies.py:236-254`) deletes exactly the `JournalLine`/`JournalEntry` rows whose `source` (or `source + "_reversal"`) is in the selected categories' set — replacing the old blanket "delete every journal entry for the company" behaviour (`companies.py:308-313` now scopes per-category instead of a company-wide wipe).

**Independent re-verification this run (not just re-reading the report's claim):** I cross-checked every entry in `_CATEGORY_JOURNAL_SOURCES` against the actual `source=` string each `journal.py` posting function passes to `_make_entry()`, by reading the function bodies directly rather than trusting the map's comment:

| Category | Map lists | Actual `journal.py` source string(s) | Match |
|---|---|---|---|
| `sales` | `invoice`, `invoice_payment`, `invoice_cogs` | `post_invoice_raised`→`"invoice"` (`:345`), `post_invoice_paid`→`"invoice_payment"` (`:378`), `post_invoice_cogs`→`"invoice_cogs"` (`:414`) | ✓ |
| `expenses` | `expense`, `expense_payment` | `post_expense`→`"expense"` (`:446`), `post_expense_paid`→`"expense_payment"` (`:769`) | ✓ |
| `employees` | `payroll` | `post_payroll`→`"payroll"` (`:597`) | ✓ |
| `banking` | `bank_import_income` | `post_bank_income`→`"bank_import_income"` (`:486`) | ✓ |
| `suppliers` | `purchase_order`, `po_payment` | `post_po_received`→`"purchase_order"` (`:820`), `post_po_paid`→`"po_payment"` (`:850`) | ✓ |
| `budgets_assets` | `fixed_asset`, `depreciation`, `asset_disposal` | `post_asset_acquisition`→`"fixed_asset"` (`:916`), `post_depreciation`→`"depreciation"` (`:942`), `post_asset_disposal`→`"asset_disposal"` (`:977`) | ✓ |
| `inventory` | `stock_adjustment` | `post_stock_adjustment`→`"stock_adjustment"` (`:878`) | ✓ |
| `customers`, `documents` | (none — correctly commented as owning no journal source) | no `_make_entry` call posts under either name | ✓ |

All 7 mappings are exact; the reversal suffix (`f"{source}_reversal"`, matching `journal.py:1226`'s own reversal-posting convention) is applied uniformly. There is no remaining category in `_CLEARABLE` whose journal postings would be left orphaned by a partial clear. This closes both halves of the original bug (the `suppliers`/`budgets_assets` omission, and the separate over-broad blanket-delete-on-any-financial-category behaviour the addendum also flagged).

**Rest of the Creditors logic (unchanged, re-confirmed):**
- `creditors_aging()` (`payroll.py:3315`): sources POs with `status IN (received, partial)`, aged from `received_date + supplier.payment_terms`, fully-paid POs excluded, supplier bank details decrypted via `decrypt_field()` before display.
- Reversal-awareness (2026-07-13 fix) still intact at all five call sites — Rule 7 (`payroll.py:2202`), creditors-aging (`:3350`), per-PO AP lookup (`:2674`), `purchase_orders.py` `pay_po` (`:445`), `financial_statements.py` AP-reconciliation query (`:558`); `journal.py` backfill carries the same filter (`:1158`).

**Verdict: this finding is closed.** Not merely "fixed pending commit" as this morning's report stated — it is now committed to `main` and independently verified line-by-line against the real journal source strings, not just against the fix's own inline comment.

## 5. Cross-module consistency

- Journal coverage for the five required transaction types unchanged and confirmed present: `post_invoice_paid` (`:378`), `post_payroll` (`:597`), `post_expense_paid` (`:769`), `post_po_received` (`:820`), `post_po_paid` (`:850`).
- Balance-sheet control-account reconciliation (Rule 6/AR `payroll.py:2160`, Rule 7/AP `:2236`) still correctly excludes `source == "import"` lines — unchanged.
- Import-awareness (2026-07-11 fixes) unchanged in `csv_import.py`: exchange rate read from the import row, unbalanced import groups rejected, `source="import"` tagging consistent, 3998/3999 offsets still present in `payroll.py`'s `balance_sheet()`.
- **The gap flagged this morning — `clear-data` as a "sixth way data can leave the sub-ledgers" that bypasses the normal add/reverse flow — is now closed** by the same `_CATEGORY_JOURNAL_SOURCES` fix (§4): every category that can post to the journal is now purged in lock-step with its own journal entries, so no partial-clear scenario can produce a ledger-vs-sub-ledger mismatch any more. Standing item (s) from the last report ("re-verify action item 1 is fixed") is satisfied.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (per `financial_statements.py`'s `meta.basis`). File is byte-identical to the 09-25/09-27-morning baseline (`git diff` empty against `f480d17`) — no code changes to verify this run.

**Standards status — re-checked this run (fresh search, 27 September 2026, evening):**
- **IFRS 18** *Presentation and Disclosure in Financial Statements* — still effective for annual periods beginning on/after 1 January 2027; not yet applicable to IFRS-for-SMEs preparers. No change.
- **IFRS for SMEs 3rd edition** — still effective 1 January 2027. No change.
- **VAT Act s7(4) Constitutional Court case:** a headline surfaced this run ("VAT Act section declared invalid as court finds it gives finance minister too much power," The Citizen) that could plausibly read as a fresh Constitutional Court ruling. Fetched and checked directly: it is dated **5 March 2026** and reports the **Western Cape High Court's** original judgment (Judge Matthew Francis), not a Constitutional Court decision — the same ruling already known from prior audits, which suspended its declaration of invalidity for 24 months and referred the matter to the Constitutional Court for confirmation. The Constitutional Court hearing (27 August 2026) remains in reserved-judgment status; no confirmation ruling found as of this run. No code impact.

**Section 5b — deferred tax:** already implemented; re-confirmed present and unchanged (fresh `grep`, not just diff-absence):
- `_deferred_tax_balance()` defined (`financial_statements.py:131`); opening/closing computed at `:266-267`; `deferred_tax_expense` folded into `total_tax` at `:601-606`; closing/opening balances disclosed at `:609-610`; equity offset at `:681`.
- `FixedAsset.wear_and_tear_rate` column (`database.py:543`) and its `ALTER TABLE` migration (`database.py:1507`, inside the migrations list literal) both present.
- No changes to `financial_statements.py` or `database.py` this run — the full mechanics verified line-by-line on 09-25 stand without re-derivation.

**Finance costs (2026-07-13 fix):** unchanged — interest lines presented below EBIT; `profit_before_tax` (not EBIT) feeds `tax_expense`/`net_profit`.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date.

Re-confirmed by direct `grep` this run (not carried forward from memory):
- `TAX_YEARS["2026/2027"]` present at `payroll.py:132`; `TAX_YEARS["2027/2028"]` (provisional placeholder) at `:152`.
- `UIF_RATE = 0.01` (`:189`), `SDL_RATE = 0.01` (`:190`) — 1%/1% correct.
- `CORP_TAX_RATE = 0.27` (`:3151`) — CIT flat 27%, correct.
- `VAT_RATE = 0.15` at all three sites (`:2032, 2426, 3507`) — standard VAT rate 15%, correct.

**Fresh web search this run:** no SARS rate-change announcements found since this morning's report; both searches ("VAT Act ... Constitutional Court ... September 2026" and "SARS tax rate change announcement September 2026") returned only previously-known items (the March 2026 High Court ruling, general 2026/2027 tax-table reference pages, filing-season notices). No new threshold, bracket, rebate, or VAT-rate news.

**Sources consulted this run:**
- [The Citizen — VAT Act section declared invalid as court finds it gives finance minister too much power](https://www.citizen.co.za/news/south-africa/courts/vat-act-section-declared-invalid-unconstitutional/) (confirmed: 5 March 2026, Western Cape High Court, not a new ConCourt ruling)
- [BusinessTech — Big VAT changes on the cards for South Africa](https://businesstech.co.za/news/government/872697/big-vat-changes-on-the-cards-for-south-africa/)
- [Polity — DA's ConCourt hearing against VAT Act underway](https://www.polity.org.za/article/das-concourt-hearing-against-vat-act-underway-2026-08-27)
- [EWN — Godongwana's lawyers urge ConCourt to uphold VAT Act provisions](https://www.ewn.co.za/2026/08/27/godongwanas-lawyers-urge-concourt-to-uphold-vat-act-provisions-for-sound-fiscal-administration)
- [BusinessDay — SARS and Treasury ask top court to overturn ruling on minister's VAT powers](https://www.businessday.co.za/news/2026-08-28-sars-and-treasury-ask-top-court-to-overturn-ruling-on-ministers-vat-powers/)
- [SARS — What's New at SARS](https://www.sars.gov.za/whats-new-at-sars/)
- [SARS — Tax Rates](https://www.sars.gov.za/tax-rates/)
- [SARS — Changes for Filing Season 2026](https://www.sars.gov.za/latest-news/changes-for-filing-season-2026/)

## 8. Action items

1. **✅ RESOLVED (this run):** `zuzan-backend/companies.py`'s `/companies/clear-data` journal-orphaning gap (flagged 13:24 today) is now committed (`d30c260`, present at HEAD `f5cf4e1`) and independently re-verified: `_CATEGORY_JOURNAL_SOURCES` matches the real `journal.py` source strings for all 7 journal-posting categories, one-for-one, including the previously-missing `suppliers`/`budgets_assets`/`inventory`. Downgrading from "Fixed, pending commit" to closed. No further action beyond ongoing awareness (see standing item (s)).
2. **Medium (carried over unchanged from 09-25/09-27):** the frontend's `DEFAULT_COA`/`journal.py` code-mismatch — collision component renumbered (`5010`-`5050`), auto-vivify fallback mitigates going forward, but `Expense.category` strings posted under the *old* routing pre-2026-09-18 remain wrongly classified. Still recommend a one-off reconciliation pass over historical expense postings.
3. **Low (repo hygiene):** `zuzan-backend/` now has **five** `.fuse_hidden*` stray files, not four — a new one (`.fuse_hidden0000000c00000005`, 13:22 today) joined the four already carried over from 14/21 September. These are harmless FUSE/editor artifacts. **User action:** delete manually via Windows Explorer.
4. **Low (data freshness, standing):** MIBCO Sector 5 Year 2 employee health-scheme contribution remains officially "TBC" industry-wide — re-check on the next run that specifically touches payroll/MIBCO logic, or at minimum monthly.
5. **Informational:** commit-message hygiene has not improved — of the 13 commits since this morning's report, 8 still carry the identical reused/inaccurate message block ("trial-to-live data selection modal… tiered payroll pricing… integrations 500 FK order… journal CASCADE migration") regardless of what each commit actually changed, and several also show mangled em-dash encoding (`ÔÇö`) suggesting a non-UTF-8 commit-message pipeline. `git log` remains unreliable for change-detection audits; this run relied on `git diff --stat` against known-good commit hashes instead. Worth fixing the commit script's encoding and message generation.
6. **New, informational only — not a defect:** two billing/admin features shipped in this run's diff window (`POST /companies/cancel-subscription` in `companies.py`+`billing.py`, and `POST /admin/api/clients/{id}/activate` in `main.py`) are outside this checklist's Reports/AR/AP/AFS/tax scope and were reviewed only for interaction with audited logic (none found). Flagging so a future run scopes them in if PayFast subscription state is ever wired into billing-exempt/CIT logic.

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
(m) the Constitutional Court has reserved judgment (heard 27 August 2026) on Section 7(4) of the VAT Act; still no ruling as of this run — monitor (re-confirmed this run, see §6);
(n) the `/integrations/invoice` (SMT) endpoint remains formally in-scope going forward — spot-check with a real create + re-post cycle once real SMT traffic exists;
(o) `POST /accountant/sync-customers` remains tracked given its proximity to Debtors scope;
(p) the employee time-clock system (`clock.html`, `clocking.py`) remains additive with no journal/AR/AP/Reports touchpoints, awareness only;
(q) mass payslip ZIP download remains a read-only export feature with no journal/AR/AP/Reports touchpoints — awareness only;
(r) the CGT annual exclusion increase (R40,000 → R50,000, Budget 2026) is a personal-tax item outside this checklist's company/payroll-tax scope, awareness only;
(s) `zuzan-backend/companies.py`'s `/companies/clear-data` endpoint (and its two frontend entry points) remains in-scope for future runs given its ability to affect AR/AP/Balance-Sheet data — action item 1 is now confirmed fixed and committed (this run); re-verify again if `_CLEARABLE` or `_CATEGORY_JOURNAL_SOURCES` change, and note the endpoint now also has a `cancel-subscription` sibling (action item 6) worth folding into scope alongside it.
