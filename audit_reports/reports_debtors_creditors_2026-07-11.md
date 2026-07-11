# Reports / Debtors / Creditors Audit — 2026-07-11

Scope: `/reports/dashboard`, `/reports/management`, `/v1/summary`, Debtors (AR), Creditors (AP), cross-module journal coverage.
Files reviewed: payroll.py, main.py, journal.py, purchase_orders.py, companies.py, suppliers.py, customers.py, database.py, csv_import.py (new since last run), App_js_fixed.js.

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | **PASS** — all checklist items verified, no regressions |
| Debtors (AR) | **PASS with new findings** — view is correct; new CSV/xlsx import path bypasses journal postings |
| Creditors (AP) | **PASS** — no issues in the audited path |
| Cross-module | **FAIL (new)** — financial-statement imports (shipped 2026-07-10) break balance-sheet equity aggregation and Rule 6/7 reconciliation semantics |

The core reporting engine is unchanged and healthy. All new findings come from the **financial statement import feature** added to csv_import.py and App_js_fixed.js on 2026-07-10 (commits 0c4b1cc…81aff38), which posts journal entries and creates invoices/expenses outside the posting functions the reports reconcile against.

## 2. Reports

✓ No issues found in the checklist items:

- `total_revenue` sums only `InvoiceStatus.paid` invoices via `_to_zar()` (payroll.py:510–516). `_to_zar` (payroll.py:17–24) prefers `paid_amount_zar`, falls back to `amount × exchange_rate`, ZAR passthrough — correct.
- `total_outstanding` = sent + overdue via `_to_zar()` (payroll.py:518–522). Note: the enum has no separate "pending" status — `sent` **is** "pending" (database.py:38).
- Expenses excluded from revenue; ex-VAT in P&L (payroll.py:524–528).
- Payroll included from all payslips incl. terminated employees, with estimate fallback (payroll.py:552–562).
- PO COGS: received/partial/paid at delivered value `_po_delivered_net` (payroll.py:530–538); duplicate-expense heuristic guards double-counting (payroll.py:589–623). Receipts post the journal instead of an Expense record (purchase_orders.py:340–344) — no structural double-count.
- Management trend loop applies `_to_zar()` + bank-import income consistently (payroll.py:1358–1362).
- `/v1/summary` mirrors dashboard: `_to_zar`, `_po_delivered_net`, depreciation, payroll (main.py:264–309).

Design note (no action needed, but document it): dashboard/management revenue reads the Invoice table plus journal entries with source `"bank_import_income"` only (payroll.py:59–97). Revenue imported via the new P&L/GL/journal imports (source `"import"`) is treated as opening-balance history and will **not** appear in dashboard revenue — intentional non-double-counting, but users migrating from Xero may ask why.

## 3. Debtors

Core view: ✓ correct.

- Backend `/reports/debtors-aging` (payroll.py:1529–1589): filters `status IN (sent, overdue)` — paid and draft excluded; amounts via `_to_zar()` (1552); aged strictly from `due_date` with no-due-date invoices parked in `not_due` (1546–1559); buckets not_due / 0–30 / 31–60 / 61–90 / 90+.
- Frontend `Debtors` (App_js_fixed.js:4731–4854): renders backend data only, refreshes on `live.invoices`, correct bucket totals and grand total.

New findings (import path, shipped 2026-07-10):

- **[H1] Imported invoices post no journal entries.** `import_invoices` (csv_import.py:390–460) inserts Invoice rows directly — no `post_invoice_raised`/`post_invoice_paid` — and the import UI never triggers `/journal/backfill` (App_js_fixed.js:10547–10565; backfill is only a manual button on the Journal tab, 3396). After a migration import, the Debtors book and dashboard show the invoices but AR control 1100 has nothing: Rule 6 fails, balance-sheet trade receivables understate, and revenue accounts miss the paid history until the user happens to click "Re-run backfill". Same gap for `import_expenses` (csv_import.py:466–516). Fix: call the backfill automatically after invoice/expense imports (it is idempotent and covers both — journal.py:688–729), or post entries per-row.
- **[M3] Hard-coded `exchange_rate = 1.0`** (csv_import.py:442) and `paid_amount_zar = total` (447). An imported USD invoice is valued 1:1 in every report `_to_zar` touches. Either capture a rate/`amount_zar` column or reject non-ZAR rows with a clear message.

## 4. Creditors

✓ No issues found.

- Backend `/reports/creditors-aging` (payroll.py:1592–1764): pulls received/partial POs (fully paid excluded, 1608–1611) plus unpaid on-credit expenses (1700–1704); per-PO amounts from actual journal AP credits with `total_amount` fallback (1616–1633, 1680); aged from `received_date + supplier payment_terms` (1652–1654); expenses aged at +30 days by design.
- Supplier bank details decrypted via `decrypt_field` before display (payroll.py:1668–1670; suppliers.py:48–50). Encryption at rest on create/update confirmed (suppliers.py:68, 78).
- `pay_po` clears the true journal AP balance, not `total_amount` (purchase_orders.py:424–450); single-commit-after-journal pattern in receive/pay verified intact (audit fixes 2026-07-09 unchanged).
- Frontend `Creditors` (App_js_fixed.js:4857–5009): backend-driven, client-side bucket filter, refreshes on PO/expense changes.

## 5. Cross-module

Journal event coverage — all wired, unchanged since last run:

| Event | Posting fn | Called from |
|---|---|---|
| Invoice raised | journal.py:181 | companies.py:251, 367, 381, 455 |
| Invoice payment | journal.py:221 | companies.py:383, portal.py:205 |
| Expense (cash/credit) | journal.py:280 | companies.py:554, 644, 961 |
| Expense payment | journal.py:392 | companies.py:699 |
| PO receipt (incremental) | journal.py:421 | purchase_orders.py:355 |
| PO payment | journal.py:473 | purchase_orders.py:461 |
| Payroll run | journal.py:355 | payroll.py:407 |
| Bank-import income | journal.py:315 | companies.py:996 |

Invoice edit semantics (reverse+repost on amount change, payment reversal, draft transitions) verified intact (companies.py:340–394).

New gaps — all from the financial-statement imports:

- **[H2] Balance sheet cannot absorb statement imports.** `/reports/balance-sheet` aggregates assets/liabilities by *hard-coded account codes* (payroll.py:742–771) but equity as `bal("3000") + Σrevenue − Σexpenses` by *account type* (778–782). The imports offset to **3999 Opening Balance Equity** (csv_import.py:660–689) and **3998 Retained Earnings** (876–885) — neither is included in total equity, and imported asset/liability accounts with non-ZuZan codes (Xero code schemes) are invisible to the asset/liability sections. Consequences: any trial-balance or balance-sheet import unbalances Rule 1; a P&L import *overstates* equity by the imported net profit (the revenue credits are counted via the type query while the 3998 debit offset is ignored) with no matching asset. Fix: aggregate assets/liabilities/equity by `Account.type` (with the code-based lines kept as named sub-rows), or at minimum include all equity-type accounts in `total_equity`.
- **[M1] Rule 6/7 are not import-aware.** Imports can post directly to 1100/2000 (`_find_or_create_account` matches system accounts by code — csv_import.py:632–657). An imported opening debtors balance makes journal-1100 exceed the invoice-table total, so Rule 6 reports FAIL and advises "run /journal/backfill", which cannot repair it (payroll.py:938–958; same for Rule 7, 960–1018). Additionally that opening AR never appears in the Debtors book (invoice-table based). Fix: either exclude source `"import"` lines from Rules 6/7 and show them as a separate "opening balances" line, or reconcile against invoices + imported openings.
- **[M2] Unbalanced journal imports are accepted.** `_import_journal_rows` flags unbalanced reference groups but imports them anyway (csv_import.py:1000–1009), silently breaking the Rule 1 equation. Fix: reject unbalanced groups, or auto-offset to 3999 like the statement imports do.
- **[L2] Duplicate account creation.** `_find_or_create_account` falls back to `code = name[:20]` when no code exists (csv_import.py:649); repeated imports with name variants can spawn duplicate revenue/expense accounts, all of which feed retained income.
- **[L1] Carried over (2026-07-09):** per-PO AP-credit lookups (payroll.py:976–987, 1620–1633; purchase_orders.py:437–448) sum credits under source `"purchase_order"` only and ignore reversal debits. Still unreachable in practice.

## 6. Action items

1. **[High — H1]** Auto-run the journal backfill (or post per-row entries) after `/import/invoices` and `/import/expenses`, so migrated data reconciles without a hidden manual step (csv_import.py:390–516; App_js_fixed.js:10547).
2. **[High — H2]** Rework `/reports/balance-sheet` aggregation to include Opening Balance Equity (3999), imported Retained Earnings (3998), and non-standard-code asset/liability accounts — type-based totals with code-based sub-rows (payroll.py:742–783).
3. **[Medium — M1]** Make Rules 6/7 import-aware: exclude/segregate source `"import"` lines on 1100/2000 and correct the misleading backfill advice (payroll.py:938–1018).
4. **[Medium — M2]** Reject or auto-offset unbalanced journal groups in `_import_journal_rows` (csv_import.py:1000–1009).
5. **[Medium — M3]** Handle foreign currency in `import_invoices` — accept a rate/ZAR-amount column or reject non-ZAR rows instead of hard-coding `exchange_rate=1.0` (csv_import.py:442, 447).
6. **[Low — L1]** Make per-PO AP-credit lookups reversal-aware (carried over from 2026-07-09).
7. **[Low — L2]** Dedupe/normalise account matching in `_find_or_create_account` (csv_import.py:632–657).

## 8. Resolution log (2026-07-11, same day)

All new issues fixed on request:

- **H1 ✅** `csv_import.py`: new `_auto_backfill()` helper runs the idempotent `journal.backfill_company()` after `/import/invoices` and `/import/expenses` commit. A backfill failure never fails the import — it surfaces in `errors` with manual-backfill instructions. Response now includes a `journal_backfill` summary.
- **H2 ✅** `payroll.py /reports/balance-sheet`: added `other_assets` / `other_liabilities` aggregates (all asset/liability-type accounts outside the known code lists) and reworked equity to include **all** equity-type accounts — 3000 (retained income basis), 3999 Opening Balance Equity, 3998 imported Retained Earnings, and `other_equity` — each exposed as its own response key. Frontend (App_js_fixed.js + zuzan-app/src/App.js) shows the new rows conditionally, plus the previously hidden income-tax/prov-tax liability rows.
- **M1 ✅** `payroll.py` Rules 6/7: source-`"import"` lines on 1100/2000 are excluded from the control-account comparison (`ar_import_bal` / `ap_import_bal`) and reported in the detail text as imported opening balances that carry no invoice/PO-level detail.
- **M2 ✅** `csv_import.py _import_journal_rows`: lines are parsed and DR/CR-validated **before** the entry is created; unbalanced groups are rejected with a per-group error ("group NOT imported"), empty groups skipped.
- **M3 ✅** `csv_import.py /import/invoices`: new `exchange_rate` column aliases; ZAR rows forced to rate 1.0; non-ZAR rows without a positive rate are rejected with a clear error; `paid_amount_zar = total × rate`.
- **L2 ✅** `_find_or_create_account`: name matching is now case-insensitive and whitespace-trimmed.

Still open: **L1** (reversal-aware AP-credit lookups, carried over from 2026-07-09).

## 7. Changes since last run (2026-07-10)

Both Medium items from yesterday (provisional-tax delivered-value COGS; cash-basis expense payments in cash-flow) remain fixed. The only substantive change since then is the **financial statement import feature** (csv_import.py + Import UI in App_js_fixed.js, commits 0c4b1cc…81aff38): trial balance / balance sheet / P&L / general ledger / journals imports plus xlsx support. It introduces two High and three Medium findings above — none regress the previously audited report code, but the imports write journal data the Reports/Debtors/Creditors reconciliation layer was not designed to absorb. The Low reversal-awareness item remains open.
