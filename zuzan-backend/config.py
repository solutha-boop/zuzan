"""
ZuZan — Centralised configuration constants.
Import from here; never redefine these in individual modules.
"""

# Subscription plan prices (ZAR, incl VAT)
# Single source of truth — referenced by auth.py and payroll.py
PLAN_PRICES = {
    "starter":      {"monthly": 399,   "annual": 3990},
    "professional": {"monthly": 699,   "annual": 6990},
    "business":     {"monthly": 999,   "annual": 9990},
}

# Payroll add-on pricing
PAYROLL_MIN     = 99.00   # Minimum payroll add-on fee


def calc_payroll_monthly(emp_count) -> float:
    """The ONE payroll add-on price (ZAR/month, ex VAT): tiered, with a R99 minimum. Used for billing, estimates and screens.

        1 employee    R89 base            -> R99 (minimum applies)
        employees 2-5   R19.00 each
        employees 6-10  R13.00 each
        employees 11+   R10.50 each
        e.g. 10 employees R230, 20 employees R335, 40 employees R545
    """
    n = int(emp_count or 0)
    if n <= 0:
        return 0.0
    cost = 89.00
    remaining = n - 1
    t2 = min(remaining, 4); cost += t2 * 19.00; remaining -= t2
    t3 = min(remaining, 5); cost += t3 * 13.00; remaining -= t3
    cost += remaining * 10.50
    return round(max(PAYROLL_MIN, cost), 2)
