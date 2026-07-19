# ZuZan — IFRS for SMEs (Third Edition) Transition Plan
**Prepared:** 19 July 2026 (closes audit action item L4)
**Owner:** ZuZan AFS module (financial_statements.py + AFS views in App_js_fixed.js)

## 1. Applicability and timing

- The IASB issued the **third edition of the IFRS for SMEs Accounting Standard** in February 2025, effective for annual periods beginning **on or after 1 January 2027**, early application permitted.
- ZuZan companies use the SA financial year (1 March – 28/29 February). The first FY caught is the one **beginning 1 March 2027** (FY ending 29 Feb 2028). First third-edition AFS due out of ZuZan: **early 2028**.
- IFRS 18 does **not** apply — it is a full-IFRS standard; ZuZan prepares under IFRS for SMEs.
- Until adoption, the current (2015 second-edition) presentation remains correct. No code change is required before the FY2028 books open.

## 2. Key third-edition changes relevant to ZuZan

1. **Section 23 Revenue (rewritten, IFRS 15 five-step model)** — the biggest change. Revenue is recognised when control of goods/services transfers, per identified performance obligations. Impact: ZuZan recognises invoice revenue at issue date (point-in-time). For typical SME service/goods invoices this outcome is unchanged, but the **accounting policy note text must be rewritten** in five-step language, and deferred revenue handling (invoices raised in advance of delivery) should be reviewed.
2. **Section 2 (revised concepts, 2018 Conceptual Framework + fair value guidance aligned with IFRS 13)** — mainly affects policy-note wording; ZuZan uses cost models throughout, so measurement impact is nil.
3. **Section 9 consolidation (IFRS 10 control model)** and **Section 19 business combinations (IFRS 3 alignment)** — not applicable: ZuZan produces single-entity AFS.
4. **Expanded disclosures** (going concern, supplier finance-style arrangements) — review Note wording at implementation.
5. Impairment of financial assets stays on the simplified model — **no ECL implementation needed**.

## 3. ZuZan implementation checklist (target: Jan–Feb 2027)

| # | Change | Where |
|---|---|---|
| 1 | Update accounting-policies note: revenue policy in five-step wording; framework reference "IFRS for SMEs Accounting Standard (Third Edition, 2025)" | financial_statements.py notes builder; AFS meta string |
| 2 | Make the framework label year-aware: FYs beginning ≥ 1 Mar 2027 → third-edition wording; earlier FYs keep current wording (comparatives/re-runs of old years must not silently relabel) | financial_statements.py (`/annual` meta), App_js_fixed.js AFS header (currently "IFRS for SMEs — SA Financial Year") |
| 3 | Review deferred/unearned revenue: if customers are invoiced in advance, add a contract-liability line + note | journal.py `post_invoice_raised`, financial_statements.py |
| 4 | Re-check note disclosures against the third-edition disclosure list (going concern statement already present?) | financial_statements.py notes 2–9 |
| 5 | Transition disclosure in the first third-edition AFS (nature of changes; restate comparatives where required by the transition provisions) | financial_statements.py |
| 6 | Regression: prior-FY AFS re-runs must be unchanged | audit task |

## 4. Timeline

- **Now – Dec 2026:** no action; monitor SAICA/IASB guidance in the daily audit runs.
- **Jan–Feb 2027:** implement checklist items 1–5 behind the FY-start date switch (they activate automatically for FYs beginning ≥ 1 March 2027).
- **1 Mar 2027:** third-edition period begins; verify labels/notes switch correctly.
- **Early 2028:** first third-edition AFS produced; run a dedicated compliance pass.

## 5. Decision

Early adoption is **not recommended**: ZuZan's customers are small SA companies in testing/onboarding; adopting on the mandatory date keeps comparatives simple and matches what their accountants expect. Revisit in the early-2027 audit runs (standing reminder replaces open item L4).
