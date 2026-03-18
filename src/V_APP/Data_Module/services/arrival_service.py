"""
Arrival Service - Manages appointments and visits.
Used by: Operator frontend, Decision Engine, Driver app.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, date, time, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, case, Integer

from infrastructure.persistence.sql_models import Appointment, Visit, Shift, Cargo, Booking, Gate, ShiftType, Company, Driver


def ensure_arrival_id(db: Session, appointment: Appointment) -> Appointment:
    if appointment.arrival_id:
        return appointment

    db.refresh(appointment)
    return appointment


def _apply_appointment_filters(query, gate_id, shift_gate_id, shift_type, shift_date, status, scheduled_date, search):
    """Applies common filters to a query — shared by list and count helpers."""
    if gate_id:
        query = query.filter(Appointment.gate_in_id == gate_id)
    if shift_gate_id and shift_type and shift_date:
        query = query.join(Visit, isouter=True).filter(
            Visit.shift_gate_id == shift_gate_id,
            Visit.shift_type == shift_type,
            Visit.shift_date == shift_date
        )
    if status:
        # Handle multiple statuses (comma-separated) or single status
        if ',' in status:
            # Filter empty strings and strip whitespace
            statuses_list = [s.strip() for s in status.split(',') if s.strip()]
            if statuses_list:  # Only apply filter if list is not empty
                query = query.filter(Appointment.status.in_(statuses_list))
        else:
            query = query.filter(Appointment.status == status)
    if scheduled_date:
        query = query.filter(func.date(Appointment.scheduled_start_time) == scheduled_date)
    if search:
        term = f"%{search.upper()}%"
        query = query.filter(func.upper(Appointment.truck_license_plate).like(term))
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
) -> List[Appointment]:
    """
    Gets appointments with optional filters.
    Used by operator frontend to list arrivals.
    """
    query = db.query(Appointment)
    query = _apply_appointment_filters(
        query, gate_id, shift_gate_id, shift_type, shift_date, status, scheduled_date, search
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
) -> int:
    """Returns total count matching the same filters as get_all_appointments."""
    query = db.query(func.count(Appointment.id))
    query = _apply_appointment_filters(
        query, gate_id, shift_gate_id, shift_type, shift_date, status, scheduled_date, search
    )
    return query.scalar() or 0


def get_appointment_by_id(db: Session, appointment_id: int) -> Optional[Appointment]:
    """Gets a specific appointment by ID."""
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if appointment and appointment.arrival_id is None:
        ensure_arrival_id(db, appointment)
    return appointment


def get_appointment_detail(db: Session, appointment_id: int) -> Optional[Dict[str, Any]]:
    """
    Gets detailed appointment info with all related data.
    Includes: driver + company, booking + cargo, gates, terminal, visit info.
    Returns a formatted dict with all nested relationships.
    """
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        return None
    
    # Ensure arrival_id is set
    if appointment.arrival_id is None:
        ensure_arrival_id(db, appointment)
    
    # Format driver info (with company)
    driver_info = None
    if appointment.driver:
        driver_info = {
            "license": appointment.driver.drivers_license,
            "name": appointment.driver.name,
            "phone": appointment.driver.phone,
            "company": {
                "nif": appointment.driver.company.nif,
                "name": appointment.driver.company.name,
                "contact": appointment.driver.company.contact,
            } if appointment.driver.company else None
        }
    
    # Format truck info
    truck_info = None
    if appointment.truck:
        truck_info = {
            "license_plate": appointment.truck.license_plate,
            "brand": appointment.truck.brand,
            "weight": appointment.truck.weight,
        }
    
    # Format booking info with cargo
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
            "scheduled_unloading": appointment.booking.scheduled_unloading.isoformat() if appointment.booking.scheduled_unloading else None,
            "origin": appointment.booking.origin,
            "destination": appointment.booking.destination,
            "cargos": cargos,
        }
    
    # Format gates info
    gate_in_info = None
    if appointment.gate_in:
        gate_in_info = {
            "id": appointment.gate_in.id,
            "name": appointment.gate_in.name,
            "terminal_id": appointment.gate_in.terminal_id,
        }
    
    gate_out_info = None
    if appointment.gate_out:
        gate_out_info = {
            "id": appointment.gate_out.id,
            "name": appointment.gate_out.name,
            "terminal_id": appointment.gate_out.terminal_id,
        }
    
    # Format terminal info
    terminal_info = None
    if appointment.terminal:
        terminal_info = {
            "id": appointment.terminal.id,
            "name": appointment.terminal.name,
            "location": appointment.terminal.location,
        }
    
    # Format visit info (if exists)
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
    """Gets appointment by arrival_id/PIN (used by driver)."""
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
    """
    Gets appointments by truck license plate.
    Used by Decision Engine to find candidate arrivals.
    """
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
        # Default: filter by today
        query = query.filter(func.date(Appointment.scheduled_start_time) == date.today())
    
    appointments = query.order_by(Appointment.scheduled_start_time.asc()).all()
    for appointment in appointments:
        if appointment.arrival_id is None:
            ensure_arrival_id(db, appointment)
    return appointments


def get_appointments_for_decision(
    db: Session,
    gate_id: int,
) -> List[Dict[str, Any]]:
    """
    Gets candidate appointments for Decision Engine.
    Returns today's appointments (in_transit or delayed) for the given gate,
    plus any delayed appointments from yesterday (midnight edge case).
    
    Includes extra info: cargo, booking, gate.
    """
    today = date.today()
    yesterday = today - timedelta(days=1)
    
    # Day boundaries
    day_start = datetime.combine(today, datetime.min.time())
    day_end = datetime.combine(today, datetime.max.time())
    yesterday_start = datetime.combine(yesterday, datetime.min.time())
    yesterday_end = datetime.combine(yesterday, datetime.max.time())
    
    # Find current shift based on time and gate
    current_shift = db.query(Shift).filter(
        Shift.date == today,
        Shift.gate_id == gate_id
    ).first()
    
    query = db.query(Appointment).filter(
        or_(
            # Today's in_transit or delayed
            and_(
                Appointment.scheduled_start_time.between(day_start, day_end),
                Appointment.status.in_(['in_transit', 'delayed'])
            ),
            # Yesterday's delayed that still haven't arrived
            and_(
                Appointment.scheduled_start_time.between(yesterday_start, yesterday_end),
                Appointment.status == 'delayed'
            )
        ),
        Appointment.gate_in_id == gate_id,
    )
    
    appointments = query.order_by(Appointment.scheduled_start_time.asc()).all()
    for appointment in appointments:
        if appointment.arrival_id is None:
            ensure_arrival_id(db, appointment)
    
    # Format response with extra info
    result = []
    for a in appointments:
        # Get cargo from booking
        cargo = None
        if a.booking and a.booking.cargos:
            c = a.booking.cargos[0]  # First cargo
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
    db: Session, 
    gate_id: Optional[int] = None, 
    target_date: Optional[date] = None
) -> Dict[str, int]:
    """
    Counts appointments grouped by status.
    Used by operator dashboard.
    """
    date_filter = target_date or date.today()
    
    start_dt = datetime.combine(date_filter, time.min)
    end_dt = datetime.combine(date_filter, time.max)
    base_filter = [
        Appointment.scheduled_start_time >= start_dt,
        Appointment.scheduled_start_time <= end_dt
    ]
    
    if gate_id:
        base_filter.append(Appointment.gate_in_id == gate_id)

    # Filtro para delayed antigos ainda não finalizados
    delayed_filter = [
        Appointment.status == "delayed",
        Appointment.scheduled_start_time < start_dt
    ]
    if gate_id:
        delayed_filter.append(Appointment.gate_in_id == gate_id)

    # Filtro para in_process antigos ainda não finalizados
    in_process_filter = [
        Appointment.status == "in_process",
        Appointment.scheduled_start_time < start_dt
    ]
    if gate_id:
        in_process_filter.append(Appointment.gate_in_id == gate_id)

    # Query para appointments do dia
    status_query = db.query(
        Appointment.status,
        func.count(Appointment.id)
    ).filter(*base_filter)

    # Query para delayed antigos
    delayed_query = db.query(
        func.count(Appointment.id)
    ).filter(*delayed_filter)

    # Query para in_process antigos
    in_process_query = db.query(
        func.count(Appointment.id)
    ).filter(*in_process_filter)

    # Query para infractions do dia
    infractions_query = db.query(
        func.count(Appointment.id)
    ).filter(*base_filter, Appointment.highway_infraction == True)

    # Query para infractions em delayed antigos
    infractions_delayed_query = db.query(
        func.count(Appointment.id)
    ).filter(*delayed_filter, Appointment.highway_infraction == True)

    # Query para infractions em in_process antigos
    infractions_in_process_query = db.query(
        func.count(Appointment.id)
    ).filter(*in_process_filter, Appointment.highway_infraction == True)

    results = status_query.group_by(Appointment.status).all()
    delayed_count = delayed_query.scalar() or 0
    in_process_count = in_process_query.scalar() or 0
    infractions_count = infractions_query.scalar() or 0
    infractions_delayed_count = infractions_delayed_query.scalar() or 0
    infractions_in_process_count = infractions_in_process_query.scalar() or 0

    counts = {
        "in_transit": 0,
        "in_process": 0,
        "delayed": 0,
        "canceled": 0,
        "completed": 0,
        "total": 0,
        "infractions": 0,
    }

    for status, count in results:
        if status in counts:
            counts[status] = count
        counts["total"] += count

    # Inclui delayed antigos
    counts["delayed"] += delayed_count
    counts["total"] += delayed_count

    # Inclui in_process antigos
    counts["in_process"] += in_process_count
    counts["total"] += in_process_count

    # Inclui infractions de todos os grupos
    counts["infractions"] = infractions_count + infractions_delayed_count + infractions_in_process_count

    return counts

def update_appointment_status(
    db: Session,
    appointment_id: int,
    new_status: str,
    notes: Optional[str] = None
) -> Optional[Appointment]:
    """
    Updates appointment status.
    Used by Decision Engine after making decision.
    """
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
    """
    Creates a Visit when an appointment is being executed.
    Called when truck arrives at gate.
    Uses composite FK to Shift.
    """
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    
    if not appointment:
        return None
    
    # Check if visit already exists
    existing_visit = db.query(Visit).filter(Visit.appointment_id == appointment_id).first()
    if existing_visit:
        return existing_visit
    
    visit = Visit(
        appointment_id=appointment_id,
        shift_gate_id=shift_gate_id,
        shift_type=shift_type,
        shift_date=shift_date,
        entry_time=entry_time or datetime.now(),
        state='unloading'  # Updated to match DeliveryStatusEnum
    )
    
    db.add(visit)
    db.commit()
    db.refresh(visit)
    
    return visit


def update_visit_status(
    db: Session,
    appointment_id: int,
    new_state: str,
    out_time: Optional[datetime] = None
) -> Optional[Visit]:
    """
    Updates visit status (e.g., to 'completed' when truck leaves).
    """
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


def update_appointment_from_decision(
    db: Session,
    appointment_id: int,
    decision_payload: Dict[str, Any]
) -> Optional[Appointment]:
    """
    Updates appointment based on Decision Engine decision.
    Includes: status, notes, and creation of alerts if needed.
    
    decision_payload expected:
    {
        "decision": "approved" | "rejected" | "manual_review",
        "status": "in_transit" | "delayed" | "canceled" | "completed",
        "notes": "...",
        "alerts": [
            {"type": "safety", "description": "Flammable cargo - UN 1203"}
        ]
    }
    """
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    
    if not appointment:
        return None
    
    # Update status
    if "status" in decision_payload:
        appointment.status = decision_payload["status"]
    
    # Update notes
    if "notes" in decision_payload:
        appointment.notes = decision_payload["notes"]
    
    db.commit()
    db.refresh(appointment)

    if appointment.arrival_id is None:
        ensure_arrival_id(db, appointment)
    
    # Create alerts if present (delegate to alert_service)
    if "alerts" in decision_payload and decision_payload["alerts"]:
        from services.alert_service import create_alerts_for_appointment
        create_alerts_for_appointment(db, appointment, decision_payload["alerts"])
    
    return appointment


def flag_appointment_highway_infraction(
    db: Session,
    appointment_id: int
) -> Optional[Appointment]:
    """
    Flags an appointment as highway infraction.
    Used when hazmat truck is detected on restricted highway route before port entry.
    """
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    
    if not appointment:
        return None
    
    appointment.highway_infraction = True
    db.commit()
    db.refresh(appointment)
    
    if appointment.arrival_id is None:
        ensure_arrival_id(db, appointment)
    
    return appointment


def get_next_appointments(
    db: Session,
    gate_id: int,
    limit: int = 5,
    status: Optional[str] = None,
) -> List[Appointment]:
    """
    Gets next scheduled appointments (used in operator's sidebar).
    Filters by status 'in_transit' or 'delayed'.
    
    Sorting: delayed appointments first, then by scheduled_start_time.
    """
    today = date.today()
    
    # Use case() to prioritize delayed status
    from sqlalchemy import case
    
    status_priority = case(
        (Appointment.status == 'delayed', 0),  # delayed first
        else_=1
    )
    
    base_filters = [
        Appointment.gate_in_id == gate_id,
        func.date(Appointment.scheduled_start_time) == today,
    ]

    if status:
        base_filters.append(Appointment.status == status)
    else:
        base_filters.append(Appointment.status.in_(['in_transit', 'delayed']))

    appointments = db.query(Appointment).filter(
        *base_filters
    ).order_by(
        status_priority,  # delayed first
        Appointment.scheduled_start_time.asc()  # then by scheduled time
    ).limit(limit).all()

    for appointment in appointments:
        if appointment.arrival_id is None:
            ensure_arrival_id(db, appointment)

    return appointments


def get_transport_stats_by_company(
    db: Session,
    target_date: Optional[date] = None,
    days: int = 30,
) -> List[Dict[str, Any]]:
    """
    Aggregates per-company KPIs by joining Appointment -> Driver -> Company + Visit.
    Uses count(distinct) to avoid inflation from LEFT JOIN.
    """
    end_date = target_date or date.today()
    start_date = end_date - timedelta(days=days)

    rows = (
        db.query(
            Company.nif,
            Company.name,
            # Defensive: count distinct to avoid inflation from LEFT JOIN
            func.count(func.distinct(Appointment.id)).label("ops_count"),
            func.avg(
                func.extract('epoch', Visit.out_time) - func.extract('epoch', Visit.entry_time)
            ).label("avg_duration_seconds"),
            # Avg wait: only count positive waits (truck arrived after scheduled time)
            func.avg(
                case(
                    (
                        func.extract('epoch', Visit.entry_time) > func.extract('epoch', Appointment.scheduled_start_time),
                        func.extract('epoch', Visit.entry_time) - func.extract('epoch', Appointment.scheduled_start_time),
                    ),
                    else_=None,
                )
            ).label("avg_wait_seconds"),
            func.sum(
                case(
                    (Appointment.status == 'completed', 1),
                    else_=0
                )
            ).label("completed_count"),
        )
        .join(Driver, Appointment.driver_license == Driver.drivers_license)
        .join(Company, Driver.company_nif == Company.nif)
        .outerjoin(Visit, Visit.appointment_id == Appointment.id)
        .filter(
            func.date(Appointment.scheduled_start_time) >= start_date,
            func.date(Appointment.scheduled_start_time) <= end_date,
        )
        .group_by(Company.nif, Company.name)
        .all()
    )

    results = []
    for nif, name, ops_count, avg_dur, avg_wait, completed in rows:
        avg_unloading = round(abs(avg_dur or 0) / 60, 1)
        avg_waiting = round((avg_wait or 0) / 60, 1)
        sla_rate = round((completed or 0) / ops_count * 100, 1) if ops_count > 0 else 0

        results.append({
            "companyName": name,
            "companyNif": nif,
            "avgUnloadingTime": avg_unloading,
            "avgWaitingTime": avg_waiting,
            "operationsCount": ops_count,
            "slaAttendedRate": sla_rate,
        })

    return sorted(results, key=lambda x: x["operationsCount"], reverse=True)


def get_avg_permanence_minutes(
    db: Session,
    target_date: Optional[date] = None,
) -> float:
    """
    Calculates average visit permanence in minutes from entry_time to out_time.
    Only includes completed visits (where both times are set).
    """
    query = (
        db.query(
            func.avg(
                func.extract('epoch', Visit.out_time) - func.extract('epoch', Visit.entry_time)
            )
        )
        .filter(
            Visit.entry_time.isnot(None),
            Visit.out_time.isnot(None),
        )
    )

    if target_date:
        query = query.filter(func.date(Visit.entry_time) == target_date)

    result = query.scalar()
    return round(abs(result or 0) / 60, 1)
