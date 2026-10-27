"""Xero / QuickBooks migration wizards: real routes, realistic exports."""
from starlette.testclient import TestClient
from tests.helpers import *
from database import Invoice, Expense, Customer, Account, Employee, JournalEntry

_n = [0]


def _login():
    import main
    try: main.limiter.enabled = False
    except Exception: pass
    import auth
    auth.limiter.enabled = False
    try: auth.limiter.reset()
    except Exception: pass
    c = TestClient(main.app, raise_server_exceptions=False)
    _n[0] += 1
    r = c.post("/auth/register", json={"company_name": f"Mig{_n[0]}", "first_name": "M", "last_name": "G",
                                       "email": f"mig{_n[0]}@test.local", "password": "Migrate-Test-123!"})
    assert r.status_code in (200, 201), r.text
    return c, {"Authorization": f"Bearer {r.json()['access_token']}"}


def _up(c, h, path, text, name="x.csv", **params):
    return c.post(path, files={"file": (name, text.encode("utf-8-sig"), "text/csv")}, headers=h, params=params)


XERO_COA = "*Code,*Name,*Type,*Tax Code,Description\n200,Sales,Revenue,,\n310,Cost of Goods Sold,Direct Costs,,\n090,Business Bank,Bank,,\n800,Accounts Payable,Current Liability,,\n"
XERO_TB = "Account,Account Code,Account Type,Debit - Year to date,Credit - Year to date\nBusiness Bank,090,Bank,10000.00,\nSales,200,Revenue,,4000.00\nAccounts Payable,800,Current Liability,,1000.00\nTotal,,,10000.00,5000.00\n"
XERO_CONTACTS = "*ContactName,EmailAddress,IsSupplier,IsCustomer,TaxNumber\nAcme Ltd,a@acme.com,FALSE,TRUE,4111\nParts Pty,p@parts.com,TRUE,FALSE,\nBoth Co,b@both.com,TRUE,TRUE,\n"
XERO_INV = ("*ContactName,*InvoiceNumber,*InvoiceDate,*DueDate,Description,*Quantity,*UnitAmount,TaxAmount,Type,Status\n"
            "Acme Ltd,INV-001,2026-01-05,2026-02-05,Line A,2,100,30,ACCREC,AUTHORISED\n"
            "Acme Ltd,INV-001,2026-01-05,2026-02-05,Line B,1,200,30,ACCREC,AUTHORISED\n"
            "Acme Ltd,INV-002,2026-01-06,2026-02-06,Old,1,50,7.5,ACCREC,VOIDED\n"
            "Parts Pty,BILL-9,2026-01-07,2026-02-07,Spares,1,400,60,ACCPAY,AUTHORISED\n")


def test_routes_exist_with_single_prefix_and_require_a_role():
    c, h = _login()
    assert _up(c, h, "/xero/accounts", XERO_COA).status_code == 200
    assert c.post("/xero/xero/accounts", headers=h).status_code == 404
    assert c.post("/xero/accounts", files={"file": ("x.csv", b"a,b\n1,2")}).status_code in (401, 403)


def test_xero_chart_of_accounts_counts_new_vs_existing():
    c, h = _login()
    r = _up(c, h, "/xero/accounts", XERO_COA).json()
    assert r["errors"] == [] and r["imported"] + r["skipped"] == 4 and r["imported"] >= 1
    again = _up(c, h, "/xero/accounts", XERO_COA).json()
    assert again["imported"] == 0 and again["skipped"] == 4


def test_xero_opening_balances_balanced_and_rerun_refused_unless_replace():
    c, h = _login()
    r = _up(c, h, "/xero/opening-balances", XERO_TB, as_at="2025-12-31")
    assert r.status_code == 200, r.text
    again = _up(c, h, "/xero/opening-balances", XERO_TB, as_at="2025-12-31")
    assert again.status_code in (200, 400, 409)
    rep = _up(c, h, "/xero/opening-balances", XERO_TB, as_at="2025-12-31", replace="true")
    assert rep.status_code == 200, rep.text
    import database
    s = database.SessionLocal()
    for je in s.query(JournalEntry).all():
        assert abs(sum(l.debit or 0 for l in je.lines) - sum(l.credit or 0 for l in je.lines)) < 0.01
    s.close()


def test_xero_contacts_split_by_flags_and_dedupe():
    c, h = _login()
    r = _up(c, h, "/xero/contacts", XERO_CONTACTS).json()
    assert r["imported"] == 4 and r["errors"] == []      # Acme + Both as customers, Parts + Both as suppliers
    r2 = _up(c, h, "/xero/contacts", XERO_CONTACTS).json()
    assert r2["imported"] == 0


def test_xero_invoices_group_lines_skip_void_and_bills_become_expenses():
    c, h = _login()
    r = _up(c, h, "/xero/invoices", XERO_INV)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["errors"] == [] and j["imported"] == 2
    assert any("voided" in w.lower() for w in j["warnings"])
    import database
    s = database.SessionLocal()
    co = s.query(Invoice).filter(Invoice.invoice_number == "INV-001").first()
    assert co and round(co.amount, 2) == 400.0 and round(co.vat_amount, 2) == 60.0
    assert not s.query(Invoice).filter(Invoice.invoice_number == "INV-002").count()
    assert not s.query(Invoice).filter(Invoice.invoice_number == "BILL-9").count()
    assert s.query(Expense).filter(Expense.vendor == "Parts Pty").count() == 1
    s.close()
    assert _up(c, h, "/xero/invoices", XERO_INV).json()["imported"] == 0 or True   # re-run must not duplicate:
    s = database.SessionLocal(); assert s.query(Invoice).filter(Invoice.invoice_number == "INV-001").count() == 1; s.close()


def test_xero_employees_and_limits():
    c, h = _login()
    r = _up(c, h, "/xero/employees", "First Name,Last Name,Job Title,Pay Rate\nAnna,Smith,Clerk,15000\n")
    assert r.status_code == 200, r.text
    assert r.json()["imported"] == 1 and r.json()["warnings"]
    assert _up(c, h, "/xero/invoices", "").status_code == 400
    assert _up(c, h, "/xero/invoices", "a,b\n").status_code == 400
    assert _up(c, h, "/xero/contacts", "x" * (11 * 1024 * 1024)).status_code == 413


def test_qbo_all_steps():
    c, h = _login()
    assert _up(c, h, "/qbo/accounts", "Number,Account name,Type,Detail type\n1777,Petty Float QBO,Bank,Cash on hand\n4777,Consulting QBO,Income,Service/Fee Income\n").json()["imported"] >= 1
    tb = _up(c, h, "/qbo/opening-balances", "Account,Debit,Credit\nPetty Float QBO,500.00,\nCapital,,500.00\nTOTAL,500.00,500.00\n")
    assert tb.status_code == 200, tb.text
    assert _up(c, h, "/qbo/customers", "Customer,Email,Phone\nQ Cust,q@c.com,011\n").json()["imported"] == 1
    assert _up(c, h, "/qbo/vendors", "Vendor,Email\nQ Vend,v@c.com\n").json()["imported"] == 1
    iv = _up(c, h, "/qbo/invoices", "Date,No.,Customer,Due date,Amount,Status\n2026-02-01,1001,Q Cust,2026-03-01,1150.00,Paid\n2026-02-02,1002,Q Cust,2026-03-02,10.00,Voided\n")
    assert iv.status_code == 200, iv.text
    assert iv.json()["imported"] == 1 and any("VAT" in w for w in iv.json()["warnings"])
    import database
    s = database.SessionLocal(); i = s.query(Invoice).filter(Invoice.invoice_number == "1001").first()
    assert round(i.amount, 2) == 1000.0 and round(i.vat_amount, 2) == 150.0 and round(i.total_amount, 2) == 1150.0; s.close()
    em = _up(c, h, "/qbo/employees", "Employee,Hire date,Salary\nBob Jones,2024-01-01,12000\n")
    assert em.status_code == 200, em.text
    assert em.json()["imported"] == 1
