"""
Notifications routes — persistent operator notifications stored in MongoDB.
Replaces localStorage-based notification state in the frontend.
"""

from typing import Optional, List
from datetime import datetime as dt

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from bson import ObjectId

from infrastructure.persistence.mongo import notifications_collection
from application.queries.notification_queries import create_notification  # re-export for convenience

__all__ = ["router", "create_notification"]

router = APIRouter(prefix="/notifications", tags=["Notifications"])


def _serialize(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    if isinstance(doc.get("created_at"), dt):
        doc["created_at"] = doc["created_at"].isoformat()
    return doc


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class NotificationOut(BaseModel):
    id: str
    gate_id: int
    title: str
    message: str
    type: str
    read: bool
    created_at: str
    appointment_id: Optional[int] = None
    license_plate: Optional[str] = None

    model_config = ConfigDict(extra="allow")


# ---------------------------------------------------------------------------
# GET /notifications
# ---------------------------------------------------------------------------

@router.get("", response_model=List[NotificationOut])
def list_notifications(
    gate_id: int = Query(..., description="Gate to fetch notifications for"),
    limit: int = Query(50, ge=1, le=200),
    unread_only: bool = Query(False, description="Return only unread notifications"),
):
    """
    Returns the most recent notifications for a gate, newest first.
    Pass unread_only=true to count badge on the bell icon.
    """
    query: dict = {"gate_id": gate_id}
    if unread_only:
        query["read"] = False

    docs = list(
        notifications_collection.find(query)
        .sort("created_at", -1)
        .limit(limit)
    )
    return [_serialize(d) for d in docs]


# ---------------------------------------------------------------------------
# PATCH /notifications/{notification_id}/read
# ---------------------------------------------------------------------------

@router.patch("/{notification_id}/read", response_model=NotificationOut)
def mark_notification_read(notification_id: str):
    """Marks a single notification as read."""
    try:
        oid = ObjectId(notification_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid notification id")

    result = notifications_collection.find_one_and_update(
        {"_id": oid},
        {"$set": {"read": True}},
        return_document=True,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    return _serialize(result)


# ---------------------------------------------------------------------------
# PATCH /notifications/read-all
# ---------------------------------------------------------------------------

@router.patch("/read-all")
def mark_all_notifications_read(
    gate_id: int = Query(..., description="Gate whose notifications to clear"),
):
    """Marks all unread notifications for a gate as read."""
    result = notifications_collection.update_many(
        {"gate_id": gate_id, "read": False},
        {"$set": {"read": True}},
    )
    return {"updated": result.modified_count}
