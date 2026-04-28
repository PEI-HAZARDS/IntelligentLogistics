"""
SQLAlchemy repository for the pending_reviews table (PD-01 / Phase 4).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from infrastructure.persistence.sql_models import PendingReview


class SqlAlchemyPendingReviewRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        event_id: str,
        truck_id: str,
        gate_id: int,
        license_plate: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        row = PendingReview(
            event_id=uuid.UUID(event_id),
            truck_id=truck_id,
            gate_id=gate_id,
            license_plate=license_plate,
            payload=payload,
            status="PENDING",
        )
        self._session.add(row)
        self._session.flush()
        return self._to_dict(row)

    def get_for_update(self, event_id: str) -> Optional[dict[str, Any]]:
        row = (
            self._session.query(PendingReview)
            .filter(PendingReview.event_id == uuid.UUID(event_id))
            .with_for_update()
            .first()
        )
        return self._to_dict(row) if row else None

    def update_status(
        self,
        event_id: str,
        status: str,
        resolved_by: Optional[str] = None,
    ) -> bool:
        row = (
            self._session.query(PendingReview)
            .filter(PendingReview.event_id == uuid.UUID(event_id))
            .with_for_update()
            .first()
        )
        if row is None:
            return False
        row.status = status
        row.resolved_at = datetime.now(timezone.utc).replace(tzinfo=None)
        row.resolved_by = resolved_by
        self._session.flush()
        return True

    @staticmethod
    def _to_dict(row: PendingReview) -> dict[str, Any]:
        return {
            "event_id": str(row.event_id),
            "truck_id": row.truck_id,
            "gate_id": row.gate_id,
            "license_plate": row.license_plate,
            "payload": row.payload or {},
            "status": row.status,
            "created_at": row.created_at,
            "resolved_at": row.resolved_at,
            "resolved_by": row.resolved_by,
        }
