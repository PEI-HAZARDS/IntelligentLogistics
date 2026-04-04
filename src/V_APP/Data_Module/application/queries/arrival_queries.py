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
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, case, Integer

from infrastructure.persistence.sql_models import (
    Appointment, Visit, Shift, Cargo, Booking, Gate, ShiftType, Company, Driver,
)


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
                query = query.filter(Appointment.status.in_(statuses_list))
        else:
            query = query.filter(Appointment.status == status)
    if scheduled_date:
        query = query.filter(func.date(Appointment.scheduled_start_time) == scheduled_date)
    if search:
        term = f"%{search.upper()}%"
        query = query.filter(func.upper(Appointment.truck_license_plate).like(term))
    if highway_infraction is not None:
        query = query.filter(Appointment.highway_infraction == highway_infraction)
    return query


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
    query = db.query(Appointment)
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
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if appointment and appointment.arrival_id is None:
        ensure_arrival_id(db, appointment)
    return appointment


def get_appointment_detail(db: Session, appointment_id: int) -> Optional[Dict[str, Any]]:
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        return None
    if appointment.arrival_id is None:
        ensure_arrival_id(db, appointment)

    driver_info = None
    if appointment.driver:
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
    return db.query(Appointment).filter(Appointment.arrival_id == arrival_id).first()


def get_appointments_by_license_plate(
    db: Session,
    license_plate: str,
    shift_gate_id: Optional[int] = None,
    shift_type: Optional[ShiftType] = None,
    shift_date: Optional[date] = None,
    status: Optional[str] = None,
    scheduled_date: Optional[date] = None
) -> List[Appointment]:
    query = db.query(Appointment).filter(Appointment.truck_license_plate == license_plate)
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


def get_appointments_for_decision(db: Session, gate_id: Optional[int] = None) -> List[Dict[str, Any]]:
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
            Appointment.status.in_(['in_transit', 'delayed'])
        ),
        and_(
            Appointment.scheduled_start_time.between(yesterday_start, yesterday_end),
            Appointment.status == 'delayed'
        )
    )
    query = db.query(Appointment).filter(time_filters)
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
            "status": a.status,
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

    delayed_filter = [Appointment.status == "delayed", Appointment.scheduled_start_time < start_dt]
    if gate_id:
        delayed_filter.append(Appointment.gate_in_id == gate_id)

    in_process_filter = [Appointment.status == "in_process", Appointment.scheduled_start_time < start_dt]
    if gate_id:
        in_process_filter.append(Appointment.gate_in_id == gate_id)

    unloading_filter = [Appointment.status == "unloading", Appointment.scheduled_start_time < start_dt]
    if gate_id:
        unloading_filter.append(Appointment.gate_in_id == gate_id)

    status_query = db.query(Appointment.status, func.count(Appointment.id)).filter(*base_filter)
    delayed_query = db.query(func.count(Appointment.id)).filter(*delayed_filter)
    in_process_query = db.query(func.count(Appointment.id)).filter(*in_process_filter)
    unloading_query = db.query(func.count(Appointment.id)).filter(*unloading_filter)
    infractions_query = db.query(func.count(Appointment.id)).filter(*base_filter, Appointment.highway_infraction == True)  # noqa: E712
    infractions_delayed_query = db.query(func.count(Appointment.id)).filter(*delayed_filter, Appointment.highway_infraction == True)  # noqa: E712
    infractions_in_process_query = db.query(func.count(Appointment.id)).filter(*in_process_filter, Appointment.highway_infraction == True)  # noqa: E712

    results = status_query.group_by(Appointment.status).all()
    delayed_count = delayed_query.scalar() or 0
    in_process_count = in_process_query.scalar() or 0
    unloading_count = unloading_query.scalar() or 0
    infractions_count = infractions_query.scalar() or 0
    infractions_delayed_count = infractions_delayed_query.scalar() or 0
    infractions_in_process_count = infractions_in_process_query.scalar() or 0

    counts = {"scheduled": 0, "in_transit": 0, "in_process": 0, "unloading": 0, "delayed": 0, "canceled": 0, "completed": 0, "total": 0, "infractions": 0}
    for status, count in results:
        if status in counts:
            counts[status] = count
        counts["total"] += count
    counts["delayed"] += delayed_count
    counts["total"] += delayed_count
    counts["in_process"] += in_process_count
    counts["total"] += in_process_count
    counts["unloading"] += unloading_count
    counts["total"] += unloading_count
    counts["infractions"] = infractions_count + infractions_delayed_count + infractions_in_process_count
    return counts


def update_appointment_status(db: Session, appointment_id: int, new_status: str, notes: Optional[str] = None) -> Optional[Appointment]:
    """DEPRECATED — bypasses UoW + Outbox.  Changes made here will
    NOT propagate to MongoDB or Redis.  Use
    ``appointment_commands.cmd_update_status`` instead.
    """
    import warnings
    warnings.warn(
        "update_appointment_status bypasses UoW + Outbox — use cmd_update_status",
        DeprecationWarning,
        stacklevel=2,
    )
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        return None
    appointment.status = new_status
    if notes:
        appointment.notes = notes
    db.commit()
    db.refresh(appointment)
    if appointment.arrival_id is None:
        ensure_arrival_id(db, appointment)
    return appointment


def create_visit_for_appointment(
    db: Session,
    appointment_id: int,
    shift_gate_id: int,
    shift_type: ShiftType,
    shift_date: date,
    entry_time: Optional[datetime] = None
) -> Optional[Visit]:
    """DEPRECATED — bypasses UoW + Outbox.  Changes made here will
    NOT propagate to MongoDB or Redis.  Use
    ``appointment_commands.cmd_create_visit`` instead.
    """
    import warnings
    warnings.warn(
        "create_visit_for_appointment bypasses UoW + Outbox — use cmd_create_visit",
        DeprecationWarning,
        stacklevel=2,
    )
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        return None
    existing_visit = db.query(Visit).filter(Visit.appointment_id == appointment_id).first()
    if existing_visit:
        return existing_visit
    visit = Visit(
        appointment_id=appointment_id,
        shift_gate_id=shift_gate_id,
        shift_type=shift_type,
        shift_date=shift_date,
        entry_time=entry_time or datetime.now(),
        state='unloading'
    )
    db.add(visit)
    db.commit()
    db.refresh(visit)
    return visit


def update_visit_status(db: Session, appointment_id: int, new_state: str, out_time: Optional[datetime] = None) -> Optional[Visit]:
    """DEPRECATED — bypasses UoW + Outbox.  Changes made here will
    NOT propagate to MongoDB or Redis.  Use
    ``appointment_commands.cmd_update_visit_state`` instead.
    """
    import warnings
    warnings.warn(
        "update_visit_status bypasses UoW + Outbox — use cmd_update_visit_state",
        DeprecationWarning,
        stacklevel=2,
    )
    visit = db.query(Visit).filter(Visit.appointment_id == appointment_id).first()
    if not visit:
        return None
    visit.state = new_state
    if out_time:
        visit.out_time = out_time
    elif new_state == 'completed':
        visit.out_time = datetime.now()
    db.commit()
    db.refresh(visit)
    return visit


def update_appointment_from_decision(db: Session, appointment_id: int, decision_payload: Dict[str, Any]) -> Optional[Appointment]:
    """DEPRECATED — bypasses UoW + Outbox.  Changes made here will
    NOT propagate to MongoDB or Redis.  Use
    ``appointment_commands.cmd_process_decision`` instead.
    """
    import warnings
    warnings.warn(
        "update_appointment_from_decision bypasses UoW + Outbox — use cmd_process_decision",
        DeprecationWarning,
        stacklevel=2,
    )
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        return None
    if "status" in decision_payload:
        appointment.status = decision_payload["status"]
    if "notes" in decision_payload:
        appointment.notes = decision_payload["notes"]
    db.commit()
    db.refresh(appointment)
    if appointment.arrival_id is None:
        ensure_arrival_id(db, appointment)
    # Create alerts if present — delegate to alert handler
    if "alerts" in decision_payload and decision_payload["alerts"]:
        from application.use_cases.alert_handlers import create_alerts_for_appointment
        from infrastructure.persistence.postgres import SessionLocal
        create_alerts_for_appointment(
            lambda: __import__('infrastructure.persistence.unit_of_work', fromlist=['SqlAlchemyUnitOfWork']).SqlAlchemyUnitOfWork(SessionLocal),
            appointment_id=appointment.id,
            alerts_payload=decision_payload["alerts"],
        )
    return appointment


def flag_appointment_highway_infraction(db: Session, appointment_id: int) -> Optional[Appointment]:
    """DEPRECATED — bypasses UoW + Outbox.  Changes made here will
    NOT propagate to MongoDB or Redis.  Use
    ``appointment_commands.cmd_flag_highway_infraction`` instead.
    """
    import warnings
    warnings.warn(
        "flag_appointment_highway_infraction bypasses UoW + Outbox — use cmd_flag_highway_infraction",
        DeprecationWarning,
        stacklevel=2,
    )
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        return None
    appointment.highway_infraction = True
    db.commit()
    db.refresh(appointment)
    if appointment.arrival_id is None:
        ensure_arrival_id(db, appointment)
    return appointment


def get_next_appointments(db: Session, gate_id: int, limit: int = 5, status: Optional[str] = None) -> List[Appointment]:
    today = date.today()
    from sqlalchemy import case as sa_case
    status_priority = sa_case((Appointment.status == 'delayed', 0), else_=1)
    base_filters = [
        Appointment.gate_in_id == gate_id,
        func.date(Appointment.scheduled_start_time) == today,
    ]
    if status:
        base_filters.append(Appointment.status == status)
    else:
        base_filters.append(Appointment.status.in_(['in_transit', 'delayed']))
    appointments = db.query(Appointment).filter(*base_filters).order_by(
        status_priority, Appointment.scheduled_start_time.asc()
    ).limit(limit).all()
    for appointment in appointments:
        if appointment.arrival_id is None:
            ensure_arrival_id(db, appointment)
    return appointments


def get_transport_stats_by_company(db: Session, target_date: Optional[date] = None, days: int = 30) -> List[Dict[str, Any]]:
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
