"""
Workers Router - Proxy endpoints for operators and managers.
Consumed by: Operator frontend, Manager frontend, Backoffice.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional, Dict, Any

import httpx
import jwt as _jwt
from fastapi import APIRouter, HTTPException, Query, Path, Body, Depends, Request
from pydantic import BaseModel

from clients import internal_api_client as internal_client
from auth.token_validator import require_role, TokenPayload

router = APIRouter(tags=["workers"])

# DM internal JWT — must match Data Module settings.jwt_secret / TOKEN_EXPIRY_HOURS
_DM_JWT_SECRET: str = os.getenv("DM_JWT_SECRET", "pei-internal-secret-replace-with-keycloak")
_DM_TOKEN_EXPIRY_HOURS: int = int(os.getenv("TOKEN_EXPIRY_HOURS", "24"))


def _dm_worker_jwt(num_worker: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    return _jwt.encode(
        {"sub": num_worker, "role": role, "iat": now,
         "exp": now + timedelta(hours=_DM_TOKEN_EXPIRY_HOURS)},
        _DM_JWT_SECRET, algorithm="HS256",
    )


def _dm_worker_auth(num_worker: str, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {_dm_worker_jwt(num_worker, role)}"}


# ==================== REQUEST MODELS ====================

class CreateWorkerRequest(BaseModel):
    num_worker: str
    name: str
    email: str
    password: str
    role: str  # "operator" | "manager"
    access_level: Optional[str] = "basic"
    phone: Optional[str] = None


class UpdatePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class UpdateEmailRequest(BaseModel):
    new_email: str


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


# ==================== SHIFT CRUD ====================

class ShiftCreatePayload(BaseModel):
    gate_id: int
    shift_type: str
    date: str
    operator_num_worker: Optional[str] = None
    manager_num_worker: Optional[str] = None


class ShiftUpdatePayload(BaseModel):
    operator_num_worker: Optional[str] = None
    manager_num_worker: Optional[str] = None


@router.post("/workers/shifts", status_code=201)
async def create_shift(
    _user: Annotated[TokenPayload, Depends(require_role("manager"))],
    body: ShiftCreatePayload,
):
    return await internal_client.post("/workers/shifts", json=body.model_dump())


@router.put("/workers/shifts/{gate_id}/{shift_type}/{shift_date}")
async def update_shift(
    _user: Annotated[TokenPayload, Depends(require_role("manager"))],
    gate_id: Annotated[int, Path()],
    shift_type: Annotated[str, Path()],
    shift_date: Annotated[str, Path()],
    body: ShiftUpdatePayload,
):
    return await internal_client.put(
        f"/workers/shifts/{gate_id}/{shift_type}/{shift_date}",
        json=body.model_dump(exclude_none=True),
    )


@router.delete("/workers/shifts/{gate_id}/{shift_type}/{shift_date}", status_code=204)
async def delete_shift(
    _user: Annotated[TokenPayload, Depends(require_role("manager"))],
    gate_id: Annotated[int, Path()],
    shift_type: Annotated[str, Path()],
    shift_date: Annotated[str, Path()],
):
    return await internal_client.delete(
        f"/workers/shifts/{gate_id}/{shift_type}/{shift_date}"
    )


@router.post("/workers/shifts/bulk", status_code=200)
async def bulk_import_shifts(
    _user: Annotated[TokenPayload, Depends(require_role("manager"))],
    request: Request,
):
    """
    Transparent proxy for multipart CSV upload. Forwards raw body without parsing.
    """
    from clients.internal_api_client import _build_url
    body = await request.body()
    content_type = request.headers.get("content-type", "multipart/form-data")
    url = _build_url("/workers/shifts/bulk")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, content=body, headers={"content-type": content_type})
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Data Module unreachable: {exc}")
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except Exception:
            detail = response.text
        raise HTTPException(status_code=response.status_code, detail=detail)
    return response.json()


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


@router.get("/workers/operators/me")
async def get_my_operator_info(
    _user: Annotated[TokenPayload, Depends(require_role("operator", "manager"))],
):
    """
    Get authenticated operator's own profile.
    Resolves identity from JWT sub (email) — no query param needed.
    """
    return await internal_client.get("/workers/operators/me", params={"email": _user.sub})


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


@router.get("/workers/managers/me")
async def get_my_manager_info(
    _user: Annotated[TokenPayload, Depends(require_role("manager"))],
):
    """
    Get authenticated manager's own profile.
    Resolves identity from JWT sub (email) — no query param needed.
    """
    return await internal_client.get("/workers/managers/me", params={"email": _user.sub})


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


# ==================== WORKER MUTATIONS ====================

@router.post("/workers")
async def create_worker(
    request: Annotated[CreateWorkerRequest, Body()],
    _user: Annotated[TokenPayload, Depends(require_role("manager"))],
):
    """
    Create a new worker (operator or manager).
    Proxy to POST /api/v1/workers
    """
    return await internal_client.post("/workers", json=request.model_dump(exclude_none=True))


@router.delete("/workers/{num_worker}")
async def deactivate_worker(
    num_worker: Annotated[str, Path(description="Worker num_worker to deactivate")],
    _user: Annotated[TokenPayload, Depends(require_role("manager"))],
):
    """
    Deactivate a worker.
    Proxy to DELETE /api/v1/workers/{num_worker}
    """
    return await internal_client.delete(f"/workers/{num_worker}")


@router.post("/workers/{num_worker}/promote")
async def promote_to_manager(
    num_worker: Annotated[str, Path(description="Operator num_worker to promote")],
    _user: Annotated[TokenPayload, Depends(require_role("manager"))],
    access_level: Annotated[str, Query(description="Manager access level")] = "basic",
):
    """
    Promote an operator to manager.
    Proxy to POST /api/v1/workers/{num_worker}/promote
    """
    return await internal_client.post(
        f"/workers/{num_worker}/promote",
        params={"access_level": access_level},
    )


@router.post("/workers/password")
async def change_password(
    num_worker: Annotated[str, Query(description="Worker num_worker")],
    request: Annotated[UpdatePasswordRequest, Body()],
    current_user: Annotated[TokenPayload, Depends(require_role("operator", "manager"))],
):
    """
    Change a worker's password. Forwards a DM-internal JWT so the Data Module
    can resolve the caller's identity via claims["sub"].
    Proxy to POST /api/v1/workers/password
    """
    dm_role = "manager" if "manager" in current_user.roles else "operator"
    return await internal_client.post(
        "/workers/password",
        json=request.model_dump(),
        headers=_dm_worker_auth(num_worker, dm_role),
    )


@router.post("/workers/email")
async def change_email(
    num_worker: Annotated[str, Query(description="Worker num_worker")],
    request: Annotated[UpdateEmailRequest, Body()],
    current_user: Annotated[TokenPayload, Depends(require_role("operator", "manager"))],
):
    """
    Change a worker's email. Forwards a DM-internal JWT so the Data Module
    can resolve the caller's identity via claims["sub"].
    Proxy to POST /api/v1/workers/email
    """
    dm_role = "manager" if "manager" in current_user.roles else "operator"
    return await internal_client.post(
        "/workers/email",
        json=request.model_dump(),
        headers=_dm_worker_auth(num_worker, dm_role),
    )
