"""
Decisions Routes - Endpoints for decision processing.
Consumed by: Decision Engine (microservice), Operator frontend.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, HTTPException, status, Body, Query, Path
from bson.objectid import ObjectId
from pydantic import BaseModel

from db.mongo import events_collection
from services.decision_service import (
    process_incoming_decision,
    query_appointments_for_decision,
    get_detection_events,
    get_decision_events,
    persist_detection_event
)

router = APIRouter(prefix="/decisions", tags=["Decisions"])


# ==================== PYDANTIC MODELS ====================

class DecisionIncomingRequest(BaseModel):
    """Request from Decision Engine to process a decision."""
    license_plate: str
    gate_id: int
    appointment_id: int
    decision: str  # "approved", "rejected", "manual_review"
    status: str  # "approved", "canceled", etc.
    notes: Optional[str] = None
    alerts: Optional[List[Dict[str, Any]]] = None
    extra_data: Optional[Dict[str, Any]] = None


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
    license_plate: str
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
    result = process_incoming_decision(
        license_plate=request.license_plate,
        gate_id=request.gate_id,
        appointment_id=request.appointment_id,
        decision=request.decision,
        status=request.status,
        alerts=request.alerts,
        notes=request.notes,
        extra_data=request.extra_data
    )
    
    return result


@router.post("/query-appointments")
def query_appointments(request: QueryAppointmentsRequest):
    """
    Decision Engine queries candidate appointments for a license plate.
    Used after license plate detection by Agent B.
    
    Returns appointments with status 'pending' or 'approved' that
    match the license plate and gate.
    """
    result = query_appointments_for_decision(
        license_plate=request.license_plate,
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
        "timestamp": datetime.utcnow().isoformat()
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
    notes: Optional[str] = Query(None, description="Operator notes")
):
    """
    Endpoint for operator manual review.
    Used when Decision Engine cannot decide automatically.
    """
    result = process_incoming_decision(
        license_plate="MANUAL",  # Manual review indicator
        gate_id=0,
        appointment_id=appointment_id,
        decision=decision,
        status="approved" if decision == "approved" else "canceled",
        notes=f"[MANUAL REVIEW] {notes or ''}",
        extra_data={"manual_review": True}
    )
    
    return result
