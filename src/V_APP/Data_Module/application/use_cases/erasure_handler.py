"""
RGPD Art. 17 — Right to Erasure handler for driver data.

Erasure is propagated across all stores in the polyglot persistence stack:
  1. PostgreSQL  — anonymise driver row (name, mobile_device_token); keep FK shell
  2. Redis       — revoke session + driver active-appointment cache
  3. MongoDB     — delete agent_detections and decision_events by license_plate
  4. MinIO       — delete all alert image objects referenced by driver's appointments
  5. Outbox      — emit DriverErased domain event (idempotency key = drivers_license)

The driver row is NOT hard-deleted because Appointment.driver_license FK would
violate referential integrity.  Anonymisation achieves the same privacy goal while
preserving audit integrity for historical appointment records.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from domain.events import EventEnvelope, new_event_id
from domain.interfaces import IUnitOfWork
from infrastructure.persistence.mongo import (
    agent_detections_collection,
    decision_events_collection,
    notifications_collection,
)
from infrastructure.persistence.redis import delete_session, invalidate_driver_active_appointment
from infrastructure.persistence.sql_models import Alert, Appointment
from utils.minio_client import delete_objects_by_urls

logger = logging.getLogger(__name__)

_ERASED_NAME = "ERASED"


def erase_driver(
    uow_factory,
    *,
    drivers_license: str,
    requested_by: str = "system",
) -> dict[str, Any]:
    """
    Execute full cross-store erasure for one driver.

    Returns a summary dict with per-store results for audit logging.
    Raises ``ValueError`` if the driver does not exist.
    """
    summary: dict[str, Any] = {
        "drivers_license": drivers_license,
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "requested_by": requested_by,
        "postgres": "pending",
        "redis": "pending",
        "mongodb": "pending",
        "minio": "pending",
        "outbox": "pending",
    }

    # ── 1. PostgreSQL: collect alert URLs then anonymise ─────────────────────
    with uow_factory() as uow:
        driver = uow.drivers.get_by_license(drivers_license)
        if not driver:
            raise ValueError(f"Driver '{drivers_license}' not found")

        # Collect image URLs from all alerts on driver's appointments
        image_urls = _collect_alert_image_urls(uow._session, drivers_license)

        # Anonymise the driver row (keeps FK shell for appointment history)
        uow.drivers.anonymise(drivers_license)

        # Emit DriverErased via Outbox (same PG transaction)
        envelope = EventEnvelope(
            event_id=new_event_id(),
            correlation_id=new_event_id(),
            causation_id=None,
            aggregate_type="driver",
            aggregate_id=drivers_license,
            event_type="DriverErased",
            event_version=1,
            occurred_at=datetime.now(timezone.utc),
            producer="data-module",
            partition_key=drivers_license,
            payload={
                "drivers_license": drivers_license,
                "erased_by": requested_by,
                "image_urls_count": len(image_urls),
            },
        )
        uow.outbox.append(envelope, topic="driver.lifecycle", key=drivers_license)
        uow.commit()

    summary["postgres"] = "anonymised"
    summary["outbox"] = "appended"
    logger.info("[RGPD] Driver %s anonymised in PostgreSQL", drivers_license)

    # ── 2. Redis: revoke session + active-appointment cache ──────────────────
    try:
        delete_session("driver", drivers_license)
        invalidate_driver_active_appointment(drivers_license)
        summary["redis"] = "evicted"
        logger.info("[RGPD] Redis entries evicted for driver %s", drivers_license)
    except Exception as exc:
        summary["redis"] = f"error: {exc}"
        logger.exception("[RGPD] Redis eviction failed for driver %s", drivers_license)

    # ── 3. MongoDB: delete detection and decision records ───────────────────
    try:
        det_result = agent_detections_collection.delete_many(
            {"detection_data.license_plate": {"$regex": drivers_license, "$options": "i"}}
        )
        dec_result = decision_events_collection.delete_many(
            {"agent_detections.license_plate_detection.license_plate": drivers_license}
        )
        notif_result = notifications_collection.delete_many(
            {"driver_license": drivers_license}
        )
        summary["mongodb"] = {
            "agent_detections_deleted": det_result.deleted_count,
            "decision_events_deleted": dec_result.deleted_count,
            "notifications_deleted": notif_result.deleted_count,
        }
        logger.info("[RGPD] MongoDB records deleted for driver %s: %s", drivers_license, summary["mongodb"])
    except Exception as exc:
        summary["mongodb"] = f"error: {exc}"
        logger.exception("[RGPD] MongoDB deletion failed for driver %s", drivers_license)

    # ── 4. MinIO: delete alert image objects ─────────────────────────────────
    if image_urls:
        try:
            results = delete_objects_by_urls(image_urls)
            failed = [url for url, ok in results.items() if not ok]
            summary["minio"] = {
                "total": len(image_urls),
                "deleted": len(image_urls) - len(failed),
                "failed": len(failed),
            }
            if failed:
                logger.warning("[RGPD] MinIO: %d objects failed to delete for driver %s", len(failed), drivers_license)
            else:
                logger.info("[RGPD] MinIO: %d objects deleted for driver %s", len(image_urls), drivers_license)
        except Exception as exc:
            summary["minio"] = f"error: {exc}"
            logger.exception("[RGPD] MinIO deletion failed for driver %s", drivers_license)
    else:
        summary["minio"] = "no_images"

    return summary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_alert_image_urls(session, drivers_license: str) -> list[str]:
    """Return all non-null image_url values from alerts on driver's appointments."""
    rows = (
        session.query(Alert.image_url)
        .join(Appointment, Alert.appointment_id == Appointment.id)
        .filter(
            Appointment.driver_license == drivers_license,
            Alert.image_url.isnot(None),
        )
        .all()
    )
    return [row.image_url for row in rows]
