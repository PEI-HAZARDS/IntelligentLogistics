from typing import Annotated, Optional, Dict, Any
from datetime import date

from fastapi import APIRouter, Query, Path, Body, Request, Depends
from pydantic import BaseModel
from loguru import logger

from clients import internal_api_client as internal_client
from dependencies import get_ws_manager
from web_socket_manager import WebSocketManager
from auth.token_validator import require_role, TokenPayload

router = APIRouter(tags=["arrivals"], dependencies=[Depends(require_role("operator", "manager"))])


# ===============================
# STATIC/SPECIFIC PATH ROUTES FIRST
# (Must come before dynamic routes like /arrivals/{gate_id})
# ===============================

# -------------------------------
# GET: /api/arrivals
# -------------------------------
@router.get("/arrivals")
async def list_all_arrivals(
    license_plate: Annotated[Optional[str], Query(alias="matricula")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    status: Annotated[Optional[str], Query(description="Filter by single status")] = None,
    statuses: Annotated[Optional[str], Query(description="Filter by multiple statuses (comma-separated)")] = None,
    scheduled_date: Annotated[Optional[date], Query(description="Filter by scheduled date")] = None,
    gate_id: Annotated[Optional[int], Query(description="Filter by entry gate")] = None,
    search: Annotated[Optional[str], Query(description="Search by license plate or driver name")] = None,
    highway_infraction: Annotated[Optional[bool], Query(description="Filter by highway infraction flag")] = None,
):
    """
    Proxy to GET /api/v1/arrivals in Data Module.
    Supports server-side pagination, filtering and search.
    """
    params = {
        "page": page,
        "limit": limit,
        **{k: v for k, v in {
            "license_plate": license_plate,
            "status": status,
            "statuses": statuses,
            "scheduled_date": scheduled_date.isoformat() if scheduled_date else None,
            "gate_id": gate_id,
            "search": search,
            "highway_infraction": highway_infraction,
        }.items() if v is not None}
    }

    return await internal_client.get("/arrivals", params=params)


# -------------------------------
# GET: /api/arrivals/stats
# NOTE: Must be before /arrivals/{gate_id}
# -------------------------------
@router.get("/arrivals/stats")
async def get_arrivals_stats(
    gate_id: Annotated[Optional[int], Query(description="Filter by gate")] = None,
    target_date: Annotated[Optional[date], Query(description="Date to query")] = None,
):
    """
    Arrival statistics by status.
    Proxy to GET /api/v1/arrivals/stats
    """
    params = {}
    if gate_id is not None:
        params["gate_id"] = gate_id
    if target_date is not None:
        params["target_date"] = target_date.isoformat()
    return await internal_client.get("/arrivals/stats", params=params)


# -------------------------------
# GET: /api/arrivals/next/{gate_id}
# NOTE: Must be before /arrivals/{gate_id}
# -------------------------------
@router.get("/arrivals/next/{gate_id}")
async def get_upcoming_arrivals(
    gate_id: Annotated[int, Path(description="Gate ID")],
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
):
    """
    Next scheduled arrivals for a gate.
    Proxy to GET /api/v1/arrivals/next/{gate_id}
    """
    params = {"limit": limit}
    return await internal_client.get(f"/arrivals/next/{gate_id}", params=params)


# -------------------------------
# GET: /api/arrivals/pin/{arrival_id}
# NOTE: Must be before /arrivals/{gate_id}
# -------------------------------
@router.get("/arrivals/pin/{arrival_id}")
async def get_arrival_by_pin(
    arrival_id: Annotated[str, Path(description="Arrival ID / PIN")],
):
    """
    Get appointment by arrival_id/PIN.
    Proxy to GET /api/v1/arrivals/pin/{arrival_id}
    """
    return await internal_client.get(f"/arrivals/pin/{arrival_id}")


# -------------------------------
# GET: /api/arrivals/detail/{appointment_id}
# NOTE: Must be before /arrivals/{gate_id}
# -------------------------------
@router.get("/arrivals/detail/{appointment_id}")
async def get_arrival_detail(
    appointment_id: Annotated[int, Path(description="Appointment ID")],
):
    """
    Get enriched appointment details by ID (with driver, company, booking, cargo, gates).
    Proxy to GET /api/v1/arrivals/{appointment_id}/detail
    """
    return await internal_client.get(f"/arrivals/{appointment_id}/detail")


# -------------------------------
# GET: /api/arrivals/query/license-plate/{license_plate}
# NOTE: Must be before /arrivals/{gate_id}
# -------------------------------
@router.get("/arrivals/query/license-plate/{license_plate}")
async def query_arrivals_by_license_plate(
    license_plate: Annotated[str, Path(description="License plate to search")],
):
    """
    Query arrivals by license plate.
    Proxy to GET /api/v1/arrivals/query/license-plate/{license_plate}
    """
    return await internal_client.get(f"/arrivals/query/license-plate/{license_plate}")


# ===============================
# DYNAMIC PATH ROUTES
# (These catch-all routes must come LAST)
# ===============================

# -------------------------------
# GET: /api/arrivals/{gate_id}/pending
# NOTE: More specific path, must be before /arrivals/{gate_id}
# NOTE: Returns arrivals pending manual review: status in ['delayed', 'in_transit']
# -------------------------------
@router.get("/arrivals/{gate_id}/pending")
async def list_arrivals_pending(
    gate_id: int,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    """
    Lists pending manual review arrivals (status='delayed' or 'in_transit') by gate.
    Used for manual review queue in operator interface.
    """
    skip = (page - 1) * limit
    params = {
        "skip": skip,
        "limit": limit,
        "gate_id": gate_id,
        "statuses": "delayed,in_transit"
    }
    return await internal_client.get("/arrivals", params=params)


# -------------------------------
# GET: /api/arrivals/{gate_id}/in_progress
# -------------------------------
@router.get("/arrivals/{gate_id}/in_progress")
async def list_arrivals_in_progress(
    gate_id: int,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    """
    Lists in-progress arrivals (status='approved' or 'in_transit').
    """
    skip = (page - 1) * limit
    params = {
        "skip": skip,
        "limit": limit,
        "gate_id": gate_id,
        "statuses": "in_process,unloading"
    }
    return await internal_client.get("/arrivals", params=params)


# -------------------------------
# GET: /api/arrivals/{gate_id}/finished
# -------------------------------
@router.get("/arrivals/{gate_id}/finished")
async def list_arrivals_finished(
    gate_id: int,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    """
    Lists finished arrivals (status='completed').
    """
    skip = (page - 1) * limit
    params = {
        "skip": skip,
        "limit": limit,
        "gate_id": gate_id,
        "status": "completed"
    }
    return await internal_client.get("/arrivals", params=params)


# -------------------------------
# GET: /api/arrivals/{gate_id}/{shift}/total
# -------------------------------
@router.get("/arrivals/{gate_id}/{shift}/total")
async def count_arrivals_by_gate_shift(
    gate_id: int,
    shift: int,
):
    """
    Total arrivals for gate and shift.
    Returns stats for the gate.
    """
    params = {"gate_id": gate_id}
    return await internal_client.get("/arrivals/stats", params=params)


# -------------------------------
# GET: /api/arrivals/{gate_id}/{shift}/pending
# -------------------------------
@router.get("/arrivals/{gate_id}/{shift}/pending")
async def list_arrivals_pending_shift(
    gate_id: int,
    shift: int,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    skip = (page - 1) * limit
    params = {
        "skip": skip,
        "limit": limit,
        "gate_id": gate_id,
        "shift_id": shift,
        "statuses": "delayed,in_transit"
    }
    return await internal_client.get("/arrivals", params=params)


# -------------------------------
# GET: /api/arrivals/{gate_id}/{shift}/in_progress
# -------------------------------
@router.get("/arrivals/{gate_id}/{shift}/in_progress")
async def list_arrivals_in_progress_shift(
    gate_id: int,
    shift: int,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    skip = (page - 1) * limit
    params = {
        "skip": skip,
        "limit": limit,
        "gate_id": gate_id,
        "shift_id": shift,
        "statuses": "in_process,unloading"
    }
    return await internal_client.get("/arrivals", params=params)


# -------------------------------
# GET: /api/arrivals/{gate_id}/{shift}/finished
# -------------------------------
@router.get("/arrivals/{gate_id}/{shift}/finished")
async def list_arrivals_finished_shift(
    gate_id: int,
    shift: int,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    skip = (page - 1) * limit
    params = {
        "skip": skip,
        "limit": limit,
        "gate_id": gate_id,
        "shift_id": shift,
        "status": "completed"
    }
    return await internal_client.get("/arrivals", params=params)


# -------------------------------
# GET: /api/arrivals/{gate_id}/{shift}
# NOTE: Two path params, order doesn't matter vs single param
# -------------------------------
@router.get("/arrivals/{gate_id}/{shift}")
async def list_arrivals_by_gate_shift(
    gate_id: int,
    shift: int,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    """
    Lists arrivals by gate and shift.
    """
    skip = (page - 1) * limit
    params = {
        "skip": skip,
        "limit": limit,
        "gate_id": gate_id,
        "shift_id": shift
    }
    return await internal_client.get("/arrivals", params=params)


# -------------------------------
# PATCH: /api/arrivals/{appointment_id}/highway-infraction
# Manager-only: Flag appointment as highway infraction
# -------------------------------
@router.patch("/arrivals/{appointment_id}/highway-infraction")
async def flag_highway_infraction(
    appointment_id: Annotated[int, Path(description="Appointment ID")],
):
    """
    Flag an appointment as highway infraction.
    Called when hazmat truck detected on restricted highway route.
    Should only be triggered by logistics manager or automated detection.
    """
    return await internal_client.patch(f"/arrivals/{appointment_id}/highway-infraction")


# -------------------------------
# PATCH: /api/arrivals/{appointment_id}/status
# -------------------------------
class AppointmentStatusUpdate(BaseModel):
    status: str
    notes: Optional[str] = None


@router.patch("/arrivals/{appointment_id}/status")
async def update_arrival_status(
    appointment_id: Annotated[int, Path(description="Appointment ID")],
    update_data: Annotated[AppointmentStatusUpdate, Body()],
    ws_manager: Annotated[WebSocketManager, Depends(get_ws_manager)],
):
    """
    Update appointment status and broadcast status_changed via WebSocket.
    """
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


# -------------------------------
# POST: /api/arrivals/{appointment_id}/visit
# -------------------------------
class CreateVisitRequest(BaseModel):
    shift_gate_id: int
    shift_type: str  # "MORNING", "AFTERNOON", "NIGHT"
    shift_date: date


@router.post("/arrivals/{appointment_id}/visit")
async def create_visit(
    appointment_id: Annotated[int, Path(description="Appointment ID")],
    request: Annotated[CreateVisitRequest, Body()],
):
    """
    Create a visit when truck arrives.
    """
    payload = request.model_dump()
    payload["shift_date"] = payload["shift_date"].isoformat()
    return await internal_client.post(f"/arrivals/{appointment_id}/visit", json=payload)


# -------------------------------
# PATCH: /api/arrivals/{appointment_id}/visit
# -------------------------------
class VisitStatusUpdate(BaseModel):
    state: str
    out_time: Optional[str] = None


@router.patch("/arrivals/{appointment_id}/visit")
async def update_visit(
    appointment_id: Annotated[int, Path(description="Appointment ID")],
    update_data: Annotated[VisitStatusUpdate, Body()],
):
    """
    Update visit status.
    """
    return await internal_client.patch(
        f"/arrivals/{appointment_id}/visit",
        json=update_data.model_dump(exclude_none=True)
    )


# -------------------------------
# GET: /api/arrivals/{gate_id}
# NOTE: This catch-all route MUST BE LAST
# -------------------------------
@router.get("/arrivals/{gate_id}")
async def list_arrivals_by_gate(
    gate_id: int,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    """
    Lists arrivals filtered by gate.
    """
    skip = (page - 1) * limit
    params = {
        "skip": skip,
        "limit": limit,
        "gate_id": gate_id
    }
    return await internal_client.get("/arrivals", params=params)
