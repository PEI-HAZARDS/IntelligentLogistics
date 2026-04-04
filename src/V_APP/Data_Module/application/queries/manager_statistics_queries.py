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
    Dock,
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
    Returns enriched dashboard summary:
        { trucksInPort, trucksInTransit, scheduledCount, unloadingCount,
          completedCount, entriesCount, exitsCount,
          avgPermanenceMinutes, avgWaitingMinutes,
          delayRate, slaCompliance, infractionCount, peakHour }
    """
    day_start, day_end = _today_range(target_date)
    db: Session = SessionLocal()
    try:
        # Appointments scheduled for this day
        base = db.query(Appointment).filter(
            Appointment.scheduled_start_time.between(day_start, day_end)
        )
        total_appointments = base.count()

        # Status counts
        scheduled_count = base.filter(Appointment.status == "scheduled").count()
        in_transit_count = base.filter(Appointment.status == "in_transit").count()
        in_process_count = base.filter(Appointment.status == "in_process").count()
        unloading_count = base.filter(Appointment.status == "unloading").count()
        completed_count = base.filter(Appointment.status == "completed").count()
        delayed_count = base.filter(Appointment.status == "delayed").count()

        # Trucks actually inside the port: in_process + unloading
        trucks_in_port = in_process_count + unloading_count

        # Infraction count
        infraction_count = base.filter(
            Appointment.highway_infraction.is_(True)
        ).count()

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

        # Average waiting time (minutes): entry_time - scheduled_start_time
        avg_wait = (
            db.query(
                func.avg(
                    extract(
                        "epoch",
                        Visit.entry_time - Appointment.scheduled_start_time,
                    )
                    / 60
                )
            )
            .join(Appointment, Visit.appointment_id == Appointment.id)
            .filter(
                Visit.entry_time.isnot(None),
                Visit.entry_time.between(day_start, day_end),
            )
            .scalar()
        )
        avg_waiting = round(float(avg_wait), 1) if avg_wait else 0.0

        # Delay rate
        delay_rate = (
            round(delayed_count / total_appointments * 100, 1)
            if total_appointments > 0
            else 0.0
        )

        # SLA compliance = completed on time / (completed + delayed) * 100
        sla_denominator = completed_count + delayed_count
        sla_compliance = (
            round(completed_count / sla_denominator * 100, 1)
            if sla_denominator > 0
            else 100.0
        )

        # Peak hour: hour with the most entries today
        peak_hour_row = (
            db.query(
                extract("hour", Visit.entry_time).label("hr"),
                func.count().label("cnt"),
            )
            .filter(
                Visit.entry_time.isnot(None),
                Visit.entry_time.between(day_start, day_end),
            )
            .group_by("hr")
            .order_by(func.count().desc())
            .first()
        )
        peak_hour = (
            {"hour": int(peak_hour_row.hr), "count": peak_hour_row.cnt}
            if peak_hour_row
            else None
        )

        # Port capacity: total dock bays in the system
        port_capacity = db.query(func.count()).select_from(Dock).scalar() or 1

        # Congestion rate: trucks currently inside vs available dock capacity
        congestion_rate = round(
            min(100.0, trucks_in_port / port_capacity * 100), 1
        )

        # Vehicles per hour: total movements / elapsed hours today
        now_utc = datetime.now(timezone.utc)
        elapsed_hours = max(
            (now_utc - day_start).total_seconds() / 3600, 1.0
        )
        vehicles_per_hour = round(
            (entries_count + exits_count) / elapsed_hours, 1
        )

        return {
            "trucksInPort": trucks_in_port,
            "trucksInTransit": in_transit_count,
            "scheduledCount": scheduled_count,
            "unloadingCount": unloading_count,
            "completedCount": completed_count,
            "entriesCount": entries_count,
            "exitsCount": exits_count,
            "avgPermanenceMinutes": avg_permanence,
            "avgWaitingMinutes": avg_waiting,
            "delayRate": delay_rate,
            "slaCompliance": sla_compliance,
            "infractionCount": infraction_count,
            "peakHour": peak_hour,
            "portCapacity": port_capacity,
            "congestionRate": congestion_rate,
            "vehiclesPerHour": vehicles_per_hour,
        }
    except Exception as e:
        logger.error("get_dashboard_summary failed: %s", e)
        return {
            "trucksInPort": 0,
            "trucksInTransit": 0,
            "scheduledCount": 0,
            "unloadingCount": 0,
            "completedCount": 0,
            "entriesCount": 0,
            "exitsCount": 0,
            "avgPermanenceMinutes": 0,
            "avgWaitingMinutes": 0,
            "delayRate": 0,
            "slaCompliance": 100,
            "infractionCount": 0,
            "peakHour": None,
            "portCapacity": 0,
            "congestionRate": 0,
            "vehiclesPerHour": 0,
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


# ---------------------------------------------------------------------------
# 5. GET /statistics/decision-analytics (MongoDB)
# ---------------------------------------------------------------------------

def get_decision_analytics(
    target_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Decision analytics from MongoDB decision_events collection.
    Returns:
        { totalDecisions, accepted, rejected, manualReview,
          acceptanceRate, avgPipelineMs, avgDetectionToDecisionMs }
    """
    from infrastructure.persistence.mongo import decision_events_collection

    day_start, day_end = _today_range(target_date)

    try:
        pipeline = [
            {"$match": {"created_at": {"$gte": day_start, "$lte": day_end}}},
            {
                "$group": {
                    "_id": None,
                    "totalDecisions": {"$sum": 1},
                    "accepted": {
                        "$sum": {
                            "$cond": [
                                {"$eq": ["$final_decision", "ACCEPTED"]},
                                1,
                                0,
                            ]
                        }
                    },
                    "rejected": {
                        "$sum": {
                            "$cond": [
                                {"$eq": ["$final_decision", "REJECTED"]},
                                1,
                                0,
                            ]
                        }
                    },
                    "manualReview": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$eq": [
                                        "$decision_engine.decision",
                                        "MANUAL_REVIEW",
                                    ]
                                },
                                1,
                                0,
                            ]
                        }
                    },
                    "avgPipelineMs": {
                        "$avg": "$timing.total_pipeline_ms"
                    },
                    "avgDetectionToDecisionMs": {
                        "$avg": "$timing.detection_to_decision_ms"
                    },
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "totalDecisions": 1,
                    "accepted": 1,
                    "rejected": 1,
                    "manualReview": 1,
                    "acceptanceRate": {
                        "$cond": [
                            {"$eq": ["$totalDecisions", 0]},
                            0,
                            {
                                "$round": [
                                    {
                                        "$multiply": [
                                            {
                                                "$divide": [
                                                    "$accepted",
                                                    "$totalDecisions",
                                                ]
                                            },
                                            100,
                                        ]
                                    },
                                    1,
                                ]
                            },
                        ]
                    },
                    "avgPipelineMs": {"$round": ["$avgPipelineMs", 0]},
                    "avgDetectionToDecisionMs": {
                        "$round": ["$avgDetectionToDecisionMs", 0]
                    },
                }
            },
        ]

        result = list(decision_events_collection.aggregate(pipeline))
        if result:
            return result[0]
        return {
            "totalDecisions": 0,
            "accepted": 0,
            "rejected": 0,
            "manualReview": 0,
            "acceptanceRate": 0,
            "avgPipelineMs": 0,
            "avgDetectionToDecisionMs": 0,
        }
    except Exception as e:
        logger.error("get_decision_analytics failed: %s", e)
        return {
            "totalDecisions": 0,
            "accepted": 0,
            "rejected": 0,
            "manualReview": 0,
            "acceptanceRate": 0,
            "avgPipelineMs": 0,
            "avgDetectionToDecisionMs": 0,
        }
