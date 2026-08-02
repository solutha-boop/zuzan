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


def patch_payroll():
    path = "zuzan-backend/payroll.py"
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    # Fix model string (2026-08-01)
    src = src.replace('model="claude-haiku-4-5",', 'model="claude-haiku-4-5-20251001",')
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print("  [payroll] model string fixed + written")


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


def patch_billing():
    path = "zuzan-backend/billing.py"
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    # Fix 1: guard resp before status_code check in adhoc_charge (2026-08-02)
    src = src.replace(
        "    try:\n        resp = _requests.post(url, data=body, headers=headers, timeout=30)",
        "    resp = None\n    try:\n        resp = _requests.post(url, data=body, headers=headers, timeout=30)",
    )
    src = src.replace(
        "    if resp.status_code == 200 and result.get(\"code\") == 200:",
        "    if resp and resp.status_code == 200 and result.get(\"code\") == 200:",
    )
    # Fix 2: decrypt PayFast credentials in afs_initiate (2026-08-02)
    src = src.replace(
        "    merchant_id  = co.payfast_merchant_id  or PAYFAST_MERCHANT_ID\n"
        "    merchant_key = co.payfast_merchant_key or PAYFAST_MERCHANT_KEY\n"
        "    passphrase   = co.payfast_passphrase   or PAYFAST_PASSPHRASE",
        "    merchant_id  = (decrypt_field(co.payfast_merchant_id)  if co.payfast_merchant_id  else None) or PAYFAST_MERCHANT_ID\n"
        "    merchant_key = (decrypt_field(co.payfast_merchant_key) if co.payfast_merchant_key else None) or PAYFAST_MERCHANT_KEY\n"
        "    passphrase   = (decrypt_field(co.payfast_passphrase)   if co.payfast_passphrase   else None) or PAYFAST_PASSPHRASE",
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print("  [billing] adhoc_charge NameError + afs_initiate decrypt fixed + written")


def patch_main_billing_loop():
    path = "zuzan-backend/main.py"
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    # Fix: add run_monthly_charges to the daily maintenance loop (2026-08-02)
    old = (
        "                from billing import check_trial_expirations, send_overdue_reminders\n"
        "                check_trial_expirations()\n"
        "                send_overdue_reminders()\n"
    )
    new = (
        "                from billing import check_trial_expirations, send_overdue_reminders, run_monthly_charges\n"
        "                check_trial_expirations()\n"
        "                send_overdue_reminders()\n"
        "                run_monthly_charges()\n"
    )
    if old in src:
        src = src.replace(old, new)
        print("  [main] added run_monthly_charges to daily loop")
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print("  [main] written")


if __name__ == "__main__":
    print("=== Applying backend patches ===")
    patch_auth()
    patch_main()
    patch_companies()
    patch_payroll()
    patch_billing()
    patch_main_billing_loop()
    print("=== Done ===")
