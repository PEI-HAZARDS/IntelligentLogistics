"""
Manager statistics queries for the Logistics Manager frontend.

Provides the 4 endpoints consumed by statistics.ts:
  /statistics/summary        → DashboardSummary
  /statistics/by-company     → TransportStats[]
  /statistics/volume          → VolumeDataPoint[]
  /statistics/alerts          → AlertsBreakdown[]

All queries hit PostgreSQL (source of truth).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import case, cast, func, Date, Integer, extract
from sqlalchemy.orm import Session

from infrastructure.persistence.postgres import SessionLocal
from infrastructure.persistence.sql_models import (
    Alert,
    Appointment,
    Company,
    Truck,
    Visit,
)

logger = logging.getLogger("manager_statistics_queries")


def _today_range(target_date: Optional[str] = None):
    """Return (start, end) datetimes for a given date string or today."""
    if target_date:
        d = datetime.strptime(target_date, "%Y-%m-%d").date()
    else:
        d = datetime.now(timezone.utc).date()
    start = datetime.combine(d, time.min, tzinfo=timezone.utc)
    end = datetime.combine(d, time.max, tzinfo=timezone.utc)
    return start, end


def _date_range(from_str: Optional[str], to_str: Optional[str]):
    """Return (start, end) datetimes from optional ISO date strings.  Defaults to today."""
    if from_str:
        start = datetime.combine(
            datetime.strptime(from_str, "%Y-%m-%d").date(),
            time.min,
            tzinfo=timezone.utc,
        )
    else:
        start = datetime.combine(
            datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc
        )
    if to_str:
        end = datetime.combine(
            datetime.strptime(to_str, "%Y-%m-%d").date(),
            time.max,
            tzinfo=timezone.utc,
        )
    else:
        end = datetime.combine(
            datetime.now(timezone.utc).date(), time.max, tzinfo=timezone.utc
        )
    return start, end


# ---------------------------------------------------------------------------
# 1. GET /statistics/summary
# ---------------------------------------------------------------------------

def get_dashboard_summary(target_date: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns:
        { totalTrucks, entriesCount, exitsCount,
          avgPermanenceMinutes, delayRate, slaCompliance }
    """
    day_start, day_end = _today_range(target_date)
    db: Session = SessionLocal()
    try:
        # Appointments scheduled for this day
        base = db.query(Appointment).filter(
            Appointment.scheduled_start_time.between(day_start, day_end)
        )
        total_appointments = base.count()
        total_trucks = (
            db.query(func.count(func.distinct(Appointment.truck_license_plate)))
            .filter(Appointment.scheduled_start_time.between(day_start, day_end))
            .scalar()
        ) or 0

        # Entries / exits via Visit
        entries_count = (
            db.query(func.count(Visit.appointment_id))
            .join(Appointment, Visit.appointment_id == Appointment.id)
            .filter(Visit.entry_time.between(day_start, day_end))
            .scalar()
        ) or 0

        exits_count = (
            db.query(func.count(Visit.appointment_id))
            .join(Appointment, Visit.appointment_id == Appointment.id)
            .filter(Visit.out_time.between(day_start, day_end))
            .scalar()
        ) or 0

        # Average permanence (minutes) for visits that have both entry and exit today
        avg_perm = (
            db.query(
                func.avg(
                    extract("epoch", Visit.out_time - Visit.entry_time) / 60
                )
            )
            .filter(
                Visit.entry_time.isnot(None),
                Visit.out_time.isnot(None),
                Visit.out_time.between(day_start, day_end),
            )
            .scalar()
        )
        avg_permanence = round(float(avg_perm), 1) if avg_perm else 0.0

        # Delay rate
        delayed_count = base.filter(
            Appointment.status.in_(["delayed"])
        ).count()
        delay_rate = (
            round(delayed_count / total_appointments * 100, 1)
            if total_appointments > 0
            else 0.0
        )

        # SLA compliance = completed on time / (completed + delayed) * 100
        completed_count = base.filter(Appointment.status == "completed").count()
        sla_denominator = completed_count + delayed_count
        sla_compliance = (
            round(completed_count / sla_denominator * 100, 1)
            if sla_denominator > 0
            else 100.0
        )

        return {
            "totalTrucks": total_trucks,
            "entriesCount": entries_count,
            "exitsCount": exits_count,
            "avgPermanenceMinutes": avg_permanence,
            "delayRate": delay_rate,
            "slaCompliance": sla_compliance,
        }
    except Exception as e:
        logger.error("get_dashboard_summary failed: %s", e)
        return {
            "totalTrucks": 0,
            "entriesCount": 0,
            "exitsCount": 0,
            "avgPermanenceMinutes": 0,
            "delayRate": 0,
            "slaCompliance": 100,
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 2. GET /statistics/by-company
# ---------------------------------------------------------------------------

def get_transport_stats(
    from_date: Optional[str] = None, to_date: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Returns per-company transport statistics:
        [{ companyName, companyNif, avgUnloadingTime, avgWaitingTime,
           operationsCount, slaAttendedRate }]
    """
    start, end = _date_range(from_date, to_date)
    db: Session = SessionLocal()
    try:
        # Subquery: appointments with their visits in the date range
        rows = (
            db.query(
                Company.name.label("company_name"),
                Company.nif.label("company_nif"),
                func.count(Appointment.id).label("ops_count"),
                func.avg(
                    extract("epoch", Visit.out_time - Visit.entry_time) / 60
                ).label("avg_unloading"),
                func.avg(
                    extract(
                        "epoch",
                        Visit.entry_time - Appointment.scheduled_start_time,
                    )
                    / 60
                ).label("avg_waiting"),
                func.sum(
                    case(
                        (Appointment.status == "completed", 1),
                        else_=0,
                    )
                ).label("completed_count"),
            )
            .join(Truck, Appointment.truck_license_plate == Truck.license_plate)
            .join(Company, Truck.company_nif == Company.nif)
            .outerjoin(Visit, Visit.appointment_id == Appointment.id)
            .filter(
                Appointment.scheduled_start_time.between(start, end),
            )
            .group_by(Company.nif, Company.name)
            .all()
        )

        result = []
        for r in rows:
            ops = r.ops_count or 0
            completed = r.completed_count or 0
            sla_rate = round(completed / ops * 100, 1) if ops > 0 else 0.0
            result.append(
                {
                    "companyName": r.company_name,
                    "companyNif": r.company_nif,
                    "avgUnloadingTime": round(float(r.avg_unloading), 0) if r.avg_unloading else 0,
                    "avgWaitingTime": round(float(r.avg_waiting), 0) if r.avg_waiting else 0,
                    "operationsCount": ops,
                    "slaAttendedRate": sla_rate,
                }
            )
        return result
    except Exception as e:
        logger.error("get_transport_stats failed: %s", e)
        return []
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 3. GET /statistics/volume
# ---------------------------------------------------------------------------

def get_volume_data(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    interval: str = "hour",
) -> List[Dict[str, Any]]:
    """
    Returns time-series volume data:
        [{ timestamp, entries, exits }]
    """
    start, end = _date_range(from_date, to_date)
    db: Session = SessionLocal()
    try:
        if interval == "day":
            trunc_fn = func.date_trunc("day", Visit.entry_time)
            trunc_fn_out = func.date_trunc("day", Visit.out_time)
        elif interval == "week":
            trunc_fn = func.date_trunc("week", Visit.entry_time)
            trunc_fn_out = func.date_trunc("week", Visit.out_time)
        else:  # hour
            trunc_fn = func.date_trunc("hour", Visit.entry_time)
            trunc_fn_out = func.date_trunc("hour", Visit.out_time)

        # Entries per bucket
        entries_q = (
            db.query(
                trunc_fn.label("bucket"),
                func.count().label("entries"),
            )
            .filter(Visit.entry_time.between(start, end))
            .group_by("bucket")
            .subquery()
        )

        # Exits per bucket
        exits_q = (
            db.query(
                trunc_fn_out.label("bucket"),
                func.count().label("exits"),
            )
            .filter(Visit.out_time.between(start, end))
            .group_by("bucket")
            .subquery()
        )

        # Full outer join via union of buckets
        from sqlalchemy import literal_column, union_all, select

        all_buckets = union_all(
            select(entries_q.c.bucket), select(exits_q.c.bucket)
        ).subquery()

        distinct_buckets = (
            db.query(func.distinct(all_buckets.c.bucket).label("bucket"))
            .subquery()
        )

        rows = (
            db.query(
                distinct_buckets.c.bucket,
                func.coalesce(entries_q.c.entries, 0).label("entries"),
                func.coalesce(exits_q.c.exits, 0).label("exits"),
            )
            .outerjoin(entries_q, entries_q.c.bucket == distinct_buckets.c.bucket)
            .outerjoin(exits_q, exits_q.c.bucket == distinct_buckets.c.bucket)
            .order_by(distinct_buckets.c.bucket)
            .all()
        )

        return [
            {
                "timestamp": r.bucket.isoformat() if r.bucket else None,
                "entries": r.entries,
                "exits": r.exits,
            }
            for r in rows
        ]
    except Exception as e:
        logger.error("get_volume_data failed: %s", e)
        return []
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 4. GET /statistics/alerts
# ---------------------------------------------------------------------------

def get_alerts_breakdown(
    from_date: Optional[str] = None, to_date: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Returns alerts breakdown by type:
        [{ type, count, percentage }]
    """
    start, end = _date_range(from_date, to_date)
    db: Session = SessionLocal()
    try:
        rows = (
            db.query(
                Alert.type.label("alert_type"),
                func.count(Alert.id).label("cnt"),
            )
            .filter(Alert.timestamp.between(start, end))
            .group_by(Alert.type)
            .all()
        )

        total = sum(r.cnt for r in rows) or 1  # avoid division by zero
        return [
            {
                "type": str(r.alert_type),
                "count": r.cnt,
                "percentage": round(r.cnt / total * 100, 1),
            }
            for r in rows
        ]
    except Exception as e:
        logger.error("get_alerts_breakdown failed: %s", e)
        return []
    finally:
        db.close()
