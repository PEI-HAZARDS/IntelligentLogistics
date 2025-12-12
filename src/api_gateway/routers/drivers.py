from fastapi import APIRouter, Query, Path
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

from clients import internal_api_client as internal_client

router = APIRouter(tags=["drivers"])


# ---------------------------------
# GET: /api/drivers
# ---------------------------------
@router.get("/drivers")
async def list_drivers(
    limit: int = Query(default=100, ge=1, le=500),
    skip: int = Query(default=0, ge=0),
):
    """
    Proxy to GET /api/v1/drivers in Data Module.
    """
    params = {
        "skip": skip,
        "limit": limit
    }
    return await internal_client.get("/drivers", params=params)


# ---------------------------------
# GET: /api/drivers/{drivers_license}
# ---------------------------------
@router.get("/drivers/{drivers_license}")
async def get_driver(
    drivers_license: str = Path(..., description="Driver's License"),
):
    """
    Proxy to GET /api/v1/drivers/{drivers_license}
    """
    # URL encode if necessary, but requests handles it usually
    return await internal_client.get(f"/drivers/{drivers_license}")


# ---------------------------------
# GET: /api/drivers/{drivers_license}/arrivals
# ---------------------------------
@router.get("/drivers/{drivers_license}/arrivals")
async def get_arrivals_for_driver(
    drivers_license: str = Path(..., description="Driver's License"),
    limit: int = Query(default=50, ge=1, le=200),
):
    """
    Proxy to GET /api/v1/drivers/{drivers_license}/arrivals
    """
    path = f"/drivers/{drivers_license}/arrivals"
    params = {"limit": limit}
    return await internal_client.get(path, params=params)


# ---------------------------------
# AUTH ENDPOINTS (Mobile App)
# ---------------------------------

class DriverLoginRequest(BaseModel):
    """Driver login credentials."""
    drivers_license: str
    password: str


class ClaimAppointmentRequest(BaseModel):
    """Request to claim appointment by PIN."""
    arrival_id: str


@router.post("/drivers/login")
async def driver_login(credentials: DriverLoginRequest):
    """
    Driver login for mobile app.
    Proxy to POST /api/v1/drivers/login
    """
    return await internal_client.post("/drivers/login", json=credentials.model_dump())


@router.post("/drivers/claim")
async def claim_appointment(
    claim_data: ClaimAppointmentRequest,
    drivers_license: str = Query(..., description="Driver's license"),
):
    """
    Driver claims appointment by PIN.
    Proxy to POST /api/v1/drivers/claim
    """
    params = {"drivers_license": drivers_license}
    return await internal_client.post("/drivers/claim", json=claim_data.model_dump(), params=params)


@router.get("/drivers/me/active")
async def get_my_active_arrival(
    drivers_license: str = Query(..., description="Driver's license"),
):
    """
    Get driver's active appointment.
    Proxy to GET /api/v1/drivers/me/active
    """
    params = {"drivers_license": drivers_license}
    return await internal_client.get("/drivers/me/active", params=params)


@router.get("/drivers/me/today")
async def get_my_today_arrivals(
    drivers_license: str = Query(..., description="Driver's license"),
):
    """
    Get driver's today appointments.
    Proxy to GET /api/v1/drivers/me/today
    """
    params = {"drivers_license": drivers_license}
    return await internal_client.get("/drivers/me/today", params=params)

