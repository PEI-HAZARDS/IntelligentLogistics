"""
Command handlers for alert mutations.
Writes to PostgreSQL via UoW + Outbox (Guardrails 2, 3, 6).
Write-through to MongoDB alerts_read after commit.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from domain.events import EventEnvelope
from domain.interfaces import IUnitOfWork

logger = logging.getLogger(__name__)

# ── reference data (moved from alert_service) ────────────────────

ADR_CODES = {
    "1203": {"description": "Gasoline", "class": "3", "hazard": "Flammable liquid"},
    "1202": {"description": "Diesel", "class": "3", "hazard": "Flammable liquid"},
    "1073": {"description": "Liquid oxygen", "class": "2.2", "hazard": "Non-flammable gas"},
    "1978": {"description": "Propane", "class": "2.1", "hazard": "Flammable gas"},
    "1789": {"description": "Hydrochloric acid", "class": "8", "hazard": "Corrosive"},
    "2031": {"description": "Nitric acid", "class": "8", "hazard": "Corrosive/Oxidizing"},
    "1830": {"description": "Sulfuric acid", "class": "8", "hazard": "Corrosive"},
    "1005": {"description": "Anhydrous ammonia", "class": "2.3", "hazard": "Toxic gas"},
    "1017": {"description": "Chlorine", "class": "2.3", "hazard": "Toxic gas"},
}

KEMLER_CODES = {
    "33": "Highly flammable liquid",
    "30": "Flammable liquid",
    "23": "Flammable gas",
    "22": "Refrigerated gas",
    "20": "Asphyxiant gas",
    "X80": "Corrosive - reacts with water",
    "80": "Corrosive",
    "60": "Toxic",
    "X66": "Very toxic - reacts with water",
}


def _write_through_alert(alert_dict: dict[str, Any]) -> None:
    """Best-effort write-through to MongoDB (outside SQL transaction)."""
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
    except Exception as exc:
        logger.warning("alerts_read write-through failed (outbox will catch up): %s", exc)


def _append_outbox(uow: IUnitOfWork, alert_dict: dict[str, Any], event_type: str) -> None:
    envelope = EventEnvelope(
        event_id=str(uuid4()),
        correlation_id=str(uuid4()),
        causation_id=None,
        aggregate_type="alert",
        aggregate_id=str(alert_dict["id"]),
        event_type=event_type,
        event_version=1,
        occurred_at=datetime.now(timezone.utc),
        producer="data-module",
        partition_key=str(alert_dict.get("visit_id") or alert_dict["id"]),
        payload=alert_dict,
    )
    uow.outbox.append(envelope, topic="alert.created", key=envelope.partition_key)


# ── handlers ─────────────────────────────────────────────────────


def create_alert(
    uow_factory,
    *,
    visit_id: Optional[int],
    alert_type: str,
    description: str,
    image_url: Optional[str] = None,
) -> dict[str, Any]:
    with uow_factory() as uow:
        alert = uow.alerts.add(
            visit_id=visit_id,
            alert_type=alert_type,
            description=description,
            image_url=image_url,
        )
        _append_outbox(uow, alert, "AlertCreated")
        uow.commit()

    _write_through_alert(alert)
    return alert


def create_hazmat_alert(
    uow_factory,
    *,
    appointment_id: int,
    un_code: Optional[str] = None,
    kemler_code: Optional[str] = None,
    detected_hazmat: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Creates a hazmat/ADR alert linked to an appointment."""
    description_parts = ["Hazardous cargo detected"]
    if un_code and un_code in ADR_CODES:
        info = ADR_CODES[un_code]
        description_parts.append(f"UN {un_code} - {info['description']}")
        description_parts.append(f"Class: {info['class']}")
        description_parts.append(f"Hazard: {info['hazard']}")
    if kemler_code and kemler_code in KEMLER_CODES:
        description_parts.append(f"Kemler {kemler_code}: {KEMLER_CODES[kemler_code]}")
    if detected_hazmat:
        description_parts.append(f"Detection: {detected_hazmat}")

    alert_type = "safety"

    with uow_factory() as uow:
        visit_id = uow.alerts.get_appointment_visit_id(appointment_id)
        alert = uow.alerts.add(
            visit_id=visit_id,
            appointment_id=appointment_id,
            alert_type=alert_type,
            description=" | ".join(description_parts),
        )
        _append_outbox(uow, alert, "HazmatAlertCreated")
        uow.commit()

    _write_through_alert(alert)
    return alert


def create_alerts_for_appointment(
    uow_factory,
    *,
    appointment_id: int,
    alerts_payload: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Bulk-create alerts for an appointment (used by arrival_service)."""
    if not alerts_payload:
        return []

    created: list[dict[str, Any]] = []
    with uow_factory() as uow:
        visit_id = uow.alerts.get_appointment_visit_id(appointment_id)
        for data in alerts_payload:
            alert = uow.alerts.add(
                visit_id=visit_id,
                appointment_id=appointment_id,
                alert_type=data.get("type", "generic"),
                description=data.get("description", "Alert without description"),
                image_url=data.get("image_url"),
            )
            created.append(alert)
        uow.commit()

    for a in created:
        _write_through_alert(a)
    return created
