"""
Statistics Routes (API Gateway Proxy)
Proxies requests to the Data Module statistics endpoints.
Also provides a manager-focused dashboard endpoint using arrivals data.
"""

import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, Query, Path

from clients import internal_api_client as internal_client

logger = logging.getLogger(__name__)
router = APIRouter(tags=["statistics"])


# ==================== MANAGER DASHBOARD ====================

@router.get("/statistics/summary")
async def manager_dashboard_summary(
    gate_id: Optional[int] = Query(None, description="Gate identifier (omit for all gates)"),
    date: Optional[str] = Query(None, description="Date (YYYY-MM-DD)"),
):
    """
    Combined summary for manager dashboard.
    Aggregates arrivals stats + real-time metrics into the shape
    that the frontend DashboardSummary interface expects:
      { totalTrucks, entriesCount, exitsCount, avgPermanenceMinutes, delayRate, slaCompliance }
    """

    # Fetch arrivals stats (counts by status) + permanence in parallel
    arrivals_params: dict = {}
    if gate_id is not None:
        arrivals_params["gate_id"] = gate_id
    if date:
        arrivals_params["target_date"] = date

    async def _noop():
        return {}

    # Realtime endpoint requires a gate_id; skip it when querying all gates
    arrivals_stats, realtime, permanence = await asyncio.gather(
        internal_client.get("/arrivals/stats", params=arrivals_params),
        internal_client.get(f"/statistics/realtime/{gate_id}") if gate_id else _noop(),
        internal_client.get("/arrivals/avg-permanence", params=arrivals_params),
        return_exceptions=True,
    )

    # Log silenced exceptions for debugging
    if isinstance(arrivals_stats, Exception):
        logger.warning("Failed to fetch arrivals stats: %s", arrivals_stats)
    if isinstance(realtime, Exception):
        logger.warning("Failed to fetch realtime metrics: %s", realtime)
    if isinstance(permanence, Exception):
        logger.warning("Failed to fetch avg permanence: %s", permanence)

    # Parse arrivals stats (Dict[str, int] of status -> count)
    stats = arrivals_stats if isinstance(arrivals_stats, dict) else {}
    in_transit = stats.get("in_transit", 0)
    in_process = stats.get("in_process", 0)
    completed = stats.get("completed", 0)
    delayed = stats.get("delayed", 0)

    total_arrivals = in_transit + in_process + completed + delayed
    entries_count = in_transit + in_process + completed + delayed
    exits_count = completed

    # Compute derived metrics
    delay_rate = (delayed / total_arrivals * 100) if total_arrivals > 0 else 0
    sla_compliance = ((total_arrivals - delayed) / total_arrivals * 100) if total_arrivals > 0 else 100

    # Get real avg permanence from visit timestamps
    avg_permanence = 45  # fallback
    if isinstance(permanence, dict):
        avg_permanence = permanence.get("avgPermanenceMinutes", 45)

    return {
        "totalTrucks": in_transit + in_process,
        "entriesCount": entries_count,
        "exitsCount": exits_count,
        "avgPermanenceMinutes": avg_permanence,
        "delayRate": round(delay_rate, 1),
        "slaCompliance": round(sla_compliance, 1),
    }


@router.get("/statistics/by-company")
async def transport_stats_proxy(
    from_date: Optional[str] = Query(None, alias="from", description="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, alias="to", description="End date (YYYY-MM-DD)"),
):
    """Proxy to Data Module: per-company transport stats."""
    params = {}
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date
    return await internal_client.get("/statistics/by-company", params=params)


@router.get("/statistics/volume")
async def volume_data(
    interval: str = Query("hour", description="Aggregation interval"),
    from_date: Optional[str] = Query(None, alias="from", description="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, alias="to", description="End date (YYYY-MM-DD)"),
):
    """
    Proxy to Data Module /statistics/volume.
    Returns real Visit entry/exit data as VolumeDataPoint[]:
      { timestamp, entries, exits }
    """
    try:
        params = {"interval": interval}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        result = await internal_client.get("/statistics/volume", params=params)
        return result if isinstance(result, list) else []
    except Exception:
        return []


@router.get("/statistics/alerts")
async def alerts_breakdown(
    from_date: Optional[str] = Query(None, alias="from", description="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, alias="to", description="End date (YYYY-MM-DD)"),
):
    """
    Proxy alerts stats and reshape as AlertsBreakdown[]:
      { type, count, percentage }
    """
    try:
        params = {}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        stats = await internal_client.get("/alerts/stats", params=params)
        if isinstance(stats, dict):
            total = sum(stats.values()) or 1
            return [
                {
                    "type": alert_type,
                    "count": count,
                    "percentage": round(count / total * 100, 1),
                }
                for alert_type, count in stats.items()
            ]
        return []
    except Exception:
        return []


# ==================== AI PIPELINE STATISTICS (PROXY) ====================

@router.get("/statistics/realtime/{gate_id}")
async def realtime_metrics(gate_id: int = Path(...)):
    """Proxy to Data Module: real-time metrics for a gate."""
    return await internal_client.get(f"/statistics/realtime/{gate_id}")


@router.get("/statistics/trend/{gate_id}/{metric}")
async def metric_trend(
    gate_id: int = Path(...),
    metric: str = Path(...),
    hours: int = Query(24, ge=1, le=168),
):
    """Proxy to Data Module: hourly trend for a specific metric."""
    return await internal_client.get(
        f"/statistics/trend/{gate_id}/{metric}",
        params={"hours": hours}
    )


@router.get("/statistics/dashboard/summary")
async def full_dashboard_summary(
    gate_id: int = Query(..., description="Gate identifier"),
):
    """Proxy to Data Module: comprehensive AI pipeline dashboard summary."""
    return await internal_client.get(
        "/statistics/dashboard/summary",
        params={"gate_id": gate_id}
    )


@router.get("/statistics/pipeline/performance")
async def pipeline_performance(
    gate_id: int = Query(...),
    hours: int = Query(24, ge=1, le=168),
):
    """Proxy to Data Module: decision pipeline performance."""
    return await internal_client.get(
        "/statistics/pipeline/performance",
        params={"gate_id": gate_id, "hours": hours}
    )


@router.get("/statistics/detections/success-rate")
async def detection_success_rate(
    gate_id: int = Query(...),
    hours: int = Query(24, ge=1, le=168),
):
    """Proxy to Data Module: detection success rate by agent."""
    return await internal_client.get(
        "/statistics/detections/success-rate",
        params={"gate_id": gate_id, "hours": hours}
    )


@router.get("/statistics/operators/performance")
async def operator_performance(
    hours: int = Query(24, ge=1, le=168),
):
    """Proxy to Data Module: operator manual review performance."""
    return await internal_client.get(
        "/statistics/operators/performance",
        params={"hours": hours}
    )
