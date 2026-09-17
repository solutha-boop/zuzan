# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 17 September 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-09-16 (FAIL — Critical Instance 4: NBCPSS provident/medical/uniform/union fields live in production but unposted, unbalancing every private-security payroll run by ~R550+/employee. Same-day addendum: Instance 4 fixed at user's explicit request. Instance 5 — garnishee orders/salary advances/once-off adjustments/expense claims — flagged as an uncommitted, not-yet-deployed fifth instance of the identical gap.)

**Change detection since last run:** `git log`/`git status -sb` show local `main` == `origin/main` at **`2cf5d30`** (16 Sep 22:47), eight commits ahead of the 09-16 baseline (`844d372`). Working tree is otherwise clean except two untracked items: `LAUNCH_READINESS_2026-07-14.md` (carried-over, see action item 6) and two new `.fuse_hidden*` files under `zuzan-backend/` (editor lock-file artifacts, not source — flagged as a new Low hygiene item).

`git diff --stat 844d372..2cf5d30` touches: `App_js_fixed.js`, `zuzan-app/src/App.js`, `commit_and_push.bat`, `patch_backend.py`, `zuzan-backend/{billing,companies,database,journal,main,payroll}.py`, plus the 09-16 audit report itself. **`financial_statements.py`, `purchase_orders.py`, `csv_import.py`, `customers.py`, `suppliers.py` are byte-identical to the 09-16 baseline** (confirmed via `git diff`, 0 lines) — Debtors/Creditors/IFRS logic re-verified unaffected without a full re-read. Within `payroll.py`, every changed hunk falls inside `calc_payroll()`, `calculate_all()`, `run_payroll()` or `_payslip_html()` — the `/reports/dashboard`, `/reports/management`, `/reports/debtors-aging` and `/reports/creditors-aging` endpoint bodies are untouched.

**Headline result: Instance 4 (09-16's Critical) is confirmed fixed and correct. Instance 5 — previously only a working-tree risk — has now been committed and pushed to production *without* the corresponding journal fix, and is today's new Critical finding.**

**Post-report addendum (same day, 17 September 2026):** Action item 1 (the live-in-production Critical below) was fixed the same day, outside this audit's normal report-only scope, at the user's explicit request. `journal.py`'s `post_payroll()` now posts `garnishee_total` to a new "Garnishee Orders Payable" liability (`2310`), `advance_deduction` + `once_off_deduction` to a new "Payroll Deductions Payable" liability (`2320`), `expense_claim` + `once_off_allowance_nontaxable` to a new "Employee Reimbursements & Allowances (Non-Taxable)" expense (`5180`), and folds `once_off_allowance_taxable` into the existing `gross_incl_ot` salary debit alongside `mibco_med_allow`/`uniform_allowance`. Verified by independently re-deriving the balance equation (in a standalone script, not by importing the edited module, since bash can serve stale reads of freshly edited `C:\Zuzan` files): a representative payslip with all six new fields plus the full 09-16 NBCPSS field set active simultaneously balances to a R0.00 residual, and all 64 on/off combinations of the six new fields individually and in combination balance to R0.00 as well. Action item 2 (process — automated balance test / pre-merge grep check) remains open; recommend implementing it before the next `Payslip`-column-adding feature ships.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary) | ✅ PASS |
| Debtors (AR) | ✅ PASS — unchanged, re-verified |
| Creditors (AP) | ✅ PASS — unchanged, re-verified |
| Cross-module consistency | ⚠️ **NEW CRITICAL FINDING — fixed same-day, see addendum above** — garnishee/advance/once-off/expense-claim payroll fields shipped to production without a journal posting, would have crashed any payroll run using them with an unbalanced-journal HTTP 500 |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) unchanged; no standards changes since 09-16 |
| Tax updates (SARS) | ✅ PASS — 2026/2027 tables current, no rate changes |

**Overall: FAIL on one Critical item at audit time; fixed same-day per the addendum above.** Yesterday's Critical (NBCPSS provident/medical/uniform/union) is confirmed fixed correctly. A second defect of the identical shape — previously reported as an uncommitted risk — had been committed to production without its journal fix; that fix has now been applied and numerically verified. Reports/Debtors/Creditors/IFRS/Tax all pass cleanly. Two prior Low process items (duplicated comment/dead-code accumulation) are resolved this run.

## 2. Reports

✓ No issues found. `payroll.py`'s dashboard/management/`v1/summary` code paths are untouched by this run's commits (confirmed via diff hunk locations — all payroll.py changes are confined to `calc_payroll()`/`calculate_all()`/`run_payroll()`/`_payslip_html()`).

- `total_revenue` (paid invoices via `_to_zar()`), `total_outstanding` (pending+overdue via `_to_zar()`), expense exclusion from revenue, PO-cost-once-via-`_po_delivered_net()`, and `/v1/summary`'s use of `_to_zar()` — all unchanged from the 09-16 baseline.
- New payslip fields (`garnishee_total`, `advance_deduction`, `expense_claim`, `once_off_deduction`, `once_off_allowance_taxable`, `once_off_allowance_nontaxable`) correctly flow into `total_cost` (`payroll.py:615-619`): `expense_claim` and `once_off_allowance_nontaxable` are added as pass-through employer costs; `once_off_allowance_taxable` is already inside `taxable_gross` (`:534`) which is the base of `total_cost`, so it isn't double-counted. `garnishee_total`/`advance_deduction`/`once_off_deduction` correctly do **not** appear in `total_cost` — they only redirect where net pay goes, they don't change what the employer spends.
- Because `Payslip.total_cost` (read directly by `payroll.py:1697,2806,3063`) is computed independently of `journal.py`, **the Reports dashboard payroll-cost figures remain accurate even though the journal itself is broken for these fields (§5)** — same "Reports layer is source-independent of the journal layer" pattern noted in the 09-14/09-15/09-16 reports.

## 3. Debtors

✓ No issues found. `/reports/debtors-aging` untouched since 09-10 (confirmed unchanged again this run): status filtered to `sent`/`overdue` only (paid excluded), aged from `due_date`, `_to_zar()`-converted, current/31_60/61_90/over_90/not_due buckets.

## 4. Creditors

✓ No issues found. `/reports/creditors-aging` untouched since 09-13 except the 09-15 MIBCO fix (already re-verified 09-16): `received`/`partial` POs only (fully paid excluded), reversal-aware net `credit − debit` over `purchase_order` + `purchase_order_reversal` sources, supplier bank details decrypted via `decrypt_field()` before display. `purchase_orders.py` byte-identical to baseline.

## 5. Cross-module consistency

**⚠️ Critical at audit time — fixed same-day, see post-report addendum above.** The identical defect shape fixed on 2026-07-15, 2026-09-14, 2026-09-15 and 2026-09-16 (a new `Payslip` field feeds `net_pay`/`taxable_gross` but is never posted to `journal.py`'s `post_payroll()`) had recurred a fifth time. Commit `2cf5d30` (pushed, `git status` shows 0 ahead/behind `origin/main`) committed the "payroll advances, garnishee orders, maternity leave, expense claims, once-off deductions/allowances" feature that the 09-16 report found only in the uncommitted working tree — **the 09-16 report's recommended pre-merge fix was not applied before merging.** This has now been fixed and numerically verified — see addendum.

**What shipped, and what's missing:**
- `calc_payroll()` (`payroll.py:445-451`) added six new parameters: `garnishee_total`, `advance_deduction`, `expense_claim`, `once_off_deduction`, `once_off_allowance_taxable`, `once_off_allowance_nontaxable` (plus `on_maternity_leave`, which is benign — see below).
- `taxable_gross` (`:534`) now includes `+ once_off_allowance_taxable`.
- `net_pay` (`:603-611`) now includes `− garnishee_total − advance_deduction − once_off_deduction + expense_claim + once_off_allowance_nontaxable`.
- `journal.py`'s `post_payroll()` (full function reviewed, `:412-610`) has **zero references** to `garnishee`, `advance_deduction`, `once_off`, or `expense_claim` anywhere in the file. Its `gross_incl_ot` debit line (`journal.py:519-521`) is unchanged from the 09-16 fix and does not include `once_off_allowance_taxable`; its bank credit line (`:558`) posts `payslip.net_pay` directly, which already has `garnishee_total`/`advance_deduction`/`once_off_deduction` subtracted and `expense_claim`/`once_off_allowance_nontaxable` added, with no offsetting debit/credit line for any of the six fields.
- **Net imbalance per payslip** = `(garnishee_total + advance_deduction + once_off_deduction) − (expense_claim + once_off_allowance_nontaxable + once_off_allowance_taxable)`, non-zero for any employee using any of these features. Example: an employee with a R500/month garnishee order and no other adjustments unbalances the entry by R500 (DR > CR), far above the 5-cent rounding-residue tolerance at `journal.py:602-607`. `_assert_balanced()` raises `ValueError`; `run_payroll()`'s try/except (`payroll.py:1004-1014`) rolls back the whole batch and returns HTTP 500.
- **Scope is broader than instances 1-4:** those were gated to specific industries (`is_security`, fuel-station MIBCO). These six fields are general-purpose — entered per-employee or per-run for **any** company — so this can break payroll for any ZuZan customer using garnishee orders, salary advances, once-off pay adjustments, or expense-claim reimbursement, not just NBCPSS/MIBCO customers.
- `on_maternity_leave` itself is **not** part of the bug: it zeroes `gross_monthly` upstream (`payroll.py:480-481`), so every dependent field naturally becomes zero and no journal line is needed.
- **Confirmed reachable / already shipped:** `database.py` adds the six `Payslip` columns (`:300-306`) plus a new `EmployeeGarnishee` table (`:227-236`), with `ALTER TABLE` migrations correctly placed inside the migrations list (`:1654-1670`, not dead code after the loop). `companies.py` adds `advance_monthly_deduction`/`on_maternity_leave` to `EmployeeCreate`/`EmployeeUpdate` and full garnishee CRUD (`/employees/{id}/garnishees`, `:1295-1481+`) — all correctly wired end-to-end at the model/API layer, so the feature is fully usable today and will crash payroll the first time any of these fields is non-zero.
- **Fix applied same-day (outside normal report-only scope, at user's explicit request):**
  1. Added "Garnishee Orders Payable" (`2310`, liability) — credited for `garnishee_total`, split into its own account (money owed to a court/third-party creditor, not the company).
  2. Added "Payroll Deductions Payable" (`2320`, liability) — credited for `advance_deduction + once_off_deduction` (recoveries with no tracked offsetting asset/expense elsewhere in the system, since ZuZan does not record advance disbursement as a separate ledger event).
  3. Added "Employee Reimbursements & Allowances (Non-Taxable)" (`5180`, expense) — debited for `expense_claim + once_off_allowance_nontaxable`, per the existing code comment at `payroll.py:614` ("Expense claims and non-taxable allowances are a pass-through employer cost").
  4. Folded `once_off_allowance_taxable` into the `gross_incl_ot` debit line in `journal.py` (now `:558-561`) alongside `mibco_med_allow`/`uniform_allowance`, since it is already part of `taxable_gross` and needed a debit.
  5. All three new accounts added to `DEFAULT_ACCOUNTS` (`journal.py:60-68, 78-80`) so `init_accounts` upserts them for existing companies on their next payroll run.
  6. Verified via an independent standalone re-derivation of the balance equation (not by importing the edited module — bash can serve stale reads of freshly edited `C:\Zuzan` files): a representative payslip with all six new fields plus the full 09-16 NBCPSS field set simultaneously active balances to a R0.00 residual, and all 64 on/off combinations of the six fields (individually and in combination) also balance to R0.00.

Otherwise unchanged and re-verified:
- Journal coverage complete for all transaction *types* (invoice raised/paid/COGS, expense, expense paid, bank income, payroll, PO received/paid, stock adjustment, asset acquisition/depreciation/disposal) — the gap is scoped to specific *payslip fields* within `post_payroll()`, as above.
- Import-awareness (2026-07-11 fixes) intact: `csv_import.py` unchanged, non-ZAR invoice imports still require an exchange rate; Rule 6/7 `source == "import"` exclusions and 3998/3999 imported-equity offset logic unchanged (`payroll.py`'s `balance_sheet()`, untouched by this run).
- Mass payslip ZIP download (new this run) is a read-only export feature — no journal/AR/AP/Reports touchpoints, confirmed out of scope.
- Clocking system (`clocking.py`) unchanged, still out of scope, no journal touchpoints.

**Process items resolved this run (carried over from 09-14/09-15/09-16, now fixed):**
- `main.py`'s disabled `_SubscriptionGateMiddleware` line: the duplicated comment fragment that had been growing across multiple runs is now a single clean comment (`git diff` confirms one `# disabled — re-enable when PayFast live` remains, the ~12 accumulated duplicates were removed).
- `billing.py`'s `adhoc_charge()`: 11 of the 12 duplicate `resp = None` lines were removed this run, leaving the single correct line. Both items can be closed off the standing action list.

**New Low item this run:** two untracked `.fuse_hidden0000000c0000000{1,2}` files appeared under `zuzan-backend/` — these are Linux FUSE editor lock/temp artifacts, not source changes, but indicate a file was open for edit through a network/cloud-synced filesystem mount during this run's commit activity. No content risk, but recommend adding `.fuse_hidden*` to `.gitignore` and cleaning up stray files to avoid accidental commits.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (unchanged). `financial_statements.py` byte-identical to the 09-16 baseline — no code changes to re-verify.

**Standards status (fresh web search this run, 17 September 2026):** no change since 09-16.
- IFRS 18 *Presentation and Disclosure in Financial Statements* — still effective for annual periods beginning on/after 1 January 2027, early application permitted; both IFRS 18 and IFRS for SMEs 3rd edition share the 2027 effective date and both require retrospective application per this run's search. Not yet applicable to IFRS-for-SMEs preparers.
- IFRS for SMEs third edition — still effective 1 January 2027 (issued 27 February 2025). No change.

**Section 5b — deferred tax:** already implemented; re-verified at the code level this run (file untouched, anchors unmoved from 09-16):
- `_deferred_tax_balance()` (`financial_statements.py:131`) present and unchanged; confirmed no hard-coded `"deferred_tax": 0.0` anywhere in the file.
- Per-asset tax base from `wear_and_tear_rate` (SARS IN47 category mapping, `:87-110`), opening/closing balances drive `deferred_tax_expense` (`:266-268`), `total_tax` = current + deferred, Note 9 fields populated, balance-sheet closing balance with matching retained-earnings adjustment — unchanged, file untouched.

Finance costs (2026-07-13 fix): interest lines presented below EBIT; tax/net-profit derive from `profit_before_tax`, not EBIT — unchanged, file untouched.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date. `TAX_YEARS`, brackets, rebates, UIF ceiling, MTC, S11F cap, VAT rate, CIT rate are all untouched by this run's commits (confirmed via diff hunk locations — only `calc_payroll()`'s new-field plumbing and `run_payroll()`/`_payslip_html()` were touched, none of which overlap the tax-table constants).

- **PAYE brackets, rebates, UIF ceiling, MTC, S11F cap:** all unchanged since the 09-16 fresh verification (primary rebate R17,820, secondary R9,765, tertiary R3,249, UIF ceiling R17,712/month, MTC R376/R254, S11F cap R430,000). UIF 1%/1%, SDL 1% unchanged.
- **CIT** remains flat 27% — no change for 2026/2027.
- **VAT** standard rate unchanged at 15%. Fresh search this run confirms the Constitutional Court **still has judgment reserved** on Section 7(4) of the VAT Act (heard 27 August 2026, SARS/Treasury asking the court to overturn the Western Cape High Court's finding that the section is unconstitutional; the High Court's order of invalidity, if confirmed, is in any case suspended for 24 months to give Parliament time to legislate). No rate change, no ruling yet, no code impact — continue monitoring.
- **2026 Draft TLAB/TALAB:** public comment period closed 28 August 2026 (unchanged status from "monitor" in prior reports); Treasury/SARS are now reviewing submissions before finalising and introducing the bills in Parliament — no rates in the current `TAX_YEARS["2026/2027"]` table are affected by anything in the draft bills reviewed this run (proposals concern inter-spousal donations tax residency and living-annuity de minimis aggregation, neither of which the payroll/company tax code implements or needs to).
- No edits made to tax tables (report-only; §5b was verification-only this run, already implemented).

**Sources consulted:** [VAT Act section declared invalid — The Citizen](https://www.citizen.co.za/news/south-africa/courts/vat-act-section-declared-invalid-unconstitutional/) · [Sars and Treasury ask top court to overturn ruling on minister's VAT powers — Business Day](https://www.businessday.co.za/news/2026-08-28-sars-and-treasury-ask-top-court-to-overturn-ruling-on-ministers-vat-powers/) · [How the VAT ruling empowers Parliament and protects taxpayers — Business Report](https://businessreport.co.za/personal-finance/financial-planning/2026-03-11-how-the-vat-ruling-empowers-parliament-and-protects-taxpayers/) · [List of judgments of the Constitutional Court of South Africa delivered in 2026 — Wikipedia](https://en.wikipedia.org/wiki/List_of_judgments_of_the_Constitutional_Court_of_South_Africa_delivered_in_2026) · [IFRS - IASB issues a major update to the IFRS for SMEs Accounting Standard](https://www.ifrs.org/news-and-events/news/2025/02/iasb-issues-major-update-smes-accounting-standard/) · [Third edition of the IFRS for SMEs Accounting Standard — ACCA](https://www.accaglobal.com/learning-and-events/corporate-reporting/third-edition-ifrs-for-smes.html) · [IFRS 18 and the Updated IFRS for SMEs Standard — Grant Thornton](https://www.grantthornton-bq.com/publications/bonaire/ifrs-update/) · [National Treasury Publishes 2026 Draft Tax Bills for Public Comment — Tax Consulting SA](https://www.taxconsulting.co.za/national-treasury-publishes-2026-draft-tax-bills-for-public-comment/) · [2026 Draft Tax Bills have been published for comment — GoLegal](https://www.golegal.co.za/2026-draft-tax-bills/)

## 8. Action items

1. ~~**Critical (live in production, cross-module journal integrity)**~~ — **FIXED same-day, see post-report addendum.** `journal.py`'s `post_payroll()` now posts balanced DR/CR lines for `garnishee_total`, `advance_deduction`, `once_off_deduction`, `expense_claim` + `once_off_allowance_nontaxable`, and `once_off_allowance_taxable`. Fix committed to the working tree this session and numerically verified (not yet committed/pushed to git by this audit — recommend the user commit and deploy `journal.py` promptly, since the underlying feature is already live and unprotected until this fix ships).
2. **High (process, still open):** the standing recommendation — repeated in the 09-14, 09-15, 09-16 and now 09-17 reports — to add an automated test running `calc_payroll()` + `post_payroll()` with every optional field populated and asserting balance (or a pre-merge grep of new `Payslip` columns against `post_payroll()`'s field references) has still not been implemented. Five live/shipped occurrences of the identical bug shape in nine weeks is a strong signal that manual review alone is not sufficient — this remains the highest-priority process item.
3. **Low (repo hygiene, new this run):** two `.fuse_hidden*` temp files were committed as untracked artifacts under `zuzan-backend/`. Recommend adding `.fuse_hidden*` to `.gitignore` and removing the stray files.
4. **Low (data freshness, carried over):** `MIBCO_SECTOR5_SCHEME_EMPLOYEE = 174.00` remains commented as "Year 1 confirmed; Year 2 TBC → using Year 1" even though the code has rolled into Year 2 (Sep 2026–Aug 2027). Not independently verifiable via this run's searches — flag for confirmation against the MIBCO Sector 5 agreement text when available.
5. **Low (repo clutter, carried over):** `LAUNCH_READINESS_2026-07-14.md` remains untracked in the project root — recommend committing or removing it.
6. **Medium (carried over):** the 13-week forecast still does not model provisional tax (IRP6) payments as a distinct weekly outflow.
7. **Low (carried over):** recommend a quick functional test adding a custom `/coa` account and posting an expense against it to confirm end-to-end routing via `expense_account()`.

**Closed this run (previously tracked, now resolved):**
- `main.py`'s duplicated `_SubscriptionGateMiddleware` comment fragment — cleaned up to a single line.
- `billing.py`'s duplicate `resp = None` lines — 11 of 12 removed, the one remaining line is correct/expected.

**Note on commit state:** the `journal.py` fix described in the addendum was made directly to the file at `C:\Zuzan\zuzan-backend\journal.py` during this session but has **not** been committed or pushed by this audit (audit sessions do not perform git operations). The user should review, commit and deploy it before the next payroll run that uses garnishee orders, salary advances, once-off adjustments or expense claims, since the underlying feature (commit `2cf5d30`) is already live without it.

**Standing reminders (not defects, carried from prior reports):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry after Budget Feb 2027 and restart the backend;
(b) early-2027 runs should execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`);
(c) the AFS PayFast payment/ad-hoc tokenization feature and `/reports/ai-insights` remain outside this audit's scope;
(d) NBCPSS/MIBCO payroll calculation detail (minimum wage checks, allowance rates, area/role rate tables) remains outside this checklist's explicit scope except where it produces an in-scope journal-integrity failure;
(e) the imported-equity-offset (3998/3999) exclusion logic lives in `payroll.py`'s `balance_sheet()`, not `financial_statements.py`;
(f) next run should keep checking for the outcome of Treasury/SARS's review of the 2026 draft TLAB/TALAB submissions and its introduction in Parliament;
(g) `parent_company_id`/`user_type`, bookkeeper-onboarding, consolidated-billing, accountant-fee-structure, and accountant-practice-dashboard/`billing_exempt` features remain outside Reports/Debtors/Creditors/AFS/tax scope, awareness only;
(h) provisional tax remains the only known 13-week-forecast gap (tracked via action item 6);
(i) compulsory VAT-registration turnover threshold is R2,300,000 (voluntary R120,000), effective 1 April 2026 — not gated anywhere in-scope, awareness only;
(j) the persistent Chart of Accounts feature (`/coa` router) is additive and outside the original checklist's endpoint list — tracked via action item 7;
(k) the invoice header-image upload, custom HTML invoice template, and service-item catalogue remain additive presentation/picklist features outside the original checklist's endpoint list;
(l) the IASB's SME consolidation-exception Exposure Draft comment period closed 9 September 2026 — no final amendment published yet; check next run for a post-close update;
(m) the Constitutional Court has reserved judgment (heard 27 August 2026) on Section 7(4) of the VAT Act; SARS/Treasury are asking it to overturn the High Court finding. No rate change and no ruling yet; monitor;
(n) the `/integrations/invoice` (SMT) endpoint remains formally in-scope going forward — spot-check with a real create + re-post cycle once real SMT traffic exists;
(o) `POST /accountant/sync-customers` remains tracked given its proximity to Debtors scope;
(p) any future PR that adds a nullable column to the `Payslip` model should be checked against `journal.py`'s `post_payroll()` before merge — this is now the fifth live/shipped occurrence of the same "new payslip field not wired into the journal" bug shape (pension/medical 2026-07-15, NBCPSS annual_bonus/levies 2026-09-14, MIBCO fields 2026-09-15, NBCPSS provident/medical/uniform/union 2026-09-16, garnishee/advance/once-off/expense-claim 2026-09-16→live 2026-09-17→fixed same-day 2026-09-17) — process fix (an automated pre-merge balance test) is tracked via action item 2 and remains the priority to prevent a sixth occurrence;
(q) the employee time-clock system (`clock.html`, `clocking.py`) remains additive with no journal/AR/AP/Reports touchpoints, awareness only unless a future OT-import path from clocking data feeds payroll without validation;
(r) new this run: mass payslip ZIP download is a read-only export feature with no journal/AR/AP/Reports touchpoints — awareness only.
