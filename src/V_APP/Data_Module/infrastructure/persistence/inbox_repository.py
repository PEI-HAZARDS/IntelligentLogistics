"""
SQLAlchemy implementation of the Inbox repository.

Guardrail 1 — duplicate ``event_id`` is caught via the UNIQUE constraint
and surfaced as a boolean return from ``try_insert_received``.
Guardrail 4 — status transitions follow
RECEIVED → PROCESSING → PROCESSED | FAILED | DEAD_LETTER.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from domain.events import ConsumeContext, EventEnvelope
from domain.interfaces import IInboxRepository
from infrastructure.persistence.inbox_outbox_models import InboxEvent


class SqlAlchemyInboxRepository(IInboxRepository):
    """Concrete inbox backed by PostgreSQL via SQLAlchemy."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # IInboxRepository
    # ------------------------------------------------------------------

    def try_insert_received(self, event: EventEnvelope, ctx: ConsumeContext) -> bool:
        """Insert a RECEIVED row. Return *False* on duplicate event_id."""
        row = InboxEvent(
            event_id=event.event_id,
            topic=ctx.topic,
            partition=ctx.partition,
            offset=ctx.offset,
            aggregate_type=event.aggregate_type,
            aggregate_id=event.aggregate_id,
            event_type=event.event_type,
            event_version=event.event_version,
            status="RECEIVED",
            payload_hash=self._hash_payload(event.payload),
            payload=event.payload,
        )
        self._session.add(row)
        try:
            # Use a SAVEPOINT so IntegrityError only rolls back this insert,
            # leaving the outer transaction (and any prior flushes) intact.
            with self._session.begin_nested():
                self._session.flush()
        except IntegrityError:
            return False
        return True

    def mark_processing(self, event_id: str) -> None:
        self._update_status(event_id, "PROCESSING")

    def mark_processed(self, event_id: str) -> None:
        row = self._get(event_id)
        row.status = "PROCESSED"
        row.processed_at = datetime.now(timezone.utc)
        self._session.flush()

    def mark_failed(self, event_id: str, error: str, retryable: bool) -> None:
        row = self._get(event_id)
        row.retry_count += 1  # type: ignore[operator]
        row.last_error = error
        row.status = "FAILED" if retryable else "DEAD_LETTER"
        self._session.flush()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get(self, event_id: str) -> InboxEvent:
        row = (
            self._session.query(InboxEvent)
            .filter(InboxEvent.event_id == event_id)
            .one()
        )
        return row

    def _update_status(self, event_id: str, status: str) -> None:
        row = self._get(event_id)
        row.status = status
        self._session.flush()

    @staticmethod
    def _hash_payload(payload: dict) -> str:
        raw = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()
