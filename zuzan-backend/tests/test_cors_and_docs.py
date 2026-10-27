import sys, os
from starlette.testclient import TestClient
import tests.conftest  # noqa: F401


def _load(env):
    for k in ("CORS_ORIGINS", "RENDER", "ENABLE_API_DOCS"):
        os.environ.pop(k, None)
    os.environ.update(env)
    sys.modules.pop("main", None)
    import main
    return TestClient(main.app)


def test_default_is_open_as_before_and_docs_on_locally():
    c = _load({})
    assert c.get("/health", headers={"Origin": "https://evil.example"}).headers.get("access-control-allow-origin") == "*"
    assert c.get("/docs").status_code == 200


def test_render_hides_docs_and_cors_list_is_enforced():
    c = _load({"RENDER": "1", "CORS_ORIGINS": "https://zuzan.co.za, https://app.zuzan.co.za"})
    assert c.get("/docs").status_code == 404 and c.get("/openapi.json").status_code == 404
    assert c.get("/health", headers={"Origin": "https://app.zuzan.co.za"}).headers.get("access-control-allow-origin") == "https://app.zuzan.co.za"
    assert "access-control-allow-origin" not in c.get("/health", headers={"Origin": "https://evil.example"}).headers
    assert c.get("/health", headers={"Origin": "https://partner.example", "X-API-Key": "k"}).headers.get("access-control-allow-origin") == "*"
    pre = c.options("/health", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in pre.headers
    ok = c.options("/health", headers={"Origin": "https://zuzan.co.za", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "authorization"})
    assert ok.headers.get("access-control-allow-origin") == "https://zuzan.co.za"


def test_docs_can_be_switched_back_on():
    c = _load({"RENDER": "1", "ENABLE_API_DOCS": "1"})
    assert c.get("/docs").status_code == 200
