from datetime import datetime, timedelta, timezone
from typing import Annotated
import os

import jwt as _jwt
from fastapi import APIRouter, Query, Path, Depends
from pydantic import BaseModel

from clients import internal_api_client as internal_client
from auth.token_validator import require_role, get_current_user, TokenPayload

router = APIRouter(tags=["drivers"])

# DM uses HS256 internal JWT for /me/* routes.  The secret and expiry are
# read from the same env vars the Data Module uses, so they always agree.
_DM_JWT_SECRET: str = os.getenv("DM_JWT_SECRET", "pei-internal-secret-replace-with-keycloak")
_DM_TOKEN_EXPIRY_HOURS: int = int(os.getenv("TOKEN_EXPIRY_HOURS", "24"))


def _dm_driver_jwt(drivers_license: str) -> str:
    """Generate a short-lived DM internal JWT for a driver identity."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": drivers_license,
        "role": "driver",
        "iat": now,
        "exp": now + timedelta(hours=_DM_TOKEN_EXPIRY_HOURS),
    }
    return _jwt.encode(payload, _DM_JWT_SECRET, algorithm="HS256")


def _dm_auth(drivers_license: str) -> dict[str, str]:
    """Return an Authorization header dict for DM /me/* calls."""
    return {"Authorization": f"Bearer {_dm_driver_jwt(drivers_license)}"}


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
    _user: Annotated[TokenPayload, Depends(require_role("manager"))],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    skip: Annotated[int, Query(ge=0)] = 0,
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
    current_user: Annotated[TokenPayload, Depends(require_role("driver"))],
    debug: Annotated[bool, Query(description="Debug mode - bypass sequential check")] = False,
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
    current_user: Annotated[TokenPayload, Depends(require_role("driver"))],
):
    """
    Get driver's active appointment.
    Driver identity extracted from JWT token.
    """
    drv_license = current_user.sub.upper()
    return await internal_client.get("/drivers/me/active", headers=_dm_auth(drv_license))


@router.get("/drivers/me/today")
async def get_my_today_arrivals(
    current_user: Annotated[TokenPayload, Depends(require_role("driver"))],
):
    """
    Get driver's today appointments.
    Driver identity extracted from JWT token.
    """
    drv_license = current_user.sub.upper()
    return await internal_client.get("/drivers/me/today", headers=_dm_auth(drv_license))


@router.get("/drivers/me/history")
async def get_my_history(
    current_user: Annotated[TokenPayload, Depends(require_role("driver"))],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    """
    Get driver's delivery history.
    Driver identity extracted from JWT token.
    """
    drv_license = current_user.sub.upper()
    return await internal_client.get("/drivers/me/history", params={"limit": limit}, headers=_dm_auth(drv_license))


# ---------------------------------
# GET: /api/drivers/{drivers_license}
# IMPORTANT: catch-all MUST be AFTER all static /drivers/* routes
# ---------------------------------
@router.get("/drivers/{drivers_license}")
async def get_driver(
    drivers_license: Annotated[str, Path(description="Driver's License")],
    _user: Annotated[TokenPayload, Depends(require_role("driver", "manager"))],
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
    drivers_license: Annotated[str, Path(description="Driver's License")],
    _user: Annotated[TokenPayload, Depends(require_role("driver", "manager"))],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    """
    Proxy to GET /api/v1/drivers/{drivers_license}/arrivals
    """
    path = f"/drivers/{drivers_license}/arrivals"
    params = {"limit": limit}
    return await internal_client.get(path, params=params)
