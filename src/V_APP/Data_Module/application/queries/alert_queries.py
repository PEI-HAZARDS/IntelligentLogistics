"""
CQRS read-side queries for alerts — reads from MongoDB alerts_read collection
with PostgreSQL fallback on projection miss (Guardrail 5).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from infrastructure.persistence.mongo import alerts_read_collection

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PostgreSQL fallback helpers (Guardrail 5)
# ---------------------------------------------------------------------------

def _pg_fallback_alerts(
    *,
    skip: int = 0,
    limit: int = 100,
    alert_type: Optional[str] = None,
    visit_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    from infrastructure.persistence.postgres import SessionLocal
    from infrastructure.persistence.sql_models import Alert

    logger.info("PROJECTION MISS get_alerts — PostgreSQL fallback (Guardrail 5)")
    db = SessionLocal()
    try:
        q = db.query(Alert)
        if alert_type:
            q = q.filter(Alert.type == alert_type)
        if visit_id:
            q = q.filter(Alert.visit_id == visit_id)
        rows = q.order_by(Alert.timestamp.desc()).offset(skip).limit(limit).all()
        return [_alert_to_dict(r) for r in rows]
    finally:
        db.close()


def _pg_fallback_active(limit: int) -> List[Dict[str, Any]]:
    from infrastructure.persistence.postgres import SessionLocal
    from infrastructure.persistence.sql_models import Alert

    logger.info("PROJECTION MISS get_active_alerts — PostgreSQL fallback (Guardrail 5)")
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        rows = (
            db.query(Alert)
            .filter(Alert.timestamp >= cutoff)
            .order_by(Alert.timestamp.desc())
            .limit(limit)
            .all()
        )
        return [_alert_to_dict(r) for r in rows]
    finally:
        db.close()


def _pg_fallback_count_by_type(
    from_date: Optional[str], to_date: Optional[str]
) -> Dict[str, int]:
    from infrastructure.persistence.postgres import SessionLocal
    from infrastructure.persistence.sql_models import Alert
    from sqlalchemy import func

    logger.info("PROJECTION MISS get_alerts_count_by_type — PostgreSQL fallback (Guardrail 5)")
    db = SessionLocal()
    try:
        q = db.query(Alert.type, func.count(Alert.id))
        if from_date:
            q = q.filter(Alert.timestamp >= f"{from_date}T00:00:00")
        if to_date:
            q = q.filter(Alert.timestamp <= f"{to_date}T23:59:59")
        if not from_date and not to_date:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            q = q.filter(Alert.timestamp >= cutoff)
        rows = q.group_by(Alert.type).all()
        return {str(r[0]): r[1] for r in rows}
    finally:
        db.close()


def _alert_to_dict(alert) -> Dict[str, Any]:
    return {
        "id": alert.id,
        "visit_id": alert.visit_id,
        "appointment_id": alert.appointment_id,
        "timestamp": alert.timestamp.isoformat() if alert.timestamp else None,
        "type": str(alert.type) if alert.type else "generic",
        "description": alert.description,
        "image_url": getattr(alert, "image_url", None),
    }


# ---------------------------------------------------------------------------
# Public query functions
# ---------------------------------------------------------------------------

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
    results = list(
        alerts_read_collection.find(query, {"_id": 0})
        .sort("timestamp", -1)
        .skip(skip)
        .limit(limit)
    )
    if results:
        return results
    return _pg_fallback_alerts(skip=skip, limit=limit, alert_type=alert_type, visit_id=visit_id)


def get_alert_by_id(alert_id: int) -> Optional[Dict[str, Any]]:
    result = alerts_read_collection.find_one({"id": alert_id}, {"_id": 0})
    if result:
        return result
    # Fallback to PG
    from infrastructure.persistence.postgres import SessionLocal
    from infrastructure.persistence.sql_models import Alert
    logger.info("PROJECTION MISS get_alert_by_id — PostgreSQL fallback (Guardrail 5)")
    db = SessionLocal()
    try:
        row = db.query(Alert).filter(Alert.id == alert_id).first()
        return _alert_to_dict(row) if row else None
    finally:
        db.close()


def get_active_alerts(limit: int = 50) -> List[Dict[str, Any]]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    results = list(
        alerts_read_collection.find({"timestamp": {"$gte": cutoff}}, {"_id": 0})
        .sort("timestamp", -1)
        .limit(limit)
    )
    if results:
        return results
    return _pg_fallback_active(limit)


def get_alerts_count_by_type(
    *,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> Dict[str, int]:
    match: dict = {}
    if from_date or to_date:
        ts_filter: dict = {}
        if from_date:
            ts_filter["$gte"] = f"{from_date}T00:00:00"
        if to_date:
            ts_filter["$lte"] = f"{to_date}T23:59:59"
        match["timestamp"] = ts_filter
    else:
        match["timestamp"] = {"$gte": (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()}

    pipeline = [
        {"$match": match},
        {"$group": {"_id": "$type", "count": {"$sum": 1}}},
    ]
    result = {doc["_id"]: doc["count"] for doc in alerts_read_collection.aggregate(pipeline)}
    if result:
        return result
    return _pg_fallback_count_by_type(from_date, to_date)


def get_alerts_for_visit(visit_id: int) -> List[Dict[str, Any]]:
    results = list(
        alerts_read_collection.find({"visit_id": visit_id}, {"_id": 0})
        .sort("timestamp", -1)
    )
    if results:
        return results
    # Fallback
    from infrastructure.persistence.postgres import SessionLocal
    from infrastructure.persistence.sql_models import Alert
    logger.info("PROJECTION MISS get_alerts_for_visit — PostgreSQL fallback (Guardrail 5)")
    db = SessionLocal()
    try:
        rows = db.query(Alert).filter(Alert.visit_id == visit_id).order_by(Alert.timestamp.desc()).all()
        return [_alert_to_dict(r) for r in rows]
    finally:
        db.close()
