import types, asyncio, datetime as dt
import pytest
from fastapi import HTTPException
from tests.helpers import *
from database import Expense, Invoice, InvoiceStatus
import journal as J, budgets as B


def _u(co): return types.SimpleNamespace(company_id=co.id, id=1)


def test_budget_input_validation_is_all_or_nothing():
    co = company("bud1", "general"); u = _u(co)
    ok = B.BudgetUpsert(year=2027, month=3, category="Rent", amount=5000)
    for bad in (dict(month=13), dict(month=0), dict(amount=-1), dict(type="profit"), dict(category=" "), dict(year=1999)):
        d = dict(year=2027, month=3, category="Rent", amount=10); d.update(bad)
        with pytest.raises(HTTPException) as ex:
            asyncio.run(B.upsert_budget(B.BudgetUpsert(**d), current_user=u, db=db))
        assert ex.value.status_code == 400, bad
    with pytest.raises(HTTPException):
        asyncio.run(B.bulk_upsert(B.BudgetBulkUpsert(entries=[ok, B.BudgetUpsert(year=2027, month=14, category="x", amount=1)]), current_user=u, db=db))
    assert asyncio.run(B.list_budgets(year=2027, current_user=u, db=db)) == []      # nothing saved from the bad batch
    asyncio.run(B.upsert_budget(ok, current_user=u, db=db)); asyncio.run(B.upsert_budget(ok, current_user=u, db=db))
    assert len(asyncio.run(B.list_budgets(year=2027, current_user=u, db=db))) == 1  # upsert, not duplicate


def test_actuals_exclude_vat_convert_currency_and_include_payroll():
    co = company("bud2", "general"); cid = co.id; u = _u(co)
    now = dt.datetime.utcnow(); y, m = now.year, now.month
    db.add(Expense(company_id=cid, vendor="V", amount=115, vat_amount=15, category="Office", expense_date=now)); db.commit()
    inv = Invoice(company_id=cid, invoice_number="U1", client_name="C", amount=100, vat_amount=0, total_amount=100, status=InvoiceStatus.paid,
                  issue_date=now, due_date=now, paid_date=now, currency="USD", exchange_rate=18.0, paid_amount_zar=1800)
    db.add(inv); db.commit()
    e = emp(co, "E1", 20000); run(co)
    s = slip(e)
    rows = asyncio.run(B.get_actuals(year=y, current_user=u, db=db))
    get = lambda t, c: sum(r["actual"] for r in rows if r["type"] == t and r["category"] == c)
    assert get("expense", "Office") == 100.0                       # ex VAT
    assert get("income", "Revenue") == 1800.0                      # USD invoice in rand, not 100
    assert abs(get("expense", "Salaries") - (s.total_cost or 0)) < 0.01 and get("expense", "Salaries") > 0
    summ = asyncio.run(B.get_summary(year=y, current_user=u, db=db))
    assert summ[s.generated_at.month - 1]["actual_expense"] >= 100 + get("expense", "Salaries") - 0.01
