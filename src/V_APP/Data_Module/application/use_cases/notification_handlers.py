"""
Notification command handlers — DW-01, DW-02.

DW-01: ``cmd_create_notification`` emits a ``NotificationCreated`` outbox
       event instead of writing directly to MongoDB.  The outbox worker
       projects the event to the ``notifications`` Mongo collection.

DW-02: Read-state mutations (mark read / mark all read) are direct Mongo
       calls.  Notification read-state is pure UI state — not a domain
       aggregate — so the outbox overhead adds no value here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from domain.events import EventEnvelope, new_event_id


def cmd_create_notification(
    uow_factory,
    *,
    gate_id: int,
    title: str,
    message: str,
    notification_type: str = "info",
    appointment_id: Optional[int] = None,
    license_plate: Optional[str] = None,
    extra: Optional[dict] = None,
) -> str:
    """Emit a NotificationCreated outbox event (DW-01).

    Returns the event_id for the emitted outbox row.
    The outbox worker projects the event into MongoDB notifications collection.
    """
    event_id = new_event_id()
    payload: dict = {
        "gate_id": gate_id,
        "title": title,
        "message": message,
        "type": notification_type,
        "read": False,
        "appointment_id": appointment_id,
        "license_plate": license_plate,
        **(extra or {}),
    }

    envelope = EventEnvelope(
        event_id=event_id,
        correlation_id=str(gate_id),
        causation_id=None,
        aggregate_type="notification",
        aggregate_id=str(gate_id),
        event_type="NotificationCreated",
        event_version=1,
        occurred_at=datetime.now(timezone.utc),
        producer="data-module",
        partition_key=str(gate_id),
        payload=payload,
    )

    with uow_factory() as uow:
        uow.outbox.append(envelope, topic="notifications", key=str(gate_id))
        uow.commit()

    return event_id


def cmd_mark_notification_read(notification_id: str) -> Optional[dict]:
    """Mark a single notification as read (DW-02).

    Returns the updated document, or None if not found.
    Raises ValueError for a malformed id.
    """
    from bson import ObjectId
    from infrastructure.persistence.mongo import notifications_collection

    try:
        oid = ObjectId(notification_id)
    except Exception as exc:
        raise ValueError(f"Invalid notification id: {notification_id!r}") from exc

    return notifications_collection.find_one_and_update(
        {"_id": oid},
        {"$set": {"read": True}},
        return_document=True,
    )


def cmd_mark_all_notifications_read(gate_id: int) -> int:
    """Mark all unread notifications for a gate as read (DW-02).

    Returns the number of documents updated.
    """
    from infrastructure.persistence.mongo import notifications_collection

    result = notifications_collection.update_many(
        {"gate_id": gate_id, "read": False},
        {"$set": {"read": True}},
    )
    return result.modified_count
