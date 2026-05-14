"""SQLAlchemy implementation of IAlertRepository."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from domain.interfaces import IAlertRepository
from infrastructure.persistence.sql_models import Alert, Visit


class SqlAlchemyAlertRepository(IAlertRepository):
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(
        self,
        *,
        visit_id: Optional[int],
        alert_type: str,
        description: str,
        image_url: Optional[str] = None,
        appointment_id: Optional[int] = None,
    ) -> dict[str, Any]:
        alert = Alert(
            visit_id=visit_id,
            appointment_id=appointment_id,
            type=alert_type,
            description=description,
            image_url=image_url,
            timestamp=datetime.now(timezone.utc),
        )
        self._s.add(alert)
        self._s.flush()
        alert_dict = {
            "id": alert.id,
            "visit_id": alert.visit_id,
            "appointment_id": alert.appointment_id,
            "type": alert.type,
            "description": alert.description,
            "image_url": alert.image_url,
            "timestamp": alert.timestamp,
        }
        return alert_dict

    def get_appointment_visit_id(self, appointment_id: int) -> Optional[int]:
        visit = (
            self._s.query(Visit)
            .filter(Visit.appointment_id == appointment_id)
            .first()
        )
        return visit.appointment_id if visit else None
