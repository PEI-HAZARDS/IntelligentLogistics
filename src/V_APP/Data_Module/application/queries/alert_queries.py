"""
CQRS read-side queries for alerts — reads from MongoDB alerts_read collection.
No SQLAlchemy dependency (Guardrail 5).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from infrastructure.persistence.mongo import alerts_read_collection

logger = logging.getLogger(__name__)


def get_alerts(
    *,
    skip: int = 0,
    limit: int = 100,
    alert_type: Optional[str] = None,
    visit_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    query: dict = {}
    if alert_type:
        query["type"] = alert_type
    if visit_id:
        query["visit_id"] = visit_id
    return list(
        alerts_read_collection.find(query, {"_id": 0})
        .sort("timestamp", -1)
        .skip(skip)
        .limit(limit)
    )


def get_alert_by_id(alert_id: int) -> Optional[Dict[str, Any]]:
    return alerts_read_collection.find_one({"id": alert_id}, {"_id": 0})


def get_active_alerts(limit: int = 50) -> List[Dict[str, Any]]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    return list(
        alerts_read_collection.find({"timestamp": {"$gte": cutoff}}, {"_id": 0})
        .sort("timestamp", -1)
        .limit(limit)
    )


def get_alerts_count_by_type() -> Dict[str, int]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    pipeline = [
        {"$match": {"timestamp": {"$gte": cutoff}}},
        {"$group": {"_id": "$type", "count": {"$sum": 1}}},
    ]
    return {doc["_id"]: doc["count"] for doc in alerts_read_collection.aggregate(pipeline)}


def get_alerts_for_visit(visit_id: int) -> List[Dict[str, Any]]:
    return list(
        alerts_read_collection.find({"visit_id": visit_id}, {"_id": 0})
        .sort("timestamp", -1)
    )
