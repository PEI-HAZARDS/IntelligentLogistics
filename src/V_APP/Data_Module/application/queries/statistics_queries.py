"""
Statistics queries — relocated from services/statistics_service.py.
No internal services/ imports.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
from bson import ObjectId

from infrastructure.persistence.mongo import (
    agent_detections_collection,
    decision_events_collection,
    statistics_hourly_collection,
    statistics_daily_collection,
    get_hourly_statistics,
)
from infrastructure.persistence.redis import (
    get_counter,
    get_counter_range,
    get_all_active_counters,
    increment_counter,
)

logger = logging.getLogger("statistics_service")

# ---------------------------------------------------------------------------
# Repeated Mongo field-path constants (avoids SonarQube S1192)
# ---------------------------------------------------------------------------
_F_DECISION = "$final_decision"
_F_TOTAL_REVIEWS = "$total_reviews"
_F_ENTRIES = "$entries"
_F_EXITS = "$exits"
_F_DAY_BUCKET = "$day_bucket"

# Cache MongoDB server version at import time to detect $percentile support.
# $percentile requires MongoDB 7.0+; on older versions aggregation silently
# returns an error which was previously swallowed.
_MONGO_SUPPORTS_PERCENTILE: bool | None = None


def _check_mongo_percentile_support() -> bool:
    global _MONGO_SUPPORTS_PERCENTILE
    if _MONGO_SUPPORTS_PERCENTILE is not None:
        return _MONGO_SUPPORTS_PERCENTILE
    try:
        from infrastructure.persistence.mongo import agent_detections_collection
        db = agent_detections_collection.database
        info = db.client.server_info()
        version_str = info.get("version", "0.0.0")
        major = int(version_str.split(".")[0])
        _MONGO_SUPPORTS_PERCENTILE = major >= 7
        if not _MONGO_SUPPORTS_PERCENTILE:
            logger.error(
                "MongoDB %s detected — $percentile aggregation requires 7.0+. "
                "Pipeline performance percentile stats will be unavailable.",
                version_str,
            )
    except Exception:
        _MONGO_SUPPORTS_PERCENTILE = False
    return _MONGO_SUPPORTS_PERCENTILE


def _log_percentile_error(exc: Exception, fn: str) -> None:
    if not _check_mongo_percentile_support():
        logger.error(
            "%s: $percentile unavailable on this MongoDB version — upgrade to 7.0+ "
            "for latency percentile stats. Error: %s",
            fn, exc,
        )
    else:
        logger.error("Failed in %s: %s", fn, exc)


def get_real_time_metrics(gate_id: int) -> Dict[str, Any]:
    try:
        counters = get_all_active_counters(gate_id)
        detections_total = counters.get("detections", 0)
        decisions_accepted = counters.get("decisions:accepted", 0)
        decisions_rejected = counters.get("decisions:rejected", 0)
        decisions_manual = counters.get("decisions:manual_review", 0)
        decisions_total = decisions_accepted + decisions_rejected + decisions_manual
        return {
            "gate_id": gate_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "current_hour": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:00"),
            "detections": {"total": detections_total, "agent_a": counters.get("detections:agent_a", 0), "agent_b": counters.get("detections:agent_b", 0), "agent_c": counters.get("detections:agent_c", 0)},
            "decisions": {"total": decisions_total, "accepted": decisions_accepted, "rejected": decisions_rejected, "manual_review": decisions_manual, "acceptance_rate": _safe_divide(decisions_accepted, decisions_total)},
            "operators": {"manual_reviews_handled": counters.get("operator:reviews", 0), "overrides": counters.get("operator:overrides", 0)},
            "errors": {"ocr_failures": counters.get("errors:ocr", 0), "api_timeouts": counters.get("errors:api_timeout", 0)},
        }
    except Exception as e:
        logger.error(f"Failed to get real-time metrics: {e}")
        return {}


def get_hourly_trend(gate_id: int, metric: str, hours: int = 24) -> Dict[str, int]:
    try:
        return get_counter_range(gate_id, metric, hours)
    except Exception as e:
        logger.error(f"Failed to get hourly trend: {e}")
        return {}


def get_detection_success_rate(gate_id: int, hours_ago: int = 24) -> List[Dict[str, Any]]:
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
        pipeline = [
            {"$match": {"timestamp": {"$gte": cutoff}, "gate_id": gate_id}},
            {"$group": {"_id": {"agent": "$agent_type", "hour": {"$dateToString": {"format": "%Y-%m-%d %H:00", "date": "$timestamp"}}}, "total_detections": {"$sum": 1}, "avg_confidence": {"$avg": "$detection_data.confidence"}, "processed_count": {"$sum": {"$cond": ["$processing.consumed_by_decision_engine", 1, 0]}}}},
            {"$project": {"_id": 0, "agent": "$_id.agent", "hour": "$_id.hour", "total_detections": 1, "avg_confidence": {"$round": ["$avg_confidence", 3]}, "processing_rate": {"$cond": [{"$eq": ["$total_detections", 0]}, 0, {"$divide": ["$processed_count", "$total_detections"]}]}}},
            {"$sort": {"hour": -1, "agent": 1}},
        ]
        return list(agent_detections_collection.aggregate(pipeline))
    except Exception as e:
        logger.error(f"Failed to get detection success rate: {e}")
        return []


def get_decision_pipeline_performance(gate_id: int, hours_ago: int = 24) -> Dict[str, Any]:
    import json as _json
    from infrastructure.persistence.redis import (
        redis_client, stats_pipeline_key, TTL_STATS_PIPELINE,
    )

    # 1. Redis cache (avoids expensive MongoDB aggregation on every dashboard poll)
    cache_key = stats_pipeline_key(gate_id, hours_ago)
    try:
        cached = redis_client.get(cache_key)
        if cached:
            return _json.loads(cached)
    except Exception:
        pass

    # 2. MongoDB aggregation (source of truth)
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
        pipeline = [
            {"$match": {"gate_id": gate_id, "created_at": {"$gte": cutoff}}},
            {"$group": {"_id": "$gate_id", "total_decisions": {"$sum": 1}, "accepted": {"$sum": {"$cond": [{"$eq": ["$final_decision", "ACCEPTED"]}, 1, 0]}}, "rejected": {"$sum": {"$cond": [{"$eq": ["$final_decision", "REJECTED"]}, 1, 0]}}, "manual_review": {"$sum": {"$cond": [{"$eq": [_F_DECISION, "MANUAL_REVIEW"]}, 1, 0]}}, "avg_pipeline_time": {"$avg": "$timing.total_pipeline_ms"}, "p50_pipeline_time": {"$percentile": {"input": "$timing.total_pipeline_ms", "p": [0.50], "method": "approximate"}}, "p95_pipeline_time": {"$percentile": {"input": "$timing.total_pipeline_ms", "p": [0.95], "method": "approximate"}}, "p99_pipeline_time": {"$percentile": {"input": "$timing.total_pipeline_ms", "p": [0.99], "method": "approximate"}}, "avg_detection_to_decision": {"$avg": "$timing.detection_to_decision_ms"}}},
            {"$project": {"_id": 0, "gate_id": "$_id", "total_decisions": 1, "decisions_by_type": {"accepted": "$accepted", "rejected": "$rejected", "manual_review": "$manual_review"}, "acceptance_rate": {"$cond": [{"$eq": ["$total_decisions", 0]}, 0, {"$divide": ["$accepted", "$total_decisions"]}]}, "manual_review_rate": {"$cond": [{"$eq": ["$total_decisions", 0]}, 0, {"$divide": ["$manual_review", "$total_decisions"]}]}, "performance": {"avg_pipeline_ms": {"$round": ["$avg_pipeline_time", 0]}, "p50_pipeline_ms": {"$round": [{"$arrayElemAt": ["$p50_pipeline_time", 0]}, 0]}, "p95_pipeline_ms": {"$round": [{"$arrayElemAt": ["$p95_pipeline_time", 0]}, 0]}, "p99_pipeline_ms": {"$round": [{"$arrayElemAt": ["$p99_pipeline_time", 0]}, 0]}, "avg_detection_to_decision_ms": {"$round": ["$avg_detection_to_decision", 0]}}}},
        ]
        result = list(decision_events_collection.aggregate(pipeline))
        data = result[0] if result else {}
        try:
            redis_client.setex(cache_key, TTL_STATS_PIPELINE, _json.dumps(data, default=str))
        except Exception:
            pass
        return data
    except Exception as e:
        _log_percentile_error(e, "get_decision_pipeline_performance")
        return {}


def get_agent_performance(agent_type: str, gate_id: int, hours_ago: int = 24) -> Dict[str, Any]:
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
        pipeline = [
            {"$match": {"agent_type": agent_type, "gate_id": gate_id, "timestamp": {"$gte": cutoff}}},
            {"$group": {"_id": None, "total_detections": {"$sum": 1}, "avg_confidence": {"$avg": "$detection_data.confidence"}, "min_confidence": {"$min": "$detection_data.confidence"}, "max_confidence": {"$max": "$detection_data.confidence"}, "processed_count": {"$sum": {"$cond": ["$processing.consumed_by_decision_engine", 1, 0]}}, "avg_latency": {"$avg": "$processing.processing_latency_ms"}}},
            {"$project": {"_id": 0, "agent_type": agent_type, "gate_id": gate_id, "total_detections": 1, "confidence_stats": {"avg": {"$round": ["$avg_confidence", 3]}, "min": {"$round": ["$min_confidence", 3]}, "max": {"$round": ["$max_confidence", 3]}}, "processing_rate": {"$cond": [{"$eq": ["$total_detections", 0]}, 0, {"$divide": ["$processed_count", "$total_detections"]}]}, "avg_latency_ms": {"$round": ["$avg_latency", 0]}}},
        ]
        result = list(agent_detections_collection.aggregate(pipeline))
        return result[0] if result else {}
    except Exception as e:
        logger.error(f"Failed to get agent performance: {e}")
        return {}


def get_complete_truck_journey(truck_id: str) -> Dict[str, Any]:
    try:
        detections_pipeline = [{"$match": {"truck_id": truck_id}}, {"$sort": {"timestamp": 1}}, {"$group": {"_id": "$truck_id", "detections": {"$push": {"agent": "$agent_type", "timestamp": "$timestamp", "confidence": "$detection_data.confidence", "data": "$detection_data"}}, "first_detection": {"$first": "$timestamp"}, "last_detection": {"$last": "$timestamp"}}}]
        detections_result = list(agent_detections_collection.aggregate(detections_pipeline))
        decision = decision_events_collection.find_one({"truck_id": truck_id})
        if not detections_result and not decision:
            return {"error": "Truck not found"}
        journey: Dict[str, Any] = {"truck_id": truck_id, "detections": detections_result[0].get("detections", []) if detections_result else [], "decision": None, "timeline": {}}
        if detections_result:
            first_detection = detections_result[0].get("first_detection")
            last_detection = detections_result[0].get("last_detection")
            journey["timeline"]["first_detection"] = first_detection.isoformat() if first_detection else None
            journey["timeline"]["last_detection"] = last_detection.isoformat() if last_detection else None
        if decision:
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
    Return operator performance metrics.
    Reads from the pre-computed operator_performance_collection first;
    falls back to a live aggregation on decision_events if the collection
    is empty (e.g. aggregator has not run yet).
    """
    try:
        from infrastructure.persistence.mongo import operator_performance_collection
        docs = list(operator_performance_collection.find({}, {"_id": 0}).sort("total_reviews", -1))
        if docs:
            return docs
    except Exception as e:
        logger.warning("operator_performance_collection read failed: %s — live fallback", e)

    # Live fallback from decision_events
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
        pipeline = [
            {"$match": {"operator_decision": {"$exists": True}, "created_at": {"$gte": cutoff}}},
            {"$group": {"_id": "$operator_decision.operator_id", "total_reviews": {"$sum": 1}, "avg_review_time_ms": {"$avg": "$timing.manual_review_duration_ms"}, "override_count": {"$sum": {"$cond": [{"$ne": [_F_DECISION, "$operator_decision.decision"]}, 1, 0]}}}},
            {"$project": {"_id": 0, "operator_id": "$_id", "total_reviews": 1, "avg_review_time_seconds": {"$round": [{"$divide": ["$avg_review_time_ms", 1000]}, 1]}, "override_rate": {"$cond": [{"$eq": [_F_TOTAL_REVIEWS, 0]}, 0, {"$divide": ["$override_count", _F_TOTAL_REVIEWS]}]}}},
            {"$sort": {"total_reviews": -1}},
        ]
        return list(decision_events_collection.aggregate(pipeline))
    except Exception as e:
        logger.error("Failed to get operator performance: %s", e)
        return []


def compute_hourly_statistics(gate_id: int, hour_timestamp: datetime = None, pg_session=None):
    """
    Aggregate detections and decisions for one hour bucket and upsert to
    statistics_hourly_collection.  If *pg_session* is provided, entry/exit
    counts are enriched from PostgreSQL visit rows for the same gate and hour.
    """
    try:
        if hour_timestamp is None:
            hour_timestamp = datetime.now(timezone.utc) - timedelta(hours=1)
        hour_bucket = hour_timestamp.replace(minute=0, second=0, microsecond=0)
        next_hour = hour_bucket + timedelta(hours=1)

        detections_pipeline = [
            {"$match": {"gate_id": gate_id, "timestamp": {"$gte": hour_bucket, "$lt": next_hour}}},
            {"$group": {"_id": "$agent_type", "count": {"$sum": 1}, "avg_confidence": {"$avg": "$detection_data.confidence"}}},
        ]
        detections_stats = list(agent_detections_collection.aggregate(detections_pipeline))

        decisions_pipeline = [
            {"$match": {"gate_id": gate_id, "created_at": {"$gte": hour_bucket, "$lt": next_hour}}},
            {"$group": {"_id": "$final_decision", "count": {"$sum": 1}}},
        ]
        decisions_stats = list(decision_events_collection.aggregate(decisions_pipeline))

        entries = exits = 0
        if pg_session is not None:
            from sqlalchemy import func as sa_func
            from infrastructure.persistence.sql_models import Visit
            entries = pg_session.query(sa_func.count(Visit.appointment_id)).filter(
                Visit.shift_gate_id == gate_id,
                Visit.entry_time >= hour_bucket,
                Visit.entry_time < next_hour,
            ).scalar() or 0
            exits = pg_session.query(sa_func.count(Visit.appointment_id)).filter(
                Visit.shift_gate_id == gate_id,
                Visit.out_time >= hour_bucket,
                Visit.out_time < next_hour,
            ).scalar() or 0

        stats_doc = {
            "gate_id": gate_id,
            "hour_bucket": hour_bucket,
            "detections": {
                "total": sum(s["count"] for s in detections_stats),
                "by_agent": {s["_id"]: s["count"] for s in detections_stats},
                "avg_confidence": {s["_id"]: round(s["avg_confidence"], 3) for s in detections_stats},
            },
            "decisions": {
                "total": sum(s["count"] for s in decisions_stats),
                "by_type": {s["_id"]: s["count"] for s in decisions_stats},
            },
            "entries": entries,
            "exits": exits,
            "computed_at": datetime.now(timezone.utc),
            "version": 1,
        }
        statistics_hourly_collection.update_one(
            {"gate_id": gate_id, "hour_bucket": hour_bucket},
            {"$set": stats_doc},
            upsert=True,
        )
        return stats_doc
    except Exception as e:
        logger.error("Failed to compute hourly statistics: %s", e)
        return None


def compute_daily_statistics(gate_id: int, day_timestamp: datetime = None, pg_session=None):
    """
    Roll up hourly docs for a full day and upsert to statistics_daily_collection.
    If *pg_session* is provided, entry/exit counts come directly from PG for
    accuracy; otherwise they are summed from hourly docs.
    """
    try:
        if day_timestamp is None:
            day_timestamp = datetime.now(timezone.utc) - timedelta(days=1)
        day_bucket = day_timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
        next_day = day_bucket + timedelta(days=1)

        hourly_docs = list(statistics_hourly_collection.find(
            {"gate_id": gate_id, "hour_bucket": {"$gte": day_bucket, "$lt": next_day}}
        ))

        total_detections = sum(d.get("detections", {}).get("total", 0) for d in hourly_docs)
        by_agent: Dict[str, int] = {}
        for d in hourly_docs:
            for agent, count in d.get("detections", {}).get("by_agent", {}).items():
                by_agent[agent] = by_agent.get(agent, 0) + count

        total_decisions = sum(d.get("decisions", {}).get("total", 0) for d in hourly_docs)
        by_type: Dict[str, int] = {}
        for d in hourly_docs:
            for dtype, count in d.get("decisions", {}).get("by_type", {}).items():
                by_type[dtype] = by_type.get(dtype, 0) + count

        if pg_session is not None:
            from sqlalchemy import func as sa_func
            from infrastructure.persistence.sql_models import Visit
            entries = pg_session.query(sa_func.count(Visit.appointment_id)).filter(
                Visit.shift_gate_id == gate_id,
                Visit.entry_time >= day_bucket,
                Visit.entry_time < next_day,
            ).scalar() or 0
            exits = pg_session.query(sa_func.count(Visit.appointment_id)).filter(
                Visit.shift_gate_id == gate_id,
                Visit.out_time >= day_bucket,
                Visit.out_time < next_day,
            ).scalar() or 0
        else:
            entries = sum(d.get("entries", 0) for d in hourly_docs)
            exits = sum(d.get("exits", 0) for d in hourly_docs)

        daily_doc = {
            "gate_id": gate_id,
            "day_bucket": day_bucket,
            "detections": {"total": total_detections, "by_agent": by_agent},
            "decisions": {"total": total_decisions, "by_type": by_type},
            "entries": entries,
            "exits": exits,
            "computed_at": datetime.now(timezone.utc),
        }
        statistics_daily_collection.update_one(
            {"gate_id": gate_id, "day_bucket": day_bucket},
            {"$set": daily_doc},
            upsert=True,
        )
        return daily_doc
    except Exception as e:
        logger.error("compute_daily_statistics failed for gate=%s: %s", gate_id, e)
        return None


def read_volume_from_mongo(from_dt: datetime, to_dt: datetime, interval: str) -> Optional[List[Dict[str, Any]]]:
    """
    Read pre-computed volume data from statistics_hourly (interval='hour') or
    statistics_daily (interval='day'|'week').
    Returns None when the relevant collection is empty so the caller can fall
    back to the PostgreSQL query.
    """
    try:
        if interval == "hour":
            pipeline = [
                {"$match": {"hour_bucket": {"$gte": from_dt, "$lte": to_dt}}},
                {"$group": {
                    "_id": "$hour_bucket",
                    "entries": {"$sum": _F_ENTRIES},
                    "exits": {"$sum": _F_EXITS},
                }},
                {"$sort": {"_id": 1}},
            ]
            docs = list(statistics_hourly_collection.aggregate(pipeline))
        elif interval == "week":
            pipeline = [
                {"$match": {"day_bucket": {"$gte": from_dt, "$lte": to_dt}}},
                {"$group": {
                    "_id": {
                        "$dateFromParts": {
                            "isoWeekYear": {"$isoWeekYear": _F_DAY_BUCKET},
                            "isoWeek": {"$isoWeek": _F_DAY_BUCKET},
                            "isoDayOfWeek": 1,
                        }
                    },
                    "entries": {"$sum": _F_ENTRIES},
                    "exits": {"$sum": _F_EXITS},
                }},
                {"$sort": {"_id": 1}},
            ]
            docs = list(statistics_daily_collection.aggregate(pipeline))
        else:  # day
            pipeline = [
                {"$match": {"day_bucket": {"$gte": from_dt, "$lte": to_dt}}},
                {"$group": {
                    "_id": _F_DAY_BUCKET,
                    "entries": {"$sum": _F_ENTRIES},
                    "exits": {"$sum": _F_EXITS},
                }},
                {"$sort": {"_id": 1}},
            ]
            docs = list(statistics_daily_collection.aggregate(pipeline))

        if not docs:
            return None  # signal caller to use PG fallback

        return [
            {
                "timestamp": d["_id"].isoformat() if hasattr(d["_id"], "isoformat") else str(d["_id"]),
                "entries": d.get("entries", 0),
                "exits": d.get("exits", 0),
            }
            for d in docs
        ]
    except Exception as e:
        logger.error("read_volume_from_mongo failed: %s", e)
        return None


def compute_operator_performance_snapshot(period_hours: int = 24) -> int:
    """
    Aggregate operator metrics from decision_events and upsert snapshots to
    operator_performance_collection.  Called by the statistics aggregator.
    Returns the number of operator documents written.
    """
    try:
        from infrastructure.persistence.mongo import operator_performance_collection
        cutoff = datetime.now(timezone.utc) - timedelta(hours=period_hours)
        pipeline = [
            {"$match": {"operator_decision": {"$exists": True}, "created_at": {"$gte": cutoff}}},
            {"$group": {
                "_id": "$operator_decision.operator_id",
                "total_reviews": {"$sum": 1},
                "avg_review_time_ms": {"$avg": "$timing.manual_review_duration_ms"},
                "override_count": {"$sum": {"$cond": [
                    {"$ne": [_F_DECISION, "$operator_decision.decision"]}, 1, 0
                ]}},
            }},
            {"$project": {
                "_id": 0,
                "operator_id": "$_id",
                "total_reviews": 1,
                "avg_review_time_seconds": {"$round": [{"$divide": ["$avg_review_time_ms", 1000]}, 1]},
                "override_rate": {"$cond": [
                    {"$eq": [_F_TOTAL_REVIEWS, 0]}, 0.0,
                    {"$divide": ["$override_count", _F_TOTAL_REVIEWS]},
                ]},
            }},
        ]
        docs = list(decision_events_collection.aggregate(pipeline))
        computed_at = datetime.now(timezone.utc)
        for doc in docs:
            doc["computed_at"] = computed_at
            doc["period_hours"] = period_hours
            operator_performance_collection.update_one(
                {"operator_id": doc["operator_id"]},
                {"$set": doc},
                upsert=True,
            )
        return len(docs)
    except Exception as e:
        logger.error("compute_operator_performance_snapshot failed: %s", e)
        return 0


def _safe_divide(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)


__all__ = [
    "get_real_time_metrics", "get_hourly_trend",
    "get_detection_success_rate", "get_decision_pipeline_performance",
    "get_agent_performance", "get_complete_truck_journey",
    "get_operator_performance", "compute_hourly_statistics",
    "compute_daily_statistics", "read_volume_from_mongo",
    "compute_operator_performance_snapshot",
]
