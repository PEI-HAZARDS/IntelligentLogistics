"""
Handlers for the durable pending-review queue (PD-01 / Phase 4).

Both commands write to PostgreSQL through SqlAlchemyUnitOfWork + Outbox so
that Redis is populated by the outbox worker, not from the command path
directly.

cmd_store_pending_review:
    Kafka consumer calls this when Decision Engine emits MANUAL_REVIEW.
    Writes a ``pending_reviews`` PG row + ``PendingReviewCreated`` outbox event
    in a single transaction.  Replaces the old direct ``redis.setex`` call.

cmd_resolve_pending_review:
    ``POST /decisions/{event_id}/resolve`` calls this when an operator submits
    their verdict.  Acquires a row-level lock (``SELECT … FOR UPDATE``), flips
    status to APPROVED or REJECTED, and appends a ``PendingReviewResolved``
    outbox event — all in one transaction.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable
from domain.events import EventEnvelope, new_event_id
from domain.interfaces import IUnitOfWork

logger = logging.getLogger(__name__)

TTL_PENDING_REVIEW_REDIS = 1800  # 30 min — matches the old Redis-only TTL


def cmd_store_pending_review(
    uow_factory: Callable[[], IUnitOfWork],
    *,
    event_id: str,
    truck_id: str,
    gate_id: int,
    license_plate: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Persist a PENDING operator-review request.

    Returns the created row dict.
    Raises on constraint violations (duplicate event_id handled by PK).
    """
    with uow_factory() as uow:
        row = uow.pending_reviews.create(
            event_id=event_id,
            truck_id=truck_id,
            gate_id=gate_id,
            license_plate=license_plate,
            payload=payload,
        )

        outbox_event = EventEnvelope(
            event_id=new_event_id(),
            correlation_id=event_id,
            causation_id=event_id,
            aggregate_type="pending_review",
            aggregate_id=event_id,
            event_type="PendingReviewCreated",
            event_version=1,
            occurred_at=datetime.now(timezone.utc),
            producer="data-module",
            partition_key=truck_id,
            payload={
                "event_id": event_id,
                "truck_id": truck_id,
                "gate_id": gate_id,
                "license_plate": license_plate,
                "ttl": TTL_PENDING_REVIEW_REDIS,
                **{k: v for k, v in payload.items() if k not in ("event_id", "truck_id")},
            },
        )
        uow.outbox.append(outbox_event, topic="pending-review.created", key=truck_id)
        uow.commit()

    logger.info(
        "Stored pending review: event_id=%s truck_id=%s gate_id=%s plate=%s",
        event_id, truck_id, gate_id, license_plate,
    )
    return row


def cmd_resolve_pending_review(
    uow_factory: Callable[[], IUnitOfWork],
    *,
    event_id: str,
    resolution: str,
    resolved_by: str,
) -> dict[str, Any] | None:
    """
    Resolve a pending review as APPROVED or REJECTED.

    Uses SELECT … FOR UPDATE to prevent concurrent resolution races.
    Returns the updated row dict, or None if the review was not found.
    Raises ValueError for invalid resolution values.
    """
    if resolution not in ("APPROVED", "REJECTED"):
        raise ValueError(f"Invalid resolution '{resolution}': must be APPROVED or REJECTED")

    with uow_factory() as uow:
        existing = uow.pending_reviews.get_for_update(event_id)
        if existing is None:
            logger.warning("Attempted to resolve non-existent pending review event_id=%s", event_id)
            return None

        if existing["status"] != "PENDING":
            logger.warning(
                "Pending review event_id=%s already resolved as %s",
                event_id, existing["status"],
            )
            return existing

        updated = uow.pending_reviews.update_status(
            event_id, status=resolution, resolved_by=resolved_by
        )
        if not updated:
            return None

        outbox_event = EventEnvelope(
            event_id=new_event_id(),
            correlation_id=event_id,
            causation_id=event_id,
            aggregate_type="pending_review",
            aggregate_id=event_id,
            event_type="PendingReviewResolved",
            event_version=1,
            occurred_at=datetime.now(timezone.utc),
            producer="data-module",
            partition_key=existing["truck_id"],
            payload={
                "event_id": event_id,
                "truck_id": existing["truck_id"],
                "gate_id": existing["gate_id"],
                "license_plate": existing["license_plate"],
                "resolution": resolution,
                "resolved_by": resolved_by,
            },
        )
        uow.outbox.append(outbox_event, topic="pending-review.resolved", key=existing["truck_id"])
        uow.commit()

    logger.info(
        "Resolved pending review: event_id=%s resolution=%s resolved_by=%s",
        event_id, resolution, resolved_by,
    )
    # Return fresh view (resolved_at is now set)
    return {**existing, "status": resolution, "resolved_by": resolved_by}
