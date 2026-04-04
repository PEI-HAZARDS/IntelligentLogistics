"""
Read-side queries for drivers — reads directly from PostgreSQL.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _driver_to_dict(driver) -> Dict[str, Any]:
    return {
        "drivers_license": driver.drivers_license,
        "name": driver.name,
        "company_nif": driver.company_nif,
        "mobile_device_token": driver.mobile_device_token,
        "active": driver.active,
        "created_at": driver.created_at.isoformat() if driver.created_at else None,
        "current_appointment_id": driver.current_appointment_id,
    }


# ---------------------------------------------------------------------------
# Public query functions
# ---------------------------------------------------------------------------

def get_drivers(
    *,
    skip: int = 0,
    limit: int = 100,
    only_active: bool = True,
) -> List[Dict[str, Any]]:
    from infrastructure.persistence.postgres import SessionLocal
    from infrastructure.persistence.sql_models import Driver

    db = SessionLocal()
    try:
        q = db.query(Driver)
        if only_active:
            q = q.filter(Driver.active == True)  # noqa: E712
        rows = q.offset(skip).limit(limit).all()
        return [_driver_to_dict(r) for r in rows]
    finally:
        db.close()


def get_driver_by_license(drivers_license: str) -> Optional[Dict[str, Any]]:
    from infrastructure.persistence.postgres import SessionLocal
    from infrastructure.persistence.sql_models import Driver

    db = SessionLocal()
    try:
        row = db.query(Driver).filter(Driver.drivers_license == drivers_license).first()
        return _driver_to_dict(row) if row else None
    finally:
        db.close()


def get_driver_active_appointment(drivers_license: str) -> Optional[Dict[str, Any]]:
    from infrastructure.persistence.postgres import SessionLocal
    from infrastructure.persistence.sql_models import Appointment as AppointmentORM
    from application.schemas import Appointment as AppointmentSchema

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


def get_driver_today_appointments(drivers_license: str) -> List[Dict[str, Any]]:
    from infrastructure.persistence.postgres import SessionLocal
    from infrastructure.persistence.sql_models import Appointment as AppointmentORM
    from application.schemas import Appointment as AppointmentSchema
    from sqlalchemy import cast, Date

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


def get_driver_appointments(
    drivers_license: str,
    *,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    from infrastructure.persistence.postgres import SessionLocal
    from infrastructure.persistence.sql_models import Appointment as AppointmentORM
    from application.schemas import Appointment as AppointmentSchema

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
