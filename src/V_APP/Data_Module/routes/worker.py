"""
Worker Routes - Endpoints for operators and managers.
Consumed by: Backoffice frontend, API Gateway (authentication).

CQRS: GET endpoints read from MongoDB. POST/PATCH/DELETE use UoW + Outbox.
Shift queries use PostgreSQL (shift data not yet projected to MongoDB).
"""

from typing import Annotated, List, Optional, Dict, Any
from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel
from loguru import logger

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
from infrastructure.persistence.postgres import get_db, SessionLocal
from sqlalchemy import func as sa_func
from infrastructure.persistence.sql_models import Shift as ShiftORM, Visit as VisitORM, Operator, Manager
from utils.auth_token import generate_internal_jwt, require_role
from infrastructure.persistence.redis import set_session
from utils.shift_utils import current_shift_type
from config import settings

router = APIRouter(prefix="/workers", tags=["Workers"])

_uow_factory = lambda: SqlAlchemyUnitOfWork(SessionLocal)


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

    session_ttl = int(settings.token_expiry_hours * 3600)
    set_session(role, worker["num_worker"], {
        "sub": worker["num_worker"],
        "role": role,
        "name": worker["name"],
    }, ttl=session_ttl)

    return WorkerLoginResponse(
        token=token,
        num_worker=worker["num_worker"],
        name=worker["name"],
        email=worker["email"],
        active=worker["active"],
    )


# ==================== PROFILE LOOKUP (used by API Gateway auth router) ====================

@router.get("/by-email/{email}")
def get_worker_by_email(email: Annotated[str, Path(description="Worker email")]):
    """
    Look up a worker profile by email (no password check).
    Called by the API Gateway after Keycloak validates credentials.
    """
    with _uow_factory() as uow:
        worker = uow.workers.get_by_email_active(email)
        if not worker:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Worker not found or deactivated",
            )
        return {
            "num_worker": worker["num_worker"],
            "name": worker["name"],
            "email": worker["email"],
            "role": worker.get("role", "operator"),
            "active": worker["active"],
        }


# ==================== SHIFT LISTING (Manager ShiftsPage) ====================

@router.get("/shifts", response_model=List[Dict[str, Any]])
def list_shifts(
    db: Annotated[Session, Depends(get_db)],
    target_date: Annotated[Optional[date], Query(description="Date to query (default: today)")] = None,
    shift_type: Annotated[Optional[str], Query(description="Filter by shift type (MORNING/AFTERNOON/NIGHT)")] = None,
    gate_id: Annotated[Optional[int], Query(description="Filter by gate")] = None,
):
    """
    Lists all shifts for a given date with operator/gate details.
    Used by the Manager ShiftsPage.

    PostgreSQL — shift data not yet projected to MongoDB (Guardrail 5).
    """
    target = target_date or date.today()
    query = (
        db.query(ShiftORM)
        .options(
            joinedload(ShiftORM.gate),
            joinedload(ShiftORM.operator).joinedload(Operator.worker),
            joinedload(ShiftORM.manager).joinedload(Manager.worker),
        )
        .filter(ShiftORM.date == target)
    )
    if gate_id is not None:
        query = query.filter(ShiftORM.gate_id == gate_id)
    if shift_type:
        from utils.shift_utils import parse_shift_type
        try:
            parsed = parse_shift_type(shift_type)
            query = query.filter(ShiftORM.shift_type == parsed)
        except ValueError:
            pass

    shifts = query.order_by(ShiftORM.gate_id, ShiftORM.shift_type).all()

    # Single GROUP BY query for all visit counts (replaces per-shift COUNT)
    visit_counts_rows = (
        db.query(
            VisitORM.shift_gate_id,
            VisitORM.shift_type,
            VisitORM.shift_date,
            sa_func.count().label("cnt"),
        )
        .filter(VisitORM.shift_date == target)
        .group_by(VisitORM.shift_gate_id, VisitORM.shift_type, VisitORM.shift_date)
        .all()
    )
    visit_count_map = {(r.shift_gate_id, r.shift_type, r.shift_date): r.cnt for r in visit_counts_rows}

    current_st = current_shift_type()
    today = date.today()

    result = []
    for s in shifts:
        if s.date == today and s.shift_type == current_st:
            shift_status = "active"
        elif s.date < today or (s.date == today and _shift_before(s.shift_type, current_st)):
            shift_status = "completed"
        else:
            shift_status = "pending"

        if not s.operator_num_worker:
            shift_status = "inactive"

        visit_count = visit_count_map.get((s.gate_id, s.shift_type, s.date), 0)

        result.append({
            "id": f"{s.gate_id}-{s.shift_type.name}-{s.date.isoformat()}",
            "gateId": s.gate_id,
            "gateName": s.gate.label if s.gate else f"Gate {s.gate_id}",
            "shiftType": s.shift_type.name,
            "date": s.date.isoformat(),
            "operatorId": s.operator_num_worker or "",
            "operatorName": s.operator.worker.name if s.operator and s.operator.worker else "",
            "managerId": s.manager_num_worker or "",
            "managerName": s.manager.worker.name if s.manager and s.manager.worker else "",
            "currentArrivals": visit_count,
            "maxArrivals": 25,
            "status": shift_status,
        })

    return result


def _shift_before(a, b) -> bool:
    """Return True if shift type `a` is earlier in the day than `b`."""
    order = {"MORNING": 0, "AFTERNOON": 1, "NIGHT": 2}
    return order.get(a.name, 0) < order.get(b.name, 0)


# ==================== OPERATOR ENDPOINTS ====================

@router.get("/operators", response_model=List[WorkerInfo])
def list_operators(
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
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


@router.get("/operators/me", response_model=Dict[str, Any], responses={404: {"description": "Operator not found"}})
def get_my_operator_info(
    num_worker: Annotated[str, Query(description="Operator num_worker (from JWT)")],
):
    """
    Gets authenticated operator information.
    In production: num_worker would come from JWT.
    """
    info = get_operator_info(num_worker)
    if not info:
        raise HTTPException(status_code=404, detail="Operator not found")
    return info


@router.get("/operators/{num_worker}", responses={404: {"description": "Operator not found"}})
def get_operator(
    num_worker: Annotated[str, Path(description="Operator num_worker")],
):
    """Gets information of a specific operator."""
    info = get_operator_info(num_worker)
    if not info:
        raise HTTPException(status_code=404, detail="Operator not found")
    return info


def _serialize_shift(s: ShiftORM) -> Dict[str, Any]:
    """Convert Shift ORM row to dict matching frontend contract."""
    return {
        "gate_id": s.gate_id,
        "shift_type": s.shift_type.name if s.shift_type else None,
        "date": s.date.isoformat() if s.date else None,
        "operator_num_worker": s.operator_num_worker,
        "manager_num_worker": s.manager_num_worker,
        "gate": {"id": s.gate.id, "label": s.gate.label} if s.gate else None,
    }


@router.get("/operators/{num_worker}/current-shift/{gate_id}")
def get_operator_shift(
    num_worker: Annotated[str, Path()],
    gate_id: Annotated[int, Path()],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Gets operator's current shift for a gate.

    PostgreSQL fallback — shift data not yet projected to MongoDB (Guardrail 5).
    """
    today = date.today()
    shift_type = current_shift_type()
    shift = (
        db.query(ShiftORM)
        .filter(
            ShiftORM.gate_id == gate_id,
            ShiftORM.date == today,
            ShiftORM.shift_type == shift_type,
            ShiftORM.operator_num_worker == num_worker,
        )
        .first()
    )
    if not shift:
        return None
    return _serialize_shift(shift)


@router.get("/operators/{num_worker}/shifts")
def list_operator_shifts(
    num_worker: Annotated[str, Path()],
    db: Annotated[Session, Depends(get_db)],
    gate_id: Annotated[Optional[int], Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    """
    Lists shifts for an operator.

    PostgreSQL fallback — shift data not yet projected to MongoDB (Guardrail 5).
    """
    query = (
        db.query(ShiftORM)
        .options(joinedload(ShiftORM.gate))
        .filter(ShiftORM.operator_num_worker == num_worker)
    )
    if gate_id is not None:
        query = query.filter(ShiftORM.gate_id == gate_id)
    shifts = query.order_by(ShiftORM.date.desc(), ShiftORM.shift_type).limit(limit).all()
    return [_serialize_shift(s) for s in shifts]


@router.get("/operators/{num_worker}/dashboard/{gate_id}", response_model=OperatorDashboard)
def get_operator_dashboard(
    num_worker: Annotated[str, Path()],
    gate_id: Annotated[int, Path()],
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
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
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


@router.get("/managers/me", response_model=Dict[str, Any], responses={404: {"description": "Manager not found"}})
def get_my_manager_info(
    num_worker: Annotated[str, Query(description="Manager num_worker (from JWT)")],
):
    """
    Gets authenticated manager information.
    In production: num_worker would come from JWT.
    """
    info = get_manager_info(num_worker)
    if not info:
        raise HTTPException(status_code=404, detail="Manager not found")
    return info


@router.get("/managers/{num_worker}", responses={404: {"description": "Manager not found"}})
def get_manager(
    num_worker: Annotated[str, Path()],
):
    """Gets information of a specific manager."""
    info = get_manager_info(num_worker)
    if not info:
        raise HTTPException(status_code=404, detail="Manager not found")
    return info


@router.get("/managers/{num_worker}/shifts")
def list_manager_shifts(
    num_worker: Annotated[str, Path()],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    """
    Lists shifts supervised by a manager.

    PostgreSQL fallback — shift data not yet projected to MongoDB (Guardrail 5).
    """
    shifts = (
        db.query(ShiftORM)
        .options(joinedload(ShiftORM.gate))
        .filter(ShiftORM.manager_num_worker == num_worker)
        .order_by(ShiftORM.date.desc(), ShiftORM.shift_type)
        .limit(limit)
        .all()
    )
    return [_serialize_shift(s) for s in shifts]


@router.get("/managers/{num_worker}/overview", response_model=ManagerOverview)
def get_manager_dashboard(
    num_worker: Annotated[str, Path()],
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
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    only_active: Annotated[bool, Query()] = True,
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


@router.get("/{num_worker}", response_model=Dict[str, Any], responses={404: {"description": "Worker not found"}})
def get_worker(
    num_worker: Annotated[str, Path()],
):
    """Gets worker data."""
    worker = get_worker_by_num(num_worker)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    return worker


# ==================== ACCOUNT MANAGEMENT ====================

_worker_claims = require_role("operator", "manager")


@router.post("/password", status_code=status.HTTP_200_OK)
def change_password(
    request: UpdatePasswordRequest,
    claims: Annotated[dict, Depends(_worker_claims)],
):
    """Updates the authenticated worker's password."""
    success, error = update_worker_password(
        _uow_factory,
        num_worker=claims["sub"],
        current_password=request.current_password,
        new_password=request.new_password,
    )
    if not success:
        status_code = 404 if error == "Worker not found" else 401
        raise HTTPException(status_code=status_code, detail=error)

    return {"message": "Password updated successfully"}


@router.post("/email", status_code=status.HTTP_200_OK, responses={400: {"description": "Email already in use or worker not found"}})
def change_email(
    request: UpdateEmailRequest,
    claims: Annotated[dict, Depends(_worker_claims)],
):
    """Updates the authenticated worker's email."""
    success, error = update_worker_email(
        _uow_factory,
        num_worker=claims["sub"],
        new_email=request.new_email,
    )
    if not success:
        raise HTTPException(status_code=400, detail=error or "Email already in use or worker not found")

    return {"message": "Email updated successfully"}


# ==================== ADMIN ENDPOINTS ====================

@router.post("", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED, responses={400: {"description": "Email or num_worker already in use"}})
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


@router.delete("/{num_worker}", status_code=status.HTTP_200_OK, responses={404: {"description": "Worker not found"}})
def deactivate_worker_endpoint(
    num_worker: Annotated[str, Path()],
):
    """Deactivates a worker."""
    worker = deactivate_worker(_uow_factory, num_worker=num_worker)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    return {"message": f"Worker {worker['name']} deactivated"}


@router.post("/{num_worker}/promote", status_code=status.HTTP_200_OK, responses={400: {"description": "Worker is not an operator or not found"}})
def promote_operator_to_manager(
    num_worker: Annotated[str, Path()],
    access_level: Annotated[str, Query()] = "basic",
):
    """Promotes an operator to manager."""
    manager = promote_to_manager(_uow_factory, num_worker=num_worker, access_level=access_level)
    if not manager:
        raise HTTPException(status_code=400, detail="Worker is not an operator or not found")

    return {"message": f"Operator promoted to manager with access level {access_level}"}
