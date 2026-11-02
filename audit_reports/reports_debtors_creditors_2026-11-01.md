# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 1 November 2026 (scheduled run)
**Prior report:** 2026-10-31

**Change detection:** HEAD is still `7908352`; newest source mtime is 30 Oct 2026 (backend 16:27, App_js_fixed.js 03:45) — nothing changed since the prior two audits. Only untracked files differ (the 30/31 Oct audit reports plus the same leftovers). Static review only (no live DB / pytest). Key lines re-grepped and confirmed. **No code edited** (5b already implemented).

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | **PASS** — `_to_zar` payroll.py:23; `VAT_RATE = 0.15` payroll.py:20 |
| Debtors (AR) | **PASS** — unchanged |
| Creditors (AP) | **PASS** — reversal-aware sources payroll.py:2972, 3443, 4192; purchase_orders.py:498-505; journal.py:1347; `decrypt_field` payroll.py:4167, 4235-4237 |
| Cross-module | **PASS** — unchanged |
| IFRS (AFS) | **PASS** — no change; deferred tax verified |
| Tax (SARS) | **PASS** — 2026/2027 table present; no rate changes found |

**Overall: 0 Critical, 0 High; Low items carried.**

## 2. Reports
✓ No issues found.

## 3. Debtors
✓ No issues found.

## 4. Creditors
✓ No issues found.

## 5. Cross-module
- Journal coverage (invoice/expense payments, PO receipt/payment, payroll) and import-awareness (backfill, Rules 6/7, 3998/3999, unbalanced-group rejection, non-ZAR rate): unchanged.
- Low (carried): benefit JSON parse in journal.py:824-825 zeroes amounts on malformed JSON (fails safe via balance assertion).
- Live control-account reconciliation not run here; see `reconciliation_2026-10-26.md` / `journal_integrity_2026-10-26.md`.

## 6. IFRS compliance (AFS)
- Framework unchanged: IFRS for SMEs (2nd ed.). IFRS 18 and IFRS for SMEs 3rd ed. both effective for periods beginning on/after 1 Jan 2027 (first affected ZuZan FY starts 1 Mar 2027). No new announcements; transition plan `ifrs_smes_3rd_edition_transition_plan.md` stands.
- **5b deferred tax — verified, not hard-coded:** `wear_and_tear_rate` database.py:606, migration inside list at :1587; `_deferred_tax_balance` financial_statements.py:139; opening/closing :283-284; Note 9 `deferred_tax` :674. No edits.
- Finance costs below EBIT / tax from PBT: unchanged ✓.

## 7. Tax updates (company + payroll)
- Tax year **2026/2027**. `TAX_YEARS["2026/2027"]` payroll.py:190, `_current_tax_year()` payroll.py:228; values unchanged (18% to R245,100 … 45% above R1,878,600; rebates R17,820 / R9,765 / R3,249; UIF ceiling R17,712).
- UIF 1%+1%, SDL 1%, VAT 15%, CIT 27% unchanged per Budget 2026. This run's search for MTBPS/November announcements returned only Budget-2026 and general 2026 tax-change coverage (e.g. [BusinessTech](https://businesstech.co.za/news/business/844500/sars-announces-tax-change-for-2026/), [Xero SA tax dates](https://blog.xero.com/small-business-resources/south-african-tax-dates-2026-2027/)) — no VAT/CIT/PAYE rate change identified.
- Provisional `2027/2028` entry (payroll.py:210) to be replaced after Budget Feb 2027. No tax-table edits made.

## 8. Action items
**Low**
1. Run full pytest locally (incl. `test_payroll_journal_balance.py`, `tests/test_security_hardening.py`); not executable here.
2. Untracked leftovers: `commit_and_push.ps1`, `zuzan-app/public/sw.js`, `zuzan-backend/_to_delete/`, `find_default_password_accounts.py`, `fix_credit_note_vat_account.py` — commit or remove.
3. Read the full MTBPS 2026 documents to confirm no rate/threshold announcements ahead of Feb 2027 Budget.

Standing reminders: confirm the EMP501 annual reconciliation (31 Oct 2026 deadline) was submitted; replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS-for-SMEs 3rd-ed. checklist Jan–Feb 2027.
