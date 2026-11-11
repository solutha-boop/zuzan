"""
READ-ONLY check: lists accounts whose password is the old default "Zuzan2025".
Changes nothing and never prints any password.

Run it where the backend can reach the database, e.g. in the Render Shell tab
of the zuzan-backend service:   python find_default_password_accounts.py
"""
from database import SessionLocal, User
from auth import pwd_context

BAD = ["Zuzan2025"]

db = SessionLocal()
hits = []
total = 0
for u in db.query(User).all():
    total += 1
    if not u.hashed_password:
        hits.append((u.id, u.email, "NO PASSWORD SET"))
        continue
    for pw in BAD:
        try:
            if pwd_context.verify(pw, u.hashed_password):
                hits.append((u.id, u.email, "uses the default password"))
                break
        except Exception:
            pass
print(f"Checked {total} accounts.")
if not hits:
    print("None found - no account uses the default password.")
for i, e, why in hits:
    print(f"  user id {i}: {e}  ->  {why}")
if hits:
    print("\nFix: use 'Forgot password' for each of these, or ask the owner to change it.")
