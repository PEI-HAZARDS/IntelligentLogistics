"""
Notifications routes — persistent operator notifications stored in MongoDB.
Replaces localStorage-based notification state in the frontend.
"""

from typing import Annotated, Optional, List
from datetime import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from application.use_cases.notification_handlers import (
    cmd_mark_notification_read,
    cmd_mark_all_notifications_read,
)
from infrastructure.persistence.mongo import notifications_collection
from utils.auth_token import get_current_claims

__all__ = ["router"]

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
    gate_id: Annotated[int, Query(description="Gate to fetch notifications for")],
    claims: Annotated[dict, Depends(get_current_claims)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    unread_only: Annotated[bool, Query(description="Return only unread notifications")] = False,
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

@router.patch("/{notification_id}/read", response_model=NotificationOut, responses={400: {"description": "Invalid notification id"}, 404: {"description": "Notification not found"}})
def mark_notification_read(
    notification_id: str,
    claims: Annotated[dict, Depends(get_current_claims)],
):
    """Marks a single notification as read."""
    try:
        result = cmd_mark_notification_read(notification_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid notification id")

    if result is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    return _serialize(result)


# ---------------------------------------------------------------------------
# PATCH /notifications/read-all
# ---------------------------------------------------------------------------

@router.patch("/read-all")
def mark_all_notifications_read(
    gate_id: Annotated[int, Query(description="Gate whose notifications to clear")],
    claims: Annotated[dict, Depends(get_current_claims)],
):
    """Marks all unread notifications for a gate as read."""
    updated = cmd_mark_all_notifications_read(gate_id)
    return {"updated": updated}
