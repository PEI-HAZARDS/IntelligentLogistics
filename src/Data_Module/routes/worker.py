"""
Worker Routes - Endpoints for operators and managers.
Consumed by: Backoffice frontend, API Gateway (authentication).
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from sqlalchemy.orm import Session
from pydantic import BaseModel

from models.pydantic_models import Worker, Manager, Operator, Shift, WorkerLoginRequest, WorkerLoginResponse
from services.worker_service import (
    authenticate_worker,
    get_worker_by_num_worker,
    get_worker_role,
    get_all_workers,
    get_operators,
    get_managers,
    get_operator_info,
    get_operator_current_shift,
    get_operator_shifts,
    get_operator_gate_dashboard,
    get_manager_info,
    get_manager_shifts,
    get_manager_overview,
    create_worker,
    update_worker_password,
    update_worker_email,
    deactivate_worker,
    promote_to_manager,
    hash_password
)
from db.postgres import get_db

router = APIRouter(prefix="/workers", tags=["Workers"])


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
def login(
    credentials: WorkerLoginRequest,
    db: Session = Depends(get_db)
):
    """
    Worker login (operator or manager).
    Returns token for authentication.
    """
    worker = authenticate_worker(
        db,
        email=credentials.email,
        password=credentials.password
    )
    
    if not worker:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials or account deactivated"
        )
    
    # MVP: generate simple token (in production use JWT)
    import secrets
    token = secrets.token_hex(32)
    
    return WorkerLoginResponse(
        token=token,
        num_worker=worker.num_worker,
        name=worker.name,
        email=worker.email,
        active=worker.active
    )


# ==================== OPERATOR ENDPOINTS ====================

@router.get("/operators", response_model=List[WorkerInfo])
def list_operators(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """Lists operators."""
    operators = get_operators(db, skip=skip, limit=limit)
    return [
        WorkerInfo(
            num_worker=op.worker.num_worker,
            name=op.worker.name,
            email=op.worker.email,
            role="operator",
            active=op.worker.active
        )
        for op in operators if op.worker
    ]


@router.get("/operators/me", response_model=Dict[str, Any])
def get_my_operator_info(
    num_worker: str = Query(..., description="Operator num_worker (from JWT)"),
    db: Session = Depends(get_db)
):
    """
    Gets authenticated operator information.
    In production: num_worker would come from JWT.
    """
    info = get_operator_info(db, num_worker)
    if not info:
        raise HTTPException(status_code=404, detail="Operator not found")
    return info


@router.get("/operators/{num_worker}")
def get_operator(
    num_worker: str = Path(..., description="Operator num_worker"),
    db: Session = Depends(get_db)
):
    """Gets information of a specific operator."""
    info = get_operator_info(db, num_worker)
    if not info:
        raise HTTPException(status_code=404, detail="Operator not found")
    return info


@router.get("/operators/{num_worker}/current-shift/{gate_id}")
def get_operator_shift(
    num_worker: str = Path(...),
    gate_id: int = Path(...),
    db: Session = Depends(get_db)
):
    """Gets operator's current shift for a gate."""
    shift = get_operator_current_shift(db, num_worker, gate_id)
    if not shift:
        return None
    
    return {
        "gate_id": shift.gate_id,
        "shift_type": shift.shift_type.name if shift.shift_type else None,
        "date": shift.date.isoformat(),
        "start_time": shift.start_time.isoformat() if hasattr(shift, 'start_time') and shift.start_time else None,
        "end_time": shift.end_time.isoformat() if hasattr(shift, 'end_time') and shift.end_time else None
    }


@router.get("/operators/{num_worker}/shifts")
def list_operator_shifts(
    num_worker: str = Path(...),
    gate_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """Lists shifts for an operator."""
    shifts = get_operator_shifts(db, num_worker, gate_id)
    return [
        {
            "gate_id": s.gate_id,
            "shift_type": s.shift_type.name if s.shift_type else None,
            "date": s.date.isoformat()
        }
        for s in shifts[:limit]
    ]


@router.get("/operators/{num_worker}/dashboard/{gate_id}", response_model=OperatorDashboard)
def get_operator_dashboard(
    num_worker: str = Path(...),
    gate_id: int = Path(...),
    db: Session = Depends(get_db)
):
    """
    Operator dashboard for a gate.
    Upcoming arrivals, alerts, statistics.
    """
    dashboard = get_operator_gate_dashboard(db, num_worker, gate_id)
    return OperatorDashboard(**dashboard)


# ==================== MANAGER ENDPOINTS ====================

@router.get("/managers", response_model=List[WorkerInfo])
def list_managers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """Lists managers."""
    managers = get_managers(db, skip=skip, limit=limit)
    return [
        WorkerInfo(
            num_worker=m.worker.num_worker,
            name=m.worker.name,
            email=m.worker.email,
            role="manager",
            active=m.worker.active
        )
        for m in managers if m.worker
    ]


@router.get("/managers/me", response_model=Dict[str, Any])
def get_my_manager_info(
    num_worker: str = Query(..., description="Manager num_worker (from JWT)"),
    db: Session = Depends(get_db)
):
    """
    Gets authenticated manager information.
    In production: num_worker would come from JWT.
    """
    info = get_manager_info(db, num_worker)
    if not info:
        raise HTTPException(status_code=404, detail="Manager not found")
    return info


@router.get("/managers/{num_worker}")
def get_manager(
    num_worker: str = Path(...),
    db: Session = Depends(get_db)
):
    """Gets information of a specific manager."""
    info = get_manager_info(db, num_worker)
    if not info:
        raise HTTPException(status_code=404, detail="Manager not found")
    return info


@router.get("/managers/{num_worker}/shifts")
def list_manager_shifts(
    num_worker: str = Path(...),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """Lists shifts supervised by a manager."""
    shifts = get_manager_shifts(db, num_worker)
    return [
        {
            "gate_id": s.gate_id,
            "shift_type": s.shift_type.name if s.shift_type else None,
            "date": s.date.isoformat(),
            "operator_num_worker": s.operator_num_worker
        }
        for s in shifts[:limit]
    ]


@router.get("/managers/{num_worker}/overview", response_model=ManagerOverview)
def get_manager_dashboard(
    num_worker: str = Path(...),
    db: Session = Depends(get_db)
):
    """
    Manager dashboard/overview.
    Gates, shifts, alerts, performance.
    """
    overview = get_manager_overview(db, num_worker)
    return ManagerOverview(**overview)


# ==================== GENERAL WORKER ENDPOINTS ====================

@router.get("", response_model=List[WorkerInfo])
def list_all_workers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    only_active: bool = Query(True),
    db: Session = Depends(get_db)
):
    """Lists all workers (backoffice)."""
    workers = get_all_workers(db, skip=skip, limit=limit, only_active=only_active)
    results = []
    for w in workers:
        role = get_worker_role(db, w.num_worker) or "unknown"
        results.append(WorkerInfo(
            num_worker=w.num_worker,
            name=w.name,
            email=w.email,
            role=role,
            active=w.active
        ))
    return results


@router.get("/{num_worker}", response_model=Dict[str, Any])
def get_worker(
    num_worker: str = Path(...),
    db: Session = Depends(get_db)
):
    """Gets worker data."""
    worker = get_worker_by_num_worker(db, num_worker)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    
    role = get_worker_role(db, num_worker) or "unknown"
    
    return {
        "num_worker": worker.num_worker,
        "name": worker.name,
        "email": worker.email,
        "phone": worker.phone,
        "role": role,
        "active": worker.active,
        "created_at": worker.created_at.isoformat() if worker.created_at else None
    }


# ==================== ACCOUNT MANAGEMENT ====================

@router.post("/password", status_code=status.HTTP_200_OK)
def change_password(
    request: UpdatePasswordRequest,
    num_worker: str = Query(..., description="Worker num_worker (from JWT)"),
    db: Session = Depends(get_db)
):
    """Updates worker's password."""
    worker = get_worker_by_num_worker(db, num_worker)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    
    # Verify current password
    from utils.hashing_pass import verify_password
    if not verify_password(request.current_password, worker.password_hash):
        raise HTTPException(status_code=401, detail="Current password incorrect")
    
    updated = update_worker_password(db, num_worker, request.new_password)
    if not updated:
        raise HTTPException(status_code=500, detail="Error updating password")
    
    return {"message": "Password updated successfully"}


@router.post("/email", status_code=status.HTTP_200_OK)
def change_email(
    request: UpdateEmailRequest,
    num_worker: str = Query(..., description="Worker num_worker (from JWT)"),
    db: Session = Depends(get_db)
):
    """Updates worker's email."""
    updated = update_worker_email(db, num_worker, request.new_email)
    if not updated:
        raise HTTPException(status_code=400, detail="Email already in use or worker not found")
    
    return {"message": "Email updated successfully"}


# ==================== ADMIN ENDPOINTS ====================

@router.post("", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
def create_new_worker(
    request: CreateWorkerRequest,
    db: Session = Depends(get_db)
):
    """
    Creates new worker (operator or manager).
    Requires admin authentication.
    """
    worker = create_worker(
        db,
        num_worker=request.num_worker,
        name=request.name,
        email=request.email,
        password=request.password,
        role=request.role,
        access_level=request.access_level,
        phone=request.phone
    )
    
    if not worker:
        raise HTTPException(status_code=400, detail="Email or num_worker already in use")
    
    return {
        "num_worker": worker.num_worker,
        "name": worker.name,
        "email": worker.email,
        "role": request.role,
        "active": worker.active
    }


@router.delete("/{num_worker}", status_code=status.HTTP_200_OK)
def deactivate_worker_endpoint(
    num_worker: str = Path(...),
    db: Session = Depends(get_db)
):
    """Deactivates a worker."""
    worker = deactivate_worker(db, num_worker)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    
    return {"message": f"Worker {worker.name} deactivated"}


@router.post("/{num_worker}/promote", status_code=status.HTTP_200_OK)
def promote_operator_to_manager(
    num_worker: str = Path(...),
    access_level: str = Query("basic"),
    db: Session = Depends(get_db)
):
    """Promotes an operator to manager."""
    manager = promote_to_manager(db, num_worker, access_level)
    if not manager:
        raise HTTPException(status_code=400, detail="Worker is not an operator or not found")
    
    return {"message": f"Operator promoted to manager with access level {access_level}"}
