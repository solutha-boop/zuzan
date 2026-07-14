"""
patch_backend.py — run by commit_and_push.bat before git add.

Applies fixes to backend Python files by reading, patching, and rewriting
them via Windows Python. This refreshes each file's mtime so git detects
the change, working around the OneDrive/mount mtime issue where edits made
through the Claude mount are not visible to git's stat cache.
"""

EFFECTIVE_STATUS_FN = '''

def effective_subscription_status(company) -> str:
    """
    Return the company's real subscription status.
    If the DB says 'expired' but trial_ends is still in the future,
    return 'trial'. Corrects stale status without a DB write at login time.
    """
    raw = company.subscription_status.value if company.subscription_status else "trial"
    if raw == "expired" and company.trial_ends and company.trial_ends > datetime.utcnow():
        return "trial"
    return raw
'''


def patch_auth():
    path = "zuzan-backend/auth.py"
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()

    # 1. Inject effective_subscription_status after TOKEN_EXPIRE_HOURS if missing
    if "effective_subscription_status" not in src:
        src = src.replace(
            "TOKEN_EXPIRE_HOURS = 24",
            "TOKEN_EXPIRE_HOURS = 24" + EFFECTIVE_STATUS_FN,
        )
        print("  [auth] added effective_subscription_status()")

    # 2. Replace all raw subscription_status returns with the helper
    old = "str(company.subscription_status.value)"
    new = "effective_subscription_status(company)"
    if old in src:
        count = src.count(old)
        src = src.replace(old, new)
        print(f"  [auth] replaced {count} subscription_status return(s)")

    # Always rewrite to refresh mtime so git detects the file as changed
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"  [auth] written")


def patch_main():
    path = "zuzan-backend/main.py"
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()

    # Update subscription gate to use effective_subscription_status
    old = "if company and company.subscription_status == SubscriptionStatus.expired:"
    new = (
        "from auth import effective_subscription_status\n"
        "                            if company and effective_subscription_status(company) == \"expired\":"
    )
    if old in src and "effective_subscription_status" not in src:
        src = src.replace(old, new)
        print("  [main] updated subscription gate to use effective_subscription_status()")

    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print("  [main] written")


if __name__ == "__main__":
    print("=== Applying backend patches ===")
    patch_auth()
    patch_main()
    print("=== Done ===")
