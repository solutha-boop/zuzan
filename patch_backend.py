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

    # Disable subscription gate until PayFast is live and DB statuses are reliable.
    # The gate was causing Demo Mode for valid trial accounts due to stale DB status.
    old = "app.add_middleware(_SubscriptionGateMiddleware)"
    new = "# app.add_middleware(_SubscriptionGateMiddleware)  # disabled — re-enable when PayFast live"
    if old in src:
        src = src.replace(old, new)
        print("  [main] disabled subscription gate middleware")

    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print("  [main] written")


def patch_companies():
    path = "zuzan-backend/companies.py"
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    # Ensure plan and billing_cycle fields are in CompanyUpdate (fix 2026-08-01)
    if "plan:                   Optional[str] = None" not in src:
        src = src.replace(
            "    # User-initiated subscription transitions only — guarded in update_company.",
            "    # Plan / billing cycle — user can switch plan at any time.\n"
            "    plan:                   Optional[str] = None\n"
            "    billing_cycle:          Optional[str] = None\n"
            "    # User-initiated subscription transitions only — guarded in update_company.",
        )
        print("  [companies] added plan + billing_cycle to CompanyUpdate")
    # Always rewrite to refresh mtime
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print("  [companies] written")


if __name__ == "__main__":
    print("=== Applying backend patches ===")
    patch_auth()
    patch_main()
    patch_companies()
    print("=== Done ===")
