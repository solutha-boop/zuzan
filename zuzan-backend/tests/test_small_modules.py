import types, asyncio, datetime as dt
import pytest
from fastapi import HTTPException
from tests.helpers import *
from database import APIKey
import api_keys as AK, customers as CU, suppliers as SU


def _u(co): return types.SimpleNamespace(company_id=co.id, id=1)


def test_api_key_daily_limit_resets_each_day_and_is_not_lifetime():
    co = company("apik", "general"); u = _u(co)
    made = asyncio.run(AK.create_key(AK.CreateKeyRequest(name="k", scopes=["read"]), current_user=u, db=db))
    raw = made["key"]
    rec = db.query(APIKey).get(made["id"])
    rec.requests_today = 1000; rec.last_used = dt.datetime.utcnow(); db.commit()
    assert AK.get_company_from_api_key(raw, db) == (None, None)                    # today's limit reached
    rec.last_used = dt.datetime.utcnow() - dt.timedelta(days=1); db.commit()       # ...but tomorrow it works again
    company_obj, key = AK.get_company_from_api_key(raw, db)
    assert company_obj is not None and key.requests_today == 1
    with pytest.raises(HTTPException):
        asyncio.run(AK.create_key(AK.CreateKeyRequest(name="  ", scopes=["read"]), current_user=u, db=db))


def test_customer_and_supplier_validation_and_isolation():
    a, b = company("cu_a", "general"), company("cu_b", "general")
    ua, ub = _u(a), _u(b)
    for mod, create, upd, Create, Upd in ((CU, CU.create_customer, CU.update_customer, CU.CustomerCreate, CU.CustomerUpdate),
                                          (SU, SU.create_supplier, SU.update_supplier, SU.SupplierCreate, SU.SupplierUpdate)):
        with pytest.raises(HTTPException):
            asyncio.run(create(Create(name="  "), current_user=ua, db=db))
        with pytest.raises(HTTPException):
            asyncio.run(create(Create(name="X", payment_terms=-5), current_user=ua, db=db))
        row = asyncio.run(create(Create(name="  Acme  ", email="a@x.co.za"), current_user=ua, db=db))
        assert row["name"] == "Acme"
        with pytest.raises(HTTPException):
            asyncio.run(upd(row["id"], Upd(name=""), current_user=ua, db=db))
        with pytest.raises(HTTPException) as ex:                                   # another company cannot edit it
            asyncio.run(upd(row["id"], Upd(name="Hijack"), current_user=ub, db=db))
        assert ex.value.status_code == 404
        cleared = asyncio.run(upd(row["id"], Upd(email=""), current_user=ua, db=db))
        assert cleared["email"] == ""                                              # a field can be cleared
