"""
Decision Service - Processing decisions from Decision Engine.
Responsibilities:
- Deduplication via Redis (SET NX)
- Decision caching in Redis
- Event persistence in MongoDB
- Appointment updates in PostgreSQL (via arrival_service)
- Hazmat alert creation (via alert_service)
"""

import json
import time
from typing import Optional, Dict, Any, List
from datetime import datetime as dt
from db.mongo import detections_collection, events_collection
from db.redis import redis_client


# ==================== CONFIGURATION ====================

DEDUP_TTL = 300             # 5 minutes to prevent immediate reprocessing
BUCKET_SECONDS = 30         # grouping window
DECISION_CACHE_TTL = 3600   # cache decision for 1 hour


# ==================== REDIS KEY HELPERS ====================

def time_bucket(ts: float, bucket_seconds: int = BUCKET_SECONDS) -> int:
    """Groups timestamps in buckets for dedup."""
    return int(ts // bucket_seconds) * bucket_seconds


def dedup_key(license_plate: Optional[str], gate_id: Optional[int], ts: float) -> Optional[str]:
    """Generates Redis key for deduplication."""
    if not license_plate or gate_id is None:
        return None
    tb = time_bucket(ts)
    return f"plate:{license_plate}:gate:{gate_id}:tb:{tb}"


def decision_cache_key(license_plate: Optional[str], gate_id: Optional[int], ts: float) -> Optional[str]:
    """Generates Redis key for decision cache."""
    k = dedup_key(license_plate, gate_id, ts)
    if not k:
        return None
    return "decision:" + k


# ==================== DEDUPLICATION ====================

def is_duplicate_and_mark(license_plate: Optional[str], gate_id: Optional[int], ts: float) -> bool:
    """
    Attempts to mark detection as processed using SET NX EX.
    Returns True if already existed (duplicate), False if marked (not duplicate).
    """
    key = dedup_key(license_plate, gate_id, ts)
    if not key:
        return False
    try:
        set_ok = redis_client.set(key, "1", nx=True, ex=DEDUP_TTL)
        return not set_ok  # True if already existed
    except Exception:
        # Graceful degradation: assume not duplicate
        return False


# ==================== DECISION CACHE ====================

def get_cached_decision(license_plate: Optional[str], gate_id: Optional[int], ts: float) -> Optional[dict]:
    """Gets cached decision if exists."""
    key = decision_cache_key(license_plate, gate_id, ts)
    if not key:
        return None
    try:
        v = redis_client.get(key)
        if v:
            return json.loads(v)
    except Exception:
        pass
    return None


def cache_decision(license_plate: Optional[str], gate_id: Optional[int], ts: float, decision: dict):
    """Stores decision in Redis cache."""
    key = decision_cache_key(license_plate, gate_id, ts)
    if not key:
        return
    try:
        redis_client.set(key, json.dumps(decision), ex=DECISION_CACHE_TTL)
    except Exception:
        pass


# ==================== MONGODB PERSISTENCE ====================

def persist_detection_event(event_data: Dict[str, Any]) -> str:
    """
    Persists detection event in MongoDB (for future statistics).
    
    event_data expected:
    {
        "type": "license_plate_detection" | "hazmat_detection" | "truck_detection",
        "license_plate": "XX-XX-XX",
        "gate_id": 1,
        "timestamp": "2025-12-09T10:30:00",
        "confidence": 0.95,
        "agent": "AgentB",
        "raw_data": {...}
    }
    """
    doc = {
        **event_data,
        "created_at": dt.utcnow().isoformat(),
        "processed": False
    }
    result = detections_collection.insert_one(doc)
    return str(result.inserted_id)


def persist_decision_event(
    license_plate: str,
    gate_id: int,
    appointment_id: Optional[int],
    decision: str,
    decision_data: Dict[str, Any]
) -> str:
    """
    Persists decision event in MongoDB (for audit and statistics).
    """
    doc = {
        "type": "decision",
        "license_plate": license_plate,
        "gate_id": gate_id,
        "appointment_id": appointment_id,
        "decision": decision,  # "approved", "rejected", "manual_review", "not_found"
        "decision_data": decision_data,
        "created_at": dt.utcnow().isoformat()
    }
    result = events_collection.insert_one(doc)
    return str(result.inserted_id)


def get_detection_events(
    license_plate: Optional[str] = None,
    gate_id: Optional[int] = None,
    event_type: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """Queries detection events from MongoDB."""
    query = {}
    if license_plate:
        query["license_plate"] = license_plate
    if gate_id:
        query["gate_id"] = gate_id
    if event_type:
        query["type"] = event_type
    
    cursor = detections_collection.find(query).sort("created_at", -1).limit(limit)
    return list(cursor)


def get_decision_events(
    license_plate: Optional[str] = None,
    gate_id: Optional[int] = None,
    decision: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """Queries decision events from MongoDB."""
    query = {"type": "decision"}
    if license_plate:
        query["license_plate"] = license_plate
    if gate_id:
        query["gate_id"] = gate_id
    if decision:
        query["decision"] = decision
    
    cursor = events_collection.find(query).sort("created_at", -1).limit(limit)
    return list(cursor)


# ==================== DECISION PROCESSING (ORCHESTRATOR) ====================

def process_incoming_decision(
    license_plate: str,
    gate_id: int,
    appointment_id: int,
    decision: str,
    status: str,
    alerts: Optional[List[Dict[str, Any]]] = None,
    notes: Optional[str] = None,
    extra_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Processes a decision from the Decision Engine.
    
    Flow:
    1. Check if duplicate (Redis dedup)
    2. Check decision cache
    3. Update appointment in PostgreSQL (via arrival_service)
    4. Create alerts if needed (via alert_service)
    5. Persist event in MongoDB
    6. Cache decision in Redis
    
    Returns dict with processing status.
    """
    from db.postgres import SessionLocal
    from services.arrival_service import update_appointment_from_decision
    
    ts = time.time()
    
    # 1. Check duplicate
    if is_duplicate_and_mark(license_plate, gate_id, ts):
        return {
            "status": "skipped",
            "reason": "duplicate_detection",
            "license_plate": license_plate,
            "gate_id": gate_id
        }
    
    # 2. Check cache
    cached = get_cached_decision(license_plate, gate_id, ts)
    if cached:
        return {
            "status": "cached",
            "decision": cached,
            "license_plate": license_plate,
            "gate_id": gate_id
        }
    
    # 3. Update appointment in PostgreSQL
    db = SessionLocal()
    try:
        decision_payload = {
            "decision": decision,
            "status": status,
            "notes": notes,
            "alerts": alerts or []
        }
        
        appointment = update_appointment_from_decision(db, appointment_id, decision_payload)
        
        if not appointment:
            # Persist not found event
            persist_decision_event(
                license_plate=license_plate,
                gate_id=gate_id,
                appointment_id=appointment_id,
                decision="not_found",
                decision_data={"error": "Appointment not found"}
            )
            return {
                "status": "error",
                "reason": "appointment_not_found",
                "appointment_id": appointment_id
            }
        
        # 4. Persist decision event
        event_id = persist_decision_event(
            license_plate=license_plate,
            gate_id=gate_id,
            appointment_id=appointment_id,
            decision=decision,
            decision_data={
                "new_status": status,
                "alerts_created": len(alerts) if alerts else 0,
                "notes": notes,
                **(extra_data or {})
            }
        )
        
        # 5. Cache decision
        result = {
            "status": "processed",
            "decision": decision,
            "appointment_id": appointment_id,
            "new_status": status,
            "event_id": event_id
        }
        cache_decision(license_plate, gate_id, ts, result)
        
        return result
        
    finally:
        db.close()


def query_appointments_for_decision(time_frame: int, gate_id: int) -> Dict[str, Any]:
    """
    Queries candidate appointments for Decision Engine.
    Used when Decision Engine needs to know which appointments exist
    for a detected license plate.
    
    Returns:
    {
        "found": True/False,
        "candidates": [...],
        "message": "..."
    }
    """
    from db.postgres import SessionLocal
    from services.arrival_service import get_appointments_for_decision
    
    db = SessionLocal()
    try:
        candidates = get_appointments_for_decision(db, time_frame=time_frame, gate_id=gate_id)
        
        return {
            "found": len(candidates) > 0,
            "candidates": candidates,
            "message": f"Found {len(candidates)} candidate appointment(s)" if candidates else "No appointments found"
        }
    finally:
        db.close()
