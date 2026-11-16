"""Monthly management report (2026-11-15): figures from the ledger, commentary, PDF, approve-and-send."""
import io, types, asyncio, json, datetime as dt
import pytest
from fastapi import UploadFile, HTTPException
from tests.helpers import *
from database import ManagementReport
import csv_import as CI
import management_report as MR

def _cu(co, role="accountant"):
    return types.SimpleNamespace(company_id=co.id, id=1, role=role, first_name="Soso", last_name="G", email="s@x.com")

def _journals(cu, text):
    return asyncio.run(CI.import_journals(file=UploadFile(filename="j.csv", file=io.BytesIO(text.encode())), db=db, cu=cu))

H = "Date,Reference,Description,Account Code,Account Name,Debit,Credit\n"

def _setup(name):
    co = company(name, "general"); co.financial_year_end = "02-28"; db.commit()
    cu = _cu(co)
    # last year Oct 2025: sales 800, purchases 500 ; this year Sep + Oct 2026; share capital; a loan; depreciation
    r = _journals(cu, H +
        "2025-10-15,A1,Sale,1010,Bank - current account,800,\n2025-10-15,A1,Sale,4000,Sales,,800\n"
        "2025-10-20,A2,Buy,5010,Purchases - Shop Stock,500,\n2025-10-20,A2,Buy,1010,Bank - current account,,500\n"
        "2026-03-01,B0,Capital,1010,Bank - current account,10000,\n2026-03-01,B0,Capital,3100,Share Capital,,1000\n"
        "2026-03-01,B0,Capital,2500,Long-Term Loan,,9000\n"
        "2026-09-10,B1,Sale,1100,Accounts Receivable,2000,\n2026-09-10,B1,Sale,4000,Sales,,2000\n"
        "2026-10-05,B2,Sale,1010,Bank - current account,3000,\n2026-10-05,B2,Sale,4000,Sales,,3000\n"
        "2026-10-06,B3,Buy,5010,Purchases - Shop Stock,1800,\n2026-10-06,B3,Buy,2005,Trade Payables,,1800\n"
        "2026-10-07,B4,Rent,6100,Rent,400,\n2026-10-07,B4,Rent,1010,Bank - current account,,400\n"
        "2026-10-08,B5,Interest,6700,Finance Costs (Interest Paid),100,\n2026-10-08,B5,Interest,1010,Bank - current account,,100\n"
        "2026-10-31,B6,Depreciation,5800,Depreciation Expense,50,\n2026-10-31,B6,Depreciation,1510,Accumulated Depreciation,,50\n"
        "2026-10-20,B7,Customer paid,1010,Bank - current account,1500,\n2026-10-20,B7,Customer paid,1100,Accounts Receivable,,1500\n")
    assert not r["errors"], r["errors"]
    from database import Account, AccountType
    a = db.query(Account).filter_by(company_id=co.id, code="5010").one(); a.type = AccountType.cogs; db.commit()   # as retyped on the trial balance
    return co, cu

def test_figures_month_ytd_comparatives_balance_sheet_and_cash_flow():
    co, cu = _setup("mrA")
    f = MR.build_figures(db, co, "2026-10")
    inc = f["income_statement"]
    assert inc["total_revenue"] == {"month": 3000, "month_py": 800, "ytd": 5000, "ytd_py": 800}
    assert inc["gross_profit"]["month"] == 1200 and inc["gross_profit"]["month_py"] == 300
    assert inc["total_finance_costs"]["month"] == 100                 # interest below operating profit
    assert inc["net_profit_before_tax"]["month"] == 3000 - 1800 - 400 - 50 - 100
    bs = f["balance_sheet"]
    assert bs["balanced"]
    cf = f["cash_flow"]["month"]
    assert cf["reconciles"] and cf["depreciation"] == 50
    assert cf["closing_cash"] - cf["opening_cash"] == cf["net_change"] == 3000 - 400 - 100 + 1500
    ytd = f["cash_flow"]["ytd"]
    assert ytd["reconciles"] and ytd["financing"] == 10000            # share capital + loan

def test_draft_save_pdf_and_send_flow(monkeypatch):
    co, cu = _setup("mrB")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = MR.make_commentary("2026-10", current_user=cu, db=db)
    assert out["commentary_source"] == "template" and "Revenue for October 2026" in out["commentary"]
    out = MR.save_report("2026-10", MR.ReportUpdate(commentary=out["commentary"] + "\nEdited.", recipients="ceo@client.co.za; cfo@client.co.za"),
                         current_user=cu, db=db)
    assert out["commentary_source"] == "edited" and out["recipients"] == "ceo@client.co.za, cfo@client.co.za"
    pdf = MR.report_pdf("2026-10", current_user=cu, db=db)
    assert pdf.body[:4] == b"%PDF" and len(pdf.body) > 2000
    sent = []
    import email_service
    monkeypatch.setattr(email_service, "send_email", lambda to, subject, html, attachments=None, **k: sent.append((to, attachments[0]["Name"])) or True)
    res = MR.send_report("2026-10", MR.SendRequest(), current_user=cu, db=db)
    assert res["status"] == "sent" and len(sent) == 2 and sent[0][1].endswith("2026_10.pdf")
    r = db.query(ManagementReport).filter_by(company_id=co.id, period="2026-10").one()
    assert json.loads(r.data_json)["income_statement"]["total_revenue"]["month"] == 3000
    with pytest.raises(HTTPException):                                 # locked once sent
        MR.save_report("2026-10", MR.ReportUpdate(commentary="x"), current_user=cu, db=db)
    MR.reopen_report("2026-10", current_user=cu, db=db)
    assert MR.save_report("2026-10", MR.ReportUpdate(commentary="fixed"), current_user=cu, db=db)["status"] == "draft"

def test_send_refuses_without_commentary_bad_email_or_open_month():
    co, cu = _setup("mrC")
    with pytest.raises(HTTPException):
        MR.send_report("2026-10", MR.SendRequest(recipients="ceo@client.co.za"), current_user=cu, db=db)   # no commentary
    with pytest.raises(HTTPException):
        MR.save_report("2026-10", MR.ReportUpdate(recipients="not-an-email"), current_user=cu, db=db)
    nxt = (dt.date.today().replace(day=1) + dt.timedelta(days=40)).strftime("%Y-%m")
    with pytest.raises(HTTPException):
        MR.send_report(nxt, MR.SendRequest(recipients="ceo@client.co.za"), current_user=cu, db=db)
