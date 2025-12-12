from typing import Optional, Dict, Any
from datetime import date

from fastapi import APIRouter, Query, Path, Body
from pydantic import BaseModel

from clients import internal_api_client as internal_client

router = APIRouter(tags=["arrivals"])


# -------------------------------
# GET: /api/arrivals
# -------------------------------
@router.get("/arrivals")
async def list_all_arrivals(
    license_plate: Optional[str] = Query(None, alias="matricula"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """
    Proxy to GET /api/v1/arrivals in Data Module.
    """
    skip = (page - 1) * limit
    params = {
        "skip": skip,
        "limit": limit,
    }
    if license_plate:
        params["license_plate"] = license_plate # DataModule expects license_plate not matricula

    return await internal_client.get("/arrivals", params=params)


# -------------------------------
# GET: /api/arrivals/{gate_id}
# -------------------------------
@router.get("/arrivals/{gate_id}")
async def list_arrivals_by_gate(
    gate_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """
    Lists arrivals filtered by gate.
    Maps to GET /api/v1/arrivals?gate_id={gate_id}
    """
    skip = (page - 1) * limit
    params = {
        "skip": skip,
        "limit": limit,
        "gate_id": gate_id
    }
    return await internal_client.get("/arrivals", params=params)


# -------------------------------
# GET: /api/arrivals/{gate_id}/{shift}
# -------------------------------
@router.get("/arrivals/{gate_id}/{shift}")
async def list_arrivals_by_gate_shift(
    gate_id: int,
    shift: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """
    Lists arrivals by gate and shift.
    Maps to GET /api/v1/arrivals?gate_id={gate_id}&shift_id={shift}
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
# GET: /api/arrivals/{gate_id}/{shift}/total
# -------------------------------
@router.get("/arrivals/{gate_id}/{shift}/total")
async def count_arrivals_by_gate_shift(
    gate_id: int,
    shift: int,
):
    """
    Total arrivals for gate and shift.
    Uses /arrivals/stats?gate_id={gate_id} (and currently filtering client-side or we accept stats limitation)
    DataModule stats endpoint: /alerts/stats or /arrivals/stats
    /arrivals/stats params: gate_id, target_date. Does not support shift_id yet.
    
    Fallback: call /arrivals with limit=1 just to get count? 
    Data Module response is a list, doesn't have metadata 'total'.
    
    For now, return a placeholder or sum from stats if possible.
    Let's return the stats for the gate.
    """
    # NOTE: shift_id is not filtered in stats yet. Returning stats for gate.
    params = {"gate_id": gate_id}
    return await internal_client.get("/arrivals/stats", params=params)


# -------------------------------
# GET: /api/arrivals/{gate_id}/pending
# -------------------------------
@router.get("/arrivals/{gate_id}/pending")
async def list_arrivals_pending(
    gate_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """
    Lists pending arrivals (status='pending') by gate.
    """
    skip = (page - 1) * limit
    params = {
        "skip": skip,
        "limit": limit,
        "gate_id": gate_id,
        "status": "pending"
    }
    return await internal_client.get("/arrivals", params=params)


# -------------------------------
# GET: /api/arrivals/{gate_id}/{shift}/pending
# -------------------------------
@router.get("/arrivals/{gate_id}/{shift}/pending")
async def list_arrivals_pending_shift(
    gate_id: int,
    shift: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    skip = (page - 1) * limit
    params = {
        "skip": skip,
        "limit": limit,
        "gate_id": gate_id,
        "shift_id": shift,
        "status": "pending"
    }
    return await internal_client.get("/arrivals", params=params)


# -------------------------------
# GET: /api/arrivals/{gate_id}/in_progress
# -------------------------------
@router.get("/arrivals/{gate_id}/in_progress")
async def list_arrivals_in_progress(
    gate_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """
    Lists in-progress arrivals (status='approved' or visit state).
    Data Module Appointment status: pending, approved, completed, canceled.
    'In progress' usually means 'approved' (waiting/entering) or 'unloading'?
    Let's map to 'approved' for now.
    """
    skip = (page - 1) * limit
    params = {
        "skip": skip,
        "limit": limit,
        "gate_id": gate_id,
        "status": "approved"
    }
    return await internal_client.get("/arrivals", params=params)


# -------------------------------
# GET: /api/arrivals/{gate_id}/{shift}/in_progress
# -------------------------------
@router.get("/arrivals/{gate_id}/{shift}/in_progress")
async def list_arrivals_in_progress_shift(
    gate_id: int,
    shift: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    skip = (page - 1) * limit
    params = {
        "skip": skip,
        "limit": limit,
        "gate_id": gate_id,
        "shift_id": shift,
        "status": "approved"
    }
    return await internal_client.get("/arrivals", params=params)


# -------------------------------
# GET: /api/arrivals/{gate_id}/finished
# -------------------------------
@router.get("/arrivals/{gate_id}/finished")
async def list_arrivals_finished(
    gate_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
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
# GET: /api/arrivals/{gate_id}/{shift}/finished
# -------------------------------
@router.get("/arrivals/{gate_id}/{shift}/finished")
async def list_arrivals_finished_shift(
    gate_id: int,
    shift: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
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


# ===============================
# NEW ENDPOINTS FROM DATA MODULE
# ===============================

# -------------------------------
# GET: /api/arrivals/stats
# -------------------------------
@router.get("/arrivals/stats")
async def get_arrivals_stats(
    gate_id: Optional[int] = Query(None, description="Filter by gate"),
    target_date: Optional[date] = Query(None, description="Date to query"),
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
# -------------------------------
@router.get("/arrivals/next/{gate_id}")
async def get_upcoming_arrivals(
    gate_id: int = Path(..., description="Gate ID"),
    limit: int = Query(5, ge=1, le=20),
):
    """
    Next scheduled arrivals for a gate.
    Proxy to GET /api/v1/arrivals/next/{gate_id}
    """
    params = {"limit": limit}
    return await internal_client.get(f"/arrivals/next/{gate_id}", params=params)


# -------------------------------
# GET: /api/arrivals/pin/{arrival_id}
# -------------------------------
@router.get("/arrivals/pin/{arrival_id}")
async def get_arrival_by_pin(
    arrival_id: str = Path(..., description="Arrival ID / PIN"),
):
    """
    Get appointment by arrival_id/PIN.
    Proxy to GET /api/v1/arrivals/pin/{arrival_id}
    """
    return await internal_client.get(f"/arrivals/pin/{arrival_id}")


# -------------------------------
# GET: /api/arrivals/detail/{appointment_id}
# -------------------------------
@router.get("/arrivals/detail/{appointment_id}")
async def get_arrival_detail(
    appointment_id: int = Path(..., description="Appointment ID"),
):
    """
    Get appointment details by ID.
    Proxy to GET /api/v1/arrivals/{appointment_id}
    """
    return await internal_client.get(f"/arrivals/{appointment_id}")


# -------------------------------
# PATCH: /api/arrivals/{appointment_id}/status
# -------------------------------
class AppointmentStatusUpdate(BaseModel):
    status: str
    notes: Optional[str] = None


@router.patch("/arrivals/{appointment_id}/status")
async def update_arrival_status(
    appointment_id: int = Path(..., description="Appointment ID"),
    update_data: AppointmentStatusUpdate = Body(...),
):
    """
    Update appointment status.
    Proxy to PATCH /api/v1/arrivals/{appointment_id}/status
    """
    return await internal_client.patch(
        f"/arrivals/{appointment_id}/status",
        json=update_data.model_dump(exclude_none=True)
    )


# -------------------------------
# POST: /api/arrivals/{appointment_id}/visit
# -------------------------------
class CreateVisitRequest(BaseModel):
    shift_gate_id: int
    shift_type: str  # "MORNING", "AFTERNOON", "NIGHT"
    shift_date: date


@router.post("/arrivals/{appointment_id}/visit")
async def create_visit(
    appointment_id: int = Path(..., description="Appointment ID"),
    request: CreateVisitRequest = Body(...),
):
    """
    Create a visit when truck arrives.
    Proxy to POST /api/v1/arrivals/{appointment_id}/visit
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
    appointment_id: int = Path(..., description="Appointment ID"),
    update_data: VisitStatusUpdate = Body(...),
):
    """
    Update visit status.
    Proxy to PATCH /api/v1/arrivals/{appointment_id}/visit
    """
    return await internal_client.patch(
        f"/arrivals/{appointment_id}/visit",
        json=update_data.model_dump(exclude_none=True)
    )
