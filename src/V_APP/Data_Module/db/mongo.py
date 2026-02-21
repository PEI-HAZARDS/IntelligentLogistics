"""
MongoDB collections and indexes for Intelligent Logistics
Implements polyglot persistence strategy with:
- Granular agent detection events
- Complete decision journey tracking
- Pre-aggregated statistics
- Cache metadata
"""

from pymongo import MongoClient, ASCENDING, DESCENDING
from config import settings
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("mongo")

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

# Enhanced collections for Phase 2
agent_detections_collection = db["agent_detections"]
decision_events_collection = db["decision_events"]
statistics_hourly_collection = db["statistics_hourly"]
cache_metadata_collection = db["cache_metadata"]

# Operator UI notifications (persistent, replaces localStorage)
notifications_collection = db["notifications"]


# ==================== INDEX CREATION ====================

def create_indexes():
    """
    Creates all indexes for MongoDB collections.
    Safe to run multiple times (MongoDB ignores duplicates).
    """
    
    logger.info("Creating MongoDB indexes...")

    # ===== notifications indexes =====
    notifications_collection.create_index(
        [("gate_id", ASCENDING), ("created_at", DESCENDING)],
        name="idx_notif_gate_created"
    )
    notifications_collection.create_index(
        [("gate_id", ASCENDING), ("read", ASCENDING)],
        name="idx_notif_gate_read"
    )
    logger.info("✓ Created notifications indexes")
    
    # Legacy index
    detections_collection.create_index(
        [("timestamp", ASCENDING), ("matricula_detectada", ASCENDING), ("gate_id", ASCENDING), ("processed", ASCENDING)]
    )
    
    # ===== agent_detections indexes =====
    
    # Compound index for correlation queries
    agent_detections_collection.create_index(
        [("truck_id", ASCENDING), ("timestamp", DESCENDING)],
        name="idx_truck_timestamp"
    )
    
    # Index for unprocessed detections
    agent_detections_collection.create_index(
        [
            ("processing.consumed_by_decision_engine", ASCENDING),
            ("timestamp", DESCENDING)
        ],
        name="idx_processing_status"
    )
    
    # Index for agent-specific queries
    agent_detections_collection.create_index(
        [
            ("agent_type", ASCENDING),
            ("gate_id", ASCENDING),
            ("timestamp", DESCENDING)
        ],
        name="idx_agent_gate_timestamp"
    )
    
    # Index for license plate lookups
    agent_detections_collection.create_index(
        [("detection_data.license_plate", ASCENDING)],
        name="idx_license_plate",
        sparse=True
    )
    
    # Unique index on detection_id
    agent_detections_collection.create_index(
        [("detection_id", ASCENDING)],
        name="idx_detection_id",
        unique=True
    )
    
    logger.info("✓ Created agent_detections indexes")
    
    # ===== decision_events indexes =====
    
    # Unique index on decision_id
    decision_events_collection.create_index(
        [("decision_id", ASCENDING)],
        name="idx_decision_id",
        unique=True
    )
    
    # Truck correlation
    decision_events_collection.create_index(
        [("truck_id", ASCENDING), ("created_at", DESCENDING)],
        name="idx_truck_created"
    )
    
    # Appointment linking
    decision_events_collection.create_index(
        [("appointment_id", ASCENDING)],
        name="idx_appointment"
    )
    
    # Decision analytics
    decision_events_collection.create_index(
        [
            ("gate_id", ASCENDING),
            ("decision_engine.decision", ASCENDING),
            ("created_at", DESCENDING)
        ],
        name="idx_gate_decision_created"
    )
    
    # Manual review queue
    decision_events_collection.create_index(
        [
            ("decision_engine.decision", ASCENDING),
            ("operator_decision.timestamp", ASCENDING)
        ],
        name="idx_manual_review",
        sparse=True
    )
    
    # Performance analysis
    decision_events_collection.create_index(
        [("timing.total_pipeline_ms", ASCENDING)],
        name="idx_pipeline_performance"
    )
    
    # License plate search
    decision_events_collection.create_index(
        [("agent_detections.license_plate_detection.license_plate", ASCENDING)],
        name="idx_decision_license_plate",
        sparse=True
    )
    
    logger.info("✓ Created decision_events indexes")
    
    # ===== statistics_hourly indexes =====
    
    # Time-series queries
    statistics_hourly_collection.create_index(
        [("gate_id", ASCENDING), ("hour_bucket", DESCENDING)],
        name="idx_gate_hour"
    )
    
    # Performance analysis
    statistics_hourly_collection.create_index(
        [("decisions.avg_processing_time_ms", ASCENDING)],
        name="idx_avg_processing_time"
    )
    
    # Unique constraint on gate + hour
    statistics_hourly_collection.create_index(
        [("gate_id", ASCENDING), ("hour_bucket", ASCENDING)],
        name="idx_gate_hour_unique",
        unique=True
    )
    
    logger.info("✓ Created statistics_hourly indexes")
    
    # ===== cache_metadata indexes =====
    
    cache_metadata_collection.create_index(
        [("cache_key_pattern", ASCENDING), ("timestamp", DESCENDING)],
        name="idx_cache_pattern_timestamp"
    )
    
    logger.info("✓ Created cache_metadata indexes")
    
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
        "decision_engine.decision": "MANUAL_REVIEW",
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