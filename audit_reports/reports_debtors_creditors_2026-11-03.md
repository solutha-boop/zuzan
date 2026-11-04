# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 3 November 2026 (scheduled run)
**Prior report:** 2026-11-02

**Change detection:** HEAD is still `aa1b13f` (same as prior run); no tracked source changes since the 2 Nov report. Static review only (no live DB / pytest). Key lines re-grepped and confirmed. **No code edited** (5b already implemented).

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | **PASS** — `_to_zar` payroll.py:23; `VAT_RATE = 0.15` payroll.py:20 |
| Debtors (AR) | **PASS** — unchanged |
| Creditors (AP) | **PASS** — reversal-aware sources payroll.py:2972, 3443, 4192; purchase_orders.py:498; journal.py:1347; financial_statements.py:626; `decrypt_field` payroll.py:4167, 4235-4237 |
| Cross-module | **PASS** — unchanged |
| IFRS (AFS) | **PASS** — no change; deferred tax verified |
| Tax (SARS) | **PASS** — 2026/2027 table present; no rate changes found |

**Overall: 0 Critical, 0 High; Low items carried from 2026-11-02.**

## 2. Reports
✓ No issues found. (Low, carried: `_build_company_context` in main.py uses hard-coded 1.15 and a "last payroll" query by latest 50 payslips — see 2 Nov report.)

## 3. Debtors
✓ No issues found.

## 4. Creditors
✓ No issues found.

## 5. Cross-module
✓ No issues found. Journal coverage and import-awareness unchanged (no code change). Low (carried): journal.py:824-825 benefit JSON parse zeroes amounts on malformed JSON (fails safe via balance assertion).

## 6. IFRS compliance (AFS)
- Framework unchanged: IFRS for SMEs (2nd ed.). IFRS 18 and IFRS for SMEs 3rd ed. effective for periods beginning on/after 1 Jan 2027 (first affected ZuZan FY starts 1 Mar 2027). No new information surfaced; transition plan stands.
- **5b deferred tax — verified, not hard-coded:** financial_statements.py:674 `"deferred_tax": deferred_tax_expense`; `wear_and_tear_rate` in database.py (migration inside list). No edits.
- Finance costs below EBIT / tax from PBT: unchanged ✓.

## 7. Tax updates (company + payroll)
- Tax year **2026/2027**: `TAX_YEARS["2026/2027"]` payroll.py:190; `_current_tax_year()` payroll.py:228; provisional `2027/2028` at payroll.py:210. Values unchanged (rebates R17,820 / R9,765 / R3,249; UIF ceiling R17,712; UIF 1%+1%, SDL 1%, VAT 15%, CIT 27%).
- MTBPS 2026 search this run (titles only; e.g. [SAIT MTBPS 2026 predictions](https://thesait.org.za/wp-content/uploads/2026/10/SAIT-Predictions-MTBPS-2026.pdf), [BDO budget 2026: corporate tax unchanged](https://www.bdo.co.za/en-za/insights/2026/budget-speech/corporate-tax-remains-unchanged,-with-a-pinch-of-positivity)) surfaced no announced rate changes. Speculation on tax hikes exists ([Daily Investor](https://dailyinvestor.com/finance/107694/tax-hike-on-the-cards-for-south-africa/)); nothing confirmed. No tax-table edits made.

## 8. Action items
**Low**
1. main.py `_build_company_context`: use `VAT_RATE`, align with dashboard logic, fix "last payroll" query.
2. Confirm POPIA/Privacy Policy covers AI-context disclosure of company financials.
3. Run full pytest locally (`test_payroll_journal_balance.py`, `tests/test_security_hardening.py`).
4. Untracked leftovers: `commit_and_push.ps1`, `zuzan-app/public/sw.js`, `zuzan-backend/_to_delete/`, `find_default_password_accounts.py`, `fix_credit_note_vat_account.py`.
5. Read the actual MTBPS 2026 documents for rate/threshold announcements ahead of Feb 2027 Budget.

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS-for-SMEs 3rd-ed. checklist Jan–Feb 2027.
