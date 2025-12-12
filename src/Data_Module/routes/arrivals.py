"""
Arrivals Routes - Endpoints for appointment and visit management.
Consumed by: Operator frontend, Decision Engine, Driver app.
"""

from typing import List, Optional, Dict, Any
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session
from pydantic import BaseModel

from models.pydantic_models import (
    Appointment, AppointmentStatusUpdate, Visit, VisitStatusUpdate, ShiftTypeEnum
)
from services.arrival_service import (
    get_all_appointments,
    get_appointment_by_id,
    get_appointment_by_arrival_id,
    get_appointments_by_license_plate,
    get_appointments_count_by_status,
    update_appointment_status,
    update_appointment_from_decision,
    get_next_appointments,
    create_visit_for_appointment,
    update_visit_status
)
from models.sql_models import ShiftType
from db.postgres import get_db

router = APIRouter(prefix="/arrivals", tags=["Arrivals"])


# ==================== LOCAL MODELS ====================

class CreateVisitRequest(BaseModel):
    """Request to create a visit with composite shift FK."""
    shift_gate_id: int
    shift_type: str  # "MORNING", "AFTERNOON", "NIGHT"
    shift_date: date


# ==================== GET ENDPOINTS ====================

@router.get("", response_model=List[Appointment])
def list_arrivals(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=500, description="Maximum records"),
    gate_id: Optional[int] = Query(None, description="Filter by entry gate"),
    shift_gate_id: Optional[int] = Query(None, description="Filter by shift gate"),
    shift_type: Optional[str] = Query(None, description="Filter by shift type"),
    shift_date: Optional[date] = Query(None, description="Filter by shift date"),
    status: Optional[str] = Query(None, description="Filter by status"),
    scheduled_date: Optional[date] = Query(None, description="Filter by scheduled date"),
    db: Session = Depends(get_db)
):
    """
    Lists appointments with optional filters.
    Used by operator frontend to list daily arrivals.
    """
    appointments = get_all_appointments(
        db, skip=skip, limit=limit,
        gate_id=gate_id,
        shift_gate_id=shift_gate_id,
        shift_type=shift_type,
        shift_date=shift_date,
        status=status,
        scheduled_date=scheduled_date
    )
    return [Appointment.model_validate(a) for a in appointments]


@router.get("/stats", response_model=Dict[str, int])
def get_arrivals_stats(
    gate_id: Optional[int] = Query(None, description="Filter by gate"),
    target_date: Optional[date] = Query(None, description="Date to query (default: today)"),
    db: Session = Depends(get_db)
):
    """
    Arrival statistics by status.
    Used in operator dashboard.
    """
    return get_appointments_count_by_status(db, gate_id=gate_id, target_date=target_date)


@router.get("/next/{gate_id}", response_model=List[Appointment])
def get_upcoming_arrivals(
    gate_id: int = Path(..., description="Gate ID"),
    limit: int = Query(5, ge=1, le=20, description="Number of arrivals"),
    db: Session = Depends(get_db)
):
    """
    Next scheduled arrivals for a gate.
    Used in operator's sidebar panel.
    """
    appointments = get_next_appointments(db, gate_id=gate_id, limit=limit)
    return [Appointment.model_validate(a) for a in appointments]


@router.get("/{appointment_id}", response_model=Appointment)
def get_arrival(
    appointment_id: int = Path(..., description="Appointment ID"),
    db: Session = Depends(get_db)
):
    """Gets details of a specific appointment."""
    appointment = get_appointment_by_id(db, appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return Appointment.model_validate(appointment)


@router.get("/pin/{arrival_id}", response_model=Appointment)
def get_arrival_by_pin_code(
    arrival_id: str = Path(..., description="Arrival ID / PIN"),
    db: Session = Depends(get_db)
):
    """
    Gets appointment by arrival_id/PIN.
    Used by driver to check their appointment.
    """
    appointment = get_appointment_by_arrival_id(db, arrival_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Invalid PIN or appointment not found")
    return Appointment.model_validate(appointment)


# ==================== DECISION ENGINE ENDPOINTS ====================

@router.get("/query/license-plate/{license_plate}", response_model=List[Appointment])
def query_arrivals_by_license_plate(
    license_plate: str = Path(..., description="Truck license plate"),
    shift_gate_id: Optional[int] = Query(None, description="Filter by shift gate"),
    shift_type: Optional[str] = Query(None, description="Filter by shift type"),
    shift_date: Optional[date] = Query(None, description="Filter by shift date"),
    status: Optional[str] = Query(None, description="Filter by status"),
    scheduled_date: Optional[date] = Query(None, description="Date (default: today)"),
    db: Session = Depends(get_db)
):
    """
    Query appointments by license plate.
    Used by Decision Engine to find candidate arrivals.
    """
    appointments = get_appointments_by_license_plate(
        db, license_plate=license_plate,
        shift_gate_id=shift_gate_id,
        shift_type=shift_type,
        shift_date=shift_date,
        status=status,
        scheduled_date=scheduled_date
    )
    return [Appointment.model_validate(a) for a in appointments]



# ==================== UPDATE ENDPOINTS ====================

@router.patch("/{appointment_id}/status", response_model=Appointment)
def update_status(
    appointment_id: int = Path(..., description="Appointment ID"),
    update_data: AppointmentStatusUpdate = ...,
    db: Session = Depends(get_db)
):
    """
    Updates appointment status.
    Used by operator or system for manual updates.
    """
    appointment = update_appointment_status(
        db, appointment_id=appointment_id,
        new_status=update_data.status,
        notes=update_data.notes
    )
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return Appointment.model_validate(appointment)


@router.post("/{appointment_id}/decision", response_model=Appointment)
def process_decision(
    appointment_id: int = Path(..., description="Appointment ID"),
    decision: Dict[str, Any] = ...,
    db: Session = Depends(get_db)
):
    """
    Processes Decision Engine decision.
    Updates status and creates alerts if needed.
    
    Expected payload:
    {
        "decision": "approved",
        "status": "in_transit",
        "notes": "Approved automatically",
        "alerts": [
            {"type": "safety", "description": "UN 1203 - Gasoline"}
        ]
    }
    """
    appointment = update_appointment_from_decision(
        db, appointment_id=appointment_id,
        decision_payload=decision
    )
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return Appointment.model_validate(appointment)


# ==================== VISIT ENDPOINTS ====================

@router.post("/{appointment_id}/visit", response_model=Visit)
def create_visit(
    appointment_id: int = Path(..., description="Appointment ID"),
    request: CreateVisitRequest = ...,
    db: Session = Depends(get_db)
):
    """
    Creates a visit when truck arrives.
    Called when appointment starts execution.
    Uses composite FK to Shift.
    """
    # Convert shift_type string to enum
    try:
        shift_type_enum = ShiftType[request.shift_type]
    except KeyError:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid shift_type. Must be one of: MORNING, AFTERNOON, NIGHT"
        )
    
    visit = create_visit_for_appointment(
        db, 
        appointment_id,
        shift_gate_id=request.shift_gate_id,
        shift_type=shift_type_enum,
        shift_date=request.shift_date
    )
    if not visit:
        raise HTTPException(status_code=404, detail="Appointment not found or visit already exists")
    return Visit.model_validate(visit)


@router.patch("/{appointment_id}/visit", response_model=Visit)
def update_visit(
    appointment_id: int = Path(..., description="Appointment ID"),
    update_data: VisitStatusUpdate = ...,
    db: Session = Depends(get_db)
):
    """
    Updates visit status (e.g., to 'completed' when truck leaves).
    """
    visit = update_visit_status(
        db, appointment_id=appointment_id,
        new_state=update_data.state,
        out_time=update_data.out_time
    )
    if not visit:
        raise HTTPException(status_code=404, detail="Visit not found")
    return Visit.model_validate(visit)