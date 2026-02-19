"""
Arrival Service - Manages appointments and visits.
Used by: Operator frontend, Decision Engine, Driver app.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, date, time, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, case, Integer

from models.sql_models import Appointment, Visit, Shift, Cargo, Booking, Gate, ShiftType, Company, Driver


def ensure_arrival_id(db: Session, appointment: Appointment) -> Appointment:
    if appointment.arrival_id:
        return appointment

    db.refresh(appointment)
    return appointment


def get_all_appointments(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    gate_id: Optional[int] = None,
    shift_gate_id: Optional[int] = None,
    shift_type: Optional[ShiftType] = None,
    shift_date: Optional[date] = None,
    status: Optional[str] = None,
    scheduled_date: Optional[date] = None
) -> List[Appointment]:
    """
    Gets appointments with optional filters.
    Used by operator frontend to list arrivals.
    """
    query = db.query(Appointment)
    
    if gate_id:
        query = query.filter(Appointment.gate_in_id == gate_id)
    if shift_gate_id and shift_type and shift_date:
        # Filter by visits that have this shift (composite FK)
        query = query.join(Visit).filter(
            Visit.shift_gate_id == shift_gate_id,
            Visit.shift_type == shift_type,
            Visit.shift_date == shift_date
        )
    if status:
        query = query.filter(Appointment.status == status)
    if scheduled_date:
        query = query.filter(func.date(Appointment.scheduled_start_time) == scheduled_date)
    
    appointments = query.order_by(Appointment.scheduled_start_time.asc()).offset(skip).limit(limit).all()
    for appointment in appointments:
        if appointment.arrival_id is None:
            ensure_arrival_id(db, appointment)
    return appointments


def get_appointment_by_id(db: Session, appointment_id: int) -> Optional[Appointment]:
    """Gets a specific appointment by ID."""
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if appointment and appointment.arrival_id is None:
        ensure_arrival_id(db, appointment)
    return appointment


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
    time_frame: int = 1,
) -> List[Dict[str, Any]]:
    """
    Gets candidate appointments for Decision Engine.
    Returns appointments with specific license plate, in current shift,
    with status 'in_transit' or 'delayed'.
    
    Includes extra info: cargo, booking, gate.
    """
    today = date.today()
    now = datetime.now()
    
    # Calculate time window safely, clamping to start/end of day
    window_start = now - timedelta(hours=time_frame)
    window_end = now + timedelta(hours=time_frame)
    
    # Clamp to today's boundaries if needed
    day_start = datetime.combine(today, datetime.min.time())
    day_end = datetime.combine(today, datetime.max.time())
    
    window_start = max(window_start, day_start)
    window_end = min(window_end, day_end)
    
    # Find current shift based on time and gate
    current_shift = db.query(Shift).filter(
        Shift.date == today,
        Shift.gate_id == gate_id
    ).first()
    
    query = db.query(Appointment).filter(
        Appointment.scheduled_start_time.between(window_start, window_end),
        Appointment.gate_in_id == gate_id,
        Appointment.status.in_(['in_transit', 'delayed'])
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
    
    query = db.query(
        Appointment.status,
        func.count(Appointment.id)
    ).filter(func.date(Appointment.scheduled_start_time) == date_filter)
    
    if gate_id:
        query = query.filter(Appointment.gate_in_id == gate_id)
    
    results = query.group_by(Appointment.status).all()
    
    counts = {
        "in_transit": 0,
        "delayed": 0,
        "canceled": 0,
        "completed": 0,
        "total": 0
    }
    
    for status, count in results:
        if status in counts:
            counts[status] = count
        counts["total"] += count
    
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


def get_next_appointments(
    db: Session,
    gate_id: int,
    limit: int = 5
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
    
    appointments = db.query(Appointment).filter(
        Appointment.gate_in_id == gate_id,
        func.date(Appointment.scheduled_start_time) == today,
        Appointment.status.in_(['in_transit', 'delayed'])
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
