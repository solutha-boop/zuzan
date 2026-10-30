# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 29 October 2026 (scheduled run)
**Prior report:** 2026-10-28

**Change detection:** Since yesterday's report the working copy gained an uncommitted security-hardening batch (modified 29 Oct 20:49): `main.py` (SecurityMiddleware, per-IP rate limiter, encryption of mandate bank fields), `companies.py` (masked secrets, role-gated bank details, HTML sanitiser, PIN throttle, `billing_exempt`/`afs_enabled` no longer owner-writable), `auth.py`, `billing.py`, `email_service.py`, and `App_js_fixed.js` / `zuzan-app/src/App.js` (escHtml + sanitizeHtml on custom invoice templates). `payroll.py`, `journal.py`, `purchase_orders.py`, `financial_statements.py`, `database.py`, `csv_import.py` are unchanged since yesterday. Static review only (no live DB / pytest run). **No code edited** (5b already implemented).

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | **PASS** — `_to_zar` (payroll.py:23), `VAT_RATE = 0.15` (payroll.py:20); main.py:519 still imports `_to_zar` |
| Debtors (AR) | **PASS** — `debtors_aging` (payroll.py:4094) unchanged |
| Creditors (AP) | **PASS** — reversal-aware sources at payroll.py:2972, 3443, 4192; purchase_orders.py:505; journal.py:1347; `decrypt_field` at payroll.py:4167, 4235-4237 |
| Cross-module | **PASS** (journal/backend unchanged) — see High finding on the frontend below |
| IFRS (AFS) | **PASS** — no change in standards; deferred tax verified |
| Tax (SARS) | **PASS** — 2026/2027 table unchanged |

**Overall: 0 Critical, 1 High (new, frontend regression), 1 Low carried.**

## 2. Reports
✓ No issues found.

## 3. Debtors
✓ No issues found.

## 4. Creditors
✓ No issues found. Supplier bank details are still decrypted at payroll.py:4235-4237. (The new role-gating in companies.py concerns the company's own bank fields, not supplier details.)

## 5. Cross-module
- Backend journal coverage (invoice/expense payments, PO receipt/payment, payroll incl. benefit schemes 2330/5190), import-awareness (backfill, Rules 6/7, 3998/3999, unbalanced-group rejection, non-ZAR rate): unchanged since the 28 Oct pass.
- **NEW — High: the Benefits Manager UI has been removed from the uncommitted working copy of `App_js_fixed.js`.** `git diff` vs HEAD shows the whole `function BenefitsManager` (HEAD lines 3492 ff., ~390 lines) and its render site (HEAD line 4259, `<BenefitsManager employees=… />`) deleted; `grep BenefitsManager` now returns nothing. The same ~416-line deletion appears in `zuzan-app/src/App.js`. The backend (`benefits.py`, payroll `benefit_contributions_json`, journal posting to 2330/5190 fixed on 28 Oct) still depends on schemes being captured, so users would have no way to create/enrol benefit schemes. The deletion looks unintentional (it sits in a diff that is otherwise only the HTML-sanitiser change) — likely a bad merge/edit. Fix: restore the block from HEAD (`git show HEAD:App_js_fixed.js`) and re-apply only the `escHtml`/`sanitizeHtml` hunks before the next deploy.
- Low (carried): benefit JSON parse in journal.py:824-825 zeroes amounts on malformed JSON (fails safe via balance assertion).
- Live control-account reconciliation not executed here; see `reconciliation_2026-10-26.md` / `journal_integrity_2026-10-26.md`.

## 6. IFRS compliance (AFS)
- Framework unchanged: IFRS for SMEs (2nd ed.). IFRS 18 and IFRS for SMEs 3rd ed. are both effective for periods beginning on/after 1 Jan 2027 (first ZuZan FY affected starts 1 Mar 2027). Searches this run found no new announcements ([Accounting Academy](https://www.accountingacademy.co.za/news/read/updated-ifrs-for-smes-3rd-edition), [ACCA](https://www.accaglobal.com/learning-and-events/corporate-reporting/third-edition-ifrs-for-smes), [IFRS Foundation](https://www.ifrs.org/content/ifrs/home/news-and-events/news/2025/02/iasb-issues-major-update-smes-accounting-standard.html)); results were titles only. Transition plan `ifrs_smes_3rd_edition_transition_plan.md` stands.
- **5b deferred tax — verified, not hard-coded** (`"deferred_tax": 0.0` no longer present in financial_statements.py): `wear_and_tear_rate` column database.py:606, migration inside the list at :1587; `_deferred_tax_balance` financial_statements.py:139; opening/closing :283-284; `total_tax = tax_expense + deferred_tax_expense` :669; Note 9 :674-678; equity movement :749. No edits.
- Finance costs below EBIT / tax from PBT: unchanged ✓.
- Note: `companies.py` now blocks owners from writing `afs_enabled` (ZuZan-controlled add-on). Intended; confirm the admin console/PayFast ITN path still sets it.

## 7. Tax updates (company + payroll)
- Tax year: **2026/2027** (1 Mar 2026 – 28 Feb 2027). `_current_tax_year()` payroll.py:228 selects by date. `TAX_YEARS["2026/2027"]` payroll.py:190-203: 18% to R245,100 … 45% above R1,878,600; rebates R17,820 / R9,765 / R3,249; UIF ceiling R17,712 — unchanged.
- UIF 1%+1% (payroll.py:247), SDL 1% (payroll.py:248, R500k threshold at :797), VAT 15%, CIT 27%: no announced changes found. Searched SARS/Budget 2026/MTBPS sources ([SARS companies rates](https://www.sars.gov.za/tax-rates/income-tax/companies-trusts-and-small-business-corporations-sbc/), [SARS Budget 2026](https://www.sars.gov.za/latest-news/what-does-the-2026-budget-mean-for-you/), [Grant Thornton Budget 2026](https://www.grantthornton.co.za/contentassets/334ab82b24354cfa91de433a7de8ed56/2026-budget-analysis-and-commentary_fa.pdf)); titles only, nothing contradicting the code. The MTBPS (late Oct/Nov 2026) is worth re-checking next run.
- Provisional `2027/2028` entry (payroll.py:210, flagged `provisional`) must be replaced after Budget Feb 2027. No tax-table edits made.

## 8. Action items
**High**
1. Restore `BenefitsManager` (component + `<BenefitsManager …/>` render site) in `App_js_fixed.js` and `zuzan-app/src/App.js`; keep only the intended sanitiser changes. Re-diff against HEAD before commit/deploy.

**Low**
2. Run `test_payroll_journal_balance.py` / full pytest locally (not executable here), including the new security middleware/throttle paths.
3. Commit or remove untracked helpers (`commit_and_push.ps1`, `zuzan-app/public/sw.js`, `zuzan-backend/_to_delete/`, `security.py` — note `main.py` now imports `security.py`, which is untracked: it must be committed or the deploy will fail on import).

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS-for-SMEs 3rd-ed. checklist Jan–Feb 2027; EMP501 annual reconciliation due 31 Oct 2026; re-check MTBPS for tax-rate announcements.
