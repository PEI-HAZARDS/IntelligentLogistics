"""
Workers Router - Proxy endpoints for operators and managers.
Consumed by: Operator frontend, Manager frontend, Backoffice.
"""

from typing import Optional, Dict, Any

from fastapi import APIRouter, Query, Path, Body
from pydantic import BaseModel

from clients import internal_api_client as internal_client

router = APIRouter(tags=["workers"])


# ==================== PYDANTIC MODELS ====================

class WorkerLoginRequest(BaseModel):
    """Worker login credentials."""
    email: str
    password: str


# ==================== AUTH ENDPOINTS ====================

@router.post("/workers/login")
async def worker_login(credentials: WorkerLoginRequest):
    """
    Worker (operator/manager) login.
    Proxy to POST /api/v1/workers/login
    """
    return await internal_client.post("/workers/login", json=credentials.model_dump())


# ==================== STATIC ROUTES FIRST ====================

@router.get("/workers")
async def list_workers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    """
    List all workers.
    Proxy to GET /api/v1/workers
    """
    params = {"skip": skip, "limit": limit}
    return await internal_client.get("/workers", params=params)


# ==================== OPERATOR ENDPOINTS ====================
# NOTE: Must be BEFORE /workers/{num_worker}

@router.get("/workers/operators")
async def list_operators(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    """
    List operators.
    Proxy to GET /api/v1/workers/operators
    """
    params = {"skip": skip, "limit": limit}
    return await internal_client.get("/workers/operators", params=params)


@router.get("/workers/operators/{num_worker}")
async def get_operator(
    num_worker: str = Path(..., description="Operator ID"),
):
    """
    Get operator details.
    Proxy to GET /api/v1/workers/operators/{num_worker}
    """
    return await internal_client.get(f"/workers/operators/{num_worker}")


@router.get("/workers/operators/{num_worker}/current-shift/{gate_id}")
async def get_operator_current_shift(
    num_worker: str = Path(...),
    gate_id: int = Path(...),
):
    """
    Get operator's current shift for a gate.
    Proxy to GET /api/v1/workers/operators/{num_worker}/current-shift/{gate_id}
    """
    return await internal_client.get(f"/workers/operators/{num_worker}/current-shift/{gate_id}")


@router.get("/workers/operators/{num_worker}/shifts")
async def list_operator_shifts(
    num_worker: str = Path(...),
    gate_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """
    List shifts for an operator.
    Proxy to GET /api/v1/workers/operators/{num_worker}/shifts
    """
    params = {"limit": limit}
    if gate_id is not None:
        params["gate_id"] = gate_id
    return await internal_client.get(f"/workers/operators/{num_worker}/shifts", params=params)


@router.get("/workers/operators/{num_worker}/dashboard/{gate_id}")
async def get_operator_dashboard(
    num_worker: str = Path(...),
    gate_id: int = Path(...),
):
    """
    Operator dashboard for a specific gate.
    Proxy to GET /api/v1/workers/operators/{num_worker}/dashboard/{gate_id}
    """
    return await internal_client.get(f"/workers/operators/{num_worker}/dashboard/{gate_id}")


# ==================== MANAGER ENDPOINTS ====================
# NOTE: Must be BEFORE /workers/{num_worker}

@router.get("/workers/managers")
async def list_managers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    """
    List managers.
    Proxy to GET /api/v1/workers/managers
    """
    params = {"skip": skip, "limit": limit}
    return await internal_client.get("/workers/managers", params=params)


@router.get("/workers/managers/{num_worker}")
async def get_manager(
    num_worker: str = Path(..., description="Manager ID"),
):
    """
    Get manager details.
    Proxy to GET /api/v1/workers/managers/{num_worker}
    """
    return await internal_client.get(f"/workers/managers/{num_worker}")


@router.get("/workers/managers/{num_worker}/shifts")
async def list_manager_shifts(
    num_worker: str = Path(...),
    limit: int = Query(50, ge=1, le=200),
):
    """
    List shifts supervised by a manager.
    Proxy to GET /api/v1/workers/managers/{num_worker}/shifts
    """
    params = {"limit": limit}
    return await internal_client.get(f"/workers/managers/{num_worker}/shifts", params=params)


@router.get("/workers/managers/{num_worker}/overview")
async def get_manager_overview(
    num_worker: str = Path(...),
):
    """
    Manager overview/dashboard.
    Proxy to GET /api/v1/workers/managers/{num_worker}/overview
    """
    return await internal_client.get(f"/workers/managers/{num_worker}/overview")


# ==================== CATCH-ALL DYNAMIC ROUTE - LAST! ====================
# NOTE: Must be LAST to avoid capturing 'operators', 'managers', 'login'

@router.get("/workers/{num_worker}")
async def get_worker(
    num_worker: str = Path(..., description="Worker ID"),
):
    """
    Get specific worker details.
    Proxy to GET /api/v1/workers/{num_worker}
    """
    return await internal_client.get(f"/workers/{num_worker}")
