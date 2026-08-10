"""
ZuZan — Centralised configuration constants.
Import from here; never redefine these in individual modules.
"""

# Subscription plan prices (ZAR, incl VAT)
# Single source of truth — referenced by auth.py and payroll.py
PLAN_PRICES = {
    "starter":      {"monthly": 399,   "annual": 3990},
    "professional": {"monthly": 699,   "annual": 6990},
    "business":     {"monthly": 1299,  "annual": 12990},
}

# Payroll add-on pricing (price parity with SimplePay)
PAYROLL_PER_EMP = 18.25   # R per employee per month
PAYROLL_MIN     = 65.00   # Minimum payroll add-on fee
