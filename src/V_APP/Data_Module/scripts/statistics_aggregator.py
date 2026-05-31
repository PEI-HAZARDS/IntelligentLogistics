#!/usr/bin/env python3
"""
Statistics Aggregator.

Runs once per hour and writes pre-computed documents into MongoDB so that
the statistics endpoints can serve from read models instead of running live
aggregation pipelines on every HTTP request.

Per cycle (triggered by the previous completed hour):
  1. statistics_hourly   — detections + decisions + PG entries/exits per gate
  2. statistics_daily    — roll-up of hourly docs per gate for the previous day
  3. operator_performance — operator review metrics from decision_events
  4. company_metrics      — per-company transport stats from PostgreSQL

Usage:
    python scripts/statistics_aggregator.py

On startup it also backfills statistics_daily/statistics_hourly for a historical
window (idempotent) so the volume / congestion-trend / heatmap / occupancy charts
have a full series from the first request — not just yesterday's rollup.

Environment variables:
    GATE_ID                          — single gate id (fallback when AGGREGATOR_GATE_IDS absent)
    AGGREGATOR_GATE_IDS              — JSON array of gate ids, e.g. '["1","2","3"]'
    AGGREGATOR_INTERVAL_SECONDS      — poll interval (default: 3600)
    AGGREGATOR_BACKFILL              — run the startup backfill (default: "true")
    AGGREGATOR_BACKFILL_DAILY_DAYS   — daily backfill horizon (default: 400)
    AGGREGATOR_BACKFILL_HOURLY_DAYS  — hourly backfill horizon (default: 14)
"""

import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone, timedelta

# ── Path setup (standalone script) ──────────────────────────────
_script_dir = os.path.dirname(os.path.abspath(__file__))
_data_module_dir = os.path.join(_script_dir, "..")
sys.path.insert(0, _data_module_dir)

from application.queries.statistics_queries import (
    compute_hourly_statistics,
    compute_daily_statistics,
    compute_operator_performance_snapshot,
)
from application.queries.manager_statistics_queries import compute_company_metrics_snapshot
from infrastructure.persistence.postgres import SessionLocal
from infrastructure.persistence.mongo import statistics_daily_collection
from config import settings

# ── Logging ─────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("statistics_aggregator")

# ── Configuration ────────────────────────────────────────────────
INTERVAL_SECONDS = int(os.getenv("AGGREGATOR_INTERVAL_SECONDS", "3600"))
BACKFILL_ENABLED = os.getenv("AGGREGATOR_BACKFILL", "true").lower() == "true"
BACKFILL_DAILY_DAYS = int(os.getenv("AGGREGATOR_BACKFILL_DAILY_DAYS", "400"))
BACKFILL_HOURLY_DAYS = int(os.getenv("AGGREGATOR_BACKFILL_HOURLY_DAYS", "14"))

_shutdown_requested = False


def _handle_signal(signum, frame):
    global _shutdown_requested
    logger.info("Received %s — shutting down after current cycle", signal.Signals(signum).name)
    _shutdown_requested = True


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


def _load_gate_ids() -> list[int]:
    raw = os.getenv("AGGREGATOR_GATE_IDS", "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                ids = [int(g) for g in parsed if str(g).strip()]
                if ids:
                    return ids
        except ValueError:
            logger.warning("Invalid AGGREGATOR_GATE_IDS format — falling back to GATE_ID")
    return [int(settings.gate_id)]


def _run_hourly(gate_ids: list[int], hour_timestamp: datetime | None, db, results: dict) -> None:
    for gate_id in gate_ids:
        try:
            doc = compute_hourly_statistics(gate_id, hour_timestamp, pg_session=db)
            if doc:
                bucket = doc["hour_bucket"].isoformat() if hasattr(doc.get("hour_bucket"), "isoformat") else str(doc.get("hour_bucket"))
                logger.info("Hourly stats: gate=%s hour=%s entries=%s exits=%s",
                            gate_id, bucket, doc.get("entries", 0), doc.get("exits", 0))
                results["ok"].append(gate_id)
            else:
                logger.warning("compute_hourly_statistics returned None for gate=%s", gate_id)
                results["failed"].append(gate_id)
        except Exception as exc:
            logger.exception("Hourly stats failed for gate=%s", gate_id)
            results["failed"].append(gate_id)


def _run_daily(gate_ids: list[int], prev_day: datetime, db) -> None:
    for gate_id in gate_ids:
        try:
            doc = compute_daily_statistics(gate_id, prev_day, pg_session=db)
            if doc:
                logger.info("Daily stats: gate=%s day=%s entries=%s exits=%s",
                            gate_id, prev_day.date(), doc.get("entries", 0), doc.get("exits", 0))
        except Exception as exc:
            logger.exception("Daily stats failed for gate=%s", gate_id)


def backfill(gate_ids: list[int]) -> None:
    """Idempotently populate statistics_daily/hourly for the historical window.

    Entry/exit counts come straight from PostgreSQL (both compute functions
    accept a ``pg_session``), so the daily/hourly volume series is accurate for
    past dates even though no Mongo hourly source docs exist for them. Without
    this, the rollups only contain "yesterday" and the volume / congestion /
    heatmap / occupancy charts collapse to a single bucket.

    Skipped when the daily collection already covers the window (cheap restarts).
    """
    if not BACKFILL_ENABLED:
        logger.info("Backfill disabled (AGGREGATOR_BACKFILL=false)")
        return

    now = datetime.now(timezone.utc)
    # Coverage guard: each backfilled day upserts one doc per gate, so a populated
    # window has ~ BACKFILL_DAILY_DAYS × gates docs. Skip if already covered.
    try:
        existing = statistics_daily_collection.count_documents(
            {"day_bucket": {"$gte": now - timedelta(days=BACKFILL_DAILY_DAYS)}}
        )
        expected = BACKFILL_DAILY_DAYS * len(gate_ids)
        if expected and existing >= 0.9 * expected:
            logger.info("Backfill skipped — statistics_daily already covers the window (%d docs)", existing)
            return
    except Exception:
        logger.exception("Backfill coverage check failed — proceeding with backfill")

    logger.info(
        "Backfill starting — daily=%d day(s), hourly=%d day(s), gates=%s (idempotent)",
        BACKFILL_DAILY_DAYS, BACKFILL_HOURLY_DAYS, gate_ids,
    )
    db = SessionLocal()
    days_done = hours_done = 0
    try:
        # Daily rollups — covers month/quarter/year volume + congestion trend.
        for i in range(1, BACKFILL_DAILY_DAYS + 1):
            if _shutdown_requested:
                break
            day = now - timedelta(days=i)
            for gate_id in gate_ids:
                try:
                    compute_daily_statistics(gate_id, day, pg_session=db)
                except Exception:
                    logger.exception("backfill daily failed gate=%s day=%s", gate_id, day.date())
            days_done += 1

        # Hourly rollups — recent days only (feeds the weekly heatmap + occupancy).
        for d in range(1, BACKFILL_HOURLY_DAYS + 1):
            if _shutdown_requested:
                break
            base = now - timedelta(days=d)
            for h in range(24):
                hour = base.replace(hour=h, minute=0, second=0, microsecond=0)
                for gate_id in gate_ids:
                    try:
                        compute_hourly_statistics(gate_id, hour, pg_session=db)
                    except Exception:
                        logger.exception("backfill hourly failed gate=%s hour=%s", gate_id, hour)
                hours_done += 1
    finally:
        db.close()

    logger.info(
        "Backfill complete — %d day(s) and %d hour(s) per gate (%d gate(s))",
        days_done, hours_done, len(gate_ids),
    )


def run_cycle(gate_ids: list[int], hour_timestamp: datetime | None = None) -> dict:
    """Run one aggregation pass for all gates. Returns summary dict."""
    results: dict = {"ok": [], "failed": []}
    db = SessionLocal()
    try:
        _run_hourly(gate_ids, hour_timestamp, db, results)

        prev_day = (hour_timestamp or datetime.now(timezone.utc)) - timedelta(days=1)
        _run_daily(gate_ids, prev_day, db)

        try:
            n = compute_operator_performance_snapshot()
            logger.info("Operator performance snapshot: %d operator(s) written", n)
        except Exception as exc:
            logger.exception("Operator performance snapshot failed")

        try:
            n = compute_company_metrics_snapshot(db)
            logger.info("Company metrics snapshot: %d company(ies) written", n)
        except Exception as exc:
            logger.exception("Company metrics snapshot failed")
    finally:
        db.close()

    return results


def main() -> None:
    gate_ids = _load_gate_ids()
    logger.info(
        "Statistics Aggregator started — gates=%s  interval=%ds",
        gate_ids, INTERVAL_SECONDS,
    )

    # One-time historical backfill so charts have a full series immediately.
    backfill(gate_ids)

    # Run immediately on startup for the previous completed hour
    prev_hour = datetime.now(timezone.utc) - timedelta(hours=1)
    results = run_cycle(gate_ids, prev_hour)
    logger.info("Startup cycle complete: ok=%s failed=%s", results["ok"], results["failed"])

    while not _shutdown_requested:
        # Sleep in small increments to react to shutdown signal promptly
        for _ in range(INTERVAL_SECONDS * 10):
            if _shutdown_requested:
                break
            time.sleep(0.1)

        if _shutdown_requested:
            break

        prev_hour = datetime.now(timezone.utc) - timedelta(hours=1)
        results = run_cycle(gate_ids, prev_hour)
        logger.info(
            "Aggregation cycle complete: ok=%s failed=%s",
            results["ok"], results["failed"],
        )

    logger.info("Statistics Aggregator stopped gracefully")


if __name__ == "__main__":
    main()
