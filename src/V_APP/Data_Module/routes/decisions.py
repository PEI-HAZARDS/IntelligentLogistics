"""
Decisions Routes - Endpoints for decision processing.
Consumed by: Decision Engine (microservice), Operator frontend.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, status, Body, Query, Path, Depends
from sqlalchemy.orm import Session
from bson.objectid import ObjectId
from pydantic import BaseModel, model_validator

from db.mongo import events_collection
from db.postgres import get_db
from services.decision_service import (
    process_incoming_decision,
    query_appointments_for_decision,
    get_detection_events,
    get_decision_events,
    persist_detection_event
)

router = APIRouter(prefix="/decisions", tags=["Decisions"])


# ==================== PYDANTIC MODELS ====================

from models.pydantic_models import AppointmentStatusEnum, DeliveryStatusEnum


class DecisionIncomingRequest(BaseModel):
    """Request from Decision Engine to process a decision."""
    license_plate: str
    gate_id: int
    appointment_id: int
    decision: str  # "approved", "rejected", "manual_review"
    appointment_status: Optional[AppointmentStatusEnum] = None
    delivery_state: Optional[DeliveryStatusEnum] = None
    status: Optional[AppointmentStatusEnum] = None
    state: Optional[DeliveryStatusEnum] = None
    notes: Optional[str] = None
    alerts: Optional[List[Dict[str, Any]]] = None
    extra_data: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def normalize_fields(self):
        if self.appointment_status is None and self.status is not None:
            self.appointment_status = self.status
        if self.delivery_state is None and self.state is not None:
            self.delivery_state = self.state
        return self


class DetectionEventRequest(BaseModel):
    """Request to register detection event (Agent A/B/C)."""
    type: str  # "license_plate_detection", "hazmat_detection", "truck_detection"
    license_plate: Optional[str] = None
    gate_id: int
    confidence: Optional[float] = None
    agent: str  # "AgentA", "AgentB", "AgentC"
    raw_data: Optional[Dict[str, Any]] = None


class QueryAppointmentsRequest(BaseModel):
    """Request from Decision Engine to query appointments."""
    time_frame: int = 1  # hours
    gate_id: int


class EventResponse(BaseModel):
    """Generic response for events."""
    id: Optional[str] = None
    type: str
    timestamp: Optional[datetime] = None
    gate_id: Optional[int] = None
    license_plate: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


# ==================== DECISION ENGINE ENDPOINTS ====================

@router.post("/process")
def process_decision(request: DecisionIncomingRequest):
    """
    Main endpoint for Decision Engine to send decisions.
    
    Flow:
    1. Check duplicate (Redis)
    2. Update appointment in PostgreSQL
    3. Create alerts if needed
    4. Persist event in MongoDB
    5. Cache result in Redis
    
    Expected payload:
    {
        "license_plate": "XX-XX-XX",
        "gate_id": 1,
        "appointment_id": 123,
        "decision": "approved",
        "status": "approved",
        "notes": "Automatically approved",
        "alerts": [{"type": "hazmat", "severity": 3, "description": "UN 1203"}]
    }
    """
    if request.appointment_status is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="appointment_status is required (or legacy status)",
        )

    result = process_incoming_decision(
        license_plate=request.license_plate,
        gate_id=request.gate_id,
        appointment_id=request.appointment_id,
        decision=request.decision,
        appointment_status=request.appointment_status,
        delivery_state=request.delivery_state,
        alerts=request.alerts,
        notes=request.notes,
        extra_data=request.extra_data
    )
    
    return result


@router.post("/query-appointments")
def query_appointments(request: QueryAppointmentsRequest):
    """
    Decision Engine queries candidate appointments within a time window.
    Used after license plate detection by Agent B to find potential matches.
    
    Returns appointments with status 'in_transit' or 'delayed' within
    the specified time_frame (hours) around current time for the given gate.
    """
    result = query_appointments_for_decision(
        time_frame=request.time_frame,
        gate_id=request.gate_id
    )
    return result


@router.post("/detection-event")
def register_detection_event(request: DetectionEventRequest):
    """
    Registers detection event from Agents (A/B/C).
    Used for persistence and future statistics.
    
    Expected payload:
    {
        "type": "license_plate_detection",
        "license_plate": "XX-XX-XX",
        "gate_id": 1,
        "confidence": 0.95,
        "agent": "AgentB",
        "raw_data": {...}
    }
    """
    event_data = {
        "type": request.type,
        "license_plate": request.license_plate,
        "gate_id": request.gate_id,
        "confidence": request.confidence,
        "agent": request.agent,
        "raw_data": request.raw_data,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    event_id = persist_detection_event(event_data)
    
    return {"status": "ok", "event_id": event_id}


# ==================== QUERY ENDPOINTS (MongoDB) ====================

@router.get("/events/detections", response_model=List[Dict[str, Any]])
def list_detection_events(
    license_plate: Optional[str] = Query(None),
    gate_id: Optional[int] = Query(None),
    event_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500)
):
    """Lists detection events from MongoDB."""
    events = get_detection_events(
        license_plate=license_plate,
        gate_id=gate_id,
        event_type=event_type,
        limit=limit
    )
    # Convert ObjectId to string
    for e in events:
        if "_id" in e:
            e["_id"] = str(e["_id"])
    return events


@router.get("/events/decisions", response_model=List[Dict[str, Any]])
def list_decision_events(
    license_plate: Optional[str] = Query(None),
    gate_id: Optional[int] = Query(None),
    decision: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500)
):
    """Lists decision events from MongoDB."""
    events = get_decision_events(
        license_plate=license_plate,
        gate_id=gate_id,
        decision=decision,
        limit=limit
    )
    # Convert ObjectId to string
    for e in events:
        if "_id" in e:
            e["_id"] = str(e["_id"])
    return events


@router.get("/events/{event_id}")
def get_event(event_id: str = Path(...)):
    """Gets a specific event by ID (MongoDB ObjectId)."""
    try:
        oid = ObjectId(event_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid event_id")
    
    # Try both collections
    doc = events_collection.find_one({"_id": oid})
    
    if not doc:
        from db.mongo import detections_collection
        doc = detections_collection.find_one({"_id": oid})
    
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    
    doc["_id"] = str(doc["_id"])
    return doc


# ==================== MANUAL REVIEW (Operator) ====================

@router.post("/manual-review/{appointment_id}")
def manual_review(
    appointment_id: int = Path(..., description="Appointment ID"),
    decision: str = Query(..., description="Decision: approved, rejected"),
    notes: Optional[str] = Query(None, description="Operator notes"),
    gate_id: Optional[int] = Query(None, description="Gate ID for visit creation"),
    db: Session = Depends(get_db)
):
    """
    Endpoint for operator manual review.
    Used when Decision Engine cannot decide automatically.
    
    Uses a single DB session for atomicity — if visit creation fails,
    the entire transaction is rolled back.
    
    When approved:
    - Updates Appointment.status to 'in_process' (confirmed arrival)
    - Creates Visit with state='unloading' if gate_id provided
    
    When rejected:
    - Updates Appointment.status to 'canceled'
    """
    from services.arrival_service import create_visit_for_appointment, update_appointment_from_decision
    from models.sql_models import ShiftType
    from datetime import date
    
    # Map decision to appointment status
    if decision == "approved":
        new_status = "in_process"
    else:
        new_status = "canceled"
    
    # Build decision payload for update_appointment_from_decision
    decision_payload = {
        "decision": decision,
        "status": new_status,
        "notes": f"[MANUAL REVIEW] {notes or ''}",
        "manual_review": True,
    }
    
    # Update appointment via canonical function (single session)
    appointment = update_appointment_from_decision(db, appointment_id, decision_payload)
    
    result = {
        "status": "ok",
        "appointment_id": appointment_id,
        "decision": decision,
        "new_status": new_status,
    }
    
    if not appointment:
        result["warning"] = "Appointment not found"
        return result
    
    # Also persist to MongoDB for audit trail
    try:
        process_incoming_decision(
            license_plate=appointment.truck_license_plate or "MANUAL",
            gate_id=gate_id or 0,
            appointment_id=appointment_id,
            decision=decision,
            appointment_status=new_status,
            delivery_state=None,
            notes=f"[MANUAL REVIEW] {notes or ''}",
            extra_data={"manual_review": True}
        )
    except Exception as e:
        logger.warning(f"MongoDB audit persistence failed for manual review: {e}")
    
    # If approved and gate_id provided, create Visit with 'unloading' state (same session)
    if decision == "approved" and gate_id:
        try:
            hour = datetime.now().hour
            if 6 <= hour < 14:
                shift_type = ShiftType.MORNING
            elif 14 <= hour < 22:
                shift_type = ShiftType.AFTERNOON
            else:
                shift_type = ShiftType.NIGHT
            
            visit = create_visit_for_appointment(
                db,
                appointment_id=appointment_id,
                shift_gate_id=gate_id,
                shift_type=shift_type,
                shift_date=date.today()
            )
            if visit:
                result["visit_created"] = True
                result["visit_state"] = "unloading"
        except Exception as e:
            result["visit_error"] = str(e)
    
    return result

