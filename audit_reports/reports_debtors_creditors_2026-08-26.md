# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 26 August 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-08-25 (full PASS).

**Change detection since last run:** `git log` shows two new commits after the 08-25 audit — `30a67a0` and `817b882` (25 Aug, 21:51 / 22:03), "13-week rolling cash flow forecast in Budgeting/Planning — backend `/reports/cash-flow-13week` endpoint + frontend `ForecastView`". `git diff c132a93..817b882 -w --stat` shows: `payroll.py` (+113, new endpoint only, appended after `cash_flow()`), `main.py` (1 line — the recurring cosmetic `_SubscriptionGateMiddleware` comment-duplication artifact, item (i) from prior reports, grew again), `billing.py` (+2 — same duplication pattern now hit `resp = None` in `adhoc_charge()`, three copies instead of one), `App_js_fixed.js` / `zuzan-app/src/App.js` (+282 each, new `ForecastView` component, kept in sync). **Zero diff** in `financial_statements.py`, `journal.py`, `database.py`, `purchase_orders.py`, `suppliers.py`, `customers.py`, `csv_import.py`, `companies.py` — all in-scope AR/AP/AFS/tax logic untouched. Working tree shows the usual CRLF-only "modified" flags on `auth.py`/`billing.py`/`companies.py`/`main.py`/`payroll.py` (`git diff -w` → 0 lines), the known deploy-pipeline artifact.

Re-verified high-risk anchors via Grep — all unchanged: `"deferred_tax": 0.0` → no matches in `financial_statements.py`; `wear_and_tear_rate` present in `database.py`; `purchase_order_reversal` present in `payroll.py`, `financial_statements.py`, `journal.py`, `purchase_orders.py`; `source == "import"` exclusion present in `payroll.py`; `CURRENT_TAX_YEAR`/`VAT_RATE`/`S11F_CAP` present and unchanged in `payroll.py`.

**Out-of-scope but flagged (Critical, security):** a plaintext file named `ghp_w0vWd0jgV1yFdHb9NODeqLMx5jlKOz3.txt` sits in the repo root (`C:\Zuzan\`, untracked) and its contents are a live-looking GitHub personal access token (`ghp_` + 36 chars — standard classic-PAT format) matching the filename. This is not part of the Reports/Debtors/Creditors/AFS/tax checklist, but a credential sitting in a synced project folder is a real exposure risk — see Action Items §8(0).

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary / new 13-week forecast) | ✅ PASS — core logic unchanged; new forecast endpoint reviewed, one gap noted |
| Debtors (AR) | ✅ PASS — aged from due_date, paid excluded, ZAR amounts |
| Creditors (AP) | ✅ PASS — reversal-aware, bank details decrypted |
| Cross-module consistency | ✅ PASS — full journal coverage, import-awareness intact |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) re-verified, no regressions |
| Tax rates (SARS) | ✅ PASS — 2026/2027 tables current, no rate changes |

**Overall: PASS.** Two new commits added a 13-week rolling cash-flow forecast feature (new endpoint, additive only) — reviewed below. No regressions to audited Reports/Debtors/Creditors/AFS/tax logic. One new medium-severity observation on the forecast feature's outflow coverage; one unrelated critical security finding (leaked credential file) flagged for awareness.

---

## 2. Reports

✓ No issues found in previously-audited endpoints (dashboard, management accounts, `/v1/summary`) — all unchanged, logic re-verified against the 08-25 baseline.

**New: `GET /reports/cash-flow-13week` (`payroll.py:1991-2098`)** — forward-looking 13-week cash-flow forecast, additive feature, does not touch existing dashboard/management/summary code paths.
- Invoice receipts per week correctly filtered to `InvoiceStatus.in_([sent, overdue])` (excludes paid, consistent with the AR/Debtors definition used elsewhere) and bucketed by `due_date`, converted via `_to_zar()` — consistent with the rest of the app's multi-currency handling (`payroll.py:2033-2039`).
- Recurring income pulled from `RecurringInvoice.next_run_date`, VAT applied when `vat_applicable` (`payroll.py:2042-2049`) — correct model fields confirmed in `database.py:947-965`.
- Payroll projected via trailing 13-week average net pay, attributed to the last calendar day of each month (`payroll.py:2052-2059`) — reasonable heuristic, clearly a forecast not an actual.
- Operating expenses use a flat trailing 8-week average per week (`payroll.py:2003-2010`), applied identically to every one of the 13 weeks.
- **Gap (Medium):** the forecast has no query against `PurchaseOrder`/creditors data — `other_payments` and `vat_payment` are hard-coded to `0.0` for every week (`payroll.py:2073-2074`), and outstanding AP (received-but-unpaid POs) is not surfaced as a distinct weekly outflow; it would only be implicitly smoothed inside the flat 8-week expense average if POs were previously expensed, which understates outflows in weeks where large PO payments or VAT201 payments actually fall due. The frontend does let users manually override cells, so this is not a correctness bug so much as an incomplete forecast — but it's an asymmetry worth flagging since Debtors receipts are modeled from real due-date data while Creditors/VAT outflows are not modeled at all.

## 3. Debtors

✓ No issues found.
- Invoice status filter unchanged: `Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.overdue])`, paid invoices excluded from all outstanding-balance calculations.
- Aging buckets keyed off `due_date`, not invoice date.
- ZAR conversion via `_to_zar()` applied consistently, including the new forecast endpoint's per-invoice receipts.

## 4. Creditors

✓ No issues found.
- Reversal-awareness (2026-07-13 fixes) confirmed present at all expected call sites — nets `credit − debit` and includes `purchase_order_reversal` alongside `purchase_order`.
- Supplier bank details decrypted via `decrypt_field` (`suppliers.py`) — unchanged.
- Not surfaced in the new forecast feature (see §2 gap) — no defect in the existing Creditors view itself.

## 5. Cross-module consistency

✓ No issues found.
- Journal coverage complete (`post_invoice_raised` through `post_asset_disposal`, 12+ functions in `journal.py`) — no gaps, unaffected by this run's changes.
- Import-awareness (2026-07-11 fixes) intact: `source == "import"` exclusions on 1100/2000, balance sheet retains 3998/3999 offsets, non-ZAR import exchange-rate requirement and unbalanced-group rejection all unchanged.
- Migration hygiene: `wear_and_tear_rate` column/`ALTER TABLE` still positioned inside the migrations list literal — untouched by this run's commits.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (declared in AFS meta). Statements: income statement, statement of financial position, changes in equity, indirect cash flow, notes 2-9. Unchanged this run.

**Standards status (fresh web search this run):** no material change since 08-25.
- IFRS 18 *Presentation and Disclosure in Financial Statements* — still effective for periods beginning on/after 1 January 2027, not applicable to IFRS-for-SMEs preparers (ZuZan's basis).
- IFRS for SMEs third edition (issued Feb 2025, effective 1 January 2027, early adoption permitted) — no new SA-specific implementation guidance found this run beyond what's already logged in `ifrs_smes_3rd_edition_transition_plan.md`.

**Section 5b — deferred tax:** already implemented; re-verified this run — no `"deferred_tax": 0.0` hard-coding found. Per-asset tax base (cost − cumulative SARS wear-and-tear), temporary difference × 27% CIT rate, opening/closing balance movement driving Note 9 `deferred_tax_expense`, balance-sheet line — all present and unchanged.
- Finance costs (2026-07-13 fix): interest still presented below EBIT, tax/net profit still derive from `profit_before_tax` — unchanged, no regression from this run's commits (which didn't touch `financial_statements.py`).

✓ No issues found.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date.

- Fresh web search this run: the 2026 draft TLAB/TALAB comment period **closes 28 August 2026** (now 2 days away) — still open, no finalized legislative changes to report. Proposals remain as previously logged (living-annuity de minimis, donations-tax spousal exemption residency restriction, SEZ arm's-length principle, Temporary Admission carnets, second-hand goods documentation, VDP interest relief) — none are enacted PAYE/UIF/SDL/CIT/VAT changes.
- PAYE brackets, rebates, UIF ceiling/percentages, SDL rate, S11F cap (`payroll.py:100-196`) — unchanged, matches 2026/2027 SARS tables (top bracket 45% above R1,878,601; primary/secondary/tertiary rebates R17,820/R9,765/R3,249; UIF ceiling R17,712; S11F cap R430,000).
- VAT confirmed 15% (`VAT_RATE = 0.15`, `payroll.py:1608,2691`) — 2025 proposed increases remain reversed.
- CIT confirmed flat 27% — matches dashboard/management/provisional-tax and `financial_statements.py` usage.
- IFRS-for-SMEs web search this run turned up nothing new specific to the SA VAT-registration turnover thresholds beyond what was already logged on 08-25 (compulsory threshold → R2,300,000, voluntary → R120,000, effective 1 April 2026) — still not gated anywhere in the audited files; awareness-only.
- No edits made (report-only per task rules; section 5b already implemented, verification-only this run).

**Sources consulted:** [National Treasury Publishes 2026 Draft Tax Bills for Public Comment — Tax Consulting SA](https://www.taxconsulting.co.za/national-treasury-publishes-2026-draft-tax-bills-for-public-comment/) · [Draft tax law changes could affect donations, VAT, medical tax credits and SARS refunds — IOL](https://iol.co.za/business/advice/2026-08-08-draft-tax-law-changes-could-affect-donations-vat-medical-tax-credits-and-sars-refunds/) · [2026 Draft Tax Bills have been published for comment — GoLegal](https://www.golegal.co.za/2026-draft-tax-bills/) · [The 2026 Draft Tax Bills Are Out. Comment Closes 28 August — Accounting Weekly](https://www.accountingweekly.com/sars-updates/2026-draft-tlab-and-talab-what-accountants-must-know) · [2026 draft TLAB: Key changes for businesses — PvdZ Consulting](https://tax.pvdz.co.za/tlab/) · [National Treasury on publication of the 2026 draft tax bills for comment — gov.za](https://www.gov.za/news/media-statements/national-treasury-publication-2026-draft-tax-bills-comment-30-jul-2026) · [South Africa consults on 2026 draft tax legislation — RegFollower](https://regfollower.com/south-africa-consults-on-2026-draft-tax-legislation/) · [New IFRS for SMEs Conceptual Framework Explained — PKF South Africa](https://www.pkf.co.za/news/2026/ifrs-for-sme-conceptual-framework/) · [Feature: Third edition of the IFRS for SMEs Accounting Standard — Accountancy SA](https://www.accountancysa.org.za/feature-third-edition-of-the-ifrs-for-smes-accounting-standard/) · [IFRS for SMEs Accounting Standard Third Edition (2025) — Nexia SAB&T](https://www.nexia-sabt.co.za/ifrs-for-smes-accounting-standard-third-edition-2025/)

## 8. Action items

1. **Critical (security, out-of-scope but urgent):** `C:\Zuzan\ghp_w0vWd0jgV1yFdHb9NODeqLMx5jlKOz3.txt` contains what appears to be a live GitHub personal access token in plaintext, sitting untracked in the project root of a folder synced via OneDrive. Recommend revoking the token in GitHub settings immediately and deleting the file, regardless of whether it was ever committed to git history (check history too — if it was ever committed, treat it as compromised even after deletion).
2. **Medium:** `/reports/cash-flow-13week` (`payroll.py:1991-2098`) does not model outstanding creditor (PO) payments or VAT201 liabilities as distinct weekly outflows (`other_payments`/`vat_payment` hard-coded `0.0`) — consider pulling due-date-bucketed outstanding POs and the next VAT201 due amount the same way invoice receipts are modeled, so the forecast's outflow side has the same fidelity as its inflow side.

**Standing reminders (not defects, carried from prior reports):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry (`payroll.py`) after Budget Feb 2027 and restart the backend;
(b) early-2027 runs should execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`);
(c) the AFS PayFast payment/ad-hoc tokenization feature and the `/reports/ai-insights` feature remain outside this audit's scope;
(d) NBCPSS private security payroll mode predates this audit's baseline, not yet part of this checklist's explicit scope;
(e) file-attribution note: the imported-equity-offset (3998/3999) exclusion logic lives in `payroll.py`'s `balance_sheet()`, not `financial_statements.py`;
(f) track the 2026 draft TLAB/TALAB (comment period closes 28 August 2026, now 2 days away) — once enacted, re-check whether any finalized provisions require rate/table changes;
(g) `parent_company_id`/`user_type` columns and bookkeeper-onboarding/consolidated-billing/accountant-fee-structure features remain outside Reports/Debtors/Creditors/AFS/tax scope, awareness only;
(h) legacy unused constants `PAYROLL_PER_EMP = 34.00` / `PAYROLL_MIN = 99.00` in `payroll.py` — still worth a cleanup pass, not a compliance issue;
(i) the cosmetic comment/statement-duplication artifact (`_SubscriptionGateMiddleware` line in `main.py`, now also `resp = None` in `billing.py`'s `adhoc_charge()`) keeps recurring across commits — harmless functionally each time, but its spread to a second file strengthens the case for a maintainer to find and fix the auto-generation/merge step producing it;
(j) compulsory VAT-registration turnover threshold rises to R2,300,000 (from R1,000,000), voluntary to R120,000 (from R50,000), effective 1 April 2026 — not gated anywhere in-scope, awareness only;
(k) new: the 13-week cash-flow forecast feature (`payroll.py:1991-2098`, `ForecastView` in `App_js_fixed.js`) is additive and outside the original Reports/Debtors/Creditors checklist's endpoint list — recommend adding it explicitly to this checklist's §1 scope in future runs since it consumes Debtors data directly, and tracking action item 2 above until resolved.
