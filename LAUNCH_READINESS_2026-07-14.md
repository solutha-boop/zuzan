# ZuZan Launch Readiness — 2026-07-14

Full pre-launch sweep covering the audit trail, code fixes, billing lifecycle, and operational/business items.

## Verdict

**Code: GO** — all audit items pass or are closed; two launch gaps found in the billing lifecycle were fixed this sweep. **Two deploy steps and three business items need action before/at launch** (see Action list).

## 1. Audit trail — all report families

| Audit | Latest run | Status |
|---|---|---|
| Reports / Debtors / Creditors + IFRS + SARS (nightly) | 2026-07-14 | ✅ PASS — deferred tax (L3, last open item) implemented |
| Journal integrity (weekly) | 2026-07-13 | ✅ PASS — 0 gaps across all 5 checks |
| Reconciliation sweep (monthly) | 2026-06-27 | ✅ PASS — all companies balanced; next run 26 Jul |
| EMP201 (monthly) | 2026-07-05 run | ✅ Automated; May warnings were test companies only |

No unresolved defects remain in any audit report. Carried-over Lows all closed (L1 reversal-awareness ✅ 07-13, L3 deferred tax ✅ 07-14, L4 finance costs ✅ 07-13, M4/L5 ✅ earlier).

## 2. Code items closed this sweep

1. **Frontend sync** — `zuzan-app/src/App.js` is byte-identical to `App_js_fixed.js` (sha256 match), including the Note 9 deferred-tax row and finance-costs rows. Nothing to do.
2. **Deferred-tax migration** — `wear_and_tear_rate` ALTER TABLE is inside the migrations list literal (database.py:1297). Runs automatically at next backend start.
3. **Calculator unification** (register `/fixed-assets/deferred-tax` vs AFS as-at-date computation) — deliberately deferred post-launch: figures differ only for historical FYs by design, and code churn now adds risk. Non-blocking.

## 3. Launch gaps found and FIXED this sweep

### 3a. Billing checks only ran at process startup — FIXED
`check_trial_expirations()` / `send_overdue_reminders()` / recurring invoices / due auto-reversals ran once at startup (main.py lifespan). On a long-running server, a trial could expire with **no email ever sent** until the next deploy. Added a 24-hour background maintenance loop inside the lifespan handler (main.py:127–160), cancelled cleanly on shutdown. All callees are idempotent (send-once timestamps, next_run_date, reversal-date checks).

### 3b. "Cancel subscription" silently no-oped — FIXED
The frontend PUTs `subscription_status` to `/companies/me` (App_js_fixed.js:7279, :7296), but the field wasn't in `CompanyUpdate`, so Pydantic dropped it: the UI showed "cancelled" while the backend kept the old status — a consumer-protection problem at launch. Fixed with guarded transitions in companies.py (update_company):

- `→ cancelled` allowed from trial/active (cancel / auto-renew off)
- `cancelled → active` allowed only as an undo, restoring what the company is entitled to: active if a successful `SubscriptionPayment` covers the current period, else trial if `trial_ends` is in the future, else expired
- everything else (e.g. self-activating from expired) → 400; activation still only happens via the PayFast ITN handler after real payment

Self-activation was and remains impossible — verified.

## 4. Billing lifecycle — verified end to end

- 14-day trial set at signup (auth.py:116) ✓
- Warning email before expiry + expiry email, each sent once via timestamp flags (billing.py:233–308) ✓ — now re-checked daily (fix 3a)
- Frontend trial countdown, expired banner, Subscribe/Reactivate via PayFast redirect (App_js_fixed.js:7249–7257, :11869–11879) ✓
- PayFast ITN activates subscription + logs `SubscriptionPayment` + confirmation email (billing.py:145–211) ✓
- Tokenized recurring billing still in build — manual follow-up on expiries remains the interim plan, per existing decision ✓

## 5. Operational — scheduled automation

All enabled and healthy: nightly reports audit (last ran 07-13), weekly journal integrity (07-13), monthly EMP201 (07-05), monthly reconciliation (next 07-26), annual SARS tax-table task (fires 1 Mar 2027), Render PostgreSQL upgrade reminder (15 Aug).

**Missing:** the planned support-inbox AI monitor is not yet scheduled (depends on support@solutha.co.za → Gmail forwarding + Gmail connector).

## 6. Action list

**Before/at launch (deploy steps):**
1. **Restart/redeploy the backend once** — runs the `wear_and_tear_rate` migration and starts the new daily maintenance loop. Then spot-check: AFS Note 9 renders, and toggling Cancel subscription on a test company persists after reload.
2. **Commit + push** today's changes (database.py, financial_statements.py, main.py, companies.py, App_js_fixed.js + synced App.js).

**Business items (not code-blocking, but pre-launch):**
3. **Information Officer registration** with the Information Regulator (POPIA) — still pending.
4. **Support email**: set up support@solutha.co.za → Gmail forwarding, connect the Gmail connector, then schedule the support monitor task.
5. **Confirm May/June EMP201 submissions** for Solutha on eFiling (flagged 06-27, cannot be verified programmatically).

**Post-launch (tracked, non-blocking):**
6. Unify the two deferred-tax calculators; PayFast tokenization for recurring billing; IFRS for SMEs 3rd-edition transition review ahead of FY2028; secondary/tertiary rebates if 65+ employees onboarded; Render PostgreSQL upgrade before free-tier expiry (reminder set, 15 Aug).
