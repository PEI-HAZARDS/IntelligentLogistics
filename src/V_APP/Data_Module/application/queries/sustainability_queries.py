"""
Sustainability queries for the Logistics Manager frontend.

Provides CO₂ estimates based on truck idle time at the gate.
Methodology: ICCT HDV Roadmap 2023 + EU JRC — 0.84 kg CO₂/hour idling
for a Euro VI heavy-duty truck. Waiting time = MAX(0, entry_time - scheduled_start_time).
Appointments without scheduled_start_time are excluded from CO₂ calculations.

Endpoints consumed:
  GET /statistics/sustainability/summary   → SustainabilitySummary
  GET /statistics/sustainability/trend     → SustainabilityTrendPoint[]
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, cast, extract, func, Float
from sqlalchemy.orm import Session

from infrastructure.persistence.postgres import SessionLocal
from infrastructure.persistence.sql_models import Appointment, Visit

logger = logging.getLogger("sustainability_queries")

# ICCT HDV Roadmap 2023 + EU JRC — Euro VI heavy-duty truck idle emissions
TRUCK_IDLE_CO2_KG_PER_HOUR: float = 0.84
TRUCK_IDLE_CO2_KG_PER_MIN: float = TRUCK_IDLE_CO2_KG_PER_HOUR / 60
DELAY_THRESHOLD_MINUTES: int = 15


def _parse_date_range(
    from_str: Optional[str], to_str: Optional[str]
) -> tuple[datetime, datetime]:
    """Return (start, end) UTC datetimes. Defaults to current week (Mon–Sun)."""
    today = datetime.now(timezone.utc).date()
    if from_str:
        d_from = datetime.strptime(from_str, "%Y-%m-%d").date()
    else:
        d_from = today - timedelta(days=today.weekday())
    if to_str:
        d_to = datetime.strptime(to_str, "%Y-%m-%d").date()
    else:
        d_to = today

    start = datetime.combine(d_from, time.min, tzinfo=timezone.utc)
    end = datetime.combine(d_to, time.max, tzinfo=timezone.utc)
    return start, end


def _waiting_minutes_expr():
    """
    SQLAlchemy expression: MAX(0, entry_time - scheduled_start_time) in minutes.
    Only computed when both fields are present.
    """
    return func.greatest(
        0.0,
        cast(
            extract("epoch", Visit.entry_time - Appointment.scheduled_start_time) / 60,
            Float,
        ),
    )


# ---------------------------------------------------------------------------
# 1. GET /statistics/sustainability/summary
# ---------------------------------------------------------------------------

def get_sustainability_summary(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Returns CO₂ and waiting-time KPIs for the given date range.

    Response shape:
    {
        "avg_waiting_minutes": float,
        "total_co2_kg_estimate": float,
        "trucks_delayed": int,             # waiting > DELAY_THRESHOLD_MINUTES
        "trucks_processed": int,           # appointments with known entry_time
        "appointments_excluded": int,      # no scheduled_start_time → excluded
        "avg_co2_per_truck_kg": float,
        "from_date": str,                  # ISO date
        "to_date": str,
        "methodology": str,
    }
    """
    start, end = _parse_date_range(from_date, to_date)
    db: Session = SessionLocal()
    try:
        # Base: appointments with entry_time in range + scheduled_start_time known
        base_q = (
            db.query(Appointment, Visit)
            .join(Visit, Visit.appointment_id == Appointment.id)
            .filter(
                Visit.entry_time.isnot(None),
                Visit.entry_time.between(start, end),
                Appointment.scheduled_start_time.isnot(None),
            )
        )

        rows = base_q.all()
        trucks_processed = len(rows)

        # Appointments in range but without scheduled_start_time (excluded)
        excluded = (
            db.query(func.count(Appointment.id))
            .join(Visit, Visit.appointment_id == Appointment.id)
            .filter(
                Visit.entry_time.isnot(None),
                Visit.entry_time.between(start, end),
                Appointment.scheduled_start_time.is_(None),
            )
            .scalar()
        ) or 0

        if trucks_processed == 0:
            return {
                "avg_waiting_minutes": 0.0,
                "total_co2_kg_estimate": 0.0,
                "trucks_delayed": 0,
                "trucks_processed": 0,
                "appointments_excluded": excluded,
                "avg_co2_per_truck_kg": 0.0,
                "wait_distribution": {"0_5": 0, "5_15": 0, "15_30": 0, "over_30": 0},
                "from_date": start.date().isoformat(),
                "to_date": end.date().isoformat(),
                "methodology": f"ICCT HDV 2023 + EU JRC — {TRUCK_IDLE_CO2_KG_PER_HOUR} kg CO₂/h idling (Euro VI)",
            }

        waiting_minutes: list[float] = []
        for appt, visit in rows:
            diff = (visit.entry_time - appt.scheduled_start_time).total_seconds() / 60
            waiting_minutes.append(max(0.0, diff))

        avg_waiting = round(sum(waiting_minutes) / len(waiting_minutes), 1)
        total_waiting = sum(waiting_minutes)
        total_co2 = round(total_waiting * TRUCK_IDLE_CO2_KG_PER_MIN, 2)
        co2_avg = round(total_co2 / trucks_processed, 2) if trucks_processed else 0.0
        delayed = sum(1 for w in waiting_minutes if w > DELAY_THRESHOLD_MINUTES)

        wait_distribution = {
            "0_5":    sum(1 for w in waiting_minutes if w <= 5),
            "5_15":   sum(1 for w in waiting_minutes if 5 < w <= 15),
            "15_30":  sum(1 for w in waiting_minutes if 15 < w <= 30),
            "over_30": sum(1 for w in waiting_minutes if w > 30),
        }

        return {
            "avg_waiting_minutes": avg_waiting,
            "total_co2_kg_estimate": total_co2,
            "trucks_delayed": delayed,
            "trucks_processed": trucks_processed,
            "appointments_excluded": excluded,
            "avg_co2_per_truck_kg": co2_avg,
            "wait_distribution": wait_distribution,
            "from_date": start.date().isoformat(),
            "to_date": end.date().isoformat(),
            "methodology": f"ICCT HDV 2023 + EU JRC — {TRUCK_IDLE_CO2_KG_PER_HOUR} kg CO₂/h idling (Euro VI)",
        }
    except Exception:
        logger.exception("get_sustainability_summary failed")
        return {
            "avg_waiting_minutes": 0.0,
            "total_co2_kg_estimate": 0.0,
            "trucks_delayed": 0,
            "trucks_processed": 0,
            "appointments_excluded": 0,
            "avg_co2_per_truck_kg": 0.0,
            "wait_distribution": {"0_5": 0, "5_15": 0, "15_30": 0, "over_30": 0},
            "from_date": start.date().isoformat(),
            "to_date": end.date().isoformat(),
            "methodology": f"ICCT HDV 2023 + EU JRC — {TRUCK_IDLE_CO2_KG_PER_HOUR} kg CO₂/h idling (Euro VI)",
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 2. GET /statistics/sustainability/trend
# ---------------------------------------------------------------------------

def get_sustainability_trend(
    granularity: str = "day",
    n_periods: int = 12,
) -> List[Dict[str, Any]]:
    """
    Returns a time-series of CO₂ estimates and avg waiting times.

    granularity: 'day' | 'week' | 'month'
    n_periods:   number of past periods to return (max 52)

    Response shape:
    [
      {
        "period": "2026-05-01",         # ISO date of period start
        "avg_waiting_minutes": float,
        "total_co2_kg": float,
        "trucks_processed": int,
      },
      ...
    ]
    """
    n_periods = min(max(n_periods, 1), 52)

    granularity_map = {"day": "day", "week": "week", "month": "month"}
    trunc = granularity_map.get(granularity, "day")

    now = datetime.now(timezone.utc)

    if trunc == "day":
        period_start = now - timedelta(days=n_periods)
    elif trunc == "week":
        period_start = now - timedelta(weeks=n_periods)
    else:  # month — align to first day of month so each bucket is a full calendar month
        today = now.date()
        month = today.month - n_periods
        year  = today.year
        while month <= 0:
            month += 12
            year  -= 1
        period_start = datetime(year, month, 1, tzinfo=timezone.utc)

    db: Session = SessionLocal()
    try:
        trunc_expr = func.date_trunc(trunc, Visit.entry_time)

        rows = (
            db.query(
                trunc_expr.label("period"),
                func.count(Appointment.id).label("trucks"),
                func.avg(_waiting_minutes_expr()).label("avg_waiting"),
                func.sum(_waiting_minutes_expr()).label("total_waiting"),
            )
            .join(Visit, Visit.appointment_id == Appointment.id)
            .filter(
                Visit.entry_time.isnot(None),
                Visit.entry_time >= period_start,
                Appointment.scheduled_start_time.isnot(None),
            )
            .group_by("period")
            .order_by("period")
            .all()
        )

        return [
            {
                "period": row.period.date().isoformat() if row.period else None,
                "avg_waiting_minutes": round(float(row.avg_waiting or 0), 1),
                "total_co2_kg": round(
                    float(row.total_waiting or 0) * TRUCK_IDLE_CO2_KG_PER_MIN, 2
                ),
                "trucks_processed": row.trucks,
            }
            for row in rows
        ]
    except Exception:
        logger.exception("get_sustainability_trend failed")
        return []
    finally:
        db.close()
