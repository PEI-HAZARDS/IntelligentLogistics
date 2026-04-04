"""
SQLAlchemy implementation of the Appointment repository.

Provides lookup by arrival_id and optimistic-concurrency status updates.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from domain.interfaces import IAppointmentRepository
from infrastructure.persistence.sql_models import Appointment


class SqlAlchemyAppointmentRepository(IAppointmentRepository):
    """Concrete appointment repo backed by PostgreSQL via SQLAlchemy."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # IAppointmentRepository
    # ------------------------------------------------------------------

    def get_by_arrival_id(self, arrival_id: str) -> Optional[dict[str, Any]]:
        row = (
            self._session.query(Appointment)
            .filter(Appointment.arrival_id == arrival_id)
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
            "driver_license": row.driver_license,
            "truck_license_plate": row.truck_license_plate,
        }

    def update_status(self, appointment_id: int, status: str, *, version: int) -> int:
        """Optimistic update — only succeeds if the row's current version matches.

        On success the version is bumped by 1.
        Returns number of affected rows (0 = optimistic concurrency conflict).
        """
        affected = (
            self._session.query(Appointment)
            .filter(
                Appointment.id == appointment_id,
                Appointment.version == version,
            )
            .update(
                {"status": status, "version": version + 1},
                synchronize_session="fetch",
            )
        )
        self._session.flush()
        return affected  # type: ignore[return-value]
