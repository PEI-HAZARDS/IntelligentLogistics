from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional
import os

import jwt as _jwt
from fastapi import APIRouter, Query, Path, Depends, Body, HTTPException, status
from pydantic import BaseModel
from loguru import logger

from clients import internal_api_client as internal_client
from auth.token_validator import require_role, get_current_user, TokenPayload
from dependencies import get_ws_manager
from web_socket_manager import WebSocketManager

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


def _normalize_license(drivers_license: str | None) -> str:
    return (drivers_license or "").strip().upper()


def _ensure_driver_self_or_manager(drivers_license: str, current_user: TokenPayload) -> None:
    """Allow managers to access any driver, but drivers only their own data."""
    if "manager" in current_user.roles:
        return

    if "driver" in current_user.roles and _normalize_license(current_user.sub) == _normalize_license(drivers_license):
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Drivers can only access their own data",
    )


async def _get_owned_appointment(appointment_id: int, current_user: TokenPayload) -> dict:
    """Fetch an appointment and ensure the authenticated driver owns it."""
    appointment = await internal_client.get(f"/arrivals/{appointment_id}")
    if not isinstance(appointment, dict):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Invalid appointment response")

    driver_license = appointment.get("driver_license")
    if _normalize_license(driver_license) != _normalize_license(current_user.sub):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Drivers can only update their own appointments",
        )

    return appointment


# ---------------------------------
# Models
# ---------------------------------
class ClaimAppointmentRequest(BaseModel):
    """Request to claim appointment by PIN."""
    arrival_id: str
    booking_reference: str


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
    drv_license = current_user.sub.upper()
    params = {"drivers_license": drv_license}
    if debug:
        params["debug"] = True
    return await internal_client.post("/drivers/claim", json=claim_data.model_dump(), params=params, headers=_dm_auth(drv_license))


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
    current_user: Annotated[TokenPayload, Depends(require_role("driver", "manager"))],
):
    """
    Proxy to GET /api/v1/drivers/{drivers_license}
    """
    _ensure_driver_self_or_manager(drivers_license, current_user)
    return await internal_client.get(f"/drivers/{drivers_license}")


# ---------------------------------
# GET: /api/drivers/{drivers_license}/arrivals
# ---------------------------------
@router.get("/drivers/{drivers_license}/arrivals")
async def get_arrivals_for_driver(
    drivers_license: Annotated[str, Path(description="Driver's License")],
    current_user: Annotated[TokenPayload, Depends(require_role("driver", "manager"))],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    """
    Proxy to GET /api/v1/drivers/{drivers_license}/arrivals
    """
    _ensure_driver_self_or_manager(drivers_license, current_user)
    path = f"/drivers/{drivers_license}/arrivals"
    params = {"limit": limit}
    return await internal_client.get(path, params=params)


# ---------------------------------
# PATCH: /api/drivers/appointments/{appointment_id}/status
# ---------------------------------
class DriverAppointmentStatusUpdate(BaseModel):
    status: str
    notes: Optional[str] = None

@router.patch("/drivers/appointments/{appointment_id}/status")
async def update_driver_appointment_status(
    appointment_id: Annotated[int, Path(description="Appointment ID")],
    update_data: Annotated[DriverAppointmentStatusUpdate, Body()],
    current_user: Annotated[TokenPayload, Depends(require_role("driver"))],
    ws_manager: Annotated[WebSocketManager, Depends(get_ws_manager)],
):
    """
    Update appointment status and broadcast status_changed via WebSocket.
    Allows drivers to update their own appointments.
    """
    await _get_owned_appointment(appointment_id, current_user)
    result = await internal_client.patch(
        f"/arrivals/{appointment_id}/status",
        json=update_data.model_dump(exclude_none=True)
    )
    ws_payload = {
        "message_type": "status_changed",
        "appointment_id": appointment_id,
        "new_status": update_data.status,
    }

    # Broadcast to the gate so operator UIs update instantly
    gate_in_id = result.get("gate_in_id") if isinstance(result, dict) else None
    if gate_in_id:
        try:
            await ws_manager.broadcast(str(gate_in_id), ws_payload)
            logger.info(f"Broadcast status_changed for appointment {appointment_id} → gate {gate_in_id}")
        except Exception as e:
            logger.warning(f"WS gate broadcast failed for status_changed: {e}")

    # Broadcast directly to the driver's mobile app
    driver_license = result.get("driver_license") if isinstance(result, dict) else None
    if driver_license:
        try:
            await ws_manager.broadcast_to_driver(driver_license, ws_payload)
            logger.info(f"Broadcast status_changed for appointment {appointment_id} → driver {driver_license}")
        except Exception as e:
            logger.warning(f"WS driver broadcast failed for status_changed: {e}")

    return result


# ---------------------------------
# PATCH: /api/drivers/appointments/{appointment_id}/visit
# ---------------------------------
class DriverVisitStateUpdate(BaseModel):
    state: str
    out_time: Optional[str] = None

@router.patch("/drivers/appointments/{appointment_id}/visit")
async def update_driver_visit_state(
    appointment_id: Annotated[int, Path(description="Appointment ID")],
    update_data: Annotated[DriverVisitStateUpdate, Body()],
    current_user: Annotated[TokenPayload, Depends(require_role("driver"))],
    ws_manager: Annotated[WebSocketManager, Depends(get_ws_manager)],
):
    """
    Update visit state (e.g. 'unloading', 'completed') and broadcast via WebSocket.
    Allows drivers to signal unloading start / completion at the dock.
    """
    appointment = await _get_owned_appointment(appointment_id, current_user)
    result = await internal_client.patch(
        f"/arrivals/{appointment_id}/visit",
        json=update_data.model_dump(exclude_none=True)
    )
    ws_payload = {
        "message_type": "status_changed",
        "appointment_id": appointment_id,
        "new_status": update_data.state,
    }

    gate_in_id = result.get("appointment_id") if isinstance(result, dict) else None
    # visit response has appointment_id; fetch gate from result if available
    try:
        appt_result = appointment
        gate_in_id = appt_result.get("gate_in_id") if isinstance(appt_result, dict) else None
        driver_license = appt_result.get("driver_license") if isinstance(appt_result, dict) else None
    except Exception:
        gate_in_id = None
        driver_license = None

    if gate_in_id:
        try:
            await ws_manager.broadcast(str(gate_in_id), ws_payload)
        except Exception as e:
            logger.warning(f"WS gate broadcast failed for visit state change: {e}")

    if driver_license:
        try:
            await ws_manager.broadcast_to_driver(driver_license, ws_payload)
        except Exception as e:
            logger.warning(f"WS driver broadcast failed for visit state change: {e}")

    return result
