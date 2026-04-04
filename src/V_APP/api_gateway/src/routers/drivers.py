from fastapi import APIRouter, Query, Path, Depends
from pydantic import BaseModel

from clients import internal_api_client as internal_client
from auth.token_validator import require_role, get_current_user, TokenPayload

router = APIRouter(tags=["drivers"])


# ---------------------------------
# Models
# ---------------------------------
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
    _user: TokenPayload = Depends(require_role("manager")),
):
    """
    Proxy to GET /api/v1/drivers in Data Module.
    """
    params = {"skip": skip, "limit": limit}
    return await internal_client.get("/drivers", params=params)


# ---------------------------------
# Static routes MUST come before the {drivers_license} catch-all
# to avoid being shadowed by the path parameter.
# ---------------------------------

@router.post("/drivers/claim")
async def claim_appointment(
    claim_data: ClaimAppointmentRequest,
    current_user: TokenPayload = Depends(require_role("driver")),
    debug: bool = Query(False, description="Debug mode - bypass sequential check"),
):
    """
    Driver claims appointment by PIN.
    Returns delivery details for navigation.
    Driver identity extracted from JWT token.
    """
    params = {"drivers_license": current_user.sub.upper()}
    if debug:
        params["debug"] = True
    return await internal_client.post("/drivers/claim", json=claim_data.model_dump(), params=params)


@router.get("/drivers/me/active")
async def get_my_active_arrival(
    current_user: TokenPayload = Depends(require_role("driver")),
):
    """
    Get driver's active appointment.
    Driver identity extracted from JWT token.
    """
    params = {"drivers_license": current_user.sub.upper()}
    return await internal_client.get("/drivers/me/active", params=params)


@router.get("/drivers/me/today")
async def get_my_today_arrivals(
    current_user: TokenPayload = Depends(require_role("driver")),
):
    """
    Get driver's today appointments.
    Driver identity extracted from JWT token.
    """
    params = {"drivers_license": current_user.sub.upper()}
    return await internal_client.get("/drivers/me/today", params=params)


@router.get("/drivers/me/history")
async def get_my_history(
    current_user: TokenPayload = Depends(require_role("driver")),
    limit: int = Query(50, ge=1, le=200),
):
    """
    Get driver's delivery history.
    Driver identity extracted from JWT token.
    """
    params = {"drivers_license": current_user.sub.upper(), "limit": limit}
    return await internal_client.get("/drivers/me/history", params=params)


# ---------------------------------
# GET: /api/drivers/{drivers_license}
# IMPORTANT: catch-all MUST be AFTER all static /drivers/* routes
# ---------------------------------
@router.get("/drivers/{drivers_license}")
async def get_driver(
    drivers_license: str = Path(..., description="Driver's License"),
    _user: TokenPayload = Depends(require_role("driver", "manager")),
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
    _user: TokenPayload = Depends(require_role("driver", "manager")),
):
    """
    Proxy to GET /api/v1/drivers/{drivers_license}/arrivals
    """
    path = f"/drivers/{drivers_license}/arrivals"
    params = {"limit": limit}
    return await internal_client.get(path, params=params)
