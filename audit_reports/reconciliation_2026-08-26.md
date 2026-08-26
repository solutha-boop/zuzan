# Monthly Reconciliation Sweep — 2026-08-26

Automated run against `zuzan-backend/zuzan.db`, mirroring the checks in `/reports/reconciliation`. Tolerance for all monetary checks: R 1.00.

## 1. Summary

| Company ID | Company | BS balanced | AR reconciled (1100) | AP reconciled (2000) | Overdue AR (>90d) | Stale POs (>60d) | Negative stock | Overall |
|---|---|---|---|---|---|---|---|---|
| 1 | Tet Company | ✅ | ✅ (n/a — no invoices) | ✅ (n/a — no POs) | 0 | 0 | 0 | PASS |
| 2 | Nwabeg | ✅ | ✅ (n/a — no invoices) | ✅ (n/a — no POs) | 0 | 0 | 0 | PASS |
| 3 | Solutha | ✅ | ✅ (R9,500.00 = R9,500.00) | ✅ (n/a — no POs) | 0 | 0 | 0 | PASS |

All three companies pass every check. No AR/AP drift, no balance sheet imbalance, no aged debtors or creditors beyond threshold, no negative inventory.

Note: company 3 (Solutha) is internal test data with 3 test employees — its single test invoice and payroll activity are not production financial data ([memory: project_solutha_test_data]).

## 2. Failures

None. No check failed or warned for any company this run.

Observation (not a failure): company 2 (Nwabeg) carries a negative cash balance of R‑17,327.37 in account 1000 (Bank/Cash), offset by a single R17,327.37 posting to account 5900 (General Expenses). The balance sheet still balances (assets = liabilities + equity = ‑R17,327.37), so this is not flagged by any reconciliation rule, but an overdrawn bank account from a single large expense entry may be worth a manual look — it either reflects a genuine overdraft or a miscategorized/duplicate expense.

## 3. Action items

1. No repairs required — all control accounts (AR 1100, AP 2000) reconcile exactly with subledger totals across all 3 companies; no need to run `/journal/backfill`.
2. Recommend Soso review the R17,327.37 General Expenses posting for Nwabeg (company 2) to confirm it's a legitimate overdraft/expense and not a miscoded entry, since it leaves the company's cash account deeply negative.
3. No overdue debtors, stale purchase orders, or negative stock to action this month.
