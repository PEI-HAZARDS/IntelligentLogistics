"""
Notification Service — persists operator UI notifications to MongoDB.
Called by other services (e.g. decision_service) when actionable events occur.
The HTTP-facing CRUD lives in routes/notifications.py.
"""

from typing import Optional
from datetime import datetime as dt, timezone

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
    """
    Persists a new notification document in MongoDB and returns its string id.

    Args:
        gate_id:           The gate this notification belongs to.
        title:             Short notification title (shown in the bell dropdown).
        message:           Full notification body.
        notification_type: 'info' | 'warning' | 'danger'
        appointment_id:    Optional linked appointment.
        license_plate:     Optional truck plate.
        extra:             Additional fields merged into the document.

    Returns:
        Inserted document id as a hex string.
    """
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
