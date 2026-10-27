import sys, datetime as dt
from starlette.testclient import TestClient
from tests.helpers import *
from database import User, Invoice, InvoiceStatus, Expense, Customer, Supplier
import auth as AU, journal as J

SKIP = ("/connect", "/callback", "/sync", "/oauth", "/export-all", "/backup")        # these call out to banks / third parties


def _seed():
    co = company("smoke", "general")
    u = User(company_id=co.id, first_name="S", last_name="M", email="smoke@x.com", hashed_password=AU.hash_password("Password123"),
             role="owner", is_active=True, email_verified=True)
    db.add(u); db.commit(); db.refresh(u)
    J.init_accounts(co.id, db)
    now = dt.datetime.utcnow()
    for n, st in (("S1", InvoiceStatus.sent), ("S2", InvoiceStatus.paid), ("S3", InvoiceStatus.partial), ("S4", InvoiceStatus.overdue), ("S5", InvoiceStatus.draft)):
        i = Invoice(company_id=co.id, invoice_number=n, client_name="Client " + n, amount=1000, vat_amount=150, total_amount=1150, status=st,
                    issue_date=now - dt.timedelta(days=40), due_date=now - dt.timedelta(days=10),
                    paid_date=now if st in (InvoiceStatus.paid, InvoiceStatus.partial) else None,
                    paid_amount_zar=1150 if st == InvoiceStatus.paid else (500 if st == InvoiceStatus.partial else None))
        db.add(i); db.commit(); db.refresh(i)
        if st != InvoiceStatus.draft:
            J.post_invoice_raised(i, db); db.commit()
    e = Expense(company_id=co.id, vendor="V", amount=230, vat_amount=30, category="Utilities", expense_date=now)
    db.add(e); db.commit(); db.refresh(e); J.post_expense(e, db); db.commit()
    db.add_all([Customer(company_id=co.id, name="Cust"), Supplier(company_id=co.id, name="Supp")]); db.commit()
    emp(co, "E1", 25000); run(co); 
    return co, u


def test_no_report_or_list_endpoint_crashes_for_a_company_with_data():
    co, u = _seed()
    sys.modules.pop("main", None)
    import main
    c = TestClient(main.app, raise_server_exceptions=False)
    h = {"Authorization": "Bearer " + AU.create_token({"user_id": u.id, "company_id": co.id})}
    crashes, calls = [], 0
    for path, ops in main.app.openapi()["paths"].items():
        if "get" not in ops or "{" in path or any(s in path for s in SKIP) or path in ("/", "/docs", "/openapi.json", "/redoc"):
            continue
        r = c.get(path, headers=h); calls += 1
        if r.status_code >= 500:
            crashes.append(f"{path} -> {r.status_code} {r.text[:160]}")
    assert calls > 80, calls
    assert not crashes, "\n".join(crashes)
