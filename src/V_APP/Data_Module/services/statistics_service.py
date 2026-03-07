"""
Statistics Service - Analytics and aggregation for Phase 2.
Responsibilities:
- Real-time metrics from Redis counters
- Hourly statistics from MongoDB aggregations
- Decision pipeline performance analysis
- Agent performance tracking
- Background computation jobs
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
from bson import ObjectId

from db.mongo import (
    agent_detections_collection,
    decision_events_collection,
    statistics_hourly_collection,
    get_hourly_statistics
)
from db.redis import (
    get_counter,
    get_counter_range,
    get_all_active_counters,
    increment_counter
)

logger = logging.getLogger("statistics_service")


# ==================== REAL-TIME METRICS ====================

def get_real_time_metrics(gate_id: int) -> Dict[str, Any]:
    """
    Get current hour real-time metrics from Redis counters.
    
    Args:
        gate_id: Gate identifier
        
    Returns:
        Dict with current metrics
    """
    try:
        counters = get_all_active_counters(gate_id)
        
        # Parse counters into structured metrics
        detections_total = counters.get("detections", 0)
        decisions_accepted = counters.get("decisions:accepted", 0)
        decisions_rejected = counters.get("decisions:rejected", 0)
        decisions_manual = counters.get("decisions:manual_review", 0)
        decisions_total = decisions_accepted + decisions_rejected + decisions_manual
        
        return {
            "gate_id": gate_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "current_hour": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:00"),
            "detections": {
                "total": detections_total,
                "agent_a": counters.get("detections:agent_a", 0),
                "agent_b": counters.get("detections:agent_b", 0),
                "agent_c": counters.get("detections:agent_c", 0)
            },
            "decisions": {
                "total": decisions_total,
                "accepted": decisions_accepted,
                "rejected": decisions_rejected,
                "manual_review": decisions_manual,
                "acceptance_rate": _safe_divide(decisions_accepted, decisions_total)
            },
            "operators": {
                "manual_reviews_handled": counters.get("operator:reviews", 0),
                "overrides": counters.get("operator:overrides", 0)
            },
            "errors": {
                "ocr_failures": counters.get("errors:ocr", 0),
                "api_timeouts": counters.get("errors:api_timeout", 0)
            }
        }
    except Exception as e:
        logger.error(f"Failed to get real-time metrics: {e}")
        return {}


def get_hourly_trend(gate_id: int, metric: str, hours: int = 24) -> Dict[str, int]:
    """
    Get hourly trend for a specific metric.
    
    Args:
        gate_id: Gate identifier
        metric: Metric name (e.g., "detections", "decisions:accepted")
        hours: Number of hours to look back
        
    Returns:
        Dict mapping hour to value
    """
    try:
        return get_counter_range(gate_id, metric, hours)
    except Exception as e:
        logger.error(f"Failed to get hourly trend: {e}")
        return {}


# ==================== AGGREGATION PIPELINES ====================

def get_detection_success_rate(gate_id: int, hours_ago: int = 24) -> List[Dict[str, Any]]:
    """
    Aggregate detection success rate by agent and hour.
    
    Args:
        gate_id: Gate identifier
        hours_ago: Number of hours to look back
        
    Returns:
        List of hourly statistics per agent
    """
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
        
        pipeline = [
            {
                "$match": {
                    "timestamp": {"$gte": cutoff},
                    "gate_id": gate_id
                }
            },
            {
                "$group": {
                    "_id": {
                        "agent": "$agent_type",
                        "hour": {
                            "$dateToString": {
                                "format": "%Y-%m-%d %H:00",
                                "date": "$timestamp"
                            }
                        }
                    },
                    "total_detections": {"$sum": 1},
                    "avg_confidence": {"$avg": "$detection_data.confidence"},
                    "processed_count": {
                        "$sum": {
                            "$cond": ["$processing.consumed_by_decision_engine", 1, 0]
                        }
                    }
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "agent": "$_id.agent",
                    "hour": "$_id.hour",
                    "total_detections": 1,
                    "avg_confidence": {"$round": ["$avg_confidence", 3]},
                    "processing_rate": {
                        "$cond": [
                            {"$eq": ["$total_detections", 0]},
                            0,
                            {"$divide": ["$processed_count", "$total_detections"]}
                        ]
                    }
                }
            },
            {"$sort": {"hour": -1, "agent": 1}}
        ]
        
        result = list(agent_detections_collection.aggregate(pipeline))
        logger.info(f"Detection success rate query returned {len(result)} records")
        return result
        
    except Exception as e:
        logger.error(f"Failed to get detection success rate: {e}")
        return []


def get_decision_pipeline_performance(gate_id: int, hours_ago: int = 24) -> Dict[str, Any]:
    """
    Analyze decision pipeline performance metrics.
    
    Args:
        gate_id: Gate identifier
        hours_ago: Number of hours to look back
        
    Returns:
        Performance statistics
    """
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
        
        pipeline = [
            {
                "$match": {
                    "gate_id": gate_id,
                    "created_at": {"$gte": cutoff}
                }
            },
            {
                "$group": {
                    "_id": "$gate_id",
                    "total_decisions": {"$sum": 1},
                    "accepted": {
                        "$sum": {"$cond": [{"$eq": ["$final_decision", "ACCEPTED"]}, 1, 0]}
                    },
                    "rejected": {
                        "$sum": {"$cond": [{"$eq": ["$final_decision", "REJECTED"]}, 1, 0]}
                    },
                    "manual_review": {
                        "$sum": {
                            "$cond": [
                                {"$eq": ["$decision_engine.decision", "MANUAL_REVIEW"]},
                                1,
                                0
                            ]
                        }
                    },
                    "avg_pipeline_time": {"$avg": "$timing.total_pipeline_ms"},
                    "p50_pipeline_time": {
                        "$percentile": {
                            "input": "$timing.total_pipeline_ms",
                            "p": [0.50],
                            "method": "approximate"
                        }
                    },
                    "p95_pipeline_time": {
                        "$percentile": {
                            "input": "$timing.total_pipeline_ms",
                            "p": [0.95],
                            "method": "approximate"
                        }
                    },
                    "p99_pipeline_time": {
                        "$percentile": {
                            "input": "$timing.total_pipeline_ms",
                            "p": [0.99],
                            "method": "approximate"
                        }
                    },
                    "avg_detection_to_decision": {
                        "$avg": "$timing.detection_to_decision_ms"
                    }
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "gate_id": "$_id",
                    "total_decisions": 1,
                    "decisions_by_type": {
                        "accepted": "$accepted",
                        "rejected": "$rejected",
                        "manual_review": "$manual_review"
                    },
                    "acceptance_rate": {
                        "$cond": [
                            {"$eq": ["$total_decisions", 0]},
                            0,
                            {"$divide": ["$accepted", "$total_decisions"]}
                        ]
                    },
                    "manual_review_rate": {
                        "$cond": [
                            {"$eq": ["$total_decisions", 0]},
                            0,
                            {"$divide": ["$manual_review", "$total_decisions"]}
                        ]
                    },
                    "performance": {
                        "avg_pipeline_ms": {"$round": ["$avg_pipeline_time", 0]},
                        "p50_pipeline_ms": {"$round": [{"$arrayElemAt": ["$p50_pipeline_time", 0]}, 0]},
                        "p95_pipeline_ms": {"$round": [{"$arrayElemAt": ["$p95_pipeline_time", 0]}, 0]},
                        "p99_pipeline_ms": {"$round": [{"$arrayElemAt": ["$p99_pipeline_time", 0]}, 0]},
                        "avg_detection_to_decision_ms": {
                            "$round": ["$avg_detection_to_decision", 0]
                        }
                    }
                }
            }
        ]
        
        result = list(decision_events_collection.aggregate(pipeline))
        return result[0] if result else {}
        
    except Exception as e:
        logger.error(f"Failed to get decision pipeline performance: {e}")
        return {}


def get_agent_performance(agent_type: str, gate_id: int, hours_ago: int = 24) -> Dict[str, Any]:
    """
    Analyze individual agent performance.
    
    Args:
        agent_type: Agent type (AgentA, AgentB, AgentC)
        gate_id: Gate identifier
        hours_ago: Number of hours to look back
        
    Returns:
        Agent performance metrics
    """
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
        
        pipeline = [
            {
                "$match": {
                    "agent_type": agent_type,
                    "gate_id": gate_id,
                    "timestamp": {"$gte": cutoff}
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total_detections": {"$sum": 1},
                    "avg_confidence": {"$avg": "$detection_data.confidence"},
                    "min_confidence": {"$min": "$detection_data.confidence"},
                    "max_confidence": {"$max": "$detection_data.confidence"},
                    "processed_count": {
                        "$sum": {
                            "$cond": ["$processing.consumed_by_decision_engine", 1, 0]
                        }
                    },
                    "avg_latency": {"$avg": "$processing.processing_latency_ms"}
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "agent_type": agent_type,
                    "gate_id": gate_id,
                    "total_detections": 1,
                    "confidence_stats": {
                        "avg": {"$round": ["$avg_confidence", 3]},
                        "min": {"$round": ["$min_confidence", 3]},
                        "max": {"$round": ["$max_confidence", 3]}
                    },
                    "processing_rate": {
                        "$cond": [
                            {"$eq": ["$total_detections", 0]},
                            0,
                            {"$divide": ["$processed_count", "$total_detections"]}
                        ]
                    },
                    "avg_latency_ms": {"$round": ["$avg_latency", 0]}
                }
            }
        ]
        
        result = list(agent_detections_collection.aggregate(pipeline))
        return result[0] if result else {}
        
    except Exception as e:
        logger.error(f"Failed to get agent performance: {e}")
        return {}


def get_complete_truck_journey(truck_id: str) -> Dict[str, Any]:
    """
    Reconstruct complete journey for a truck from detection to decision.
    
    Args:
        truck_id: Truck identifier
        
    Returns:
        Complete truck journey with all events
    """
    try:
        # Get all detections
        detections_pipeline = [
            {"$match": {"truck_id": truck_id}},
            {"$sort": {"timestamp": 1}},
            {
                "$group": {
                    "_id": "$truck_id",
                    "detections": {
                        "$push": {
                            "agent": "$agent_type",
                            "timestamp": "$timestamp",
                            "confidence": "$detection_data.confidence",
                            "data": "$detection_data"
                        }
                    },
                    "first_detection": {"$first": "$timestamp"},
                    "last_detection": {"$last": "$timestamp"}
                }
            }
        ]
        
        detections_result = list(agent_detections_collection.aggregate(detections_pipeline))
        
        # Get decision
        decision = decision_events_collection.find_one({"truck_id": truck_id})
        
        if not detections_result and not decision:
            return {"error": "Truck not found"}
        
        journey = {
            "truck_id": truck_id,
            "detections": detections_result[0].get("detections", []) if detections_result else [],
            "decision": None,
            "timeline": {}
        }
        
        if detections_result:
            first_detection = detections_result[0].get("first_detection")
            last_detection = detections_result[0].get("last_detection")
            
            journey["timeline"]["first_detection"] = first_detection.isoformat() if first_detection else None
            journey["timeline"]["last_detection"] = last_detection.isoformat() if last_detection else None
        
        if decision:
            # Convert ObjectId to string for JSON serialization
            decision["_id"] = str(decision["_id"])
            journey["decision"] = decision
            
            if "created_at" in decision:
                journey["timeline"]["decision_made"] = decision["created_at"].isoformat()
            
            if "postgres_updates" in decision and "update_timestamp" in decision["postgres_updates"]:
                journey["timeline"]["postgres_updated"] = decision["postgres_updates"]["update_timestamp"].isoformat()
        
        return journey
        
    except Exception as e:
        logger.error(f"Failed to get truck journey for {truck_id}: {e}")
        return {"error": str(e)}


def get_operator_performance(hours_ago: int = 24) -> List[Dict[str, Any]]:
    """
    Analyze operator manual review performance.
    
    Args:
        hours_ago: Number of hours to look back
        
    Returns:
        List of operator performance metrics
    """
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
        
        pipeline = [
            {
                "$match": {
                    "operator_decision": {"$exists": True},
                    "created_at": {"$gte": cutoff}
                }
            },
            {
                "$group": {
                    "_id": "$operator_decision.operator_id",
                    "total_reviews": {"$sum": 1},
                    "avg_review_time_ms": {
                        "$avg": "$timing.manual_review_duration_ms"
                    },
                    "override_count": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$ne": [
                                        "$decision_engine.decision",
                                        "$operator_decision.decision"
                                    ]
                                },
                                1,
                                0
                            ]
                        }
                    }
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "operator_id": "$_id",
                    "total_reviews": 1,
                    "avg_review_time_seconds": {
                        "$round": [{"$divide": ["$avg_review_time_ms", 1000]}, 1]
                    },
                    "override_rate": {
                        "$cond": [
                            {"$eq": ["$total_reviews", 0]},
                            0,
                            {"$divide": ["$override_count", "$total_reviews"]}
                        ]
                    }
                }
            },
            {"$sort": {"total_reviews": -1}}
        ]
        
        result = list(decision_events_collection.aggregate(pipeline))
        logger.info(f"Operator performance query returned {len(result)} operators")
        return result
        
    except Exception as e:
        logger.error(f"Failed to get operator performance: {e}")
        return []


# ==================== BACKGROUND COMPUTATION ====================

def compute_hourly_statistics(gate_id: int, hour_timestamp: datetime = None):
    """
    Compute and store hourly statistics for a gate.
    This should be called by a background job every hour.
    
    Args:
        gate_id: Gate identifier
        hour_timestamp: Hour to compute (default: previous hour)
    """
    try:
        if hour_timestamp is None:
            # Compute for previous hour
            hour_timestamp = datetime.now(timezone.utc) - timedelta(hours=1)
        
        # Round to hour
        hour_bucket = hour_timestamp.replace(minute=0, second=0, microsecond=0)
        next_hour = hour_bucket + timedelta(hours=1)
        
        logger.info(f"Computing hourly statistics for gate {gate_id}, hour {hour_bucket}")
        
        # Aggregate detections
        detections_pipeline = [
            {
                "$match": {
                    "gate_id": gate_id,
                    "timestamp": {"$gte": hour_bucket, "$lt": next_hour}
                }
            },
            {
                "$group": {
                    "_id": "$agent_type",
                    "count": {"$sum": 1},
                    "avg_confidence": {"$avg": "$detection_data.confidence"}
                }
            }
        ]
        
        detections_stats = list(agent_detections_collection.aggregate(detections_pipeline))
        
        # Aggregate decisions
        decisions_pipeline = [
            {
                "$match": {
                    "gate_id": gate_id,
                    "created_at": {"$gte": hour_bucket, "$lt": next_hour}
                }
            },
            {
                "$group": {
                    "_id": "$final_decision",
                    "count": {"$sum": 1}
                }
            }
        ]
        
        decisions_stats = list(decision_events_collection.aggregate(decisions_pipeline))
        
        # Build statistics document
        stats_doc = {
            "gate_id": gate_id,
            "hour_bucket": hour_bucket,
            "detections": {
                "total": sum(s["count"] for s in detections_stats),
                "by_agent": {
                    s["_id"]: s["count"] for s in detections_stats
                },
                "avg_confidence": {
                    s["_id"]: round(s["avg_confidence"], 3) for s in detections_stats
                }
            },
            "decisions": {
                "total": sum(s["count"] for s in decisions_stats),
                "by_type": {
                    s["_id"]: s["count"] for s in decisions_stats
                }
            },
            "computed_at": datetime.now(timezone.utc),
            "version": 1
        }
        
        # Upsert into statistics_hourly collection
        statistics_hourly_collection.update_one(
            {"gate_id": gate_id, "hour_bucket": hour_bucket},
            {"$set": stats_doc},
            upsert=True
        )
        
        logger.info(f"✓ Computed hourly statistics for gate {gate_id}, hour {hour_bucket}")
        return stats_doc
        
    except Exception as e:
        logger.error(f"Failed to compute hourly statistics: {e}")
        return None


# ==================== HELPER FUNCTIONS ====================

def _safe_divide(numerator: int, denominator: int) -> float:
    """Safe division returning 0 if denominator is 0."""
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)


# ==================== EXPORT ====================

__all__ = [
    # Real-time metrics
    "get_real_time_metrics",
    "get_hourly_trend",
    # Aggregation pipelines
    "get_detection_success_rate",
    "get_decision_pipeline_performance",
    "get_agent_performance",
    "get_complete_truck_journey",
    "get_operator_performance",
    # Background computation
    "compute_hourly_statistics",
]
