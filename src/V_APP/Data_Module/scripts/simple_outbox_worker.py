#!/usr/bin/env python3
"""
Simple Outbox Worker — Eventual Consistency via Transactional Outbox.

Polls the ``outbox_events`` table for PENDING rows and projects each event
into the read models (MongoDB for audit trail, Redis for hot cache), then
marks the row as PUBLISHED.

Failed projections are retried with exponential backoff + jitter (Guardrail 8).
After ``MAX_RETRIES`` consecutive failures an event is moved to DEAD_LETTER.

┌────────────┐  commit   ┌──────────┐  poll   ┌──────────────────┐
│  Command   │──────────▶│ outbox_  │◀───────│  THIS WORKER     │
│  Handler   │           │ events   │         │                  │
│ (Postgres) │           │ (PG)     │────────▶│  ┌── MongoDB ──┐ │
└────────────┘           └──────────┘  read   │  │  (audit)    │ │
                                       batch  │  └─────────────┘ │
                                              │  ┌── Redis ────┐ │
                                              │  │  (hot cache) │ │
                                              │  └─────────────┘ │
                                              └──────────────────┘

Usage:
    python scripts/simple_outbox_worker.py

Guardrails enforced:
  3 — Outbox is the ONLY source of side-effects; no direct publish.
  7 — Projections are idempotent (upsert in Mongo, overwrite in Redis).
  8 — DLQ policy: exponential backoff for transient errors, DEAD_LETTER
      after MAX_RETRIES with full error metadata.
"""

import json
import sys
import os
import signal
import time
import random
import logging
from datetime import datetime, timezone, timedelta
from prometheus_client import (
    Counter, Gauge, Histogram, start_http_server,
)

# ── Path setup (standalone script) ──────────────────────────────
_script_dir = os.path.dirname(os.path.abspath(__file__))
_data_module_dir = os.path.join(_script_dir, "..")
sys.path.insert(0, _data_module_dir)

# ── Imports from Data Module ────────────────────────────────────
from infrastructure.persistence.postgres import SessionLocal
from infrastructure.persistence.mongo import (
    decision_events_collection,
    notifications_collection,
    agent_detections_collection,
)
from infrastructure.persistence.redis import (
    redis_client,
    cache_appointment,
    invalidate_appointment_cache,
    increment_counter,
    pending_review_key,
    alert_detail_key,
    active_alerts_list_key,
    cache_driver_active_appointment,
    invalidate_driver_active_appointment,
    TTL_ALERT_DETAIL,
)
from infrastructure.persistence.inbox_outbox_models import OutboxEvent
from infrastructure.persistence.sql_models import Appointment as AppointmentORM
from application.schemas import Appointment as AppointmentSchema
from config import settings
from sqlalchemy import or_, and_

# ── Best-effort DLQ producer ─────────────────────────────────────
try:
    from confluent_kafka import Producer as _KafkaProducer
    _dlq_producer = _KafkaProducer({"bootstrap.servers": settings.kafka_bootstrap})
    _DLQ_TOPIC = "data.dlq"
except Exception:
    _dlq_producer = None
    _DLQ_TOPIC = "data.dlq"

# ── Configuration ───────────────────────────────────────────────
BATCH_SIZE = 50
POLL_INTERVAL_SECONDS = 2
MAX_RETRIES = 5
BACKOFF_BASE_SECONDS = 2       # 2, 4, 8, 16, 32 seconds
BACKOFF_MAX_SECONDS = 60       # cap backoff at 1 minute
JITTER_MAX_SECONDS = 2         # random jitter up to 2 seconds
METRICS_PORT = int(os.getenv("OUTBOX_METRICS_PORT", "9100"))

# ── Prometheus metrics ───────────────────────────────────────────
_outbox_projected_total = Counter(
    "outbox_projected_total",
    "Total outbox events successfully projected to read models",
    ["event_type"],
)
_outbox_dead_letter_total = Counter(
    "outbox_dead_letter_total",
    "Total outbox events moved to DEAD_LETTER",
    ["event_type"],
)
_outbox_retries_total = Counter(
    "outbox_retries_total",
    "Total outbox projection retry increments",
    ["event_type"],
)
_outbox_pending_rows = Gauge(
    "outbox_pending_rows",
    "Current PENDING + eligible FAILED rows in outbox_events",
)
_outbox_projection_lag_seconds = Gauge(
    "outbox_projection_lag_seconds",
    "Age in seconds of the oldest PENDING outbox row",
)
_outbox_batch_seconds = Histogram(
    "outbox_batch_seconds",
    "Wall-clock time to process one poll batch",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)
_outbox_projection_seconds = Histogram(
    "outbox_projection_seconds",
    "Time to project a single outbox event (Mongo + Redis)",
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)

# ── Logging ─────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("outbox_worker")

# ── Graceful shutdown ───────────────────────────────────────────
_shutdown_requested = False


def _handle_signal(signum, frame):
    global _shutdown_requested
    sig_name = signal.Signals(signum).name
    logger.info("Received %s — finishing current batch and shutting down", sig_name)
    _shutdown_requested = True


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


# ═══════════════════════════════════════════════════════════════
# Backoff calculation
# ═══════════════════════════════════════════════════════════════


def compute_next_retry_at(retry_count: int) -> datetime:
    """
    Exponential backoff with jitter.

    delay = min(BACKOFF_BASE ** retry_count, BACKOFF_MAX) + random(0, JITTER_MAX)
    """
    delay = min(BACKOFF_BASE_SECONDS ** retry_count, BACKOFF_MAX_SECONDS)
    jitter = random.uniform(0, JITTER_MAX_SECONDS)
    return datetime.now(timezone.utc) + timedelta(seconds=delay + jitter)


# ═══════════════════════════════════════════════════════════════
# Projection functions
# ═══════════════════════════════════════════════════════════════


def project_to_mongo(event_row: OutboxEvent) -> None:
    """
    Project the event to the appropriate MongoDB collection.

    - DetectionEventReceived → agent_detections_collection
    - All other types → decision_events_collection (audit trail)

    Uses ``event_id`` as the idempotency key (Guardrail 7).
    """
    payload = event_row.payload or {}
    doc = {
        "event_id": event_row.event_id,
        "event_type": event_row.event_type,
        "event_version": event_row.event_version,
        "aggregate_type": event_row.aggregate_type,
        "aggregate_id": event_row.aggregate_id,
        "partition_key": event_row.partition_key,
        "topic": event_row.topic,
        "payload": payload,
        "created_at": event_row.created_at or datetime.now(timezone.utc),
        "projected_at": datetime.now(timezone.utc),
    }

    if event_row.event_type == "DetectionEventReceived":
        detection_doc = {
            "detection_id": event_row.event_id,
            "event_id": event_row.event_id,
            "agent_type": payload.get("agent", "Unknown"),
            "gate_id": payload.get("gate_id"),
            "timestamp": datetime.now(timezone.utc),
            "detection_data": {
                "license_plate": payload.get("license_plate"),
                "confidence": payload.get("confidence"),
                "type": payload.get("type"),
                "raw_data": payload.get("raw_data"),
            },
            "projected_at": datetime.now(timezone.utc),
        }
        agent_detections_collection.update_one(
            {"event_id": event_row.event_id},
            {"$setOnInsert": detection_doc},
            upsert=True,
        )
    else:
        decision_events_collection.update_one(
            {"event_id": event_row.event_id},
            {"$set": doc},
            upsert=True,
        )

    logger.debug(
        "MongoDB projection OK: event_id=%s  type=%s",
        event_row.event_id,
        event_row.event_type,
    )


_APPOINTMENT_EVENT_TYPES = {
    "AppointmentStateChanged",
    "AppointmentStatusUpdated",
    "AppointmentHighwayInfractionFlagged",
    "DecisionProcessed",
    "VisitCreated",
    "VisitStateUpdated",
}


def _project_appointment_event(payload: dict, event_type: str, session) -> None:
    if event_type not in _APPOINTMENT_EVENT_TYPES:
        return
    appointment_id = payload.get("appointment_id")
    if appointment_id is None:
        return
    invalidate_appointment_cache(int(appointment_id))
    appt = session.query(AppointmentORM).filter(AppointmentORM.id == int(appointment_id)).first()
    if appt:
        snapshot = AppointmentSchema.model_validate(appt).model_dump(mode="json")
        cache_appointment(int(appointment_id), snapshot)
        driver_license = getattr(appt, "driver_license", None)
        if driver_license:
            if appt.status == "in_process":  # covers in_process + unloading sub-state
                cache_driver_active_appointment(driver_license, snapshot)
            else:
                invalidate_driver_active_appointment(driver_license)
    else:
        logger.warning("Appointment %s not found during projection", appointment_id)
    gate_id = payload.get("gate_in_id") or payload.get("gate_out_id")
    if gate_id is not None:
        new_state = payload.get("new_state", "unknown")
        increment_counter(int(gate_id), f"transitions:{new_state}")


def _project_alert_event(event_row: OutboxEvent, payload: dict) -> None:
    if event_row.event_type not in {"AlertCreated", "HazmatAlertCreated"}:
        return
    appointment_id = payload.get("appointment_id")
    if appointment_id is not None:
        invalidate_appointment_cache(int(appointment_id))
    alert_id = payload.get("id")
    if alert_id is not None:
        try:
            redis_client.setex(
                alert_detail_key(int(alert_id)),
                TTL_ALERT_DETAIL,
                json.dumps(payload, default=str),
            )
        except Exception as _ae:
            logger.exception("Failed to cache alert %s", alert_id)
    redis_client.delete(active_alerts_list_key())


def project_to_redis(event_row: OutboxEvent, session) -> None:
    """Update Redis hot caches so dashboards reflect the latest state."""
    payload = event_row.payload or {}
    event_type = event_row.event_type

    _project_appointment_event(payload, event_type, session)
    _project_alert_event(event_row, payload)

    if event_type == "PendingReviewCreated":
        pr_event_id = payload.get("event_id")
        if pr_event_id:
            ttl = int(payload.get("ttl", 1800))
            redis_client.setex(pending_review_key(pr_event_id), ttl, json.dumps(payload, default=str))
            logger.debug("Cached pending review: event_id=%s TTL=%s", pr_event_id, ttl)

    if event_type == "PendingReviewResolved":
        pr_event_id = payload.get("event_id")
        if pr_event_id:
            redis_client.delete(pending_review_key(pr_event_id))
            logger.debug("Evicted resolved pending review: event_id=%s", pr_event_id)

    if event_type == "NotificationCreated":
        doc = dict(payload)
        doc["event_id"] = event_row.event_id
        doc.setdefault("read", False)
        doc.setdefault("created_at", datetime.now(timezone.utc))
        notifications_collection.update_one(
            {"event_id": event_row.event_id},
            {"$setOnInsert": doc},
            upsert=True,
        )
        logger.debug("Notification projected to Mongo: event_id=%s gate_id=%s", event_row.event_id, payload.get("gate_id"))

    logger.debug(
        "Redis projection OK: event_id=%s  type=%s",
        event_row.event_id,
        event_type,
    )


# ═══════════════════════════════════════════════════════════════
# DLQ forwarding
# ═══════════════════════════════════════════════════════════════


def _forward_to_dlq(row: OutboxEvent) -> None:
    """Publish a DEAD_LETTER outbox row to the Kafka DLQ topic (best-effort)."""
    if _dlq_producer is None:
        logger.warning("DLQ producer unavailable; skipping Kafka publish for outbox_id=%s", row.id)
        return
    try:
        msg = json.dumps({
            "outbox_id": row.id,
            "event_id": row.event_id,
            "event_type": row.event_type,
            "aggregate_type": row.aggregate_type,
            "aggregate_id": row.aggregate_id,
            "retry_count": row.retry_count,
            "last_error": row.last_error,
            "payload": row.payload,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }, default=str)
        _dlq_producer.produce(
            _DLQ_TOPIC,
            key=str(row.event_id),
            value=msg.encode(),
        )
        _dlq_producer.poll(0)
        logger.info("Forwarded DEAD_LETTER outbox_id=%s to %s", row.id, _DLQ_TOPIC)
    except Exception as exc:
        logger.exception("Failed to forward DEAD_LETTER outbox_id=%s to DLQ", row.id)


# ═══════════════════════════════════════════════════════════════
# Failure classification
# ═══════════════════════════════════════════════════════════════


# Permanent errors that should not be retried
_PERMANENT_ERROR_TYPES = (
    KeyError,
    ValueError,
    TypeError,
)


def _is_permanent_error(exc: Exception) -> bool:
    """Return True if the error is a contract/domain violation (non-retryable)."""
    return isinstance(exc, _PERMANENT_ERROR_TYPES)


# ═══════════════════════════════════════════════════════════════
# Main loop
# ═══════════════════════════════════════════════════════════════


def fetch_projectable_rows(session, batch_size: int):
    """
    Fetch rows eligible for projection:
    - PENDING (new events)
    - FAILED with retry_count < MAX_RETRIES and next_retry_at <= now
    """
    now = datetime.now(timezone.utc)

    return (
        session.query(OutboxEvent)
        .filter(
            or_(
                OutboxEvent.status == "PENDING",
                and_(
                    OutboxEvent.status == "FAILED",
                    OutboxEvent.retry_count < MAX_RETRIES,
                    or_(
                        OutboxEvent.next_retry_at.is_(None),
                        OutboxEvent.next_retry_at <= now,
                    ),
                ),
            )
        )
        .order_by(OutboxEvent.id)
        .limit(batch_size)
        .all()
    )


def _update_gauges(session) -> None:
    """Refresh Prometheus gauges that require a DB query."""
    try:
        now = datetime.now(timezone.utc)
        pending = (
            session.query(OutboxEvent)
            .filter(
                or_(
                    OutboxEvent.status == "PENDING",
                    OutboxEvent.status == "FAILED",
                )
            )
            .count()
        )
        _outbox_pending_rows.set(pending)

        oldest = (
            session.query(OutboxEvent.created_at)
            .filter(OutboxEvent.status == "PENDING")
            .order_by(OutboxEvent.id)
            .limit(1)
            .scalar()
        )
        if oldest:
            lag = (now - oldest.replace(tzinfo=timezone.utc)).total_seconds()
            _outbox_projection_lag_seconds.set(max(0.0, lag))
        else:
            _outbox_projection_lag_seconds.set(0.0)
    except Exception as exc:
        logger.debug("Gauge update skipped: %s", exc)


def process_batch(session) -> int:
    """
    Fetch a batch of projectable outbox rows, project each one,
    then mark as PUBLISHED inside the same Postgres session.

    Returns the number of events successfully projected.
    """
    rows = fetch_projectable_rows(session, BATCH_SIZE)

    if not rows:
        return 0

    projected = 0

    with _outbox_batch_seconds.time():
        for row in rows:
            event_type = row.event_type or "unknown"
            try:
                # ── Project to read models ───────────────────────
                with _outbox_projection_seconds.time():
                    project_to_mongo(row)
                    project_to_redis(row, session)

                # ── Mark PUBLISHED in Postgres ───────────────────
                row.status = "PUBLISHED"
                row.published_at = datetime.now(timezone.utc)
                _outbox_projected_total.labels(event_type=event_type).inc()
                projected += 1

            except Exception as exc:
                # Classify error: permanent → DEAD_LETTER, transient → retry
                retry_count = row.retry_count or 0
                row.retry_count = retry_count + 1
                row.last_error = str(exc)[:500]

                if _is_permanent_error(exc) or row.retry_count >= MAX_RETRIES:
                    row.status = "DEAD_LETTER"
                    _forward_to_dlq(row)
                    _outbox_dead_letter_total.labels(event_type=event_type).inc()
                    logger.exception(
                        "DEAD_LETTER outbox_id=%s event_id=%s retries=%d",
                        row.id,
                        row.event_id,
                        row.retry_count,
                    )
                else:
                    row.status = "FAILED"
                    row.next_retry_at = compute_next_retry_at(row.retry_count)
                    _outbox_retries_total.labels(event_type=event_type).inc()
                    logger.exception(
                        "Projection FAILED (retry %d/%d) outbox_id=%s event_id=%s "
                        "next_retry_at=%s",
                        row.retry_count,
                        MAX_RETRIES,
                        row.id,
                        row.event_id,
                        row.next_retry_at.isoformat(),
                    )

    # Single commit for the whole batch (status updates only).
    session.commit()
    return projected


def warm_up_redis_cache() -> None:
    """
    Load ALL existing PostgreSQL appointments into Redis hot cache on startup.

    Ensures the cache is warm so GET /arrivals/{id} can serve O(1) reads
    immediately after worker restart.
    """
    session = SessionLocal()
    try:
        total_pg = session.query(AppointmentORM).count()
        logger.info("Warm-up: caching %d PG appointments → Redis", total_pg)

        appointments = session.query(AppointmentORM).all()
        cached = 0

        for appt in appointments:
            try:
                snapshot = AppointmentSchema.model_validate(appt).model_dump(
                    mode="json"
                )
                cache_appointment(appt.id, snapshot)
                cached += 1
            except Exception as exc:
                logger.exception(
                    "Warm-up: failed to cache appointment %s",
                    appt.id,
                )

        logger.info("Warm-up complete: cached %d / %d appointments", cached, total_pg)
    except Exception as exc:
        logger.exception("Warm-up failed")
    finally:
        session.close()


def main() -> None:
    """Entry-point: infinite poll loop with graceful shutdown."""
    start_http_server(METRICS_PORT)
    logger.info(
        "Outbox Worker started — batch_size=%d  poll_interval=%ds  max_retries=%d  metrics=:%d",
        BATCH_SIZE,
        POLL_INTERVAL_SECONDS,
        MAX_RETRIES,
        METRICS_PORT,
    )

    # ── Warm-up: ensure Redis has all PG appointments cached ───
    warm_up_redis_cache()

    while not _shutdown_requested:
        session = SessionLocal()
        try:
            count = process_batch(session)
            if count > 0:
                logger.info("Projected %d event(s) to read models", count)
            _update_gauges(session)
        except Exception as exc:
            # Session-level or DB-level error — roll back and retry
            # on the next cycle.  The worker stays alive.
            logger.exception("Batch cycle failed")
            session.rollback()
        finally:
            session.close()

        # Sleep in small increments to react to shutdown signal promptly
        for _ in range(int(POLL_INTERVAL_SECONDS * 10)):
            if _shutdown_requested:
                break
            time.sleep(0.1)

    logger.info("Outbox Worker stopped gracefully")


if __name__ == "__main__":
    main()
