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

from loguru import logger

from infrastructure.persistence.mongo import events_collection
from infrastructure.persistence.postgres import get_db
from application.queries.decision_queries import (
    process_incoming_decision,
    query_appointments_for_decision,
    get_detection_events,
    get_decision_events,
    persist_detection_event,
)

router = APIRouter(prefix="/decisions", tags=["Decisions"])


# ==================== PYDANTIC MODELS ====================

from application.schemas import AppointmentStatusEnum, DeliveryStatusEnum


class DecisionIncomingRequest(BaseModel):
    """Request from Decision Engine to process a decision."""
    event_id: Optional[str] = None  # Caller-provided idempotency key (Guardrail 1)
    license_plate: str
    gate_id: int
    appointment_id: Optional[int] = None   # None when no matching appointment exists
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
    gate_id: Optional[int] = None


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

    When appointment_id is None the truck has no matching appointment —
    the decision (MANUAL_REVIEW / REJECTED) is still fully persisted to MongoDB.
    """
    if request.appointment_status is None and request.appointment_id is not None:
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
        extra_data=request.extra_data,
        event_id=request.event_id,
    )

    return result


@router.post("/query-appointments")
def query_appointments(request: QueryAppointmentsRequest):
    """
    Decision Engine queries candidate appointments.
    Used after license plate detection by Agent B to find potential matches.
    
    Returns appointments with status 'in_transit' or 'delayed' for the given gate.
    """
    result = query_appointments_for_decision(
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
        from infrastructure.persistence.mongo import detections_collection
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
    Endpoint for operator manual review — UoW + Outbox (Guardrails 2, 3, 6).
    Used when Decision Engine cannot decide automatically.

    When approved:
    - Updates Appointment.status to 'in_process' (confirmed arrival)
    - Creates Visit with state='unloading' if gate_id provided

    When rejected:
    - Updates Appointment.status to 'canceled'
    """
    from application.use_cases.appointment_commands import (
        cmd_process_decision,
        cmd_create_visit,
    )
    from infrastructure.persistence.postgres import SessionLocal
    from infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
    from infrastructure.persistence.sql_models import ShiftType
    from datetime import date

    def _uow_factory():
        return SqlAlchemyUnitOfWork(SessionLocal)

    # Map decision to appointment status
    if decision == "approved":
        new_status = "in_process"
    else:
        new_status = "canceled"

    # Build decision payload
    decision_payload = {
        "decision": decision,
        "status": new_status,
        "notes": f"[MANUAL REVIEW] {notes or ''}",
        "manual_review": True,
    }

    # PG write via UoW + Outbox (Guardrails 2, 3, 6)
    cmd_result = cmd_process_decision(_uow_factory, appointment_id, decision_payload)

    result = {
        "status": "ok",
        "appointment_id": appointment_id,
        "decision": decision,
        "new_status": new_status,
    }

    if cmd_result is None:
        result["warning"] = "Appointment not found"
        return result

    # MongoDB audit trail (async projection — will become outbox-driven later)
    try:
        # Read license plate for Mongo audit
        from application.queries.arrival_queries import get_appointment_by_id
        appointment = get_appointment_by_id(db, appointment_id)
        license_plate = appointment.truck_license_plate if appointment else "MANUAL"

        process_incoming_decision(
            license_plate=license_plate,
            gate_id=gate_id or 0,
            appointment_id=appointment_id,
            decision=decision,
            appointment_status=new_status,
            delivery_state=None,
            notes=f"[MANUAL REVIEW] {notes or ''}",
            extra_data={"manual_review": True, "_skip_pg_write": True}
        )
    except Exception as e:
        logger.warning(f"MongoDB audit persistence failed for manual review: {e}")

    # If approved and gate_id provided, create Visit via UoW + Outbox
    if decision == "approved" and gate_id:
        try:
            hour = datetime.now().hour
            if 6 <= hour < 14:
                shift_type = ShiftType.MORNING
            elif 14 <= hour < 22:
                shift_type = ShiftType.AFTERNOON
            else:
                shift_type = ShiftType.NIGHT

            visit_result = cmd_create_visit(
                _uow_factory,
                appointment_id=appointment_id,
                shift_gate_id=gate_id,
                shift_type=shift_type,
                shift_date=date.today(),
            )
            if visit_result:
                result["visit_created"] = True
                result["visit_state"] = "unloading"
        except Exception as e:
            result["visit_error"] = str(e)

    return result

