"""
Decision audit command handlers (DW-08).

DW-08: cmd_record_manual_review_audit emits an ``OperatorReviewCompleted``
       outbox event instead of writing directly to MongoDB.  The outbox
       worker projects the event to the ``decision_events`` Mongo collection
       via the generic projection path (project_to_mongo else-branch).

       For approved decisions a ``NotificationCreated`` outbox event is also
       emitted so the operator dashboard receives the approval notification.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from domain.events import EventEnvelope, new_event_id


def cmd_record_manual_review_audit(
    uow_factory,
    *,
    appointment_id: int,
    license_plate: str,
    gate_id: int,
    decision: str,
    appointment_status: str,
    notes: Optional[str] = None,
    operator_id: Optional[str] = None,
) -> str:
    """Emit an OperatorReviewCompleted outbox event (DW-08).

    Returns the event_id of the emitted outbox row.
    The outbox worker upserts the event to the ``decision_events`` MongoDB
    collection and, for approved decisions, the ``NotificationCreated`` handler
    projects the approval notification to the ``notifications`` collection.
    """
    event_id = new_event_id()
    payload: dict = {
        "appointment_id": appointment_id,
        "license_plate": license_plate,
        "gate_id": gate_id,
        "decision": decision,
        "appointment_status": appointment_status,
        "notes": notes,
        "operator_id": operator_id,
        "manual_review": True,
    }

    envelope = EventEnvelope(
        event_id=event_id,
        correlation_id=str(appointment_id),
        causation_id=None,
        aggregate_type="appointment",
        aggregate_id=str(appointment_id),
        event_type="OperatorReviewCompleted",
        event_version=1,
        occurred_at=datetime.now(timezone.utc),
        producer="data-module",
        partition_key=str(gate_id or 0),
        payload=payload,
    )

    with uow_factory() as uow:
        uow.outbox.append(envelope, topic="decision.audit", key=str(gate_id or 0))
        uow.commit()

    # Approved decisions emit a notification via the notification outbox path.
    if decision == "approved":
        from application.use_cases.notification_handlers import cmd_create_notification
        cmd_create_notification(
            uow_factory,
            gate_id=gate_id or 0,
            title="Vehicle Approved",
            message=f"Truck {license_plate} approved for entry after manual review.",
            notification_type="info",
            appointment_id=appointment_id,
            license_plate=license_plate,
        )

    return event_id
