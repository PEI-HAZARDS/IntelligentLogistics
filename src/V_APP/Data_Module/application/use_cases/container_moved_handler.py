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
from datetime import date, datetime, timezone
from typing import Any
from domain.events import ConsumeContext, EventEnvelope, new_event_id
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
            aggregate = uow.appointment_state.get_for_update(appointment_id)
            if aggregate is None:
                error_msg = f"Appointment {appointment_id} not found"
                logger.error(error_msg)
                uow.inbox.mark_failed(event.event_id, error_msg, retryable=False)
                uow.commit()
                return

            # ── Step 5: Execute command (write model only) ────────
            new_state = self._resolve_new_state(event.payload, aggregate)
            metadata = self._extract_transition_metadata(event.payload)

            uow.appointment_state.save_state_transition(
                appointment_id, new_state, metadata
            )

            # Auto-create visit when transitioning to in_process (accept)
            visit_created = False
            if new_state == "in_process" and aggregate["status"] != "in_process":
                visit_created = self._auto_create_visit(
                    uow, appointment_id, event.payload, aggregate
                )

            # Persist derived domain event in Outbox (Guardrail 3)
            derived_event = EventEnvelope(
                event_id=new_event_id(),
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
                    "visit_created": visit_created,
                    **metadata,
                },
            )
            uow.outbox.append(
                derived_event,
                topic="appointment.state.changed",
                key=event.partition_key,
            )

            # Notifications for accepted trucks — durable outbox events (Guardrail 3)
            if new_state == "in_process" and aggregate["status"] != "in_process":
                self._append_accept_notification_events(
                    uow, appointment_id, event.payload, aggregate
                )

            # Mark inbox PROCESSED (Guardrail 4)
            uow.inbox.mark_processed(event.event_id)

            # ── Step 6: Commit UnitOfWork ─────────────────────────
            uow.commit()

        logger.info(
            "ContainerMoved processed: appointment=%s  %s → %s  visit_created=%s",
            appointment_id,
            aggregate["status"],
            new_state,
            visit_created,
        )

        # ── Post-commit: invalidate stats cache so /stats returns fresh counts ──
        try:
            from application.use_cases.appointment_commands import _invalidate_stats_cache
            _invalidate_stats_cache(aggregate.get("gate_in_id"))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Auto-create visit on accept
    # ------------------------------------------------------------------

    @staticmethod
    def _auto_create_visit(
        uow: IUnitOfWork,
        appointment_id: int,
        payload: dict[str, Any],
        aggregate: dict[str, Any],
    ) -> bool:
        """Auto-create a Visit within the same UoW transaction on accept."""
        gate_id = (
            payload.get("gate_id")
            or payload.get("gate_in_id")
            or aggregate.get("gate_in_id")
        )
        if not gate_id:
            logger.warning(
                "Cannot auto-create visit for appointment=%s: no gate_id",
                appointment_id,
            )
            return False

        try:
            gate_id_int = int(gate_id)
        except (TypeError, ValueError):
            logger.warning("Invalid gate_id=%s for visit auto-creation", gate_id)
            return False

        # Determine current shift type from UTC time of day
        now_utc = datetime.now(timezone.utc)
        hour = now_utc.hour
        if 6 <= hour < 14:
            shift_type = "MORNING"
        elif 14 <= hour < 22:
            shift_type = "AFTERNOON"
        else:
            shift_type = "NIGHT"

        # Store as naive UTC to match TIMESTAMP (without time zone) columns
        now = now_utc.replace(tzinfo=None)

        visit = uow.visits.create(
            appointment_id=appointment_id,
            shift_gate_id=gate_id_int,
            shift_type=shift_type,
            shift_date=now_utc.date(),
            entry_time=now,
        )
        if visit:
            logger.info(
                "Auto-created visit for appointment=%s at gate=%s shift=%s",
                appointment_id, gate_id_int, shift_type,
            )
            return True
        return False

    # ------------------------------------------------------------------
    # In-transaction notification outbox events (Guardrail 3)
    # ------------------------------------------------------------------

    @staticmethod
    def _append_accept_notification_events(
        uow: IUnitOfWork,
        appointment_id: int,
        payload: dict[str, Any],
        aggregate: dict[str, Any],
    ) -> None:
        """Append NotificationCreated outbox events inside the UoW transaction."""
        license_plate = payload.get("license_plate", "Unknown")
        gate_id = (
            payload.get("gate_id")
            or payload.get("gate_in_id")
            or aggregate.get("gate_in_id")
        )
        if not gate_id:
            return
        try:
            gate_id_int = int(gate_id)
        except (TypeError, ValueError):
            return

        notifications = [
            {
                "title": "Truck Accepted",
                "message": f"Truck {license_plate} has been accepted. Gate opening.",
                "type": "success",
                "target": "operator",
            },
            {
                "title": "Entry Approved",
                "message": (
                    "Your entry has been approved. Gate is opening. "
                    "Please proceed to the designated dock area."
                ),
                "type": "success",
                "target": "driver",
            },
        ]
        for notif in notifications:
            notif_event = EventEnvelope(
                event_id=new_event_id(),
                correlation_id=str(appointment_id),
                causation_id=None,
                aggregate_type="notification",
                aggregate_id=str(gate_id_int),
                event_type="NotificationCreated",
                event_version=1,
                occurred_at=datetime.now(timezone.utc),
                producer="data-module",
                partition_key=str(gate_id_int),
                payload={
                    "gate_id": gate_id_int,
                    "appointment_id": appointment_id,
                    "license_plate": license_plate,
                    "read": False,
                    **notif,
                },
            )
            uow.outbox.append(notif_event, topic="notifications", key=str(gate_id_int))

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
