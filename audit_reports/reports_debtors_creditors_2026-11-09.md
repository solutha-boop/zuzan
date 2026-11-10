# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 9 November 2026 (scheduled run, 22:10 UTC)
**Prior report:** 2026-11-08 (incl. its 2026-11-09 fixes addendum)

**Method:** static review (git log/diff since c08eef3, `ast` parse of payroll, main, csv_import, journal, financial_statements, database, purchase_orders, fixed_assets, companies — all OK; grep anchor checks). No live DB / pytest. **No code edited this run** (5b already implemented).

**Changes since last report:** 14 commits on 2026-11-09 (HEAD a8c00fb). Relevant: (a) financial_statements.py:118-121 `_wt_rate_pct` now converts a decimal-stored `wear_and_tear_rate` (0.20) to a percentage — fixes a deferred-tax understatement bug; fixed_assets.py:53 adds "Generators / UPS systems" IN47 category (5 yrs); (b) plan gating added via new `plans.py` (payroll.py:2906, 3477, 4028, 4285; companies.py:751; auth.py:941; recurring_invoices.py:243); (c) csv_import/main.py fixes from the 11-08 addendum; (d) frontend +185 lines (fixed-assets edit modal).

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | **PASS** — `_to_zar` (payroll.py:23), `VAT_RATE` (payroll.py:20) intact |
| Debtors (AR) | **PASS** — unchanged |
| Creditors (AP) | **PASS** — reversal-aware sources + `decrypt_field` intact; creditors book now plan-gated (see item 2) |
| Cross-module | **PASS (Medium owner action carried)** |
| IFRS (AFS) | **PASS** — deferred-tax rate-unit fix verified |
| Tax (SARS) | **PASS** — 2026/2027 present, no changes found |

**Overall: 0 Critical, 1 High (new), 2 Medium, Lows carried.**

## 2. Reports
✓ No issues found. `_to_zar` payroll.py:23, `VAT_RATE=0.15` payroll.py:20.
- Low (new): payroll.py:3477-3480 — the `cash_flow_13week` docstring now sits after the `from plans import` / plan-check statements, so it is no longer a docstring (cosmetic; OpenAPI description lost). Same pattern at payroll.py:4285-4289 (`creditors_aging`).

## 3. Debtors
✓ No issues found.

## 4. Creditors
✓ No data issues. `purchase_order_reversal` refs: payroll.py 6, purchase_orders.py 2, journal.py 1, financial_statements.py 2. `decrypt_field` for bank_name/account_number/branch_code at payroll.py:4362-4364.
- Medium (new, behavioural): payroll.py:4285 — `/reports/creditors-aging` now requires the **professional** plan (reconciliation at payroll.py:2906 also professional; 13-week cash flow business). Confirm the frontend hides/handles the 403 for Starter users and that Starter is meant to lose the creditors book.

## 5. Cross-module
- Journal coverage (invoice payments, expense payments, PO receipts, PO payments, payroll) unchanged ✓. Journal-integrity run 2026-11-09 06:06: 0 gaps (local SQLite only).
- Import-awareness paths: csv_import.py changed (+243 lines, 11-08 reclassify dry-run fix and `tests/test_import_payments.py` added); not run live.
- Medium (carried): owner to review account types (2000/2100/3xxx/4000) in companies that imported a GL before 2026-11-05 (use `/import/reclassify-gl-accounts?dry_run=true`).

## 6. IFRS compliance (AFS)
- Framework unchanged: IFRS for SMEs (2nd ed.). IFRS 18 and IFRS for SMEs 3rd edition effective for periods beginning on/after 1 Jan 2027 (first affected ZuZan FY starts 1 Mar 2027). No SA-specific change found; transition plan `ifrs_smes_3rd_edition_transition_plan.md` stands.
- **5b deferred tax — verified (not hard-coded):** financial_statements.py:286-288 opening/closing `_deferred_tax_balance`, :672 `total_tax = current + deferred`, :677 `"deferred_tax": deferred_tax_expense`, :752 equity movement; CIT rate single-sourced via `fixed_assets.SA_CIT_RATE` = 0.27 (fixed_assets.py:84).
- **Today's fix verified:** financial_statements.py:118-121 converts decimal rates (<1.0) to percent. Residual Low: a genuine rate below 1% p.a. would be mis-scaled ×100 — only theoretical; consider storing one unit consistently.
- Finance costs below EBIT; tax from `profit_before_tax` (financial_statements.py:277-280) ✓.
- Sources: [IFRS Foundation — IFRS for SMEs update](https://www.ifrs.org/news-and-events/news/2025/02/iasb-issues-major-update-smes-accounting-standard/), [Forvis Mazars SA](https://www.forvismazars.com/za/en/services/audit-assurance/financial-reporting/ifrs-for-smes-R-accounting-standard), [Accounting Academy SA](https://www.accountingacademy.co.za/news/read/updated-ifrs-for-smes-3rd-edition) (search returned link lists only; no contradicting news).

## 7. Tax updates (company + payroll)
- Current tax year at run date: **2026/2027** (1 Mar 2026 – 28 Feb 2027). `TAX_YEARS["2026/2027"]` payroll.py:294 (18%→45%; thresholds 245,100 / 383,100 / 530,200 / 695,800 / 887,000 / 1,878,600; rebates 17,820 / 9,765 / 3,249; UIF ceiling 17,712); provisional "2027/2028" payroll.py:314; `_current_tax_year` payroll.py:332; `SDL_RATE=0.01` payroll.py:352, SDL threshold R500k (payroll.py:901); UIF 1%+1%. VAT 15%, CIT 27% — unchanged; no announced change found.
- Sources: [SARS Guide for Employers 2027](https://www.sars.gov.za/guide-for-employers-in-respect-of-employees-tax-2027/), [Accounter SARS tax tables 2026/27](https://accounter.co.za/news/sars-tax-tables-2026-2027), [Xero SA tax tables](https://www.xero.com/za/guides/sars-tax-tables-2026/). Search returned link lists only; values compared against prior verified figures. No tax-table edits made.

## 8. Action items
**Critical:** none.

**High**
1. **`zuzan-backend/plans.py` is untracked (never committed)** yet is imported at module level by main.py:422 and lazily by payroll.py, companies.py, auth.py, recurring_invoices.py. A push/deploy of HEAD without it crashes startup (ImportError). Fix: `git add zuzan-backend/plans.py` and commit before the next deploy.

**Medium**
2. Confirm intended plan gating on creditors-aging/reconciliation/13-week cash flow and that the frontend handles the 403 (payroll.py:2906, 3477, 4285).
3. Owner: review account types in companies that imported a GL before 2026-11-05 (reclassify dry-run).

**Low**
4. Docstrings displaced by plan checks (payroll.py:3477, 4285).
5. `_wt_rate_pct` unit heuristic (<1.0 ⇒ decimal) — normalise storage unit.
6. POPIA/Privacy Policy coverage of AI-context disclosure.
7. Run full pytest locally (syntax only here), incl. new test_plan_gates / test_import_payments.
8. Untracked leftovers: commit_and_push.ps1, zuzan-app/public/sw.js, zuzan-backend/_to_delete/, find_default_password_accounts.py, fix_credit_note_vat_account.py.
9. Normalise CRLF line endings.

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS-for-SMEs 3rd-ed. / IFRS 18 checklist Jan–Feb 2027.
