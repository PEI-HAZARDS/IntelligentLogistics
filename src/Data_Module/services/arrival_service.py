"""
Arrival Service - Manages appointments and visits.
Used by: Operator frontend, Decision Engine, Driver app.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, date, time
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from models.sql_models import Appointment, Visit, Shift, Cargo, Booking, Gate, ShiftType


def get_all_appointments(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    gate_id: Optional[int] = None,
    shift_gate_id: Optional[int] = None,
    shift_type: Optional[str] = None,
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
    
    return query.order_by(Appointment.scheduled_start_time.asc()).offset(skip).limit(limit).all()


def get_appointment_by_id(db: Session, appointment_id: int) -> Optional[Appointment]:
    """Gets a specific appointment by ID."""
    return db.query(Appointment).filter(Appointment.id == appointment_id).first()


def get_appointment_by_arrival_id(db: Session, arrival_id: str) -> Optional[Appointment]:
    """Gets appointment by arrival_id/PIN (used by driver)."""
    return db.query(Appointment).filter(Appointment.arrival_id == arrival_id).first()


def get_appointments_by_license_plate(
    db: Session,
    license_plate: str,
    shift_gate_id: Optional[int] = None,
    shift_type: Optional[str] = None,
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
    
    return query.order_by(Appointment.scheduled_start_time.asc()).all()


def get_appointments_for_decision(
    db: Session,
    license_plate: str,
    gate_id: int,
    current_time: Optional[time] = None
) -> List[Dict[str, Any]]:
    """
    Gets candidate appointments for Decision Engine.
    Returns appointments with specific license plate, in current shift,
    with status 'in_transit' or 'delayed'.
    
    Includes extra info: cargo, booking, gate.
    """
    today = date.today()
    now = current_time or datetime.now().time()
    
    # Find current shift based on time and gate
    current_shift = db.query(Shift).filter(
        Shift.date == today,
        Shift.gate_id == gate_id
    ).first()
    
    query = db.query(Appointment).filter(
        Appointment.truck_license_plate == license_plate,
        func.date(Appointment.scheduled_start_time) == today,
        Appointment.gate_in_id == gate_id,
        Appointment.status.in_(['in_transit', 'delayed'])
    )
    
    appointments = query.order_by(Appointment.scheduled_start_time.asc()).all()
    
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
    """
    today = date.today()
    now = datetime.now()
    
    return db.query(Appointment).filter(
        Appointment.gate_in_id == gate_id,
        func.date(Appointment.scheduled_start_time) == today,
        Appointment.status.in_(['in_transit', 'delayed']),
        Appointment.scheduled_start_time >= now
    ).order_by(Appointment.scheduled_start_time.asc()).limit(limit).all()