# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 29 September 2026 (scheduled run)
**Scope:** Reports, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS (AFS), SARS tax rates
**Prior report:** 2026-09-27 (22:19 UTC follow-up, PASS)

**Change detection:** HEAD is now `45a5aa8` (was `f5cf4e1` at last report; 9 more commits, all re-commits of the same billing/admin work with a reused commit message). `git diff --stat f480d17 HEAD` on `payroll.py`, `financial_statements.py`, `journal.py`, `purchase_orders.py`, `database.py`, `csv_import.py`, `suppliers.py`, `customers.py` is **empty** — all remain byte-identical to the last fully verified baseline. Files changed since last report: `companies.py` (1 line: `subscription_status` enum → `.value`), `main.py` (+71: admin `activate` next_billing_date fix, new admin `clear-data` endpoint + dashboard button), `App_js_fixed.js` (1 line: sidebar shows "Active subscription"), `commit_and_push.bat`, and the binary `zuzan.db`. Line anchors below were re-grepped this run and match.

## 1. Summary

| Section | Verdict |
|---|---|
| Reports | ✅ PASS — unchanged |
| Debtors (AR) | ✅ PASS — unchanged |
| Creditors (AP) | ✅ PASS — unchanged, reversal-awareness intact |
| Cross-module | ⚠️ PASS with one Medium note — new admin clear-data endpoint (see §5) |
| IFRS (AFS) | ✅ PASS — no standards changes; deferred tax (5b) present, no edit needed |
| Tax (SARS) | ✅ PASS — 2026/2027 tables current, no rate changes |

**Overall: PASS.** No Critical/High findings. One Medium (git-tracked SQLite DB) and one Low (admin clear-data omits `import` journal source / credit notes).

## 2. Reports
✓ No issues found. `payroll.py`: `dashboard()` `:1649`, `total_revenue = sum(_to_zar(i) …paid…)` `:1661`, `total_outstanding` `:1669` (`_to_zar`), `management_accounts()` `:2860`, revenue `:2894`, outstanding `:2969`, trend loop `:2986` (`_to_zar`). `/v1/summary` in `main.py` unchanged by this diff. Expenses/PO COGS/payroll remain separate expense-side aggregates (no revenue overlap, no double-count).

## 3. Debtors
✓ No issues found. `debtors_aging()` `payroll.py:3252` unchanged (`_to_zar`, aged from `due_date`, paid excluded). Frontend files changed only in the sidebar subscription label.

## 4. Creditors
✓ No issues found. `creditors_aging()` `:3315` unchanged (received/partial POs, paid excluded, `decrypt_field` on bank details). Reversal-awareness (`credit − debit`, `purchase_order` + `purchase_order_reversal`) confirmed at `payroll.py:2202`, `:2674`, `:3350`, `purchase_orders.py:445`, `journal.py:1158`, and `financial_statements.py:~542`.

## 5. Cross-module
- Journal coverage for invoice payments, expense payments, PO receipts, PO payments and payroll unchanged (`journal.py`). Import-awareness (auto backfill, Rules 6/7 excluding `source="import"`, 3998/3999, unbalanced import groups rejected, non-ZAR import requires rate) — `csv_import.py`/`journal.py` byte-identical, so still in place.
- **New: `POST /admin/api/clients/{id}/clear-data` (`main.py`, new this window).** Reuses `_CATEGORY_JOURNAL_SOURCES` / `_clear_journal_for_sources`, so it purges journal postings in lock-step with sub-ledger rows for all 9 categories — consistent with the 09-27 fix. Two gaps:
  - (Low) Neither this endpoint nor the user-facing `/companies/clear-data` maps `source="import"` (CSV-imported journal lines) or credit-note postings; deleting invoices/expenses leaves those journal lines orphaned in 1100/2000/equity offsets. Also `CompanyAccount`/`ServiceItem` are imported but not deleted (fine, config).
  - (Info) The admin endpoint wipes everything with no `confirm` flag server-side; the only safeguard is the browser confirm/typed-name prompt in the admin page. Protected by `_check_admin` secret only.
- Journal integrity report of 2026-09-28 (separate task): PASS on a tiny local dev DB; note it flags schema drift (7 missing `invoices` columns in that SQLite file) — confirm production Postgres migrated.

## 6. IFRS compliance (AFS)
- Framework: IFRS for SMEs (`financial_statements.py` `meta.basis`); file unchanged.
- Web check this run: IFRS 18 remains effective for annual periods beginning on/after 1 Jan 2027; IFRS for SMEs 3rd edition effective 1 Jan 2027 (SAICA, IFRS Foundation, PKF/Nexia/Forvis Mazars pages). No change since the previous audit. The transition plan (`ifrs_smes_3rd_edition_transition_plan.md`) stands.
- **5b deferred tax:** already implemented — `_deferred_tax_balance()` `financial_statements.py:131`; opening/closing `:266-267`; Note 9 `"deferred_tax"` `:606`; `FixedAsset.wear_and_tear_rate` `database.py:543`; migration inside list literal `database.py:1507`. No edits made this run.
- Finance costs below EBIT / tax from profit_before_tax: unchanged.

## 7. Tax updates (company + payroll)
- Tax year: 2026/2027 (1 Mar 2026 – 28 Feb 2027). `TAX_YEARS["2026/2027"]` `payroll.py:132`; provisional `"2027/2028"` `:152`. `UIF_RATE=0.01` `:189`, `SDL_RATE=0.01` `:190`, `CORP_TAX_RATE=0.27` `:3151`, `VAT_RATE=0.15` at `:2032, 2426, 3507`.
- Web search (SARS tax rates / Budget 2026 pages, Xero, KPMG, Werksmans): no new rate, bracket, rebate or VAT changes found. Rates unchanged; no edits made.
- Sources: [SARS Tax Rates](https://www.sars.gov.za/tax-rates/), [SARS Budget 2026 FAQ](https://www.sars.gov.za/about/sars-tax-and-customs-system/budget/budget-2026-frequently-asked-questions/), [SARS Companies/SBC rates](https://www.sars.gov.za/tax-rates/income-tax/companies-trusts-and-small-business-corporations-sbc/), [Werksmans Budget 2026 overview](https://werksmans.com/budget-speech-2026-2027-tax-overview/), [SAICA – new era for financial reporting](https://www.saica.org.za/news/a-new-era-for-financial-reporting/), [IFRS for SMEs](https://www.ifrs.org/issued-standards/ifrs-for-smes/).

## 8. Action items
1. **Medium — `zuzan-backend/zuzan.db` is tracked in git and pushed to origin** (`.gitignore:221` ignores `*.db` but the file was added earlier; commit `2b40163` grew it 294 KB → 770 KB). It may contain real client/trial data. Run `git rm --cached zuzan-backend/zuzan.db`, consider purging history if it holds real data, and add `zuzan.db.bak-*` to `.gitignore`. Untracked `zuzan.db.bak-20260928-184955` is also present.
2. **Low —** extend `_CATEGORY_JOURNAL_SOURCES` (or add a handling step) for `import` and credit-note journal sources so clear-data cannot orphan them; consider a server-side `confirm` requirement on the admin clear-data endpoint.
3. **Low —** confirm the production Postgres has the 7 `invoices` columns flagged as missing in the local SQLite file.
4. **Low (carried) —** historical `Expense.category` postings pre-2026-09-18 under the old DEFAULT_COA routing remain misclassified (a reclass script `reclass_expenses_2026-09-28.py` now exists — confirm it was run against production).
5. **Low (carried) —** stray `.fuse_hidden*` files in `zuzan-backend/`; delete manually. New untracked `journal_check.py` — decide whether to commit.
6. **Info —** commit messages remain reused/inaccurate (9 recent commits share one message); `git index.lock` could not be unlinked from the audit shell (read-only for deletes) — harmless.

Standing reminders unchanged: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; run IFRS-for-SMEs 3rd-edition checklist early 2027; ConCourt VAT s7(4) judgment reserved (no ruling found); MIBCO Sector 5 Year 2 contributions TBC.

## 9. Fixes applied after this report (same day, at user request)
1. **zuzan.db untracked** — `git rm --cached zuzan-backend/zuzan.db` (staged, not yet committed/pushed); `.gitignore` now also ignores `zuzan.db.bak-*`, `*.db.bak*`, `.fuse_hidden*`. Stale zero-byte `.git/index.lock` removed. **Still needed from you:** run `commit_and_push.bat`; the DB stays in past git history/origin — if it held real client data, purge history (`git filter-repo --path zuzan-backend/zuzan.db --invert-paths` + force-push) and rotate any secrets it held. Not done automatically (rewrites shared history).
2. **Clear-data journal gaps** — `companies.py`: `credit_note` added to the `sales` sources; new `_journal_sources_for_categories()` also purges `source="import"` lines, but only when both `sales` and `expenses` are cleared (so clearing one category cannot wipe the other's imported balances). Both `/companies/clear-data` and the admin endpoint use it. `main.py`: admin clear-data now requires `confirm_company_name` matching the company name server-side; admin page sends it. Both files pass `py_compile`; not runtime-tested.
3. **Invoices schema drift** — verified `database.py:1606-1612` already carries `ALTER TABLE invoices ADD COLUMN IF NOT EXISTS …` for all 7 columns (Postgres path), so production is covered by code; the drift is confined to the local SQLite dev file.
4. **`.fuse_hidden*` files** — all deleted from `zuzan-backend/`.
5. **Commit hygiene** — `commit_and_push.bat` now takes the message as an argument (`commit_and_push.bat "msg"`), falling back to `chore: update [stamp]`; it also stages `journal_check.py`.
6. **Not fixable from here:** the expense reclass script (`reclass_expenses_2026-09-28.py`) — cannot confirm it was run against production Postgres; run it there deliberately. `zuzan.db.bak-20260928-184955` left on disk (now git-ignored) — delete when no longer needed.

---

# Follow-up run — 29 Sep 2026, 22:07 UTC (scheduled)
**Prior report:** the 19:06 run above (PASS). **Change detection:** HEAD is now `798be6a` (was `45a5aa8`). `git diff --stat 45a5aa8 HEAD` shows changes only in `auth.py` (+35), `billing.py` (+11), `companies.py`, `main.py`, `App_js_fixed.js`/`zuzan-app/src/App.js` (sidebar label), `.gitignore`, `commit_and_push.bat`, new `journal_check.py`, and `zuzan.db` removed from the index (item 1 of §9 done and committed). `payroll.py`, `financial_statements.py`, `journal.py`, `purchase_orders.py`, `database.py`, `csv_import.py`, `suppliers.py`, `customers.py` are unchanged, so Reports, Debtors, Creditors, cross-module journal coverage, IFRS and tax verdicts from the 19:06 run stand (anchors re-grepped: `deferred_tax` `financial_statements.py:606`, `TAX_YEARS["2026/2027"]` `payroll.py:132`, `CORP_TAX_RATE=0.27` `:3151`). Standards and SARS rates: no change since this morning's web check.

## New finding
**Medium — example-data seed/cleanup references a non-existent `Employee.notes` column.**
- `auth.py:238-243` builds `Employee(..., notes="[zuzan-example]")` and `billing.py:398` filters on `_Emp.notes`. `class Employee` (`database.py:181`) has no `notes` column (grep confirms; `Invoice.notes` does exist).
- Effect at signup: the `Employee(...)` constructor raises `TypeError`, which the `try/except` at `auth.py:~247` swallows (logs a warning). Result: **neither the example invoice nor the example employee is seeded** — the feature silently does nothing.
- Effect at activation (`billing.py:395-404`): `_Emp.notes` raises `AttributeError`; the `except` runs `db.rollback()`. The example-invoice delete on the line before is uncommitted at that point, so it is rolled back too. Harmless today only because nothing gets seeded — but if someone adds the column to fix the seed, verify the cleanup then works.
- Fix: add `notes = Column(Text)` to `Employee` plus an `ALTER TABLE employees ADD COLUMN IF NOT EXISTS notes TEXT` inside the `database.py` migrations list literal (Postgres path), or tag the example employee via `employee_number="EMP-EXAMPLE"` and filter on that instead. Not edited (audit is report-only outside §5b).
- Design note (Low): if seeding does start working, the example employee is `is_active=True` with gross R10,000 and would be picked up by payroll runs/EMP201 for trial accounts, and the example invoice is `draft` (correctly excluded from AR/revenue). Consider `is_active=False` or excluding `[zuzan-example]` records from payroll runs.

## Action items (changes vs 19:06 list)
1. **Medium (new)** — fix `Employee.notes` mismatch above.
2. Items 1–5 of §9 remain as previously reported (history purge decision for `zuzan.db` in origin; production run of `reclass_expenses_2026-09-28.py`; delete `zuzan.db.bak-20260928-184955`).
3. Standing reminders unchanged (2027/2028 TAX_YEARS after Budget Feb 2027; IFRS for SMEs 3rd edition / IFRS 18 from 1 Jan 2027; VAT s7(4) ConCourt ruling).

**Overall follow-up verdict: PASS with one new Medium.** No Critical/High findings.

## Fix applied (30 Sep 2026, at user request)
**Medium (`Employee.notes`) — fixed.** `database.py`: added `notes = Column(Text, nullable=True)` to `Employee`, and `"ALTER TABLE employees ADD COLUMN notes TEXT"` inside the migrations list literal (after the `hourly_rate` migration). All other fields used by the `auth.py` seed and `billing.py` cleanup (Invoice and Employee) were verified to exist; `database.py` passes `py_compile`. Not runtime-tested. The seed and cleanup code itself is unchanged. Still open (Low): the seeded example employee is `is_active=True` (R10,000 gross) so it would be included in trial accounts' payroll runs/EMP201 until activation removes it — consider `is_active=False` or excluding `[zuzan-example]` from payroll runs.
