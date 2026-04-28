"""
Decision queries and processing — relocated from services/decision_service.py.
Internal imports updated to application.queries.*.
"""

import time
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime as dt, timezone

from infrastructure.persistence.mongo import (
    agent_detections_collection,
    decision_events_collection,
    detections_collection,
    events_collection,
)

from infrastructure.persistence.redis import (
    is_duplicate_event as redis_is_duplicate_event,
    get_cached_decision as redis_get_decision,
    cache_decision as redis_cache_decision,
    increment_counter,
)

logger = logging.getLogger("decision_service")

DEDUP_TTL = 300
BUCKET_SECONDS = 30
DECISION_CACHE_TTL = 3600


def validate_consensus(detection: Dict[str, Any], threshold: float = 0.7) -> bool:
    """Return True if *detection* passes consensus validation.

    Delegates to utils.plate_validation.validate_consensus.
    Rejects if confidence < threshold or 'origem' is absent.
    """
    from utils.plate_validation import validate_consensus as _vc
    return _vc(detection, threshold)


def time_bucket(ts: float, bucket_seconds: int = BUCKET_SECONDS) -> int:
    return int(ts // bucket_seconds) * bucket_seconds


def dedup_key(license_plate: Optional[str], gate_id: Optional[int], ts: float) -> Optional[str]:
    if not license_plate or gate_id is None:
        return None
    tb = time_bucket(ts)
    return f"plate:{license_plate}:gate:{gate_id}:tb:{tb}"


def decision_cache_key(license_plate: Optional[str], gate_id: Optional[int], ts: float) -> Optional[str]:
    k = dedup_key(license_plate, gate_id, ts)
    return "decision:" + k if k else None


def is_duplicate_and_mark(
    _license_plate: Optional[str],
    _gate_id: Optional[int],
    _ts: float,
    *,
    event_id: Optional[str] = None,
) -> bool:
    """Check for duplicate event using event_id (Guardrail 1).

    Returns False (not duplicate) when no event_id is supplied — callers
    without an explicit id must rely on inbox dedup at the handler layer.
    """
    if not event_id:
        return False
    try:
        return redis_is_duplicate_event(event_id)
    except Exception as e:
        logger.error(f"Event-id dedup failed: {e}")
        return False


def get_cached_decision(license_plate: Optional[str], gate_id: Optional[int], ts: float) -> Optional[dict]:
    if not license_plate or gate_id is None:
        return None
    tb = time_bucket(ts)
    try:
        return redis_get_decision(license_plate, gate_id, tb)
    except Exception as e:
        logger.error(f"Failed to get cached decision: {e}")
        return None


def cache_decision_result(license_plate: Optional[str], gate_id: Optional[int], ts: float, decision: dict):
    if not license_plate or gate_id is None:
        return
    tb = time_bucket(ts)
    try:
        redis_cache_decision(license_plate, gate_id, tb, decision)
    except Exception as e:
        logger.error(f"Failed to cache decision: {e}")




def get_detection_events(license_plate: Optional[str] = None, gate_id: Optional[int] = None, event_type: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    query: dict = {}
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
    legacy_query: dict = {}
    if license_plate:
        legacy_query["license_plate"] = license_plate
    if gate_id:
        legacy_query["gate_id"] = gate_id
    if event_type:
        legacy_query["type"] = event_type
    return list(detections_collection.find(legacy_query).sort("created_at", -1).limit(limit))


def get_decision_events(license_plate: Optional[str] = None, gate_id: Optional[int] = None, decision: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    query: dict = {}
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
    legacy_query: dict = {"type": "decision"}
    if license_plate:
        legacy_query["license_plate"] = license_plate
    if gate_id:
        legacy_query["gate_id"] = gate_id
    if decision:
        legacy_query["decision"] = decision
    return list(events_collection.find(legacy_query).sort("created_at", -1).limit(limit))


def process_incoming_decision(
    license_plate: str, gate_id: int, appointment_id: int, decision: str,
    appointment_status: str, delivery_state: Optional[str] = None,
    alerts: Optional[List[Dict[str, Any]]] = None, notes: Optional[str] = None,
    extra_data: Optional[Dict[str, Any]] = None,
    *,
    event_id: Optional[str] = None,
) -> Dict[str, Any]:
    from infrastructure.persistence.postgres import SessionLocal
    from infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
    from application.use_cases.appointment_commands import (
        cmd_process_decision,
        cmd_update_visit_state,
    )
    from application.use_cases.notification_handlers import cmd_create_notification

    ts = time.time()

    if appointment_id is None:
        increment_counter(gate_id, "decisions:unmatched")
        increment_counter(gate_id, f"decisions:{decision.lower()}")
        return {"status": "persisted_unmatched", "decision": decision, "license_plate": license_plate, "gate_id": gate_id, "reason": "no_appointment_found"}

    if is_duplicate_and_mark(license_plate, gate_id, ts, event_id=event_id):
        return {"status": "skipped", "reason": "duplicate_detection", "license_plate": license_plate, "gate_id": gate_id}
    cached = get_cached_decision(license_plate, gate_id, ts)
    if cached:
        return {"status": "cached", "decision": cached, "license_plate": license_plate, "gate_id": gate_id}

    # Skip PG write when called from manual-review (already wrote via UoW)
    skip_pg = (extra_data or {}).get("_skip_pg_write", False)

    def _uow_factory():
        return SqlAlchemyUnitOfWork(SessionLocal)

    if not skip_pg:
        decision_payload = {"decision": decision, "status": appointment_status, "notes": notes, "alerts": alerts or []}
        cmd_result = cmd_process_decision(_uow_factory, appointment_id, decision_payload)
        if cmd_result is None:
            return {"status": "error", "reason": "appointment_not_found", "appointment_id": appointment_id}

        if delivery_state:
            cmd_update_visit_state(_uow_factory, appointment_id, new_state=delivery_state)

    # Mongo projection and Redis cache maintenance are handled by the outbox worker.
    result = {"status": "processed", "decision": decision, "appointment_id": appointment_id, "new_status": appointment_status}

    if alerts:
        for alert in alerts:
            alert_type = alert.get("type", "")
            if alert_type == "highway_infraction":
                title, ntype = "Highway Infraction", "danger"
            elif alert_type == "manual_review":
                title, ntype = "Manual Review Needed", "warning"
            else:
                title, ntype = "Vehicle Approved", "info"
            cmd_create_notification(_uow_factory, gate_id=gate_id, title=title, message=alert.get("message", f"Alert for {license_plate}"), notification_type=ntype, appointment_id=appointment_id, license_plate=license_plate, extra={"alert_type": alert_type})
    elif decision == "approved":
        cmd_create_notification(_uow_factory, gate_id=gate_id, title="Vehicle Approved", message=f"Truck {license_plate} approved for entry.", notification_type="info", appointment_id=appointment_id, license_plate=license_plate)
    return result


def query_appointments_for_decision(gate_id: Optional[int] = None) -> Dict[str, Any]:
    from infrastructure.persistence.postgres import SessionLocal
    from application.queries.arrival_queries import get_appointments_for_decision
    db = SessionLocal()
    try:
        candidates = get_appointments_for_decision(db, gate_id=gate_id)
        return {"found": len(candidates) > 0, "candidates": candidates, "message": f"Found {len(candidates)} candidate appointment(s)" if candidates else "No appointments found"}
    finally:
        db.close()


def update_appointment_after_infraction(license_plate: str, infraction: bool = True) -> Optional[Dict[str, Any]]:
    from infrastructure.persistence.postgres import SessionLocal
    from infrastructure.persistence.sql_models import Appointment

    # Read: find the active appointment by license plate
    db = SessionLocal()
    try:
        appointment = db.query(Appointment).filter(Appointment.truck_license_plate == license_plate, Appointment.status.in_(["in_transit", "delayed", "in_process", "unloading"])).order_by(Appointment.scheduled_start_time.desc(), Appointment.id.desc()).first()
        if not appointment:
            logger.warning(f"No active appointment found for infraction update: license_plate={license_plate}")
            return None
        appointment_id = appointment.id
        old_highway_infraction = bool(appointment.highway_infraction)
    finally:
        db.close()

    new_highway_infraction = old_highway_infraction or bool(infraction)
    if new_highway_infraction != old_highway_infraction:
        # Write via UoW + Outbox (Guardrails 2, 3, 6)
        from application.use_cases.appointment_commands import cmd_flag_highway_infraction
        from infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork

        def _uow_factory():
            return SqlAlchemyUnitOfWork(SessionLocal)

        cmd_flag_highway_infraction(_uow_factory, appointment_id)

    return {"appointment_id": appointment_id, "appointment_status": appointment.status, "old_highway_infraction": old_highway_infraction, "new_highway_infraction": new_highway_infraction}
