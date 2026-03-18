"""
Arrivals Routes - Endpoints for appointment and visit management.
Consumed by: Operator frontend, Decision Engine, Driver app.
"""

from typing import List, Optional, Dict, Any, Generic, TypeVar
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session
from pydantic import BaseModel
from loguru import logger

from models.pydantic_models import (
    Appointment, AppointmentStatusUpdate, Visit, VisitStatusUpdate, ShiftTypeEnum
)
from services.arrival_service import (
    get_all_appointments,
    count_all_appointments,
    get_appointment_by_id,
    get_appointment_detail,
    get_appointment_by_arrival_id,
    get_appointments_by_license_plate,
    get_appointments_count_by_status,
    update_appointment_status,
    update_appointment_from_decision,
    flag_appointment_highway_infraction,
    get_next_appointments,
    create_visit_for_appointment,
    update_visit_status
)
from services.cache_service import get_or_cache
from db.redis import get_cached_appointment, cache_appointment

T = TypeVar("T")

class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    limit: int
    pages: int
from models.sql_models import ShiftType
from db.postgres import get_db
from utils.shift_utils import parse_shift_type

router = APIRouter(prefix="/arrivals", tags=["Arrivals"])


# ==================== LOCAL MODELS ====================

class CreateVisitRequest(BaseModel):
    """Request to create a visit with composite shift FK."""
    shift_gate_id: int
    shift_type: str  # "MORNING", "AFTERNOON", "NIGHT"
    shift_date: date


# ==================== GET ENDPOINTS ====================

@router.get("", response_model=PaginatedResponse[Appointment])
def list_arrivals(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    gate_id: Optional[int] = Query(None, description="Filter by entry gate"),
    shift_gate_id: Optional[int] = Query(None, description="Filter by shift gate"),
    shift_type: Optional[str] = Query(None, description="Filter by shift type"),
    shift_date: Optional[date] = Query(None, description="Filter by shift date"),
    status: Optional[str] = Query(None, description="Filter by single status"),
    statuses: Optional[str] = Query(None, description="Filter by multiple statuses (comma-separated)"),
    scheduled_date: Optional[date] = Query(None, description="Filter by scheduled date"),
    search: Optional[str] = Query(None, description="Search by license plate or driver name"),
    db: Session = Depends(get_db),
):
    """
    Lists appointments with server-side pagination, filtering and search.
    Used by operator frontend to list daily arrivals.
    Supports filtering by single status or multiple statuses (comma-separated).
    
    Note: If both status and statuses are provided, statuses takes precedence.
    """
    parsed_shift_type = None
    if shift_type:
        try:
            parsed_shift_type = parse_shift_type(shift_type)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    skip = (page - 1) * limit
    
    # Handle both single status and multiple statuses
    # Warn if both are provided (statuses takes precedence)
    final_status = status
    if statuses:
        if status:
            logger.warning(f"Both status and statuses provided. Using statuses='{statuses}', ignoring status='{status}'")
        final_status = statuses
    
    filter_kwargs = dict(
        gate_id=gate_id,
        shift_gate_id=shift_gate_id,
        shift_type=parsed_shift_type,
        shift_date=shift_date,
        status=final_status,
        scheduled_date=scheduled_date,
        search=search,
    )

    total = count_all_appointments(db, **filter_kwargs)
    appointments = get_all_appointments(db, skip=skip, limit=limit, **filter_kwargs)

    return PaginatedResponse(
        items=[Appointment.model_validate(a) for a in appointments],
        total=total,
        page=page,
        limit=limit,
        pages=max(1, -(-total // limit)),
    )


@router.get("/stats", response_model=Dict[str, int])
def get_arrivals_stats(
    gate_id: Optional[int] = Query(None, description="Filter by gate"),
    target_date: Optional[date] = Query(None, description="Date to query (default: today)"),
    db: Session = Depends(get_db),
):
    """
    Arrival statistics by status.
    Cached in Redis for 30 s to avoid hitting PostgreSQL on every dashboard refresh.
    """
    today = (target_date or date.today()).isoformat()
    cache_key = f"stats:gate:{gate_id or 'all'}:{today}"
    return get_or_cache(
        key=cache_key,
        ttl=30,
        fallback=lambda: get_appointments_count_by_status(db, gate_id=gate_id, target_date=target_date),
    )


@router.get("/next/{gate_id}", response_model=List[Appointment])
def get_upcoming_arrivals(
    gate_id: int = Path(..., description="Gate ID"),
    limit: int = Query(5, ge=1, le=20, description="Number of arrivals"),
    status: Optional[str] = Query(None, description="Filter by status"),
    db: Session = Depends(get_db)
):
    """
    Next scheduled arrivals for a gate.
    Used in operator's sidebar panel.
    """
    appointments = get_next_appointments(db, gate_id=gate_id, limit=limit, status=status)
    return [Appointment.model_validate(a) for a in appointments]


@router.get("/{appointment_id}/detail", response_model=Dict[str, Any])
def get_arrival_detail(
    appointment_id: int = Path(..., description="Appointment ID"),
    db: Session = Depends(get_db)
):
    """
    Gets enriched appointment details with all related data.
    Includes: driver + company, booking + cargo, gates, terminal, visit status.
    Used by operator interface for detailed appointment review.
    """
    detail = get_appointment_detail(db, appointment_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return detail


@router.get("/{appointment_id}", response_model=Appointment)
def get_arrival(
    appointment_id: int = Path(..., description="Appointment ID"),
    db: Session = Depends(get_db),
):
    """
    Gets details of a specific appointment.

    **CQRS Query Side** — reads from Redis hot cache first (O(1)).
    Falls back to PostgreSQL only on projection miss (Guardrail 5).

    The outbox worker keeps this cache warm: every
    ``AppointmentStateChanged`` event writes a full snapshot into
    ``appointment:{id}:details``.
    """
    # ── 1) Redis hot cache (written by outbox worker) ─────────
    cached = get_cached_appointment(appointment_id)
    if cached:
        logger.debug("CACHE HIT  appointment_id=%s", appointment_id)
        return cached

    # ── 2) Projection miss → PostgreSQL fallback (observable) ─
    logger.info(
        "CACHE MISS appointment_id=%s — PostgreSQL fallback (Guardrail 5)",
        appointment_id,
    )
    appointment = get_appointment_by_id(db, appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    # ── 3) Warm cache for subsequent reads ────────────────────
    result = Appointment.model_validate(appointment)
    cache_appointment(appointment_id, result.model_dump(mode="json"))

    return result



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
    parsed_shift_type = None
    if shift_type:
        try:
            parsed_shift_type = parse_shift_type(shift_type)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    appointments = get_appointments_by_license_plate(
        db, license_plate=license_plate,
        shift_gate_id=shift_gate_id,
        shift_type=parsed_shift_type,
        shift_date=shift_date,
        status=status,
        scheduled_date=scheduled_date
    )
    return [Appointment.model_validate(a) for a in appointments]



# ==================== HIGHWAY INFRACTION ====================

@router.patch("/{appointment_id}/highway-infraction", response_model=Appointment)
def flag_highway_infraction(
    appointment_id: int = Path(..., description="Appointment ID"),
    db: Session = Depends(get_db)
):
    """
    Flag an appointment as highway infraction.
    Hazmat truck detected on restricted highway route before port entry.
    """
    appointment = flag_appointment_highway_infraction(db, appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return Appointment.model_validate(appointment)


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
    try:
        shift_type_enum = parse_shift_type(request.shift_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    
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