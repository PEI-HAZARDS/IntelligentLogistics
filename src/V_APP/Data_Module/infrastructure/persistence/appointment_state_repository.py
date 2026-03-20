"""
SQLAlchemy implementation of the Appointment State repository.

Provides aggregate locking (SELECT … FOR UPDATE) and state transition
persistence for the Appointment write model.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from domain.interfaces import IAppointmentStateRepository
from infrastructure.persistence.sql_models import Appointment


class SqlAlchemyAppointmentStateRepository(IAppointmentStateRepository):
    """Appointment state transition repo backed by PostgreSQL via SQLAlchemy."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # IAppointmentStateRepository
    # ------------------------------------------------------------------

    def get_for_update(self, appointment_id: int) -> Optional[dict[str, Any]]:
        """Lock the appointment row (Guardrail 2 — single PG transaction)."""
        row = (
            self._session.query(Appointment)
            .filter(Appointment.id == appointment_id)
            .with_for_update()
            .one_or_none()
        )
        if row is None:
            return None
        return {
            "id": row.id,
            "arrival_id": row.arrival_id,
            "status": row.status,
            "version": row.version,
            "terminal_id": row.terminal_id,
            "gate_in_id": row.gate_in_id,
            "gate_out_id": row.gate_out_id,
        }

    def save_state_transition(
        self, appointment_id: int, new_state: str, metadata: dict[str, Any]
    ) -> None:
        row = (
            self._session.query(Appointment)
            .filter(Appointment.id == appointment_id)
            .one()
        )
        row.status = new_state
        row.version = (row.version or 1) + 1
        if "gate_in_id" in metadata:
            row.gate_in_id = metadata["gate_in_id"]
        if "gate_out_id" in metadata:
            row.gate_out_id = metadata["gate_out_id"]
        if "notes" in metadata:
            row.notes = metadata["notes"]
        self._session.flush()
