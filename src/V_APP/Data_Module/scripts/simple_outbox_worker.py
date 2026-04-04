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

import sys
import os
import signal
import time
import random
import logging
from datetime import datetime, timezone, timedelta

# ── Path setup (standalone script) ──────────────────────────────
_script_dir = os.path.dirname(os.path.abspath(__file__))
_data_module_dir = os.path.join(_script_dir, "..")
sys.path.insert(0, _data_module_dir)

# ── Imports from Data Module ────────────────────────────────────
from infrastructure.persistence.postgres import SessionLocal
from infrastructure.persistence.mongo import decision_events_collection
from infrastructure.persistence.redis import (
    redis_client,
    cache_appointment,
    invalidate_appointment_cache,
    increment_counter,
)
from infrastructure.persistence.inbox_outbox_models import OutboxEvent
from infrastructure.persistence.sql_models import Appointment as AppointmentORM
from application.schemas import Appointment as AppointmentSchema
from sqlalchemy import or_, and_

# ── Configuration ───────────────────────────────────────────────
BATCH_SIZE = 50
POLL_INTERVAL_SECONDS = 2
MAX_RETRIES = 5
BACKOFF_BASE_SECONDS = 2       # 2, 4, 8, 16, 32 seconds
BACKOFF_MAX_SECONDS = 60       # cap backoff at 1 minute
JITTER_MAX_SECONDS = 2         # random jitter up to 2 seconds

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
    Insert (or upsert) the event into MongoDB decision_events for audit trail.

    Uses ``event_id`` as the idempotency key so re-processing the same
    outbox row produces identical state (Guardrail 7).
    """
    doc = {
        "event_id": event_row.event_id,
        "event_type": event_row.event_type,
        "event_version": event_row.event_version,
        "aggregate_type": event_row.aggregate_type,
        "aggregate_id": event_row.aggregate_id,
        "partition_key": event_row.partition_key,
        "topic": event_row.topic,
        "payload": event_row.payload,
        "created_at": event_row.created_at or datetime.now(timezone.utc),
        "projected_at": datetime.now(timezone.utc),
    }

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


def project_to_redis(event_row: OutboxEvent, session) -> None:
    """
    Update Redis hot caches so dashboards reflect the latest state.

    For appointment-related events:
      1. Invalidate the stale appointment cache entry.
      2. Query the full Appointment from PostgreSQL and write a JSON
         snapshot into Redis — GET /arrivals/{id} reads this key (O(1)).
      3. Bump the real-time counter for the gate.
    """
    payload = event_row.payload or {}
    event_type = event_row.event_type

    _APPOINTMENT_EVENT_TYPES = {
        "AppointmentStateChanged",
        "AppointmentStatusUpdated",
        "AppointmentHighwayInfractionFlagged",
        "DecisionProcessed",
        "VisitCreated",
        "VisitStateUpdated",
    }

    if event_type in _APPOINTMENT_EVENT_TYPES:
        appointment_id = payload.get("appointment_id")
        if appointment_id is not None:
            # 1) Invalidate stale entry
            invalidate_appointment_cache(int(appointment_id))

            # 2) Full appointment snapshot → Redis hot cache
            appt = (
                session.query(AppointmentORM)
                .filter(AppointmentORM.id == int(appointment_id))
                .first()
            )
            if appt:
                snapshot = AppointmentSchema.model_validate(appt).model_dump(
                    mode="json"
                )
                cache_appointment(int(appointment_id), snapshot)
            else:
                logger.warning(
                    "Appointment %s not found during projection",
                    appointment_id,
                )

            # 3) Real-time counters
            gate_id = payload.get("gate_in_id") or payload.get("gate_out_id")
            if gate_id is not None:
                new_state = payload.get("new_state", "unknown")
                increment_counter(int(gate_id), f"transitions:{new_state}")

    # Alert events: just invalidate related appointment cache
    if event_type in {"AlertCreated", "HazmatAlertCreated"}:
        appointment_id = payload.get("appointment_id")
        if appointment_id is not None:
            invalidate_appointment_cache(int(appointment_id))

    logger.debug(
        "Redis projection OK: event_id=%s  type=%s",
        event_row.event_id,
        event_type,
    )


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

    for row in rows:
        try:
            # ── Project to read models ───────────────────────
            project_to_mongo(row)
            project_to_redis(row, session)

            # ── Mark PUBLISHED in Postgres ───────────────────
            row.status = "PUBLISHED"
            row.published_at = datetime.now(timezone.utc)
            projected += 1

        except Exception as exc:
            # Classify error: permanent → DEAD_LETTER, transient → retry
            row.retry_count = (row.retry_count or 0) + 1
            row.last_error = str(exc)[:500]

            if _is_permanent_error(exc) or row.retry_count >= MAX_RETRIES:
                row.status = "DEAD_LETTER"
                logger.error(
                    "DEAD_LETTER outbox_id=%s event_id=%s retries=%d: %s",
                    row.id,
                    row.event_id,
                    row.retry_count,
                    exc,
                )
            else:
                row.status = "FAILED"
                row.next_retry_at = compute_next_retry_at(row.retry_count)
                logger.warning(
                    "Projection FAILED (retry %d/%d) outbox_id=%s event_id=%s "
                    "next_retry_at=%s: %s",
                    row.retry_count,
                    MAX_RETRIES,
                    row.id,
                    row.event_id,
                    row.next_retry_at.isoformat(),
                    exc,
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
                logger.warning(
                    "Warm-up: failed to cache appointment %s: %s",
                    appt.id,
                    exc,
                )

        logger.info("Warm-up complete: cached %d / %d appointments", cached, total_pg)
    except Exception as exc:
        logger.error("Warm-up failed: %s", exc, exc_info=True)
    finally:
        session.close()


def main() -> None:
    """Entry-point: infinite poll loop with graceful shutdown."""
    logger.info(
        "Outbox Worker started — batch_size=%d  poll_interval=%ds  max_retries=%d",
        BATCH_SIZE,
        POLL_INTERVAL_SECONDS,
        MAX_RETRIES,
    )

    # ── Warm-up: ensure Redis has all PG appointments cached ───
    warm_up_redis_cache()

    while not _shutdown_requested:
        session = SessionLocal()
        try:
            count = process_batch(session)
            if count > 0:
                logger.info("Projected %d event(s) to read models", count)
        except Exception as exc:
            # Session-level or DB-level error — roll back and retry
            # on the next cycle.  The worker stays alive.
            logger.error("Batch cycle failed: %s", exc, exc_info=True)
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
