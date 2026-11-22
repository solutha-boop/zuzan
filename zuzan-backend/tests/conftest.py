"""
Test configuration. Everything runs against a throwaway SQLite database - never zuzan.db or production.
The environment must be set BEFORE database.py is imported (it reads DATABASE_URL at import time).
"""
import os, sys, tempfile, atexit, shutil

_TMP = tempfile.mkdtemp(prefix="zuzan_tests_")
atexit.register(lambda: shutil.rmtree(_TMP, ignore_errors=True))
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/zuzan_test.db"
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.pop("RENDER", None)
os.environ.pop("CORS_ORIGINS", None)
os.environ["ZUZAN_DISABLE_THROTTLE"] = "1"      # the per-IP request ceiling would trip on the big route sweeps; tests/test_security_hardening.py switches it on

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


import pytest


@pytest.fixture(autouse=True)
def _release_shared_session():
    """End any transaction a test left open on the shared helpers session (2026-11-22).
    SQLite allows one writer: a test that wrote without committing kept the database locked, so every
    later test that goes through the app (its own session) failed with 'database is locked' and a 500 -
    the 7 migration-wizard failures that only appeared when the whole suite ran."""
    yield
    h = sys.modules.get("tests.helpers")
    if h is None:
        return
    try:
        h.db.commit()
    except Exception:
        h.db.rollback()
