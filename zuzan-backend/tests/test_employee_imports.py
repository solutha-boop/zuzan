import io, types, asyncio
from fastapi import UploadFile
from tests.helpers import *
from database import Employee
import csv_import as CI


def _up(text):
    return UploadFile(filename="x.csv", file=io.BytesIO(text.encode("utf-8")))


def _setup(name):
    co = company(name, "general")
    return co, types.SimpleNamespace(company_id=co.id, id=1, role="owner")


def _emps(cu, csv):
    return asyncio.run(CI.import_employees(file=_up(csv), db=db, cu=cu))


def _adj(cu, csv):
    return asyncio.run(CI.import_payroll_adjustments(file=_up(csv), db=db, cu=cu))


def _get(co, no):
    db.expire_all()
    return db.query(Employee).filter_by(company_id=co.id, employee_number=no).one()


def test_employee_import_numbers_decimal_comma_percent_and_bad_values():
    co, cu = _setup("empA")
    r = _emps(cu, "Employee Number,First Name,Last Name,Gross Salary,Pension Employee Pct\n"
                  "E1,Ann,Able,\"12 345,67\",7.5%\n"
                  "E2,Bob,Baker,twelve thousand,\n"
                  "E3,Cy,Cole,15000,abc\n")
    assert r["created"] == 1 and len(r["errors"]) == 1 + 1
    e = _get(co, "E1")
    assert e.gross_salary == 12345.67 and e.pension_fund_employee_pct == 7.5
    assert db.query(Employee).filter_by(company_id=co.id).count() == 1


def test_employee_import_never_overwrites_a_namesake_with_a_different_id():
    co, cu = _setup("empB")
    _emps(cu, "Employee Number,ID Number,First Name,Last Name,Gross Salary\nE1,8001015009087,Sam,Smith,10000\n")
    r = _emps(cu, "Employee Number,ID Number,First Name,Last Name,Gross Salary\nE9,9202204720082,Sam,Smith,20000\n")
    assert r["created"] == 1
    assert _get(co, "E1").gross_salary == 10000 and _get(co, "E9").gross_salary == 20000
    r = _emps(cu, "ID Number,First Name,Last Name,Gross Salary\n123,Zed,Zulu,9000\n")
    assert any("13-digit" in w["message"] for w in r["warnings"])


def test_payroll_adjustments_blank_cells_do_not_zero_pay_and_zero_is_allowed():
    co, cu = _setup("empC")
    _emps(cu, "Employee Number,First Name,Last Name,Gross Salary,Medical Aid Employee,Medical Aid Dependants\n"
              "E1,Ann,Able,10000,500,2\nE2,Bob,Baker,20000,0,0\n")
    r = _adj(cu, "Employee Number,New Salary,Medical Aid Employee,Dependants\n"
                 "E1,,0,\n"                     # salary blank = unchanged; medical set to a deliberate 0; dependants blank
                 "E2,21000,,\n")
    assert r["imported"] == 2 and not r["errors"]
    e1, e2 = _get(co, "E1"), _get(co, "E2")
    assert e1.gross_salary == 10000 and e1.medical_aid_employee == 0 and e1.medical_aid_dependants == 2
    assert e2.gross_salary == 21000
    r = _adj(cu, "Employee Number,New Salary\nE1,-5\nE2,0\nE1,\"1 234,50\"\n")
    assert len(r["errors"]) == 2 and _get(co, "E1").gross_salary == 1234.5 and _get(co, "E2").gross_salary == 21000
