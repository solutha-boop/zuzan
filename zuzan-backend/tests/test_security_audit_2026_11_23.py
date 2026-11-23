"""Security audit 2026-11-23 fixes: encrypted employee ID/tax numbers, masking, POPIA export/closure,
portal-link expiry, upload limits, safe error messages, CSP header, hashed reset codes."""
import sys, io, json, datetime as dt
from sqlalchemy import text
from starlette.testclient import TestClient
from tests.helpers import *
from database import User, Company, Employee, Invoice, InvoiceStatus, Supplier, CompanyMembership, AuditLog
import auth as AU
import crypto


def _client():
    sys.modules.pop("main", None)
    import main
    return TestClient(main.app, raise_server_exceptions=False)


def _user(co, email, role="owner"):
    u = User(company_id=co.id, first_name="F", last_name="L", email=email, hashed_password=AU.hash_password("Password123"),
             role=role, is_active=True, email_verified=True)
    db.add(u); db.commit(); db.refresh(u); return u


def _hdr(u):
    return {"Authorization": "Bearer " + AU.create_token({"user_id": u.id, "company_id": u.company_id})}


ID_NO = "8001015009087"
TAX_NO = "0123456789"
ACC_NO = "62123456789"


def test_employee_id_and_tax_numbers_are_encrypted_at_rest_and_matched_by_blind_index():
    co = company("secEnc", "general")
    e = emp(co, "S1", 15000, id_number=ID_NO, tax_number=TAX_NO)
    raw = db.execute(text("SELECT id_number, tax_number, id_number_hash FROM employees WHERE id = :i"), {"i": e.id}).one()
    assert crypto.encryption_enabled()
    assert ID_NO not in (raw[0] or "") and TAX_NO not in (raw[1] or "")        # not stored in plaintext
    assert raw[2] == crypto.blind_index(ID_NO)                                   # blind index kept in step
    db.expire_all()
    assert db.query(Employee).get(e.id).id_number == ID_NO                       # ORM still reads the real value
    assert db.query(Employee).filter_by(company_id=co.id, id_number_hash=crypto.blind_index("800101 5009 087")).first().id == e.id


def test_employee_list_masks_numbers_and_full_view_is_restricted_and_logged():
    c = _client()
    co = company("secMask", "general")
    owner = _user(co, "secmask-owner@x.com")
    acct = _user(co, "secmask-acct@x.com", role="accountant")
    e = emp(co, "S2", 15000, id_number=ID_NO, tax_number=TAX_NO, account_number=crypto.encrypt_field(ACC_NO))
    row = [r for r in c.get("/employees/", headers=_hdr(owner)).json() if r["id"] == e.id][0]
    assert row["id_number"].endswith(ID_NO[-4:]) and ID_NO not in row["id_number"]
    assert ACC_NO not in row["account_number"] and row["account_number"].endswith(ACC_NO[-4:])
    full = [r for r in c.get("/employees/?full=1", headers=_hdr(owner)).json() if r["id"] == e.id][0]
    assert full["id_number"] == ID_NO and full["account_number"] == ACC_NO
    assert c.get("/employees/?full=1", headers=_hdr(acct)).status_code == 403
    db.expire_all()
    assert db.query(AuditLog).filter_by(company_id=co.id, action="employees.sensitive_view").count() == 1
    # Saving the edit form with the masked values sent back must not overwrite the real numbers
    r = c.put(f"/employees/{e.id}", headers=_hdr(owner),
              json={"id_number": row["id_number"], "account_number": row["account_number"], "position": "Clerk"})
    assert r.status_code == 200
    db.expire_all()
    e2 = db.query(Employee).get(e.id)
    assert e2.id_number == ID_NO and crypto.decrypt_field(e2.account_number) == ACC_NO and e2.position == "Clerk"


def test_supplier_account_number_is_masked_and_masked_value_is_ignored_on_update():
    c = _client()
    co = company("secSup", "general")
    owner = _user(co, "secsup@x.com")
    s = Supplier(company_id=co.id, name="Acme", account_number=crypto.encrypt_field(ACC_NO), is_active=True)
    db.add(s); db.commit(); db.refresh(s)
    row = [r for r in c.get("/suppliers/", headers=_hdr(owner)).json() if r["id"] == s.id][0]
    assert ACC_NO not in row["account_number"]
    assert c.put(f"/suppliers/{s.id}", headers=_hdr(owner), json={"account_number": row["account_number"]}).status_code == 200
    db.expire_all()
    assert crypto.decrypt_field(db.query(Supplier).get(s.id).account_number) == ACC_NO


def test_company_data_export_contains_only_own_company_and_no_secrets():
    c = _client()
    a = company("secExpA", "general"); b = company("secExpB", "general")
    ua = _user(a, "secexp-a@x.com"); _user(b, "secexp-b@x.com")
    emp(a, "A1", 10000, id_number=ID_NO); emp(b, "OTHERCOMPANYEMP", 10000)
    r = c.get("/companies/me/data-export", headers=_hdr(ua))
    assert r.status_code == 200 and "attachment" in r.headers.get("content-disposition", "")
    body = r.text
    data = json.loads(body)["tables"]
    assert "OTHERCOMPANYEMP" not in body and "secexp-b@x.com" not in body
    assert all(row.get("company_id") in (None, a.id) for rows in data.values() for row in rows)
    assert "hashed_password" not in body and "id_number_hash" not in body
    assert any(row.get("id_number") == ID_NO for row in data["employees"])     # decrypted for the owner
    acct = _user(a, "secexp-acct@x.com", role="accountant")
    assert c.get("/companies/me/data-export", headers=_hdr(acct)).status_code == 403


def test_close_account_requires_name_and_blocks_all_access():
    c = _client()
    co = company("secClose", "general")
    owner = _user(co, "secclose-o@x.com"); staff = _user(co, "secclose-s@x.com", role="admin")
    h = _hdr(owner)
    assert c.post("/companies/me/close-account", headers=h, json={"confirm_company_name": "wrong"}).status_code == 400
    r = c.post("/companies/me/close-account", headers=h, json={"confirm_company_name": "SECCLOSE"})
    assert r.status_code == 200 and r.json()["records_retained_until"]
    assert c.get("/auth/team", headers=_hdr(staff)).status_code == 401
    assert c.post("/auth/login", json={"email": "secclose-o@x.com", "password": "Password123"}).status_code == 401
    db.expire_all()
    assert db.query(Company).get(co.id).closed_at is not None


def test_portal_links_expire():
    c = _client()
    co = company("secPortal", "general")
    inv = Invoice(company_id=co.id, invoice_number="P-1", client_name="C", amount=100, vat_amount=15, total_amount=115,
                  status=InvoiceStatus.sent, portal_token="tok-fresh-123", portal_token_created_at=dt.datetime.utcnow())
    old = Invoice(company_id=co.id, invoice_number="P-2", client_name="C", amount=100, vat_amount=15, total_amount=115,
                  status=InvoiceStatus.sent, portal_token="tok-old-123",
                  portal_token_created_at=dt.datetime.utcnow() - dt.timedelta(days=400))
    db.add_all([inv, old]); db.commit()
    assert c.get("/portal/invoice/tok-fresh-123").status_code == 200
    assert c.get("/portal/invoice/tok-old-123").status_code == 410


def test_import_upload_rejects_wrong_type_and_oversize():
    import csv_import
    c = _client()
    co = company("secUpl", "general"); owner = _user(co, "secupl@x.com")
    files = {"file": ("evil.exe", io.BytesIO(b"MZ..."), "application/octet-stream")}
    assert c.post("/import/customers", headers=_hdr(owner), files=files).status_code == 400
    big = b"name\n" + b"x" * (csv_import.MAX_IMPORT_BYTES + 10)
    assert c.post("/import/customers", headers=_hdr(owner),
                  files={"file": ("big.csv", io.BytesIO(big), "text/csv")}).status_code == 413


def test_public_error_hides_internal_details():
    from security import public_error
    assert public_error(ValueError("The period is locked")) == "The period is locked"
    msg = public_error(RuntimeError("psycopg2 connection to db-host password=hunter2 failed"))
    assert "hunter2" not in msg and "reference" in msg


def test_api_responses_carry_csp_and_health_reports_flags_only():
    c = _client()
    r = c.get("/health")
    assert "default-src 'none'" in r.headers.get("content-security-policy", "")
    j = r.json()
    assert j["field_encryption"] is True and set(j) >= {"status", "field_encryption", "secret_key_configured"}
    assert all(isinstance(v, (bool, str)) for v in j.values())


def test_sentry_scrubber_removes_personal_data():
    import main
    ev = {"request": {"headers": {"Authorization": "Bearer abc"}, "data": {"id_number": ID_NO, "note": f"acc {ACC_NO}"}},
          "exception": {"values": [{"value": f"bad id {ID_NO}", "stacktrace": {"frames": [{"vars": {"x": 1}}]}}]}}
    out = json.dumps(main._sentry_before_send(ev, {}))
    assert ID_NO not in out and ACC_NO not in out and "Bearer abc" not in out and '"vars"' not in out
