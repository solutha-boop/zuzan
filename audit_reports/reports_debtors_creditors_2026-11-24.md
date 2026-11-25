# ZuZan Audit: Reports, Debtors, Creditors and Security
**Date:** 24 November 2026 (scheduled run)
**Prior report:** 2026-11-23, including its same-day Remediation section.

**Method:**
- Git HEAD is **eac8e09** (= origin/main). The 23 Nov remediation was committed and pushed in 226d544 → eac8e09. The working tree is clean apart from two untracked files in audit_reports/.
- Changed since the last audited code (403da72): 47 files, +884/−138 in the remediation commit. I reviewed every code diff in that range. Accounting files changed only in error-message handling, audit logging, masking and the bank-import duplicate guards.
- I re-ran the anchor greps for every carried checklist item.
- Web checks were done for IFRS and SARS.
- Tests ran on the local VM under Python 3.11.18 (matching runtime.txt 3.11.9) against the throwaway SQLite database from conftest.py. pip-audit was run.
- No client database was opened. zuzan.db, its -wal/-shm files and the .bak file were only checked for existence and for being ignored by git.
- **No code was edited.** 5b is already implemented, the tax tables are report-only, and §7 is report-only.

**Security scope:** **changed-files review** of the remediation diff, plus re-confirmation of every carried finding. The next full sweep is on 1 Dec 2026.

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | **PASS.** No logic change since 23 Nov |
| Debtors (AR) | **FAIL. New High:** the reworked duplicate guard can settle a second invoice when an overlapping statement is re-imported (companies.py:2457-2461) |
| Creditors (AP) | **FAIL.** The same new High applies on the AP side (companies.py:2497-2506) |
| Cross-module | **PASS.** Journal coverage, Rules 6/7 and PPE routing are unchanged |
| IFRS (AFS) | **PASS.** Standards are unchanged and deferred tax is verified |
| Tax (SARS) | **PASS.** Tables are current and nothing new was announced |
| **Security / POPIA** | **FAIL. 2 Critical carried (owner action still outstanding), 0 High, 1 Medium carried.** The remediation code is verified. The cleaned history was **not** pushed, and the prepared bundle is now stale |

## 2. Reports
✓ No issues found. The dashboard and management engine are unchanged:
- `_to_zar` (payroll.py:24), `_received_net_zar` (:34) and `_balance_zar` (:46) are in place.
- The tax provision is 27% (payroll.py:4081).
- The trend loop still uses `_received_net_zar`.
- `/v1/summary` still imports these helpers.

The 23 Nov Low (the payroll-zero rule) was reviewed by the owner and kept by design. **Closed.**

## 3. Debtors
- ✓ `debtors_aging` (payroll.py:4372) filters sent/overdue/partial, ages from `due_date`, uses ZAR balances and excludes paid invoices.
- ✓ A 1100 allocation goes through `_settle_bank_control_line` (companies.py:2442). Unmatched or ambiguous lines are returned in `needs_matching` (companies.py:2803). A line is never posted as a loose `bank_import_transfer`.
- **HIGH (new; introduced by the 23 Nov Low-12 fix), companies.py:2457-2461.** The "already settled" test is now skipped whenever the narrative names a customer who still has an open invoice for the same amount.
  - Example: a customer has a recurring same-amount invoice. Last month's invoice was settled by a statement import, and the user re-imports a statement that overlaps that line (overlapping date ranges are common).
  - The re-imported line names the customer, so the guard is bypassed. `_pick_match` then settles **next month's open invoice** on the old bank date and posts the cash receipt a second time.
  - Result: cash is overstated, debtors are understated, and an invoice the customer has not paid is shown as paid.
  - There is no statement-line-level dedupe on control-account lines, and the frontend does not dedupe either.
  - The old guard failed safe (it skipped the line); the new one fails unsafe.
  - **Fix:** keep the narrative exception, but treat the line as a duplicate when a payment already exists with the same date, amount and named customer. Alternatively, add a per-line import fingerprint (date + amount + description) for control-account lines.
- **Low (new):** the new `duplicates_skipped` list (companies.py:2583) is returned by the API but is not rendered in App_js_fixed.js. Neither is `transfers_skipped`; only `credits_skipped` is shown (App_js_fixed.js:10123). So the "listed to the user" part of the 23 Nov fix is not visible in the UI.

## 4. Creditors
- ✓ The reversal-aware AP lookups are unchanged:
  - payroll.py:3167, :3700 and :4473
  - purchase_orders.py:506
  - journal.py:1498
  - companies.py:2423 (`_po_ap_outstanding`, :2419)
- ✓ Supplier bank details are decrypted and now masked to the last 4 digits (suppliers.py:49; payroll.py:4517).
- **HIGH (new; same root cause as §3), companies.py:2497-2506.** The same-day `po_payment`/`expense_payment` duplicate check is bypassed when the narrative names a supplier that has an unpaid PO or on-credit expense of the same amount. Re-importing a statement therefore pays the next recurring bill (for example rent) a second time, on the old date. **Fix:** the same as §3.

## 5. Cross-module
✓ No issues found. Nothing changed in this area:
- Journal coverage of invoice payments, expense payments, PO receipts, PO payments and payroll is unchanged.
- PPE allocations still go through `_book_bank_asset_purchase` (companies.py:2525).
- Rules 6/7 and the import-awareness rules are unchanged. The remediation diff touched only error text and audit logging in journal.py, purchase_orders.py and payroll.py.

## 6. IFRS compliance (AFS)
- **Framework:** IFRS for SMEs (2nd ed.) presentation, unchanged.
- **Upcoming standards:** IFRS 18 and IFRS for SMEs 3rd ed. are effective 1 Jan 2027. ZuZan's first affected year starts 1 Mar 2027. Today's search found no deferral. **Standards are unchanged since the prior report**, and the Jan–Feb 2027 checklist reminder stands.
- **Finance costs ✓.** `profit_before_tax = ebit − finance_costs` (financial_statements.py:375).
- **Classification ✓.** The helpers are at financial_statements.py:201, :206 and :213, and `_FINANCING_CL_CODES` is at :198.
- **5b deferred tax ✓ (verified, not re-implemented).**
  - `_deferred_tax_balance` is at financial_statements.py:222.
  - Note 9 `deferred_tax` is at :790.
  - The `wear_and_tear_rate` column is at database.py:616, with its migration inside the list at :1658.
- Sources: [IFRS 18 — IFRS Foundation](https://www.ifrs.org/issued-standards/list-of-standards/ifrs-18-presentation-and-disclosure-in-financial-statements/), [IAS Plus — effective 2027](https://www.iasplus.com/en-gb/events/effective-1/2027), [PwC Viewpoint IFRS 18](https://viewpoint.pwc.com/gx/en/IFRS_18_Presentation.html).

## 7. Tax updates (company + payroll)
- **Tax year:** 2026/2027 (1 Mar 2026 – 28 Feb 2027).
- **Rates: all unchanged and current.**
  - `TAX_YEARS["2026/2027"]` is at payroll.py:357, and the provisional 2027/2028 entry is at :377.
  - `_current_tax_year` is at :395.
  - VAT is 15% (payroll.py:21) and CIT is 27% (:4081). The SBC table is at :3512.
  - UIF and SDL are 1%.
- Nothing new was announced by SARS or Treasury.
- Sources: [SARS — Rates of tax for individuals](https://www.sars.gov.za/tax-rates/income-tax/rates-of-tax-for-individuals/), [Budget 2026 Tax guide](https://www.treasury.gov.za/documents/national%20budget/2026/sars/Budget%202026%20Tax%20guide.pdf), [SARS — companies / SBC](https://www.sars.gov.za/tax-rates/income-tax/companies-trusts-and-small-business-corporations-sbc/).

## 8. Security and data protection (changed-files review + carried items)
1. **Tenant isolation ✓.**
   - The new `build_company_export` (companies.py:319) selects only `company_id == cid` rows, plus child tables reached by foreign key from those rows. The child tables are payslips, garnishees, benefits, PO items and journal lines; none can reach another company.
   - `close_account` (companies.py:373) touches only this company's users and memberships.
   - The new masking and `?full=1` changes are company-scoped.
2. **Authentication / authorisation ✓.**
   - Data export and close-account are `require_role("owner")`.
   - `GET /employees/?full=1` is limited to owner/admin/payroll and audit-logged (companies.py:2127-2139).
   - Portal links now expire (portal.py:68-90), and reset codes are stored hashed (auth.py:758 and :769).
   - **Low:** `/payroll/irp5` (payroll.py:2080) returns full ID and tax numbers to any role except employee, including accountant. This is needed for SARS, but unlike `?full=1` it is not audit-logged.
3. **Passwords / sessions ✓.**
   - PyJWT decode pins `algorithms=[ALGORITHM]` (auth.py:175; main.py:387).
   - **Medium (carried, owner):** `/health` exposes `secret_key_configured`, but the code fallback is unchanged (auth.py:33-39). Confirm a dedicated SECRET_KEY is set in Render.
   - **Low:** reset codes are an unsalted SHA-256 of a 32-bit code, so they are brute-forceable offline if the database leaks. They still expire after 30 minutes, so the risk is small.
4. **Encryption and secrets: FAIL (carried Critical).**
   - **CRITICAL (carried): the history purge was not pushed.** origin/main is eac8e09, and `git log --all -- zuzan-backend/zuzan.db` still lists 070d83e, b9a757d, 2b40163 and b3e5acf. The GitHub-token prefix is still in historical commits (for example 8b2627d and 690f833), even though HEAD is redacted.
     - The prepared `_history_clean/zuzan-clean-history.bundle` (tip eac3243) was built from 226d544. Its push script requires GitHub main to equal 226d544, so it will now **refuse to run**. The rewrite must be regenerated from eac8e09 before it can be pushed.
     - I cannot confirm that the token was revoked.
   - **CRITICAL (carried):** revoke the GitHub PAT (owner).
   - ✓ The 23 Nov High is fixed:
     - `Employee.id_number`/`tax_number` use `EncryptedString` (database.py:208, :210), with an HMAC blind index (crypto.py `blind_index`).
     - crypto.py now refuses to start on Render without a valid key (crypto.py:28-37).
     - The Sentry DSN comes from the environment (main.py:43).
     - **Low:** the old Sentry DSN is still in git history; rotate it in Sentry. `blind_index` falls back to a fixed key when FIELD_ENCRYPTION_KEY is unset; this cannot happen on Render.
   - ✓ `git ls-files` shows no database, .env, key or backup file. zuzan.db, its -wal/-shm files, the .bak file and `_history_clean/` are all gitignored.
5. **Input handling ✓.**
   - All CSV/Excel imports go through `read_upload` (10 MB, CSV/Excel only).
   - The sanitiser is in place before the only `dangerouslySetInnerHTML`.
   - No new raw SQL was added.
6. **Data exposure ✓, with Low items.**
   - Employee ID, tax and bank numbers and supplier account numbers are masked.
   - 33 handlers now use `public_error`.
   - Sentry has a `before_send` scrubber and local variables turned off (main.py:26-40).
   - **Low (new):** the data export omits secret columns by name (companies.py:298-301), but the list misses `users.email_verify_token` and `employees.clock_pin_hash`. Both would appear in the owner's export file. Add them to `_EXPORT_SECRET_COLUMNS`.
7. **Web / transport ✓.**
   - CSP is set on API responses and HTML (security.py:131-186), and netlify.toml has a `[[headers]]` block.
   - Tokens are still stored in localStorage. This is an accepted residual risk, reduced by the CSP.
   - **Low:** the HTML CSP allows `'unsafe-inline'` scripts.
8. **POPIA ✓.**
   - `log_action` now covers clear-data, employee CRUD, full-number views, profile and lock-date changes, bank imports, journal reversal/redate, export and closure.
   - Export and closure exist, closure records a 5-year retention date, and privacy.html is present.
   - **Carried (owner):** legal review of privacy.html and the `[DATE]`/`[REGION]` placeholders.
9. **Tests and dependencies.**
   - Security run: test_auth_security, test_security_hardening, test_security_audit_2026_11_23 and test_bank_control_allocations gave **37 passed, 1 failed**.
   - The failure is `test_close_account_requires_name_and_blocks_all_access`. It gets 429 instead of 401 when run after the other security files, because the in-memory login throttle carries state between test files. It **passes alone** (10/10). This is a test-isolation issue, not a security defect (Low).
   - **pip-audit on requirements.txt: no known vulnerabilities.**
   - npm audit was not run.

## 9. Action items
**Critical**
1. (Carried, owner) Purge `zuzan-backend/zuzan.db` and the GitHub-token prefix from git history. **The prepared bundle is stale:**
   - regenerate the filter-repo rewrite from eac8e09 (or update the guard in push_clean_history.ps1);
   - force-push it;
   - ask GitHub Support to purge cached refs;
   - re-clone other copies;
   - assess POPIA s22 if real client data was ever in that database.
2. (Carried, owner) Revoke the GitHub PAT whose prefix appeared in the Aug/Sep reports.

**High**

3. (New) companies.py:2457-2461 and :2497-2506: the duplicate guards on re-imported bank lines allocated to 1100/2110 can settle the next same-amount invoice, PO or expense and double-post cash. Keep a duplicate check that matches on date + amount + named counterparty (or add a per-line import fingerprint), and add a regression test that re-imports a statement while a recurring same-amount document is open.

**Medium**

4. (Carried, owner) Set a dedicated SECRET_KEY, SENTRY_DSN and CORS_ORIGINS in Render, and confirm `/health` shows `field_encryption: true` and `secret_key_configured: true`.

**Low**

5. (New) App_js_fixed.js around :10123: show `duplicates_skipped` and `transfers_skipped` in the bank-import result.
6. (New) companies.py:298-301: add `email_verify_token` and `clock_pin_hash` to `_EXPORT_SECRET_COLUMNS`.
7. (New) payroll.py:2080: audit-log IRP5 retrievals, since they return full ID and tax numbers. Consider salting or HMAC-ing reset-code hashes.
8. (New) Rotate the old Sentry DSN that is still in git history.
9. (New) tests: reset the in-memory login throttle between test modules so the security suite passes when run together.
10. (Carried, owner) Get legal review of privacy.html and fill in `[DATE]`/`[REGION]`.
11. (Carried, owner) Run `reclassify-gl-accounts` and do a dry run of `check_fixed_asset_useful_life.py` in production. Reverse legacy `bank_import_transfer` entries on 1100/2000.

**Closed since last run (verified in eac8e09):**
- 23 Nov High 3: employee ID/tax encryption.
- Mediums 5-10: field-encryption fail-closed, masking, audit logging, dependencies, POPIA export/closure plus `public_error` plus CSP, and upload limits.
- Lows 11-14: payroll-zero rule kept by design; Sentry/CORS/headers/.gitignore; portal expiry and hashed reset codes.
- Medium 4 is only partly closed: the code is in, but the Render setting is unconfirmed.

**Standing reminders:**
- After Budget Feb 2027, replace the provisional 2027/2028 `TAX_YEARS` entry.
- Run the IFRS 18 / SMEs 3rd ed. checklist in Jan–Feb 2027.
- Next full security sweep: 1 Dec 2026.

---

## Remediation (24 Nov 2026, on request; uncommitted working-tree changes on top of eac8e09)

**High 3: fixed.** The bank-import duplicate guards are now in `_already_settled_today` (companies.py, just above `_settle_bank_control_line`). A line counts as already settled when a settlement journal exists on the same bank date for the same amount:
- `invoice_payment` for AR; `po_payment` or `expense_payment` for AP;
- the settled document must still be paid (a reversed payment does not count).

How the guard decides:
- If the narrative names the counterparty of that settlement, the line is a duplicate (a re-imported line).
- If the narrative names nobody, the line is a duplicate; this is the fail-safe case.
- If the narrative names a different counterparty that has an open document of this amount, the line is not a duplicate and is settled.

Re-importing an overlapping statement therefore no longer settles the next recurring invoice or bill.

Two regression tests were added to tests/test_bank_control_allocations.py: a recurring invoice re-import, and recurring rent plus a different supplier paid on the same day. Both fail on the old code and pass on the new.

**Low items: fixed.**

5. The bank-import result screen now lists the skipped duplicate lines (date, narrative, amount) with guidance, and shows other skipped balance-sheet lines (App_js_fixed.js, synced to zuzan-app/src/App.js).
6. `email_verify_token` and `clock_pin_hash` are added to `_EXPORT_SECRET_COLUMNS`.
7. `/payroll/irp5` and `/payroll/easyfile-export` now write audit-log entries. Reset codes are stored as HMAC-SHA256 keyed with SECRET_KEY (`hmac:` prefix). The 23 Nov `sha256:` format is still accepted for codes issued just before the deploy.
9. tests/conftest.py now resets the login/reset rate limits at the start of every test module. The close-account test passes when run after the other security files; without the fix the same combination fails.

**Critical 1: the history rewrite has been rebuilt from eac8e09** (git filter-repo, all 697 commits).
- Removed from every commit: zuzan.db, *.db.bak*, -wal and -shm.
- Redacted: every `ghp_…` token, and the old backend Sentry DSN. The browser DSN in App.js is public by design and is kept.
- Checks on the rewritten history: 0 commits touch zuzan.db, and 0 token or backend-DSN matches.
- The tip tree is identical to eac8e09 except main_py_fixed.py, an unused copy, whose DSN line is redacted the same way in the working tree.
- The new bundle is `_history_clean/zuzan-clean-history.bundle` (tip 099faae). `push_clean_history.ps1` is updated to expect GitHub main = eac8e09.

**Owner actions (cannot be done from here):**
1. **Revoke the GitHub PAT** (Critical 2) in GitHub → Settings → Developer settings.
2. **Run `_history_clean\push_clean_history.ps1` BEFORE `commit_and_push.bat`.** If anything else is pushed first, GitHub main moves and the script will refuse again. Then:
   - ask GitHub Support to purge cached views and refs;
   - re-clone any other copies;
   - assess POPIA s22 if zuzan.db ever held real client data.
3. Run `commit_and_push.bat` to commit today's fixes.
4. In Render, set SECRET_KEY (32+ random characters), SENTRY_DSN and CORS_ORIGINS. **Rotate the old backend Sentry DSN** in Sentry, then check `/health`.
5. Carried items: legal review of privacy.html (`[DATE]`/`[REGION]`), and the production data clean-up (reclassify-gl-accounts, legacy `bank_import_transfer` reversals).

**Tests (Python 3.11.18, throwaway SQLite):**
- All 67 test files pass when run in batches.
- The only failure in the batched run was test_payroll_journal_balance_runner. That was a sandbox limitation: the script cannot delete its own temporary database inside the mounted folder. The underlying script passes in a scratch copy (18/18 scenarios balanced).
- The JSX parses, and pip-audit is clean.
