# ZuZan Audit Report — Reports, Debtors & Creditors
**Date:** 2026-07-03
**Scope:** Reports (dashboard/management/trend/summary), Debtors (AR), Creditors (AP), Cross-module journal coverage
**Files reviewed:** `payroll.py`, `journal.py`, `purchase_orders.py`, `companies.py`, `main.py`, `database.py`, `portal.py`, `App_js_fixed.js`

---

## 1. Summary

| Section | Verdict |
|---|---|
| Reports — `/reports/dashboard` | ⚠️ ISSUE (pay-a-partial-PO reopens P&L/journal divergence) |
| Reports — `/reports/management` | ⚠️ Same issue |
| Reports — `/reports/monthly-trend` | ⚠️ Same issue |
| Reports — `/v1/summary` (Public API) | ⚠️ Same issue |
| Debtors (AR) — backend `/reports/debtors-aging` | ✅ PASS |
| Debtors (AR) — frontend `Debtors` component | ✅ PASS |
| Creditors (AP) — backend `/reports/creditors-aging` | ✅ PASS |
| Creditors (AP) — frontend `Creditors` component | ✅ PASS |
| Cross-module journal coverage | ❌ FAIL (client-portal payments never reach the journal) |

**Overall verdict:** All six fixes applied after the 2026-07-02 audit are verified in source and correct. Two new issues found: (1) the client-portal PayFast payment handler calls a journal function that does not exist, so portal-paid invoices silently skip their journal posting — the AR control account will fail reconciliation after any portal payment; (2) paying a partially delivered PO flips its status to `"paid"`, which makes `_po_delivered_net()` fall back to the full subtotal — reopening (via a different door) the P&L-vs-journal divergence that was fixed yesterday.

### Changes since last audit (2026-07-02)

All same-day fixes from yesterday's report re-verified in today's source:

- Dashboard, monthly-trend, management (+trend), and `/v1/summary` all use `_po_delivered_net()` (payroll.py:485–491, 641–649, 1168–1175, 1245–1250; main.py:261–277). ✓
- Reconciliation Rule 7 reconciles against journal-derived per-PO AP credits (payroll.py:893–951); Rule 5 uses delivered value (payroll.py:854–869). ✓
- `PurchaseOrderItem.quantity_received` column + idempotent migration and legacy backfill (database.py:250–252, 1013–1015); cumulative receipt tracking with over-receipt rejection (purchase_orders.py:231–260). ✓
- `receive_po` blocks status `"paid"` (purchase_orders.py:228); `update_po` blocks item edits on received/partial/paid POs (purchase_orders.py:117–122). ✓
- `received_date` set only on first delivery (purchase_orders.py:271–272). ✓
- Backfill posts delivered value for tracked partial POs (journal.py:656–677). ✓
- Frontend receive-remaining flow with per-item remaining defaults (App_js_fixed.js:7843–7853). ✓

**New since last run:** the portal payment journal bug (Issue 1) — `portal.py` was not in previous audits' file lists; and the pay-partial-PO P&L fallback (Issue 2), a gap in yesterday's fix #3.

---

## 2. Reports

### `/reports/dashboard` (payroll.py:455–596)

- Total revenue (payroll.py:464–468): sums ONLY `InvoiceStatus.paid` invoices via `_to_zar()`. ✓
- `_to_zar()` (payroll.py:17–24): non-ZAR uses `paid_amount_zar` when present, else `total_amount × exchange_rate`; ZAR as-is. ✓
- Total outstanding (payroll.py:470–474): `sent` + `overdue` via `_to_zar()` (`sent` = "pending" per enum). ✓
- Expenses excluded from revenue; ex-VAT for P&L (payroll.py:477–480). ✓
- Payroll included via all payslips (incl. terminated employees), estimate fallback (payroll.py:504–516). ✓
- PO COGS from `_po_delivered_net()` for received/partial/paid POs, no separate Expense created on receipt (no double-count; purchase_orders.py:274–278), plus structural duplicate-expense warning (payroll.py:532–573). ✓
- Depreciation included (payroll.py:494–498). ✓

**⚠️ Issue (Medium — new):** `_po_delivered_net()` (payroll.py:27–41) returns the **full subtotal for any status other than `"partial"`**. `pay_po` accepts partial POs (purchase_orders.py:352) and the UI shows "Mark as Paid" for partial POs (App_js_fixed.js:7855–7863). Paying a half-delivered PO sets status `"paid"`, so all four P&L endpoints jump from delivered value to full subtotal — while the journal correctly carries only the delivered COGS (the payment clears only the actual AP balance, purchase_orders.py:362–390). Expenses are overstated by the undelivered portion. Fix: for `"paid"` POs, use the same `quantity_received × unit_price` sum when tracking data exists (legacy items on paid POs were backfilled to full quantity, so they are unaffected).

### `/reports/management` (payroll.py:1117–1289)

- Revenue via `_to_zar()` (1152), expenses ex-VAT (1160), PO COGS via `_po_delivered_net()` (1175), depreciation (1183–1190), payroll incl. terminated (1198–1212), trend loop applies `_to_zar()` consistently (1238) and `_po_delivered_net()` (1245). ✓
- **⚠️ Same Medium issue** via `_po_delivered_net()` fallback for paid-formerly-partial POs (1168–1175, 1245–1250).

### `/reports/monthly-trend` (payroll.py:599–669)

- Revenue per month via `_to_zar()` on `paid_date` (623–630). ✓ Expenses ex-VAT (632–638). ✓ Depreciation per period (652–658). ✓
- **⚠️ Same Medium issue** (641–650).

### `/v1/summary` (main.py:258–300)

- Imports and applies `_to_zar()` and `_po_delivered_net()` (main.py:261–277, 294). ✓
- **⚠️ Same Medium issue.**

---

## 3. Debtors (AR)

✓ No issues found.

- **Status filter** (payroll.py:1411–1414): `status.in_([sent, overdue])` — paid and draft invoices excluded. ✓
- **ZAR amounts** (payroll.py:1425): `_to_zar(inv)` applied to every entry. ✓
- **Aging from `due_date`** (payroll.py:1418–1445): no fallback to issue/created dates; invoices with no due date go to `not_due`. Buckets: not_due / 0–30 / 31–60 / 61–90 / 90+. ✓
- **Frontend `Debtors`** (App_js_fixed.js:4670–4793): fetches `/reports/debtors-aging` on mount (4676), refreshes on `live.invoices` change (4680–4684), displays backend ZAR amounts as-is (4749), demo-mode fallback clearly badged and only when the API returns null (4704–4716). ✓

---

## 4. Creditors (AP)

✓ No issues found in the Creditors view itself.

- **PO filter** (payroll.py:1481–1484): `status.in_(["received","partial"])` — fully paid POs excluded. ✓
- **Partial PO amounts** (payroll.py:1486–1506, 1549–1553): creditor amount = sum of AP credits (account 2000) posted per delivery, with `po.total_amount` fallback only when no journal entry exists. ✓
- **On-credit expenses** (payroll.py:1571–1619): unpaid `is_on_credit` expenses included, aged from `expense_date + 30`. ✓
- **Bank details decrypted** (payroll.py:1541–1543): `decrypt_field()` on bank_name / account_number / branch_code. ✓
- **Frontend `Creditors`** (App_js_fixed.js:4796–4930): fetches `/reports/creditors-aging` on mount (4803), refreshes on `live.purchaseOrders`/`live.expenses` (4807–4811), bucket filter recomputes vendor totals from filtered items correctly (4833–4838). ✓

*Note (Low, carried):* decrypted supplier bank details are returned by the aging API but never rendered by the frontend — consider omitting them from this endpoint to reduce exposure surface.

---

## 5. Cross-module Journal Coverage

| Event | Posting function | Called from | Status |
|---|---|---|---|
| Invoice raised / COGS / paid / deleted | post_invoice_* / reverse | companies.py:228, 231, 275, 301 | ✓ |
| **Invoice paid via client portal (PayFast IPN)** | *nonexistent function* | portal.py:188 | ❌ |
| Expense incurred / credit expense paid / deleted | post_expense(_paid) / reverse | companies.py:421, 552, 573, 782 | ✓ |
| PO received / paid / deleted | post_po_received / post_po_paid / reverse | purchase_orders.py:291, 390, 195 | ✓ |
| Payroll run | post_payroll | payroll.py:361 | ✓ |
| Asset acquisition / depreciation / disposal | post_asset_* / post_depreciation | fixed_assets.py:326, 628, 403 | ✓ |

**AR Control (1100):** Rule 6 (payroll.py:871–891) compares journal balance to outstanding invoices via `_to_zar()`, tolerance R1.00. ✓
**AP Control (2000):** Rule 7 (payroll.py:893–951) reconciles against journal-derived per-PO AP credits + unpaid credit expenses. ✓ *(fixed since 2026-07-01, verified today)*

**❌ Issue 1 (Critical) — client-portal payments never post to the journal.**
`portal.py:184–191` (PayFast IPN handler) has three defects in one block:
1. It calls `journal_engine.post_invoice_payment(inv.id, db2)` — **no such function exists** (journal.py defines `post_invoice_paid`). Every call raises `AttributeError`.
2. Even if the name were right, it passes `inv.id` instead of the invoice object.
3. It never commits `db2`, so nothing would persist anyway.
The exception is swallowed by `except ... logger.warning(... non-fatal ...)`, so the failure is invisible. Net effect: every invoice paid through the client portal is marked paid **without** the DR Bank / CR Accounts Receivable posting — the journal still carries the invoice in AR, and **Rule 6 (AR Control) fails** until someone runs `/journal/backfill` (which does repair it, since backfill covers `invoice_payment`). Fix: `journal_engine.post_invoice_paid(inv, db)` on the request's own session, committed, mirroring companies.py:275.

**⚠️ Issue 2 (Medium) — paying a partial PO reverts its P&L COGS to full subtotal.**
See Reports section. Journal, creditors book, and Rules 5/7 all correctly exclude/settle the PO; only the four P&L report endpoints overstate. Related: `backfill_company` (journal.py:662–673) computes delivered-value kwargs only when `po.status == "partial"`, so a paid-formerly-partial PO missing journal entries would also backfill at full value — fix together with `_po_delivered_net()`.

**⚠️ Issue 3 (Medium, out of nominal scope but a known recurring pitfall) — dead migration code in `database.py`.**
database.py:1064–1098: the Client-Portal `DO $$ ... $$` block, the `invite_tokens`/`audit_log` CREATE TABLE statements, and `"UPDATE users SET role = 'owner' WHERE role IS NULL OR role = ''"` sit **after** the for-loop's try/except as bare string expressions — they are evaluated and discarded, never executed. Practical impact is limited (InviteToken/AuditLog are ORM models created by `create_all`; plain `portal_token` ALTERs exist inside the list at database.py:962–963) but the **role backfill never runs** (legacy users with NULL/empty role are never promoted to owner) and the partial unique index on `portal_token` is never created. Move all four statements inside the migrations list literal.

**⚠️ Issue 4 (Low) — `update_po` accepts arbitrary status transitions.**
purchase_orders.py:113 assigns `data.status` unvalidated. The UI only uses this for draft → cancelled (App_js_fixed.js:7879–7881), but any API client can PUT `status: "received"` or `"paid"`, bypassing journal posting and receipt tracking entirely (Rule 7's `total_amount` fallback would then report a false AP figure). Whitelist allowed transitions (e.g. draft/sent ↔ cancelled only) and route everything else through `/receive` and `/pay`.

---

## 6. Action Items

**#1 — Critical: Fix the portal payment journal posting**
`portal.py:184–191`. Replace with `journal_engine.post_invoice_paid(inv, db)` on the same session, followed by `db.commit()`; drop the throwaway `db2` session (or commit and close it in a `finally`). Consider surfacing (not just warn-logging) journal failures. Until fixed, run `/journal/backfill` after portal payments to keep Rule 6 passing.

**#2 — Medium: Make `_po_delivered_net()` delivery-aware for `"paid"` POs**
`payroll.py:27–41`. When a PO has receipt tracking data (`any(i.quantity_received for i in po.items)`), return the delivered sum regardless of status; keep the full-subtotal fallback only for untracked legacy POs. Apply the same condition in `backfill_company` (journal.py:662–673). Alternatively, block `pay_po` for partial POs and require closing the PO first.

**#3 — Medium: Move dead migration statements into the migrations list**
`database.py:1064–1098`. Known pitfall — bare strings after the loop's try/except are no-ops. The `UPDATE users SET role='owner'` backfill and the `portal_token` unique index currently never execute.

**#4 — Low: Whitelist status transitions in `update_po`**
`purchase_orders.py:113`.

**#5 — Low (carried from 2026-07-01): legacy `received_date` backfill uses `created_at` as proxy**
`purchase_orders.py:314–337`. Unchanged; consider flagging affected POs in the UI.

**#6 — Low (carried): omit decrypted supplier bank details from `/reports/creditors-aging`**
`payroll.py:1541–1543`. Frontend never renders them.

---

## 7. Fixes Applied (same day, 2026-07-03)

Action items #1–#4 were fixed after this audit was written:

| # | Fix | Files |
|---|---|---|
| 1 | Portal IPN now calls `journal_engine.post_invoice_paid(inv, db)` (real function, Invoice object, request's own session) after `init_accounts`, followed by `db.commit()`. Kept non-fatal by design (invoice is already marked paid; IPN retries hit the already-paid guard), but failures now log at ERROR level with an explicit pointer to `/journal/backfill`. | portal.py:184–202 |
| 2 | `_po_delivered_net()` now treats `"paid"` like `"partial"`: uses the per-item `quantity_received × unit_price` sum when tracking data exists, so paying a partially delivered PO no longer reverts P&L COGS to the full subtotal. Fully received/paid POs unchanged (delivered sum = subtotal; migration backfilled their quantities in full); untracked legacy POs keep the full-subtotal fallback. Backfill receive loop applies the same condition, and the backfill payment loop now clears only the actual AP credits posted for each PO (mirrors `pay_po`), falling back to `total_amount` only when no credits exist. | payroll.py:27–47; journal.py:658–677, 683–718 |
| 3 | Dead migration statements moved INTO the migrations list literal: Client-Portal DO block (with the unique index moved outside the column-existence IF so it also gets created on databases where the columns already exist), `invite_tokens`/`audit_log` CREATE TABLEs, and the `UPDATE users SET role='owner'` backfill (idempotent, runs every startup now). | database.py:1056–1097 |
| 4 | `update_po` whitelists status transitions (draft ↔ sent, draft/sent → cancelled, cancelled → draft). Financial statuses (received/partial/paid) are rejected with a message directing callers to `/receive` and `/pay`. No-op same-status PUTs skip validation, so the frontend's `saveDraft` flow is unaffected; the UI's only direct transition (draft → cancelled) is allowed. | purchase_orders.py:113–129 |

**Verification:** all edited regions re-read from disk (Read tool, per the stale-mount pitfall — not bash); `_po_delivered_net` logic validated with 8 unit cases (paid-formerly-partial returns delivered value; fully paid returns subtotal; legacy untracked falls back to full; fractional quantities; no-VAT POs) and the transition whitelist with 8 cases — all pass. Frontend PO flows checked against the new whitelist: `updateStatus` is used only for draft → cancelled (App_js_fixed.js:7879–7881) and `saveDraft` only PUTs `status:"draft"` on draft/sent POs — both permitted.

**Residual notes (unchanged):**
- Action #5 (legacy `received_date` = `created_at` proxy) is a data-quality item on pre-existing rows — needs user judgment per PO, left open.
- Action #6 (bank details in the creditors-aging response) intentionally NOT applied: the audit brief's checklist explicitly requires supplier bank details decrypted in the Creditors view data, so removing them would contradict the spec. Flag remains for the owner to decide.
- Legacy paid-formerly-partial POs from before receipt tracking still fall back to full-amount treatment everywhere (consistent across journal, P&L, backfill).
