"""One payroll price everywhere: billing, signup/payment estimates and payroll summaries use config.calc_payroll_monthly."""
import config, billing
from tests.helpers import *


def test_tiers_and_minimum():
    f = config.calc_payroll_monthly
    assert [f(n) for n in (0, 1, 2, 5, 10, 20, 40, 50)] == [0.0, 99.0, 108.0, 165.0, 230.0, 335.0, 545.0, 650.0]
    assert f(None) == 0.0 and f("3") == 127.0


def test_billing_uses_the_same_formula():
    assert billing.calc_payroll_monthly is config.calc_payroll_monthly


def test_no_other_per_employee_rates_left():
    import payroll, auth
    assert not hasattr(config, "PAYROLL_PER_EMP") and not hasattr(payroll, "PAYROLL_PER_EMP")
