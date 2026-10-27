"""Shared fixtures for the scenario tests: a company/employee factory, a payroll runner and a journal-balance check."""
import types, asyncio, datetime as dt

import tests.conftest  # noqa: F401  (sets DATABASE_URL etc. before database.py is imported)
from database import Base, engine, SessionLocal, Company, Employee, Payslip, JournalEntry
import payroll as P, journal

Base.metadata.create_all(bind=engine)
db = SessionLocal()
now = dt.datetime.utcnow()


def company(name, industry):
    co = Company(name=name, email=f"{name}@x.com", industry=industry)
    db.add(co); db.commit(); db.refresh(co)
    journal.init_accounts(co.id, db)
    return co


def emp(co, no, sal, **kw):
    e = Employee(company_id=co.id, employee_number=no, first_name=no, last_name="T", gross_salary=sal, is_active=True,
                 pay_schedule=kw.pop("pay_schedule", "salaried"), employment_type=kw.pop("employment_type", "salaried"), **kw)
    db.add(e); db.commit(); db.refresh(e)
    return e


def run(co, **kw):
    req = P.RunPayrollRequest(**kw)
    return asyncio.run(P.run_payroll(data=req, current_user=types.SimpleNamespace(company_id=co.id), db=db))


def slip(e):
    return db.query(Payslip).filter_by(employee_id=e.id).order_by(Payslip.id.desc()).first()


def unbal(co):
    """Number of journal entries of this company whose debits and credits differ."""
    bad = 0
    for je in db.query(JournalEntry).filter_by(company_id=co.id).all():
        if abs(sum(l.debit or 0 for l in je.lines) - sum(l.credit or 0 for l in je.lines)) > 0.005:
            bad += 1
    return bad
