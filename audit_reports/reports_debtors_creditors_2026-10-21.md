# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 21 October 2026 (scheduled run)
**Prior report:** 2026-10-20 (+ `medium_items_check_2026-10-20.md`)

**Change detection:** HEAD `9f2c425` (21 Oct 22:02, "feat: partial invoice payments"). Since the last report: new `InvoiceStatus.partial` (`database.py:42` + `ALTER TYPE` migration inside the list literal, `database.py:1662`); `companies.py:913-1080` (update_invoice partial logic, journal posts only the incremental payment); `App_js_fixed.js` (pay modal sends cumulative amount, "Partial" badge/Top-Up button); `payroll.py` easyfile IRP5 codes (+18/−4); `main.py` (+6, `repair_unposted_invoices` at startup); plus portal/billing/leave/budgets/recurring_invoices/csv_import edits. `py_compile` passes on payroll, main, companies, journal, financial_statements, database, purchase_orders, csv_import. Local `zuzan.db` unchanged since 28 Sep (no runtime data checked). No code edited by this run (5b already implemented).

## 1. Summary
| Section | Verdict |
|---|---|
| Reports | **FAIL** — new `partial` invoice status is not handled by any report/dashboard filter |
| Debtors (AR) | **FAIL** — partially-paid invoices vanish from `/reports/debtors-aging` |
| Creditors (AP) | PASS — reversal-awareness intact |
| Cross-module | **FAIL (reconciliation)** — Debtors Control (1100) carries the residual of partial invoices that the AR reports/AFS omit; import-awareness intact |
| IFRS (AFS) | PASS for standards; AFS trade receivables affected by the partial-status gap |
| Tax (SARS) | PASS — rates/tables current; prior High (IRP5 codes) now FIXED in `get_easyfile_export` (response-key labels still stale, Low) |

**Overall: FAIL — 1 new High (partial-invoice status unhandled in reports/AR/AFS), 1 new Medium (FX on partial payment of foreign invoices).**

## 2. Reports
- Unchanged and correct: revenue = paid invoices via `_to_zar` (`payroll.py:18, 2289, 2909`); outstanding = sent+overdue (`payroll.py:2297`); expenses excluded; PO cost via `_po_cost_net`/`_stock_pl_cost`; `/v1/summary` (`main.py:517-518`) uses `_to_zar`.
- **HIGH (new): `partial` status missing from every outstanding/receivable filter.** `Invoice.status.in_([sent, overdue])` is still used at `payroll.py:2297` (dashboard outstanding), `2682`, `2778` (Rule 6 recon), `3375`, `3622` (outstanding/overdue count), `3917` (debtors-aging); `main.py:518` (/v1/summary); `financial_statements.py:470` (trade receivables). Invoice-set filters incl. paid/written_off at `payroll.py:2350, 2704, 3065, 4210`, `financial_statements.py:505` also omit `partial`. Effect: once a customer part-pays, the invoice is not "paid" (not in revenue) and not "sent/overdue" (not outstanding) — it disappears from revenue, outstanding, VAT/IRP6 and AFS receivables, while the journal already holds Dr Bank / Cr 1100 for the part payment and the original Dr 1100 for the full invoice. Fix: add `InvoiceStatus.partial` to the outstanding filters and use balance = `total − paid_amount_zar` (ZAR) for those rows; decide revenue treatment (cash basis: recognise the received portion) and apply consistently.
- Carried Medium: revenue-trend loop filters raw `paid_date`/`expense_date` (`payroll.py:~2454`); NULL-dated legacy rows drop from trend but not period totals. Mitigated for new partial/paid rows (`companies.py:~989` defaults paid_date).
- Carried Low: `VAT_RATE = 0.15` redefined at `payroll.py:2663, 3057, 4177`, `companies.py`, `quotes.py`. Carried Medium: no regression tests for inventory-aware COGS.

## 3. Debtors
- **HIGH:** `debtors_aging` (`payroll.py:3917`) filters `sent`/`overdue` only → partial invoices are excluded entirely (customer owes the balance but it is not shown). Even once included, `amount` uses `_to_zar(inv)` (`payroll.py:18-24`), which for non-ZAR invoices returns `paid_amount_zar` when set — for a partial invoice that returns the amount *received*, not the outstanding balance. Needs an explicit outstanding-balance helper (`total×rate − paid_amount_zar`). The frontend `Debtors` view (`App_js_fixed.js:7806`) consumes this endpoint, so it inherits both problems.
- Aging from `due_date` ✓, no-due-date → not_due ✓, buckets current/31-60/61-90/90+ ✓, paid excluded ✓.
- Note: `partial` is never auto-transitioned to `overdue` (nor included in overdue marking), so partial invoices past due will not be flagged. Frontend `StatusBadge` handles "partial" ✓ (`App_js_fixed.js:403`); line 890/13886 dashboard fallbacks use `!== "paid"` (mock-only).

## 4. Creditors
✓ No issues found. `creditors_aging` (`payroll.py:3987-4057`): received/partial POs net `credit − debit` on 2000 with sources `purchase_order` + `purchase_order_reversal` (11 references across `payroll.py`, `purchase_orders.py`, `journal.py`, `financial_statements.py`); fully paid POs excluded; supplier bank name/account decrypted via `decrypt_field` (`payroll.py:4048-4049`).

## 5. Cross-module
- **MEDIUM (new): partial payment of a foreign-currency invoice mis-posts FX.** `companies.py:~1070` temporarily sets `paid_amount_zar = payment_delta` and calls `post_invoice_paid` (`journal.py:431-471`). For non-ZAR invoices `ar_carried` = full `total_amount × exchange_rate` while `zar_received` = the delta, so the entry credits 1100 for the whole invoice and books the difference as a bogus realised FX loss (5960). Fix: pass the delta and carry AR proportionally (`ar_carried = delta_in_invoice_ccy × rate`).
- **MEDIUM (new): backfill/repair ignore partials.** `journal.py:1192` (payment backfill) and `recurring_invoices.py:311-317` (`repair_unposted_invoices`, now run at startup `main.py:~108`) only consider `paid` — partial payments are never re-posted if their entry is missing, and the single `invoice_payment` source/id key may not support multiple payment entries per invoice (verify idempotency checks in backfill with >1 payment).
- Journal coverage (invoices, payments, expenses, PO receipts/payments, payroll): last integrity run 2026-10-19 = 0 gaps; not re-run (DB unchanged). Balance-sheet reconciliation (1100 vs invoices) will break for any partial invoice until the High above is fixed.
- Import-awareness ✓: `_auto_backfill` after invoice/expense imports (`csv_import.py:541, 623`); Rules 6/7 exclude `source="import"`; 3998/3999 included; unbalanced journal groups rejected; non-ZAR imports require rate. `csv_import.py:226` can still produce `overdue` but never `partial`.
- Carried Mediums: EMP201-submitted guard on `DELETE /payslips/{period}`; bank-import `db.rollback()` in loop (use SAVEPOINTs); `fix_credit_note_vat_account.py` untracked.

## 6. IFRS compliance (AFS)
- Framework: IFRS for SMEs (current edition). IFRS 18 and IFRS for SMEs 3rd edition remain effective for periods beginning on/after 1 Jan 2027 (early adoption permitted) — unchanged; `ifrs_smes_3rd_edition_transition_plan.md` stands. Sources: [Forvis Mazars SA](https://www.forvismazars.com/za/en/services/audit-assurance/financial-reporting/ifrs-for-smes-R-accounting-standard), [Accounting Academy](https://www.accountingacademy.co.za/news/read/updated-ifrs-for-smes-3rd-edition), [IFRS Foundation drop-in session](https://www.ifrs.org/content/dam/ifrs/events-and-conferences/2026/september/wss-conference/drop-in-session-ifrs-for-smes-accounting-standard.pdf). (Search returned titles only; no contradicting information.)
- **5b deferred tax:** verified present — `financial_statements.py:640` `"deferred_tax": deferred_tax_expense`; per-asset temporary difference × CIT rate; `wear_and_tear_rate` column exists. Not hard-coded 0.0; no edits made.
- Finance costs below EBIT; tax from profit_before_tax ✓. AFS trade receivables (`financial_statements.py:470`) omit `partial` invoices (see Reports High).
- Carried Medium: Income Tax Payable (estimate) must net provisional-tax payments once journalled.

## 7. Tax updates (company + payroll)
- Tax year at run date: **2026/2027** (1 Mar 2026 – 28 Feb 2027). `TAX_YEARS["2026/2027"]` (`payroll.py:158`) present with brackets 18% ≤ R245,100 … 45%, rebates R17,820 / R9,765 / R3,249, UIF ceiling R17,712; provisional `"2027/2028"` entry at `payroll.py:178` awaits Budget Feb 2027. UIF 1%+1%, SDL 1%, VAT 15%, CIT 27% — no announced changes found. Sources: [SARS Employer Guide 2027](https://www.sars.gov.za/guide-for-employers-in-respect-of-employees-tax-2027/), [Treasury Budget 2026 Tax Guide](https://www.treasury.gov.za/documents/national%20budget/2026/sars/Budget%202026%20Tax%20guide.pdf), [Accounter 2026/27 tables](https://accounter.co.za/news/sars-tax-tables-2026-2027), [Xero SARS tables](https://www.xero.com/za/guides/sars-tax-tables-2026/). (Search returned titles only; conclusion rests on prior source reads.)
- **Prior High — IRP5 codes: FIXED** (`payroll.py:2093-2098, 2170-2180`): employee pension 4001, provident 4003, employer 4472/4473 now written from actual contributions; 4005/7002 removed; 4141/4142/4102 correct. Remaining **Low:** response keys still mislabelled at `payroll.py:1889-1891, 1904-1906` (`code_4001_paye`, `code_4002_uif_employee`, `code_4005_pension`, `code_4003_uif_employer`, `code_4474_sdl`, `code_7002_pension_empr`) — cosmetic, but misleading; rename. Validate one EasyFile export against the SARS BRS before the 31 Oct 2026 EMP501 submission.
- No edits made to tax tables (report-only).

## 8. Action items
**Critical:** none.
**High**
1. Add `InvoiceStatus.partial` to all outstanding/receivable filters (`payroll.py:2297, 2682, 2778, 3375, 3622, 3917`; `main.py:518`; `financial_statements.py:470`) and the invoice-set filters (`payroll.py:2350, 2704, 3065, 4210`; `financial_statements.py:505`); use outstanding = total − paid for these rows; define revenue treatment for part payments. Add tests.
2. Fix `debtors_aging` amount for partial invoices (outstanding balance, in ZAR) and include in aging; make overdue marking cover `partial`.
**Medium**
3. Fix FX posting for partial payments on foreign-currency invoices (`companies.py:~1070`, `journal.py:431-471`).
4. Make payment backfill/repair partial-aware and idempotent for multiple payments per invoice (`journal.py:1192`, `recurring_invoices.py:311-317`).
5. Regression tests for inventory-aware COGS (`_po_cost_net` / `_stock_pl_cost`) and for the partial-payment flow.
6. EMP201-submitted guard on `DELETE /payslips/{period}` (needs submission flag).
7. Bank-import loop: SAVEPOINTs instead of whole-session `rollback()` (`companies.py:~2062-2221`).
8. Decide fate of `fix_credit_note_vat_account.py`; net AFS Income Tax Payable against future provisional-tax journals; COALESCE trend-loop dates.
9. Commit/review uncommitted `tests/`, `pytest.ini`, scripts; use descriptive commit messages (six near-identical auto-commit messages).
**Low**
10. Rename mislabelled IRP5 response keys (`payroll.py:1889-1906`); consolidate `VAT_RATE`; label VAT201 due-date rule; explicit `inventory_item_id` on PO lines; confirm NBCPSS bonus formula; purge `zuzan.db` from git history.

Standing reminders: replace provisional 2027/2028 `TAX_YEARS` after Budget Feb 2027; IFRS-for-SMEs 3rd ed./IFRS 18 checklist early 2027; EMP501 due 31 Oct 2026.
