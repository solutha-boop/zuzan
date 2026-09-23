"""
Automated payroll <-> journal balance test.

WHY THIS FILE EXISTS
---------------------
Five times between 2026-07-15 and 2026-09-17, a new optional Payslip field
was added (a new payroll adjustment, allowance or deduction), wired into
calc_payroll()'s net_pay/taxable_gross formula, but NOT wired into
journal.post_payroll() — silently unbalancing every payroll run that used
the new field until an audit caught it (sometimes after the feature had
already shipped to production). See the 2026-09-18 audit report, action
item 2, for the incident history.

This script is the automated pre-merge check the audit repeatedly
recommended: it runs calc_payroll() + post_payroll() for one representative
employee across a battery of scenarios — each of the app's real optional
payroll fields turned on individually, plus one "kitchen sink" scenario with
everything on at once — and asserts every resulting journal entry balances
(sum of debits == sum of credits) to the cent.

HOW TO RUN
----------
    cd zuzan-backend
    python3 test_payroll_journal_balance.py

Uses a throwaway SQLite database (PAYROLL_TEST_DB_PATH, deleted before and
after the run) — never touches zuzan.db. Exits non-zero on any failure, so
it can be wired into CI / a pre-merge hook.

MAINTENANCE — READ THIS BEFORE ADDING A NEW PAYSLIP FIELD
-----------------------------------------------------------
If you add a new optional parameter to calc_payroll() that feeds into
net_pay or taxable_gross (a new allowance, deduction, levy, once-off item,
etc.), you MUST:
  1. Add a scenario for it below in SCENARIOS (or add it to the "kitchen
     sink" scenario if it composes cleanly with the others).
  2. Add its Payslip column name to TESTED_MONEY_FIELDS.
Running this script will otherwise still pass (it can only test what it
knows to test) — but the ACCOUNTED_FOR_FIELDS self-check below will fail
loudly if a new *_amount-shaped Float column shows up on Payslip that isn't
in either TESTED_MONEY_FIELDS or EXCLUDED_MONEY_FIELDS, forcing you to
classify it (and therefore notice the gap) before merging.
"""
import os
import sys

TEST_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_test_payroll_journal.db")

# Must be set before importing database.py (it reads DATABASE_URL at import time).
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"
os.environ.setdefault("SECRET_KEY", "test-secret-key-payroll-journal-balance-check")

if os.path.exists(TEST_DB_PATH):
    os.remove(TEST_DB_PATH)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import (  # noqa: E402
    Base, engine, SessionLocal, Company, Employee, Payslip,
    JournalEntry, JournalLine,
)
from payroll import calc_payroll, age_at_tax_year_end  # noqa: E402
import journal  # noqa: E402


# ── Static field-coverage self-check ────────────────────────────────────────
# Every Payslip column that represents a real money amount potentially posted
# to (or offset in) the journal must be classified below. This is the "grep
# new Payslip columns against post_payroll()'s field references" the audit
# recommended, expressed as a maintained allow-list instead of fragile
# source-text scraping.

TESTED_MONEY_FIELDS = {
    "overtime_amount", "sunday_amount", "ph_amount",
    "pension_employee", "pension_employer",
    "medical_aid_employee_ded", "medical_aid_employer_con",
    "night_shift_allowance", "special_allowance_amount", "cleaning_allowance",
    "bc_levy_employer", "psira_levy_employer",
    "annual_bonus",
    "mibco_med_allow", "mibco_scheme_employer", "mibco_scheme_employee",
    "nbcpss_provident_employee", "nbcpss_provident_employer",
    "nbcpss_medical_employee", "nbcpss_medical_employer",
    "uniform_allowance", "union_subscription_ded",
    "garnishee_total", "advance_deduction", "expense_claim",
    "once_off_deduction", "once_off_allowance_taxable", "once_off_allowance_nontaxable",
}

EXCLUDED_MONEY_FIELDS = {
    # Not a money amount — foreign key.
    "employee_id",
    # Base/always-present fields (not "optional" — every payslip has these,
    # and they're the anchors the balance equation is checked against, not
    # additional lines that could independently go unbalanced).
    "gross_salary", "paye", "uif_employee", "uif_employer", "sdl",
    "net_pay", "total_cost",
    # Hour/shift counts, not money (their *_amount / *_allowance counterparts
    # above are the actual money fields derived from them).
    "overtime_hours", "sunday_hours", "ph_hours", "normal_hours",
    "night_shift_shifts", "special_allowance_shifts",
    # s11F / medical tax credit bookkeeping — these affect the size of `paye`
    # itself (already covered), they are not separate DR/CR lines.
    "s11f_deduction", "s11f_excess", "s11f_carry_used", "medical_tax_credit",
}


def _payslip_float_columns():
    return {
        col.name for col in Payslip.__table__.columns
        if col.type.python_type in (float, int) and col.name != "id"
    }


def check_field_coverage():
    all_fields = _payslip_float_columns()
    classified = TESTED_MONEY_FIELDS | EXCLUDED_MONEY_FIELDS
    unclassified = all_fields - classified
    if unclassified:
        raise AssertionError(
            "New Payslip money field(s) found that aren't classified in "
            f"test_payroll_journal_balance.py: {sorted(unclassified)}. "
            "Add each to TESTED_MONEY_FIELDS (and a SCENARIOS entry that "
            "exercises it) if post_payroll() should post it, or to "
            "EXCLUDED_MONEY_FIELDS with a one-line reason if it's genuinely "
            "not a separate journal line. See the module docstring."
        )
    print(f"Field coverage OK — {len(all_fields)} Payslip money fields, "
          f"{len(TESTED_MONEY_FIELDS)} tested, {len(EXCLUDED_MONEY_FIELDS)} excluded by design.")


# ── Scenarios ────────────────────────────────────────────────────────────────
# Each scenario is a dict of calc_payroll() kwarg overrides on top of BASE.
# is_security / is_fuel_station gate several fields inside calc_payroll
# itself (see payroll.py), so scenarios that need those fields set the gate
# flags too.

BASE = dict(
    gross_monthly=15000.0,
    annual_payroll_total=15000.0 * 12 * 5,  # >= R500k so SDL applies
    overtime_hours=0, sunday_hours=0, ph_hours=0,
    pension_employee_pct=0.0, pension_employer_pct=0.0,
    medical_aid_employee=0.0, medical_aid_employer=0.0, medical_aid_dependants=0,
    night_shift_shifts=0.0, special_allowance_shifts=0.0,
    is_security=False, security_grade=None, security_area="3",
    annual_bonus=0.0, age=35,
    mibco_role=None, is_fuel_station=False, mibco_scheme_enrolled=False,
    union_subscription=0.0,
    on_maternity_leave=False, garnishee_total=0.0, advance_deduction=0.0,
    expense_claim=0.0, once_off_deduction=0.0,
    once_off_allowance_taxable=0.0, once_off_allowance_nontaxable=0.0,
)

SCENARIOS = {
    "baseline (nothing optional set)": {},
    "overtime (weekday/Sunday/PH)": dict(overtime_hours=10, sunday_hours=5, ph_hours=2),
    "pension (employee + employer)": dict(pension_employee_pct=0.075, pension_employer_pct=0.075),
    "medical aid": dict(medical_aid_employee=1500, medical_aid_employer=1500, medical_aid_dependants=2),
    "NBCPSS security bundle (night/special/cleaning/BC/PSIRA/provident/medical/uniform)": dict(
        is_security=True, security_grade="C", night_shift_shifts=4, special_allowance_shifts=2,
    ),
    "annual bonus": dict(annual_bonus=1200.0),
    "MIBCO fuel station bundle (med allow + scheme)": dict(
        is_fuel_station=True, mibco_role="cashier", mibco_scheme_enrolled=True,
    ),
    "union subscription": dict(union_subscription=150.0),
    "garnishee order": dict(garnishee_total=500.0),
    "salary advance deduction": dict(advance_deduction=800.0),
    "expense claim reimbursement": dict(expense_claim=350.0),
    "once-off deduction": dict(once_off_deduction=600.0),
    "once-off taxable allowance": dict(once_off_allowance_taxable=700.0),
    "once-off non-taxable allowance": dict(once_off_allowance_nontaxable=450.0),
    "maternity leave (gross zeroed)": dict(on_maternity_leave=True),
    "KITCHEN SINK — everything on at once": dict(
        overtime_hours=10, sunday_hours=5, ph_hours=2,
        pension_employee_pct=0.075, pension_employer_pct=0.075,
        medical_aid_employee=1500, medical_aid_employer=1500, medical_aid_dependants=2,
        is_security=True, security_grade="C", night_shift_shifts=4, special_allowance_shifts=2,
        annual_bonus=1200.0,
        is_fuel_station=True, mibco_role="cashier", mibco_scheme_enrolled=True,
        union_subscription=150.0,
        garnishee_total=500.0, advance_deduction=800.0, expense_claim=350.0,
        once_off_deduction=600.0, once_off_allowance_taxable=700.0,
        once_off_allowance_nontaxable=450.0,
    ),
}


def build_payslip(employee, c: dict) -> Payslip:
    """Mirror run_payroll()'s Payslip(**...) construction (payroll.py) field
    for field, so this test exercises exactly what production persists."""
    ot = c["overtime"]
    return Payslip(
        employee_id=employee.id,
        period="2026-09",
        gross_salary=c["gross"],
        paye=c["paye"],
        uif_employee=c["uif_employee"],
        uif_employer=c["uif_employer"],
        sdl=c["sdl"],
        net_pay=c["net_pay"],
        total_cost=c["total_cost"],
        overtime_hours=ot["overtime_hours"],
        overtime_amount=ot["overtime_amount"],
        sunday_hours=ot["sunday_hours"],
        sunday_amount=ot["sunday_amount"],
        ph_hours=ot["ph_hours"],
        ph_amount=ot["ph_amount"],
        pension_employee=c["pension_employee"],
        pension_employer=c["pension_employer"],
        s11f_deduction=c["s11f_deduction"],
        s11f_excess=c["s11f_excess_monthly"],
        s11f_carry_used=c["s11f_carry_used_monthly"],
        medical_aid_employee_ded=c["medical_aid_employee"],
        medical_aid_employer_con=c["medical_aid_employer"],
        medical_tax_credit=c["medical_tax_credit"],
        night_shift_shifts=c["night_shift_shifts"],
        night_shift_allowance=c["night_shift_allowance"],
        special_allowance_shifts=c["special_allowance_shifts"],
        special_allowance_amount=c["special_allowance_amount"],
        cleaning_allowance=c["cleaning_allowance"],
        bc_levy_employer=c["bc_levy_employer"],
        psira_levy_employer=c["psira_levy_employer"],
        normal_hours=c["normal_hours"],
        annual_bonus=c["annual_bonus"],
        mibco_med_allow=c["mibco_med_allow"],
        mibco_scheme_employer=c["mibco_scheme_employer"],
        mibco_scheme_employee=c["mibco_scheme_employee"],
        nbcpss_provident_employee=c["nbcpss_provident_employee"],
        nbcpss_provident_employer=c["nbcpss_provident_employer"],
        nbcpss_medical_employee=c["nbcpss_medical_employee"],
        nbcpss_medical_employer=c["nbcpss_medical_employer"],
        uniform_allowance=c["uniform_allowance"],
        union_subscription_ded=c["union_subscription_ded"],
        on_maternity_leave=c["on_maternity_leave"],
        garnishee_total=c["garnishee_total"],
        advance_deduction=c["advance_deduction"],
        expense_claim=c["expense_claim"],
        once_off_deduction=c["once_off_deduction"],
        once_off_allowance_taxable=c["once_off_allowance_taxable"],
        once_off_allowance_nontaxable=c["once_off_allowance_nontaxable"],
    )


def run():
    check_field_coverage()

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    company = Company(name="Payroll Balance Test Co", email="payrolltest@example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    employee = Employee(
        company_id=company.id, first_name="Test", last_name="Employee",
        gross_salary=15000.0, is_active=True,
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)

    journal.init_accounts(company.id, db)

    failures = []
    for name, overrides in SCENARIOS.items():
        kwargs = {**BASE, **overrides}
        c = calc_payroll(kwargs.pop("gross_monthly"), **kwargs)
        payslip = build_payslip(employee, c)
        db.add(payslip)
        db.flush()

        try:
            entry = journal.post_payroll(payslip, employee, db)
            db.flush()
        except Exception as e:
            failures.append((name, f"post_payroll() raised: {e}"))
            db.rollback()
            continue

        lines = db.query(JournalLine).filter(JournalLine.entry_id == entry.id).all()
        total_debit = round(sum(l.debit or 0 for l in lines), 2)
        total_credit = round(sum(l.credit or 0 for l in lines), 2)
        residual = round(total_debit - total_credit, 2)

        status = "PASS" if abs(residual) < 0.01 else "FAIL"
        print(f"[{status}] {name}: debit={total_debit:,.2f}  credit={total_credit:,.2f}  "
              f"residual={residual:+.2f}")
        if status == "FAIL":
            failures.append((name, f"unbalanced by {residual:+.2f} "
                                    f"(debit={total_debit:,.2f}, credit={total_credit:,.2f})"))

        db.commit()

    db.close()
    engine.dispose()
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)

    print()
    if failures:
        print(f"{len(failures)} scenario(s) FAILED:")
        for name, reason in failures:
            print(f"  - {name}: {reason}")
        sys.exit(1)
    else:
        print(f"All {len(SCENARIOS)} scenarios balanced. Payroll <-> journal integrity OK.")
        sys.exit(0)


if __name__ == "__main__":
    run()
