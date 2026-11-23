# ZuZan Audit: Reports, Debtors, Creditors and Security
**Date:** 23 November 2026 (scheduled run)
**Prior report:** 2026-11-22, including its same-day Remediation addendum.

**Method:**
- I checked git: HEAD is **403da72**, 13 commits since the audited b7fff99. There are uncommitted changes in App_js_fixed.js, csv_import.py, quickbooks_migrate.py and xero_migrate.py, plus one new untracked test.
- I re-ran the anchor greps for every carried item and read the new remediation code.
- I did web checks for IFRS and SARS changes.
- I installed the test dependencies on the local VM and ran the security and tenant tests against the throwaway SQLite database that conftest.py sets up. I also ran pip-audit.
- No client database was opened. zuzan.db, its -wal/-shm files and the .bak file were only checked for existence and git tracking.
- **No code was edited.** 5b was already implemented, the tax tables are report-only, and §7 is report-only.

**Security scope:** this is the **first run with checklist section 7**, so it is a **full sweep** of all backend routers and App_js_fixed.js, not a changed-files-only review.

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | **PASS.** The dashboard now takes its P&L from the Management Pack engine (`/reports/dashboard`, payroll.py:2543 → `management_accounts`, payroll.py:3948). Revenue counts paid invoices only, ex-VAT, through `_received_net_zar`/`_to_zar`. One Low observation |
| Debtors (AR) | **PASS. The High from 22 Nov is closed.** A 1100 allocation now settles the invoice through `_settle_bank_control_line` (companies.py:2303) or is returned in `needs_matching` |
| Creditors (AP) | **PASS. The High from 22 Nov is closed.** A 2110/2000 allocation now settles the PO or on-credit expense, using reversal-aware `_po_ap_outstanding` (companies.py:2280) |
| Cross-module | **PASS. The Medium from 22 Nov is closed.** PPE allocations now go through `_book_bank_asset_purchase` (companies.py:2380). Rules 6/7 report legacy `bank_import_transfer` amounts |
| IFRS (AFS) | **PASS. The Medium from 22 Nov is closed.** The classification helpers are at financial_statements.py:201-216. Standards are unchanged and deferred tax is verified |
| Tax (SARS) | **PASS. The Low from 22 Nov is closed** (PAYE example updated). Tables are current |
| **Security / POPIA** | **FAIL: 2 Critical, 1 High, 6 Medium, several Low (all newly reported; this is the first §7 sweep).** The worst item is a client-database file in git history. Tenant isolation, authentication and webhooks pass |

**Overall:**
- **Accounting:** 0 Critical, 0 High, 0 Medium open in code. The 3 High/Medium items and 2 Low items from 22 Nov are verified fixed.
- **Security:** 2 Critical, 1 High, 6 Medium. All are new findings, because this is the first sweep.

## 2. Reports
✓ No issues found in the checklist items:
- **Revenue.** It is `pl["revenue"]` (payroll.py:2580). The engine sums `_received_net_zar` over paid invoices, which takes `paid_amount_zar` for non-ZAR invoices and amount × rate otherwise, through `_to_zar` (payroll.py:23). Bank-import income and GL-import income are added on top. Expenses are never added to revenue.
- **Outstanding.** It covers sent + overdue + partial invoices, using `_balance_zar` (payroll.py:2586 and :4088). There is no `pending` status in the enum.
- **Expenses.** Payroll comes from period payslips (payroll.py:4060-4072). Received-PO cost comes through `_po_cost_net` and `_stock_pl_cost` as one COGS figure, with no double count. The tax provision is 27% (payroll.py:4079).
- **Trend loop.** It uses `_received_net_zar` (payroll.py:4105).
- **`/v1/summary`.** It imports `_to_zar`/`_balance_zar`/`_received_net_zar` (main.py:530-533).
- **Low (new observation), payroll.py:4067-4071.** When a period has no payslips but has *any* GL-import or manual-journal revenue or expense, payroll is set to 0. This assumes the staff costs are in the GL. A company that imports only revenue journals but pays staff outside ZuZan would show no payroll cost. The opposite case can also occur: payslips plus an imported GL that already contains salaries would double-count. Consider basing the rule on salary-type GL accounts rather than "any GL activity".

## 3. Debtors
✓ **The High from 22 Nov is closed.** The bank import (companies.py:2437-2464) calls `control_account_allocation` first. This is journal.py:347-353, which maps 1100→ar and 2110/2000→ap. Only after that does it reach `is_balance_sheet_allocation`, so a 1100 line can never become a loose `bank_import_transfer`.
- Receipts settle the named open invoice, or the single open invoice with the same amount. The settlement uses `post_invoice_paid`, dated on the bank date.
- Lines with no match, more than one match, or a non-ZAR invoice are returned in `needs_matching` (companies.py:2651) and are not posted.

Debtors otherwise ✓:
- `debtors_aging` (payroll.py:4369) filters sent/overdue/partial and ages from `due_date`.
- Balances are in ZAR through `_balance_zar`, and paid invoices are excluded.

**Low (new):** the duplicate guard at companies.py:2320-2323 treats a receipt as already settled when a paid invoice of the same ZAR amount was paid that day. If there is only one such invoice, it matches even when that invoice is not named in the narrative. A second, genuine same-amount receipt on the same day would then be skipped, and its invoice stays open. This fails safe (no double posting), but the user sees it only in the skip count. Consider requiring the narrative match for the duplicate test, or listing skipped lines.

## 4. Creditors
✓ **The High from 22 Nov is closed.** Payments allocated to 2110/2000 settle a received or partial PO for its reversal-aware AP balance. `_po_ap_outstanding` nets credit − debit across purchase_order, purchase_order_reversal, po_payment and po_payment_reversal (companies.py:2280-2290). Otherwise they settle an unpaid on-credit expense. Both are dated on the bank date: `post_po_paid(when=day)` and `paid_at=day`.

Reversal-aware lookups ✓ in all of these places:
- payroll.py:3166 (Rule 7)
- payroll.py:3699 and :4471 (creditors aging / management)
- purchase_orders.py:505 (`pay_po`)
- journal.py:1498 (backfill)
- companies.py:2284

Creditors otherwise ✓:
- Supplier bank fields are decrypted with `decrypt_field` (suppliers.py:48-50; payroll.py:4514-4516).
- Received-unpaid POs are outstanding, and paid POs are excluded.

**Low (new):** the AP duplicate guard at companies.py:2341-2347 skips any bank debit when a `po_payment`/`expense_payment` of the same amount already exists that day, even one for a different supplier. This also fails safe.

## 5. Cross-module
- Journal coverage ✓: invoice payments, expense payments, PO receipts, PO payments and payroll runs.
- ✓ **PPE fix (Medium, closed).** `ppe_allocation_category` (journal.py:365) routes 1211-1219 and 1500 to `_book_bank_asset_purchase`. That creates a FixedAsset and posts DR 1500 / DR 1300 / CR 1000. Receipts are refused and directed to Dispose.
- ✓ **Rules 6/7.** They now report legacy `bank_import_transfer` amounts on 1100/2000 (payroll.py:3125-3129 and :3212-3217) and still exclude `import` lines.
- ✓ **Import-awareness** is unchanged:
  - invoice/expense imports still auto-run the backfill;
  - unbalanced journal groups are rejected;
  - non-ZAR invoice imports need an exchange rate;
  - 3998/3999 and imported equity, asset and liability accounts stay on the balance sheet.
- Note: the uncommitted csv_import.py work (+424 lines) passed the tenant-scope scan (no unscoped id lookups). Its new test test_import_screen_audit.py was not run this time.

## 6. IFRS compliance (AFS)
- **Framework:** unchanged, IFRS for SMEs (2nd ed.) presentation (Section 3/4/5/7 statements and notes).
- **Upcoming standards:** IFRS 18 and IFRS for SMEs 3rd ed. are effective for periods beginning on or after 1 Jan 2027. ZuZan's first affected FY starts 1 Mar 2027. Today's search found no deferral and no new pronouncement. **Standards are unchanged since the prior report.** The Jan–Feb 2027 checklist reminder stands; see audit_reports/ifrs_smes_3rd_edition_transition_plan.md.
- **Finance costs ✓.** Account 6700 and name-matched lines are below EBIT (financial_statements.py:320-326). `profit_before_tax = ebit − finance_costs` (financial_statements.py:375), and tax derives from PBT.
- **Classification ✓ (the 22 Nov Medium is closed):**
  - `_is_non_current_asset` (financial_statements.py:201) treats 1210-1229 as non-current.
  - `_is_ppe_cost_code` (financial_statements.py:206): movements on 1210-1219 are investing (financial_statements.py:579); 1220-1229 stay in operating as the add-back (financial_statements.py:551).
  - `_is_non_current_liab` (financial_statements.py:213) treats 2410/2420 as non-current and financing.
  - `_FINANCING_CL_CODES` 2150/2160 are current, with financing cash flows (financial_statements.py:198 and :584).
- **5b deferred tax: verified, still computed** (no hard-coded 0.0):
  - `_deferred_tax_balance` is at financial_statements.py:222.
  - Opening/closing balances and the movement are at financial_statements.py:387-389.
  - Note 9 `deferred_tax` is at financial_statements.py:790, with `total_tax = current + deferred` at :785.
  - The equity adjustment is at :872.
  - The `wear_and_tear_rate` column is at database.py:610, and its migration sits inside the list at :1639.
  - The frontend renders it at App_js_fixed.js:15678 and the DTL/DTA rows at :14208.
- Sources: [IFRS 18 — IFRS Foundation](https://www.ifrs.org/issued-standards/list-of-standards/ifrs-18-presentation-and-disclosure-in-financial-statements/), [IASB technical update Nov 2026](https://www.ifrs.org/content/dam/ifrs/meetings/2026/november/eeg/ap3-iasb-technical-update.pdf), [IAS Plus — effective 2027](https://www.iasplus.com/en-gb/events/effective-1/2027).

## 7. Tax updates (company + payroll)
- **Tax year:** 2026/2027 (1 Mar 2026 – 28 Feb 2027).
- **Rates: all unchanged.**
  - `TAX_YEARS["2026/2027"]` is at payroll.py:356 (the lines moved since 22 Nov because of edits higher in the file). Values are unchanged: rebates R17,820 / R9,765 / R3,249 and UIF ceiling R17,712.
  - The provisional "2027/2028" entry is at payroll.py:376.
  - `_current_tax_year` is at payroll.py:394.
  - UIF is 1% employee and 1% employer, and SDL is 1% (payroll.py:413-414).
  - VAT is 15% (payroll.py:20).
  - CIT is 27% (payroll.py:4079), and the SBC table is at payroll.py:3511.
- I found no new SARS or Treasury announcements.
- ✓ The stale PAYE example (the 22 Nov Low) is fixed.
- Sources: [SARS — Rates of tax for individuals](https://www.sars.gov.za/tax-rates/income-tax/rates-of-tax-for-individuals/), [Budget 2026 Tax guide](https://www.treasury.gov.za/documents/national%20budget/2026/sars/Budget%202026%20Tax%20guide.pdf), [SARS — Budget 2026 FAQ](https://www.sars.gov.za/about/sars-tax-and-customs-system/budget/budget-2026-frequently-asked-questions/).

## 8. Security and data protection (full sweep, first §7 run)
1. **Tenant isolation ✓.**
   - An AST scan of every route found no record-id lookup on client models without a `company_id` scope. The unscoped `User.id` reads in auth.py:1178 and :1219 are only reached after a company-scoped `CompanyMembership` check.
   - `reverse_entry_by_id` (journal.py:1659) is only called after a scoped lookup (journal.py:2048-2051).
   - On switch-company, membership is re-verified on every request (auth.py:194-205).
   - The practice MCP is read-only (no add/commit in practice_mcp.py). It is limited to the user's memberships (practice_mcp.py:57-68), and its token is compared with `hmac.compare_digest` and must be at least 32 characters (practice_mcp.py:36-43).
   - Kiosk endpoints are scoped by kiosk token.
2. **Authentication / authorisation ✓.**
   - The public routes are all deliberate: login, register, reset, invite, verify-email, health, the PayFast ITNs, the bank OAuth callbacks (with a random 15-minute state, bank_direct_feeds.py:98-104), the portal token links, the kiosk, the analytics `/track` endpoint, and fixed-asset reference tables.
   - The `/admin` page is static HTML. Its APIs require `ADMIN_SECRET`, compared with `compare_digest` (main.py:856).
   - A server-side role policy (auth.py:149-165) blocks payroll/employee roles outside their own areas.
   - Clear-data is owner-only (companies.py:373).
   - PayFast ITNs verify the signature and do a remote VALID check (billing.py:333-338, :711-720; portal.py:46, :57). The legacy `/payroll/notify` returns 410.
   - API keys are stored as SHA-256 hashes and scoped to one company (api_keys.py:19-48).
   - Invite tokens use `token_urlsafe(32)` and expire after 48h.
   - **Low:** journal reversal (journal.py:2036), redate-reversals (journal.py:1994) and lock-date changes (companies.py:160/185) are also open to the `accountant` role, not only owner/admin. This is acceptable for an accountant workflow; just confirm it is intended.
   - **Low:** the reset code is 8 hex characters, stored in plaintext and looked up by code alone (auth.py:756, :776). It is throttled and expires after 30 minutes. Portal tokens (uuid4, companies.py:1290) never expire.
3. **Passwords / sessions ✓, with one Medium.**
   - Passwords use bcrypt via passlib (auth.py:59).
   - JWT uses HS256 pinned on decode (auth.py:174-177), with a 24h expiry. Tokens are invalidated when the password changes (`pv` claim).
   - Login is throttled per account and per IP, and reset is throttled per IP and globally (auth.py:19-22). There is no hard-coded default password; the old empty→default behaviour was removed at auth.py:101.
   - **Medium:** the `SECRET_KEY` default at auth.py:33 is a usable literal. On Render it is replaced by a key derived from DATABASE_URL (auth.py:34-39), so anyone who has the DB URL can forge tokens. Set a dedicated random SECRET_KEY in Render and confirm the CRITICAL log line is absent.
   - **Low:** the throttles are in-memory and per process.
4. **Encryption and secrets: FAIL.**
   - **CRITICAL: a client database is in git history.** `zuzan-backend/zuzan.db` was committed in 070d83e (28 May) and grown in b9a757d and 2b40163 (up to ~770 KB on 28 Sep). It was removed from the tree in b3e5acf (29 Sep), but it is still in history and was pushed to the `origin` GitHub remote. I could not check whether that repo is private, because this scheduled run has no GitHub access to it. The Oct reports listed a history purge only as an open decision. If that database held any real company or employee data, this is a POPIA notifiable-breach question. **Owner:** confirm repo visibility. Purge the file from history (git filter-repo + force-push, and ask GitHub to clear cached views). If any real data was in it, rotate anything derived from it and assess s22 POPIA notification.
   - **CRITICAL: a GitHub token prefix is in tracked files.** The 26–30 Aug audit reports (audit_reports/reports_debtors_creditors_2026-08-26.md:10/89 through -08-30.md:106, 18 .md files in all) quote a 35-character GitHub personal-access-token prefix. It appears as the name of a file that was later deleted. audit_reports/ is tracked and pushed. A later report marked the file deleted but never confirmed the token was **revoked**. **Owner:** revoke that token in GitHub now, if not already done. Redact the prefix from those reports and purge it from history.
   - **HIGH: employee identity and tax numbers are stored in plaintext.** `Employee.id_number` / `tax_number` (database.py:203-204) are stored and matched as plaintext (csv_import.py:2387, :2578; companies.py:1842 create path) and returned unmasked (payroll.py:2137-2138). Employee and supplier bank fields **are** encrypted with `encrypt_field` (companies.py:2051-2054, :2097; suppliers.py; bank-feed tokens bank_direct_feeds.py:238 and following).
   - **Medium:** `crypto.py:16-27` fails open. If `FIELD_ENCRYPTION_KEY` is missing or invalid, every "encrypted" field is silently written in plaintext and only a warning is logged. Confirm the key is set in Render, and consider refusing to start in production without it.
   - **Low:** the Sentry DSN is hard-coded at main.py:6. It is an ingest key that can only send events, but it should move to an environment variable.
   - ✓ No other secrets are hard-coded in the backend or App_js_fixed.js.
   - ✓ .gitignore covers .env, *.db/-wal/-shm/-journal, *.db.bak*, *.log and _to_delete/. **Low:** it has no `uploads/` or `exports/` patterns. Documents are stored in the DB, so the risk is low.
   - ✓ `git ls-files` shows no database, .env, key or backup tracked today.
5. **Input handling ✓, with one Medium.**
   - No f-string SQL on user input; the only one is journal_check.py:107, an offline script using fixed table names.
   - Documents are capped at 10 MB, stored in the DB (no filesystem path, so no traversal), and served as attachments (documents.py:18, :72, :130).
   - There is a global 25 MB body cap (security.py:100, :157).
   - `invoice_template_html` is cleaned server-side (companies.py:178-179) and with `sanitizeHtml` before the only `dangerouslySetInnerHTML` (App_js_fixed.js:1404).
   - Logos are never fetched remotely (payroll.py:1930). Outbound calls go only to fixed bank and PayFast URLs, so there is no SSRF.
   - **Medium:** CSV/Excel import endpoints read the whole upload (csv_import.py:374, :440, :509, :714, :812, :1471 …) with no per-route size or type check beyond the 25 MB global cap.
6. **Data exposure: Medium.**
   - ✓ No password hash or secret appears in responses. PayFast credentials are masked (companies.py:136-138), and company bank details are shown only to finance roles.
   - **Medium:** employee bank details (companies.py:1963-1966), supplier account numbers (suppliers.py:49; payroll.py:4515) and employee ID/tax numbers are returned in full, not masked.
   - **Medium:** 28 handlers return `str(e)` or `{e}` in `detail`, which can leak internals. accountant.py:188 logs a contact email address.
   - ✓ Sentry has `send_default_pii=False` (main.py:10), but there is no `before_send` scrubber.
7. **Web / transport ✓, with Low items.**
   - CORS is "*" **without** credentials when `CORS_ORIGINS` is unset (main.py:227-252). The API uses bearer tokens, so this is hygiene. **Low:** set `CORS_ORIGINS` on Render.
   - The backend sets HSTS, nosniff, X-Frame-Options DENY and Referrer-Policy (security.py:122-127).
   - **Low:** netlify.toml has no `[[headers]]` block (no CSP/HSTS) for the landing page.
   - **Medium:** the JWT is stored in `localStorage` (`zuzan_token`, App_js_fixed.js:98 and others), so any XSS would expose a 24h token. The HTML sanitiser reduces this risk; a CSP would reduce it further.
8. **POPIA: Medium.**
   - **Medium:** `log_action` is used in auth, clocking, accountant, journal and management_report only. companies.py imports it but never calls it, so clear-data, employee create/update/delete, bank imports and company-profile changes are not audit-logged.
   - **Medium:** there is no whole-company data export (subject access / portability) and no account-closure endpoint. Clear-data (owner-only and company-scoped) is the only deletion path. Before deleting, check the retention rule: SARS and the Tax Administration Act require 5 years.
   - privacy.html exists and broadly matches the data collected (bank feeds, Sentry, PayFast, Anthropic, Render). It still has `[DATE]`/`[REGION]` placeholders, and its statement that bank details are encrypted at rest depends on item 4. The owner legal review is carried.
9. **Tests and dependencies.**
   - The security tests **passed**: test_auth_security, test_security_hardening and test_cors_and_docs gave 25 passed, 1 skipped. test_accountant, test_accountant_company_profile, test_practice_mcp, test_portal_payfast, test_clock_kiosk_pin, test_plan_gates and test_bank_control_allocations gave 36 passed. All ran on the throwaway SQLite database.
   - **pip-audit (Medium):** run against requirements.txt (the installed versions).
     - starlette 0.37.2 has multipart/DoS advisories; fixed at ≥0.40, and the latest fix is 1.3.1.
     - pillow 12.3.0 has 42 advisories; fixed in 13.0.0.
     - cryptography 49.0.0 has 2 advisories; fixed in 50.0.0.
     - pyasn1 0.4.8 is fixed in 0.6.5.
     - dnspython 2.8.0 is fixed in 2.9.2.
     - python-jose 3.4.0 and ecdsa 0.19.2 have advisories with no fixed release. HS256 pinning mitigates this; consider moving to PyJWT.
   - npm audit was not run.

## 9. Action items
**Critical**
1. (New, owner) Git history still contains `zuzan-backend/zuzan.db` (commits 070d83e → 2b40163), and it was pushed to origin.
   - Confirm repo visibility.
   - Purge it with git filter-repo and force-push, then ask GitHub support to remove cached refs.
   - If it ever held real client data, assess POPIA s22 notification.
2. (New, owner) Revoke the GitHub PAT whose prefix is quoted in audit_reports/reports_debtors_creditors_2026-08-26 … -08-30 (and other Aug/Sep reports, 18 files in all). Redact the prefix and purge it from history.

**High**

3. (New) database.py:203-204, companies.py:1842-2097, csv_import.py:2387/2578, payroll.py:2137: encrypt `Employee.id_number`/`tax_number`. For duplicate matching, store a keyed hash (HMAC) and match on that. Mask them in API responses.

**Medium**

4. (New) auth.py:33-39: set a dedicated random `SECRET_KEY` in Render, and do not rely on the DATABASE_URL-derived fallback.
5. (New) crypto.py:16-27: refuse to start in production when `FIELD_ENCRYPTION_KEY` is missing or invalid. Confirm it is set in Render.
6. (New) companies.py:1963-1966, suppliers.py:49, payroll.py:4515: mask bank account numbers (last 4) except in EFT/export flows.
7. (New) companies.py (clear-data :370, employee CRUD, bank import) and payroll.py: add `log_action` calls for sensitive actions.
8. (New) Upgrade starlette/fastapi, pillow, cryptography, pyasn1 and dnspython. Plan the move from python-jose to PyJWT.
9. (New) Add a whole-company POPIA export and an account-closure flow that respects the 5-year retention rule. Stop returning `str(e)` in 28 handlers. Add a CSP and consider moving tokens out of localStorage.
10. (New) csv_import.py: add per-route size and type limits on CSV/Excel uploads.

**Low**

11. (New) payroll.py:4067-4071: base the payroll-zero rule on salary-type GL accounts.
12. (New) companies.py:2320 and :2341: tighten the same-day duplicate guards, or list the skipped lines to the user.
13. (New) main.py:6: move the Sentry DSN to an environment variable and add a `before_send` scrubber. Set `CORS_ORIGINS`. Add security headers to netlify.toml. Add `uploads/` and `exports/` to .gitignore.
14. (New) Give portal tokens an expiry, and hash reset codes at rest. Confirm that accountant-role access to journal reversal and lock date is intended.
15. (Carried, owner) Run `reclassify-gl-accounts` and do a dry run of `check_fixed_asset_useful_life.py` in production.
16. (Carried, owner) Get legal review of privacy.html, fill in `[DATE]`/`[REGION]`, then publish it.
17. (Carried, owner) Production data clean-up from 22 Nov: reverse legacy `bank_import_transfer` entries on 1100/2000, and register any assets already booked to 1212-1214.

**Closed since last run:** the 22 Nov High (1100/2110 allocations), both Mediums (PPE allocation, AFS classification) and both Lows (PAYE example, inventory warning). All are verified in committed code at HEAD 403da72.

**Standing reminders:**
- After Budget Feb 2027, replace the provisional 2027/2028 `TAX_YEARS` entry.
- Run the IFRS 18 / IFRS for SMEs 3rd ed. checklist in Jan–Feb 2027.
- Next security full sweep: 1 Dec 2026.
