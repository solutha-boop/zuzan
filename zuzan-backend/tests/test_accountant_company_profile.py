"""An accountant (practice member) can edit a client's company profile, but not its billing, payroll add-on or bank details."""
import asyncio, uuid
import pytest
from fastapi import HTTPException
from tests.helpers import *
from database import User, Company
import auth, companies as CO


def _user(co, role):
    tag = uuid.uuid4().hex[:8]
    u = User(email=f"u-{tag}@x.test", hashed_password=auth.hash_password("x-Strong-1"), first_name="A", last_name="B",
             company_id=co.id, role=role)
    db.add(u); db.commit(); db.refresh(u)
    return u



def test_accountant_can_rename_but_not_touch_billing_or_bank():
    co = company(f"Cascade Bed & Breeakfast {uuid.uuid4().hex[:6]}", "hospitality")
    co.plan = "starter"; db.commit()
    acc = _user(co, "accountant")
    out = asyncio.run(CO.update_company(CO.CompanyUpdate(name="Cascade Bed & Breakfast", vat_number="4123456789",
                                                         plan="business", bank_account="123456", payfast_passphrase="x"),
                                        current_user=acc, db=db))
    db.refresh(co)
    assert co.name == "Cascade Bed & Breakfast" and co.vat_number == "4123456789"
    assert co.plan == "starter"
    assert not co.bank_account or "123456" not in str(co.bank_account)
    assert set(out["not_saved"]) == {"plan", "bank_account", "payfast_passphrase"}


def test_owner_still_saves_everything_and_gets_no_note():
    co = company(f"Owner Co {uuid.uuid4().hex[:6]}", "retail")
    own = _user(co, "owner")
    out = asyncio.run(CO.update_company(CO.CompanyUpdate(name="Owner Co Renamed", plan="professional"), current_user=own, db=db))
    db.refresh(co)
    assert co.name == "Owner Co Renamed" and co.plan == "professional" and "not_saved" not in out


def test_role_gate_now_admits_accountant_but_not_payroll_or_employee():
    import inspect
    sig = inspect.signature(CO.update_company)
    dep = sig.parameters["current_user"].default.dependency
    co = company(f"Gate Co {uuid.uuid4().hex[:6]}", "retail")
    for role, ok in (("accountant", True), ("owner", True), ("admin", True), ("payroll", False), ("employee", False)):
        u = _user(co, role)
        if ok:
            assert dep(current_user=u) is u
        else:
            with pytest.raises(HTTPException):
                dep(current_user=u)
