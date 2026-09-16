# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 16 September 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-09-15 (FAIL — one Critical: MIBCO Sector 5 `mibco_med_allow`/`mibco_scheme_employee`/`mibco_scheme_employer` were computed on the payslip but never posted to the journal, unbalancing every fuel-station payroll run by ~R88.98/employee.)

**Post-report addendum (same day, 16 September 2026):** Action item 1 (the live-in-production Critical below) was fixed the same day, outside this audit's normal report-only scope, at the user's explicit request. `journal.py`'s `post_payroll()` now posts `nbcpss_provident_employee/employer`, `nbcpss_medical_employee/employer` and `union_subscription_ded` via three new accounts (`2280`/`2290`/`2300` liabilities, `5160`/`5170` expenses), and folds `uniform_allowance` into the existing salary debit line. Verified by re-deriving the balance equation numerically for a representative NBCPSS employee with all five fields active simultaneously (DR = CR = R7,609.45 in the test case). Action item 2 (the uncommitted once-off/garnishee/maternity gap) was **not** fixed — it remains open since it isn't yet deployed.

**Change detection since last run:** `git log` shows the codebase moved from `544c3d6` (14 Sep 21:29, the 09-15 report's baseline) to **`844d372`** (15 Sep 22:49) on `main`, with `git status -sb` showing local == `origin/main` (0 ahead/behind) — i.e. `844d372` is live. On top of that, the working tree (not yet committed) carries a further, uncommitted round of changes to `App_js_fixed.js`, `zuzan-app/src/App.js`, `companies.py`, `database.py` and `payroll.py`.

The eleven commits since the 09-15 baseline contain: (1) a new employee time-clock system (`clock.html`, `clocking.py`, `ClockEvent` table) — confirmed it posts nothing to the journal and has no AR/AP/Reports touchpoints, out of scope; (2) NBCPSS Area-3-only rate cleanup and OT-modal fixes; (3) **the 09-15 audit's MIBCO fix — confirmed correctly applied** (accounts 2270/5150 added, `post_payroll()` now posts `mibco_scheme_employer`/`mibco_scheme_employee`/`mibco_med_allow`); and (4) a brand-new feature, **NBCPSS prescribed provident fund (PSSPF 7.5%), prescribed medical aid (PSSSBC R197), uniform allowance (R150) and union subscription**, plus mass payslip ZIP download. Diff review of item (4) found **the exact same bug shape flagged and fixed three times previously (2026-07-15, 2026-09-14, 2026-09-15) has recurred a fourth time, and is now live in production** (§5) — and the *uncommitted* working-tree changes (general payroll adjustments: garnishee orders, salary advances, once-off allowances/deductions, maternity leave) add a **fifth, not-yet-shipped instance of the identical gap**.

`financial_statements.py`, `purchase_orders.py`, `csv_import.py`, `customers.py`, `suppliers.py` are byte-identical to the 09-15 baseline (confirmed via `git diff`, 0 lines) — Debtors/Creditors/IFRS logic re-verified unaffected without needing a full re-read.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ✅ PASS |
| Debtors (AR) | ✅ PASS — unchanged, re-verified |
| Creditors (AP) | ✅ PASS — unchanged, re-verified; 09-15 MIBCO fix confirmed correct |
| Cross-module consistency | ⚠️ **NEW CRITICAL FINDING** — every NBCPSS private-security payroll run will crash with an unbalanced-journal 500, and is already live in production |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) unchanged; no standards changes since 09-15 |
| Tax updates (SARS) | ✅ PASS — 2026/2027 tables current, no rate changes |

**Overall: FAIL on one Critical item** — the fourth recurrence of a defect pattern flagged in three prior reports, this time already deployed to production, plus a fifth (uncommitted) instance of the same gap in progress. Reports/Debtors/Creditors/IFRS/Tax all pass cleanly; yesterday's MIBCO Critical finding is confirmed fixed and correct.

## 2. Reports

✓ No issues found.

- `total_revenue` (paid invoices via `_to_zar()`, `payroll.py:1658`) plus `_bank_import_income()` (`:1660`); `total_outstanding` (`:1666`) — both `_to_zar()`-converted, unchanged logic.
- Expenses excluded from revenue; ex-VAT expense total (`:1668-1672`); PO costs added once via `_po_delivered_net()` on delivered value only (`:1674-1682`); depreciation included (`:1684-1688`).
- Payroll costs: `total_payroll` sums `Payslip.total_cost` across all payslips, including terminated employees (`:1696-1706`). `total_cost` (`payroll.py:615-619`) already includes `nbcpss_provident_employer`, `nbcpss_medical_employer` and `uniform_allowance` — **Reports dashboard payroll-cost figures remain complete and correct for these new fields**, because this path reads the `Payslip` table directly and is unaffected by the journal gap in §5 (the pattern is identical to the 09-14/09-15 findings: the Reports layer and the journal layer read the same source fields independently, so a journal-posting gap doesn't corrupt Reports, only the ledger).
- `management_accounts()` (`:2723` onward) mirrors the same `_to_zar()` pattern for `total_outstanding` (`:2832`) — consistent.
- `/v1/summary` (`main.py:462-496`) imports and uses `_to_zar()`/`_po_delivered_net()`/`_bank_import_income()` from `payroll.py` — unchanged, consistent.

## 3. Debtors

✓ No issues found. File unchanged since 09-10, re-verified this run:

- `/reports/debtors-aging` (`payroll.py:3114-3174`) queries only `sent`/`overdue` invoices (`InvoiceStatus.sent`, `InvoiceStatus.overdue` — paid excluded); ages strictly from `due_date` (invoices with no due date go to a separate `not_due` bucket rather than being misdated); amounts are `_to_zar()`-converted (`:3137`); buckets are current/31_60/61_90/over_90/not_due.

## 4. Creditors

✓ No issues found. File unchanged since 09-13 except the 09-15 MIBCO journal fix (which is Creditors-adjacent but doesn't touch this endpoint's code), re-verified this run:

- `/reports/creditors-aging` (`payroll.py:3177-3273+`) pulls `received`/`partial` POs (fully paid excluded, `:3193-3196`) plus unpaid on-credit expenses; ages from `received_date/order_date/created_at + supplier.payment_terms`.
- Reversal-aware AP balance confirmed present and correct: per-PO AP amount is net `credit − debit` over sources `purchase_order` **and** `purchase_order_reversal` (`payroll.py:3205-3221`) — matches the same pattern in `purchase_orders.py`'s `pay_po`, `journal.py`'s backfill (`:944-957`), and `financial_statements.py` (all untouched, unchanged since 07-13).
- Supplier bank details decrypted via `decrypt_field()` before display (`payroll.py:3256-3258`).

## 5. Cross-module consistency

**⚠️ Critical — new this run, and already deployed to production.** The exact defect shape fixed on 2026-07-15 (pension/medical), 2026-09-14 (NBCPSS annual bonus + BC/PSIRA levies) and 2026-09-15 (MIBCO medical allowance + health scheme) has recurred a fourth time, in code that is **already live** (`844d372`, pushed, `git status` shows 0 ahead/behind `origin/main`), plus a fifth, not-yet-committed instance in the working tree.

**Instance 4 (live in production) — NBCPSS provident fund, medical aid, uniform allowance, union subscription:**
- `payroll.py`'s `calc_payroll()` computes, unconditionally for every `is_security` employee (no toggle required): `nbcpss_prov_emp = gross_monthly × 7.5%` (`:507`), `nbcpss_med_emp = R197` fixed (`:510`), `uniform_allow = R150` fixed (`:513`), and `union_sub` (`:515`, employee-entered). These feed directly into `net_pay` (`:601-611`): `net_pay = taxable_gross − paye_after_mtc − uif_employee − pension_employee_monthly − medical_aid_employee − mibco_scheme_empe − nbcpss_prov_emp − nbcpss_med_emp − union_sub + uniform_allow − garnishee_total − advance_deduction − once_off_deduction + expense_claim + once_off_allowance_nontaxable`.
- `journal.py`'s `post_payroll()` has **zero references** to `nbcpss_provident`, `nbcpss_medical`, `uniform`, or `union` anywhere in the file (confirmed via full-file review). Its `gross_incl_ot` debit line (`journal.py:483-485`) is unchanged from the 09-15 fix and does not net any of these four items, and there is no credit/payable line for any of them (unlike the pension/medical-aid pattern at `journal.py:513-524`, which correctly nets employee+employer via accounts 2230/5120 and 2240/5130).
- **Net effect:** for any NBCPSS security employee, `net_pay` (the CR Bank line) moves by `−(nbcpss_prov_emp + nbcpss_med_emp) + uniform_allow − union_sub` relative to the DR side, which never changes. Example: a Grade-B security employee on R6,726/month gross has `nbcpss_prov_emp = R504.45`, `nbcpss_med_emp = R197`, `uniform_allow = R150` → imbalance of **R551.45**, far above the 5-cent rounding-residue tolerance at `journal.py:543-545`. `_assert_balanced()` (`:218-222`) raises `ValueError`; `run_payroll`'s try/except (`payroll.py:1004-1014`) treats this as fatal, rolls back the entire batch, and returns HTTP 500.
- **Because these three fields are unconditional for every `is_security` employee** (not gated behind an annual-bonus toggle or a specific allowance, unlike the 09-14/09-15 bugs), **every payroll run for every `private_security`-industry company will now fail in its entirety**, for every employee in the batch, not just NBCPSS-specific edge cases. This is a materially more severe regression than the three prior instances.
- **Confirmed reachable / already shipped:** `companies.py`'s `EmployeeCreate`/`EmployeeUpdate` (committed diff, `544c3d6`→`844d372`) added `union_subscription`; `database.py` added the `nbcpss_provident_employee/employer`, `nbcpss_medical_employee/employer`, `uniform_allowance`, `union_subscription_ded` Payslip columns with matching `ALTER TABLE` migrations inside the migrations list (correct placement). No feature flag gates this — any existing `private_security` company's next payroll run is affected today.
- **Recommended fix (not applied — report-only per this audit's authorized-edit scope, which covers only §5b):**
  1. Add `nbcpss_provident_employer` and `nbcpss_medical_employer` (employer costs) as new expense/liability account pairs, e.g. `5160` "NBCPSS Provident Fund (Employer)" / `2280` "NBCPSS Provident Fund Payable" and `5170` "NBCPSS Medical Aid (Employer)" / `2290` "NBCPSS Medical Aid Payable" (mirroring the `bc_levy_er`/`psira_levy_er` pattern at `journal.py:525-533`), each posting DR expense (employer portion only) / CR payable (employee + employer combined) — the employee portions (`nbcpss_prov_emp`, `nbcpss_med_emp`) reduce `net_pay` and must be credited to the same payable accounts.
  2. Add a CR payable line for `union_subscription_ded` (e.g. a new liability account "Union Dues Payable", since this is money owed to a third-party union, not the company) and net `uniform_allowance` into the `gross_incl_ot` debit the same way `mibco_med_allow` is handled today, since it's a taxable-adjacent addition to net pay (though non-taxable, it must still appear as a debit to balance the credit-side increase).
  3. Re-derive the balance equation to confirm zero residual after the fix, the same way the 09-14/09-15 fixes were verified.

**Instance 5 (uncommitted, working tree only) — general payroll adjustments:**
- The uncommitted diff to `payroll.py` adds `on_maternity_leave`, `garnishee_total`, `advance_deduction`, `expense_claim`, `once_off_deduction`, `once_off_allowance_taxable`, `once_off_allowance_nontaxable` as new parameters that flow into `taxable_gross` (`:534`, `once_off_allowance_taxable` only) and `net_pay`/`total_cost` (`:603-619`). `database.py`'s uncommitted diff adds the matching `Payslip` columns and a new `EmployeeGarnishee` table/relationship, and `companies.py`'s uncommitted diff adds garnishee CRUD endpoints (`/employees/{id}/garnishees`) and the `advance_monthly_deduction`/`on_maternity_leave` fields — all correctly wired at the model/API layer.
- `journal.py` has no references to any of these seven fields. If this code is committed and deployed as-is, it will reproduce the identical crash for **any** payroll run using a garnishee order, salary advance, once-off allowance/deduction, or maternity leave — regardless of industry (this path is not NBCPSS/MIBCO-gated, so it affects every company).
- **Recommended fix (not applied, same report-only scope):** before merging, add `garnishee_total`, `advance_deduction`, `once_off_deduction` as credit lines against a "Payroll Deductions Payable"-style suspense/liability account (or, for garnishees, a dedicated "Garnishee Orders Payable"), `expense_claim` + `once_off_allowance_nontaxable` as an employer-expense debit (they are pass-through employer costs per the `total_cost` formula, `payroll.py:615-619`, comment "Expense claims and non-taxable allowances are a pass-through employer cost"), and `once_off_allowance_taxable` folded into the `gross_incl_ot` debit alongside `mibco_med_allow`. `on_maternity_leave` itself needs no separate posting (it zeroes `gross_monthly` upstream, so all dependent fields naturally become zero) but should be included in any test fixture used to verify balance.
- **Standing recommendation (repeated from the 09-15 report, now proven prescient):** any PR that adds a new `Payslip` column feeding `taxable_gross`, `net_pay`, or `total_cost` should grep `journal.py`'s `post_payroll()` for that field name before merge, or run an automated test that calls `calc_payroll()` + `post_payroll()` with every optional field populated and asserts the entry balances. This is now the fourth live occurrence plus a fifth pending one — a manual-review-only process has demonstrably failed to catch this bug shape four times in nine weeks.

Otherwise unchanged and re-verified:
- Journal coverage complete: all `post_*` functions present (invoice raised/paid/COGS, expense, expense paid, bank income, payroll, PO received/paid, stock adjustment, asset acquisition/depreciation/disposal) — no gaps in coverage of transaction *types*, only in coverage of specific *payslip fields* within `post_payroll()` as detailed above.
- Import-awareness (2026-07-11 fixes) intact: `csv_import.py` unchanged, still rejects non-ZAR invoice import rows lacking an explicit exchange rate; Rule 6/7 `source == "import"` exclusions and the 3998/3999 imported-equity offset logic unchanged (file untouched, logic lives in `payroll.py`'s `balance_sheet()`).
- Clocking system (`clocking.py`, new this run) posts nothing to the journal and has no AR/AP/Reports touchpoints — confirmed out of scope, no cross-module risk.

**Process observation (Low, carried over, partially improved):** `main.py`'s disabled `# app.add_middleware(_SubscriptionGateMiddleware)` line grew a further duplicated comment fragment this run (shorter than the 09-14/09-15 growth, but still appending rather than replacing). `billing.py`'s `adhoc_charge()` had 4 of its 7 duplicate `resp = None` lines removed this run (3 remain) — improving but not resolving the underlying issue of the deploy pipeline re-appending prior patch content. Recommend a cleanup commit and continued monitoring of the commit/deploy pipeline.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (unchanged). `financial_statements.py` byte-identical to the 09-15 baseline — no code changes to re-verify.

**Standards status (fresh web search this run, 16 September 2026):**
- IFRS 18 *Presentation and Disclosure in Financial Statements* — still effective for annual periods beginning on/after 1 January 2027, early application permitted; not yet applicable to IFRS-for-SMEs preparers. No change.
- IFRS for SMEs third edition — still effective 1 January 2027 (issued 27 February 2025 by the IASB). No change since 09-15.

**Section 5b — deferred tax:** already implemented; re-verified at the code level this run, anchors unmoved from 09-15 (file untouched):
- `_deferred_tax_balance()` (`financial_statements.py:131`) computes per-asset tax base from `wear_and_tear_rate` (SARS IN47 category mapping, `:87-110` — explicit rate takes priority, falls back to accounting useful life so unmapped categories produce a zero temporary difference).
- Opening/closing balances drive `deferred_tax_expense` (`:266-268`); `total_tax` = current + deferred (`:601`); Note 9 fields `deferred_tax`, `deferred_tax_opening_balance`, `deferred_tax_closing_balance` populated (`:606, 609-610`); `deferred_tax_movement` disclosed on the balance sheet (`:681`).
- Balance-sheet closing balance carries the matching retained-earnings adjustment so Assets = Equity + Liabilities holds — unchanged, file untouched.

Finance costs (2026-07-13 fix): interest lines presented below EBIT; tax/net-profit derive from `profit_before_tax`, not EBIT — unchanged, file untouched.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date (16 September 2026 falls within it; `_current_tax_year()` at `payroll.py:170-183` derives this correctly). `TAX_YEARS`, brackets, rebates and UIF ceiling untouched by this run's commits (only NBCPSS provident/medical/uniform/union, clocking, and payslip-date logic were touched).

- **PAYE brackets, rebates, UIF ceiling** — fresh SARS-adjacent search this run confirms: primary rebate R17,820, secondary (65+) R9,765, tertiary (75+) R3,249, UIF ceiling R17,712/month, all matching `TAX_YEARS["2026/2027"]` (`payroll.py:132-146`) exactly. UIF 1%/1% (`:189`), SDL 1% (`:190`) unchanged and confirmed correct.
- **Medical Scheme Fees Tax Credit (s6A):** confirmed R376 (first two members) / R254 (each additional dependant) for 2026/2027 — matches `MTC_MAIN_FIRST`/`MTC_ADDITIONAL` (`payroll.py:201-202`) and `calc_medical_tax_credit()` logic exactly.
- **Section 11F retirement fund cap:** confirmed R430,000 (raised from R350,000 in Budget 2026) — matches `S11F_CAP` (`payroll.py:197`) exactly.
- **CIT** remains flat 27% (dashboard tax provision `payroll.py:1710`, `fixed_assets.SA_CIT_RATE` for deferred tax) — no change for 2026/2027, no code impact.
- **VAT** standard rate unchanged at 15% across all hard-coded sites. The Constitutional Court case on Section 7(4) of the VAT Act **remains at "judgment reserved"** as at this run's date (heard 27 August 2026; fresh search on 16 September 2026 finds no ruling issued yet — same status as 09-15). No rate change; no code impact. Continue monitoring.
- No edits made to tax tables (report-only per task rules; §5b was verification-only this run, as it was already implemented).

**Sources consulted:** [VAT Act section declared invalid — The Citizen](https://www.citizen.co.za/news/south-africa/courts/vat-act-section-declared-invalid-unconstitutional/) · [Big VAT changes on the cards for South Africa — BusinessTech](https://businesstech.co.za/news/government/872697/big-vat-changes-on-the-cards-for-south-africa/) · [List of judgments of the Constitutional Court of South Africa delivered in 2026 — Wikipedia](https://en.wikipedia.org/wiki/List_of_judgments_of_the_Constitutional_Court_of_South_Africa_delivered_in_2026) · [IFRS - IASB issues a major update to the IFRS for SMEs Accounting Standard](https://www.ifrs.org/news-and-events/news/2025/02/iasb-issues-major-update-smes-accounting-standard/) · [Third edition of the IFRS for SMEs Accounting Standard — ACCA](https://www.accaglobal.com/learning-and-events/corporate-reporting/third-edition-ifrs-for-smes.html) · [IFRS 18 and the Updated IFRS for SMEs Standard — Grant Thornton](https://www.grantthornton-bq.com/publications/bonaire/ifrs-update/) · [SARS Tax Tables 2026/2027 — Accounter](https://accounter.co.za/news/sars-tax-tables-2026-2027) · [PAYE Calculator South Africa 2026/2027 — Govchain](https://www.govchain.co.za/salary-tax-calculator) · [South Africa payroll in 2026: PAYE, UIF, SDL + COIDA guide — AnooreHR](https://anoorehr.com/blog/south-africa-payroll-guide-2026)

## 8. Action items

1. **Critical (live in production, cross-module journal integrity):** `journal.py`'s `post_payroll()` must be updated to post balanced DR/CR pairs for `nbcpss_provident_employee/employer`, `nbcpss_medical_employee/employer`, `uniform_allowance`, and `union_subscription_ded` (new liability/expense accounts, mirroring the `bc_levy_er`/`psira_levy_er` pattern at `journal.py:525-533`), or every payroll run for a `private_security`-industry company will unbalance and roll back with HTTP 500 for the whole batch — unconditionally, for every security employee, starting from commit `844d372` (pushed, live now). This is more severe than the three prior instances of this bug because it is not gated behind an optional toggle.
2. **Critical (pre-merge, not yet deployed):** before committing the working-tree changes for garnishee orders, salary advances, once-off allowances/deductions and maternity leave, wire `garnishee_total`, `advance_deduction`, `once_off_deduction`, `expense_claim`, `once_off_allowance_taxable`, `once_off_allowance_nontaxable` into `journal.py`'s `post_payroll()` following the same pattern — this is a fifth instance of the identical gap and is currently only prevented from reaching production by not yet being committed.
3. **High (process):** implement the standing recommendation from the last two reports — an automated test that runs `calc_payroll()` + `post_payroll()` for a synthetic payslip with every optional field populated and asserts balance, or a pre-merge grep check for new `Payslip` columns against `post_payroll()`'s field references. Four live occurrences plus a fifth pending one in nine weeks indicates manual review alone is not catching this bug shape.
4. **Low (process, carried over, partially improved):** `main.py` and `billing.py` continue to pick up duplicate-application artifacts from the deploy pipeline (a further duplicated comment fragment; 3 of 7 redundant `resp = None` lines still remain after this run's partial cleanup). Recommend a cleanup commit and a review of why the pipeline re-commits overlapping patches.
5. **Low (data freshness, carried over):** `MIBCO_SECTOR5_SCHEME_EMPLOYEE = 174.00` remains commented as "Year 1 confirmed; Year 2 TBC → using Year 1" even though the code has rolled into Year 2 (Sep 2026–Aug 2027) per `_mibco_scheme_year()`. Not independently verifiable via this run's searches — flag for confirmation against the MIBCO Sector 5 agreement text when available.
6. **Low (repo clutter, carried over):** `LAUNCH_READINESS_2026-07-14.md` remains untracked in the project root — recommend committing or removing it.
7. **Medium (carried over):** the 13-week forecast still does not model provisional tax (IRP6) payments as a distinct weekly outflow.
8. **Low (carried over):** recommend a quick functional test adding a custom `/coa` account and posting an expense against it to confirm end-to-end routing via `expense_account()`.

**Standing reminders (not defects, carried from prior reports):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry after Budget Feb 2027 and restart the backend;
(b) early-2027 runs should execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`);
(c) the AFS PayFast payment/ad-hoc tokenization feature and `/reports/ai-insights` remain outside this audit's scope;
(d) NBCPSS/MIBCO payroll calculation detail (minimum wage checks, allowance rates, area/role rate tables) predates or sits alongside this audit's baseline and remains outside this checklist's explicit scope — except where, as in §5, it produces an in-scope journal-integrity failure;
(e) file-attribution note: the imported-equity-offset (3998/3999) exclusion logic lives in `payroll.py`'s `balance_sheet()`, not `financial_statements.py`;
(f) next run should keep checking for Treasury's review outcome or Parliamentary introduction of the 2026 draft TLAB/TALAB;
(g) `parent_company_id`/`user_type`, bookkeeper-onboarding, consolidated-billing, accountant-fee-structure, and accountant-practice-dashboard/`billing_exempt` features remain outside Reports/Debtors/Creditors/AFS/tax scope, awareness only;
(h) provisional tax remains the only known 13-week-forecast gap (tracked via action item 7);
(i) compulsory VAT-registration turnover threshold is R2,300,000 (voluntary R120,000), effective 1 April 2026 — not gated anywhere in-scope, awareness only;
(j) the persistent Chart of Accounts feature (`/coa` router) is additive and outside the original checklist's endpoint list — tracked via action item 8;
(k) the invoice header-image upload, custom HTML invoice template, and service-item catalogue remain additive presentation/picklist features outside the original checklist's endpoint list;
(l) the IASB's SME consolidation-exception Exposure Draft comment period closed 9 September 2026 — no final amendment published yet; check next run for a post-close update;
(m) the Constitutional Court has reserved judgment (heard 27 August 2026) on Section 7(4) of the VAT Act. No rate change and no ruling yet; monitor;
(n) the `/integrations/invoice` (SMT) endpoint remains formally in-scope going forward — spot-check with a real create + re-post cycle once real SMT traffic exists;
(o) `POST /accountant/sync-customers` remains tracked given its proximity to Debtors scope;
(p) any future PR that adds a nullable column to the `Payslip` model should be checked against `journal.py`'s `post_payroll()` before merge — this is now the fourth live occurrence of the same "new payslip field not wired into the journal" bug shape (pension/medical 2026-07-15, NBCPSS annual_bonus/levies 2026-09-14, MIBCO fields 2026-09-15, NBCPSS provident/medical/uniform/union 2026-09-15→live 2026-09-16), plus a fifth pending in the working tree (general payroll adjustments) — tracked via action items 1-3;
(q) new this run: the employee time-clock system (`clock.html`, `clocking.py`, `ClockEvent`/kiosk-token additions to `Company`) is additive, has no journal/AR/AP/Reports touchpoints, and remains outside this checklist's scope — awareness only unless a future OT-import path from clocking data feeds payroll without validation.
