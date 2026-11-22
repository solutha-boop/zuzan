"""Regression: /companies/clear-data with "employees" crashed with a 500 (the
browser shows "Failed to fetch") on any company that had run payroll, because
it called _del(db, Payslip, cid) and Payslip has no company_id column."""
import asyncio
import datetime as dt
import types

from tests.helpers import db, company, emp, run
from database import Employee, Payslip, JournalEntry
import companies


def test_clear_employees_after_payroll_run():
    co = company("ClearPayrollCo", "general")
    e1 = emp(co, "CP1", 30000)
    e2 = emp(co, "CP2", 18000)
    ids = [e1.id, e2.id]
    run(co, period=dt.date.today().strftime("%Y-%m"))
    assert db.query(Payslip).filter(Payslip.employee_id.in_(ids)).count() == 2

    res = asyncio.run(companies.clear_company_data(
        req=companies.ClearDataRequest(categories=["employees"], confirm=True),
        current_user=types.SimpleNamespace(company_id=co.id, id=0),
        db=db,
    ))

    assert res["cleared"] == ["employees"]
    assert db.query(Employee).filter_by(company_id=co.id).count() == 0
    assert db.query(Payslip).filter(Payslip.employee_id.in_(ids)).count() == 0
    assert db.query(JournalEntry).filter(
        JournalEntry.company_id == co.id,
        JournalEntry.source.in_(["payroll", "payroll_reversal"]),
    ).count() == 0
