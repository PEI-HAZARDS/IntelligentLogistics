from typing import Optional, Dict, Any

from fastapi import APIRouter, Query

from ..clients import internal_api_client as internal_client

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
