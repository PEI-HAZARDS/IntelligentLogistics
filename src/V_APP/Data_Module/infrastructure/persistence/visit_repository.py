"""
SQLAlchemy implementation of the Visit repository.

Provides visit creation and state updates within UoW transactions.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from domain.interfaces import IVisitRepository
from infrastructure.persistence.sql_models import Appointment, Shift, Visit

logger = logging.getLogger(__name__)


class SqlAlchemyVisitRepository(IVisitRepository):
    """Visit repo backed by PostgreSQL via SQLAlchemy."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        appointment_id: int,
        shift_gate_id: int,
        shift_type: str,
        shift_date: Any,
        entry_time: Any = None,
    ) -> Optional[dict[str, Any]]:
        appointment = (
            self._session.query(Appointment)
            .filter(Appointment.id == appointment_id)
            .one_or_none()
        )
        if appointment is None:
            return None

        existing = (
            self._session.query(Visit)
            .filter(Visit.appointment_id == appointment_id)
            .one_or_none()
        )
        if existing is not None:
            return self._to_dict(existing)

        # Ensure the required Shift row exists (auto-create if missing).
        # Visit has a DB-level FK constraint on (shift_gate_id, shift_type, shift_date)
        # referencing shift(gate_id, shift_type, date).  If no Shift was created for
        # the current day/gate (e.g. during demo or off-hours), the flush() would
        # raise IntegrityError and poison the entire UoW transaction.
        self._ensure_shift_exists(shift_gate_id, shift_type, shift_date)

        visit = Visit(
            appointment_id=appointment_id,
            shift_gate_id=shift_gate_id,
            shift_type=shift_type,
            shift_date=shift_date,
            entry_time=entry_time or datetime.now(),
            state="unloading",
        )
        self._session.add(visit)
        self._session.flush()
        return self._to_dict(visit)

    def _ensure_shift_exists(
        self, gate_id: int, shift_type: Any, shift_date: Any
    ) -> None:
        """Auto-create a Shift row if one does not exist for this gate/type/date.

        This prevents FK violation when auto-creating visits during acceptance
        of trucks at gates that have no operator-assigned shift yet.
        The created shift has no assigned operator or manager (nullable cols).
        """
        existing = (
            self._session.query(Shift)
            .filter(
                Shift.gate_id == gate_id,
                Shift.shift_type == shift_type,
                Shift.date == shift_date,
            )
            .one_or_none()
        )
        if existing is None:
            new_shift = Shift(
                gate_id=gate_id,
                shift_type=shift_type,
                date=shift_date,
            )
            self._session.add(new_shift)
            self._session.flush()
            logger.info(
                "Auto-created missing Shift gate=%s type=%s date=%s",
                gate_id, shift_type, shift_date,
            )

    def update_state(
        self,
        appointment_id: int,
        new_state: str,
        out_time: Any = None,
    ) -> Optional[dict[str, Any]]:
        visit = (
            self._session.query(Visit)
            .filter(Visit.appointment_id == appointment_id)
            .one_or_none()
        )
        if visit is None:
            return None
        visit.state = new_state
        if out_time:
            visit.out_time = out_time
        elif new_state == "completed":
            visit.out_time = datetime.now()
        self._session.flush()
        return self._to_dict(visit)

    def get_by_appointment(self, appointment_id: int) -> Optional[dict[str, Any]]:
        visit = (
            self._session.query(Visit)
            .filter(Visit.appointment_id == appointment_id)
            .one_or_none()
        )
        if visit is None:
            return None
        return self._to_dict(visit)

    @staticmethod
    def _to_dict(visit: Visit) -> dict[str, Any]:
        return {
            "appointment_id": visit.appointment_id,
            "shift_gate_id": visit.shift_gate_id,
            "shift_type": visit.shift_type.name if hasattr(visit.shift_type, "name") else str(visit.shift_type),
            "shift_date": visit.shift_date,
            "entry_time": visit.entry_time,
            "out_time": visit.out_time,
            "state": visit.state,
        }
