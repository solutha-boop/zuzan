# ZuZan Audit: Reports, Debtors, Creditors and Security
**Date:** 25 November 2026 (scheduled run)
**Prior report:** 2026-11-24, including its same-day Remediation section.

**Method:**
- Git HEAD is still **eac8e09**, and GitHub main (`git ls-remote`) is also eac8e09. The 24 Nov remediation is **uncommitted** in the working tree (9 files, +149/−20). It is not yet in production.
- **Changed since the last audited code:** only that working-tree diff. I reviewed every hunk:
  - companies.py: `_already_settled_today` and `_EXPORT_SECRET_COLUMNS`
  - auth.py: HMAC reset-code hash
  - payroll.py: IRP5/e@syFile audit log
  - App_js_fixed.js: duplicate/transfer skipped messages
  - main_py_fixed.py: DSN redaction
  - tests/conftest.py: throttle reset
  - two new regression tests
- I re-ran the anchor greps for every carried checklist item. Line numbers below reflect the working tree.
- Web checks were done for SARS and IFRS.
- **Tests:** installing packages on the local VM was refused by the permission policy. The backend code and test files (no database) were copied to the cloud workspace and run there under Python 3.13 against conftest's throwaway SQLite database. pip-audit was run there too.
- No client database was opened. zuzan.db, its -wal/-shm files and the .bak file were checked for existence only; all are gitignored and none are tracked.
- **No code was edited.** 5b is already implemented, the tax tables are report-only, and §7 is report-only.

**Security scope:** **changed-files review** of the uncommitted remediation diff, plus re-confirmation of every carried item. The next full sweep is on **1 Dec 2026**.

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | **PASS.** Unchanged |
| Debtors (AR) | **PASS in the working tree.** The 24 Nov High is fixed and verified by tests, but it is **not deployed**, so production still carries it until it is committed and pushed |
| Creditors (AP) | **PASS in the working tree.** The same fix covers AP. Not deployed |
| Cross-module | **PASS.** Unchanged |
| IFRS (AFS) | **PASS.** Standards are unchanged and deferred tax is verified |
| Tax (SARS) | **PASS.** Tables are current and nothing new was announced |
| **Security / POPIA** | **FAIL. 2 Critical carried (owner action: the history purge is still not pushed and PAT revocation is unconfirmed), 0 High, 1 Medium carried.** Nothing new above Low |

## 2. Reports
✓ No issues found.
- `_to_zar` (payroll.py:24), `_received_net_zar` (:34) and `_balance_zar` (:46) are unchanged.
- The tax provision is 27% (payroll.py:4089; it was :4081 before the +8 lines of IRP5 logging).
- The trend loop and `/v1/summary` are unchanged.

## 3. Debtors
- ✓ `debtors_aging` is unchanged: sent/overdue/partial invoices, aged from `due_date`, ZAR balances, paid invoices excluded.
- ✓ A 1100 allocation goes through `_settle_bank_control_line` (companies.py:2486). `needs_matching` is at :2614. No line is posted as a loose `bank_import_transfer`.
- ✓ **The 24 Nov High is fixed in the working tree.** The fix is `_already_settled_today` (companies.py:2443-2483):
  - It keys on an actual `invoice_payment` journal on the same bank date, for the same amount, on account 1000, for an invoice that is still paid or partial.
  - A re-imported line that names last month's customer is now a duplicate.
  - A genuine payment on a new date is still settled.
  - Two same-day, same-amount payments from the same customer fail safe: the second is skipped and is now listed in the UI (App_js_fixed.js:10124).
  - The regression test passes.
- ✓ The 24 Nov Low is fixed: `duplicates_skipped` and `transfers_skipped` are now rendered (App_js_fixed.js:10124-10125).
- **Deployment note:** production (eac8e09) still runs the old guard until the working tree is committed and pushed. See action item 3.

## 4. Creditors
- ✓ The reversal-aware AP lookups are unchanged, including `_po_ap_outstanding` (companies.py:2420).
- ✓ Supplier bank details are decrypted and masked as before.
- ✓ The AP duplicate guard now uses the same helper (`po_payment`/`expense_payment` on account 1000, matched on credit amount). The rent plus second-supplier regression test passes.
- **Low (new), companies.py:2471.** The PO branch counts `status in ("paid", "partial")` as settled. For POs, "partial" means *partially received* (database.py:435), not part-paid.
  - This could only matter if a `po_payment` was reversed and the PO reverted to "partial".
  - In that case the guard fails safe: the line is skipped and listed. No money is mis-posted.
  - Tighten the check to `"paid"` only, or check for the absence of a `po_payment_reversal`.

## 5. Cross-module
✓ No issues found. Nothing changed in this area:
- Journal coverage of invoice payments, expense payments, PO receipts, PO payments and payroll is unchanged.
- `_book_bank_asset_purchase` (companies.py:2557) is unchanged.
- Rules 6/7 and the import-awareness rules are unchanged.

## 6. IFRS compliance (AFS)
- **Framework:** IFRS for SMEs (2nd ed.) presentation, unchanged.
- **Upcoming standards:** IFRS 18 and IFRS for SMEs 3rd ed. are effective 1 Jan 2027. ZuZan's first affected year begins 1 Mar 2027. Today's search found no deferral. **Standards are unchanged since the prior report.**
- **Finance costs ✓.** `profit_before_tax = ebit − finance_costs` (financial_statements.py:375).
- **Classification ✓.** The helpers are at :201, :206 and :213.
- **5b deferred tax ✓ (verified, not re-implemented).**
  - `_deferred_tax_balance` is at financial_statements.py:222.
  - Note 9 `deferred_tax` is at :790.
  - The `wear_and_tear_rate` column is at database.py:616, with its migration inside the list at :1658.
  - test_annual_statements and test_afs_edge_cases pass.
- Sources: [IFRS 18 — IFRS Foundation](https://www.ifrs.org/issued-standards/list-of-standards/ifrs-18-presentation-and-disclosure-in-financial-statements/), [IAS Plus — effective 2027](https://www.iasplus.com/en-gb/events/effective-1/2027), [PwC Viewpoint IFRS 18](https://viewpoint.pwc.com/gx/en/IFRS_18_Presentation.html).

## 7. Tax updates (company + payroll)
- **Tax year:** 2026/2027 (1 Mar 2026 – 28 Feb 2027).
- **Rates: unchanged and current.**
  - `TAX_YEARS["2026/2027"]` is at payroll.py:357, and the provisional "2027/2028" entry is at :377.
  - `_current_tax_year` is at :395.
  - `VAT_RATE = 0.15` is at :21, and CIT is 27% (:4089). The SBC table is at :3520.
  - UIF and SDL are 1%.
- Nothing new was announced.
- Sources: [SARS — Rates of tax for individuals](https://www.sars.gov.za/tax-rates/income-tax/rates-of-tax-for-individuals/), [SARS Budget 2026 FAQ](https://www.sars.gov.za/about/sars-tax-and-customs-system/budget/budget-2026-frequently-asked-questions/), [SARS — companies / SBC](https://www.sars.gov.za/tax-rates/income-tax/companies-trusts-and-small-business-corporations-sbc/).

## 8. Security and data protection (changed-files review + carried items)
1. **Tenant isolation ✓.** Every query in `_already_settled_today` filters `company_id == cid`, both on the journal join and on each Invoice/PO/Expense lookup (companies.py:2457-2479). No new endpoints were added.
2. **Authentication / authorisation ✓.**
   - No route changes.
   - IRP5 and e@syFile now call `log_action` (payroll.py:2091, :2252). This closes the 24 Nov Low.
3. **Passwords / sessions ✓, plus the carried Medium.**
   - Reset codes are now HMAC-SHA256 keyed with SECRET_KEY (auth.py:769-774). The legacy `sha256:` format is still accepted (auth.py:777-781, :791).
   - **Low (new):** remove the legacy branch once the deploy is more than 30 minutes old, since all legacy codes will have expired by then.
   - **Medium (carried, owner):** the code fallback for SECRET_KEY is still at auth.py:35-40. Confirm a dedicated SECRET_KEY is set in Render. The HMAC'd reset codes also depend on it.
4. **Encryption and secrets: FAIL (2 Critical carried).**
   - **CRITICAL (carried): the history purge is not pushed.** GitHub main is still eac8e09. `git log --all -- zuzan-backend/zuzan.db` still lists 4 historical commits (070d83e, b9a757d, 2b40163, b3e5acf), and the token prefix is still in historical commits.
     - The rebuilt bundle (`_history_clean/zuzan-clean-history.bundle`, 24 Nov) and `push_clean_history.ps1` expect GitHub main = eac8e09. **That still matches, so the script is ready to run now.**
     - It must be run **before** `commit_and_push.bat`; otherwise main moves and the guard refuses again.
   - **CRITICAL (carried):** revocation of the GitHub PAT is unconfirmed (owner).
   - ✓ `git ls-files` shows no database, .env, key or backup file. err.log and the test database are gitignored.
   - Hygiene: a 0-byte `zuzan-backend/New Text Document.txt` is tracked. It is harmless; remove it.
5. **Input handling ✓.** No raw SQL was added. The new code uses the ORM only.
6. **Data exposure ✓.** `email_verify_token` and `clock_pin_hash` are now excluded from the data export (companies.py:301). This closes the 24 Nov Low.
7. **Web / transport ✓, unchanged.**
   - CSP and netlify headers are in place.
   - Tokens are still in localStorage (accepted residual risk). The HTML CSP still allows `'unsafe-inline'` scripts (Low, carried).
8. **POPIA ✓.**
   - IRP5 and e@syFile views are now audit-logged.
   - **Carried (owner):** legal review of privacy.html (`[DATE]`/`[REGION]`).
9. **Tests and dependencies.**
   - Run in the cloud workspace on Python 3.13 with a throwaway SQLite database: test_auth_security, test_security_hardening, test_security_audit_2026_11_23, test_bank_control_allocations, test_bank_import, test_accountant, test_practice_mcp, test_cors_and_docs, test_annual_statements, test_afs_edge_cases and test_signup_flow. Result: **56 passed, 0 failed**.
   - Run together, the security files no longer hit the 429 throttle issue, so the 24 Nov test-isolation Low is closed.
   - **pip-audit on requirements.txt: no known vulnerabilities.**
   - npm audit was not run.
   - The local-VM run was not possible: the package install there was refused by the permission policy.

## 9. Action items
**Critical**
1. (Carried, owner) **Run `_history_clean\push_clean_history.ps1` now, while GitHub main is still eac8e09**, then:
   - ask GitHub Support to purge cached refs;
   - re-clone any other copies;
   - assess POPIA s22 if real client data was ever in the historical zuzan.db.
2. (Carried, owner) Revoke the GitHub PAT whose prefix appeared in the Aug/Sep reports.

**High**

3. (Carried, deploy only) The 24 Nov High (re-imported bank lines double-settling recurring invoices and bills) is fixed in the working tree but **not committed or deployed**. Run `commit_and_push.bat` **after** item 1.

**Medium**

4. (Carried, owner) In Render, set SECRET_KEY, SENTRY_DSN and CORS_ORIGINS, rotate the old backend Sentry DSN, and confirm `/health` shows `field_encryption: true` and `secret_key_configured: true`.

**Low**

5. (New) companies.py:2471: count only `"paid"` POs as settled in `_already_settled_today`, since "partial" means partially received.
6. (New) auth.py:777-791: drop the legacy `sha256:` reset-code branch after the next deploy has been live for more than 30 minutes.
7. (New, hygiene) Remove the tracked 0-byte `zuzan-backend/New Text Document.txt`.
8. (Carried) Tighten the HTML CSP to remove `'unsafe-inline'` scripts when feasible.
9. (Carried, owner) Get legal review of privacy.html and fill in `[DATE]`/`[REGION]`.
10. (Carried, owner) Run `reclassify-gl-accounts` and do a dry run of `check_fixed_asset_useful_life.py` in production. Reverse legacy `bank_import_transfer` entries on 1100/2000.

**Closed since last run (verified in the working tree):**
- 24 Nov High 3 (code; deploy pending).
- Lows 5 (UI duplicate list), 6 (export secret columns), 7 (IRP5/e@syFile audit log, HMAC reset codes) and 9 (test throttle isolation).

**Standing reminders:**
- After Budget Feb 2027, replace the provisional 2027/2028 `TAX_YEARS` entry.
- Run the IFRS 18 / SMEs 3rd ed. checklist in Jan–Feb 2027.
- Next full security sweep: 1 Dec 2026.
