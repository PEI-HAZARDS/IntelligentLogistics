"""
Statistics Routes - Endpoints for analytics and metrics.
Consumed by: Dashboards, Monitoring systems, Operators.
"""

from typing import Annotated, Optional
from fastapi import APIRouter, Query, HTTPException, status
from datetime import datetime

from application.queries.statistics_queries import (
    get_real_time_metrics,
    get_hourly_trend,
    get_detection_success_rate,
    get_decision_pipeline_performance,
    get_agent_performance,
    get_complete_truck_journey,
    get_operator_performance,
    compute_hourly_statistics,
)
from application.queries.manager_statistics_queries import (
    get_dashboard_summary,
    get_transport_stats,
    get_volume_data,
    get_alerts_breakdown,
    get_decision_analytics,
)

router = APIRouter(prefix="/statistics", tags=["Statistics & Analytics"])


# ==================== MANAGER DASHBOARD (frontend contract) ====================

@router.get("/summary")
def dashboard_summary_for_manager(
    date: Annotated[Optional[str], Query(description="ISO date (YYYY-MM-DD), defaults to today")] = None,
):
    """
    Dashboard summary consumed by the Logistics Manager frontend.

    **Response shape** (matches statistics.ts DashboardSummary):
    ```json
    { "trucksInPort", "trucksInTransit", "scheduledCount", "unloadingCount",
      "completedCount", "entriesCount", "exitsCount",
      "avgPermanenceMinutes", "avgWaitingMinutes",
      "delayRate", "slaCompliance", "infractionCount", "peakHour" }
    ```
    """
    return get_dashboard_summary(date)


@router.get("/by-company")
def transport_stats_by_company(
    from_date: Annotated[Optional[str], Query(alias="from", description="Start date (YYYY-MM-DD)")] = None,
    to_date: Annotated[Optional[str], Query(alias="to", description="End date (YYYY-MM-DD)")] = None,
):
    """
    Per-company transport statistics consumed by the Logistics Manager frontend.

    **Response shape** (matches statistics.ts TransportStats[]):
    ```json
    [{ "companyName", "companyNif", "avgUnloadingTime",
       "avgWaitingTime", "operationsCount", "slaAttendedRate" }]
    ```
    """
    return get_transport_stats(from_date, to_date)


@router.get("/volume")
def volume_time_series(
    from_date: Annotated[Optional[str], Query(alias="from", description="Start date (YYYY-MM-DD)")] = None,
    to_date: Annotated[Optional[str], Query(alias="to", description="End date (YYYY-MM-DD)")] = None,
    interval: Annotated[str, Query(description="Bucket size: hour | day | week")] = "hour",
):
    """
    Volume time-series data consumed by the Logistics Manager frontend.

    **Response shape** (matches statistics.ts VolumeDataPoint[]):
    ```json
    [{ "timestamp", "entries", "exits" }]
    ```
    """
    if interval not in ("hour", "day", "week"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="interval must be one of: hour, day, week",
        )
    return get_volume_data(from_date, to_date, interval)


@router.get("/alerts")
def alerts_breakdown(
    from_date: Annotated[Optional[str], Query(alias="from", description="Start date (YYYY-MM-DD)")] = None,
    to_date: Annotated[Optional[str], Query(alias="to", description="End date (YYYY-MM-DD)")] = None,
):
    """
    Alerts breakdown by type consumed by the Logistics Manager frontend.

    **Response shape** (matches statistics.ts AlertsBreakdown[]):
    ```json
    [{ "type", "count", "percentage" }]
    ```
    """
    return get_alerts_breakdown(from_date, to_date)


@router.get("/decision-analytics")
def decision_analytics(
    date: Annotated[Optional[str], Query(description="ISO date (YYYY-MM-DD), defaults to today")] = None,
):
    """
    Decision analytics from MongoDB decision_events collection.

    **Response shape** (matches statistics.ts DecisionAnalytics):
    ```json
    { "totalDecisions", "accepted", "rejected", "manualReview",
      "acceptanceRate", "avgPipelineMs", "avgDetectionToDecisionMs" }
    ```
    """
    return get_decision_analytics(date)


# ==================== REAL-TIME METRICS ====================

@router.get("/realtime/{gate_id}")
def get_realtime_metrics(gate_id: int):
    """
    Get current hour real-time metrics for a gate.

    **Returns:**
    - Detection counts (total, by agent)
    - Decision counts (accepted, rejected, manual_review)
    - Operator activity
    - Error counts

    **Example:**
    ```
    GET /api/v1/statistics/realtime/1
    ```
    """
    try:
        metrics = get_real_time_metrics(gate_id)
        if not metrics:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No real-time metrics found for gate {gate_id}"
            )
        return metrics
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get real-time metrics: {str(e)}"
        )


@router.get("/trend/{gate_id}/{metric}")
def get_metric_trend(
    gate_id: int,
    metric: str,
    hours: Annotated[int, Query(ge=1, le=168, description="Hours to look back (1-168)")] = 24,
):
    """
    Get hourly trend for a specific metric.

    **Metrics:**
    - `detections` - Total detections
    - `detections:agent_a` - Agent A detections
    - `detections:agent_b` - Agent B detections
    - `detections:agent_c` - Agent C detections
    - `decisions:accepted` - Accepted decisions
    - `decisions:rejected` - Rejected decisions
    - `decisions:manual_review` - Manual review decisions

    **Example:**
    ```
    GET /api/v1/statistics/trend/1/detections?hours=48
    ```
    """
    try:
        trend = get_hourly_trend(gate_id, metric, hours)
        return {
            "gate_id": gate_id,
            "metric": metric,
            "hours": hours,
            "data": trend
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get trend: {str(e)}"
        )


# ==================== AGGREGATED ANALYTICS ====================

@router.get("/detections/success-rate")
def detection_success_rate(
    gate_id: Annotated[int, Query(description="Gate identifier")],
    hours: Annotated[int, Query(ge=1, le=168, description="Hours to analyze")] = 24,
):
    """
    Get detection success rate by agent over time.

    **Returns:**
    - Total detections per agent per hour
    - Average confidence per agent
    - Processing rate (detections consumed by Decision Engine)

    **Example:**
    ```
    GET /api/v1/statistics/detections/success-rate?gate_id=1&hours=24
    ```
    """
    try:
        stats = get_detection_success_rate(gate_id, hours)
        return {
            "gate_id": gate_id,
            "hours_analyzed": hours,
            "results": stats
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get detection success rate: {str(e)}"
        )


@router.get("/pipeline/performance")
def pipeline_performance(
    gate_id: Annotated[int, Query(description="Gate identifier")],
    hours: Annotated[int, Query(ge=1, le=168, description="Hours to analyze")] = 24,
):
    """
    Analyze decision pipeline performance.

    **Returns:**
    - Total decisions
    - Decisions by type (accepted, rejected, manual_review)
    - Acceptance rate
    - Manual review rate
    - Performance metrics (avg, p50, p95, p99 latency)

    **Example:**
    ```
    GET /api/v1/statistics/pipeline/performance?gate_id=1&hours=24
    ```
    """
    try:
        stats = get_decision_pipeline_performance(gate_id, hours)
        if not stats:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No pipeline performance data found for gate {gate_id}"
            )
        return {
            "gate_id": gate_id,
            "hours_analyzed": hours,
            **stats
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get pipeline performance: {str(e)}"
        )


@router.get("/agent/{agent_type}/performance")
def agent_performance(
    agent_type: str,
    gate_id: Annotated[int, Query(description="Gate identifier")],
    hours: Annotated[int, Query(ge=1, le=168, description="Hours to analyze")] = 24,
):
    """
    Analyze individual agent performance.

    **Agent Types:**
    - `AgentA` - Truck detection
    - `AgentB` - License plate detection
    - `AgentC` - Hazmat detection

    **Returns:**
    - Total detections
    - Confidence statistics (avg, min, max)
    - Processing rate
    - Average latency

    **Example:**
    ```
    GET /api/v1/statistics/agent/AgentB/performance?gate_id=1&hours=24
    ```
    """
    if agent_type not in ["AgentA", "AgentB", "AgentC"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid agent_type. Must be AgentA, AgentB, or AgentC"
        )

    try:
        stats = get_agent_performance(agent_type, gate_id, hours)
        if not stats:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No performance data found for {agent_type} at gate {gate_id}"
            )
        return {
            "hours_analyzed": hours,
            **stats
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get agent performance: {str(e)}"
        )


@router.get("/operators/performance")
def operator_performance(
    hours: Annotated[int, Query(ge=1, le=168, description="Hours to analyze")] = 24,
):
    """
    Analyze operator manual review performance.

    **Returns:**
    - List of operators with:
      - Total reviews handled
      - Average review time
      - Override rate (% of decisions changed)

    **Example:**
    ```
    GET /api/v1/statistics/operators/performance?hours=24
    ```
    """
    try:
        stats = get_operator_performance(hours)
        return {
            "hours_analyzed": hours,
            "operators": stats
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get operator performance: {str(e)}"
        )


# ==================== TRUCK JOURNEY ====================

@router.get("/truck/{truck_id}/journey")
def truck_journey(truck_id: str):
    """
    Get complete journey for a truck from detection to decision.

    **Returns:**
    - All agent detections (chronological)
    - Decision event (if exists)
    - Timeline with key timestamps

    **Example:**
    ```
    GET /api/v1/statistics/truck/TRUCK-12345/journey
    ```
    """
    try:
        journey = get_complete_truck_journey(truck_id)
        if "error" in journey:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=journey["error"]
            )
        return journey
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get truck journey: {str(e)}"
        )


# ==================== BACKGROUND JOBS (ADMIN) ====================

@router.post("/compute/hourly/{gate_id}")
def trigger_hourly_computation(
    gate_id: int,
    hour_timestamp: Annotated[Optional[str], Query(description="ISO format hour (YYYY-MM-DDTHH:00:00Z)")] = None,
):
    """
    Manually trigger hourly statistics computation.

    **Note:** Normally runs automatically every hour via background job.

    **Example:**
    ```
    POST /api/v1/statistics/compute/hourly/1?hour_timestamp=2025-02-16T10:00:00Z
    ```
    """
    try:
        hour_dt = None
        if hour_timestamp:
            hour_dt = datetime.fromisoformat(hour_timestamp.replace('Z', '+00:00'))

        result = compute_hourly_statistics(gate_id, hour_dt)

        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to compute hourly statistics"
            )

        return {
            "status": "computed",
            "gate_id": gate_id,
            "hour_bucket": result["hour_bucket"].isoformat(),
            "computed_at": result["computed_at"].isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger computation: {str(e)}"
        )


# ==================== DASHBOARD SUMMARY ====================

@router.get("/dashboard/summary")
def dashboard_summary(
    gate_id: Annotated[int, Query(description="Gate identifier")],
):
    """
    Get comprehensive dashboard summary combining real-time and historical data.

    **Returns:**
    - Current hour real-time metrics
    - Last 24h pipeline performance
    - All agents performance
    - Operator statistics

    **Example:**
    ```
    GET /api/v1/statistics/dashboard/summary?gate_id=1
    ```
    """
    try:
        realtime = get_real_time_metrics(gate_id)
        pipeline = get_decision_pipeline_performance(gate_id, 24)
        agent_a = get_agent_performance("AgentA", gate_id, 24)
        agent_b = get_agent_performance("AgentB", gate_id, 24)
        agent_c = get_agent_performance("AgentC", gate_id, 24)
        operators = get_operator_performance(24)

        return {
            "gate_id": gate_id,
            "generated_at": datetime.utcnow().isoformat(),
            "realtime": realtime,
            "pipeline_24h": pipeline,
            "agents_24h": {
                "AgentA": agent_a,
                "AgentB": agent_b,
                "AgentC": agent_c
            },
            "operators_24h": operators
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate dashboard summary: {str(e)}"
        )
