# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 2 November 2026 (scheduled run)
**Prior report:** 2026-11-01

**Change detection:** Since the prior audit (HEAD `7908352`) the only source change is `zuzan-backend/main.py` (+86/−2): new `_build_company_context()` (main.py ~609-676) feeding live figures into the `/ai/chat` prompt. Other files show 2 Nov mtimes but no content diff (git sync). Static review only (no live DB / pytest). Key lines re-grepped and confirmed. **No code edited** (5b already implemented).

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | **PASS** — `_to_zar` payroll.py:23; `VAT_RATE = 0.15` payroll.py:20; new AI context in main.py uses the `_received_net_zar` / `_balance_zar` helpers |
| Debtors (AR) | **PASS** — unchanged |
| Creditors (AP) | **PASS** — reversal-aware sources payroll.py:2972, 3443, 4192; purchase_orders.py:498-505; journal.py:1347; `decrypt_field` payroll.py:4167, 4235-4237 |
| Cross-module | **PASS** — unchanged (journal integrity run 2026-11-02: 0 gaps) |
| IFRS (AFS) | **PASS** — no change; deferred tax verified |
| Tax (SARS) | **PASS** — 2026/2027 table present; no rate changes found |

**Overall: 0 Critical, 0 High; 2 new Low items (AI context), earlier Low items carried.**

## 2. Reports
✓ No issues found in `/reports/dashboard`, `/reports/management`, `/v1/summary`.
New code note (Low): `_build_company_context` (main.py ~609-676) is an AI-assistant context, not a report, but its figures can differ from the dashboard:
- Expense total divides by a hard-coded `1.15` (instead of `VAT_RATE`) and does not use the dashboard's payroll/PO/stock-cost logic, so "gross profit" quoted by the assistant may not match the dashboard.
- "Last payroll net pay" sums the latest 50 payslips by id regardless of pay period, so it is wrong for >50 employees or multiple runs; `period_label` is not a Payslip column (grep: none in database.py), so the label always falls back to "last run".

## 3. Debtors
✓ No issues found. (New AI context counts sent/overdue/partial using `_balance_zar` — ZAR-converted, paid excluded.)

## 4. Creditors
✓ No issues found.

## 5. Cross-module
- Journal coverage (invoice/expense payments, PO receipt/payment, payroll) and import-awareness (backfill, Rules 6/7, 3998/3999, unbalanced-group rejection, non-ZAR rate): unchanged.
- Journal integrity (`journal_integrity_2026-11-02.md`): 0 gaps on local SQLite (1 invoice, 14 expenses, 0 POs, 16 entries); production DB not covered.
- Low (carried): benefit JSON parse in journal.py:824-825 zeroes amounts on malformed JSON (fails safe via balance assertion).

## 6. IFRS compliance (AFS)
- Framework unchanged: IFRS for SMEs (2nd ed.). IFRS 18 and IFRS for SMEs 3rd ed. both effective for periods beginning on/after 1 Jan 2027 (first affected ZuZan FY starts 1 Mar 2027). Search this run surfaced no new SA adoption changes ([IFRS Foundation](https://www.ifrs.org/content/ifrs/home/news-and-events/news/2025/02/iasb-issues-major-update-smes-accounting-standard.html), [Forvis Mazars SA](https://www.forvismazars.com/za/en/services/audit-assurance/financial-reporting/ifrs-for-smes-R-accounting-standard)). Transition plan `ifrs_smes_3rd_edition_transition_plan.md` stands.
- **5b deferred tax — verified, not hard-coded:** `wear_and_tear_rate` database.py:606, migration inside list at :1587; rate resolution financial_statements.py:115-118; Note 9 `deferred_tax` :674. No edits.
- Finance costs below EBIT / tax from PBT: unchanged ✓.

## 7. Tax updates (company + payroll)
- Tax year **2026/2027**. `TAX_YEARS["2026/2027"]` payroll.py:190; `_current_tax_year()` payroll.py:228. Values unchanged (18% to R245,100 … 45% above R1,878,600; rebates R17,820 / R9,765 / R3,249; UIF ceiling R17,712).
- UIF 1%+1%, SDL 1%, VAT 15%, CIT 27% unchanged per Budget 2026. Sources: [SARS rates for individuals](https://www.sars.gov.za/tax-rates/income-tax/rates-of-tax-for-individuals/), [Treasury Budget 2026 Tax Guide](https://www.treasury.gov.za/documents/national%20budget/2026/sars/Budget%202026%20Tax%20guide.pdf), [SimplePay](https://www.simplepay.co.za/blog/2026/02/27/national-budget-speech-2026/). Search returned titles only; no VAT/CIT/PAYE change identified.
- Provisional `2027/2028` entry (payroll.py:210) to be replaced after Budget Feb 2027. No tax-table edits made.

## 8. Action items
**Low**
1. main.py `_build_company_context`: use `VAT_RATE`, align expense/profit with dashboard logic (or label as approximate), and fix the "last payroll" query to the latest pay period.
2. Privacy: the AI context sends live company financials and debtor client names to the Anthropic API — confirm this is covered in the Privacy Policy / POPIA operator disclosures.
3. Run full pytest locally (incl. `test_payroll_journal_balance.py`, `tests/test_security_hardening.py`).
4. Untracked leftovers: `commit_and_push.ps1`, `zuzan-app/public/sw.js`, `zuzan-backend/_to_delete/`, `find_default_password_accounts.py`, `fix_credit_note_vat_account.py`.
5. Read MTBPS 2026 documents for any rate/threshold announcements ahead of Feb 2027 Budget.

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS-for-SMEs 3rd-ed. checklist Jan–Feb 2027.
