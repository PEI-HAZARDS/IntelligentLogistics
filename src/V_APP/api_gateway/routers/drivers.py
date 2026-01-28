from fastapi import APIRouter, Query, Path
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

from clients import internal_api_client as internal_client

router = APIRouter(tags=["drivers"])


# ---------------------------------
# Models
# ---------------------------------
class DriverLoginRequest(BaseModel):
    """Driver login credentials."""
    drivers_license: str
    password: str


class ClaimAppointmentRequest(BaseModel):
    """Request to claim appointment by PIN."""
    arrival_id: str


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
    params = {"skip": skip, "limit": limit}
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

@router.post("/drivers/login")
async def driver_login(credentials: DriverLoginRequest):
    """
    Driver login for mobile app.
    Validates credentials, returns driver info.
    
    Future: Will return JWT token when OAuth 2.0 is implemented.
    """
    return await internal_client.post("/drivers/login", json=credentials.model_dump())


@router.post("/drivers/claim")
async def claim_appointment(
    claim_data: ClaimAppointmentRequest,
    drivers_license: str = Query(..., description="Driver's license"),
    debug: bool = Query(False, description="Debug mode - bypass sequential check"),
):
    """
    Driver claims appointment by PIN.
    Returns delivery details for navigation.
    
    Future: Will require Bearer token when OAuth 2.0 is implemented.
    """
    params = {"drivers_license": drivers_license}
    if debug:
        params["debug"] = True
    return await internal_client.post("/drivers/claim", json=claim_data.model_dump(), params=params)


@router.get("/drivers/me/active")
async def get_my_active_arrival(
    drivers_license: str = Query(..., description="Driver's license"),
):
    """
    Get driver's active appointment.
    
    Future: Will use Bearer token when OAuth 2.0 is implemented.
    """
    params = {"drivers_license": drivers_license}
    return await internal_client.get("/drivers/me/active", params=params)


@router.get("/drivers/me/today")
async def get_my_today_arrivals(
    drivers_license: str = Query(..., description="Driver's license"),
):
    """
    Get driver's today appointments.
    
    Future: Will use Bearer token when OAuth 2.0 is implemented.
    """
    params = {"drivers_license": drivers_license}
    return await internal_client.get("/drivers/me/today", params=params)


@router.get("/drivers/me/history")
async def get_my_history(
    drivers_license: str = Query(..., description="Driver's license"),
    limit: int = Query(50, ge=1, le=200),
):
    """
    Get driver's delivery history.
    
    Future: Will use Bearer token when OAuth 2.0 is implemented.
    """
    params = {"drivers_license": drivers_license, "limit": limit}
    return await internal_client.get("/drivers/me/history", params=params)
