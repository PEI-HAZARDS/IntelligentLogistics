"""
MongoDB collections and indexes for Intelligent Logistics
Implements polyglot persistence strategy with:
- Granular agent detection events
- Complete decision journey tracking
- Pre-aggregated statistics
- CQRS read models (appointments_read)
"""

from pymongo import MongoClient, ASCENDING, DESCENDING
from config import settings
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("mongo")

_FIELD_DECISION = _FIELD_DECISION

# Initialize MongoDB client
mongo_client = MongoClient(
    settings.mongo_url,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000
)

db = mongo_client["intelligent_logistics"]

# ==================== COLLECTIONS ====================

# Legacy collections (for backward compatibility)
detections_collection = db["detections"]
events_collection = db["events"]
system_logs_collection = db["system_logs"]
ocr_failures_collection = db["ocr_failures"]

# Enhanced collections
agent_detections_collection = db["agent_detections"]
decision_events_collection = db["decision_events"]
statistics_hourly_collection = db["statistics_hourly"]
statistics_daily_collection = db["statistics_daily"]
operator_performance_collection = db["operator_performance"]
company_metrics_collection = db["company_metrics"]

# Scale-up read model (BR-29): at current port volume the GET /arrivals/{id}
# read path is Redis → PG (two-tier).  For high-volume deployments this
# collection can be activated as a middle tier: extend the outbox worker to
# project AppointmentStateChanged events here, then restore the Mongo block
# in routes/arrivals.py::get_arrival.  Collection + indexes are kept ready.
appointments_read_collection = db["appointments_read"]

# Operator UI notifications (persistent, replaces localStorage)
notifications_collection = db["notifications"]


# ==================== INDEX CREATION ====================

def _drop_index_safe(collection, index_name: str):
    """Drop an index if it exists, ignoring errors."""
    try:
        collection.drop_index(index_name)
    except Exception:
        pass


# Retention policy (seconds)
TTL_NOTIFICATIONS     = 30  * 24 * 3600   # 30 days
TTL_AGENT_DETECTIONS  = 30  * 24 * 3600   # 30 days
TTL_DECISION_EVENTS   = 90  * 24 * 3600   # 90 days
TTL_LEGACY            = 7   * 24 * 3600   # 7 days  (legacy: detections, events)
TTL_SYSTEM_LOGS       = 30  * 24 * 3600   # 30 days
TTL_OCR_FAILURES      = 30  * 24 * 3600   # 30 days
TTL_STATS_LONG        = 400 * 24 * 3600   # 400 days (statistics_*, operator_performance, company_metrics)


def create_indexes():
    """
    Creates all indexes for MongoDB collections.
    Safe to run multiple times (MongoDB ignores duplicates).
    Drops and recreates indexes whose options may have changed.
    """

    logger.info("Creating MongoDB indexes...")

    # Drop indexes whose options changed so create_index can recreate them.
    _drop_index_safe(decision_events_collection, "idx_decision_id")
    # BR-37 (Hypothesis A): replace non-unique idx_appointment with unique version
    _drop_index_safe(decision_events_collection, "idx_appointment")

    # ===== notifications =====
    notifications_collection.create_index(
        [("gate_id", ASCENDING), ("created_at", DESCENDING)],
        name="idx_notif_gate_created",
    )
    notifications_collection.create_index(
        [("gate_id", ASCENDING), ("read", ASCENDING)],
        name="idx_notif_gate_read",
    )
    notifications_collection.create_index(
        [("created_at", ASCENDING)],
        name="idx_notif_ttl",
        expireAfterSeconds=TTL_NOTIFICATIONS,
    )
    logger.info("✓ notifications indexes")

    # ===== legacy collections =====
    detections_collection.create_index(
        [("timestamp", ASCENDING), ("matricula_detectada", ASCENDING),
         ("gate_id", ASCENDING), ("processed", ASCENDING)],
    )
    detections_collection.create_index(
        [("created_at", ASCENDING)],
        name="idx_detections_ttl",
        expireAfterSeconds=TTL_LEGACY,
    )
    events_collection.create_index(
        [("created_at", ASCENDING)],
        name="idx_events_ttl",
        expireAfterSeconds=TTL_LEGACY,
    )
    system_logs_collection.create_index(
        [("created_at", ASCENDING)],
        name="idx_system_logs_ttl",
        expireAfterSeconds=TTL_SYSTEM_LOGS,
    )
    ocr_failures_collection.create_index(
        [("created_at", ASCENDING)],
        name="idx_ocr_failures_ttl",
        expireAfterSeconds=TTL_OCR_FAILURES,
    )
    logger.info("✓ legacy collection TTL indexes")

    # ===== agent_detections =====
    agent_detections_collection.create_index(
        [("truck_id", ASCENDING), ("timestamp", DESCENDING)],
        name="idx_truck_timestamp",
    )
    agent_detections_collection.create_index(
        [("processing.consumed_by_decision_engine", ASCENDING), ("timestamp", DESCENDING)],
        name="idx_processing_status",
    )
    agent_detections_collection.create_index(
        [("agent_type", ASCENDING), ("gate_id", ASCENDING), ("timestamp", DESCENDING)],
        name="idx_agent_gate_timestamp",
    )
    agent_detections_collection.create_index(
        [("detection_data.license_plate", ASCENDING)],
        name="idx_license_plate",
        sparse=True,
    )
    agent_detections_collection.create_index(
        [("detection_id", ASCENDING)],
        name="idx_detection_id",
        unique=True,
    )
    agent_detections_collection.create_index(
        [("created_at", ASCENDING)],
        name="idx_agent_detections_ttl",
        expireAfterSeconds=TTL_AGENT_DETECTIONS,
    )
    logger.info("✓ agent_detections indexes")

    # ===== decision_events =====
    decision_events_collection.create_index(
        [("decision_id", ASCENDING)],
        name="idx_decision_id",
        unique=True,
        partialFilterExpression={"decision_id": {"$type": "string"}},
    )
    decision_events_collection.create_index(
        [("truck_id", ASCENDING), ("created_at", DESCENDING)],
        name="idx_truck_created",
    )
    decision_events_collection.create_index(
        [("appointment_id", ASCENDING)],
        name="idx_appointment",
        unique=True,
        partialFilterExpression={"appointment_id": {"$type": "int"}},
    )
    decision_events_collection.create_index(
        [("gate_id", ASCENDING), (_FIELD_DECISION, ASCENDING), ("created_at", DESCENDING)],
        name="idx_gate_decision_created",
    )
    decision_events_collection.create_index(
        [(_FIELD_DECISION, ASCENDING), ("operator_decision.timestamp", ASCENDING)],
        name="idx_manual_review",
        sparse=True,
    )
    decision_events_collection.create_index(
        [("timing.total_pipeline_ms", ASCENDING)],
        name="idx_pipeline_performance",
    )
    decision_events_collection.create_index(
        [("agent_detections.license_plate_detection.license_plate", ASCENDING)],
        name="idx_decision_license_plate",
        sparse=True,
    )
    decision_events_collection.create_index(
        [("created_at", ASCENDING)],
        name="idx_decision_events_ttl",
        expireAfterSeconds=TTL_DECISION_EVENTS,
    )
    logger.info("✓ decision_events indexes")

    # ===== statistics_hourly =====
    statistics_hourly_collection.create_index(
        [("gate_id", ASCENDING), ("hour_bucket", DESCENDING)],
        name="idx_gate_hour",
    )
    statistics_hourly_collection.create_index(
        [("decisions.avg_processing_time_ms", ASCENDING)],
        name="idx_avg_processing_time",
    )
    statistics_hourly_collection.create_index(
        [("gate_id", ASCENDING), ("hour_bucket", ASCENDING)],
        name="idx_gate_hour_unique",
        unique=True,
    )
    statistics_hourly_collection.create_index(
        [("hour_bucket", ASCENDING)],
        name="idx_stats_hourly_ttl",
        expireAfterSeconds=TTL_STATS_LONG,
    )
    logger.info("✓ statistics_hourly indexes")

    # ===== statistics_daily =====
    statistics_daily_collection.create_index(
        [("gate_id", ASCENDING), ("day_bucket", ASCENDING)],
        name="idx_stats_daily_gate_day",
        unique=True,
    )
    statistics_daily_collection.create_index(
        [("day_bucket", ASCENDING)],
        name="idx_stats_daily_ttl",
        expireAfterSeconds=TTL_STATS_LONG,
    )
    logger.info("✓ statistics_daily indexes")

    # ===== operator_performance =====
    operator_performance_collection.create_index(
        [("operator_id", ASCENDING), ("computed_at", DESCENDING)],
        name="idx_op_perf_operator_time",
    )
    operator_performance_collection.create_index(
        [("computed_at", ASCENDING)],
        name="idx_op_perf_ttl",
        expireAfterSeconds=TTL_STATS_LONG,
    )
    logger.info("✓ operator_performance indexes")

    # ===== company_metrics =====
    company_metrics_collection.create_index(
        [("company_nif", ASCENDING), ("computed_at", DESCENDING)],
        name="idx_company_metrics_nif_time",
    )
    company_metrics_collection.create_index(
        [("computed_at", ASCENDING)],
        name="idx_company_metrics_ttl",
        expireAfterSeconds=TTL_STATS_LONG,
    )
    logger.info("✓ company_metrics indexes")

    # ===== appointments_read (CQRS projection) =====
    appointments_read_collection.create_index(
        [("appointment_id", ASCENDING)],
        name="idx_appts_read_appointment_id",
        unique=True,
    )
    appointments_read_collection.create_index(
        [("driver_license", ASCENDING), ("status", ASCENDING)],
        name="idx_appts_read_driver_status",
    )
    logger.info("✓ appointments_read indexes")

    logger.info("✅ All MongoDB indexes created successfully")


# ==================== INITIALIZATION ====================

try:
    create_indexes()
except Exception as e:
    logger.error(f"Failed to create indexes: {e}")


# ==================== HELPER FUNCTIONS ====================

def get_agent_detections_for_truck(truck_id: str, limit: int = 100):
    """
    Get all agent detections for a specific truck, ordered by timestamp.
    
    Args:
        truck_id: Truck identifier
        limit: Maximum number of results
        
    Returns:
        List of detection documents
    """
    return list(
        agent_detections_collection
        .find({"truck_id": truck_id})
        .sort("timestamp", DESCENDING)
        .limit(limit)
    )


def get_unprocessed_detections(agent_type: str = None, limit: int = 100):
    """
    Get detections not yet consumed by Decision Engine.
    
    Args:
        agent_type: Filter by agent type (AgentA, AgentB, AgentC)
        limit: Maximum number of results
        
    Returns:
        List of unprocessed detection documents
    """
    query = {"processing.consumed_by_decision_engine": False}
    if agent_type:
        query["agent_type"] = agent_type
    
    return list(
        agent_detections_collection
        .find(query)
        .sort("timestamp", ASCENDING)
        .limit(limit)
    )


def get_decision_by_truck(truck_id: str):
    """
    Get decision event for a specific truck.
    
    Args:
        truck_id: Truck identifier
        
    Returns:
        Decision event document or None
    """
    return decision_events_collection.find_one({"truck_id": truck_id})


def get_decision_by_appointment(appointment_id: int):
    """
    Get decision event for a specific appointment.
    
    Args:
        appointment_id: PostgreSQL appointment ID
        
    Returns:
        Decision event document or None
    """
    return decision_events_collection.find_one({"appointment_id": appointment_id})


def get_pending_manual_reviews(gate_id: int = None, limit: int = 50):
    """
    Get decisions awaiting manual review.
    
    Args:
        gate_id: Filter by gate
        limit: Maximum number of results
        
    Returns:
        List of decision events pending manual review
    """
    query = {
        _FIELD_DECISION: "MANUAL_REVIEW",
        "operator_decision": {"$exists": False}
    }
    if gate_id:
        query["gate_id"] = gate_id
    
    return list(
        decision_events_collection
        .find(query)
        .sort("created_at", ASCENDING)
        .limit(limit)
    )


def get_hourly_statistics(gate_id: int, hours_ago: int = 24):
    """
    Get hourly statistics for a gate.
    
    Args:
        gate_id: Gate identifier
        hours_ago: Number of hours to look back
        
    Returns:
        List of hourly statistics documents
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    
    return list(
        statistics_hourly_collection
        .find({
            "gate_id": gate_id,
            "hour_bucket": {"$gte": cutoff}
        })
        .sort("hour_bucket", DESCENDING)
    )


# ==================== DATA VALIDATION ====================

def validate_agent_detection_schema(doc: dict) -> bool:
    """
    Validates an agent detection document against expected schema.
    
    Required fields:
    - detection_id
    - truck_id
    - agent_type
    - gate_id
    - timestamp
    - detection_data
    """
    required_fields = [
        "detection_id", "truck_id", "agent_type",
        "gate_id", "timestamp", "detection_data"
    ]
    
    for field in required_fields:
        if field not in doc:
            logger.warning(f"Missing required field: {field}")
            return False
    
    if doc["agent_type"] not in ["AgentA", "AgentB", "AgentC"]:
        logger.warning(f"Invalid agent_type: {doc['agent_type']}")
        return False

    plate = (doc.get("detection_data") or {}).get("license_plate")
    if plate is not None:
        try:
            from utils.plate_validation import is_valid_plate_relaxed
            if not is_valid_plate_relaxed(plate):
                logger.warning("Detection schema: invalid license_plate format %r", plate)
                return False
        except ImportError:
            pass

    confidence = (doc.get("detection_data") or {}).get("confidence")
    if confidence is not None and float(confidence) < 0.5:
        logger.warning("Detection schema: confidence %.3f below minimum threshold — rejected", confidence)
        return False

    origin = doc.get("origin")
    if origin is not None and origin not in {"IA", "Manual"}:
        logger.warning("Detection schema: invalid origin %r (expected 'IA' or 'Manual') — rejected", origin)
        return False

    return True


def validate_decision_event_schema(doc: dict) -> bool:
    """
    Validates a decision event document against expected schema.
    
    Required fields:
    - decision_id
    - truck_id
    - gate_id
    - agent_detections
    - decision_engine
    """
    required_fields = [
        "decision_id", "truck_id", "gate_id",
        "agent_detections", "decision_engine"
    ]
    
    for field in required_fields:
        if field not in doc:
            logger.warning(f"Missing required field: {field}")
            return False
    
    return True