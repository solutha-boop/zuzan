import types, asyncio, datetime as dt
import pytest
from fastapi import HTTPException
from tests.helpers import *
from database import LeaveRequest, LeaveBalance
import leave as L


def _u(co): return types.SimpleNamespace(company_id=co.id, id=1, first_name="Boss", last_name="B")
def _submit(co, e, **kw):
    d = dict(employee_id=e.id, leave_type="annual", start_date="2027-03-01", end_date="2027-03-03")
    d.update(kw)
    return asyncio.run(L.submit_request(L.LeaveRequestCreate(**d), current_user=_u(co), db=db))
def _review(co, rid, status): return asyncio.run(L.review_request(rid, L.LeaveRequestReview(status=status), current_user=_u(co), db=db))
def _bal(e): db.expire_all(); return db.query(LeaveBalance).filter_by(employee_id=e.id).first()


def test_public_holidays_are_not_leave_days():
    # Mon 19 Apr 2027 is the Monday after Easter (Family Day); 22-26 Mar... use Good Friday 2027-03-26 and 2027-04-05
    assert L.count_working_days(dt.date(2027, 3, 22), dt.date(2027, 3, 26)) == 3.0     # Human Rights Day (Mon 22) and Good Friday (26) excluded
    assert L.count_working_days(dt.date(2027, 3, 1), dt.date(2027, 3, 5)) == 5.0


def test_pending_requests_reserve_balance_overlap_and_bad_dates_are_rejected():
    co = company("lv1", "general"); e = emp(co, "E1", 15000)
    for bad in (dict(start_date="31/12/2027", end_date="2027-12-31"), dict(start_date="2027-03-05", end_date="2027-03-01")):
        with pytest.raises(HTTPException) as ex:
            _submit(co, e, **bad)
        assert ex.value.status_code == 400
    r1 = _submit(co, e, start_date="2027-05-03", end_date="2027-05-14")          # 10 days of the 15
    with pytest.raises(HTTPException):                                            # overlap
        _submit(co, e, start_date="2027-05-10", end_date="2027-05-12")
    with pytest.raises(HTTPException) as ex:                                      # 10 pending + 10 more > 15
        _submit(co, e, start_date="2027-06-01", end_date="2027-06-14")
    assert "Insufficient" in ex.value.detail
    _submit(co, e, start_date="2027-06-01", end_date="2027-06-07")                # 5 days still fits exactly


def test_approve_cancel_restores_balance_and_cannot_overdraw():
    co = company("lv2", "general"); e = emp(co, "E1", 15000)
    r = _submit(co, e, start_date="2027-05-03", end_date="2027-05-07")            # 5 days
    _review(co, r["id"], "approved")
    assert _bal(e).annual_balance == 10 and _bal(e).annual_taken_ytd == 5
    _review(co, r["id"], "cancelled")                                             # approved leave can be cancelled
    assert _bal(e).annual_balance == 15 and _bal(e).annual_taken_ytd == 0
    with pytest.raises(HTTPException):
        _review(co, r["id"], "approved")                                          # decided requests are final
    # a balance that dropped after submission blocks approval and auto-approval
    r2 = _submit(co, e, start_date="2027-07-05", end_date="2027-07-09")
    b = _bal(e); b.annual_balance = 2; db.commit()
    with pytest.raises(HTTPException) as ex:
        _review(co, r2["id"], "approved")
    assert ex.value.status_code == 400
    q = db.query(LeaveRequest).get(r2["id"]); q.submitted_at = dt.datetime.utcnow() - dt.timedelta(hours=72); db.commit()
    asyncio.run(L.list_requests(current_user=_u(co), db=db))
    db.expire_all(); assert db.query(LeaveRequest).get(r2["id"]).status == "pending"
