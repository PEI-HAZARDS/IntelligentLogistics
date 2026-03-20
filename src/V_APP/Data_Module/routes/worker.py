"""
Worker Routes - Endpoints for operators and managers.
Consumed by: Backoffice frontend, API Gateway (authentication).

CQRS: GET endpoints read from MongoDB. POST/PATCH/DELETE use UoW + Outbox.
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, status, Query, Path
from pydantic import BaseModel

from application.schemas import Worker, Manager, Operator, Shift, WorkerLoginRequest, WorkerLoginResponse
from application.use_cases.worker_handlers import (
    authenticate_worker,
    create_worker,
    update_worker_password,
    update_worker_email,
    deactivate_worker,
    promote_to_manager,
)
from application.queries.worker_queries import (
    get_all_workers,
    get_operators,
    get_managers,
    get_worker_by_num,
    get_operator_info,
    get_manager_info,
    get_operator_gate_dashboard,
    get_manager_overview,
)
from infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from utils.auth_token import generate_internal_jwt

router = APIRouter(prefix="/workers", tags=["Workers"])

_uow_factory = SqlAlchemyUnitOfWork


# ==================== LOCAL PYDANTIC MODELS ====================

class CreateWorkerRequest(BaseModel):
    """Request to create new worker."""
    num_worker: str
    name: str
    email: str
    password: str
    role: str  # "operator" or "manager"
    access_level: Optional[str] = None  # For managers
    phone: Optional[str] = None


class UpdatePasswordRequest(BaseModel):
    """Request to update password."""
    current_password: str
    new_password: str


class UpdateEmailRequest(BaseModel):
    """Request to update email."""
    new_email: str


class WorkerInfo(BaseModel):
    """Worker information."""
    num_worker: str
    name: str
    email: str
    role: str
    active: bool


class OperatorDashboard(BaseModel):
    """Operator dashboard."""
    operator_num_worker: str
    gate_id: int
    date: str
    upcoming_arrivals: List[Dict[str, Any]]
    stats: Dict[str, int]


class ManagerOverview(BaseModel):
    """Manager overview."""
    manager_num_worker: str
    date: str
    active_gates: int
    shifts_today: int
    recent_alerts: int
    statistics: Dict[str, int]


# ==================== AUTH ENDPOINTS ====================

@router.post("/login", response_model=WorkerLoginResponse)
def login(credentials: WorkerLoginRequest):
    """
    Worker login (operator or manager).
    Returns token for authentication.
    """
    worker = authenticate_worker(
        _uow_factory,
        email=credentials.email,
        password=credentials.password,
    )

    if not worker:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials or account deactivated",
        )

    # KEYCLOAK: this token will be issued by Keycloak once integrated.
    role = worker.get("role", "operator")
    token = generate_internal_jwt(sub=worker["num_worker"], role=role)

    return WorkerLoginResponse(
        token=token,
        num_worker=worker["num_worker"],
        name=worker["name"],
        email=worker["email"],
        active=worker["active"],
    )


# ==================== OPERATOR ENDPOINTS ====================

@router.get("/operators", response_model=List[WorkerInfo])
def list_operators(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    """Lists operators."""
    operators = get_operators(skip=skip, limit=limit)
    return [
        WorkerInfo(
            num_worker=op["num_worker"],
            name=op["name"],
            email=op["email"],
            role="operator",
            active=op.get("active", True),
        )
        for op in operators
    ]


@router.get("/operators/me", response_model=Dict[str, Any])
def get_my_operator_info(
    num_worker: str = Query(..., description="Operator num_worker (from JWT)"),
):
    """
    Gets authenticated operator information.
    In production: num_worker would come from JWT.
    """
    info = get_operator_info(num_worker)
    if not info:
        raise HTTPException(status_code=404, detail="Operator not found")
    return info


@router.get("/operators/{num_worker}")
def get_operator(
    num_worker: str = Path(..., description="Operator num_worker"),
):
    """Gets information of a specific operator."""
    info = get_operator_info(num_worker)
    if not info:
        raise HTTPException(status_code=404, detail="Operator not found")
    return info


@router.get("/operators/{num_worker}/current-shift/{gate_id}")
def get_operator_shift(
    num_worker: str = Path(...),
    gate_id: int = Path(...),
):
    """Gets operator's current shift for a gate."""
    # Shift data not yet projected to MongoDB — return None for now
    return None


@router.get("/operators/{num_worker}/shifts")
def list_operator_shifts(
    num_worker: str = Path(...),
    gate_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Lists shifts for an operator."""
    # Shift data not yet projected to MongoDB — return empty list
    return []


@router.get("/operators/{num_worker}/dashboard/{gate_id}", response_model=OperatorDashboard)
def get_operator_dashboard(
    num_worker: str = Path(...),
    gate_id: int = Path(...),
):
    """
    Operator dashboard for a gate.
    Upcoming arrivals, alerts, statistics.
    """
    dashboard = get_operator_gate_dashboard(num_worker, gate_id)
    return OperatorDashboard(**dashboard)


# ==================== MANAGER ENDPOINTS ====================

@router.get("/managers", response_model=List[WorkerInfo])
def list_managers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    """Lists managers."""
    managers = get_managers(skip=skip, limit=limit)
    return [
        WorkerInfo(
            num_worker=m["num_worker"],
            name=m["name"],
            email=m["email"],
            role="manager",
            active=m.get("active", True),
        )
        for m in managers
    ]


@router.get("/managers/me", response_model=Dict[str, Any])
def get_my_manager_info(
    num_worker: str = Query(..., description="Manager num_worker (from JWT)"),
):
    """
    Gets authenticated manager information.
    In production: num_worker would come from JWT.
    """
    info = get_manager_info(num_worker)
    if not info:
        raise HTTPException(status_code=404, detail="Manager not found")
    return info


@router.get("/managers/{num_worker}")
def get_manager(
    num_worker: str = Path(...),
):
    """Gets information of a specific manager."""
    info = get_manager_info(num_worker)
    if not info:
        raise HTTPException(status_code=404, detail="Manager not found")
    return info


@router.get("/managers/{num_worker}/shifts")
def list_manager_shifts(
    num_worker: str = Path(...),
    limit: int = Query(50, ge=1, le=200),
):
    """Lists shifts supervised by a manager."""
    # Shift data not yet projected to MongoDB — return empty list
    return []


@router.get("/managers/{num_worker}/overview", response_model=ManagerOverview)
def get_manager_dashboard(
    num_worker: str = Path(...),
):
    """
    Manager dashboard/overview.
    Gates, shifts, alerts, performance.
    """
    overview = get_manager_overview(num_worker)
    return ManagerOverview(**overview)


# ==================== GENERAL WORKER ENDPOINTS ====================

@router.get("", response_model=List[WorkerInfo])
def list_all_workers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    only_active: bool = Query(True),
):
    """Lists all workers (backoffice)."""
    workers = get_all_workers(skip=skip, limit=limit, only_active=only_active)
    return [
        WorkerInfo(
            num_worker=w["num_worker"],
            name=w["name"],
            email=w["email"],
            role=w.get("role", "unknown"),
            active=w.get("active", True),
        )
        for w in workers
    ]


@router.get("/{num_worker}", response_model=Dict[str, Any])
def get_worker(
    num_worker: str = Path(...),
):
    """Gets worker data."""
    worker = get_worker_by_num(num_worker)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    return worker


# ==================== ACCOUNT MANAGEMENT ====================

@router.post("/password", status_code=status.HTTP_200_OK)
def change_password(
    request: UpdatePasswordRequest,
    num_worker: str = Query(..., description="Worker num_worker (from JWT)"),
):
    """Updates worker's password."""
    success, error = update_worker_password(
        _uow_factory,
        num_worker=num_worker,
        current_password=request.current_password,
        new_password=request.new_password,
    )
    if not success:
        status_code = 404 if error == "Worker not found" else 401
        raise HTTPException(status_code=status_code, detail=error)

    return {"message": "Password updated successfully"}


@router.post("/email", status_code=status.HTTP_200_OK)
def change_email(
    request: UpdateEmailRequest,
    num_worker: str = Query(..., description="Worker num_worker (from JWT)"),
):
    """Updates worker's email."""
    success, error = update_worker_email(
        _uow_factory,
        num_worker=num_worker,
        new_email=request.new_email,
    )
    if not success:
        raise HTTPException(status_code=400, detail=error or "Email already in use or worker not found")

    return {"message": "Email updated successfully"}


# ==================== ADMIN ENDPOINTS ====================

@router.post("", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
def create_new_worker(request: CreateWorkerRequest):
    """
    Creates new worker (operator or manager).
    Requires admin authentication.
    """
    worker = create_worker(
        _uow_factory,
        num_worker=request.num_worker,
        name=request.name,
        email=request.email,
        password=request.password,
        role=request.role,
        access_level=request.access_level,
        phone=request.phone,
    )

    if not worker:
        raise HTTPException(status_code=400, detail="Email or num_worker already in use")

    return {
        "num_worker": worker["num_worker"],
        "name": worker["name"],
        "email": worker["email"],
        "role": request.role,
        "active": worker.get("active", True),
    }


@router.delete("/{num_worker}", status_code=status.HTTP_200_OK)
def deactivate_worker_endpoint(
    num_worker: str = Path(...),
):
    """Deactivates a worker."""
    worker = deactivate_worker(_uow_factory, num_worker=num_worker)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    return {"message": f"Worker {worker['name']} deactivated"}


@router.post("/{num_worker}/promote", status_code=status.HTTP_200_OK)
def promote_operator_to_manager(
    num_worker: str = Path(...),
    access_level: str = Query("basic"),
):
    """Promotes an operator to manager."""
    manager = promote_to_manager(_uow_factory, num_worker=num_worker, access_level=access_level)
    if not manager:
        raise HTTPException(status_code=400, detail="Worker is not an operator or not found")

    return {"message": f"Operator promoted to manager with access level {access_level}"}
