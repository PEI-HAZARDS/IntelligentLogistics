from fastapi import APIRouter, Query, Path
from typing import Optional, Dict, Any, List
from pydantic import BaseModel

from clients import internal_api_client as internal_client

router = APIRouter(tags=["alerts"])


# ===============================
# STATIC/SPECIFIC PATH ROUTES FIRST
# (Must come before /alerts/{alert_id})
# ===============================

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
    """
    params = {
        "skip": skip,
        "limit": limit
    }
    if severity is not None:
        params["severity_min"] = severity

    return await internal_client.get("/alerts", params=params)


# ---------------------------------
# GET: /api/alerts/active
# NOTE: Must be before /alerts/{alert_id}
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
# NOTE: Must be before /alerts/{alert_id}
# ---------------------------------
@router.get("/alerts/stats")
async def get_alerts_stats():
    """
    Proxy to GET /api/v1/alerts/stats
    """
    return await internal_client.get("/alerts/stats")


# ---------------------------------
# GET: /api/alerts/visit/{visit_id}
# NOTE: Must be before /alerts/{alert_id}
# ---------------------------------
@router.get("/alerts/visit/{visit_id}")
async def get_visit_alerts(
    visit_id: int = Path(..., description="Visit ID"),
):
    """
    Get all alerts for a specific visit.
    Proxy to GET /api/v1/alerts/visit/{visit_id}
    """
    return await internal_client.get(f"/alerts/visit/{visit_id}")


# ---------------------------------
# REFERENCE DATA
# NOTE: Must be before /alerts/{alert_id}
# ---------------------------------
@router.get("/alerts/reference/adr-codes")
async def get_adr_codes():
    """
    List ADR/UN codes reference.
    """
    return await internal_client.get("/alerts/reference/adr-codes")


@router.get("/alerts/reference/kemler-codes")
async def get_kemler_codes():
    """
    List Kemler codes reference.
    """
    return await internal_client.get("/alerts/reference/kemler-codes")


# ---------------------------------
# POST: /api/alerts/hazmat
# NOTE: Must be before /alerts/{alert_id} (POST but path is /alerts/hazmat)
# ---------------------------------
class CreateHazmatAlertRequest(BaseModel):
    appointment_id: int
    un_code: Optional[str] = None
    kemler_code: Optional[str] = None
    detected_hazmat: Optional[str] = None


@router.post("/alerts/hazmat")
async def create_hazmat_alert(request: CreateHazmatAlertRequest):
    """
    Create hazmat/ADR specific alert.
    Proxy to POST /api/v1/alerts/hazmat
    """
    return await internal_client.post("/alerts/hazmat", json=request.model_dump(exclude_none=True))


# ---------------------------------
# POST: /api/alerts
# ---------------------------------
class CreateAlertRequest(BaseModel):
    visit_id: Optional[int] = None
    type: str  # generic, safety, problem, operational
    description: str
    image_url: Optional[str] = None


@router.post("/alerts")
async def create_alert(request: CreateAlertRequest):
    """
    Create an alert.
    Proxy to POST /api/v1/alerts
    """
    return await internal_client.post("/alerts", json=request.model_dump(exclude_none=True))


# ===============================
# DYNAMIC PATH ROUTES LAST
# ===============================

# ---------------------------------
# GET: /api/alerts/{alert_id}
# NOTE: This catch-all route MUST BE LAST
# ---------------------------------
@router.get("/alerts/{alert_id}")
async def get_alert(alert_id: int):
    """
    Proxy to GET /api/v1/alerts/{alert_id}
    """
    return await internal_client.get(f"/alerts/{alert_id}")
