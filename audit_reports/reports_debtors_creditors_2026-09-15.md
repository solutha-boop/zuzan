# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 15 September 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-09-14 (FAIL — one Critical: NBCPSS `annual_bonus` unbalanced the payroll journal. Per memory, this was fixed the same day, 2026-09-14, outside the audit's normal report-only scope, along with the related `bc_levy_employer`/`psira_levy_employer` ledger gap.)

**Change detection since last run:** `git log` shows the codebase moved from `674328f` (13 Sep 21:42, the 09-14 report's baseline) to **`544c3d6`** (14 Sep 21:29) — eleven new commits, all same-day. `git status -sb` shows the local tree is level with `origin/main` (no ahead/behind) — the "pending deploy" fixes flagged in prior working notes (Date import crash fix, NBCPSS grade-key fix, MIBCO Sector 5 feature) are **committed and pushed**. Untracked clutter remains: `LAUNCH_READINESS_2026-07-14.md` (carried over, Low) and two `.fuse_hidden*` mount artifacts in `zuzan-backend/` (not real files, ignore).

The eleven commits contain: (1) the 09-14 audit's Critical/Medium fixes (`annual_bonus` added to the journal debit; `bc_levy_employer`/`psira_levy_employer` now posted via new accounts 5140/2250/2260) — **verified in place and correct**; (2) a `Date` import fix in `database.py` (Render crash fix); (3) an NBCPSS OT-modal min-wage key fix (`emp.grade` → `emp.security_grade`); (4) payslip payment-date logic; and (5) a new feature, **MIBCO Sector 5 fuel-station payroll** (minimum hourly rates, medical insurance allowance, compulsory health scheme). Diff review of this last feature surfaced a **new Critical cross-module finding** (§5) — the exact same bug shape flagged and fixed for `annual_bonus` yesterday has reappeared for the two new MIBCO payslip fields, and was not caught before merge.

`financial_statements.py`, `purchase_orders.py`, `csv_import.py`, `customers.py`, `suppliers.py` are byte-identical to the 09-14 baseline (confirmed via `git diff`, 0 lines) — no re-verification needed beyond re-confirming Debtors/Creditors/IFRS logic is unaffected.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary / cash-flow-13week) | ✅ PASS |
| Debtors (AR) | ✅ PASS — unchanged, re-verified |
| Creditors (AP) | ✅ PASS — unchanged, re-verified |
| Cross-module consistency | ⚠️ **NEW CRITICAL FINDING** — MIBCO Sector 5 payroll runs will crash with an unbalanced-journal 500 error |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) unchanged; no standards changes since 09-14 |
| Tax updates (SARS) | ✅ PASS — 2026/2027 tables current, no rate changes |

**Overall: FAIL on one Critical item**, a recurrence of yesterday's exact defect pattern in a different feature. Reports/Debtors/Creditors/IFRS/Tax all pass cleanly; yesterday's Critical and Medium findings are both confirmed fixed.

## 2. Reports

✓ No issues found.

- `total_revenue` (paid invoices via `_to_zar()`, `payroll.py:1259`) and `_bank_import_income()` (`:1261`); `total_outstanding` (`:1267`) — unchanged from 09-14, re-verified byte-identical.
- Expenses excluded from revenue (`:1270-1273`); PO costs added once via `_po_delivered_net()` on delivered value only (`:1278-1283`); depreciation included (`:1286-1289`).
- Payroll costs: `total_payroll` sums `Payslip.total_cost` (`:1297-1307`). `total_cost` (`payroll.py:~617`) now also includes `mibco_scheme_employer` (new this run) alongside `bc_levy_emp`/`psira_levy`/`annual_bonus` — **Reports dashboard payroll-cost figures remain complete and correct for MIBCO fuel-station employees**, because this path reads the Payslip table directly and is unaffected by the journal gap in §5.
- `management_accounts()` mirrors the same pattern (`period_payslips_total` from `Payslip.total_cost`) — consistent.
- Management-accounts revenue trend loop and `/v1/summary` (`main.py`) apply `_to_zar()`/`_bank_import_income()` consistently — unchanged.
- `/reports/cash-flow-13week` unchanged at the code level.

## 3. Debtors

✓ No issues found. File unchanged since 09-10, re-verified:

- `/reports/debtors-aging` (`payroll.py:2716-2775`) queries only `sent`/`overdue` invoices (paid excluded); ages strictly from `due_date`; amounts `_to_zar()`-converted; buckets current/31_60/61_90/over_90.

## 4. Creditors

✓ No issues found. File unchanged since 09-13, re-verified:

- `/reports/creditors-aging` (`payroll.py:2778-2934`) pulls received/partial POs (fully paid excluded) plus unpaid on-credit expenses.
- Reversal-aware AP balance confirmed present and correct (net `credit − debit`, sources `purchase_order`/`purchase_order_reversal`) across `payroll.py`, `purchase_orders.py`, `journal.py`, `financial_statements.py` — files untouched since 09-13, unchanged.
- Supplier bank details decrypted via `decrypt_field()` before display.

## 5. Cross-module consistency

**⚠️ Critical — new this run.** MIBCO Sector 5 fuel-station payroll runs will fail with a hard 500 error and roll back, for the same reason yesterday's `annual_bonus` bug did.

- `payroll.py`'s new MIBCO fields (`calc_payroll`, lines ~483-491): `mibco_med_allow` (R19.62/week ≈ R85.02/month, taxable, paid **to** the employee) is added into `taxable_gross` (`payroll.py:503`: `taxable_gross = effective_gross + total_overtime + night_allow + special_allow + cleaning_allow + annual_bonus + mibco_med_allow`); `mibco_scheme_employee` (fixed R174/month, deducted **from** the employee, default-enrolled — `mibco_scheme_enrolled` defaults to `True` in both `companies.py`'s `EmployeeCreate` and `payroll.py`'s `run_payroll`/`calculate_all` via `bool(getattr(emp, "mibco_scheme_enrolled", True))`) is subtracted in `net_pay` (`payroll.py:~566`: `net_pay = taxable_gross − paye_after_mtc − uif_employee − pension_employee_monthly − medical_aid_employee − mibco_scheme_empe`).
- `journal.py`'s `post_payroll()` was fixed for `annual_bonus` and `bc_levy_employer`/`psira_levy_employer` this run (confirmed correct — see below) but has **zero references to `mibco`** anywhere (`grep -ci mibco zuzan-backend/journal.py` → 0). Its debit line `gross_incl_ot` (`journal.py:~450`) does not include `mibco_med_allow`, and there is no credit/payable line anywhere for `mibco_scheme_employee`.
- Net effect on any payslip where `is_fuel_station=True` (company industry = `fuel_station`, employee has `mibco_role` set) and `mibco_scheme_enrolled` is true (the default): `net_pay` moves by `+85.02 − 174.00 = −88.98` relative to what the journal's debit side reflects, since the debit (`gross_incl_ot`) never changes but the credit (`CR Bank = net_pay`) does. This produces a **DR/CR imbalance of R88.98 per affected payslip** — far above the 5-cent rounding-residue tolerance folded in at `journal.py:495-497` (`if 0 < abs(residue) <= 0.05`). `_assert_balanced()` (`journal.py:212-216`) raises `ValueError`, and `run_payroll`'s try/except (`payroll.py:890-900`) treats this as fatal: `db.rollback()` + HTTP 500, rolling back the **entire batch**, not just the fuel-station employee.
- **Confirmed reachable from the UI, not dead code:** `App_js_fixed.js` lets a company set `industry = "fuel_station"` and assign employees a `mibcoRole` (Forecourt Attendant / Cashier / Char) with `mibcoSchemeEnrolled` defaulted to `true` in the Add/Edit Employee forms (lines ~3159, ~4207-4234, ~4594-4606) — a company that turns on this industry and adds one qualifying employee will have its next payroll run fail for every employee in the batch.
- **Recommended fix (not applied — this section is report-only per the audit's authorized-edit scope, which covers only §5b):**
  1. In `journal.py:~450`, add `mibco_med_allow` to the `gross_incl_ot` debit (mirroring how `annual_bonus` was just added): `gross_incl_ot = round((payslip.gross_salary or 0) + overtime_total + annual_bonus + (getattr(payslip, "mibco_med_allow", 0) or 0), 2)`.
  2. Add a credit line for `mibco_scheme_employee` (and a debit for `mibco_scheme_employer`, which — like the pre-fix `bc_levy_employer`/`psira_levy_employer` — is currently computed and shown in Reports via `Payslip.total_cost` but never posted to the ledger at all) against new accounts, e.g. `5150` "MIBCO Health Scheme (Employer)" expense and `2270` "MIBCO Health Scheme Payable" liability, following the exact pattern used for `bc_levy_er`/`psira_levy_er` immediately above it in the same function.
  3. Given this is now the **fourth** occurrence of "new Payslip field feeds `taxable_gross`/`net_pay`/`total_cost` but is never wired into `post_payroll()`'s journal lines" (after pension/medical 2026-07-15, `annual_bonus`/NBCPSS levies 2026-09-14, and now MIBCO), recommend a standing rule: any PR adding a new `Payslip` column must grep `journal.py`'s `post_payroll()` for that field name before merge, or add an automated test that runs `calc_payroll()` + `post_payroll()` for a synthetic payslip with every optional field populated and asserts balance.

Otherwise unchanged and re-verified:
- Journal coverage complete: all `post_*` functions present (invoice raised/paid/COGS, expense, expense paid, bank income, payroll, PO received/paid, stock adjustment, asset acquisition/depreciation/disposal) — no gaps.
- Import-awareness (2026-07-11 fixes) intact: `csv_import.py` unchanged, still rejects non-ZAR invoice import rows lacking an explicit exchange rate.
- Rule 6/7 `source == "import"` exclusions and the 3998/3999 imported-equity offset logic unchanged (file untouched).

**Process observation (Low, new):** two of the eleven new commits contain apparent duplicate-application artifacts rather than clean diffs: `main.py`'s already-commented-out `# app.add_middleware(_SubscriptionGateMiddleware)` line has a very long run of duplicated `# disabled — re-enable when PayFast live` fragments appended again (functionally inert, since the line was commented out before and after, but growing unboundedly with each commit); and `billing.py`'s `adhoc_charge()` gained eight additional `resp = None` lines immediately before the pre-existing ones (dead code, harmless since `resp` is reassigned before use, but indicates something in the local edit/commit pipeline is re-appending prior patch content instead of replacing it — see commit history: three near-identical "NBCPSS modal" commits and three near-identical "Date import + MIBCO" commits were pushed within minutes of each other on 2026-09-14). Recommend a cleanup commit removing the duplicate lines, and checking why the pipeline is producing repeat commits with cumulative cruft.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (unchanged). `financial_statements.py` byte-identical to the 09-14 baseline — no code changes to re-verify.

**Standards status (fresh web search this run, 15 September 2026):**
- IFRS 18 *Presentation and Disclosure in Financial Statements* — still effective for annual periods beginning on/after 1 January 2027, early application permitted; not yet applicable to IFRS-for-SMEs preparers. No change.
- IFRS for SMEs third edition — still effective 1 January 2027. No change since 09-14.

**Section 5b — deferred tax:** already implemented; re-verified at the code level, anchors unmoved from 09-14 (file untouched):
- `_deferred_tax_balance()` (`financial_statements.py:131`) computes per-asset tax base from `wear_and_tear_rate` (SARS IN47 category mapping, `:87-110`).
- Opening/closing balances drive `deferred_tax_expense` (`:266-268`); `total_tax` = current + deferred (`:601`); Note 9 fields populated (`:606,609-610`); `deferred_tax_movement` disclosed (`:681`).
- Balance-sheet closing balance carries the matching retained-earnings adjustment so Assets = Equity + Liabilities holds — unchanged, file untouched.

Finance costs (2026-07-13 fix): interest lines presented below EBIT; tax/net-profit derive from `profit_before_tax`, not EBIT — unchanged, file untouched.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date. `payroll.py`'s `TAX_YEARS` dict, brackets, rebates, UIF ceiling untouched by this run's commits (only NBCPSS/MIBCO sections and payslip payment-date logic were touched) — re-confirmed unchanged.

- PAYE brackets, primary/secondary/tertiary rebates, UIF ceiling (R17,712/month), UIF 1%/1%, SDL 1% — all unchanged and previously verified against a fresh SARS search on 09-14; no rate-change announcements found in this run's searches.
- CIT remains flat 27% (`fixed_assets.SA_CIT_RATE`) — no change for 2026/2027.
- VAT standard rate unchanged at 15% across all hard-coded sites. The Constitutional Court case on Section 7(4) of the VAT Act **remains at "judgment reserved"** as at this run's date (heard 27 August 2026; fresh search on 15 September 2026 finds no ruling issued yet). No rate change; no code impact. Continue monitoring.
- The 2026 Draft Taxation Laws Amendment Bill and Draft Tax Administration Laws Amendment Bill (public comment closed 28 August 2026) contain no proposals affecting PAYE brackets/rebates, UIF, SDL, CIT, or VAT rates as currently coded — proposals relate to living-annuity de minimis limits, donations-tax spousal exemptions, and SEZ transfer pricing. Not yet introduced in Parliament as final legislation. No code impact.
- No edits made to tax tables (report-only per task rules; §5b was verification-only this run, as it was already implemented).

**Sources consulted:** [Big VAT changes on the cards for South Africa — BusinessTech](https://businesstech.co.za/news/government/872697/big-vat-changes-on-the-cards-for-south-africa/) · [VAT Act section declared invalid — The Citizen](https://www.citizen.co.za/news/south-africa/courts/vat-act-section-declared-invalid-unconstitutional/) · [Democratic Alliance v Minister of Finance: VAT Act Analysis — CMS](https://cms.law/en/zaf/legal-updates/no-more-value-added-tax-increases-by-decree) · [ConCourt reserves judgment on Finance Minister's power to change VAT rate — eNCA](https://www.enca.com/news-top-stories/concourt-reserves-judgment-finance-ministers-power-change-vat-rate) · [List of judgments of the Constitutional Court of South Africa delivered in 2026 — Wikipedia](https://en.wikipedia.org/wiki/List_of_judgments_of_the_Constitutional_Court_of_South_Africa_delivered_in_2026) · [Sars and Treasury ask top court to overturn ruling on minister's VAT powers — Business Day](https://www.businessday.co.za/news/2026-08-28-sars-and-treasury-ask-top-court-to-overturn-ruling-on-ministers-vat-powers/) · [DRAFT TAXATION LAWS AMENDMENT BILL 2026 — SARS](https://www.sars.gov.za/wp-content/uploads/Legal/Drafts/Legal-LPrep-Draft-2026-31-Draft-Taxation-Laws-Amendment-Bill-2026-30-July-2026.pdf) · [2026 Draft Tax Bills have been published for comment — GoLegal](https://www.golegal.co.za/2026-draft-tax-bills/) · [Big tax changes proposed: what the new draft bills mean for taxpayers — IOL](https://iol.co.za/business/2026-08-06-big-tax-changes-proposed-what-the-new-draft-bills-mean-for-taxpayers/) · [SARS announces 2026 filing season dates — SAnews](https://www.sanews.gov.za/south-africa/sars-announces-2026-filing-season-dates) · [Get ready for Filing Season 2026 — SARS](https://www.sars.gov.za/latest-news/get-ready-for-filing-season-2026/)

## 8. Action items

1. **Critical (new, cross-module journal integrity):** `journal.py`'s `post_payroll()` must include `payslip.mibco_med_allow` in the `gross_incl_ot` debit and post a balanced DR/CR pair for `mibco_scheme_employee`/`mibco_scheme_employer` (new liability/expense accounts, mirroring the `bc_levy_er`/`psira_levy_er` pattern immediately above it), or every payroll run for a `fuel_station`-industry company with at least one MIBCO-role employee will unbalance by ~R88.98/employee and roll back with HTTP 500 for the whole batch. Reachable today from the live UI (Add/Edit Employee → MIBCO Role selector, `App_js_fixed.js`).
2. **Low (process, new):** `main.py` and `billing.py` picked up duplicate-application artifacts (a runaway duplicated comment fragment; eight redundant `resp = None` lines) from what appears to be the deploy pipeline re-committing overlapping patches multiple times in quick succession on 2026-09-14. Harmless functionally but recommend a cleanup commit and a look at why near-identical commits are being pushed 2-3 times each.
3. **Low (data freshness, new, awareness only):** `MIBCO_SECTOR5_SCHEME_EMPLOYEE = 174.00` is commented as "Year 1 confirmed; Year 2 TBC → using Year 1" (`payroll.py`) even though the code has now rolled into Year 2 (Sep 2026–Aug 2027) per `_mibco_scheme_year()`. Not a SARS-rate item and not independently verifiable via this run's searches — flagging so the actual Year 2 Affinity Health employee contribution can be confirmed against the MIBCO Sector 5 agreement text when available.
4. **Low (repo clutter, carried over):** `LAUNCH_READINESS_2026-07-14.md` remains untracked in the project root — recommend committing or removing it.
5. **Medium (carried over):** the 13-week forecast still does not model provisional tax (IRP6) payments as a distinct weekly outflow.
6. **Low (carried over):** recommend a quick functional test adding a custom `/coa` account and posting an expense against it to confirm end-to-end routing via `expense_account()`.

**Standing reminders (not defects, carried from prior reports):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry after Budget Feb 2027 and restart the backend;
(b) early-2027 runs should execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`);
(c) the AFS PayFast payment/ad-hoc tokenization feature and `/reports/ai-insights` remain outside this audit's scope;
(d) NBCPSS/MIBCO payroll calculation detail (minimum wage checks, allowance rates, area/role rate tables) predates or sits alongside this audit's baseline and remains outside this checklist's explicit scope — except where, as in §5, it produces an in-scope journal-integrity failure;
(e) file-attribution note: the imported-equity-offset (3998/3999) exclusion logic lives in `payroll.py`'s `balance_sheet()`, not `financial_statements.py`;
(f) next run should keep checking for Treasury's review outcome or Parliamentary introduction of the 2026 draft TLAB/TALAB (comment period closed 28 Aug 2026, not yet introduced as final legislation);
(g) `parent_company_id`/`user_type`, bookkeeper-onboarding, consolidated-billing, accountant-fee-structure, and accountant-practice-dashboard/`billing_exempt` features remain outside Reports/Debtors/Creditors/AFS/tax scope, awareness only;
(h) provisional tax remains the only known 13-week-forecast gap (tracked via action item 5);
(i) compulsory VAT-registration turnover threshold is R2,300,000 (voluntary R120,000), effective 1 April 2026 — not gated anywhere in-scope, awareness only;
(j) the persistent Chart of Accounts feature (`/coa` router) is additive and outside the original checklist's endpoint list — tracked via action item 6;
(k) the invoice header-image upload, custom HTML invoice template, and service-item catalogue remain additive presentation/picklist features outside the original checklist's endpoint list;
(l) the IASB's SME consolidation-exception Exposure Draft comment period closed 9 September 2026 — no final amendment published yet; check next run for a post-close update;
(m) the Constitutional Court has reserved judgment (heard 27 August 2026) on Section 7(4) of the VAT Act. No rate change and no ruling yet; monitor;
(n) the `/integrations/invoice` (SMT) endpoint remains formally in-scope going forward — spot-check with a real create + re-post cycle once real SMT traffic exists;
(o) `POST /accountant/sync-customers` remains tracked given its proximity to Debtors scope;
(p) **new:** any future PR that adds a nullable column to the `Payslip` model should be checked against `journal.py`'s `post_payroll()` before merge — this is the fourth occurrence of the same "new payslip field not wired into the journal" bug shape (pension/medical 2026-07-15, NBCPSS annual_bonus/levies 2026-09-14, MIBCO fields 2026-09-15).
