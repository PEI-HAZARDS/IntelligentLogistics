"""
SQLAlchemy implementation of the Outbox repository.

Guardrail 3 — every domain change that should propagate is persisted
here in the same PostgreSQL transaction as the aggregate mutation.
The relay worker (Phase 1) will poll PENDING rows and publish to Kafka.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from domain.events import EventEnvelope
from domain.interfaces import IOutboxRepository
from infrastructure.persistence.inbox_outbox_models import OutboxEvent


class SqlAlchemyOutboxRepository(IOutboxRepository):
    """Concrete outbox backed by PostgreSQL via SQLAlchemy."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # IOutboxRepository
    # ------------------------------------------------------------------

    def append(self, event: EventEnvelope, *, topic: str, key: str) -> None:
        row = OutboxEvent(
            event_id=event.event_id,
            topic=topic,
            partition_key=key,
            aggregate_type=event.aggregate_type,
            aggregate_id=event.aggregate_id,
            event_type=event.event_type,
            event_version=event.event_version,
            payload=event.payload,
            status="PENDING",
        )
        self._session.add(row)
        self._session.flush()

    def fetch_batch(self, batch_size: int) -> list[dict[str, Any]]:
        rows = (
            self._session.query(OutboxEvent)
            .filter(OutboxEvent.status == "PENDING")
            .order_by(OutboxEvent.id)
            .limit(batch_size)
            .all()
        )
        return [
            {
                "id": str(r.id),
                "event_id": r.event_id,
                "topic": r.topic,
                "partition_key": r.partition_key,
                "aggregate_type": r.aggregate_type,
                "aggregate_id": r.aggregate_id,
                "event_type": r.event_type,
                "event_version": r.event_version,
                "payload": r.payload,
            }
            for r in rows
        ]

    def mark_published(self, outbox_id: str) -> None:
        row = self._get(outbox_id)
        row.status = "PUBLISHED"
        row.published_at = datetime.now(timezone.utc)
        self._session.flush()

    def mark_publish_failed(self, outbox_id: str, error: str) -> None:
        row = self._get(outbox_id)
        row.status = "FAILED"
        row.retry_count = (row.retry_count or 0) + 1
        row.last_error = error
        self._session.flush()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get(self, outbox_id: str) -> OutboxEvent:
        row = (
            self._session.query(OutboxEvent)
            .filter(OutboxEvent.id == int(outbox_id))
            .one()
        )
        return row
