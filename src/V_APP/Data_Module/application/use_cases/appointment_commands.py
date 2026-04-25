"""
Command handlers for appointment write operations.

All demo-critical writes go through UoW + Outbox so that:
  - PG state and outbox event are in the same transaction (Guardrail 2, 3).
  - No direct session factory usage in business logic (Guardrail 6).
  - Side-effects propagate via outbox worker (Guardrail 3).

Each function takes a ``uow_factory`` callable that returns an IUnitOfWork
context manager (same pattern as ContainerMovedHandler).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from domain.events import EventEnvelope, new_event_id
from domain.interfaces import IUnitOfWork
from infrastructure.persistence.redis import redis_client

logger = logging.getLogger(__name__)


def _invalidate_stats_cache(gate_in_id: Any = None) -> None:
    """Delete cached stats keys so the next /stats call computes fresh counts."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    keys_to_delete = [f"stats:gate:all:{today}"]
    if gate_in_id:
        keys_to_delete.append(f"stats:gate:{gate_in_id}:{today}")
    for key in keys_to_delete:
        try:
            redis_client.delete(key)
        except Exception:
            pass


def _outbox_event(
    aggregate_id: int,
    event_type: str,
    payload: dict[str, Any],
    *,
    correlation_id: str | None = None,
) -> EventEnvelope:
    """Build an outbox EventEnvelope for appointment commands."""
    return EventEnvelope(
        event_id=new_event_id(),
        correlation_id=correlation_id or new_event_id(),
        causation_id=None,
        aggregate_type="appointment",
        aggregate_id=str(aggregate_id),
        event_type=event_type,
        event_version=1,
        occurred_at=datetime.now(timezone.utc),
        producer="data-module",
        partition_key=str(aggregate_id),
        payload=payload,
    )


# ------------------------------------------------------------------
# Command: Update appointment status
# ------------------------------------------------------------------

def cmd_update_status(
    uow_factory: Callable[..., IUnitOfWork],
    appointment_id: int,
    new_status: str,
    notes: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Update appointment status via UoW + Outbox.

    Returns aggregate dict on success, None if appointment not found.
    """
    with uow_factory() as uow:
        aggregate = uow.appointment_state.get_for_update(appointment_id)
        if aggregate is None:
            return None

        old_status = aggregate["status"]
        metadata: dict[str, Any] = {}
        if notes:
            metadata["notes"] = notes

        uow.appointment_state.save_state_transition(
            appointment_id, new_status, metadata
        )

        uow.outbox.append(
            _outbox_event(
                appointment_id,
                "AppointmentStatusUpdated",
                {
                    "appointment_id": appointment_id,
                    "previous_status": old_status,
                    "new_status": new_status,
                    "notes": notes,
                },
            ),
            topic="appointment.state.changed",
            key=str(appointment_id),
        )

        uow.commit()

    logger.info(
        "cmd_update_status: appointment=%s  %s → %s",
        appointment_id, old_status, new_status,
    )
    _invalidate_stats_cache(aggregate.get("gate_in_id"))
    return {
        "id": appointment_id,
        "status": new_status,
        "previous_status": old_status,
    }


# ------------------------------------------------------------------
# Command: Process decision (update appointment + optional visit)
# ------------------------------------------------------------------

def cmd_process_decision(
    uow_factory: Callable[..., IUnitOfWork],
    appointment_id: int,
    decision_payload: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """Process a decision engine result: update appointment + create alerts.

    Returns aggregate dict on success, None if appointment not found.
    """
    with uow_factory() as uow:
        aggregate = uow.appointment_state.get_for_update(appointment_id)
        if aggregate is None:
            return None

        old_status = aggregate["status"]
        new_status = decision_payload.get("status", old_status)
        metadata: dict[str, Any] = {}
        if "notes" in decision_payload:
            metadata["notes"] = decision_payload["notes"]

        uow.appointment_state.save_state_transition(
            appointment_id, new_status, metadata
        )

        # Create alerts if present
        alerts_payload = decision_payload.get("alerts", [])
        alerts_created = 0
        if alerts_payload:
            visit_id = uow.alerts.get_appointment_visit_id(appointment_id)
            for alert_data in alerts_payload:
                uow.alerts.add(
                    visit_id=visit_id,
                    alert_type=alert_data.get("type", "generic"),
                    description=alert_data.get("description", ""),
                    image_url=alert_data.get("image_url"),
                    appointment_id=appointment_id,
                )
                alerts_created += 1

        uow.outbox.append(
            _outbox_event(
                appointment_id,
                "DecisionProcessed",
                {
                    "appointment_id": appointment_id,
                    "previous_status": old_status,
                    "new_status": new_status,
                    "decision": decision_payload.get("decision"),
                    "alerts_created": alerts_created,
                },
            ),
            topic="appointment.state.changed",
            key=str(appointment_id),
        )

        uow.commit()

    logger.info(
        "cmd_process_decision: appointment=%s  %s → %s  alerts=%d",
        appointment_id, old_status, new_status, alerts_created,
    )
    _invalidate_stats_cache(aggregate.get("gate_in_id"))
    return {
        "id": appointment_id,
        "status": new_status,
        "previous_status": old_status,
        "alerts_created": alerts_created,
    }


# ------------------------------------------------------------------
# Command: Flag highway infraction
# ------------------------------------------------------------------

def cmd_flag_highway_infraction(
    uow_factory: Callable[..., IUnitOfWork],
    appointment_id: int,
) -> Optional[dict[str, Any]]:
    """Flag an appointment as highway infraction via UoW + Outbox.

    Returns aggregate dict on success, None if not found.
    """
    with uow_factory() as uow:
        aggregate = uow.appointment_state.get_for_update(appointment_id)
        if aggregate is None:
            return None

        # save_state_transition keeps same status but we need to set
        # highway_infraction — extend metadata for this flag
        uow.appointment_state.save_state_transition(
            appointment_id,
            aggregate["status"],
            {"highway_infraction": True},
        )

        uow.outbox.append(
            _outbox_event(
                appointment_id,
                "AppointmentHighwayInfractionFlagged",
                {"appointment_id": appointment_id},
            ),
            topic="appointment.state.changed",
            key=str(appointment_id),
        )

        uow.commit()

    logger.info("cmd_flag_highway_infraction: appointment=%s", appointment_id)
    return {"id": appointment_id, "highway_infraction": True}


# ------------------------------------------------------------------
# Command: Create visit
# ------------------------------------------------------------------

def cmd_create_visit(
    uow_factory: Callable[..., IUnitOfWork],
    appointment_id: int,
    shift_gate_id: int,
    shift_type: str,
    shift_date: Any,
    entry_time: Any = None,
) -> Optional[dict[str, Any]]:
    """Create a visit for an appointment via UoW + Outbox.

    Returns visit dict on success, None if appointment not found.
    """
    with uow_factory() as uow:
        visit = uow.visits.create(
            appointment_id=appointment_id,
            shift_gate_id=shift_gate_id,
            shift_type=shift_type,
            shift_date=shift_date,
            entry_time=entry_time,
        )
        if visit is None:
            return None

        uow.outbox.append(
            _outbox_event(
                appointment_id,
                "VisitCreated",
                {
                    "appointment_id": appointment_id,
                    "shift_gate_id": shift_gate_id,
                    "state": visit["state"],
                },
            ),
            topic="appointment.visit.changed",
            key=str(appointment_id),
        )

        uow.commit()

    logger.info("cmd_create_visit: appointment=%s", appointment_id)
    return visit


# ------------------------------------------------------------------
# Command: Update visit state
# ------------------------------------------------------------------

def cmd_update_visit_state(
    uow_factory: Callable[..., IUnitOfWork],
    appointment_id: int,
    new_state: str,
    out_time: Any = None,
) -> Optional[dict[str, Any]]:
    """Update visit state via UoW + Outbox.

    Returns visit dict on success, None if not found.
    """
    with uow_factory() as uow:
        visit = uow.visits.update_state(
            appointment_id=appointment_id,
            new_state=new_state,
            out_time=out_time,
        )
        if visit is None:
            return None

        uow.outbox.append(
            _outbox_event(
                appointment_id,
                "VisitStateUpdated",
                {
                    "appointment_id": appointment_id,
                    "new_state": new_state,
                },
            ),
            topic="appointment.visit.changed",
            key=str(appointment_id),
        )

        uow.commit()

    logger.info(
        "cmd_update_visit_state: appointment=%s → %s",
        appointment_id, new_state,
    )
    return visit
