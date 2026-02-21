"""
Decision Service - Processing decisions from Decision Engine
Responsibilities:
- Deduplication via Redis (SET NX)
- Decision caching in Redis (hot data + decisions)
- Event persistence in MongoDB (agent_detections + decision_events)
- Appointment updates in PostgreSQL (via arrival_service)
- Hazmat alert creation (via alert_service)
- Real-time metrics tracking
"""

import json
import time
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime as dt, timezone

# MongoDB collections
from db.mongo import (
    agent_detections_collection,
    decision_events_collection,
    detections_collection,  # Legacy
    events_collection,  # Legacy
    validate_agent_detection_schema,
    validate_decision_event_schema
)
from services.notification_service import create_notification

# Redis operations
from db.redis import (
    is_duplicate_and_mark as redis_is_duplicate,
    get_cached_decision as redis_get_decision,
    cache_decision as redis_cache_decision,
    increment_counter,
    cache_appointment,
    invalidate_appointment_cache,
    cache_license_plate_appointments,
    invalidate_license_plate_cache
)

logger = logging.getLogger("decision_service")


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
    Uses enhanced Redis layer.
    """
    if not license_plate or gate_id is None:
        return False
    tb = time_bucket(ts)
    try:
        return redis_is_duplicate(license_plate, gate_id, tb)
    except Exception as e:
        logger.error(f"Deduplication check failed: {e}")
        return False


# ==================== DECISION CACHE ====================

def get_cached_decision(license_plate: Optional[str], gate_id: Optional[int], ts: float) -> Optional[dict]:
    """
    Gets cached decision if exists.
    Uses enhanced Redis layer.
    """
    if not license_plate or gate_id is None:
        return None
    tb = time_bucket(ts)
    try:
        return redis_get_decision(license_plate, gate_id, tb)
    except Exception as e:
        logger.error(f"Failed to get cached decision: {e}")
        return None


def cache_decision_result(license_plate: Optional[str], gate_id: Optional[int], ts: float, decision: dict):
    """
    Stores decision in Redis cache.
    Uses enhanced Redis layer.
    """
    if not license_plate or gate_id is None:
        return
    tb = time_bucket(ts)
    try:
        redis_cache_decision(license_plate, gate_id, tb, decision)
    except Exception as e:
        logger.error(f"Failed to cache decision: {e}")


# ==================== MONGODB PERSISTENCE ====================

def persist_detection_event(event_data: Dict[str, Any]) -> str:
    """
    Persists detection event in enhanced MongoDB collections.
    
    Creates entries in both:
    1. agent_detections (new enhanced schema)
    2. detections (legacy, for backward compatibility)
    
    event_data expected:
    {
        "type": "license_plate_detection" | "hazmat_detection" | "truck_detection",
        "license_plate": "XX-XX-XX",
        "gate_id": 1,
        "timestamp": "2025-12-09T10:30:00",
        "confidence": 0.95,
        "agent": "AgentB",
        "raw_data": {...},
        "truck_id": "TRUCK-12345"  # Optional correlation ID
    }
    """
    try:
        # Generate detection ID
        timestamp_str = dt.now(timezone.utc).strftime("%s")
        detection_id = f"det_{event_data.get('agent', 'Unknown')}_{timestamp_str}_{event_data.get('gate_id', 0)}"
        
        # Map event type to agent type
        agent_type_map = {
            "truck_detection": "AgentA",
            "license_plate_detection": "AgentB",
            "hazmat_detection": "AgentC"
        }
        agent_type = agent_type_map.get(event_data.get("type"), "Unknown")
        
        # Build enhanced document
        enhanced_doc = {
            "detection_id": detection_id,
            "truck_id": event_data.get("truck_id", f"TRUCK-{timestamp_str}"),
            "agent_type": agent_type,
            "gate_id": event_data.get("gate_id", 1),
            "timestamp": dt.fromisoformat(event_data["timestamp"]) if isinstance(event_data.get("timestamp"), str) else dt.now(timezone.utc),
            "detection_data": {
                "type": event_data.get("type"),
                "confidence": event_data.get("confidence", 0.0),
                "crop_url": event_data.get("raw_data", {}).get("crop_url", ""),
                "license_plate": event_data.get("license_plate"),
                "ocr_raw": event_data.get("raw_data", {}).get("ocr_raw"),
                "un_number": event_data.get("raw_data", {}).get("un"),
                "kemler_code": event_data.get("raw_data", {}).get("kemler"),
            },
            "processing": {
                "consumed_by_decision_engine": False,
                "decision_engine_timestamp": None,
                "correlated_truck_id": event_data.get("truck_id"),
                "processing_latency_ms": 0
            },
            "created_at": dt.now(timezone.utc),
            "kafka_offset": event_data.get("kafka_offset"),
            "kafka_partition": event_data.get("kafka_partition")
        }
        
        # Validate schema
        if validate_agent_detection_schema(enhanced_doc):
            result = agent_detections_collection.insert_one(enhanced_doc)
            logger.debug(f"Persisted detection {detection_id} to agent_detections")
            
            # Increment real-time counter
            increment_counter(event_data.get("gate_id", 1), "detections")
            increment_counter(event_data.get("gate_id", 1), f"detections:{agent_type.lower()}")
            
            return str(result.inserted_id)
        else:
            logger.error("Detection event failed schema validation")
            
    except Exception as e:
        logger.error(f"Failed to persist enhanced detection event: {e}")
    
    # Fallback to legacy collection
    try:
        legacy_doc = {
            **event_data,
            "created_at": dt.now(timezone.utc).isoformat(),
            "processed": False
        }
        result = detections_collection.insert_one(legacy_doc)
        return str(result.inserted_id)
    except Exception as e:
        logger.error(f"Failed to persist legacy detection event: {e}")
        raise


def persist_decision_event(
    license_plate: str,
    gate_id: int,
    appointment_id: Optional[int],
    decision: str,
    decision_data: Dict[str, Any]
) -> str:
    """
    Persists decision event in enhanced MongoDB collections.
    
    Creates comprehensive decision event with complete journey.
    """
    try:
        # Generate decision ID
        timestamp_str = dt.now(timezone.utc).strftime("%s")
        decision_id = f"dec_gate{gate_id}_{timestamp_str}_{appointment_id or '0'}"
        
        truck_id = decision_data.get("truck_id", f"TRUCK-{timestamp_str}")
        
        # Build enhanced decision event
        enhanced_doc = {
            "decision_id": decision_id,
            "truck_id": truck_id,
            "gate_id": gate_id,
            "appointment_id": appointment_id,
            
            # Agent detections (embedded for complete context)
            "agent_detections": {
                "truck_detection": decision_data.get("truck_detection", {}),
                "license_plate_detection": {
                    "license_plate": license_plate,
                    "confidence": decision_data.get("lp_confidence"),
                    "crop_url": decision_data.get("license_crop_url"),
                    "timestamp": dt.now(timezone.utc)
                },
                "hazmat_detection": {
                    "un_number": decision_data.get("un"),
                    "kemler_code": decision_data.get("kemler"),
                    "confidence": decision_data.get("hz_confidence"),
                    "crop_url": decision_data.get("hazard_crop_url"),
                    "timestamp": dt.now(timezone.utc)
                }
            },
            
            # Decision engine logic
            "decision_engine": {
                "timestamp": dt.now(timezone.utc),
                "decision": decision,
                "decision_reason": decision_data.get("decision_reason", ""),
                "matched_license_plate": license_plate if decision == "approved" else None,
                "appointment_candidates": decision_data.get("appointment_candidates", []),
                "processing_time_ms": decision_data.get("processing_time_ms", 0)
            },
            
            # Operator intervention (if manual review)
            "operator_decision": decision_data.get("operator_decision"),
            
            # Final outcome
            "final_decision": decision_data.get("final_decision", decision),
            "final_decision_source": decision_data.get("decision_source", "agent"),
            
            # PostgreSQL updates
            "postgres_updates": {
                "appointment_updated": decision_data.get("appointment_updated", False),
                "appointment_new_status": decision_data.get("new_status"),
                "alerts_created": decision_data.get("alerts_created", 0),
                "update_timestamp": dt.now(timezone.utc)
            },
            
            # Timing analysis
            "timing": {
                "detection_to_decision_ms": decision_data.get("detection_to_decision_ms", 0),
                "decision_to_persistence_ms": decision_data.get("decision_to_persistence_ms", 0),
                "total_pipeline_ms": decision_data.get("total_pipeline_ms", 0),
                "manual_review_duration_ms": decision_data.get("manual_review_duration_ms")
            },
            
            # Audit
            "created_at": dt.now(timezone.utc),
            "updated_at": dt.now(timezone.utc),
            "version": 1
        }
        
        # Validate and insert
        if validate_decision_event_schema(enhanced_doc):
            result = decision_events_collection.insert_one(enhanced_doc)
            logger.info(f"Persisted decision {decision_id} to decision_events")
            
            # Increment real-time counters
            increment_counter(gate_id, f"decisions:{decision.lower()}")
            
            return str(result.inserted_id)
        else:
            logger.error("Decision event failed schema validation")
            
    except Exception as e:
        logger.error(f"Failed to persist enhanced decision event: {e}")
    
    # Fallback to legacy collection
    try:
        legacy_doc = {
            "type": "decision",
            "license_plate": license_plate,
            "gate_id": gate_id,
            "appointment_id": appointment_id,
            "decision": decision,
            "decision_data": decision_data,
            "created_at": dt.now(timezone.utc).isoformat()
        }
        result = events_collection.insert_one(legacy_doc)
        return str(result.inserted_id)
    except Exception as e:
        logger.error(f"Failed to persist legacy decision event: {e}")
        raise


def get_detection_events(
    license_plate: Optional[str] = None,
    gate_id: Optional[int] = None,
    event_type: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """Queries detection events from MongoDB (Phase 2 collections with legacy fallback)."""
    # Phase 2 query (agent_detections_collection)
    query = {}
    if license_plate:
        query["detection_data.license_plate"] = license_plate
    if gate_id:
        query["gate_id"] = gate_id
    if event_type:
        query["detection_data.type"] = event_type
    
    try:
        cursor = agent_detections_collection.find(query).sort("created_at", -1).limit(limit)
        results = list(cursor)
        if results:
            return results
    except Exception as e:
        logger.warning(f"Phase 2 detection query failed, falling back to legacy: {e}")
    
    # Legacy fallback
    legacy_query = {}
    if license_plate:
        legacy_query["license_plate"] = license_plate
    if gate_id:
        legacy_query["gate_id"] = gate_id
    if event_type:
        legacy_query["type"] = event_type
    
    cursor = detections_collection.find(legacy_query).sort("created_at", -1).limit(limit)
    return list(cursor)


def get_decision_events(
    license_plate: Optional[str] = None,
    gate_id: Optional[int] = None,
    decision: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """Queries decision events from MongoDB (Phase 2 collections with legacy fallback)."""
    # Phase 2 query (decision_events_collection)
    query = {}
    if license_plate:
        query["agent_detections.license_plate_detection.license_plate"] = license_plate
    if gate_id:
        query["gate_id"] = gate_id
    if decision:
        query["final_decision"] = decision
    
    try:
        cursor = decision_events_collection.find(query).sort("created_at", -1).limit(limit)
        results = list(cursor)
        if results:
            return results
    except Exception as e:
        logger.warning(f"Phase 2 decision query failed, falling back to legacy: {e}")
    
    # Legacy fallback
    legacy_query = {"type": "decision"}
    if license_plate:
        legacy_query["license_plate"] = license_plate
    if gate_id:
        legacy_query["gate_id"] = gate_id
    if decision:
        legacy_query["decision"] = decision
    
    cursor = events_collection.find(legacy_query).sort("created_at", -1).limit(limit)
    return list(cursor)


# ==================== DECISION PROCESSING (ORCHESTRATOR) ====================

def process_incoming_decision(
    license_plate: str,
    gate_id: int,
    appointment_id: int,
    decision: str,
    appointment_status: str,
    delivery_state: Optional[str] = None,
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
    from services.arrival_service import update_appointment_from_decision, update_visit_status
    
    ts = time.time()

    # ------------------------------------------------------------------ #
    # UNMATCHED TRUCK — no appointment found by the Decision Engine        #
    # Skip PostgreSQL update; persist the full decision to MongoDB so the  #
    # event is never lost and is visible in the operator interface.        #
    # ------------------------------------------------------------------ #
    if appointment_id is None:
        logger.info(
            f"[process_incoming_decision] No appointment for plate={license_plate} "
            f"gate={gate_id} decision={decision} — persisting to MongoDB only"
        )
        event_id = persist_decision_event(
            license_plate=license_plate,
            gate_id=gate_id,
            appointment_id=None,
            decision=decision,
            decision_data={
                "reason": "no_appointment_found",
                "decision_source": (extra_data or {}).get("decision_source", "automated"),
                "decision_reason": (extra_data or {}).get("decision_reason", "unknown"),
                "alerts": alerts or [],
                "notes": notes,
                **(extra_data or {}),
            },
        )
        increment_counter(gate_id, "decisions:unmatched")
        increment_counter(gate_id, f"decisions:{decision.lower()}")
        return {
            "status": "persisted_unmatched",
            "decision": decision,
            "license_plate": license_plate,
            "gate_id": gate_id,
            "event_id": event_id,
            "reason": "no_appointment_found",
        }

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
            "status": appointment_status,
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
        
        if delivery_state:
            update_visit_status(db, appointment_id, new_state=delivery_state)

        # 4. Persist decision event
        event_id = persist_decision_event(
            license_plate=license_plate,
            gate_id=gate_id,
            appointment_id=appointment_id,
            decision=decision,
            decision_data={
                "new_status": appointment_status,
                "delivery_state": delivery_state,
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
            "new_status": appointment_status,
            "event_id": event_id
        }
        cache_decision_result(license_plate, gate_id, ts, result)
        
        # 6. Cache appointment for hot data access
        if appointment:
            cache_appointment(appointment_id, {
                "appointment_id": appointment_id,
                "license_plate": license_plate,
                "driver_name": getattr(appointment.driver, 'name', 'Unknown') if appointment.driver else 'Unknown',
                "status": appointment_status,
                "scheduled_start": appointment.scheduled_start_time.isoformat() if appointment.scheduled_start_time else None,
                "gate_id": gate_id
            })
            
        # 7. Invalidate license plate cache (data updated)
        invalidate_license_plate_cache(license_plate)
        
        # 8. Increment real-time metrics
        increment_counter(gate_id, "decisions:processed")

        # 9. Persist operator notification when alerts are present
        if alerts:
            for alert in alerts:
                alert_type = alert.get("type", "")
                if alert_type == "highway_infraction":
                    title = "Highway Infraction"
                    ntype = "danger"
                elif alert_type == "manual_review":
                    title = "Manual Review Needed"
                    ntype = "warning"
                else:
                    title = "Vehicle Approved"
                    ntype = "info"
                create_notification(
                    gate_id=gate_id,
                    title=title,
                    message=alert.get("message", f"Alert for {license_plate}"),
                    notification_type=ntype,
                    appointment_id=appointment_id,
                    license_plate=license_plate,
                    extra={"alert_type": alert_type},
                )
        elif decision == "approved":
            create_notification(
                gate_id=gate_id,
                title="Vehicle Approved",
                message=f"Truck {license_plate} approved for entry.",
                notification_type="info",
                appointment_id=appointment_id,
                license_plate=license_plate,
            )

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


# ==================== KAFKA CONSUMER HELPERS ====================

def persist_decision_event_from_kafka(decision_data: Dict[str, Any]) -> str:
    """
    Adapter function for Kafka consumer to persist decision events.
    Transforms Kafka message structure to decision_service format.
    """
    license_plate = decision_data.get("license_plate", "UNKNOWN")
    gate_id = decision_data.get("gate_id", 1) 
    appointment_id = decision_data.get("appointment_id")
    decision = decision_data.get("decision", "UNKNOWN")
    
    # Build decision_data structure
    kafka_decision_data = {
        "agent_decision": decision_data.get("agent_decision"),
        "agent_decision_reason": decision_data.get("agent_decision_reason"),
        "operator_decision": decision_data.get("operator_decision"),
        "operator_decision_reason": decision_data.get("operator_decision_reason"),
        "decision_source": decision_data.get("decision_source", "unknown"),
        "processed_at": decision_data.get("processed_at"),
        "truck_id": decision_data.get("truck_id"),
        "un": decision_data.get("un"),
        "kemler": decision_data.get("kemler"),
        "alerts": decision_data.get("alerts", []),
        "route": decision_data.get("route", ""),
        "license_crop_url": decision_data.get("license_crop_url"),
        "hazard_crop_url": decision_data.get("hazard_crop_url"),
    }
    
    return persist_decision_event(
        license_plate=license_plate,
        gate_id=gate_id,
        appointment_id=appointment_id,
        decision=decision,
        decision_data=kafka_decision_data
    )


def update_appointment_after_decision(
    license_plate: str,
    gate_id: int,
    decision_data: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Updates appointment status after an ACCEPTED decision.
    Delegates to update_appointment_from_decision for consistency
    (alerts, notes, ensure_arrival_id all handled in one place).
    
    Also auto-triggers highway_infraction if gate metadata indicates
    a restricted highway gate.
    """
    from db.postgres import SessionLocal
    from models.sql_models import Appointment
    from services.arrival_service import update_appointment_from_decision
    
    db = SessionLocal()
    try:
        # Find appointment by license plate and gate
        appointment = db.query(Appointment).filter(
            Appointment.truck_license_plate == license_plate,
            Appointment.gate_in_id == gate_id,
            Appointment.status.in_(['in_transit', 'delayed'])
        ).first()
        

        if not appointment:
            logger.warning(f"No appointment found for license_plate={license_plate}, gate_id={gate_id}")
            return None
        else:
            logger.info(f"Appointment found for license_plate={license_plate}, gate_id={gate_id}, appointment_status={appointment.status}")

        
        # Build decision payload for canonical update
        decision_payload = {
            "decision": decision_data.get("decision", "ACCEPTED"),
            "status": "in_process",
            "notes": decision_data.get("decision_reason", ""),
            "alerts": decision_data.get("alerts", []),
        }
        
        # Delegate to canonical update (handles alerts, notes, ensure_arrival_id)
        updated = update_appointment_from_decision(db, appointment.id, decision_payload)
        
        if not updated:
            return None
        
        # Fix 6: Auto-trigger highway_infraction based on gate metadata
        gate_type = decision_data.get("gate_type", "")
        if gate_type == "highway_restricted" and not updated.highway_infraction:
            updated.highway_infraction = True
            db.commit()
            db.refresh(updated)
            logger.info(f"Highway infraction auto-flagged for appointment {updated.id} (gate_type=highway_restricted)")
        
        old_status = "in_transit"
        logger.info(f"Appointment {updated.id} updated: {old_status} -> in_process")
        
        return {
            "appointment_id": updated.id,
            "old_status": old_status,
            "new_status": 'in_process',
            "highway_infraction": updated.highway_infraction,
        }
    
    except Exception as e:
        logger.error(f"Error updating appointment: {e}", exc_info=True)
        db.rollback()
        return None
    finally:
        db.close()
