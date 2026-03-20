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
    validate_agent_detection_schema,
    validate_decision_event_schema,
)
from application.queries.notification_queries import create_notification

from infrastructure.persistence.redis import (
    is_duplicate_event as redis_is_duplicate_event,
    is_duplicate_and_mark as redis_is_duplicate_legacy,
    get_cached_decision as redis_get_decision,
    cache_decision as redis_cache_decision,
    increment_counter,
    cache_appointment,
    invalidate_license_plate_cache,
)

logger = logging.getLogger("decision_service")

DEDUP_TTL = 300
BUCKET_SECONDS = 30
DECISION_CACHE_TTL = 3600


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
    license_plate: Optional[str],
    gate_id: Optional[int],
    ts: float,
    *,
    event_id: Optional[str] = None,
) -> bool:
    """Check for duplicate event. Prefers event_id when available (Guardrail 1)."""
    if event_id:
        try:
            return redis_is_duplicate_event(event_id)
        except Exception as e:
            logger.error(f"Event-id dedup failed: {e}")
            return False

    # Legacy fallback: time-window dedup (deprecated)
    if not license_plate or gate_id is None:
        return False
    tb = time_bucket(ts)
    logger.warning(
        "dedup: falling back to time-window for plate=%s gate=%s (no event_id)",
        license_plate, gate_id,
    )
    try:
        return redis_is_duplicate_legacy(license_plate, gate_id, tb)
    except Exception as e:
        logger.error(f"Deduplication check failed: {e}")
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


def persist_detection_event(event_data: Dict[str, Any]) -> str:
    try:
        timestamp_str = dt.now(timezone.utc).strftime("%s")
        detection_id = f"det_{event_data.get('agent', 'Unknown')}_{timestamp_str}_{event_data.get('gate_id', 0)}"
        agent_type_map = {"truck_detection": "AgentA", "license_plate_detection": "AgentB", "hazmat_detection": "AgentC"}
        agent_type = agent_type_map.get(event_data.get("type"), "Unknown")
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
            "kafka_partition": event_data.get("kafka_partition"),
        }
        if validate_agent_detection_schema(enhanced_doc):
            result = agent_detections_collection.insert_one(enhanced_doc)
            increment_counter(event_data.get("gate_id", 1), "detections")
            increment_counter(event_data.get("gate_id", 1), f"detections:{agent_type.lower()}")
            return str(result.inserted_id)
        else:
            logger.error("Detection event failed schema validation")
    except Exception as e:
        logger.error(f"Failed to persist enhanced detection event: {e}")
    try:
        legacy_doc = {**event_data, "created_at": dt.now(timezone.utc).isoformat(), "processed": False}
        result = detections_collection.insert_one(legacy_doc)
        return str(result.inserted_id)
    except Exception as e:
        logger.error(f"Failed to persist legacy detection event: {e}")
        raise


def persist_decision_event(license_plate: str, gate_id: int, appointment_id: Optional[int], decision: str, decision_data: Dict[str, Any]) -> Optional[str]:
    try:
        timestamp_str = dt.now(timezone.utc).strftime("%s")
        decision_id = f"dec_gate{gate_id}_{timestamp_str}_{appointment_id or '0'}"
        truck_id = decision_data.get("truck_id", f"TRUCK-{timestamp_str}")
        enhanced_doc = {
            "decision_id": decision_id,
            "truck_id": truck_id,
            "gate_id": gate_id,
            "appointment_id": appointment_id,
            "agent_detections": {
                "truck_detection": decision_data.get("truck_detection", {}),
                "license_plate_detection": {"license_plate": license_plate, "confidence": decision_data.get("lp_confidence"), "crop_url": decision_data.get("license_crop_url"), "timestamp": dt.now(timezone.utc)},
                "hazmat_detection": {"un_number": decision_data.get("un"), "kemler_code": decision_data.get("kemler"), "confidence": decision_data.get("hz_confidence"), "crop_url": decision_data.get("hazard_crop_url"), "timestamp": dt.now(timezone.utc)},
            },
            "decision_engine": {"timestamp": dt.now(timezone.utc), "decision": decision, "decision_reason": decision_data.get("decision_reason", ""), "matched_license_plate": license_plate if decision == "approved" else None, "appointment_candidates": decision_data.get("appointment_candidates", []), "processing_time_ms": decision_data.get("processing_time_ms", 0)},
            "operator_decision": decision_data.get("operator_decision"),
            "final_decision": decision_data.get("final_decision", decision),
            "final_decision_source": decision_data.get("decision_source", "agent"),
            "postgres_updates": {"appointment_updated": decision_data.get("appointment_updated", False), "appointment_new_status": decision_data.get("new_status"), "alerts_created": decision_data.get("alerts_created", 0), "update_timestamp": dt.now(timezone.utc)},
            "timing": {"detection_to_decision_ms": decision_data.get("detection_to_decision_ms", 0), "decision_to_persistence_ms": decision_data.get("decision_to_persistence_ms", 0), "total_pipeline_ms": decision_data.get("total_pipeline_ms", 0), "manual_review_duration_ms": decision_data.get("manual_review_duration_ms")},
            "created_at": dt.now(timezone.utc),
            "updated_at": dt.now(timezone.utc),
            "version": 1,
        }
        if validate_decision_event_schema(enhanced_doc):
            result = decision_events_collection.insert_one(enhanced_doc)
            logger.info(f"Persisted decision {decision_id} to decision_events")
            increment_counter(gate_id, f"decisions:{decision.lower()}")
            return str(result.inserted_id)
        else:
            logger.error("Decision event failed schema validation")
    except Exception as e:
        logger.error(f"Failed to persist enhanced decision event: {e}")
    try:
        legacy_doc = {"type": "decision", "license_plate": license_plate, "gate_id": gate_id, "appointment_id": appointment_id, "decision": decision, "decision_data": decision_data, "created_at": dt.now(timezone.utc).isoformat()}
        result = events_collection.insert_one(legacy_doc)
        return str(result.inserted_id)
    except Exception as e:
        logger.error(f"Failed to persist legacy decision event: {e}")
        return None


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

    ts = time.time()

    if appointment_id is None:
        mongo_event_id = persist_decision_event(license_plate=license_plate, gate_id=gate_id, appointment_id=None, decision=decision, decision_data={"reason": "no_appointment_found", "decision_source": (extra_data or {}).get("decision_source", "automated"), "decision_reason": (extra_data or {}).get("decision_reason", "unknown"), "alerts": alerts or [], "notes": notes, **(extra_data or {})})
        increment_counter(gate_id, "decisions:unmatched")
        increment_counter(gate_id, f"decisions:{decision.lower()}")
        result = {"status": "persisted_unmatched", "decision": decision, "license_plate": license_plate, "gate_id": gate_id, "event_id": mongo_event_id, "reason": "no_appointment_found"}
        if mongo_event_id is None:
            result["warning"] = "mongo_write_failed"
        return result

    if is_duplicate_and_mark(license_plate, gate_id, ts, event_id=event_id):
        return {"status": "skipped", "reason": "duplicate_detection", "license_plate": license_plate, "gate_id": gate_id}
    cached = get_cached_decision(license_plate, gate_id, ts)
    if cached:
        return {"status": "cached", "decision": cached, "license_plate": license_plate, "gate_id": gate_id}

    # Skip PG write when called from manual-review (already wrote via UoW)
    skip_pg = (extra_data or {}).get("_skip_pg_write", False)

    if not skip_pg:
        # PG writes via UoW + Outbox (Guardrails 2, 3, 6)
        def _uow_factory():
            return SqlAlchemyUnitOfWork(SessionLocal)

        decision_payload = {"decision": decision, "status": appointment_status, "notes": notes, "alerts": alerts or []}
        cmd_result = cmd_process_decision(_uow_factory, appointment_id, decision_payload)
        if cmd_result is None:
            persist_decision_event(license_plate=license_plate, gate_id=gate_id, appointment_id=appointment_id, decision="not_found", decision_data={"error": "Appointment not found"})
            return {"status": "error", "reason": "appointment_not_found", "appointment_id": appointment_id}

        if delivery_state:
            cmd_update_visit_state(_uow_factory, appointment_id, new_state=delivery_state)

    # Mongo event persistence (async projection — will become outbox-driven)
    mongo_event_id = persist_decision_event(license_plate=license_plate, gate_id=gate_id, appointment_id=appointment_id, decision=decision, decision_data={"new_status": appointment_status, "delivery_state": delivery_state, "alerts_created": len(alerts) if alerts else 0, "notes": notes, **(extra_data or {})})
    result = {"status": "processed", "decision": decision, "appointment_id": appointment_id, "new_status": appointment_status, "event_id": mongo_event_id}
    if mongo_event_id is None:
        result["warning"] = "mongo_write_failed"

    # Redis cache updates (async projection — will become outbox-driven)
    cache_decision_result(license_plate, gate_id, ts, result)
    cache_appointment(appointment_id, {"appointment_id": appointment_id, "license_plate": license_plate, "status": appointment_status, "gate_id": gate_id})
    invalidate_license_plate_cache(license_plate)
    increment_counter(gate_id, "decisions:processed")

    # Notifications (async projection — will become outbox-driven)
    if alerts:
        for alert in alerts:
            alert_type = alert.get("type", "")
            if alert_type == "highway_infraction":
                title, ntype = "Highway Infraction", "danger"
            elif alert_type == "manual_review":
                title, ntype = "Manual Review Needed", "warning"
            else:
                title, ntype = "Vehicle Approved", "info"
            create_notification(gate_id=gate_id, title=title, message=alert.get("message", f"Alert for {license_plate}"), notification_type=ntype, appointment_id=appointment_id, license_plate=license_plate, extra={"alert_type": alert_type})
    elif decision == "approved":
        create_notification(gate_id=gate_id, title="Vehicle Approved", message=f"Truck {license_plate} approved for entry.", notification_type="info", appointment_id=appointment_id, license_plate=license_plate)
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


def persist_infraction_event_from_kafka(truck_id: str, infraction_data: Dict[str, Any]) -> str:
    license_plate = infraction_data.get("license_plate", "UNKNOWN")
    gate_id = infraction_data.get("gate_id", 1)
    appointment_id = infraction_data.get("appointment_id")
    infraction = bool(infraction_data.get("infraction", False))
    decision = "HIGHWAY_INFRACTION" if infraction else "NO_INFRACTION"
    kafka_infraction_data = {"decision_source": "infraction_engine", "processed_at": infraction_data.get("processed_at"), "truck_id": truck_id, "un": infraction_data.get("un"), "kemler": infraction_data.get("kemler"), "alerts": ["highway_infraction"] if infraction else [], "route": "highway_restricted", "license_crop_url": infraction_data.get("license_crop_url"), "hazard_crop_url": infraction_data.get("hazard_crop_url"), "decision_reason": "hazmat_on_restricted_route" if infraction else "no_highway_infraction", "final_decision": decision, "appointment_updated": False}
    return persist_decision_event(license_plate=license_plate, gate_id=int(gate_id), appointment_id=appointment_id, decision=decision, decision_data=kafka_infraction_data)


def update_appointment_after_infraction(license_plate: str, infraction: bool = True) -> Optional[Dict[str, Any]]:
    from infrastructure.persistence.postgres import SessionLocal
    from infrastructure.persistence.sql_models import Appointment

    # Read: find the active appointment by license plate
    db = SessionLocal()
    try:
        appointment = db.query(Appointment).filter(Appointment.truck_license_plate == license_plate, Appointment.status.in_(["in_transit", "delayed", "in_process"])).order_by(Appointment.scheduled_start_time.desc(), Appointment.id.desc()).first()
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
