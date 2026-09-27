# ZuZan Monthly Reconciliation Sweep — 2026-09-27

**Source:** `C:\Zuzan\zuzan-backend\zuzan.db` (opened read-only) · **Run date:** 27 Sep 2026 · **Tolerance:** R 1.00
**Script:** `recon_sweep.py` (automated scheduled run)

> ⚠️ **Data freshness:** this SQLite file was last modified 29 Jun 2026. The latest journal entry is dated 27 Jun 2026 and the latest invoice 27 May 2026. `database.py` falls back to this file only when `DATABASE_URL` is unset — if the live app runs on Postgres, this sweep did **not** see September's payroll or any activity after June. Results below reflect the local DB only.

## 1. Summary

| company_id | Name | BS balanced | AR reconciled | AP reconciled | Overdue AR (>90d) | Stale POs (>60d) | Negative stock | Overall |
|---|---|---|---|---|---|---|---|---|
| 1 | Tet Company | ✅ (no journal activity) | ✅ R 0.00 | ✅ R 0.00 | 0 | 0 | 0 | **PASS** |
| 2 | Nwabeg | ✅ R 0.00 diff | ✅ R 0.00 | ✅ R 0.00 | 0 | 0 | 0 | **PASS** |
| 3 | Solutha | ✅ R 0.00 diff | ✅ R 0.00 | ✅ R 0.00 | 1 (R 9,500.00) | 0 | 0 | **WARN** |

No FAIL conditions. All 16 journal entries balance individually (Dr = Cr) and no lines post to another company's accounts.

## 2. Failures & warnings

No check **failed**. One warning:

### Company 3 (Solutha) — Check 4: Overdue AR > 90 days — WARN

| Invoice ID | Invoice # | Client | Currency | Amount (ZAR) | Due date | Days overdue |
|---|---|---|---|---|---|---|
| 1 | INV-0001 | Okwendalo | ZAR | R 9,500.00 | 2026-05-31 | 119 |

The AR control account (1100) carries exactly this R 9,500.00, so the ledger is consistent — the issue is collectability, not a posting error.

### Check detail (for reference)

| Company | Assets | Liabilities | Equity | Revenue | Expenses | Dr-normal total | Cr-normal total |
|---|---|---|---|---|---|---|---|
| 1 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 2 | −17,327.37 | 0.00 | 0.00 | 0.00 | 17,327.37 | 0.00 | 0.00 |
| 3 | −16,639.82 | 2,737.30 | 0.00 | 9,500.00 | 28,877.12 | 12,237.30 | 12,237.30 |

AR (1100): Co 3 journal R 9,500.00 vs outstanding invoices R 9,500.00 (no import-sourced lines). AP (2000): zero journal balance for all companies; no purchase orders exist in the DB and no unpaid on-credit expenses.

### Observations outside the six checks (not scored)

- **Negative bank balances (account 1000):** Nwabeg R −17,327.37 (13 expenses imported from a NEDBANK statement, no receipts or opening balance); Solutha R −26,139.82. The books balance, but cash is overdrawn on paper — most likely a missing opening bank balance / unrecorded deposits rather than a real overdraft.
- **Unpaid payroll liabilities (Solutha):** PAYE R 2,183.06, UIF R 354.24, SDL R 200.00 (total R 2,737.30) from the May 2026 payroll remain credited to 2200/2210/2220 with no settlement entry. The May EMP201 was due 7 Jun 2026.
- **Spec vs endpoint differences:** the task spec's AR/AP checks are simpler than the live `/reports/reconciliation` (in `payroll.py` at ~line 2024, not 725–914): the endpoint excludes `source='import'` journal lines, uses delivered/journal-credited PO values for partial POs, and includes unpaid on-credit expenses in AP. The script follows the spec but also computed those components — all were zero this run, so the results agree either way.

## 3. Action items

1. **Confirm which database is live.** If production uses `DATABASE_URL` (e.g. Postgres), re-point this sweep at it (or run `/reports/reconciliation` against the server). This run cannot vouch for anything after 29 Jun 2026.
2. **Follow up INV-0001 (Okwendalo, R 9,500.00, 119 days overdue)** — chase payment, or consider a credit note / bad-debt write-off if uncollectable.
3. **Record opening bank balances / missing receipts** for Nwabeg and Solutha so account 1000 is no longer negative; reconcile against the NEDBANK statements.
4. **Check Solutha's May EMP201 (R 2,737.30)** — if paid to SARS, post the payment against 2200/2210/2220; if not, it is overdue.
5. No AR/AP drift was found. Should future runs show a 1100/2000 difference, `/journal/backfill` can repair missed invoice/PO postings.
6. **Update the scheduled task text:** the reconciliation function is at ~line 2024 of `payroll.py`, and the spec's AP check should include unpaid on-credit expenses and exclude imported opening balances to match the endpoint.
