"""
One-off reconciliation: repost historical Expense journal lines that were
misclassified before the 2026-09-18/09-19 expense_account() fixes.

Two distinct bugs, per reports_debtors_creditors_2026-09-27.md action item 2:
  1. Most DEFAULT_COA "{code} - {name}" picks didn't exist in the ledger at
     all pre-fix, so they silently fell back to 5900 General Expenses.
  2. Five DEFAULT_COA codes (5110-5150, all Cost-of-Sales items) collided
     with different-meaning ledger accounts (5110-5150 payroll-levy range).
     The frontend was renumbered to 5010-5050 going forward, but old stored
     Expense.category strings still read "5110 - Purchases" etc, and that
     code still resolves (today) to the real-but-wrong ledger account, so
     it is NOT self-correcting via expense_account() and needs an explicit
     remap.

This script is read-only unless run with --apply. In dry-run (default) it
only prints what it *would* change. Nothing is written to the database, no
Account rows are auto-vivified, in dry-run mode.
"""
import sys
from datetime import datetime

sys.path.insert(0, ".")
from database import SessionLocal, Expense, JournalEntry, JournalLine, Account
import journal as J

APPLY = "--apply" in sys.argv

# The five known collisions (audit fix 2026-09-19). Only remap when the
# stored name matches exactly what that DEFAULT_COA option used to be —
# never touch a code+name combination we don't recognise.
COLLISION_REMAP = {
    "5110": ("5010", "Purchases"),
    "5120": ("5020", "Freight and Delivery"),
    "5130": ("5030", "Import Duties"),
    "5140": ("5040", "Direct Labour"),
    "5150": ("5050", "Direct Materials"),
}


def parse_cat(cat):
    cat = (cat or "").strip()
    if " - " in cat:
        prefix, rest = cat.split(" - ", 1)
        prefix = prefix.strip()
        if prefix.isdigit():
            return prefix, rest.strip() or None
    return None, None


def target_code_name(code, name):
    """What expense_account() *should* resolve this to. For the 5 known
    collisions, remap explicitly (see module docstring). Otherwise trust the
    stored code+name as-is — expense_account() will find/create exactly that
    account, which is correct for every non-collision case."""
    if code in COLLISION_REMAP and COLLISION_REMAP[code][1] == name:
        return COLLISION_REMAP[code]
    return code, name


def main():
    db = SessionLocal()
    expenses = db.query(Expense).order_by(Expense.id).all()

    mismatches = []
    for e in expenses:
        code, name = parse_cat(e.category)
        if code is None:
            continue  # bare legacy category string — different code path (CATEGORY_TO_CODE), not this bug

        entry = (
            db.query(JournalEntry)
            .filter(JournalEntry.source == "expense", JournalEntry.source_id == e.id)
            .first()
        )
        if not entry:
            print(f"  [SKIP] Expense {e.id} ({e.category}): no 'expense' journal entry found — flag separately, not touched")
            continue

        line = (
            db.query(JournalLine)
            .join(Account, Account.id == JournalLine.account_id)
            .filter(JournalLine.entry_id == entry.id, JournalLine.debit > 0, Account.code != "1300")
            .first()
        )
        if not line:
            continue
        current_acct = db.query(Account).get(line.account_id)

        target_code, target_name = target_code_name(code, name)
        if current_acct.code != target_code:
            mismatches.append(dict(
                expense=e, entry=entry, line=line, current_acct=current_acct,
                target_code=target_code, target_name=target_name or name,
                net_amount=round(line.debit, 2),
            ))

    if not mismatches:
        print("No misclassified expense postings found. Nothing to do.")
        return

    print(f"{'ID':>4}  {'Company':>3}  {'Date':<10}  {'Vendor':<30}  {'Category (stored)':<30}  "
          f"{'Currently posted to':<28}  {'Should be':<28}  {'Net R':>10}")
    print("-" * 165)
    for m in mismatches:
        e = m["expense"]
        print(f"{e.id:>4}  {e.company_id:>3}  {str(e.expense_date)[:10]:<10}  {(e.vendor or '')[:30]:<30}  "
              f"{e.category[:30]:<30}  {m['current_acct'].code} - {m['current_acct'].name[:22]:<22}  "
              f"{m['target_code']} - {m['target_name'][:22]:<22}  {m['net_amount']:>10.2f}")

    total = round(sum(m["net_amount"] for m in mismatches), 2)
    by_target = {}
    for m in mismatches:
        k = f"{m['target_code']} - {m['target_name']}"
        by_target[k] = round(by_target.get(k, 0) + m["net_amount"], 2)

    print(f"\n{len(mismatches)} expense postings misclassified, totalling R{total:,.2f} moving off "
          f"'{mismatches[0]['current_acct'].code} - {mismatches[0]['current_acct'].name}' "
          f"(all currently 5900 unless noted otherwise above).")
    print("\nBreakdown of where it would move TO:")
    for k, v in sorted(by_target.items(), key=lambda x: -x[1]):
        print(f"  {k:<35} R{v:>10,.2f}")

    if not APPLY:
        print("\n[DRY RUN] No changes made. Re-run with --apply to post the reclassification journal entries.")
        db.close()
        return

    print("\n[APPLYING] Posting reclassification journal entries...")
    posted = 0
    for m in mismatches:
        e = m["expense"]
        # Resolve (and auto-vivify if needed) the correct target account via
        # the app's own expense_account() — same code path production uses,
        # so the created account is identical to what a fresh post today
        # would produce.
        target_cat_string = f"{m['target_code']} - {m['target_name']}"
        target_acct = J.expense_account(e.company_id, target_cat_string, db)

        reclass_entry = J._make_entry(
            e.company_id,
            datetime.utcnow(),
            f"Reclassification — {e.vendor}: corrected mis-posted category "
            f"'{e.category}' (was on {m['current_acct'].code} {m['current_acct'].name}, "
            f"audit fix 2026-09-18/19, one-off reconciliation {datetime.utcnow().date()})",
            f"RECLASS-EXP-{e.id}",
            "expense_reclass",
            e.id,
            db,
        )
        lines = [
            J._line(reclass_entry.id, target_acct, debit=m["net_amount"],
                    description=f"Reclass in — {e.category}"),
            J._line(reclass_entry.id, m["current_acct"], credit=m["net_amount"],
                    description=f"Reclass out — {e.category}"),
        ]
        J._assert_balanced(lines)
        for l in lines:
            db.add(l)
        posted += 1

    db.commit()
    print(f"Posted {posted} reclassification journal entries (source='expense_reclass'). Committed.")
    db.close()


if __name__ == "__main__":
    main()
