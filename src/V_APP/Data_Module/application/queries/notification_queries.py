"""
Notification persistence — writes and reads against MongoDB notifications collection.
Moved from services/notification_service.py.
"""

from __future__ import annotations

from datetime import datetime as dt, timezone
from typing import Optional

from infrastructure.persistence.mongo import notifications_collection


def create_notification(
    gate_id: int,
    title: str,
    message: str,
    notification_type: str = "info",
    appointment_id: Optional[int] = None,
    license_plate: Optional[str] = None,
    extra: Optional[dict] = None,
) -> str:
    """Persists a new notification in MongoDB and returns its string id."""
    doc = {
        "gate_id": gate_id,
        "title": title,
        "message": message,
        "type": notification_type,
        "read": False,
        "created_at": dt.now(tz=timezone.utc),
        "appointment_id": appointment_id,
        "license_plate": license_plate,
        **(extra or {}),
    }
    result = notifications_collection.insert_one(doc)
    return str(result.inserted_id)
