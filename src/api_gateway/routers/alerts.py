from fastapi import APIRouter, Query, Path
from typing import Optional, Dict, Any, List
from pydantic import BaseModel

from ..clients import internal_api_client as internal_client

router = APIRouter(tags=["alerts"])


# ---------------------------------
# GET: /api/alerts
# ---------------------------------
@router.get("/alerts")
async def list_alerts(
    severity: Optional[int] = Query(default=None, ge=1, le=5, alias="severidade"),
    limit: int = Query(default=50, ge=1, le=200),
    skip: int = Query(default=0, ge=0),
):
    """
    Proxy to GET /api/v1/alerts.
    Maps 'severidade' query param to 'severity_min'.
    """
    params = {
        "skip": skip,
        "limit": limit
    }
    if severity is not None:
        params["severity_min"] = severity

    return await internal_client.get("/alerts", params=params)


# ---------------------------------
# GET: /api/alerts/{alert_id}
# ---------------------------------
@router.get("/alerts/{alert_id}")
async def get_alert(alert_id: int):
    """
    Proxy to GET /api/v1/alerts/{alert_id}
    """
    path = f"/alerts/{alert_id}"
    return await internal_client.get(path)


# ---------------------------------
# GET: /api/alerts/active
# ---------------------------------
@router.get("/alerts/active")
async def list_active_alerts(
    limit: int = Query(50, ge=1, le=200),
):
    """
    Proxy to GET /api/v1/alerts/active
    """
    params = {"limit": limit}
    return await internal_client.get("/alerts/active", params=params)


# ---------------------------------
# GET: /api/alerts/stats
# ---------------------------------
@router.get("/alerts/stats")
async def get_alerts_stats():
    """
    Proxy to GET /api/v1/alerts/stats
    """
    return await internal_client.get("/alerts/stats")
