"""
Statistics Routes (API Gateway Proxy)
Proxies requests to the Data Module statistics endpoints.
Also provides a manager-focused dashboard endpoint using arrivals data.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Query, Path

from clients import internal_api_client as internal_client

logger = logging.getLogger(__name__)
router = APIRouter(tags=["statistics"])


# ==================== MANAGER DASHBOARD ====================

@router.get("/statistics/summary")
async def manager_dashboard_summary(
    date: Optional[str] = Query(None, description="Date (YYYY-MM-DD)"),
):
    """
    Combined summary for manager dashboard.
    Proxies to Data Module /statistics/summary which now returns enriched data:
      { trucksInPort, trucksInTransit, scheduledCount, unloadingCount,
        completedCount, entriesCount, exitsCount,
        avgPermanenceMinutes, avgWaitingMinutes,
        delayRate, slaCompliance, infractionCount, peakHour }
    """
    params = {}
    if date:
        params["date"] = date

    try:
        result = await internal_client.get("/statistics/summary", params=params)
        return result if isinstance(result, dict) else {}
    except Exception as e:
        logger.warning("Failed to fetch dashboard summary: %s", e)
        return {}


@router.get("/statistics/decision-analytics")
async def decision_analytics_proxy(
    date: Optional[str] = Query(None, description="Date (YYYY-MM-DD)"),
):
    """
    Proxy to Data Module: decision analytics from MongoDB.
    Returns acceptance rate, pipeline performance, etc.
    """
    params = {}
    if date:
        params["date"] = date

    try:
        result = await internal_client.get("/statistics/decision-analytics", params=params)
        return result if isinstance(result, dict) else {}
    except Exception as e:
        logger.warning("Failed to fetch decision analytics: %s", e)
        return {}


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
