"""
Recurring-shift scheduler.

Materialises concrete ``Shift`` rows from active ``ShiftTemplate`` rules for an
upcoming horizon. Idempotent — it relies on the ``Shift`` composite primary key
``(gate_id, shift_type, date)`` to never create a duplicate, so it is safe to
run repeatedly (e.g. daily from ``scripts/shift_scheduler.py``).

This is intentionally PostgreSQL-only, mirroring the existing shift routes
(shifts are not projected to Mongo). It does not emit domain events.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def generate_shifts_from_templates(
    horizon_days: int = 14,
    *,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """Create Shift rows from active templates for the next ``horizon_days`` days.

    Rules applied:
      - only templates whose gate is active ('Ativo') are expanded;
      - a template produces a shift on a date only when ``template.covers(date)``
        (weekday mask + valid_from/valid_until + active);
      - existing ``(gate, shift_type, date)`` shifts are never overwritten;
      - an operator is not double-booked on a date — if the template's operator
        is already assigned that day, the generated shift is left unstaffed
        (``inactive``) for a manager to fill, rather than silently conflicting.

    Returns a summary dict ``{created, skipped, templates, horizon_days}``.
    """
    from infrastructure.persistence.postgres import SessionLocal
    from infrastructure.persistence.sql_models import (
        ShiftTemplate, Shift as ShiftORM, Gate as GateORM,
    )

    db = SessionLocal()
    created = 0
    skipped = 0
    try:
        start = today or date.today()
        if horizon_days < 1:
            horizon_days = 1
        days = [start + timedelta(days=i) for i in range(horizon_days)]
        window_start, window_end = days[0], days[-1]

        templates = db.query(ShiftTemplate).filter(ShiftTemplate.active.is_(True)).all()
        if not templates:
            return {"created": 0, "skipped": 0, "templates": 0, "horizon_days": horizon_days}

        active_gate_ids = {
            gid for (gid,) in db.query(GateORM.id).filter(GateORM.estado == "Ativo").all()
        }

        # Shifts already present in the window — never overwrite these.
        existing = {
            (s.gate_id, s.shift_type, s.date)
            for s in db.query(ShiftORM.gate_id, ShiftORM.shift_type, ShiftORM.date)
                       .filter(ShiftORM.date >= window_start, ShiftORM.date <= window_end)
                       .all()
        }
        # Operators already booked per date (avoid double-booking).
        operator_dates = {
            (s.operator_num_worker, s.date)
            for s in db.query(ShiftORM.operator_num_worker, ShiftORM.date)
                       .filter(ShiftORM.date >= window_start, ShiftORM.date <= window_end,
                               ShiftORM.operator_num_worker.isnot(None))
                       .all()
        }

        for tpl in templates:
            if tpl.gate_id not in active_gate_ids:
                continue
            for d in days:
                if not tpl.covers(d):
                    continue
                key = (tpl.gate_id, tpl.shift_type, d)
                if key in existing:
                    skipped += 1
                    continue

                operator = tpl.operator_num_worker
                if operator and (operator, d) in operator_dates:
                    operator = None  # already booked elsewhere that day → leave unstaffed

                db.add(ShiftORM(
                    gate_id=tpl.gate_id,
                    shift_type=tpl.shift_type,
                    date=d,
                    operator_num_worker=operator,
                    manager_num_worker=tpl.manager_num_worker,
                ))
                existing.add(key)
                if operator:
                    operator_dates.add((operator, d))
                created += 1

        db.commit()
        logger.info(
            "shift scheduler: created=%d skipped=%d from %d template(s) over %d day(s)",
            created, skipped, len(templates), horizon_days,
        )
        return {
            "created": created,
            "skipped": skipped,
            "templates": len(templates),
            "horizon_days": horizon_days,
        }
    except Exception:
        db.rollback()
        logger.exception("shift scheduler generation failed")
        raise
    finally:
        db.close()
