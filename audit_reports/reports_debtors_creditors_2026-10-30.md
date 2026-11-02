# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 30 October 2026 (scheduled run)
**Prior report:** 2026-10-29

**Change detection:** Working copy was committed since yesterday (HEAD `7908352`, "sync working copy [2026-10-30_1827]"; also `9c8bdc5`). `git diff 3b8095c HEAD` touches only the security-hardening batch (auth.py, billing.py, companies.py, email_service.py, main.py (6 lines), security.py, requirements.txt, tests, App.js). `payroll.py`, `journal.py`, `purchase_orders.py`, `financial_statements.py`, `database.py`, `csv_import.py` are unchanged. Static review only (no live DB / pytest). **No code edited** (5b already implemented).

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | **PASS** — `_to_zar` payroll.py:23, `VAT_RATE = 0.15` payroll.py:20; main.py:519 still imports `_to_zar` |
| Debtors (AR) | **PASS** — unchanged |
| Creditors (AP) | **PASS** — reversal-aware sources payroll.py:2972, 3443, 4192; purchase_orders.py:505; journal.py:1347; `decrypt_field` payroll.py:4167, 4235-4237 |
| Cross-module | **PASS** — yesterday's High (BenefitsManager) is **resolved** |
| IFRS (AFS) | **PASS** — no change; deferred tax verified |
| Tax (SARS) | **PASS** — 2026/2027 table unchanged |

**Overall: 0 Critical, 0 High, Low items carried.**

## 2. Reports
✓ No issues found.

## 3. Debtors
✓ No issues found.

## 4. Creditors
✓ No issues found.

## 5. Cross-module
- **Resolved:** `BenefitsManager` component is back in `App_js_fixed.js` (definition line 3511, render site line 4278). Same fix present in the committed tree.
- **Resolved:** `security.py` is now tracked (imported by main.py:24, middleware at main.py:286) — deploy import risk removed.
- Backend journal coverage (invoice/expense payments, PO receipt/payment, payroll incl. benefit schemes), import-awareness (backfill, Rules 6/7, 3998/3999, unbalanced-group rejection, non-ZAR rate): unchanged.
- Low (carried): benefit JSON parse in journal.py:824-825 zeroes amounts on malformed JSON (fails safe via balance assertion).
- Live control-account reconciliation not executed here; see `reconciliation_2026-10-26.md` / `journal_integrity_2026-10-26.md`.

## 6. IFRS compliance (AFS)
- Framework unchanged: IFRS for SMEs (2nd ed.). IFRS 18 and IFRS for SMEs 3rd ed. both effective for periods beginning on/after 1 Jan 2027 (first affected ZuZan FY starts 1 Mar 2027). Search this run found no new announcements ([Accounting Academy](https://www.accountingacademy.co.za/news/read/updated-ifrs-for-smes-3rd-edition), [ACCA](https://www.accaglobal.com/learning-and-events/corporate-reporting/third-edition-ifrs-for-smes), [IFRS Foundation](https://www.ifrs.org/content/ifrs/home/news-and-events/news/2025/02/iasb-issues-major-update-smes-accounting-standard.html)). Transition plan `ifrs_smes_3rd_edition_transition_plan.md` stands.
- **5b deferred tax — verified, not hard-coded:** `wear_and_tear_rate` column database.py:606, migration in list at :1587; `_deferred_tax_balance` financial_statements.py:139; opening/closing :283-284; `total_tax` :669; Note 9 :674-678; equity movement :749. No edits.
- Finance costs below EBIT / tax from PBT: unchanged ✓.

## 7. Tax updates (company + payroll)
- Tax year **2026/2027**. `_current_tax_year()` payroll.py:228. `TAX_YEARS["2026/2027"]` payroll.py:190-203: 18% to R245,100 … 45% above R1,878,600; rebates R17,820 / R9,765 / R3,249; UIF ceiling R17,712 — unchanged.
- UIF 1%+1%, SDL 1%, VAT 15%, CIT 27%: Budget 2026 left rates unchanged ([BDO](https://www.bdo.co.za/en-za/insights/2026/budget-speech/corporate-tax-remains-unchanged,-with-a-pinch-of-positivity), [Grant Thornton](https://www.grantthornton.co.za/insights2/2026-budget-analysis-and-commentary/)). MTBPS 2026 search returned no results on rate changes (titles only); re-check in a few days once coverage is published.
- Provisional `2027/2028` entry (payroll.py:210) must be replaced after Budget Feb 2027. No tax-table edits made.

## 8. Action items
**Low**
1. Run `test_payroll_journal_balance.py` / full pytest locally (incl. new `tests/test_security_hardening.py`); not executable here.
2. Untracked leftovers: `commit_and_push.ps1`, `zuzan-app/public/sw.js`, `zuzan-backend/_to_delete/`, `find_default_password_accounts.py`, `fix_credit_note_vat_account.py` — commit or remove.
3. Re-check MTBPS (Nov 2026) for tax-rate announcements.

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS-for-SMEs 3rd-ed. checklist Jan–Feb 2027; EMP501 annual reconciliation due 31 Oct 2026 (tomorrow).
