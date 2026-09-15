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
import secrets
from datetime import datetime, timedelta, date, time as dtime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db, Company, Employee, ClockEvent, User
from auth import get_current_user, log_action

router = APIRouter()

# ── South African public holidays (fixed dates; Easter-based ones approximated) ──
# Extend this list each year or fetch from a public API.
_SA_PUBLIC_HOLIDAYS_2026 = {
    date(2026, 1, 1),   # New Year's Day
    date(2026, 3, 21),  # Human Rights Day
    date(2026, 4, 3),   # Good Friday (approx)
    date(2026, 4, 6),   # Family Day (approx)
    date(2026, 4, 27),  # Freedom Day
    date(2026, 5, 1),   # Workers' Day
    date(2026, 6, 16),  # Youth Day
    date(2026, 8, 9),   # National Women's Day (observed Mon 10 Aug)
    date(2026, 8, 10),  # Women's Day observed
    date(2026, 9, 24),  # Heritage Day
    date(2026, 12, 16), # Day of Reconciliation
    date(2026, 12, 25), # Christmas Day
    date(2026, 12, 26), # Day of Goodwill
}
_SA_PUBLIC_HOLIDAYS_2027 = {
    date(2027, 1, 1),
    date(2027, 3, 21),
    date(2027, 3, 26),  # Good Friday
    date(2027, 3, 29),  # Family Day
    date(2027, 4, 27),
    date(2027, 5, 1),
    date(2027, 6, 16),
    date(2027, 8, 9),
    date(2027, 9, 24),
    date(2027, 12, 16),
    date(2027, 12, 25),
    date(2027, 12, 26),
}

def _is_ph(d: date) -> bool:
    return d in _SA_PUBLIC_HOLIDAYS_2026 or d in _SA_PUBLIC_HOLIDAYS_2027


def _is_night_shift(dt_in: datetime, dt_out: datetime) -> bool:
    """True if any part of the shift falls between 18:00 and 05:59."""
    # Check if the shift overlaps with the night window [18:00, next day 06:00)
    night_start = dt_in.replace(hour=18, minute=0, second=0, microsecond=0)
    next_day_06 = (dt_in + timedelta(days=1)).replace(hour=6, minute=0, second=0, microsecond=0)
    return dt_out > night_start or dt_in < next_day_06.replace(
        year=dt_in.year, month=dt_in.month, day=dt_in.day
    )


def _bucket_hours(dt_in: datetime, dt_out: datetime, daily_threshold: float = 8.0):
    """
    Given a clock-in / clock-out pair, return a dict of categorised hours.
    Shifts crossing midnight are split at midnight and each part bucketed.
    """
    result = {"normal_hours": 0.0, "ot_hours": 0.0,
              "sunday_hours": 0.0, "ph_hours": 0.0,
              "night_shift_shifts": 0}

    # Split at midnight
    segments = []
    current = dt_in
    while current.date() < dt_out.date():
        midnight = (current + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        segments.append((current, midnight))
        current = midnight
    segments.append((current, dt_out))

    for seg_in, seg_out in segments:
        if seg_out <= seg_in:
            continue
        hours = (seg_out - seg_in).total_seconds() / 3600.0
        d = seg_in.date()
        if _is_ph(d):
            result["ph_hours"] += hours
        elif d.weekday() == 6:  # Sunday
            result["sunday_hours"] += hours
        else:
            normal = min(hours, max(0.0, daily_threshold - result["normal_hours"]))
            result["normal_hours"] += normal
            result["ot_hours"] += hours - normal
        # Night-shift counter (per shift pair, not per segment)

    # Night shift: checked on the whole original pair
    night_start = dt_in.replace(hour=18, minute=0, second=0, microsecond=0)
    prev_06 = dt_in.replace(hour=6, minute=0, second=0, microsecond=0)
    if dt_out > night_start or dt_in < prev_06:
        result["night_shift_shifts"] = 1

    return result


def _pair_events(events: list) -> list:
    """
    Convert a flat list of ClockEvent rows (sorted by timestamp) into
    paired (in, out) sessions.  Unmatched trailing 'in' events are open sessions.
    """
    sessions = []
    pending_in = None
    for ev in events:
        if ev.event_type == "in":
            pending_in = ev
        elif ev.event_type == "out" and pending_in is not None:
            sessions.append((pending_in, ev))
            pending_in = None
    if pending_in:
        sessions.append((pending_in, None))  # still clocked in
    return sessions


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
    ).order_by(Employee.name).all()
    return {
        "company_id": company.id,
        "company_name": company.name,
        "employees": [
            {"id": e.id, "name": e.name, "employee_number": e.employee_number or str(e.id)}
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
        timestamp=data.timestamp or datetime.utcnow(),
        method=data.method or "kiosk",
        notes=data.notes,
        created_by=current_user.id,
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return {"id": ev.id, "employee": emp.name, "event_type": ev.event_type,
            "timestamp": ev.timestamp.isoformat()}


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
        timestamp=data.timestamp or datetime.utcnow(),
        method=data.method or "kiosk",
        notes=data.notes,
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return {"id": ev.id, "employee": emp.name, "event_type": ev.event_type,
            "timestamp": ev.timestamp.isoformat()}


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
    ).order_by(Employee.name).all()

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
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
            "name":            emp.name,
            "employee_number": emp.employee_number or str(emp.id),
            "status":          ev.event_type if ev else "out",
            "last_event":      ev.timestamp.isoformat() if ev else None,
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
    ).order_by(Employee.name).all()
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
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
            "name":            emp.name,
            "employee_number": emp.employee_number or str(emp.id),
            "status":          ev.event_type if ev else "out",
            "last_event":      ev.timestamp.isoformat() if ev else None,
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
                "employee_name":   emp_map.get(eid, {}).name if hasattr(emp_map.get(eid), "name") else "?",
                "employee_number": getattr(emp_map.get(eid), "employee_number", None) or str(eid),
                "clock_in_id":     ev_in.id,
                "clock_in":        ev_in.timestamp.isoformat(),
                "clock_in_method": ev_in.method,
                "clock_out_id":    ev_out.id if ev_out else None,
                "clock_out":       ev_out.timestamp.isoformat() if ev_out else None,
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
    daily_threshold: float = Query(8.0,  description="Normal hours per day before OT kicks in"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Aggregate clock events into per-employee hour buckets matching the Zuzan OT modal.
    Returns: normal_hours, ot_hours, sunday_hours, ph_hours, night_shift_shifts per employee.
    """
    cid = current_user.company_id
    try:
        dt_from = datetime.strptime(date_from, "%Y-%m-%d")
        dt_to   = datetime.strptime(date_to,   "%Y-%m-%d") + timedelta(days=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use yyyy-mm-dd")

    events = db.query(ClockEvent).filter(
        ClockEvent.company_id == cid,
        ClockEvent.timestamp >= dt_from,
        ClockEvent.timestamp < dt_to,
    ).order_by(ClockEvent.employee_id, ClockEvent.timestamp).all()

    by_emp: dict[int, list] = {}
    for ev in events:
        by_emp.setdefault(ev.employee_id, []).append(ev)

    emp_map = {e.id: e for e in db.query(Employee).filter(Employee.company_id == cid).all()}

    result = []
    for eid, evs in by_emp.items():
        emp = emp_map.get(eid)
        totals = {"normal_hours": 0.0, "ot_hours": 0.0,
                  "sunday_hours": 0.0, "ph_hours": 0.0,
                  "night_shift_shifts": 0}
        for ev_in, ev_out in _pair_events(evs):
            if ev_out is None:
                continue  # still clocked in — skip open session
            b = _bucket_hours(ev_in.timestamp, ev_out.timestamp, daily_threshold)
            for k in totals:
                totals[k] += b[k]
        if emp:
            result.append({
                "employee_id":         eid,
                "employee_number":     emp.employee_number or str(eid),
                "name":                emp.name,
                "normal_hours":        round(totals["normal_hours"], 2),
                "ot_hours":            round(totals["ot_hours"], 2),
                "sunday_hours":        round(totals["sunday_hours"], 2),
                "ph_hours":            round(totals["ph_hours"], 2),
                "night_shift_shifts":  int(totals["night_shift_shifts"]),
            })
    return result


# ── GET /clocking/export-csv — download OT CSV matching Zuzan upload template ─

@router.get("/export-csv")
async def export_csv(
    date_from:       str   = Query(...),
    date_to:         str   = Query(...),
    daily_threshold: float = Query(8.0),
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
        daily_threshold=daily_threshold,
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
            r["normal_hours"], r["ot_hours"],
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
    if data.timestamp:  ev.timestamp  = data.timestamp
    if data.event_type: ev.event_type = data.event_type
    if data.notes is not None: ev.notes = data.notes
    ev.created_by = current_user.id
    db.commit()
    log_action(db, current_user.company_id, current_user.id, "clock_event_edited",
               f"Edited clock event {event_id}")
    return {"id": ev.id, "timestamp": ev.timestamp.isoformat(), "event_type": ev.event_type}


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
        timestamp=data.timestamp,
        method="manual",
        notes=data.notes,
        created_by=current_user.id,
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    log_action(db, current_user.company_id, current_user.id, "clock_event_manual",
               f"Manual clock {data.event_type} for {emp.name} at {data.timestamp}")
    return {"id": ev.id, "employee": emp.name, "event_type": ev.event_type,
            "timestamp": ev.timestamp.isoformat(), "method": "manual"}
