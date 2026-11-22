"""Regression: /companies/clear-data with "employees" failed (500, which the
browser reports as "Failed to fetch") because employee_benefits rows still
referenced the employees being deleted. Every table with a foreign key to
employees.id must be cleared in the employees block before Employee itself."""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _models_referencing_employees():
    src = (ROOT / "database.py").read_text(encoding="utf-8").split("\n")
    names = set()
    for i, line in enumerate(src):
        if re.search(r"ForeignKey\(['\"]employees\.id['\"]\)", line):
            j = i
            while not src[j].startswith("class "):
                j -= 1
            names.add(re.match(r"class (\w+)", src[j]).group(1))
    return names


def test_employees_clear_removes_every_child_table():
    src = (ROOT / "companies.py").read_text(encoding="utf-8")
    start = src.index('if "employees" in cats:')
    end = src.index("_del(db, Employee, cid)", start)
    block = src[start:end]
    children = _models_referencing_employees()
    assert "EmployeeBenefit" in children
    missing = sorted(m for m in children if m not in block)
    assert not missing, f"clear-data leaves rows that block deleting employees: {missing}"
