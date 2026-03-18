"""
Application-layer handler for the ContainerMoved command event.

Orchestrates the full transactional flow described in the refactor plan
(Steps 3–6) using the Unit of Work abstraction.

Guardrails enforced:
  1 — Idempotency via Inbox dedup gate.
  2 — Single PostgreSQL transaction (no multi-DB writes).
  3 — Side-effects persisted in Outbox, not published directly.
  4 — Inbox state machine: RECEIVED → PROCESSING → PROCESSED | FAILED.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from domain.events import ConsumeContext, EventEnvelope
from domain.interfaces import IUnitOfWork

logger = logging.getLogger(__name__)


class ContainerMovedHandler:
    """
    Processes a ``ContainerMoved`` event inside a single PostgreSQL
    transaction managed by the :class:`IUnitOfWork`.

    This handler is a pure application-layer orchestrator: it depends
    only on domain interfaces (Guardrail 6) and never imports
    SQLAlchemy sessions or engines.
    """

    def __init__(self, uow_factory: type[IUnitOfWork], **uow_kwargs: Any) -> None:
        self._uow_factory = uow_factory
        self._uow_kwargs = uow_kwargs

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def handle(self, event: EventEnvelope, ctx: ConsumeContext) -> None:
        """Execute the ContainerMoved command flow (Steps 3–6).

        Parameters
        ----------
        event:
            The ``ContainerMoved`` event envelope received from Kafka.
        ctx:
            Kafka consume context (topic, partition, offset).
        """
        with self._uow_factory(**self._uow_kwargs) as uow:  # type: ignore[call-arg]
            # ── Step 3: Inbox insert (idempotency gate) ──────────
            is_new = uow.inbox.try_insert_received(event, ctx)
            if not is_new:
                logger.info(
                    "Duplicate event %s — ACK + NOOP (Guardrail 1)",
                    event.event_id,
                )
                return

            uow.inbox.mark_processing(event.event_id)

            # ── Step 4: Acquire aggregate lock ────────────────────
            appointment_id = int(event.aggregate_id)
            aggregate = uow.containers.get_for_update(appointment_id)
            if aggregate is None:
                error_msg = f"Appointment {appointment_id} not found"
                logger.error(error_msg)
                uow.inbox.mark_failed(event.event_id, error_msg, retryable=False)
                uow.commit()
                return

            # ── Step 5: Execute command (write model only) ────────
            new_state = self._resolve_new_state(event.payload, aggregate)
            metadata = self._extract_transition_metadata(event.payload)

            uow.containers.save_state_transition(
                appointment_id, new_state, metadata
            )

            # Persist derived domain event in Outbox (Guardrail 3)
            derived_event = EventEnvelope(
                event_id=str(uuid4()),
                correlation_id=event.correlation_id,
                causation_id=event.event_id,
                aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id,
                event_type="AppointmentStateChanged",
                event_version=1,
                occurred_at=datetime.now(timezone.utc),
                producer="data-module",
                partition_key=event.partition_key,
                payload={
                    "appointment_id": appointment_id,
                    "previous_state": aggregate["status"],
                    "new_state": new_state,
                    **metadata,
                },
            )
            uow.outbox.append(
                derived_event,
                topic="appointment.state.changed",
                key=event.partition_key,
            )

            # Mark inbox PROCESSED (Guardrail 4)
            uow.inbox.mark_processed(event.event_id)

            # ── Step 6: Commit UnitOfWork ─────────────────────────
            uow.commit()

        logger.info(
            "ContainerMoved processed: appointment=%s  %s → %s",
            appointment_id,
            aggregate["status"],
            new_state,
        )

    # ------------------------------------------------------------------
    # Domain helpers (pure logic, no I/O)
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_new_state(
        payload: dict[str, Any], aggregate: dict[str, Any]
    ) -> str:
        """Determine the target appointment state from the event payload."""
        return str(payload.get("new_state", "in_process"))

    @staticmethod
    def _extract_transition_metadata(payload: dict[str, Any]) -> dict[str, Any]:
        """Pull optional transition metadata from the payload."""
        meta: dict[str, Any] = {}
        if "gate_in_id" in payload:
            meta["gate_in_id"] = payload["gate_in_id"]
        if "gate_out_id" in payload:
            meta["gate_out_id"] = payload["gate_out_id"]
        if "notes" in payload:
            meta["notes"] = payload["notes"]
        return meta
