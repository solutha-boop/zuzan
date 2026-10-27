"""Sign-up must work end to end (a stray local `import timedelta` once made every registration return 500)."""
from starlette.testclient import TestClient
from tests.helpers import *


def _client():
    import main
    try:
        main.limiter.enabled = False
    except Exception:
        pass
    return TestClient(main.app, raise_server_exceptions=False)


def test_new_company_can_register_log_in_and_see_example_data_then_add_a_second_company():
    c = _client()
    r = c.post("/auth/register", json={"company_name": "Signup Co", "first_name": "Sam", "last_name": "New",
                                       "email": "signup@test.local", "password": "Signup-Test-123!"})
    assert r.status_code in (200, 201), r.text
    tok = r.json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert c.get("/companies/me", headers=h).status_code == 200
    inv = c.get("/invoices/", headers=h)
    assert inv.status_code == 200 and any("EXAMPLE" in (i.get("invoice_number") or "") for i in inv.json()), inv.text[:200]
    lg = c.post("/auth/login", json={"email": "signup@test.local", "password": "Signup-Test-123!"})
    assert lg.status_code == 200, lg.text
    two = c.post("/auth/add-company", json={"company_name": "Second Entity"}, headers=h)
    assert two.status_code == 200, two.text
    assert two.json()["company"]["name"] == "Second Entity"
    dup = c.post("/auth/register", json={"company_name": "X", "first_name": "A", "last_name": "B",
                                         "email": "SIGNUP@test.local", "password": "Signup-Test-123!"})
    assert dup.status_code == 400
