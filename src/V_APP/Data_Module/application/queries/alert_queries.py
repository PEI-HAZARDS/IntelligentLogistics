"""
Read-side queries for alerts — reads directly from PostgreSQL.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
    from infrastructure.persistence.postgres import SessionLocal
    from infrastructure.persistence.sql_models import Alert

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


def get_alert_by_id(alert_id: int) -> Optional[Dict[str, Any]]:
    from infrastructure.persistence.redis import redis_client, alert_detail_key, TTL_ALERT_DETAIL
    import json as _json

    # 1. Redis hot cache (BR-38)
    try:
        raw = redis_client.get(alert_detail_key(alert_id))
        if raw:
            return _json.loads(raw)
    except Exception:
        pass

    # 2. PostgreSQL source of truth
    from infrastructure.persistence.postgres import SessionLocal
    from infrastructure.persistence.sql_models import Alert

    db = SessionLocal()
    try:
        row = db.query(Alert).filter(Alert.id == alert_id).first()
        if row is None:
            return None
        result = _alert_to_dict(row)
        try:
            redis_client.setex(alert_detail_key(alert_id), TTL_ALERT_DETAIL, _json.dumps(result))
        except Exception:
            pass
        return result
    finally:
        db.close()


def get_active_alerts(limit: int = 50) -> List[Dict[str, Any]]:
    from infrastructure.persistence.redis import (
        redis_client, active_alerts_list_key, TTL_ACTIVE_ALERTS_LIST,
    )
    import json as _json

    # 1. Redis short-TTL cache (BR-38) — only for the default batch size
    if limit == 50:
        try:
            raw = redis_client.get(active_alerts_list_key())
            if raw:
                return _json.loads(raw)
        except Exception:
            pass

    # 2. PostgreSQL source of truth
    from infrastructure.persistence.postgres import SessionLocal
    from infrastructure.persistence.sql_models import Alert

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
        result = [_alert_to_dict(r) for r in rows]
        if limit == 50:
            try:
                redis_client.setex(active_alerts_list_key(), TTL_ACTIVE_ALERTS_LIST, _json.dumps(result))
            except Exception:
                pass
        return result
    finally:
        db.close()


def get_alerts_count_by_type(
    *,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> Dict[str, int]:
    from infrastructure.persistence.postgres import SessionLocal
    from infrastructure.persistence.sql_models import Alert
    from sqlalchemy import func

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


def get_alerts_for_visit(visit_id: int) -> List[Dict[str, Any]]:
    from infrastructure.persistence.postgres import SessionLocal
    from infrastructure.persistence.sql_models import Alert

    db = SessionLocal()
    try:
        rows = db.query(Alert).filter(Alert.visit_id == visit_id).order_by(Alert.timestamp.desc()).all()
        return [_alert_to_dict(r) for r in rows]
    finally:
        db.close()
