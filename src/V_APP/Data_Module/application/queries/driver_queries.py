"""
CQRS read-side queries for drivers — reads from MongoDB drivers_read
and appointments_read collections with PostgreSQL fallback (Guardrail 5).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from infrastructure.persistence.mongo import (
    appointments_read_collection,
    drivers_read_collection,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PostgreSQL fallback helpers (Guardrail 5 — observable projection miss)
# ---------------------------------------------------------------------------

def _pg_verify_active_status(appointment_id: int) -> Optional[str]:
    """Return the current PG status for an appointment, or None if not found.

    Used to guard against stale MongoDB reads: if MongoDB claims the
    appointment is active (in_process / unloading) but PG already moved it
    to completed / canceled, the driver would incorrectly appear "inside
    the port". A quick single-column PG lookup lets us detect and discard
    the stale projection before returning it to the client.
    """
    from infrastructure.persistence.postgres import SessionLocal
    from infrastructure.persistence.sql_models import Appointment as AppointmentORM

    db = SessionLocal()
    try:
        row = (
            db.query(AppointmentORM.status)
            .filter(AppointmentORM.id == appointment_id)
            .first()
        )
        return row.status if row else None
    except Exception as exc:
        logger.warning("PG status verification failed for appointment %s: %s", appointment_id, exc)
        return None
    finally:
        db.close()


def _pg_fallback_active(drivers_license: str) -> Optional[Dict[str, Any]]:
    """Fall back to PostgreSQL for active appointment lookup."""
    from infrastructure.persistence.postgres import SessionLocal
    from infrastructure.persistence.sql_models import Appointment as AppointmentORM
    from application.schemas import Appointment as AppointmentSchema

    logger.info(
        "PROJECTION MISS get_driver_active_appointment — PostgreSQL fallback (Guardrail 5)"
    )
    db = SessionLocal()
    try:
        row = (
            db.query(AppointmentORM)
            .filter(
                AppointmentORM.driver_license == drivers_license,
                AppointmentORM.status.in_(["in_process", "unloading"]),
            )
            .order_by(AppointmentORM.scheduled_start_time)
            .first()
        )
        if row is None:
            return None
        return AppointmentSchema.model_validate(row).model_dump(mode="json")
    finally:
        db.close()


def _pg_fallback_today(drivers_license: str) -> List[Dict[str, Any]]:
    """Fall back to PostgreSQL for today's appointments."""
    from infrastructure.persistence.postgres import SessionLocal
    from infrastructure.persistence.sql_models import Appointment as AppointmentORM
    from application.schemas import Appointment as AppointmentSchema
    from sqlalchemy import cast, Date

    logger.info(
        "PROJECTION MISS get_driver_today_appointments — PostgreSQL fallback (Guardrail 5)"
    )
    db = SessionLocal()
    try:
        rows = (
            db.query(AppointmentORM)
            .filter(
                AppointmentORM.driver_license == drivers_license,
                cast(AppointmentORM.scheduled_start_time, Date) == date.today(),
            )
            .order_by(AppointmentORM.scheduled_start_time)
            .all()
        )
        return [
            AppointmentSchema.model_validate(r).model_dump(mode="json")
            for r in rows
        ]
    finally:
        db.close()


def _pg_fallback_history(drivers_license: str, limit: int) -> List[Dict[str, Any]]:
    """Fall back to PostgreSQL for appointment history."""
    from infrastructure.persistence.postgres import SessionLocal
    from infrastructure.persistence.sql_models import Appointment as AppointmentORM
    from application.schemas import Appointment as AppointmentSchema

    logger.info(
        "PROJECTION MISS get_driver_appointments — PostgreSQL fallback (Guardrail 5)"
    )
    db = SessionLocal()
    try:
        rows = (
            db.query(AppointmentORM)
            .filter(AppointmentORM.driver_license == drivers_license)
            .order_by(AppointmentORM.scheduled_start_time.desc())
            .limit(limit)
            .all()
        )
        return [
            AppointmentSchema.model_validate(r).model_dump(mode="json")
            for r in rows
        ]
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Public query functions
# ---------------------------------------------------------------------------

def get_drivers(
    *,
    skip: int = 0,
    limit: int = 100,
    only_active: bool = True,
) -> List[Dict[str, Any]]:
    query: dict = {}
    if only_active:
        query["active"] = True
    return list(
        drivers_read_collection.find(query, {"_id": 0, "password_hash": 0})
        .skip(skip)
        .limit(limit)
    )


def get_driver_by_license(drivers_license: str) -> Optional[Dict[str, Any]]:
    return drivers_read_collection.find_one(
        {"drivers_license": drivers_license},
        {"_id": 0, "password_hash": 0},
    )


def get_driver_active_appointment(drivers_license: str) -> Optional[Dict[str, Any]]:
    result = appointments_read_collection.find_one(
        {
            "driver_license": drivers_license,
            "status": {"$in": ["in_process", "unloading"]},
        },
        {"_id": 0},
        sort=[("scheduled_start_time", 1)],
    )
    if result is not None:
        # Guard against stale MongoDB projections: verify the appointment is
        # still active in PostgreSQL before returning it.  If the outbox worker
        # hasn't caught up yet (e.g. appointment already completed in PG),
        # the driver would otherwise appear stuck "inside the port".
        appointment_id = result.get("id")
        if appointment_id is not None:
            pg_status = _pg_verify_active_status(int(appointment_id))
            if pg_status is not None and pg_status not in ("in_process", "unloading"):
                logger.info(
                    "Stale MongoDB projection for appointment_id=%s "
                    "(mongo_status=%s pg_status=%s) — falling back to PG",
                    appointment_id, result.get("status"), pg_status,
                )
                result = None
        if result is not None:
            return result
    # Projection miss or stale — fall back to PostgreSQL (Guardrail 5)
    return _pg_fallback_active(drivers_license)


def get_driver_today_appointments(drivers_license: str) -> List[Dict[str, Any]]:
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())
    tomorrow_start = datetime.combine(today, datetime.max.time())

    # Query using scheduled_start_time range (no separate date field needed)
    results = list(
        appointments_read_collection.find(
            {
                "driver_license": drivers_license,
                "scheduled_start_time": {
                    "$gte": today_start.isoformat(),
                    "$lte": tomorrow_start.isoformat(),
                },
            },
            {"_id": 0},
        ).sort("scheduled_start_time", 1)
    )
    if results:
        return results
    # Projection miss — fall back to PostgreSQL (Guardrail 5)
    return _pg_fallback_today(drivers_license)


def get_driver_appointments(
    drivers_license: str,
    *,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    results = list(
        appointments_read_collection.find(
            {"driver_license": drivers_license},
            {"_id": 0},
        )
        .sort("scheduled_start_time", -1)
        .limit(limit)
    )
    if results:
        return results
    # Projection miss — fall back to PostgreSQL (Guardrail 5)
    return _pg_fallback_history(drivers_license, limit)
