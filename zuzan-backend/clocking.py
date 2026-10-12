"""
ZuZan — Clocking System
Employees clock in / out via kiosk or mobile. Manager views attendance,
edits records, exports hours to the Zuzan OT CSV format, or pushes
aggregated hours directly to the payroll OT modal via the /payroll-hours
endpoint.

Hours bucketing rules (per shift pair):
  • Sunday              → sunday_hours
  • Public Holiday (SA) → ph_hours
  • Weekday / Saturday  → normal_hours up to daily_threshold, then ot_hours
  • Night shift         → any shift touching 18:00–05:59 counts as 1 night-shift shift
"""

import csv
import io
import os
import secrets
from datetime import datetime, timedelta, date, time as dtime, timezone
from functools import lru_cache
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db, Company, Employee, ClockEvent, User
from auth import get_current_user, log_action

router = APIRouter()

# ── Time zone ────────────────────────────────────────────────────────────────
# All ClockEvent.timestamp values are stored as NAIVE UTC (datetime.utcnow() / client toISOString()).
# Every pay rule (Sunday, public holiday, night shift, week boundaries) is defined in South African local
# time (SAST, UTC+2, no daylight saving), so timestamps are converted before bucketing.
LOCAL_UTC_OFFSET = timedelta(hours=float(os.getenv("CLOCK_UTC_OFFSET_HOURS", "2")))


def _emp_name(e) -> str:
    """Employee has first_name/last_name columns (there is no .name attribute)."""
    return f"{getattr(e, 'first_name', '') or ''} {getattr(e, 'last_name', '') or ''}".strip()


def _to_utc_naive(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalise any incoming datetime to naive UTC (the storage convention)."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _utc_iso(dt: Optional[datetime]) -> Optional[str]:
    """ISO string with an explicit 'Z' so browsers convert to local time correctly."""
    if dt is None:
        return None
    return dt.isoformat() + ("" if dt.tzinfo else "Z")


def _local(dt_utc: datetime) -> datetime:
    return dt_utc + LOCAL_UTC_OFFSET


def _local_midnight_utc(d: date) -> datetime:
    """The UTC instant at which local calendar day `d` begins."""
    return datetime.combine(d, dtime(0, 0)) - LOCAL_UTC_OFFSET


# ── South African public holidays (computed for any year) ────────────────────
# Fixed-date holidays, Good Friday and Family Day (Easter-based), and the rule that a holiday falling on a
# Sunday is also observed on the following Monday (Public Holidays Act 36 of 1994, s2(1)).
# One-off proclaimed days (e.g. election days) cannot be computed - add them to _SA_EXTRA_PUBLIC_HOLIDAYS.
_SA_EXTRA_PUBLIC_HOLIDAYS: set = set()
_SA_FIXED_HOLIDAYS = [(1, 1), (3, 21), (4, 27), (5, 1), (6, 16), (8, 9), (9, 24), (12, 16), (12, 25), (12, 26)]


def _easter(year: int) -> date:
    """Gregorian Easter Sunday (anonymous / Meeus algorithm)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


@lru_cache(maxsize=64)
def _sa_holidays(year: int) -> frozenset:
    hs = set()
    for m, d in _SA_FIXED_HOLIDAYS:
        dt = date(year, m, d)
        hs.add(dt)
        if dt.weekday() == 6:
            hs.add(dt + timedelta(days=1))
    easter = _easter(year)
    hs.add(easter - timedelta(days=2))   # Good Friday
    hs.add(easter + timedelta(days=1))   # Family Day
    return frozenset(hs)


def _is_ph(d: date) -> bool:
    return d in _sa_holidays(d.year) or d in _SA_EXTRA_PUBLIC_HOLIDAYS


# ── Shift maths (all inputs are LOCAL naive datetimes) ───────────────────────

def _round_dt(dt: datetime, minutes: int) -> datetime:
    """Round a punch to the nearest `minutes` (0 = exact). Stops clock jitter (e.g. out at 18:03) from
    creating a few minutes of 'overtime' every single shift."""
    if not minutes or minutes <= 0:
        return dt
    step = minutes * 60
    secs = (dt - datetime(dt.year, dt.month, dt.day)).total_seconds()
    return datetime(dt.year, dt.month, dt.day) + timedelta(seconds=round(secs / step) * step)


def _segments(local_in: datetime, local_out: datetime):
    """Split a shift at local midnight -> [(seg_in, seg_out, local_date)]."""
    segs, cur = [], local_in
    while cur.date() < local_out.date():
        midnight = datetime.combine(cur.date() + timedelta(days=1), dtime(0, 0))
        segs.append((cur, midnight, cur.date()))
        cur = midnight
    if local_out > cur:
        segs.append((cur, local_out, cur.date()))
    return segs


def _is_night_shift(local_in: datetime, local_out: datetime) -> bool:
    """A night shift is one where at least half the hours worked fall between 18:00 and 06:00.
    (A day shift clocked out a few minutes after 18:00 is NOT a night shift.)"""
    total = (local_out - local_in).total_seconds()
    if total <= 0:
        return False
    night = 0.0
    day = local_in.date() - timedelta(days=1)
    while day <= local_out.date():
        w_start = datetime.combine(day, dtime(18, 0))
        w_end = w_start + timedelta(hours=12)
        lo, hi = max(local_in, w_start), min(local_out, w_end)
        if hi > lo:
            night += (hi - lo).total_seconds()
        day += timedelta(days=1)
    return night >= 0.5 * total


def _bucket_hours(dt_in: datetime, dt_out: datetime, daily_threshold: float = 8.0, _daily_normal: Optional[dict] = None):
    """
    General (non-security) bucketing of one shift. dt_in / dt_out are LOCAL times.
    Sunday -> sunday_hours; public holiday -> ph_hours; other days -> normal up to daily_threshold per
    calendar day (across ALL that day's shifts), then ot_hours.
    """
    result = {"normal_hours": 0.0, "ot_hours": 0.0, "sunday_hours": 0.0, "ph_hours": 0.0, "night_shift_shifts": 0}
    daily = _daily_normal if _daily_normal is not None else {}
    for seg_in, seg_out, d in _segments(dt_in, dt_out):
        hours = (seg_out - seg_in).total_seconds() / 3600.0
        if _is_ph(d):
            result["ph_hours"] += hours
        elif d.weekday() == 6:
            result["sunday_hours"] += hours
        else:
            room = max(0.0, daily_threshold - daily.get(d, 0.0))
            normal = min(hours, room)
            daily[d] = daily.get(d, 0.0) + normal
            result["normal_hours"] += normal
            result["ot_hours"] += hours - normal
    if _is_night_shift(dt_in, dt_out):
        result["night_shift_shifts"] = 1
    return result


NBCPSS_WEEKLY_ORDINARY_HOURS = 48.0


def _aggregate_security(sessions: list, period_start: date, period_end: date, all_sessions: Optional[list] = None):
    """
    NBCPSS bucketing for a security officer. `sessions` = [(local_in, local_out)] CLOCKED IN inside the
    period; `all_sessions` = every paired session fetched around it (used only for the weekly overtime test).
    * Ordinary hours are 48 per week (12h shifts): overtime is only time worked beyond 48h in a Mon-Sun
      week - NOT beyond 8h in a day. A week's overtime is paid once, in the period that contains the
      week's Sunday, using the whole week's hours (so month-end weeks are never pro-rated or split).
    * Sunday / public-holiday hours are paid through their own premium and are not counted again as
      overtime: overtime is taken from weekday hours only.
    * Night shift = one night-shift allowance per shift that is mostly between 18:00 and 06:00.
    """
    sun = ph = 0.0
    night = 0
    total_hours = 0.0
    for lin, lout in sessions:
        if _is_night_shift(lin, lout):
            night += 1
        for seg_in, seg_out, d in _segments(lin, lout):
            h = (seg_out - seg_in).total_seconds() / 3600.0
            total_hours += h
            if _is_ph(d):
                ph += h
            elif d.weekday() == 6:
                sun += h
    weeks: dict = {}
    for lin, lout in (all_sessions if all_sessions is not None else sessions):
        for seg_in, seg_out, d in _segments(lin, lout):
            h = (seg_out - seg_in).total_seconds() / 3600.0
            wk = d - timedelta(days=d.weekday())
            w = weeks.setdefault(wk, {"total": 0.0, "weekday": 0.0})
            w["total"] += h
            if not _is_ph(d) and d.weekday() != 6:
                w["weekday"] += h
    ot = 0.0
    for wk, w in weeks.items():
        week_sunday = wk + timedelta(days=6)
        if period_start <= week_sunday <= period_end:
            ot += min(max(0.0, w["total"] - NBCPSS_WEEKLY_ORDINARY_HOURS), w["weekday"])
    return {"ot_hours": ot, "sunday_hours": sun, "ph_hours": ph,
            "night_shift_shifts": night, "total_hours": total_hours}


def _pair_events_ex(events: list):
    """
    Pair a time-ordered list of ClockEvent rows into (in, out) sessions and report every irregularity
    instead of silently dropping punches: an 'in' followed by another 'in' (missed clock-out), an 'out'
    with no 'in' (missed clock-in), and a trailing open session.
    """
    sessions, problems, pending = [], [], None
    for ev in events:
        if ev.event_type == "in":
            if pending is not None:
                problems.append({"type": "missing_clock_out", "at": pending.timestamp,
                                 "message": f"Clocked in {_local(pending.timestamp):%a %d %b %H:%M} with no clock-out - shift not paid"})
            pending = ev
        elif ev.event_type == "out":
            if pending is not None:
                sessions.append((pending, ev))
                pending = None
            else:
                problems.append({"type": "missing_clock_in", "at": ev.timestamp,
                                 "message": f"Clocked out {_local(ev.timestamp):%a %d %b %H:%M} with no clock-in - shift not paid"})
    if pending is not None:
        sessions.append((pending, None))
    return sessions, problems


def _pair_events(events: list) -> list:
    return _pair_events_ex(events)[0]


# ── Kiosk token helpers ───────────────────────────────────────────────────────

def _generate_kiosk_token(company: Company, db: Session) -> str:
    token = secrets.token_urlsafe(24)
    company.kiosk_token = token
    company.kiosk_token_created_at = datetime.utcnow()
    db.commit()
    return token


# ══════════════════════════════════════════════════════════════════════════════
# Endpoints
# ══════════════════════════════════════════════════════════════════════════════

# ── POST /clocking/kiosk-token ────────────────────────────────────────────────

@router.post("/kiosk-token")
async def generate_kiosk_token(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate (or regenerate) the company's kiosk token. Returns the full kiosk URL."""
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    token = _generate_kiosk_token(company, db)
    log_action(db, company.id, current_user.id, "kiosk_token_generated", "Kiosk token regenerated")
    return {"kiosk_token": token, "kiosk_url": f"https://zuzan.co.za/clock?token={token}"}


# ── GET /clocking/kiosk-info — public endpoint for kiosk token auth ───────────

@router.get("/kiosk-info")
async def kiosk_info(
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    """
    Public endpoint — validates a kiosk token and returns the company's employee list.
    Used by the standalone clock.html to bootstrap without requiring staff login.
    """
    company = db.query(Company).filter(Company.kiosk_token == token).first()
    if not company:
        raise HTTPException(status_code=403, detail="Invalid or expired kiosk token")
    employees = db.query(Employee).filter(
        Employee.company_id == company.id,
        Employee.is_active.is_(True),
    ).order_by(Employee.first_name, Employee.last_name).all()
    return {
        "company_id": company.id,
        "company_name": company.name,
        "employees": [
            {"id": e.id, "name": _emp_name(e), "employee_number": e.employee_number or str(e.id)}
            for e in employees
        ],
    }


# ── POST /clocking/clock — single endpoint for both in and out ────────────────

class ClockIn(BaseModel):
    employee_id: int
    event_type: str          # "in" or "out"
    method: Optional[str] = "kiosk"
    notes: Optional[str] = None
    timestamp: Optional[datetime] = None   # override for manual entry

class KioskClock(BaseModel):
    kiosk_token: str
    employee_id: int
    event_type: str          # "in" or "out"
    method: Optional[str] = "kiosk"
    notes: Optional[str] = None
    timestamp: Optional[datetime] = None


@router.post("/clock")
async def clock_event_authenticated(
    data: ClockIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Authenticated clock (manager / staff logged in via JWT)."""
    emp = db.query(Employee).filter(
        Employee.id == data.employee_id,
        Employee.company_id == current_user.company_id,
    ).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    if data.event_type not in ("in", "out"):
        raise HTTPException(status_code=400, detail="event_type must be 'in' or 'out'")
    ev = ClockEvent(
        company_id=current_user.company_id,
        employee_id=data.employee_id,
        event_type=data.event_type,
        timestamp=_to_utc_naive(data.timestamp) or datetime.utcnow(),
        method=data.method or "kiosk",
        notes=data.notes,
        created_by=current_user.id,
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return {"id": ev.id, "employee": _emp_name(emp), "event_type": ev.event_type,
            "timestamp": _utc_iso(ev.timestamp)}


@router.post("/clock-kiosk")
async def clock_event_kiosk(
    data: KioskClock,
    db: Session = Depends(get_db),
):
    """
    Public kiosk endpoint — no JWT required; authenticated by kiosk_token.
    The standalone clock.html uses this so employees don't need to log in.
    """
    company = db.query(Company).filter(Company.kiosk_token == data.kiosk_token).first()
    if not company:
        raise HTTPException(status_code=403, detail="Invalid kiosk token")
    emp = db.query(Employee).filter(
        Employee.id == data.employee_id,
        Employee.company_id == company.id,
        Employee.is_active.is_(True),
    ).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    if data.event_type not in ("in", "out"):
        raise HTTPException(status_code=400, detail="event_type must be 'in' or 'out'")
    ev = ClockEvent(
        company_id=company.id,
        employee_id=data.employee_id,
        event_type=data.event_type,
        timestamp=datetime.utcnow(),   # server clock ONLY - a public kiosk caller must never choose the time
        method=data.method or "kiosk",
        notes=data.notes,
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return {"id": ev.id, "employee": _emp_name(emp), "event_type": ev.event_type,
            "timestamp": _utc_iso(ev.timestamp)}


# ── GET /clocking/today — who is currently clocked in ────────────────────────

@router.get("/today")
async def today_attendance(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns each employee's current status (in/out) as of now."""
    cid = current_user.company_id
    employees = db.query(Employee).filter(
        Employee.company_id == cid, Employee.is_active.is_(True)
    ).order_by(Employee.first_name, Employee.last_name).all()

    today_start = datetime.utcnow() - timedelta(hours=24)   # not "since midnight": a night shift in progress must still show IN
    events = db.query(ClockEvent).filter(
        ClockEvent.company_id == cid,
        ClockEvent.timestamp >= today_start,
    ).order_by(ClockEvent.employee_id, ClockEvent.timestamp).all()

    # Last event per employee today
    last_event = {}
    for ev in events:
        last_event[ev.employee_id] = ev

    result = []
    for emp in employees:
        ev = last_event.get(emp.id)
        result.append({
            "employee_id":     emp.id,
            "name":            _emp_name(emp),
            "employee_number": emp.employee_number or str(emp.id),
            "status":          ev.event_type if ev else "out",
            "last_event":      _utc_iso(ev.timestamp) if ev else None,
            "last_method":     ev.method if ev else None,
        })
    return result


@router.get("/today-kiosk")
async def today_attendance_kiosk(
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    """Public version of /today for the kiosk (uses kiosk token instead of JWT)."""
    company = db.query(Company).filter(Company.kiosk_token == token).first()
    if not company:
        raise HTTPException(status_code=403, detail="Invalid kiosk token")
    employees = db.query(Employee).filter(
        Employee.company_id == company.id, Employee.is_active.is_(True)
    ).order_by(Employee.first_name, Employee.last_name).all()
    today_start = datetime.utcnow() - timedelta(hours=24)   # not "since midnight": a night shift in progress must still show IN
    events = db.query(ClockEvent).filter(
        ClockEvent.company_id == company.id,
        ClockEvent.timestamp >= today_start,
    ).order_by(ClockEvent.employee_id, ClockEvent.timestamp).all()
    last_event = {}
    for ev in events:
        last_event[ev.employee_id] = ev
    result = []
    for emp in employees:
        ev = last_event.get(emp.id)
        result.append({
            "employee_id":     emp.id,
            "name":            _emp_name(emp),
            "employee_number": emp.employee_number or str(emp.id),
            "status":          ev.event_type if ev else "out",
            "last_event":      _utc_iso(ev.timestamp) if ev else None,
        })
    return result


# ── GET /clocking/sessions — raw sessions for a date range ───────────────────

@router.get("/sessions")
async def get_sessions(
    date_from: str = Query(...),
    date_to:   str = Query(...),
    employee_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return all clock events in the date range, grouped as (in, out) pairs per employee per day.
    date_from / date_to: ISO date strings yyyy-mm-dd (inclusive).
    """
    cid = current_user.company_id
    try:
        dt_from = datetime.strptime(date_from, "%Y-%m-%d")
        dt_to   = datetime.strptime(date_to,   "%Y-%m-%d") + timedelta(days=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use yyyy-mm-dd")

    q = db.query(ClockEvent).filter(
        ClockEvent.company_id == cid,
        ClockEvent.timestamp >= dt_from,
        ClockEvent.timestamp < dt_to,
    )
    if employee_id:
        q = q.filter(ClockEvent.employee_id == employee_id)
    events = q.order_by(ClockEvent.employee_id, ClockEvent.timestamp).all()

    # Group by employee
    by_emp: dict[int, list] = {}
    for ev in events:
        by_emp.setdefault(ev.employee_id, []).append(ev)

    emp_map = {e.id: e for e in db.query(Employee).filter(Employee.company_id == cid).all()}

    sessions = []
    for eid, evs in by_emp.items():
        pairs = _pair_events(evs)
        for ev_in, ev_out in pairs:
            sessions.append({
                "employee_id":     eid,
                "employee_name":   _emp_name(emp_map[eid]) if eid in emp_map else "?",
                "employee_number": getattr(emp_map.get(eid), "employee_number", None) or str(eid),
                "clock_in_id":     ev_in.id,
                "clock_in":        _utc_iso(ev_in.timestamp),
                "clock_in_method": ev_in.method,
                "clock_out_id":    ev_out.id if ev_out else None,
                "clock_out":       _utc_iso(ev_out.timestamp) if ev_out else None,
                "clock_out_method": ev_out.method if ev_out else None,
                "hours":           round((ev_out.timestamp - ev_in.timestamp).total_seconds() / 3600, 2) if ev_out else None,
                "open":            ev_out is None,
            })
    return sessions


# ── GET /clocking/payroll-hours — aggregated hours for OT modal ──────────────

@router.get("/payroll-hours")
async def payroll_hours(
    date_from:       str   = Query(...),
    date_to:         str   = Query(...),
    daily_threshold: float = Query(8.0,  description="Non-security staff: normal hours per day before OT kicks in"),
    round_minutes:   int   = Query(15,   description="Round each punch to the nearest N minutes (0 = exact)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Aggregate clock events into per-employee hour buckets for the payroll OT modal.

    * date_from / date_to are LOCAL (SAST) calendar days, inclusive. A shift belongs to the period in
      which it was CLOCKED IN, so a night shift that starts on the last day and ends after midnight is
      paid once, in the right period.
    * Security officers (NBCPSS grade set): overtime is beyond 48h per Mon-Sun week (paid in the period
      holding that week's Sunday), night shifts are
      judged by where the hours fall, and normal hours are NOT sent for pay (apply_normal_hours=false)
      because basic pay is the contracted monthly salary.
    * Every irregularity (missed clock-in/out, open session, very long shift) is returned in
      `exceptions` - nothing is dropped silently.
    """
    cid = current_user.company_id
    try:
        d_from = datetime.strptime(date_from, "%Y-%m-%d").date()
        d_to   = datetime.strptime(date_to,   "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use yyyy-mm-dd")
    if d_to < d_from:
        raise HTTPException(status_code=400, detail="date_to is before date_from")

    # Fetch one extra day either side so a shift that straddles the period edge is still paired.
    win_from = _local_midnight_utc(d_from) - timedelta(days=8)   # reach back to the Monday of the first week
    win_to   = _local_midnight_utc(d_to + timedelta(days=1)) + timedelta(days=1)
    events = db.query(ClockEvent).filter(
        ClockEvent.company_id == cid,
        ClockEvent.timestamp >= win_from,
        ClockEvent.timestamp < win_to,
    ).order_by(ClockEvent.employee_id, ClockEvent.timestamp).all()

    by_emp: dict[int, list] = {}
    for ev in events:
        by_emp.setdefault(ev.employee_id, []).append(ev)

    emp_map = {e.id: e for e in db.query(Employee).filter(Employee.company_id == cid).all()}
    now_utc = datetime.utcnow()

    def _in_period(dt_utc: datetime) -> bool:
        return d_from <= _local(dt_utc).date() <= d_to

    result = []
    for eid, evs in by_emp.items():
        emp = emp_map.get(eid)
        if not emp:
            continue
        is_sec = bool((getattr(emp, "security_grade", None) or "").strip())
        pairs, problems = _pair_events_ex(evs)
        exceptions = [{"type": p["type"], "message": p["message"]} for p in problems if _in_period(p["at"])]
        sessions_local = []
        all_local = []
        for ev_in, ev_out in pairs:
            if ev_out is not None:
                all_local.append((_round_dt(_local(ev_in.timestamp), round_minutes), _round_dt(_local(ev_out.timestamp), round_minutes)))
            if not _in_period(ev_in.timestamp):
                continue                       # belongs to the neighbouring period
            if ev_out is None:
                still_on = (now_utc - ev_in.timestamp) < timedelta(hours=16)
                exceptions.append({"type": "still_clocked_in" if still_on else "missing_clock_out",
                                   "message": f"Clocked in {_local(ev_in.timestamp):%a %d %b %H:%M} and not clocked out" +
                                              (" (may still be on shift)" if still_on else " - shift not paid")})
                continue
            lin = _round_dt(_local(ev_in.timestamp), round_minutes)
            lout = _round_dt(_local(ev_out.timestamp), round_minutes)
            if (lout - lin) > timedelta(hours=16):
                exceptions.append({"type": "long_shift",
                                   "message": f"Shift of {(lout - lin).total_seconds() / 3600:.1f}h starting {lin:%a %d %b %H:%M} - check for a missed punch"})
            sessions_local.append((lin, lout))

        if is_sec:
            agg = _aggregate_security(sessions_local, d_from, d_to, all_local)
            totals = {"normal_hours": 0.0, "ot_hours": agg["ot_hours"], "sunday_hours": agg["sunday_hours"],
                      "ph_hours": agg["ph_hours"], "night_shift_shifts": agg["night_shift_shifts"]}
            worked = agg["total_hours"]
        else:
            totals = {"normal_hours": 0.0, "ot_hours": 0.0, "sunday_hours": 0.0, "ph_hours": 0.0, "night_shift_shifts": 0}
            daily: dict = {}
            worked = 0.0
            for lin, lout in sessions_local:
                b = _bucket_hours(lin, lout, daily_threshold, daily)
                for k in totals:
                    totals[k] += b[k]
                worked += (lout - lin).total_seconds() / 3600.0

        if not sessions_local and not exceptions:
            continue
        result.append({
            "employee_id":         eid,
            "employee_number":     emp.employee_number or str(eid),
            "name":                _emp_name(emp),
            "is_security":         is_sec,
            "apply_normal_hours":  not is_sec,
            "hours_worked":        round(worked, 2),
            "normal_hours":        round(totals["normal_hours"], 2),
            "ot_hours":            round(totals["ot_hours"], 2),
            "sunday_hours":        round(totals["sunday_hours"], 2),
            "ph_hours":            round(totals["ph_hours"], 2),
            "night_shift_shifts":  int(totals["night_shift_shifts"]),
            "exceptions":          exceptions,
        })
    return result


# ── GET /clocking/export-csv — download OT CSV matching Zuzan upload template ─

@router.get("/export-csv")
async def export_csv(
    date_from:       str   = Query(...),
    date_to:         str   = Query(...),
    daily_threshold: float = Query(8.0),
    round_minutes:   int   = Query(15),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Download a CSV of aggregated hours in the exact format that Zuzan's
    'Upload overtime from file' slot expects:
    Employee Number, Employee Name, Normal_Hours, Weekday_OT_Hours,
    Sunday_Hours, PH_Hours, Night_Shift_Shifts, Special_Allow_Shifts
    """
    rows = await payroll_hours(
        date_from=date_from, date_to=date_to,
        daily_threshold=daily_threshold, round_minutes=round_minutes,
        current_user=current_user, db=db,
    )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Employee Number", "Employee Name",
        "Normal_Hours", "Weekday_OT_Hours",
        "Sunday_Hours", "PH_Hours",
        "Night_Shift_Shifts", "Special_Allow_Shifts",
    ])
    for r in rows:
        writer.writerow([
            r["employee_number"], r["name"],
            (r["normal_hours"] if r.get("apply_normal_hours", True) else 208), r["ot_hours"],
            r["sunday_hours"], r["ph_hours"],
            r["night_shift_shifts"], 0,
        ])
    output.seek(0)
    filename = f"clocking_{date_from}_{date_to}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── DELETE /clocking/event/{id} — manager corrects a clock event ─────────────

@router.delete("/event/{event_id}")
async def delete_event(
    event_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ev = db.query(ClockEvent).filter(
        ClockEvent.id == event_id,
        ClockEvent.company_id == current_user.company_id,
    ).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")
    db.delete(ev)
    db.commit()
    log_action(db, current_user.company_id, current_user.id, "clock_event_deleted",
               f"Deleted clock event {event_id}")
    return {"status": "deleted"}


# ── PATCH /clocking/event/{id} — manager edits timestamp ─────────────────────

class EventPatch(BaseModel):
    timestamp:  Optional[datetime] = None
    event_type: Optional[str]      = None
    notes:      Optional[str]      = None

@router.patch("/event/{event_id}")
async def patch_event(
    event_id: int,
    data: EventPatch,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ev = db.query(ClockEvent).filter(
        ClockEvent.id == event_id,
        ClockEvent.company_id == current_user.company_id,
    ).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")
    if data.timestamp:  ev.timestamp  = _to_utc_naive(data.timestamp)
    if data.event_type: ev.event_type = data.event_type
    if data.notes is not None: ev.notes = data.notes
    ev.created_by = current_user.id
    db.commit()
    log_action(db, current_user.company_id, current_user.id, "clock_event_edited",
               f"Edited clock event {event_id}")
    return {"id": ev.id, "timestamp": _utc_iso(ev.timestamp), "event_type": ev.event_type}


# ── POST /clocking/manual — manager adds a clock event manually ───────────────

class ManualEvent(BaseModel):
    employee_id: int
    event_type:  str
    timestamp:   datetime
    notes:       Optional[str] = None

@router.post("/manual")
async def add_manual_event(
    data: ManualEvent,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    emp = db.query(Employee).filter(
        Employee.id == data.employee_id,
        Employee.company_id == current_user.company_id,
    ).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    ev = ClockEvent(
        company_id=current_user.company_id,
        employee_id=data.employee_id,
        event_type=data.event_type,
        timestamp=_to_utc_naive(data.timestamp),
        method="manual",
        notes=data.notes,
        created_by=current_user.id,
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    log_action(db, current_user.company_id, current_user.id, "clock_event_manual",
               f"Manual clock {data.event_type} for {_emp_name(emp)} at {data.timestamp}")
    return {"id": ev.id, "employee": _emp_name(emp), "event_type": ev.event_type,
            "timestamp": _utc_iso(ev.timestamp), "method": "manual"}
