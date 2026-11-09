"""POST /import/payments: part payments, full payments, dates, duplicates, dry run, refusals."""
import sys, io, types, asyncio, datetime as dt
from starlette.testclient import TestClient
from tests.helpers import *
from database import Invoice, InvoiceStatus, User, JournalEntry, JournalLine, Account
import auth as AU
import companies as CO


def _client():
    sys.modules.pop("main", None)
    import main
    return TestClient(main.app, raise_server_exceptions=False)


def _setup(name, role="owner"):
    co = company(name, "general")
    u = User(company_id=co.id, first_name="F", last_name="L", email=f"imp_{name}@pay-test.com", hashed_password=AU.hash_password("Str0ng-Pass-77"),
             role=role, is_active=True, email_verified=True)
    db.add(u); db.commit(); db.refresh(u)
    user = types.SimpleNamespace(company_id=co.id, id=u.id, role="owner", first_name="B", last_name="B")
    inv = asyncio.run(CO.create_invoice(CO.InvoiceCreate(client_name="Client", description="d", amount=1000), current_user=user, db=db))
    h = {"Authorization": "Bearer " + AU.create_token({"user_id": u.id, "company_id": co.id})}
    return co, inv, h


def _up(c, h, text, dry=False):
    return c.post("/import/payments" + ("?dry_run=true" if dry else ""), headers=h, files={"file": ("p.csv", io.BytesIO(text.encode()), "text/csv")})


def _bank(co):
    acc = db.query(Account).filter_by(company_id=co.id, code="1000").first()
    return round(sum((l.debit or 0) - (l.credit or 0) for l in db.query(JournalLine).filter_by(account_id=acc.id)), 2)


def _inv(i):
    db.expire_all(); return db.query(Invoice).filter_by(id=i.id).first()


def test_part_then_full_payment_updates_status_and_bank():
    co, inv, h = _setup("ip1"); c = _client()
    d1 = (dt.date.today() - dt.timedelta(days=3)).isoformat()
    d2 = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    r = _up(c, h, f"Invoice Number,Amount,Payment Date\n{inv.invoice_number},500,{d1}\n{inv.invoice_number},650,{d2}\n")
    j = r.json()
    assert r.status_code == 200 and j["imported"] == 2 and not j["errors"], j
    assert j["applied"][0]["result"] == "part payment" and j["applied"][1]["result"] == "paid in full"
    i = _inv(inv)
    assert i.status == InvoiceStatus.paid and round(i.paid_amount_zar, 2) == 1150
    assert _bank(co) == 1150


def test_reupload_does_not_record_twice():
    co, inv, h = _setup("ip2"); c = _client()
    d = (dt.date.today() - dt.timedelta(days=2)).isoformat()
    txt = f"Invoice Number,Amount,Payment Date\n{inv.invoice_number},400,{d}\n"
    assert _up(c, h, txt).json()["imported"] == 1
    j = _up(c, h, txt).json()
    assert j["imported"] == 0 and j["duplicates"] == 1
    assert _bank(co) == 400 and round(_inv(inv).paid_amount_zar, 2) == 400


def test_dry_run_changes_nothing():
    co, inv, h = _setup("ip3"); c = _client()
    j = _up(c, h, f"Invoice Number,Amount\n{inv.invoice_number},300\n{inv.invoice_number},850\n", dry=True).json()
    assert j["dry_run"] and j["imported"] == 2 and j["applied"][1]["result"] == "paid in full"
    assert _inv(inv).status == InvoiceStatus.sent and _bank(co) == 0


def test_bad_rows_are_refused_with_reasons():
    co, inv, h = _setup("ip4"); c = _client()
    fut = (dt.date.today() + dt.timedelta(days=10)).isoformat()
    txt = ("Invoice Number,Amount,Payment Date\n"
           "NOPE-1,100,\n"                                   # unknown invoice
           f"{inv.invoice_number},0,\n"                      # zero
           f"{inv.invoice_number},5000,\n"                   # more than balance
           f"{inv.invoice_number},100,{fut}\n"               # future date
           f"{inv.invoice_number},100,32/13/2026\n")         # bad date
    j = _up(c, h, txt).json()
    assert j["imported"] == 0 and len(j["errors"]) == 5, j
    assert _inv(inv).status == InvoiceStatus.sent and _bank(co) == 0


def test_missing_columns_and_role_and_isolation():
    co, inv, h = _setup("ip5"); c = _client()
    assert _up(c, h, "Foo,Bar\n1,2\n").status_code == 400
    co2, inv2, h2 = _setup("ip6", role="employee")
    assert _up(c, h2, f"Invoice Number,Amount\n{inv2.invoice_number},100\n").status_code == 403
    # another company's invoice number is not found for this user
    inv.invoice_number = "ONLYA-77"; db.commit()
    co3, inv3, h3 = _setup("ip7")
    j = _up(c, h3, "Invoice Number,Amount\nONLYA-77,100\n").json()
    assert j["imported"] == 0 and "not found" in j["errors"][0]["message"]
    assert not _inv(inv).paid_amount_zar
