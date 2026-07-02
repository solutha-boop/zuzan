# ZuZan Audit Report — Reports, Debtors & Creditors
**Date:** 2026-07-02
**Scope:** Reports (dashboard/management/trend), Debtors (AR), Creditors (AP), Cross-module journal coverage
**Files reviewed:** `payroll.py`, `journal.py`, `purchase_orders.py`, `companies.py`, `main.py`, `database.py`, `App_js_fixed.js`

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports — `/reports/dashboard` | ⚠️ ISSUE (partial-PO COGS now diverges from journal) |
| Reports — `/reports/management` | ⚠️ ISSUE (same partial-PO COGS divergence) |
| Reports — `/reports/monthly-trend` | ⚠️ ISSUE (same, plus received_date overwrite) |
| Reports — `/v1/summary` (Public API) | ⚠️ ISSUE (same partial-PO COGS divergence) |
| Debtors (AR) — backend `/reports/debtors-aging` | ✅ PASS |
| Debtors (AR) — frontend `Debtors` component | ✅ PASS |
| Creditors (AP) — backend `/reports/creditors-aging` | ✅ PASS (fixed since 2026-07-01) |
| Creditors (AP) — frontend `Creditors` component | ✅ PASS |
| Cross-module journal coverage | ⚠️ ISSUES (Rule 7 false-fail; no cumulative receipt tracking) |

**Overall verdict:** The three partial-PO issues from the 2026-07-01 audit were fixed with an incremental-posting redesign — the journal and Creditors book are now correct. However, the redesign was not carried through to the P&L reports or the AP reconciliation check, and the absence of per-item received-quantity tracking leaves a double-posting path open through the normal UI flow.

### Changes since last audit (2026-07-01)

- **FIXED — prior Action #1 (Critical):** `receive_po` now computes `received_total`/`received_vat` per delivery and passes them to `post_po_received` (purchase_orders.py:222–266; journal.py:363–412). The journal posts only what was delivered. ✓
- **FIXED — prior Action #3 (Medium):** `/reports/creditors-aging` now derives each PO's creditor amount from actual AP credits in the journal (payroll.py:1432–1452, 1495–1499) rather than `po.total_amount`. ✓
- **BONUS FIX:** `pay_po` now clears only the actual AP balance from the journal, not `po.total_amount` (purchase_orders.py:333–361; journal.py:415–441). ✓
- **PARTIALLY FIXED — prior Action #2:** the incremental design replaces the missing dedup guard, but without cumulative quantity tracking a new double-posting path exists (see Cross-module, Issue 2).
- **NOT CARRIED THROUGH:** dashboard/management/monthly-trend//v1/summary P&L and reconciliation Rule 7 still use full `po.total_amount` for partial POs — they now disagree with the (correct) journal.

---

## 2. Reports

### `/reports/dashboard` (payroll.py:430–569)

- Total revenue (line 443): sums only `InvoiceStatus.paid` invoices via `_to_zar()`. ✓
- Total outstanding (lines 445–449): `sent` + `overdue` via `_to_zar()`. ✓ (`sent` = "pending" per database.py enum comment.)
- Expenses ex-VAT, excluded from revenue. ✓
- Payroll: sums `Payslip.total_cost` for all employees incl. terminated; estimate fallback. ✓
- Depreciation included. ✓
- PO duplicate-count structural check present (lines 505–546). ✓

**⚠️ Issue (Medium):** PO COGS (lines 457–465) sums the **full** `(po.total_amount − po.vat_amount)` for status `"partial"` POs. Since 2026-07-01 the journal posts only delivered amounts, so for a half-delivered PO the dashboard P&L shows double the journal COGS. This overstates expenses and understates gross/net profit, and contradicts the design note in `post_po_received` (journal.py:376–380) that the journal P&L should match the dashboard.

### `/reports/management` (payroll.py:1064–1235)

- Revenue `_to_zar()` (1099), expenses ex-VAT (1107), depreciation (1129–1136), payroll incl. terminated (1144–1158), trend loop applies `_to_zar()` consistently (1184). ✓
- **⚠️ Same Medium issue:** PO COGS (1115–1126) and trend PO COGS (1191–1196) use full `total_amount` for partial POs.

### `/reports/monthly-trend` (payroll.py:572–641)

- Revenue per month via `_to_zar()` on `paid_date` (596–602). ✓ Expenses ex-VAT. ✓ Depreciation per period. ✓
- **⚠️ Same Medium issue:** PO COGS (613–622) uses full `total_amount` for partial POs.
- **⚠️ Low:** `receive_po` overwrites `po.received_date` on every delivery (purchase_orders.py:243), so a PO delivered across two months has its full COGS assigned to the **latest** delivery month.

### `/v1/summary` (main.py:251–293)

- Imports and applies `_to_zar()` for revenue and outstanding. ✓ Expenses/depreciation/payroll consistent with dashboard. ✓
- **⚠️ Same Medium issue:** PO COGS uses full `total_amount` for partial POs.

---

## 3. Debtors (AR)

✓ No issues found.

- **Status filter** (payroll.py:1357–1360): `status.in_([sent, overdue])` — paid and draft invoices excluded. ✓
- **ZAR amounts** (1371): `_to_zar(inv)` applied to every entry. ✓
- **Aging from `due_date`** (1364–1391): no fallback to issue/created dates; invoices without a due date go to `not_due`. Buckets: not_due / 0–30 / 31–60 / 61–90 / 90+. ✓
- **Frontend `Debtors`** (App_js_fixed.js:4670–4793): fetches `/reports/debtors-aging` on mount (4676), refreshes on `live.invoices` change (4680–4684), displays backend ZAR amounts (4749), demo-mode fallback only when API returns null. ✓

---

## 4. Creditors (AP)

✓ No issues found in the Creditors view itself (both prior issues fixed).

- **PO filter** (payroll.py:1427–1430): `status.in_(["received","partial"])` — fully paid POs excluded. ✓
- **Partial PO amounts** (1432–1452, 1495–1499): creditor amount = sum of AP credits (account 2000) posted by each delivery, with `po.total_amount` fallback only when no journal entry exists. Correct for partial deliveries. ✓ *(fixed since last audit)*
- **On-credit expenses** (1519–1565): unpaid `is_on_credit` expenses included, aged from `expense_date + 30`. ✓
- **Bank details decrypted** (1487–1489): `decrypt_field()` on bank_name / account_number / branch_code. ✓
- **Frontend `Creditors`** (App_js_fixed.js:4796+): fetches `/reports/creditors-aging` on mount, refreshes on `live.purchaseOrders`/`live.expenses`, client-side bucket filter recomputes vendor totals correctly (4833–4838). ✓

*Note (Low, informational):* decrypted supplier bank details are returned in the aging API response but not rendered by the frontend — consider omitting them from this endpoint to reduce exposure surface.

---

## 5. Cross-module Journal Coverage

All primary financial events remain wired to journal postings (verified in source):

| Event | Posting function | Called from | Status |
|---|---|---|---|
| Invoice raised / paid / COGS / deleted | post_invoice_* / reverse | companies.py:228, 275, 231, 301 | ✓ |
| Expense incurred / credit expense paid / deleted | post_expense(_paid) / reverse | companies.py:421, 552, 573, 782 | ✓ |
| PO received / paid / deleted | post_po_received / post_po_paid / reverse | purchase_orders.py:262, 361, 189 | ✓ |
| Payroll run | post_payroll | payroll.py:336 | ✓ |
| Asset acquisition / depreciation / disposal | post_asset_* / post_depreciation | fixed_assets.py:326, 628, 403 | ✓ |

**AR Control (1100):** reconciliation Rule 6 (payroll.py:842–862) compares journal balance to outstanding invoices via `_to_zar()`, tolerance R1.00. ✓

**⚠️ Issue 1 (High) — AP reconciliation Rule 7 not updated for incremental postings.**
payroll.py:864–898 compares the journal 2000 balance against `sum(po.total_amount)` for open POs (line 873). With incremental delivery postings, a partially-delivered PO's journal AP balance is *less* than `total_amount`, so **Rule 7 now false-fails whenever any partial PO exists**. Worse, the failure message tells users to run `/journal/backfill`, which skips POs that already have entries — the "repair" cannot clear the false fail. Rule 7 should reuse the same journal-credit lookup that creditors-aging uses. (Rule 5, lines 826–840, has the same overstatement but is warn-only informational — Low.)

**⚠️ Issue 2 (High) — no cumulative received-quantity tracking enables double-posting via the normal flow.**
`PurchaseOrderItem` (database.py:244–249) has no `quantity_received` column, and `receive_po` (purchase_orders.py:222–242) evaluates only the quantities in *this* call:
- A PO delivered 50 + 50 of 100 never reaches status `"received"` — each call compares its own quantity to the full ordered quantity (line 229), so the PO stays `"partial"` forever.
- To close it out, the user's natural move is to submit the full quantity in a final call — which posts the **full amount again** to COGS/AP. The old double-posting bug is reachable through the intended UI path.
- Nothing caps cumulative receipts at the ordered quantity (receive 60, then 60 again → 120% of PO posted).

**⚠️ Issue 3 (Medium) — backfill posts full amounts for partial POs.**
`backfill_company` (journal.py:652–663) calls `post_po_received(po, db)` without `received_net`, posting the full `total_amount` for any partial PO lacking journal entries — overstating AP/COGS for the undelivered portion.

**⚠️ Issue 4 (Medium) — pay-then-receive workflow gap.**
`pay_po` marks the whole PO `"paid"` even when only part was delivered/cleared, yet `receive_po` does not block status `"paid"` (line 219 blocks only `"received"`/`"cancelled"`). Receiving the remainder after payment flips the status back to `"partial"`/`"received"`, re-opening the PO in creditors-aging while the earlier payment debits (source `"po_payment"`) are ignored by the credit-only AP lookup (payroll.py:1440) — overstating the creditor.

---

## 6. Action Items

**#1 — High: Update reconciliation Rule 7 to reconcile against journal-derived per-PO AP balances**
`payroll.py:864–898`. Replace `sum(po.total_amount)` with the same account-2000 credit (minus `po_payment` debit) lookup used by `/reports/creditors-aging`, so partial POs don't trigger false FAILs directing users to a backfill that cannot fix them.

**#2 — High: Add `quantity_received` tracking to `PurchaseOrderItem`**
`database.py` (add column + migration inside the migrations list literal — see prior migration pitfall), `purchase_orders.py:222–242`. Accumulate received quantities per item, compute `all_received` from cumulative totals, post only the delta, and reject receipts exceeding the ordered quantity. This closes the double-posting path and lets multi-delivery POs reach `"received"`.

**#3 — Medium: Make P&L PO COGS consistent with the journal for partial POs**
`payroll.py:457–465, 613–622, 1115–1126, 1191–1196`; `main.py` `/v1/summary`. Either source PO COGS from journal account 5000 entries, or pro-rate by delivered amount. Until then, dashboard expenses are overstated for partially delivered POs.

**#4 — Medium: Pass delivered amounts in backfill, or skip partial POs with a warning**
`journal.py:652–663`. Backfilling a partial PO at full `total_amount` recreates the pre-fix overstatement.

**#5 — Medium: Block `receive_po` on status `"paid"` (or handle post-payment deliveries explicitly)**
`purchase_orders.py:219`. Also make the AP lookup in creditors-aging subtract `po_payment` debits if paid-then-received is meant to be supported.

**#6 — Low: Stop overwriting `received_date` on subsequent deliveries**
`purchase_orders.py:243`. Set it only on first receipt (or track per-delivery dates) so trend reports assign COGS to the right month.

**#7 — Low (carried from 2026-07-01): legacy `received_date` backfill uses `created_at` as proxy**
`main.py` startup backfill and `purchase_orders.py:285–308`. Unchanged; consider flagging affected POs in the UI.

---

## 7. Fixes Applied (same day, 2026-07-02)

All action items except #7 were fixed after this audit was written:

| # | Fix | Files |
|---|---|---|
| 1 | Rule 7 now reconciles against journal-derived per-PO AP credits (same lookup as creditors-aging), with `total_amount` fallback only when no entry exists. Rule 5 amounts use delivered value. | payroll.py:893–926, 854–869 |
| 2 | Added `PurchaseOrderItem.quantity_received` (+ idempotent migration inside the migrations list; legacy items on received/paid POs backfilled to full quantity). `receive_po` accumulates per-item receipts, rejects over-receipt with a clear message, derives `all_received` from cumulative totals, and rejects negative quantities. | database.py:250–252, 798–805; purchase_orders.py:222–260 |
| 3 | P&L PO COGS uses new `_po_delivered_net()` (delivered value for partial POs; full-subtotal fallback for legacy partials, consistent with their full-amount journal entries) in dashboard, monthly-trend, management + trend, and `/v1/summary`. | payroll.py:27–48, 486, 642, 1175, 1245; main.py:254, 266 |
| 4 | `backfill_company` posts delivered value for partial POs with tracking data; full amount only for legacy partials (matching `_po_delivered_net`). | journal.py:656–677 |
| 5 | `receive_po` now blocks status `"paid"`; `update_po` blocks item edits on received/partial/paid POs (would wipe receipt tracking and desync journal). | purchase_orders.py:228, 117–122 |
| 6 | `received_date` set only on first delivery. | purchase_orders.py:271–272 |
| — | Frontend: "Receive Goods" button now also shown for partial POs ("Receive Remaining Goods"); receipt modal shows Ordered/Prior/This-delivery columns, defaults to remaining quantity, and caps input at remaining. `to_dict` returns `quantity_received`. | App_js_fixed.js:7807–7818, 7863–7889, 7911; purchase_orders.py:57 |

**Verification:** all edited regions re-read from disk; cumulative-receipt and delivered-net logic validated with unit tests (two half-deliveries reach "received" and post 100% exactly once; over-receipt and re-submitting the full order are rejected; fractional quantities handled; legacy partial POs fall back to full value; multi-item completion logic correct).

**Residual notes:**
- Legacy partial POs (created before quantity tracking) have `quantity_received = 0`; their prior deliveries can't be reconstructed, so they fall back to full-amount treatment everywhere (consistent across journal, P&L, creditors). Their receive flow starts counting from zero — users should verify these POs manually.
- Action item #7 (legacy `received_date` = `created_at` proxy) remains open.
