import io, types, asyncio
import pytest
from fastapi import HTTPException, UploadFile
from starlette.testclient import TestClient
from tests.helpers import *
import documents as DOC


def _upload(user, name, filename, content=b"hello"):
    f = UploadFile(file=io.BytesIO(content), filename=filename, headers=None)
    return asyncio.run(DOC.upload_document(name=name, category="Contracts", description="", file=f, db=db, current_user=user))


def test_download_works_for_unusual_file_names_and_rejects_empty_or_oversize():
    co = company("docs", "general")
    user = types.SimpleNamespace(company_id=co.id, id=1, role="owner")
    for fname in ("Financiële verslag — 2026.pdf", 'quote "final".pdf', "line\r\nbreak.pdf", "日本語.pdf"):
        d = _upload(user, "doc", fname)
        resp = DOC.download_document(d["id"], db=db, current_user=user)
        cd = resp.headers["content-disposition"]
        assert "\r" not in cd and "\n" not in cd and cd.startswith("attachment;")
        cd.encode("latin-1")                                   # what the HTTP layer will do - must not raise
        assert resp.body == b"hello" and resp.headers["x-content-type-options"] == "nosniff"
    assert "filename*=UTF-8''" in DOC.download_document(_upload(user, "d", "Financiële.pdf")["id"], db=db, current_user=user).headers["content-disposition"]
    with pytest.raises(HTTPException):
        _upload(user, "empty", "e.txt", content=b"")
    with pytest.raises(HTTPException):
        _upload(user, "big", "b.bin", content=b"x" * (DOC.MAX_BYTES + 1))
