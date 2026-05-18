"""
Arrival / Appointment queries and mutations.
Relocated from services/arrival_service.py — internal cross-references
updated to point at application.use_cases / application.queries.

NOTE: This module still uses SQLAlchemy for write mutations and complex
Postgres queries (visits, company KPIs).  Reads that CAN be served from
MongoDB should be migrated incrementally.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, date, time, timedelta
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func, and_, or_, case, Integer

from infrastructure.persistence.sql_models import (
    Appointment, Visit, Shift, Cargo, Booking, Gate, ShiftType, Company, Driver,
    DELAY_TOLERANCE_MINUTES,
)


def _delayed_condition():
    """SQLAlchemy condition: appointment is effectively delayed.

    Matches rows stored as 'delayed' (backward compat) and rows that are
    'in_transit' past the delay tolerance threshold.

    scheduled_start_time is stored as UTC naive datetime (Docker containers
    run with TZ=UTC). cutoff uses UTC naive to match.
    """
    from datetime import timezone as _tz
    cutoff = datetime.now(_tz.utc).replace(tzinfo=None) - timedelta(minutes=DELAY_TOLERANCE_MINUTES)
    return or_(
        Appointment.status == 'delayed',
        and_(
            Appointment.status == 'in_transit',
            Appointment.scheduled_start_time.isnot(None),
            Appointment.scheduled_start_time < cutoff,
        ),
    )


def _in_transit_ontime_condition():
    """SQLAlchemy condition: in_transit and not yet past the delay threshold."""
    from datetime import timezone as _tz
    cutoff = datetime.now(_tz.utc).replace(tzinfo=None) - timedelta(minutes=DELAY_TOLERANCE_MINUTES)
    return and_(
        Appointment.status == 'in_transit',
        or_(
            Appointment.scheduled_start_time.is_(None),
            Appointment.scheduled_start_time >= cutoff,
        ),
    )


def _unloading_condition():
    """SQLAlchemy condition: appointment is in the unloading sub-state.

    Matches in_process appointments with an active Visit in unloading state,
    plus backward-compat rows stored with status='unloading'.
    """
    return or_(
        Appointment.status == 'unloading',
        and_(
            Appointment.status == 'in_process',
            Appointment.id.in_(
                # subquery: appointment_ids with an active unloading Visit
                # (using a raw subselect to avoid JOIN conflicts in callers)
                __import__('sqlalchemy').select(Visit.appointment_id).where(
                    and_(
                        Visit.state == 'unloading',
                        Visit.out_time.is_(None),
                    )
                )
            ),
        ),
    )


def _resolve_status_filter(status: str):
    """Translate a ?status= query param to the correct SQLAlchemy condition.

    Handles virtual sub-states 'delayed' and 'unloading' that are no longer
    stored as primary values in Appointment.status.

    'in_transit' maps to on-time only — delayed in_transit appointments are
    returned by 'delayed' filter instead, keeping the two filters disjoint.
    """
    if status == 'delayed':
        return _delayed_condition()
    if status == 'unloading':
        return _unloading_condition()
    if status == 'in_transit':
        return _in_transit_ontime_condition()
    return Appointment.status == status


def ensure_arrival_id(db: Session, appointment: Appointment) -> Appointment:
    if appointment.arrival_id:
        return appointment
    db.refresh(appointment)
    return appointment


def _apply_appointment_filters(query, gate_id, shift_gate_id, shift_type, shift_date, status, scheduled_date, search, highway_infraction=None):
    if gate_id:
        query = query.filter(Appointment.gate_in_id == gate_id)
    if shift_gate_id and shift_type and shift_date:
        query = query.join(Visit, isouter=True).filter(
            Visit.shift_gate_id == shift_gate_id,
            Visit.shift_type == shift_type,
            Visit.shift_date == shift_date
        )
    if status:
        if ',' in status:
            statuses_list = [s.strip() for s in status.split(',') if s.strip()]
            if statuses_list:
                conditions = [_resolve_status_filter(s) for s in statuses_list]
                query = query.filter(or_(*conditions))
        else:
            query = query.filter(_resolve_status_filter(status))
    if scheduled_date:
        query = query.filter(func.date(Appointment.scheduled_start_time) == scheduled_date)
    if search:
        term = f"%{search.upper()}%"
        query = query.filter(func.upper(Appointment.truck_license_plate).like(term))
    if highway_infraction is not None:
        query = query.filter(Appointment.highway_infraction == highway_infraction)
    return query


_APPOINTMENT_EAGER_LOADS = [
    selectinload(Appointment.booking).selectinload(Booking.cargos),
    selectinload(Appointment.driver).selectinload(Driver.company),
    selectinload(Appointment.truck),
    selectinload(Appointment.terminal),
    selectinload(Appointment.gate_in),
    selectinload(Appointment.gate_out),
    selectinload(Appointment.visit),
]


def get_all_appointments(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    gate_id: Optional[int] = None,
    shift_gate_id: Optional[int] = None,
    shift_type: Optional[ShiftType] = None,
    shift_date: Optional[date] = None,
    status: Optional[str] = None,
    scheduled_date: Optional[date] = None,
    search: Optional[str] = None,
    highway_infraction: Optional[bool] = None,
) -> List[Appointment]:
    query = db.query(Appointment).options(*_APPOINTMENT_EAGER_LOADS)
    query = _apply_appointment_filters(
        query, gate_id, shift_gate_id, shift_type, shift_date, status, scheduled_date, search,
        highway_infraction=highway_infraction,
    )
    appointments = query.order_by(Appointment.scheduled_start_time.asc()).offset(skip).limit(limit).all()
    for appointment in appointments:
        if appointment.arrival_id is None:
            ensure_arrival_id(db, appointment)
    return appointments


def count_all_appointments(
    db: Session,
    gate_id: Optional[int] = None,
    shift_gate_id: Optional[int] = None,
    shift_type: Optional[ShiftType] = None,
    shift_date: Optional[date] = None,
    status: Optional[str] = None,
    scheduled_date: Optional[date] = None,
    search: Optional[str] = None,
    highway_infraction: Optional[bool] = None,
) -> int:
    query = db.query(func.count(Appointment.id))
    query = _apply_appointment_filters(
        query, gate_id, shift_gate_id, shift_type, shift_date, status, scheduled_date, search,
        highway_infraction=highway_infraction,
    )
    return query.scalar() or 0


def get_appointment_by_id(db: Session, appointment_id: int) -> Optional[Appointment]:
    appointment = (
        db.query(Appointment)
        .options(*_APPOINTMENT_EAGER_LOADS)
        .filter(Appointment.id == appointment_id)
        .first()
    )
    if appointment and appointment.arrival_id is None:
        ensure_arrival_id(db, appointment)
    return appointment


def get_appointment_detail(db: Session, appointment_id: int) -> Optional[Dict[str, Any]]:
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        return None
    if appointment.arrival_id is None:
        ensure_arrival_id(db, appointment)

    # Privacy by Design: infraction is associated with the truck, not the driver.
    # Suppress all driver identity fields when highway_infraction is set so
    # the logistics manager cannot correlate an infraction with a specific driver.
    driver_info = None
    if appointment.driver and not appointment.highway_infraction:
        driver_info = {
            "license": appointment.driver.drivers_license,
            "name": appointment.driver.name,
            "phone": appointment.driver.mobile_device_token,
            "company": {
                "nif": appointment.driver.company.nif,
                "name": appointment.driver.company.name,
                "contact": appointment.driver.company.contact,
            } if appointment.driver.company else None
        }

    truck_info = None
    if appointment.truck:
        truck_info = {
            "license_plate": appointment.truck.license_plate,
            "brand": appointment.truck.brand,
        }

    booking_info = None
    if appointment.booking:
        cargos = []
        if appointment.booking.cargos:
            for cargo in appointment.booking.cargos:
                cargos.append({
                    "id": cargo.id,
                    "description": cargo.description,
                    "state": cargo.state,
                    "quantity": float(cargo.quantity) if cargo.quantity else None,
                })
        booking_info = {
            "reference": appointment.booking.reference,
            "direction": appointment.booking.direction,
            "scheduled_unloading": appointment.booking.scheduled_unloading.isoformat() if getattr(appointment.booking, 'scheduled_unloading', None) else None,
            "origin": getattr(appointment.booking, 'origin', None),
            "destination": getattr(appointment.booking, 'destination', None),
            "cargos": cargos,
        }

    gate_in_info = None
    if appointment.gate_in:
        gate_in_info = {
            "id": appointment.gate_in.id,
            "name": getattr(appointment.gate_in, 'name', appointment.gate_in.label),
            "terminal_id": getattr(appointment.gate_in, 'terminal_id', None),
        }

    gate_out_info = None
    if appointment.gate_out:
        gate_out_info = {
            "id": appointment.gate_out.id,
            "name": getattr(appointment.gate_out, 'name', appointment.gate_out.label),
            "terminal_id": getattr(appointment.gate_out, 'terminal_id', None),
        }

    terminal_info = None
    if appointment.terminal:
        terminal_info = {
            "id": appointment.terminal.id,
            "name": appointment.terminal.name,
            "location": getattr(appointment.terminal, 'location', None),
        }

    visit_info = None
    if appointment.visit:
        visit_info = {
            "appointment_id": appointment.visit.appointment_id,
            "shift_gate_id": appointment.visit.shift_gate_id,
            "shift_type": appointment.visit.shift_type.name if appointment.visit.shift_type else None,
            "shift_date": appointment.visit.shift_date.isoformat() if appointment.visit.shift_date else None,
            "entry_time": appointment.visit.entry_time.isoformat() if appointment.visit.entry_time else None,
            "out_time": appointment.visit.out_time.isoformat() if appointment.visit.out_time else None,
            "state": appointment.visit.state,
        }

    return {
        "id": appointment.id,
        "arrival_id": appointment.arrival_id,
        "status": appointment.status,
        "scheduled_start_time": appointment.scheduled_start_time.isoformat() if appointment.scheduled_start_time else None,
        "expected_duration": appointment.expected_duration,
        "notes": appointment.notes,
        "highway_infraction": appointment.highway_infraction,
        "driver": driver_info,
        "truck": truck_info,
        "booking": booking_info,
        "gate_in": gate_in_info,
        "gate_out": gate_out_info,
        "terminal": terminal_info,
        "visit": visit_info,
    }


def get_appointment_by_arrival_id(db: Session, arrival_id: str) -> Optional[Appointment]:
    return (
        db.query(Appointment)
        .options(*_APPOINTMENT_EAGER_LOADS)
        .filter(Appointment.arrival_id == arrival_id)
        .first()
    )


def get_appointments_by_license_plate(
    db: Session,
    license_plate: str,
    shift_gate_id: Optional[int] = None,
    shift_type: Optional[ShiftType] = None,
    shift_date: Optional[date] = None,
    status: Optional[str] = None,
    scheduled_date: Optional[date] = None
) -> List[Appointment]:
    query = db.query(Appointment).options(*_APPOINTMENT_EAGER_LOADS).filter(Appointment.truck_license_plate == license_plate)
    if shift_gate_id and shift_type and shift_date:
        query = query.join(Visit).filter(
            Visit.shift_gate_id == shift_gate_id,
            Visit.shift_type == shift_type,
            Visit.shift_date == shift_date
        )
    if status:
        query = query.filter(Appointment.status == status)
    if scheduled_date:
        query = query.filter(func.date(Appointment.scheduled_start_time) == scheduled_date)
    else:
        query = query.filter(func.date(Appointment.scheduled_start_time) == date.today())
    appointments = query.order_by(Appointment.scheduled_start_time.asc()).all()
    for appointment in appointments:
        if appointment.arrival_id is None:
            ensure_arrival_id(db, appointment)
    return appointments


def get_appointments_for_decision(db: Session, gate_id: Optional[int] = None) -> List[Dict[str, Any]]:  # noqa: E501
    today = date.today()
    yesterday = today - timedelta(days=1)
    day_start = datetime.combine(today, datetime.min.time())
    day_end = datetime.combine(today, datetime.max.time())
    yesterday_start = datetime.combine(yesterday, datetime.min.time())
    yesterday_end = datetime.combine(yesterday, datetime.max.time())

    current_shift = None
    if gate_id:
        current_shift = db.query(Shift).filter(Shift.date == today, Shift.gate_id == gate_id).first()

    time_filters = or_(
        and_(
            Appointment.scheduled_start_time.between(day_start, day_end),
            Appointment.status == 'in_transit',
        ),
        and_(
            Appointment.scheduled_start_time.between(yesterday_start, yesterday_end),
            Appointment.status == 'in_transit',
        )
    )
    query = db.query(Appointment).options(*_APPOINTMENT_EAGER_LOADS).filter(time_filters)
    if gate_id:
        query = query.filter(Appointment.gate_in_id == gate_id)
    appointments = query.order_by(Appointment.scheduled_start_time.asc()).all()
    for appointment in appointments:
        if appointment.arrival_id is None:
            ensure_arrival_id(db, appointment)

    result = []
    for a in appointments:
        cargo = None
        if a.booking and a.booking.cargos:
            c = a.booking.cargos[0]
            cargo = {
                "id": c.id,
                "description": c.description,
                "state": c.state,
                "quantity": float(c.quantity) if c.quantity else None
            }
        result.append({
            "appointment_id": a.id,
            "license_plate": a.truck_license_plate,
            "gate_in_id": a.gate_in_id,
            "terminal_id": a.terminal_id,
            "shift_gate_id": current_shift.gate_id if current_shift else None,
            "shift_type": current_shift.shift_type.name if current_shift and current_shift.shift_type else None,
            "shift_date": current_shift.date.isoformat() if current_shift else None,
            "scheduled_time": a.scheduled_start_time.isoformat() if a.scheduled_start_time else None,
            "status": a.computed_status,           # display_status (compat)
            "display_status": a.computed_status,   # explicit alias for new consumers
            "primary_status": a.status,            # raw DB state (never delayed/unloading)
            "is_delayed": a.is_delayed,
            "is_unloading": a.is_unloading,
            "highway_infraction": a.highway_infraction,
            "cargo": cargo,
            "booking": {
                "reference": a.booking.reference,
                "direction": a.booking.direction
            } if a.booking else None
        })
    return result


def get_appointments_count_by_status(
    db: Session, gate_id: Optional[int] = None, target_date: Optional[date] = None
) -> Dict[str, int]:
    date_filter = target_date or date.today()
    start_dt = datetime.combine(date_filter, time.min)
    end_dt = datetime.combine(date_filter, time.max)
    base_filter = [
        Appointment.scheduled_start_time >= start_dt,
        Appointment.scheduled_start_time <= end_dt
    ]
    if gate_id:
        base_filter.append(Appointment.gate_in_id == gate_id)

    # Use the same conditions as _resolve_status_filter so stat card counts
    # are consistent with what each filter returns in the list.
    gate_filter = [Appointment.gate_in_id == gate_id] if gate_id else []

    def _q(condition):
        return db.query(func.count(Appointment.id)).filter(condition, *gate_filter)

    scheduled_count   = _q(and_(Appointment.status == "scheduled",   Appointment.scheduled_start_time.between(start_dt, end_dt))).scalar() or 0
    in_transit_count  = _q(and_(_in_transit_ontime_condition(),       Appointment.scheduled_start_time.between(start_dt, end_dt))).scalar() or 0
    delayed_count     = _q(_delayed_condition()).scalar() or 0
    in_process_count  = _q(and_(Appointment.status == "in_process",  Appointment.scheduled_start_time.between(start_dt, end_dt))).scalar() or 0
    unloading_count   = _q(and_(_unloading_condition(),               Appointment.scheduled_start_time.between(start_dt, end_dt))).scalar() or 0
    completed_count   = _q(and_(Appointment.status == "completed",   Appointment.scheduled_start_time.between(start_dt, end_dt))).scalar() or 0
    canceled_count    = _q(and_(Appointment.status == "canceled",    Appointment.scheduled_start_time.between(start_dt, end_dt))).scalar() or 0
    infractions_count = db.query(func.count(Appointment.id)).filter(
        Appointment.highway_infraction == True,  # noqa: E712
        Appointment.scheduled_start_time.between(start_dt, end_dt),
        *gate_filter,
    ).scalar() or 0

    total = scheduled_count + in_transit_count + delayed_count + in_process_count + unloading_count + completed_count + canceled_count

    return {
        "scheduled":   scheduled_count,
        "in_transit":  in_transit_count,
        "delayed":     delayed_count,
        "in_process":  in_process_count,
        "unloading":   unloading_count,
        "completed":   completed_count,
        "canceled":    canceled_count,
        "total":       total,
        "infractions": infractions_count,
    }




def get_next_appointments(db: Session, gate_id: int, limit: int = 5, status: Optional[str] = None) -> List[Appointment]:
    today = date.today()
    from sqlalchemy import case as sa_case
    status_priority = sa_case((_delayed_condition(), 0), else_=1)
    base_filters = [
        Appointment.gate_in_id == gate_id,
        func.date(Appointment.scheduled_start_time) == today,
    ]
    if status:
        base_filters.append(Appointment.status == status)
    else:
        base_filters.append(Appointment.status == 'in_transit')
    appointments = db.query(Appointment).options(*_APPOINTMENT_EAGER_LOADS).filter(*base_filters).order_by(
        status_priority, Appointment.scheduled_start_time.asc()
    ).limit(limit).all()
    for appointment in appointments:
        if appointment.arrival_id is None:
            ensure_arrival_id(db, appointment)
    return appointments


def get_transport_stats_by_company(db: Session, target_date: Optional[date] = None, days: int = 30) -> List[Dict[str, Any]]:
    """DEPRECATED — use manager_statistics_queries.get_transport_stats instead."""
    import warnings
    warnings.warn(
        "get_transport_stats_by_company is deprecated — use manager_statistics_queries.get_transport_stats",
        DeprecationWarning,
        stacklevel=2,
    )
    end_date = target_date or date.today()
    start_date = end_date - timedelta(days=days)
    rows = (
        db.query(
            Company.nif, Company.name,
            func.count(func.distinct(Appointment.id)).label("ops_count"),
            func.avg(func.extract('epoch', Visit.out_time) - func.extract('epoch', Visit.entry_time)).label("avg_duration_seconds"),
            func.avg(case((func.extract('epoch', Visit.entry_time) > func.extract('epoch', Appointment.scheduled_start_time), func.extract('epoch', Visit.entry_time) - func.extract('epoch', Appointment.scheduled_start_time)), else_=None)).label("avg_wait_seconds"),
            func.sum(case((Appointment.status == 'completed', 1), else_=0)).label("completed_count"),
        )
        .join(Driver, Appointment.driver_license == Driver.drivers_license)
        .join(Company, Driver.company_nif == Company.nif)
        .outerjoin(Visit, Visit.appointment_id == Appointment.id)
        .filter(func.date(Appointment.scheduled_start_time) >= start_date, func.date(Appointment.scheduled_start_time) <= end_date)
        .group_by(Company.nif, Company.name)
        .all()
    )
    results = []
    for nif, name, ops_count, avg_dur, avg_wait, completed in rows:
        avg_unloading = round(abs(avg_dur or 0) / 60, 1)
        avg_waiting = round((avg_wait or 0) / 60, 1)
        sla_rate = round((completed or 0) / ops_count * 100, 1) if ops_count > 0 else 0
        results.append({"companyName": name, "companyNif": nif, "avgUnloadingTime": avg_unloading, "avgWaitingTime": avg_waiting, "operationsCount": ops_count, "slaAttendedRate": sla_rate})
    return sorted(results, key=lambda x: x["operationsCount"], reverse=True)


def get_avg_permanence_minutes(db: Session, target_date: Optional[date] = None) -> float:
    query = db.query(func.avg(func.extract('epoch', Visit.out_time) - func.extract('epoch', Visit.entry_time))).filter(Visit.entry_time.isnot(None), Visit.out_time.isnot(None))
    if target_date:
        query = query.filter(func.date(Visit.entry_time) == target_date)
    result = query.scalar()
    return round(abs(result or 0) / 60, 1)
