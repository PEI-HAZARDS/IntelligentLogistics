"""
CQRS read-side queries for workers — reads from MongoDB workers_read
and related collections.  No SQLAlchemy dependency (Guardrail 5).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from infrastructure.persistence.mongo import (
    alerts_read_collection,
    appointments_read_collection,
    workers_read_collection,
)
from infrastructure.persistence.redis import get_all_active_counters

logger = logging.getLogger(__name__)


# ── Worker lists ─────────────────────────────────────────────────


def get_all_workers(
    *,
    skip: int = 0,
    limit: int = 100,
    only_active: bool = True,
) -> List[Dict[str, Any]]:
    query: dict = {}
    if only_active:
        query["active"] = True
    return list(
        workers_read_collection.find(query, {"_id": 0, "password_hash": 0})
        .skip(skip)
        .limit(limit)
    )


def get_operators(*, skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
    return list(
        workers_read_collection.find(
            {"role": "operator"}, {"_id": 0, "password_hash": 0}
        )
        .skip(skip)
        .limit(limit)
    )


def get_managers(*, skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
    return list(
        workers_read_collection.find(
            {"role": "manager"}, {"_id": 0, "password_hash": 0}
        )
        .skip(skip)
        .limit(limit)
    )


# ── Single worker ────────────────────────────────────────────────


def get_worker_by_num(num_worker: str) -> Optional[Dict[str, Any]]:
    return workers_read_collection.find_one(
        {"num_worker": num_worker}, {"_id": 0, "password_hash": 0}
    )


def get_operator_info(num_worker: str) -> Optional[Dict[str, Any]]:
    w = workers_read_collection.find_one(
        {"num_worker": num_worker, "role": "operator"},
        {"_id": 0, "password_hash": 0},
    )
    return w


def get_manager_info(num_worker: str) -> Optional[Dict[str, Any]]:
    return workers_read_collection.find_one(
        {"num_worker": num_worker, "role": "manager"},
        {"_id": 0, "password_hash": 0},
    )


# ── Dashboards (CQRS read from MongoDB + Redis) ─────────────────


def get_operator_gate_dashboard(
    num_worker: str,
    gate_id: int,
) -> Dict[str, Any]:
    today_str = date.today().isoformat()

    upcoming = list(
        appointments_read_collection.find(
            {
                "gate_in_id": gate_id,
                "scheduled_start_date": today_str,
                "status": {"$in": ["in_transit", "delayed"]},
            },
            {"_id": 0},
        )
        .sort("scheduled_start_time", 1)
        .limit(10)
    )

    stats_pipeline = [
        {
            "$match": {
                "gate_in_id": gate_id,
                "scheduled_start_date": today_str,
            }
        },
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    stats_raw = appointments_read_collection.aggregate(stats_pipeline)
    stats_dict = {doc["_id"]: doc["count"] for doc in stats_raw}

    return {
        "operator_num_worker": num_worker,
        "gate_id": gate_id,
        "date": today_str,
        "upcoming_arrivals": [
            {
                "appointment_id": a.get("id"),
                "license_plate": a.get("truck_license_plate"),
                "scheduled_time": a.get("scheduled_start_time"),
                "terminal_id": a.get("terminal_id"),
                "status": a.get("status"),
            }
            for a in upcoming
        ],
        "stats": {
            "in_transit": stats_dict.get("in_transit", 0),
            "delayed": stats_dict.get("delayed", 0),
            "completed": stats_dict.get("completed", 0),
            "canceled": stats_dict.get("canceled", 0),
        },
    }


def get_manager_overview(num_worker: str) -> Dict[str, Any]:
    today_str = date.today().isoformat()

    # Count distinct gates from today's appointments
    active_gates_pipeline = [
        {"$match": {"scheduled_start_date": today_str}},
        {"$group": {"_id": "$gate_in_id"}},
        {"$count": "total"},
    ]
    gates_result = list(appointments_read_collection.aggregate(active_gates_pipeline))
    active_gates = gates_result[0]["total"] if gates_result else 0

    # Recent alerts count
    cutoff_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    recent_alerts = alerts_read_collection.count_documents(
        {"timestamp": {"$gte": cutoff_24h}}
    )

    # Appointment stats by status today
    stats_pipeline = [
        {"$match": {"scheduled_start_date": today_str}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    stats_raw = appointments_read_collection.aggregate(stats_pipeline)
    statistics = {doc["_id"]: doc["count"] for doc in stats_raw}

    return {
        "manager_num_worker": num_worker,
        "date": today_str,
        "active_gates": active_gates,
        "shifts_today": 0,  # shift data not yet projected to MongoDB
        "recent_alerts": recent_alerts,
        "statistics": statistics,
    }
