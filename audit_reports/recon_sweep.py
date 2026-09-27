"""ZuZan monthly reconciliation sweep — read-only checks against zuzan.db.

Usage: python recon_sweep.py <path-to-zuzan.db> [YYYY-MM-DD]
Prints JSON results per company to stdout. Opens the DB read-only.
"""
import json, sqlite3, sys
from datetime import datetime, date, timedelta

DB = sys.argv[1] if len(sys.argv) > 1 else "zuzan.db"
TODAY = datetime.strptime(sys.argv[2], "%Y-%m-%d").date() if len(sys.argv) > 2 else date.today()
TOL = 1.00

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
con.row_factory = sqlite3.Row
q = lambda sql, *a: con.execute(sql, a).fetchall()


def to_date(v):
    if v is None:
        return None
    return datetime.fromisoformat(str(v).replace("Z", "")[:26]).date() if len(str(v)) > 10 else date.fromisoformat(str(v))


def to_zar(inv):
    if inv["currency"] and inv["currency"] != "ZAR":
        if inv["paid_amount_zar"]:
            return inv["paid_amount_zar"]
        return (inv["total_amount"] or 0) * (inv["exchange_rate"] or 1.0)
    return inv["total_amount"] or 0


def acct_balance(acct_id, acct_type, source=None):
    """Mirror of journal.account_balance(); optional filter on entry source."""
    sql = ("SELECT COALESCE(SUM(l.debit),0) dr, COALESCE(SUM(l.credit),0) cr FROM journal_lines l "
           "JOIN journal_entries e ON e.id=l.entry_id WHERE l.account_id=?")
    args = [acct_id]
    if source:
        sql += " AND e.source=?"; args.append(source)
    r = q(sql, *args)[0]
    return round(r["dr"] - r["cr"], 2) if acct_type in ("asset", "expense") else round(r["cr"] - r["dr"], 2)


def run_company(cid, name):
    res = {"company_id": cid, "name": name}
    accts = q("SELECT id, code, name, type FROM accounts WHERE company_id=?", cid)
    je_count = q("SELECT COUNT(*) n FROM journal_entries WHERE company_id=?", cid)[0]["n"]
    res["journal_entries"] = je_count

    # Check 1 — balance sheet / trial balance equation
    tot = {t: 0.0 for t in ("asset", "liability", "equity", "revenue", "expense")}
    for a in accts:
        tot[a["type"]] += acct_balance(a["id"], a["type"])
    tot = {k: round(v, 2) for k, v in tot.items()}
    lhs = round(tot["asset"] + tot["expense"], 2)
    rhs = round(tot["liability"] + tot["equity"] + tot["revenue"], 2)
    # Assets − (Liabilities + Equity incl. current-period earnings)
    diff = round(tot["asset"] - (tot["liability"] + tot["equity"] + tot["revenue"] - tot["expense"]), 2)
    # Also flag unbalanced individual entries
    unbal = [dict(r) for r in q(
        "SELECT e.id, e.reference, e.source, ROUND(SUM(l.debit),2) dr, ROUND(SUM(l.credit),2) cr FROM journal_entries e "
        "JOIN journal_lines l ON l.entry_id=e.id WHERE e.company_id=? GROUP BY e.id HAVING ABS(SUM(l.debit)-SUM(l.credit))>0.005", cid)]
    # Lines posted to accounts owned by another company
    cross = q("SELECT COUNT(*) n FROM journal_lines l JOIN journal_entries e ON e.id=l.entry_id "
              "JOIN accounts a ON a.id=l.account_id WHERE e.company_id=? AND a.company_id<>?", cid, cid)[0]["n"]
    res["c1"] = {"totals": tot, "debit_normal": lhs, "credit_normal": rhs, "imbalance": diff,
                 "unbalanced_entries": unbal, "cross_company_lines": cross,
                 "pass": abs(diff) <= TOL}

    # Check 2 — AR control 1100
    ar = next((a for a in accts if a["code"] == "1100"), None)
    invs = q("SELECT * FROM invoices WHERE company_id=? AND status IN ('sent','overdue')", cid)
    inv_total = round(sum(to_zar(i) for i in invs), 2)
    ar_bal = acct_balance(ar["id"], ar["type"]) if ar else None
    ar_import = acct_balance(ar["id"], ar["type"], "import") if ar else 0.0
    ar_diff = round((ar_bal or 0) - inv_total, 2)
    res["c2"] = {"account_exists": ar is not None, "journal_balance": ar_bal, "import_portion": ar_import,
                 "invoice_total": inv_total, "diff": ar_diff,
                 "invoices": [{"id": i["id"], "number": i["invoice_number"], "zar": round(to_zar(i), 2)} for i in invs],
                 "pass": abs(ar_diff) <= TOL}

    # Check 3 — AP control 2000
    ap = next((a for a in accts if a["code"] == "2000"), None)
    pos = q("SELECT * FROM purchase_orders WHERE company_id=? AND status IN ('received','partial')", cid)
    po_total = round(sum(p["total_amount"] or 0 for p in pos), 2)
    ap_bal = acct_balance(ap["id"], ap["type"]) if ap else None
    ap_import = acct_balance(ap["id"], ap["type"], "import") if ap else 0.0
    credit_exp = round(q("SELECT COALESCE(SUM(amount),0) s FROM expenses WHERE company_id=? AND is_on_credit=1 AND paid_at IS NULL", cid)[0]["s"], 2)
    ap_diff = round((ap_bal or 0) - po_total, 2)
    res["c3"] = {"account_exists": ap is not None, "journal_balance": ap_bal, "import_portion": ap_import,
                 "po_total": po_total, "unpaid_credit_expenses": credit_exp, "diff": ap_diff,
                 "pos": [{"id": p["id"], "number": p["po_number"], "total": p["total_amount"]} for p in pos],
                 "pass": abs(ap_diff) <= TOL}

    # Check 4 — overdue AR > 90 days
    cutoff = TODAY - timedelta(days=90)
    od = []
    for i in invs:
        dd = to_date(i["due_date"])
        if dd and dd < cutoff:
            od.append({"id": i["id"], "client": i["client_name"], "number": i["invoice_number"],
                       "currency": i["currency"], "zar": round(to_zar(i), 2), "due": str(dd),
                       "days": (TODAY - dd).days})
    res["c4"] = od

    # Check 5 — open POs > 60 days
    cutoff = TODAY - timedelta(days=60)
    st = []
    for p in pos:
        rd = to_date(p["received_date"])
        if rd and rd < cutoff:
            st.append({"id": p["id"], "supplier": p["supplier_name"], "number": p["po_number"],
                       "total": p["total_amount"], "received": str(rd), "days": (TODAY - rd).days})
    res["c5"] = st

    # Check 6 — negative inventory
    res["c6"] = [dict(r) for r in q(
        "SELECT id, sku, name, quantity_on_hand, is_active FROM inventory WHERE company_id=? AND quantity_on_hand<0", cid)]

    fails = not (res["c1"]["pass"] and res["c2"]["pass"] and res["c3"]["pass"]) or bool(res["c6"])
    warns = bool(od or st)
    res["overall"] = "FAIL" if fails else ("WARN" if warns else "PASS")
    return res


meta = {"db": DB, "today": str(TODAY),
        "last_journal_entry": q("SELECT MAX(created_at) m FROM journal_entries")[0]["m"],
        "last_invoice": q("SELECT MAX(created_at) m FROM invoices")[0]["m"]}
out = {"meta": meta, "companies": [run_company(r["id"], r["name"]) for r in q("SELECT id, name FROM companies ORDER BY id")]}
print(json.dumps(out, indent=2, default=str))
