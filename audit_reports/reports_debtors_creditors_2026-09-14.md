# ZuZan Audit — Reports, Debtors & Creditors
**Date:** 14 September 2026
**Scope:** Reports endpoints, Debtors (AR), Creditors (AP), cross-module journal consistency, IFRS compliance (AFS), SARS tax rates
**Prior report:** 2026-09-13 (PASS; one High process item — three fixes verified but uncommitted — and several Medium/Low carried-over items).

**Change detection since last run:** `git log` shows the codebase moved from `e44fb1b` (10 Sep) to **`674328f`** (13 Sep 21:42) — eight new commits. `git status --short` shows a clean tree except one untracked file, `LAUNCH_READINESS_2026-07-14.md` (stray doc, Low/clutter — see Action Items).

The three fixes flagged as "uncommitted" in the 09-13 report (cash-flow-13week `creditor_payments`/`vat_payment`, `billing.py` duplicate-line cleanup, `App_js_fixed.js` linked-client badge) are now **committed** — 09-13's prior High process item is resolved.

The eight new commits are almost entirely a new feature: **NBCPSS private-security payroll enhancements** (BC levy R9.40→R7.00, PSIRA fee R5.00→R4.00 rate correction; area selector Urban/Rural; `normal_hours` for hourly employees paid less than the 208-hour month; `annual_bonus` — NBCPSS's 1-week-pay December bonus), plus an employee-import template and a DataImport tab auto-detect fix. Per prior reports' standing reminder (d), NBCPSS payroll calculation detail predates this audit's checklist scope — but this run's diff review surfaced a **new, in-scope journal-integrity defect** introduced by the `annual_bonus` feature (commit `674328f`), documented in §5 below, plus a related pre-existing completeness gap. `financial_statements.py`, `journal.py`, `purchase_orders.py`, `companies.py`, `csv_import.py`, `database.py` (aside from the two new nullable Payslip columns, migration correctly placed inside the list literal) are otherwise untouched and re-verified line-for-line against the 09-13 baseline.

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports (dashboard / management / v1 summary / cash-flow-13week) | ✅ PASS |
| Debtors (AR) | ✅ PASS — unchanged, re-verified |
| Creditors (AP) | ✅ PASS — unchanged, re-verified |
| Cross-module consistency | ⚠️ **NEW CRITICAL FINDING** — NBCPSS annual-bonus payroll runs will crash with an unbalanced-journal 500 error |
| IFRS compliance (AFS) | ✅ PASS — deferred tax (5b) unchanged; no standards changes since 09-13 |
| Tax updates (SARS) | ✅ PASS — 2026/2027 tables current, no rate changes |

**Overall: FAIL on one Critical item.** Everything in the original checklist's Reports/Debtors/Creditors/IFRS/Tax scope passes cleanly. The one new defect sits at the boundary of the explicitly out-of-scope NBCPSS feature and in-scope journal integrity — it is reported because it will hard-block a real payroll run (not because NBCPSS calculation correctness generally is now in scope).

## 2. Reports

✓ No issues found.

- `total_revenue` (paid invoices via `_to_zar()`, `payroll.py:1259`, plus `_bank_import_income()`, `:1261`) and `total_outstanding` (`:1267`) unchanged from 09-13.
- Expenses exclude revenue (`:1270-1273`); PO costs added once via `_po_delivered_net()` on delivered value only (`:1278-1283`); depreciation included (`:1286-1289`).
- Payroll costs: `total_payroll` sums `Payslip.total_cost` across **all** payslips, not just active employees (`:1297-1307`) — and `total_cost` itself (`payroll.py:499`) already includes `bc_levy_emp`, `psira_levy`, and (new this run) `annual_bonus`. **Reports/Dashboard payroll-cost figures are therefore complete and correct even for NBCPSS employees** — this uses the Payslip table directly, not the journal, so it is unaffected by the journal gap in §5 below.
- `management_accounts()` mirrors the same pattern (`period_payslips_total` from `Payslip.total_cost`, `:2406-2420`) — consistent.
- Management-accounts revenue trend loop (`:2450-2454`) and `/v1/summary` (`main.py:461,491`) apply `_to_zar()` and `_bank_import_income()` consistently — unchanged.
- `/reports/cash-flow-13week`: the 09-12/09-13 fix (real `creditor_payments` and `vat_payment` instead of hard-coded `0.0`) is now committed and unchanged at the code level — re-verified.

## 3. Debtors

✓ No issues found. Re-verified against current file (unchanged since 09-10):

- `/reports/debtors-aging` (`payroll.py:2716-2775`) queries only `sent`/`overdue` invoices (paid excluded); ages strictly from `due_date` with a `not_due` bucket for missing dates (no issue_date fallback); amounts are `_to_zar()`-converted; buckets are current/31_60/61_90/over_90.
- `_resolve_currency_and_rate()` (`integrations.py`) and the paid-invoice amount-edit block (`integrations.py`) are unchanged.

## 4. Creditors

✓ No issues found. Re-verified against current file (unchanged since 09-13):

- `/reports/creditors-aging` (`payroll.py:2778-2934`+) pulls received/partial POs (fully paid excluded by status filter) plus unpaid on-credit expenses, aged from `received_date + supplier.payment_terms` (POs) or `expense_date + 30` (expenses).
- Reversal-aware AP balance confirmed present and correct at `payroll.py:2809-2822` (creditors-aging), `payroll.py` cash-flow-13week's own lookup, `purchase_orders.py`, `journal.py`, `financial_statements.py` — all net `credit − debit` on account 2000 and include `source in ("purchase_order", "purchase_order_reversal")`.
- Supplier bank details decrypted via `decrypt_field()` before display (`payroll.py:2857-2859`).

## 5. Cross-module consistency

**⚠️ Critical — new this run.** NBCPSS annual-bonus payroll runs will fail with a hard 500 error and roll back.

- `payroll.py`'s `annual_bonus` field (added commit `674328f`, `run_payroll` computes `emp_bonus = round(emp.gross_salary * 12/52, 2)` at `payroll.py:709-710` when `include_annual_bonus=True` and the employee is NBCPSS security) is folded into `taxable_gross` (`payroll.py:428`), which drives `net_pay` (`payroll.py:496`: `net_pay = taxable_gross − paye_after_mtc − uif_employee − pension_employee_monthly − medical_aid_employee`). So the bonus (net of its own PAYE/UIF effect) flows into `net_pay`.
- `journal.py`'s `post_payroll()` (`journal.py:388-464`, unchanged by this run's commits) computes the debit side as `gross_incl_ot = payslip.gross_salary + overtime_amount + sunday_amount + ph_amount` (`journal.py:421-425`) — **this does not include `annual_bonus` at all**, while the credit side (`CR Bank`, `journal.py:442`) uses the full `net_pay`, which now embeds the bonus. The residue-fold safety net only absorbs drift ≤ 5 cents (`journal.py:459-460`); a bonus of even a few hundred rand triggers `_assert_balanced()` (`journal.py:208-209`) to raise `ValueError("Journal entry is unbalanced…")`.
- `run_payroll`'s journal-post try/except (`payroll.py:772-782`) treats this as fatal: it rolls back the whole payroll run and returns HTTP 500 ("Payroll processed but journal entry failed... Payroll has been rolled back — please retry.") for **every** employee in the batch, not just the security ones.
- Confirmed reachable from the UI: `App_js_fixed.js`'s new December bonus banner sets `includeBonus` and sends `include_annual_bonus: true` in the `/payroll/run` payload whenever the "Include bonus" toggle is checked (`App_js_fixed.js`, Run Payroll modal). This is a live, user-facing path, not dead code — the first NBCPSS company that clicks "Include bonus" in December will have its entire payroll run fail.
- **Recommended fix (not applied — outside this run's authorized edit scope, see §5b note below):** add `annual_bonus` to the `gross_incl_ot` debit in `journal.py:425` (e.g. `gross_incl_ot = round((payslip.gross_salary or 0) + overtime_total + (getattr(payslip, "annual_bonus", 0) or 0), 2)`).

**Medium — related, pre-existing gap (not new this run).** `bc_levy_employer` and `psira_levy_employer` (NBCPSS employer levies, R7.00 + R4.00/month per security employee, corrected this run from R9.40/R5.00) are computed in `calc_payroll` (`payroll.py:421-422`) and stored on the Payslip, and are correctly included in Reports' `Payslip.total_cost`-based payroll figures (see §2) — but `journal.py`'s `post_payroll()` never debits/credits them at all (no reference to either field in `journal.py`, confirmed via search). Because these are pure employer costs (not deducted from the employee, so they don't unbalance the existing entry), this doesn't crash payroll runs the way `annual_bonus` does — but it does mean the **general ledger** (trial balance, balance sheet, AFS) permanently understates payroll-related liabilities/expenses by R11/security-employee/month relative to what the Reports dashboard shows from the Payslip table. This predates the 2026-09-13 baseline (bc_levy/psira existed before) and was not previously flagged because NBCPSS was explicitly out of scope — flagging now because it's a direct Reports-vs-Ledger reconciliation gap.

Otherwise unchanged and re-verified:
- Journal coverage complete: all 13 `post_*` functions present in `journal.py` (invoice raised/paid/COGS, expense, expense paid, bank income, payroll, PO received/paid, stock adjustment, asset acquisition/depreciation/disposal) — no gaps.
- Import-awareness (2026-07-11 fixes) intact: `csv_import.py:463-475` still rejects non-ZAR invoice import rows lacking an explicit exchange rate.
- Rule 6/7 `source == "import"` exclusions and the 3998/3999 imported-equity offset logic (`payroll.py:1548-1568,1758,1834`) unchanged.

## 6. IFRS compliance (AFS)

**Framework:** IFRS for SMEs (unchanged). `financial_statements.py` untouched since before the 09-13 baseline (last touched in commit `5c5844a`/`381a9d5`, well before this run's diff range) — no code changes to re-verify beyond confirming byte-identical.

**Standards status (fresh web search this run, 14 September 2026):**
- IFRS 18 *Presentation and Disclosure in Financial Statements* — still effective for annual periods beginning on/after 1 January 2027, early application permitted; not yet applicable to IFRS-for-SMEs preparers. No change.
- IFRS for SMEs third edition (issued Feb 2025) — still effective 1 January 2027, full retrospective application under Section 10 with transition reliefs; 2015 edition remains usable until then. No change since 09-13.

**Section 5b — deferred tax:** already implemented (not hard-coded to `0.0`); re-verified at the code level, anchors unmoved from 09-13:
- `_deferred_tax_balance()` (`financial_statements.py:131`) computes per-asset tax base from `wear_and_tear_rate` (SARS IN47 category mapping documented `:87-110`).
- Opening/closing deferred tax balances drive `deferred_tax_expense` (`:266-268`); `total_tax` = current + deferred (`:601`); Note 9 fields populated (`:606,609-610`); `deferred_tax_movement` disclosed at `:681`.
- Balance-sheet closing balance carries the matching retained-earnings adjustment so Assets = Equity + Liabilities holds (unchanged, file untouched).

Finance costs (2026-07-13 fix): interest lines presented below EBIT; `profit_before_tax = ebit − finance_costs`; tax/net-profit derive from `profit_before_tax`, not EBIT — unchanged, file untouched.

## 7. Tax updates (company + payroll)

**Tax year checked:** 2026/2027 (1 March 2026 – 28 February 2027) — correct for the run date, present at `payroll.py:132-146`. Tables unchanged by this run's commits (only the NBCPSS section and cash-flow-13week were touched).

- PAYE brackets confirmed exact against a fresh web search this run: top of first bracket R245,100 at 18% (`payroll.py:134`) ✓, top bracket threshold R1,878,600 at 45% (`:140`) ✓, primary rebate R17,820 (`:142`) ✓, secondary rebate R9,765 (`:143`) ✓, tertiary rebate R3,249 (`:144`) ✓ — all match currently published SARS 2026/2027 figures. UIF ceiling R17,712/month (`:145`) ✓ matches (max employee UIF deduction R177.12/month), at `UIF_RATE = 0.01` (`:189`) employee + employer, `SDL_RATE = 0.01` (`:190`) employer-only — standard, unchanged. `_current_tax_year()` (`:170-181`) correctly resolves to `"2026/2027"` for the 14 Sept 2026 run date.
- CIT remains flat 27% — single source of truth `fixed_assets.SA_CIT_RATE` (`fixed_assets.py:78`), consumed by `financial_statements.py:82-84` and `payroll.py:2615` (`CORP_TAX_RATE`). No CIT change for 2026/2027.
- VAT standard rate confirmed unchanged at 15% across every hard-coded site: `companies.py:289`, `payroll.py:1630,2024,2971`, `quotes.py:15` (the new `_vat_net_for_month()` helper added 09-12/13 also uses its own local `VAT_RATE = 0.15` at `payroll.py:2024`, consistent). The Constitutional Court case on Section 7(4) of the VAT Act (Finance Minister's power to set the VAT rate without prior Parliamentary approval) **remains at "judgment reserved"** as at this run's date (heard 27 August 2026; fresh search on 14 September 2026 finds no ruling issued yet). No rate change; no code impact. Continue monitoring.
- No edits made to tax tables (report-only per task rules; §5b was verification-only this run, as it was already implemented).

**Sources consulted:** [VAT Act section declared invalid — The Citizen](https://www.citizen.co.za/news/south-africa/courts/vat-act-section-declared-invalid-unconstitutional/) · [Big VAT changes on the cards for South Africa — BusinessTech](https://businesstech.co.za/news/government/872697/big-vat-changes-on-the-cards-for-south-africa/) · [The Law Reports – September 2026 — De Rebus](https://www.derebus.org.za/the-law-reports-september-2026/) · [Godongwana's lawyers urge ConCourt to uphold VAT Act provisions — EWN](https://www.ewn.co.za/2026/08/27/godongwanas-lawyers-urge-concourt-to-uphold-vat-act-provisions-for-sound-fiscal-administration) · [Sars and Treasury ask top court to overturn ruling on minister's VAT powers — Business Day](https://www.businessday.co.za/news/2026-08-28-sars-and-treasury-ask-top-court-to-overturn-ruling-on-ministers-vat-powers/) · [ConCourt reserves judgment on Finance Minister's power to change VAT rate — eNCA](https://www.enca.com/news-top-stories/concourt-reserves-judgment-finance-ministers-power-change-vat-rate) · [List of judgments of the Constitutional Court of South Africa delivered in 2026 — Wikipedia](https://en.wikipedia.org/wiki/List_of_judgments_of_the_Constitutional_Court_of_South_Africa_delivered_in_2026) · [SARS Tax Tables 2026/2027 — Accounter](https://accounter.co.za/news/sars-tax-tables-2026-2027) · [PAYE Calculator South Africa | Salary, UIF & Net Pay 2026/2027 — Govchain](https://www.govchain.co.za/salary-tax-calculator) · [IFRS for SMEs gets a major update — XBRL](https://www.xbrl.org/news/ifrs-for-smes-gets-a-major-update/) · [Third edition of the IFRS for SMEs Accounting Standard — ACCA](https://www.accaglobal.com/learning-and-events/corporate-reporting/third-edition-ifrs-for-smes.html) · [IFRS for SMEs — ICAEW](https://www.icaew.com/technical/corporate-reporting/ifrs/ifrs-accounting-standards-tracker/ifrs-for-smes)

## 8. Action items

1. **Critical (new, cross-module journal integrity):** `journal.py`'s `post_payroll()` (`:421-425`) must include `payslip.annual_bonus` in the `gross_incl_ot` debit, or the entry will be unbalanced and `_assert_balanced()` (`journal.py:208-209`) will raise, rolling back the entire payroll run (`payroll.py:772-782`) whenever any employee has `include_annual_bonus=True` set (reachable today from `App_js_fixed.js`'s December bonus toggle). This will affect the first NBCPSS-industry company that runs a December payroll with the bonus included. Recommend an immediate targeted fix: add `+ (getattr(payslip, "annual_bonus", 0) or 0)` to the `gross_incl_ot` calculation.
2. **Medium (new, ledger completeness):** `journal.py`'s `post_payroll()` never posts `bc_levy_employer`/`psira_levy_employer` (R7.00 + R4.00 per NBCPSS security employee/month) to any account — these employer costs are visible in the Reports dashboard (sourced from `Payslip.total_cost`) but invisible in the trial balance/balance sheet/AFS (sourced from the journal). Recommend adding a debit to a payroll-levies expense account and a credit to a corresponding payable (mirroring the existing pension/medical pattern at `journal.py:444-455`) so the ledger reconciles with the Reports figures for security-industry companies.
3. **Low (repo clutter, new):** an untracked `LAUNCH_READINESS_2026-07-14.md` file exists in the project root — recommend committing or removing it.
4. **Medium (carried over):** the 13-week forecast still does not model provisional tax (IRP6) payments as a distinct weekly outflow.
5. **Low (carried over):** recommend a quick functional test adding a custom `/coa` account and posting an expense against it to confirm end-to-end routing via `expense_account()`.

**Standing reminders (not defects, carried from prior reports):**
(a) replace the provisional 2027/2028 `TAX_YEARS` entry after Budget Feb 2027 and restart the backend;
(b) early-2027 runs should execute the IFRS for SMEs 3rd-edition transition-plan checklist (`ifrs_smes_3rd_edition_transition_plan.md`);
(c) the AFS PayFast payment/ad-hoc tokenization feature and `/reports/ai-insights` remain outside this audit's scope;
(d) NBCPSS private security payroll mode predates this audit's baseline and its calculation detail (minimum wage checks, allowance rates, area rate tables) remains outside this checklist's explicit scope — except where, as in this run, it produces an in-scope journal-integrity failure;
(e) file-attribution note: the imported-equity-offset (3998/3999) exclusion logic lives in `payroll.py`'s `balance_sheet()`, not `financial_statements.py`;
(f) next run should keep checking for Treasury's review outcome or Parliamentary introduction of the 2026 draft TLAB/TALAB;
(g) `parent_company_id`/`user_type`, bookkeeper-onboarding, consolidated-billing, accountant-fee-structure, and accountant-practice-dashboard/`billing_exempt` features remain outside Reports/Debtors/Creditors/AFS/tax scope, awareness only;
(h) provisional tax remains the only known 13-week-forecast gap (tracked via action item 4);
(i) compulsory VAT-registration turnover threshold is R2,300,000 (voluntary R120,000), effective 1 April 2026 — not gated anywhere in-scope, awareness only;
(j) the persistent Chart of Accounts feature (`/coa` router) is additive and outside the original checklist's endpoint list — tracked via action item 5;
(k) the invoice header-image upload, custom HTML invoice template, and service-item catalogue (2026-08-29) remain additive presentation/picklist features outside the original checklist's endpoint list;
(l) the IASB's SME consolidation-exception Exposure Draft comment period closed 9 September 2026 — no final amendment published yet; check next run for a post-close update;
(m) the Constitutional Court has reserved judgment (heard 27 August 2026) on Section 7(4) of the VAT Act. No rate change and no ruling yet; monitor;
(n) the `/integrations/invoice` (SMT) endpoint remains formally in-scope going forward — spot-check with a real create + re-post cycle once real SMT traffic exists;
(o) `POST /accountant/sync-customers` remains tracked given its proximity to Debtors scope.
