"""
Workers Router - Proxy endpoints for operators and managers.
Consumed by: Operator frontend, Manager frontend, Backoffice.
"""

from typing import Annotated, Optional, Dict, Any

from fastapi import APIRouter, Query, Path, Depends

from clients import internal_api_client as internal_client
from auth.token_validator import require_role, TokenPayload

router = APIRouter(tags=["workers"])


# ==================== SHIFT LISTING ====================

@router.get("/workers/shifts")
async def list_shifts(
    _user: Annotated[TokenPayload, Depends(require_role("operator", "manager"))],
    target_date: Annotated[Optional[str], Query()] = None,
    shift_type: Annotated[Optional[str], Query()] = None,
    gate_id: Annotated[Optional[int], Query()] = None,
):
    """
    List all shifts for a date (manager ShiftsPage).
    Proxy to GET /api/v1/workers/shifts
    """
    params: Dict[str, Any] = {}
    if target_date:
        params["target_date"] = target_date
    if shift_type:
        params["shift_type"] = shift_type
    if gate_id is not None:
        params["gate_id"] = gate_id
    return await internal_client.get("/workers/shifts", params=params)


# ==================== OPERATOR ENDPOINTS ====================
# NOTE: These must come BEFORE /workers/{num_worker} to avoid path conflicts

@router.get("/workers/operators")
async def list_operators(
    _user: Annotated[TokenPayload, Depends(require_role("operator", "manager"))],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    """
    List operators.
    Proxy to GET /api/v1/workers/operators
    """
    params = {"skip": skip, "limit": limit}
    return await internal_client.get("/workers/operators", params=params)


@router.get("/workers/operators/{num_worker}")
async def get_operator(
    num_worker: Annotated[str, Path(description="Operator ID")],
    _user: Annotated[TokenPayload, Depends(require_role("operator", "manager"))],
):
    """
    Get operator details.
    Proxy to GET /api/v1/workers/operators/{num_worker}
    """
    return await internal_client.get(f"/workers/operators/{num_worker}")


@router.get("/workers/operators/{num_worker}/current-shift/{gate_id}")
async def get_operator_current_shift(
    num_worker: Annotated[str, Path()],
    gate_id: Annotated[int, Path()],
    _user: Annotated[TokenPayload, Depends(require_role("operator", "manager"))],
):
    """
    Get operator's current shift for a gate.
    Proxy to GET /api/v1/workers/operators/{num_worker}/current-shift/{gate_id}
    """
    return await internal_client.get(f"/workers/operators/{num_worker}/current-shift/{gate_id}")


@router.get("/workers/operators/{num_worker}/shifts")
async def list_operator_shifts(
    num_worker: Annotated[str, Path()],
    _user: Annotated[TokenPayload, Depends(require_role("operator", "manager"))],
    gate_id: Annotated[Optional[int], Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
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
    num_worker: Annotated[str, Path()],
    gate_id: Annotated[int, Path()],
    _user: Annotated[TokenPayload, Depends(require_role("operator", "manager"))],
):
    """
    Operator dashboard for a specific gate.
    Proxy to GET /api/v1/workers/operators/{num_worker}/dashboard/{gate_id}
    """
    return await internal_client.get(f"/workers/operators/{num_worker}/dashboard/{gate_id}")


# ==================== MANAGER ENDPOINTS ====================
# NOTE: These must come BEFORE /workers/{num_worker} to avoid path conflicts

@router.get("/workers/managers")
async def list_managers(
    _user: Annotated[TokenPayload, Depends(require_role("manager"))],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    """
    List managers.
    Proxy to GET /api/v1/workers/managers
    """
    params = {"skip": skip, "limit": limit}
    return await internal_client.get("/workers/managers", params=params)


@router.get("/workers/managers/{num_worker}")
async def get_manager(
    num_worker: Annotated[str, Path(description="Manager ID")],
    _user: Annotated[TokenPayload, Depends(require_role("manager"))],
):
    """
    Get manager details.
    Proxy to GET /api/v1/workers/managers/{num_worker}
    """
    return await internal_client.get(f"/workers/managers/{num_worker}")


@router.get("/workers/managers/{num_worker}/shifts")
async def list_manager_shifts(
    num_worker: Annotated[str, Path()],
    _user: Annotated[TokenPayload, Depends(require_role("manager"))],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    """
    List shifts supervised by a manager.
    Proxy to GET /api/v1/workers/managers/{num_worker}/shifts
    """
    params = {"limit": limit}
    return await internal_client.get(f"/workers/managers/{num_worker}/shifts", params=params)


@router.get("/workers/managers/{num_worker}/overview")
async def get_manager_overview(
    num_worker: Annotated[str, Path()],
    _user: Annotated[TokenPayload, Depends(require_role("manager"))],
):
    """
    Manager overview/dashboard.
    Proxy to GET /api/v1/workers/managers/{num_worker}/overview
    """
    return await internal_client.get(f"/workers/managers/{num_worker}/overview")


# ==================== GENERAL WORKER ENDPOINTS ====================
# NOTE: Dynamic routes /{num_worker} must come LAST to avoid capturing 'operators'/'managers'

@router.get("/workers")
async def list_workers(
    _user: Annotated[TokenPayload, Depends(require_role("operator", "manager"))],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    """
    List all workers.
    Proxy to GET /api/v1/workers
    """
    params = {"skip": skip, "limit": limit}
    return await internal_client.get("/workers", params=params)


@router.get("/workers/{num_worker}")
async def get_worker(
    num_worker: Annotated[str, Path(description="Worker ID")],
    _user: Annotated[TokenPayload, Depends(require_role("operator", "manager"))],
):
    """
    Get specific worker details.
    Proxy to GET /api/v1/workers/{num_worker}
    """
    return await internal_client.get(f"/workers/{num_worker}")
