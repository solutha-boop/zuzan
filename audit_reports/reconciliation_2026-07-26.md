# Monthly Reconciliation Sweep — 2026-07-26

Automated run against `zuzan.db` directly (no live server). Mirrors the checks in `/reports/reconciliation` for each company in the database.

**Note on methodology:** Checks 2 (AR) and 3 (AP) here are simplified relative to the live endpoint. The live `/reports/reconciliation` excludes imported opening balances (journal entries with `source == "import"`) from the AR/AP comparison, and its AP check also folds in unpaid on-credit expenses. This sweep does not make those adjustments. None of that mattered this run — no import-sourced lines or unpaid credit expenses were present on accounts 1100/2000 for any company — but it's worth knowing if a future run shows an AR/AP diff that the live endpoint doesn't.

## 1. Summary

| Company | BS Balanced | AR Reconciled | AP Reconciled | Overdue AR (>90d) | Stale POs (>60d) | Negative Stock | Overall |
|---|---|---|---|---|---|---|---|
| 1 — Tet Company | ✓ | ✓ | ✓ | 0 | 0 | 0 | **PASS** |
| 2 — Nwabeg | ✓ | ✓ | ✓ | 0 | 0 | 0 | **PASS** |
| 3 — Solutha | ✓ | ✓ | ✓ | 0 | 0 | 0 | **PASS** |

All three companies pass every check. Companies 1 and 2 have no posted journal activity, invoices, purchase orders, or inventory yet — their zeros reflect an empty ledger, not a reconciled one. Company 3 (Solutha) has live activity and reconciles exactly:

- Trial balance: debit-normal (assets + expenses) total R12,237.30 = credit-normal (liabilities + equity + revenue) total R12,237.30.
- AR control (1100): journal balance R9,500.00 = outstanding invoice total R9,500.00 (1 invoice, status `sent`/`overdue`).
- AP control (2000): journal balance R0.00 = open PO total R0.00 (no purchase orders in the database).

## 2. Failures

None. No check failed or produced a warning for any company this run.

## 3. Action items

1. No repairs required — all reconciliation checks passed for all three companies as of 2026-07-26.
2. Re-run this sweep after each future payroll run / month-end; if a future AR or AP diff appears, run `/journal/backfill` first (repairs missed postings), then re-check — if the diff persists, check for import-sourced opening-balance lines or unpaid on-credit expenses per the methodology note above before treating it as a genuine break.
3. Companies 1 (Tet Company) and 2 (Nwabeg) show no financial activity at all — confirm whether these are intentional test/demo companies or accounts that should have been onboarded with real data; if test accounts, consider excluding them from future sweeps to keep the summary table focused on real customers.
