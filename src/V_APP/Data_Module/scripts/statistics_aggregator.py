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

Environment variables:
    GATE_ID                      — single gate id (fallback when AGGREGATOR_GATE_IDS absent)
    AGGREGATOR_GATE_IDS          — JSON array of gate ids, e.g. '["1","2","3"]'
    AGGREGATOR_INTERVAL_SECONDS  — poll interval (default: 3600)
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
        except (json.JSONDecodeError, ValueError):
            logger.warning("Invalid AGGREGATOR_GATE_IDS format — falling back to GATE_ID")
    return [int(settings.gate_id)]


def run_cycle(gate_ids: list[int], hour_timestamp: datetime | None = None) -> dict:
    """Run one aggregation pass for all gates. Returns summary dict."""
    results: dict = {"ok": [], "failed": []}
    db = SessionLocal()
    try:
        # ── 1. Hourly stats per gate ─────────────────────────────────────────
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
                logger.error("Hourly stats failed for gate=%s: %s", gate_id, exc, exc_info=True)
                results["failed"].append(gate_id)

        # ── 2. Daily roll-up per gate ────────────────────────────────────────
        prev_day = (hour_timestamp or datetime.now(timezone.utc)) - timedelta(days=1)
        for gate_id in gate_ids:
            try:
                doc = compute_daily_statistics(gate_id, prev_day, pg_session=db)
                if doc:
                    logger.info("Daily stats: gate=%s day=%s entries=%s exits=%s",
                                gate_id, prev_day.date(), doc.get("entries", 0), doc.get("exits", 0))
            except Exception as exc:
                logger.error("Daily stats failed for gate=%s: %s", gate_id, exc, exc_info=True)

        # ── 3. Operator performance snapshot ────────────────────────────────
        try:
            n = compute_operator_performance_snapshot()
            logger.info("Operator performance snapshot: %d operator(s) written", n)
        except Exception as exc:
            logger.error("Operator performance snapshot failed: %s", exc, exc_info=True)

        # ── 4. Company metrics snapshot ──────────────────────────────────────
        try:
            n = compute_company_metrics_snapshot(db)
            logger.info("Company metrics snapshot: %d company(ies) written", n)
        except Exception as exc:
            logger.error("Company metrics snapshot failed: %s", exc, exc_info=True)

    finally:
        db.close()

    return results


def main() -> None:
    gate_ids = _load_gate_ids()
    logger.info(
        "Statistics Aggregator started — gates=%s  interval=%ds",
        gate_ids, INTERVAL_SECONDS,
    )

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
