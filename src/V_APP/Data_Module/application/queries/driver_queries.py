"""
CQRS read-side queries for drivers — reads from MongoDB drivers_read
and appointments_read collections.  No SQLAlchemy dependency (Guardrail 5).
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
    return appointments_read_collection.find_one(
        {
            "driver_license": drivers_license,
            "status": {"$in": ["in_transit", "delayed", "in_process"]},
        },
        {"_id": 0},
        sort=[("scheduled_start_time", 1)],
    )


def get_driver_today_appointments(drivers_license: str) -> List[Dict[str, Any]]:
    today_str = date.today().isoformat()
    return list(
        appointments_read_collection.find(
            {
                "driver_license": drivers_license,
                "scheduled_start_date": today_str,
            },
            {"_id": 0},
        ).sort("scheduled_start_time", 1)
    )


def get_driver_appointments(
    drivers_license: str,
    *,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    return list(
        appointments_read_collection.find(
            {"driver_license": drivers_license},
            {"_id": 0},
        )
        .sort("scheduled_start_time", -1)
        .limit(limit)
    )
