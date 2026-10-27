import io, types, asyncio, datetime as dt
import pytest
from fastapi import UploadFile
from tests.helpers import *
from database import Invoice, InvoiceStatus, Expense
import csv_import as CI


@pytest.mark.parametrize("raw,expected", [
    ("1234.56", 1234.56), ("1,234.56", 1234.56), ("R 1 234.56", 1234.56), ("1 234,56", 1234.56), ("1234,56", 1234.56),
    ("12,5", 12.5), ("1,234", 1234.0), ("1,234,567", 1234567.0), ("1.234.567,89", 1234567.89),
    ("(500.00)", -500.0), ("500.00-", -500.0), ("-R500", -500.0), ("R-500", -500.0), ("ZAR 99.10", 99.10),
    ("1 234,50", 1234.50), ("", 0.0), (None, 0.0), ("abc", 0.0), ("  ", 0.0),
])
def test_amounts_parse_correctly(raw, expected):
    assert CI._parse_float(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("2026-03-01", dt.datetime(2026, 3, 1)), ("01/03/2026", dt.datetime(2026, 3, 1)), ("13/03/2026", dt.datetime(2026, 3, 13)),
    ("03/13/2026", dt.datetime(2026, 3, 13)), ("1 Mar 2026", dt.datetime(2026, 3, 1)), ("01.03.2026", dt.datetime(2026, 3, 1)),
    ("01/03/26", dt.datetime(2026, 3, 1)), ("2026-03-01 00:00:00", dt.datetime(2026, 3, 1)), ("20260301", dt.datetime(2026, 3, 1)),
    ("Mar 1, 2026", dt.datetime(2026, 3, 1)),
])
def test_dates_parse_correctly(raw, expected):
    assert CI._parse_date(raw) == expected
    assert CI._parse_date("not a date") is None


def test_statuses():
    P = CI._parse_status
    assert P("Paid") == InvoiceStatus.paid and P("OPEN") == InvoiceStatus.sent and P("Authorised") == InvoiceStatus.sent
    assert P("Void") == InvoiceStatus.draft and P("Cancelled") == InvoiceStatus.draft and P("Overdue") == InvoiceStatus.overdue


def _up(text, name="x.csv"):
    return UploadFile(file=io.BytesIO(text.encode("utf-8")), filename=name)


def test_single_column_file_does_not_crash_the_reader():
    h, rows = CI._read_csv(b"Client\nAcme\nBeta\n")
    assert h == ["Client"] and len(rows) == 2


def test_invoice_import_is_not_doubled_and_bad_dates_are_reported():
    co = company("csvinv", "general"); cu = types.SimpleNamespace(company_id=co.id, id=1, role="owner")
    csv = ("Invoice Number,Client Name,Date,Total,VAT,Status\n"
           "A-1,Acme,2026-03-01,\"1 150,00\",150,Paid\n"
           "A-2,Beta,not-a-date,500,0,Sent\n"
           "A-3,Gamma,2026-03-05,230,30,Open\n")
    r1 = asyncio.run(CI.import_invoices(file=_up(csv), db=db, cu=cu))
    assert r1["imported"] == 2 and any("A-2" in e["message"] for e in r1["errors"])
    a1 = db.query(Invoice).filter_by(company_id=co.id, invoice_number="A-1").one()
    assert a1.total_amount == 1150 and a1.amount == 1000 and a1.status == InvoiceStatus.paid
    r2 = asyncio.run(CI.import_invoices(file=_up(csv), db=db, cu=cu))                 # the same file again
    assert r2["imported"] == 0
    assert db.query(Invoice).filter_by(company_id=co.id).count() == 2
    assert unbal(co) == 0


def test_expense_import_skips_rows_already_in_the_books_but_keeps_genuine_repeats():
    co = company("csvexp", "general"); cu = types.SimpleNamespace(company_id=co.id, id=1, role="owner")
    csv = "Vendor,Amount,VAT,Date,Category\nShell,115.00,15.00,2026-03-02,Fuel\nShell,115.00,15.00,2026-03-02,Fuel\nEskom,500,0,2026-03-03,Utilities\nBad,10,0,31-31-2026,Other\n"
    r1 = asyncio.run(CI.import_expenses(file=_up(csv), db=db, cu=cu))
    assert r1["imported"] == 3 and any("recognised format" in e["message"] for e in r1["errors"])   # two identical fuel stops are both real
    r2 = asyncio.run(CI.import_expenses(file=_up(csv), db=db, cu=cu))
    assert r2["imported"] == 0
    assert db.query(Expense).filter_by(company_id=co.id).count() == 3
