#!/usr/bin/env python3
"""
Recurring-shift scheduler worker.

Periodically materialises concrete ``shift`` rows from active ``shift_template``
rules for an upcoming horizon, so managers don't have to create repeating shifts
by hand. Generation is idempotent (existing shifts are skipped), so a missed,
delayed, or overlapping run never produces duplicates.

Run as its own process (see docker-compose ``shift-scheduler`` service):
    python scripts/shift_scheduler.py

Environment:
    SHIFT_SCHEDULER_INTERVAL_SECONDS  poll period (default 86400 = once a day)
    SHIFT_SCHEDULER_HORIZON_DAYS      days ahead to materialise (default 14)
    SHIFT_SCHEDULER_RUN_ON_START      run immediately on boot (default "true")
"""

import os
import sys
import signal
import time
import logging

# ── Path setup (standalone script) ──────────────────────────────
_script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_script_dir, ".."))

from application.use_cases.shift_scheduler import generate_shifts_from_templates  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("shift_scheduler")

INTERVAL = int(os.environ.get("SHIFT_SCHEDULER_INTERVAL_SECONDS", "86400"))
HORIZON = int(os.environ.get("SHIFT_SCHEDULER_HORIZON_DAYS", "14"))
RUN_ON_START = os.environ.get("SHIFT_SCHEDULER_RUN_ON_START", "true").lower() == "true"

_shutdown = False


def _handle_signal(signum, _frame):
    global _shutdown
    _shutdown = True
    logger.info("Shutdown requested (signal %s)", signum)


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


def _run_once() -> None:
    try:
        result = generate_shifts_from_templates(HORIZON)
        logger.info("Generation cycle: %s", result)
    except Exception:
        # Stay alive — retry next cycle.
        logger.exception("Generation cycle failed")


def main() -> None:
    logger.info("Shift scheduler started — interval=%ds horizon=%dd", INTERVAL, HORIZON)
    if RUN_ON_START:
        _run_once()

    while not _shutdown:
        # Sleep in 1-second steps so SIGTERM is honoured promptly.
        for _ in range(INTERVAL):
            if _shutdown:
                break
            time.sleep(1)
        if _shutdown:
            break
        _run_once()

    logger.info("Shift scheduler stopped gracefully")


if __name__ == "__main__":
    main()
