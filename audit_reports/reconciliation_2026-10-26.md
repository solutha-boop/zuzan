# ZuZan Monthly Reconciliation Sweep — 2026-10-26

**Source:** `C:\Zuzan\zuzan-backend\zuzan.db` (copied with its WAL, opened read-only) · **Run date:** 26 Oct 2026 · **Tolerance:** R 1.00
**Script:** `recon_sweep.py` (in this folder; unchanged from the 27 Sep run)

> ⚠️ **Data freshness:** the latest journal entry in this DB is dated 27 Jun 2026 and the latest invoice 27 May 2026 — nothing since. `database.py` uses this file only when `DATABASE_URL` is unset. If the live app runs on another database, this sweep did **not** see July–October activity (including the September/October payroll runs). Results reflect the local DB only.

## 1. Summary

| company_id | Name | BS balanced | AR reconciled | AP reconciled | Overdue AR (>90d) | Stale POs (>60d) | Negative stock | Overall |
|---|---|---|---|---|---|---|---|---|
| 1 | Tet Company | ✅ (no journal activity) | ✅ R 0.00 | ✅ R 0.00 | 0 | 0 | 0 | **PASS** |
| 2 | Nwabeg | ✅ R 0.00 diff | ✅ R 0.00 | ✅ R 0.00 | 0 | 0 | 0 | **PASS** |
| 3 | Solutha | ✅ R 0.00 diff | ✅ R 0.00 | ✅ R 0.00 | 1 (R 9,500.00) | 0 | 0 | **WARN** |

No FAIL conditions. All 16 journal entries balance individually and no lines post to another company's accounts.

## 2. Failures & warnings

No check **failed**. One warning (carried over from the 27 Sep run):

### Company 3 (Solutha) — Check 4: Overdue AR > 90 days — WARN

| Invoice ID | Invoice # | Client | Currency | Amount (ZAR) | Due date | Days overdue |
|---|---|---|---|---|---|---|
| 1 | INV-0001 | Okwendalo | ZAR | R 9,500.00 | 2026-05-31 | 148 |

Account 1100 carries exactly this R 9,500.00, so the ledger is consistent — the issue is collectability, not posting.

### Check detail

| Company | Assets | Liabilities | Equity | Revenue | Expenses |
|---|---|---|---|---|---|
| 1 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 2 | −17,327.37 | 0.00 | 0.00 | 0.00 | 17,327.37 |
| 3 | −16,639.82 | 2,737.30 | 0.00 | 9,500.00 | 28,877.12 |

AR (1100): Co 3 journal R 9,500.00 vs outstanding invoices R 9,500.00. AP (2000): zero for all companies; no purchase orders, no unpaid on-credit expenses. Balance-sheet check uses Assets − (Liabilities + Equity + Revenue − Expenses).

## 3. Action items

1. **Confirm which database is live.** If production is not this SQLite file, point the sweep at it (or call `/reports/reconciliation` on the server). This run cannot vouch for anything after 27 Jun 2026.
2. **Follow up INV-0001 (Okwendalo, R 9,500.00, 148 days overdue)** — chase, or issue a credit note / write off if uncollectable.
3. **Record opening bank balances / missing receipts** for Nwabeg and Solutha (account 1000 is negative on paper); reconcile to bank statements.
4. **Solutha payroll liabilities (R 2,737.30: PAYE 2,183.06, UIF 354.24, SDL 200.00)** from May 2026 still sit unsettled in 2200/2210/2220 — post the SARS payment if paid, otherwise it is overdue.
5. No AR/AP drift found. If a future run shows a 1100/2000 difference, `/journal/backfill` can repair missed invoice/PO postings.
6. Update the scheduled task text: the live reconciliation function is at ~line 2749 of `payroll.py`; its AR/AP checks exclude `source='import'` lines and AP includes unpaid on-credit expenses and journal-credited PO values.
