"""
One-off correction: credit-note VAT used to be posted to 2200 (PAYE Payable) instead of 2100 (VAT Output).
Run in the backend Render Shell:   python fix_credit_note_vat_account.py          (dry run, changes nothing)
                                   python fix_credit_note_vat_account.py --apply  (moves the lines)
Only journal lines with source 'credit_note' on account 2200 are moved to that company's 2100.
"""
import sys
from database import SessionLocal, JournalEntry, JournalLine, Account
APPLY = "--apply" in sys.argv
db = SessionLocal()
rows = (db.query(JournalLine, JournalEntry, Account)
          .join(JournalEntry, JournalLine.entry_id == JournalEntry.id)
          .join(Account, JournalLine.account_id == Account.id)
          .filter(JournalEntry.source == "credit_note", Account.code == "2200").all())
print(f"{len(rows)} credit-note line(s) on 2200 found")
moved = 0
for ln, je, acc in rows:
    tgt = db.query(Account).filter(Account.company_id == je.company_id, Account.code == "2100").first()
    if not tgt:
        print(f"  skip entry {je.id} (company {je.company_id}): no 2100 account"); continue
    print(f"  entry {je.id} company {je.company_id} {je.reference}: debit {ln.debit} credit {ln.credit} -> 2100")
    if APPLY:
        ln.account_id = tgt.id; moved += 1
if APPLY:
    db.commit(); print(f"Moved {moved} line(s).")
else:
    print("Dry run only. Re-run with --apply to fix.")
db.close()
