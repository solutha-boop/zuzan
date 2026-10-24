"""Regression tests for the 2026-10-24 audit follow-ups: EMP201 submission lock, per-line SAVEPOINT in bank import,
provisional tax netted in the AFS tax line."""
import types, asyncio, datetime as dt
import pytest
from fastapi import HTTPException
from tests.helpers import *
from database import Invoice, InvoiceStatus, Account, JournalLine
import journal as J, financial_statements as FS, companies as CO, payroll as P


def _bal(cid, code):
    a = db.query(Account).filter_by(company_id=cid, code=code).first()
    return round(sum((l.debit or 0) - (l.credit or 0) for l in db.query(JournalLine).filter_by(account_id=a.id)), 2)


def test_emp201_submission_blocks_payslip_delete_until_withdrawn():
    co = company("emp201lock", "general"); cid = co.id
    e = emp(co, "E1", 20000)
    run(co)
    period = slip(e).period
    user = types.SimpleNamespace(company_id=cid, id=1, role="owner")
    r = asyncio.run(P.emp201_mark_submitted(period, P.Emp201SubmitRequest(reference="REF1"), current_user=user, db=db))
    assert r["submitted"] is True
    assert asyncio.run(P.emp201(current_user=user, db=db, period=period))["submitted"] is True
    with pytest.raises(HTTPException) as ex:
        asyncio.run(P.delete_payroll_period(period, current_user=user, db=db))
    assert ex.value.status_code == 409
    asyncio.run(P.emp201_withdraw_submission(period, current_user=user, db=db))
    out = asyncio.run(P.delete_payroll_period(period, current_user=user, db=db))
    assert out["deleted"] == 1


def _profit_company(name):
    co = company(name, "general"); cid = co.id
    user = types.SimpleNamespace(company_id=cid, id=1, role="owner")
    i = Invoice(company_id=cid, invoice_number="A", client_name="C", amount=10000, vat_amount=0, total_amount=10000,
                status=InvoiceStatus.sent, issue_date=dt.datetime(2025, 6, 10), due_date=dt.datetime(2025, 6, 10))
    db.add(i); db.commit(); db.refresh(i); J.post_invoice_raised(i, db); db.commit()
    i.status = InvoiceStatus.paid; i.paid_date = dt.datetime(2025, 6, 20); i.paid_amount_zar = 10000; db.commit()
    J.post_invoice_paid(i, db); db.commit()
    return co, user


def _pay_provisional(cid, amount):
    en = J._make_entry(cid, dt.datetime(2025, 9, 1), "Provisional tax paid", "IRP6", "manual", None, db)
    lines = [J._line(en.id, J.get_account(cid, "2127", db), debit=amount), J._line(en.id, J.get_account(cid, "1000", db), credit=amount)]
    for l in lines: db.add(l)
    db.commit()


def test_provisional_tax_netted_against_income_tax_payable():
    co, user = _profit_company("provnet"); _pay_provisional(co.id, 1000)
    bs = FS.annual_financial_statements(year=2026, db=db, current_user=user)["balance_sheet"]
    assert bs["balanced"]
    cl = bs["current_liabilities"] if "current_liabilities" in bs else bs["liabilities"]["current"]
    assert not any(l["code"] == "2127" for l in cl)
    assert [l["amount"] for l in cl if l["code"] == "2400"] == [1700.0]       # 27% x 10 000 - 1 000


def test_provisional_tax_exceeding_estimate_becomes_receivable():
    co, user = _profit_company("provrec"); _pay_provisional(co.id, 5000)
    bs = FS.annual_financial_statements(year=2026, db=db, current_user=user)["balance_sheet"]
    assert bs["balanced"]
    s = str(bs)
    assert "Income Tax Receivable" in s and "'2400'" not in s


def test_bank_import_bad_line_rolls_back_alone(monkeypatch):
    co = company("bksp", "general"); cid = co.id
    user = types.SimpleNamespace(company_id=cid, id=1, role="owner")
    real = J.post_bank_income
    def flaky(company_id, txn, session):
        if "BAD" in txn.description:
            real(company_id, txn, session)                  # post, then fail -> savepoint must undo the partial posting
            raise RuntimeError("boom")
        return real(company_id, txn, session)
    monkeypatch.setattr(J, "post_bank_income", flaky)
    today = dt.date.today().isoformat(); T = CO.BankTransaction
    r = asyncio.run(CO.import_bank_statement(CO.BankImportRequest(bank="fnb", transactions=[
        T(date=today, description="GOOD ONE", amount=100, type="credit"),
        T(date=today, description="BAD ONE", amount=200, type="credit"),
        T(date=today, description="GOOD TWO", amount=300, type="credit")]), current_user=user, db=db))
    assert r["credits_recorded"] == 2 and len(r["failed"]) == 1 and r["failed"][0]["description"] == "BAD ONE"
    assert _bal(cid, "1000") == 400                          # only the two good lines hit the bank; the bad one left nothing behind
    assert unbal(co) == 0
