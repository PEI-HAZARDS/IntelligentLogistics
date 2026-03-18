#!/usr/bin/env python3
"""
Simple Outbox Worker — Eventual Consistency via Transactional Outbox.

Polls the ``outbox_events`` table for PENDING rows and projects each event
into the read models (MongoDB for history, Redis for hot cache), then marks
the row as PUBLISHED.

This is the missing piece between the write path (ContainerMovedHandler
commits domain mutation + outbox row atomically in PostgreSQL) and the
read path (dashboards query MongoDB/Redis).

┌────────────┐  commit   ┌──────────┐  poll   ┌──────────────────┐
│  Command   │──────────▶│ outbox_  │◀───────│  THIS WORKER     │
│  Handler   │           │ events   │         │                  │
│ (Postgres) │           │ (PG)     │────────▶│  ┌── MongoDB ──┐ │
└────────────┘           └──────────┘  read   │  │  (history)  │ │
                                       batch  │  └─────────────┘ │
                                              │  ┌── Redis ────┐ │
                                              │  │  (hot cache) │ │
                                              │  └─────────────┘ │
                                              └──────────────────┘

Usage:
    python scripts/simple_outbox_worker.py

Guardrails enforced:
  3 — Outbox is the ONLY source of side-effects; no direct publish.
  5 — CQRS strict split: this worker updates READ models only.
  7 — Projections are idempotent (upsert in Mongo, overwrite in Redis).
"""

import sys
import os
import time
import json
import logging
from datetime import datetime, timezone

# ── Path setup (standalone script) ──────────────────────────────
_script_dir = os.path.dirname(os.path.abspath(__file__))
_data_module_dir = os.path.join(_script_dir, "..")
sys.path.insert(0, _data_module_dir)

# ── Imports from Data Module ────────────────────────────────────
from db.postgres import SessionLocal
from db.mongo import decision_events_collection
from db.redis import (
    redis_client,
    cache_appointment,
    invalidate_appointment_cache,
    increment_counter,
)
from infrastructure.persistence.inbox_outbox_models import OutboxEvent

# ── Configuration ───────────────────────────────────────────────
BATCH_SIZE = 50
POLL_INTERVAL_SECONDS = 2

# ── Logging ─────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("outbox_worker")


# ═══════════════════════════════════════════════════════════════
# Projection functions (one per event_type)
# ═══════════════════════════════════════════════════════════════


def project_to_mongo(event_row: OutboxEvent) -> None:
    """
    Insert (or upsert) the event into MongoDB for historical queries.

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

    # Upsert — idempotent: replaying the same event overwrites with
    # identical data instead of creating a duplicate.
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


def project_to_redis(event_row: OutboxEvent) -> None:
    """
    Update Redis hot caches so dashboards reflect the latest state.

    For ``AppointmentStateChanged`` events we:
      1. Invalidate the stale appointment cache entry.
      2. Write a lightweight snapshot so the next read is a cache HIT.
      3. Bump the real-time counter for the gate.
    """
    payload = event_row.payload or {}
    event_type = event_row.event_type

    if event_type == "AppointmentStateChanged":
        appointment_id = payload.get("appointment_id")
        if appointment_id is not None:
            # 1) Invalidate stale entry
            invalidate_appointment_cache(int(appointment_id))

            # 2) Write new snapshot into the hot cache
            snapshot = {
                "appointment_id": appointment_id,
                "status": payload.get("new_state"),
                "previous_status": payload.get("previous_state"),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            cache_appointment(int(appointment_id), snapshot)

            # 3) Real-time counters (extract gate from payload metadata)
            gate_id = payload.get("gate_in_id") or payload.get("gate_out_id")
            if gate_id is not None:
                new_state = payload.get("new_state", "unknown")
                increment_counter(int(gate_id), f"transitions:{new_state}")

    logger.debug(
        "Redis projection OK: event_id=%s  type=%s",
        event_row.event_id,
        event_type,
    )


# ═══════════════════════════════════════════════════════════════
# Main loop
# ═══════════════════════════════════════════════════════════════


def process_batch(session) -> int:
    """
    Fetch a batch of PENDING outbox rows, project each one,
    then mark as PUBLISHED inside the same Postgres session.

    Returns the number of events successfully projected.
    """
    rows = (
        session.query(OutboxEvent)
        .filter(OutboxEvent.status == "PENDING")
        .order_by(OutboxEvent.id)
        .limit(BATCH_SIZE)
        .all()
    )

    if not rows:
        return 0

    projected = 0

    for row in rows:
        try:
            # ── Project to read models ───────────────────────
            project_to_mongo(row)
            project_to_redis(row)

            # ── Mark PUBLISHED in Postgres ───────────────────
            row.status = "PUBLISHED"
            row.published_at = datetime.now(timezone.utc)
            projected += 1

        except Exception as exc:
            # Transient failure on ONE event must not kill the batch.
            # Log, mark FAILED, and continue with the next row.
            logger.error(
                "Projection failed for outbox_id=%s event_id=%s: %s",
                row.id,
                row.event_id,
                exc,
                exc_info=True,
            )
            row.status = "FAILED"
            row.last_error = str(exc)[:500]

    # Single commit for the whole batch (status updates only).
    session.commit()
    return projected


def main() -> None:
    """Entry-point: infinite poll loop with graceful error handling."""
    logger.info(
        "Outbox Worker started — batch_size=%d  poll_interval=%ds",
        BATCH_SIZE,
        POLL_INTERVAL_SECONDS,
    )

    while True:
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

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
