"""
Read-side queries for workers — reads directly from PostgreSQL.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func as sa_func
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _worker_to_dict(w) -> Dict[str, Any]:
    """Convert Worker ORM to dict with role derived from relationships."""
    role = "unknown"
    if w.manager:
        role = "manager"
    elif w.operator:
        role = "operator"
    return {
        "num_worker": w.num_worker,
        "name": w.name,
        "phone": w.phone,
        "email": w.email,
        "active": w.active,
        "created_at": w.created_at.isoformat() if w.created_at else None,
        "role": role,
        "access_level": w.manager.access_level if w.manager else None,
    }


# ---------------------------------------------------------------------------
# Worker lists
# ---------------------------------------------------------------------------

def _worker_eager_options():
    from infrastructure.persistence.sql_models import Worker, Manager, Operator
    return [selectinload(Worker.manager), selectinload(Worker.operator)]


def get_all_workers(
    *,
    skip: int = 0,
    limit: int = 100,
    only_active: bool = True,
) -> List[Dict[str, Any]]:
    from infrastructure.persistence.postgres import SessionLocal
    from infrastructure.persistence.sql_models import Worker

    db = SessionLocal()
    try:
        q = db.query(Worker).options(*_worker_eager_options())
        if only_active:
            q = q.filter(Worker.active == True)  # noqa: E712
        rows = q.offset(skip).limit(limit).all()
        return [_worker_to_dict(r) for r in rows]
    finally:
        db.close()


def get_operators(*, skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
    from infrastructure.persistence.postgres import SessionLocal
    from infrastructure.persistence.sql_models import Worker, Operator

    db = SessionLocal()
    try:
        rows = (
            db.query(Worker)
            .options(*_worker_eager_options())
            .join(Operator)
            .offset(skip)
            .limit(limit)
            .all()
        )
        return [_worker_to_dict(r) for r in rows]
    finally:
        db.close()


def get_managers(*, skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
    from infrastructure.persistence.postgres import SessionLocal
    from infrastructure.persistence.sql_models import Worker, Manager

    db = SessionLocal()
    try:
        rows = (
            db.query(Worker)
            .options(*_worker_eager_options())
            .join(Manager)
            .offset(skip)
            .limit(limit)
            .all()
        )
        return [_worker_to_dict(r) for r in rows]
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Single worker
# ---------------------------------------------------------------------------

def get_worker_by_num(num_worker: str) -> Optional[Dict[str, Any]]:
    from infrastructure.persistence.postgres import SessionLocal
    from infrastructure.persistence.sql_models import Worker

    db = SessionLocal()
    try:
        w = db.query(Worker).filter(Worker.num_worker == num_worker).first()
        return _worker_to_dict(w) if w else None
    finally:
        db.close()


def get_operator_info(num_worker: str) -> Optional[Dict[str, Any]]:
    from infrastructure.persistence.postgres import SessionLocal
    from infrastructure.persistence.sql_models import Worker, Operator

    db = SessionLocal()
    try:
        w = (
            db.query(Worker)
            .join(Operator)
            .filter(Worker.num_worker == num_worker)
            .first()
        )
        return _worker_to_dict(w) if w else None
    finally:
        db.close()


def get_manager_info(num_worker: str) -> Optional[Dict[str, Any]]:
    from infrastructure.persistence.postgres import SessionLocal
    from infrastructure.persistence.sql_models import Worker, Manager

    db = SessionLocal()
    try:
        w = (
            db.query(Worker)
            .join(Manager)
            .filter(Worker.num_worker == num_worker)
            .first()
        )
        return _worker_to_dict(w) if w else None
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Dashboards
# ---------------------------------------------------------------------------

def get_operator_gate_dashboard(
    num_worker: str,
    gate_id: int,
) -> Dict[str, Any]:
    from infrastructure.persistence.postgres import SessionLocal
    from infrastructure.persistence.sql_models import Appointment

    today = date.today()
    today_str = today.isoformat()

    db = SessionLocal()
    try:
        # Upcoming arrivals for gate today
        upcoming_rows = (
            db.query(Appointment)
            .filter(
                Appointment.gate_in_id == gate_id,
                sa_func.date(Appointment.scheduled_start_time) == today,
                Appointment.status == "in_transit",
            )
            .order_by(Appointment.scheduled_start_time)
            .limit(10)
            .all()
        )

        # Stats by status for gate today
        stats_rows = (
            db.query(Appointment.status, sa_func.count(Appointment.id))
            .filter(
                Appointment.gate_in_id == gate_id,
                sa_func.date(Appointment.scheduled_start_time) == today,
            )
            .group_by(Appointment.status)
            .all()
        )
        stats_dict = {row[0]: row[1] for row in stats_rows}

        return {
            "operator_num_worker": num_worker,
            "gate_id": gate_id,
            "date": today_str,
            "upcoming_arrivals": [
                {
                    "appointment_id": a.id,
                    "license_plate": a.truck_license_plate,
                    "scheduled_time": a.scheduled_start_time.isoformat() if a.scheduled_start_time else None,
                    "terminal_id": a.terminal_id,
                    "status": a.status,
                }
                for a in upcoming_rows
            ],
            "stats": {
                "in_transit": stats_dict.get("in_transit", 0),
                "delayed": stats_dict.get("delayed", 0),
                "completed": stats_dict.get("completed", 0),
                "canceled": stats_dict.get("canceled", 0),
            },
        }
    finally:
        db.close()


def _count_shifts_today() -> int:
    """Count today's shifts from PostgreSQL."""
    try:
        from infrastructure.persistence.postgres import SessionLocal
        from infrastructure.persistence.sql_models import Shift as ShiftORM
        db = SessionLocal()
        try:
            return db.query(sa_func.count()).select_from(ShiftORM).filter(
                ShiftORM.date == date.today()
            ).scalar() or 0
        finally:
            db.close()
    except Exception as e:
        logger.warning("Failed to count shifts from PG: %s", e)
        return 0


def get_manager_overview(num_worker: str) -> Dict[str, Any]:
    from infrastructure.persistence.postgres import SessionLocal
    from infrastructure.persistence.sql_models import Appointment, Alert

    today = date.today()
    today_str = today.isoformat()

    db = SessionLocal()
    try:
        # Count distinct gates from today's appointments
        active_gates = (
            db.query(sa_func.count(sa_func.distinct(Appointment.gate_in_id)))
            .filter(sa_func.date(Appointment.scheduled_start_time) == today)
            .scalar()
        ) or 0

        # Recent alerts count (last 24h)
        cutoff_24h = datetime.now(timezone.utc) - timedelta(hours=24)
        recent_alerts = (
            db.query(sa_func.count(Alert.id))
            .filter(Alert.timestamp >= cutoff_24h)
            .scalar()
        ) or 0

        # Appointment stats by status today
        stats_rows = (
            db.query(Appointment.status, sa_func.count(Appointment.id))
            .filter(sa_func.date(Appointment.scheduled_start_time) == today)
            .group_by(Appointment.status)
            .all()
        )
        statistics = {row[0]: row[1] for row in stats_rows}

        return {
            "manager_num_worker": num_worker,
            "date": today_str,
            "active_gates": active_gates,
            "shifts_today": _count_shifts_today(),
            "recent_alerts": recent_alerts,
            "statistics": statistics,
        }
    finally:
        db.close()
