"""VAT201 picks up VAT that exists only in the ledger (2026-11-22).

A client that migrates from QuickBooks/Xero mid-month has no invoices or expense records for the part
of the month brought over as journals, so the VAT201 must read VAT posted by journal / general-ledger
imports and manual journals - without counting SARS payments, opening balances or native documents twice."""
import io, types, asyncio, datetime as dt
from fastapi import UploadFile
from tests.helpers import *
from database import Invoice, InvoiceStatus, Expense, Account, JournalEntry
import csv_import as CI, payroll as P, journal as J

H = "Date,Reference,Description,Account Code,Account Name,Debit,Credit\n"


def _co(name, journals=""):
    co = company(name, "general")
    cu = types.SimpleNamespace(company_id=co.id, id=1, role="accountant", first_name="S", last_name="G", email="s@x.com")
    J.init_accounts(co.id, db)
    if journals:
        r = asyncio.run(CI.import_journals(file=UploadFile(filename="j.csv", file=io.BytesIO((H + journals).encode())), db=db, cu=cu))
        assert not r["errors"], r["errors"]
    return co, cu


def _vat(co, period="2026-10", months=1):
    return asyncio.run(P.vat201(current_user=types.SimpleNamespace(company_id=co.id, id=1, role="owner"), db=db, period=period, months=months))


# Okwendalo-shaped month: fuel (zero-rated) and shop sales on one sales journal with output VAT,
# purchases with input VAT, a later correction, a SARS payment, interest received.
OCT = (
    "2026-10-31,S1,Sales per store reports,1150,Sales receipts clearing,1530000,\n"
    "2026-10-31,S1,Sales per store reports,4000,Fuel Sales,,1300000\n"
    "2026-10-31,S1,Sales per store reports,4010,Shop Sales,,200000\n"
    "2026-10-31,S1,Sales per store reports,2100,VAT Output (Payable to SARS),,30000\n"
    "2026-10-05,P1,Shop stock,5010,Purchases - Shop Stock,100000,\n"
    "2026-10-05,P1,Shop stock,1300,VAT Input (Recoverable),15000,\n"
    "2026-10-05,P1,Shop stock,1000,Bank / Cash,,115000\n"
    "2026-10-31,P2,PnP VAT correction,5010,Purchases - Shop Stock,500,\n"
    "2026-10-31,P2,PnP VAT correction,1300,VAT Input (Recoverable),,500\n"
    "2026-10-23,V1,SARS VAT payment,2100,VAT Output (Payable to SARS),9999,\n"
    "2026-10-23,V1,SARS VAT payment,1000,Bank / Cash,,9999\n"
    "2026-10-20,I1,Interest,1000,Bank / Cash,1200,\n"
    "2026-10-20,I1,Interest,4050,Interest Received,,1200\n"
    "2026-09-30,X1,September sale (other period),1000,Bank / Cash,115,\n"
    "2026-09-30,X1,September sale (other period),4010,Shop Sales,,100\n"
    "2026-09-30,X1,September sale (other period),2100,VAT Output (Payable to SARS),,15\n")


def test_imported_journals_fill_the_vat201():
    co, _ = _co("vj1", OCT)
    r = _vat(co)
    o, i = r["output"], r["input"]
    assert o["field_4a_output_vat"] == 30000 and o["journal_output_vat"] == 30000
    assert o["field_1a_standard_supplies_excl_vat"] == 200000
    assert o["field_1b_zero_rated_supplies"] == 1300000          # fuel: revenue above output VAT / 15%
    assert o["field_3_exempt_supplies"] == 1200                  # interest is exempt
    assert i["journal_input_vat"] == 14500 and i["field_14_input_vat"] == 14500   # 15,000 less the 500 correction
    assert r["net"]["field_15_net_vat"] == 15500                 # SARS payment ignored
    assert i["apportionment"]["ratio"] == 1.0                    # de minimis exempt supplies
    assert "journal entr" in i["note"]


def test_native_documents_and_journals_add_up_without_double_counting():
    co, _ = _co("vj2", OCT)
    db.add(Invoice(company_id=co.id, invoice_number="N1", client_name="C", amount=1000, vat_amount=150, total_amount=1150,
                   currency="ZAR", exchange_rate=1, status=InvoiceStatus.sent, issue_date=dt.datetime(2026, 10, 25)))
    db.add(Expense(company_id=co.id, vendor="V", amount=230, vat_amount=30, category="Office", expense_date=dt.datetime(2026, 10, 26)))
    db.commit()
    r = _vat(co)
    assert r["output"]["field_4a_output_vat"] == 30150 and r["output"]["journal_output_vat"] == 30000
    assert r["input"]["field_14_input_vat"] == 14530 and r["input"]["journal_input_vat"] == 14500


def test_no_journals_leaves_the_vat201_unchanged():
    co, _ = _co("vj3")
    r = _vat(co)
    assert r["output"]["journal_output_vat"] == 0 and r["input"]["journal_input_vat"] == 0 and r["input"]["journal_entries"] == 0
    assert "journal" not in r["input"]["note"]


def test_opening_balance_import_is_not_period_activity():
    co, cu = _co("vj4")
    up = UploadFile(filename="tb.csv", file=io.BytesIO(b"Code,Account Name,Type,Debit,Credit\n1000,Bank,Asset,5000,\n2100,VAT Output,Liability,,5000\n"))
    asyncio.run(CI.import_trial_balance(file=up, as_at="2026-10-15", replace=False, db=db, cu=cu))
    assert _vat(co)["output"]["field_4a_output_vat"] == 0


def test_combined_vat_account_is_read_by_sign():
    co, _ = _co("vj5",
        "2026-10-10,G1,Guarding services,1100,Accounts Receivable,11500,\n"
        "2026-10-10,G1,Guarding services,4000,Sales,,10000\n"
        "2026-10-10,G1,Guarding services,820,VAT,,1500\n"
        "2026-10-12,G2,Fuel,3620,Motor Vehicle Expenses - Fuel,1000,\n"
        "2026-10-12,G2,Fuel,820,VAT,150,\n"
        "2026-10-12,G2,Fuel,2000,Accounts Payable,,1150\n")
    r = _vat(co)
    assert r["output"]["field_4a_output_vat"] == 1500 and r["output"]["field_1a_standard_supplies_excl_vat"] == 10000
    assert r["output"]["field_1b_zero_rated_supplies"] == 0
    assert r["input"]["field_14_input_vat"] == 150


def test_reversed_journal_nets_to_nil_and_manual_journal_counts():
    co, _ = _co("vj6",
        "2026-10-10,M1,Sale,1000,Bank / Cash,1150,\n2026-10-10,M1,Sale,4010,Shop Sales,,1000\n"
        "2026-10-10,M1,Sale,2100,VAT Output (Payable to SARS),,150\n")
    e = db.query(JournalEntry).filter_by(company_id=co.id, reference="M1").one()
    J._post_reversal_for_entry(e, db, reason="posted in error", date=dt.datetime(2026, 10, 11)); db.commit()
    assert _vat(co)["output"]["field_4a_output_vat"] == 0
    acc = {a.code: a.id for a in db.query(Account).filter_by(company_id=co.id).all()}
    u = types.SimpleNamespace(company_id=co.id, id=1, role="owner")
    asyncio.run(J.create_manual_entry(J.ManualEntry(date="2026-10-28", description="Input VAT on supplier invoice missed",
        lines=[J.ManualEntryLine(account_id=acc["1300"], debit=45), J.ManualEntryLine(account_id=acc["2000"], credit=45)]),
        current_user=u, db=db))
    r = _vat(co)
    assert r["input"]["field_14_input_vat"] == 45 and r["input"]["journal_entries"] == 3   # sale, its reversal, the manual journal


def test_bi_monthly_period_includes_both_months():
    co, _ = _co("vj7", OCT)
    r = _vat(co, "2026-09", 2)
    assert r["output"]["field_4a_output_vat"] == 30015 and r["input"]["field_14_input_vat"] == 14500
