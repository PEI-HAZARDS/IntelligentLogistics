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
        # Best-effort write-through to MongoDB read model
        self._write_through(alert_dict)
        return alert_dict

    @staticmethod
    def _write_through(alert_dict: dict) -> None:
        """Best-effort write-through to MongoDB alerts_read collection."""
        try:
            from infrastructure.persistence.mongo import alerts_read_collection

            doc = {**alert_dict}
            ts = doc.get("timestamp")
            if ts and not isinstance(ts, str):
                doc["timestamp"] = ts.isoformat()
            alerts_read_collection.update_one(
                {"id": doc["id"]},
                {"$set": doc},
                upsert=True,
            )
        except Exception:
            pass  # outbox worker will eventually catch up

    def get_appointment_visit_id(self, appointment_id: int) -> Optional[int]:
        visit = (
            self._s.query(Visit)
            .filter(Visit.appointment_id == appointment_id)
            .first()
        )
        return visit.appointment_id if visit else None
