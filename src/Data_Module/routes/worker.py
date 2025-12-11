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
    get_worker_by_nif,
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
    nif: str
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
    nif: str
    name: str
    email: str
    role: str
    active: bool


class OperatorDashboard(BaseModel):
    """Operator dashboard."""
    operator_nif: str
    gate_id: int
    date: str
    upcoming_arrivals: List[Dict[str, Any]]
    stats: Dict[str, int]


class ManagerOverview(BaseModel):
    """Manager overview."""
    manager_nif: str
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
        nif=worker.nif,
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
            nif=op.worker.nif,
            name=op.worker.name,
            email=op.worker.email,
            role="operator",
            active=op.worker.active
        )
        for op in operators if op.worker
    ]


@router.get("/operators/me", response_model=Dict[str, Any])
def get_my_operator_info(
    nif: str = Query(..., description="Operator NIF (from JWT)"),
    db: Session = Depends(get_db)
):
    """
    Gets authenticated operator information.
    In production: nif would come from JWT.
    """
    info = get_operator_info(db, nif)
    if not info:
        raise HTTPException(status_code=404, detail="Operator not found")
    return info


@router.get("/operators/{nif}")
def get_operator(
    nif: str = Path(..., description="Operator NIF"),
    db: Session = Depends(get_db)
):
    """Gets information of a specific operator."""
    info = get_operator_info(db, nif)
    if not info:
        raise HTTPException(status_code=404, detail="Operator not found")
    return info


@router.get("/operators/{nif}/current-shift/{gate_id}")
def get_operator_shift(
    nif: str = Path(...),
    gate_id: int = Path(...),
    db: Session = Depends(get_db)
):
    """Gets operator's current shift for a gate."""
    shift = get_operator_current_shift(db, nif, gate_id)
    if not shift:
        return None
    
    return {
        "id": shift.id,
        "date": shift.date.isoformat(),
        "shift_type": shift.shift_type.name if shift.shift_type else None,
        "start_time": shift.start_time.isoformat() if shift.start_time else None,
        "end_time": shift.end_time.isoformat() if shift.end_time else None,
        "gate_id": shift.gate_id
    }


@router.get("/operators/{nif}/shifts")
def list_operator_shifts(
    nif: str = Path(...),
    gate_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """Lists shifts for an operator."""
    shifts = get_operator_shifts(db, nif, gate_id)
    return [
        {
            "id": s.id,
            "date": s.date.isoformat(),
            "shift_type": s.shift_type.name if s.shift_type else None,
            "gate_id": s.gate_id
        }
        for s in shifts[:limit]
    ]


@router.get("/operators/{nif}/dashboard/{gate_id}", response_model=OperatorDashboard)
def get_operator_dashboard(
    nif: str = Path(...),
    gate_id: int = Path(...),
    db: Session = Depends(get_db)
):
    """
    Operator dashboard for a gate.
    Upcoming arrivals, alerts, statistics.
    """
    dashboard = get_operator_gate_dashboard(db, nif, gate_id)
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
            nif=m.worker.nif,
            name=m.worker.name,
            email=m.worker.email,
            role="manager",
            active=m.worker.active
        )
        for m in managers if m.worker
    ]


@router.get("/managers/me", response_model=Dict[str, Any])
def get_my_manager_info(
    nif: str = Query(..., description="Manager NIF (from JWT)"),
    db: Session = Depends(get_db)
):
    """
    Gets authenticated manager information.
    In production: nif would come from JWT.
    """
    info = get_manager_info(db, nif)
    if not info:
        raise HTTPException(status_code=404, detail="Manager not found")
    return info


@router.get("/managers/{nif}")
def get_manager(
    nif: str = Path(...),
    db: Session = Depends(get_db)
):
    """Gets information of a specific manager."""
    info = get_manager_info(db, nif)
    if not info:
        raise HTTPException(status_code=404, detail="Manager not found")
    return info


@router.get("/managers/{nif}/shifts")
def list_manager_shifts(
    nif: str = Path(...),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """Lists shifts supervised by a manager."""
    shifts = get_manager_shifts(db, nif)
    return [
        {
            "id": s.id,
            "date": s.date.isoformat(),
            "shift_type": s.shift_type.name if s.shift_type else None,
            "gate_id": s.gate_id,
            "operator_nif": s.operator_nif
        }
        for s in shifts[:limit]
    ]


@router.get("/managers/{nif}/overview", response_model=ManagerOverview)
def get_manager_dashboard(
    nif: str = Path(...),
    db: Session = Depends(get_db)
):
    """
    Manager dashboard/overview.
    Gates, shifts, alerts, performance.
    """
    overview = get_manager_overview(db, nif)
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
        role = get_worker_role(db, w.nif) or "unknown"
        results.append(WorkerInfo(
            nif=w.nif,
            name=w.name,
            email=w.email,
            role=role,
            active=w.active
        ))
    return results


@router.get("/{nif}", response_model=Dict[str, Any])
def get_worker(
    nif: str = Path(...),
    db: Session = Depends(get_db)
):
    """Gets worker data."""
    worker = get_worker_by_nif(db, nif)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    
    role = get_worker_role(db, nif) or "unknown"
    
    return {
        "nif": worker.nif,
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
    nif: str = Query(..., description="Worker NIF (from JWT)"),
    db: Session = Depends(get_db)
):
    """Updates worker's password."""
    worker = get_worker_by_nif(db, nif)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    
    # Verify current password
    from utils.hashing_pass import verify_password
    if not verify_password(request.current_password, worker.password_hash):
        raise HTTPException(status_code=401, detail="Current password incorrect")
    
    updated = update_worker_password(db, nif, request.new_password)
    if not updated:
        raise HTTPException(status_code=500, detail="Error updating password")
    
    return {"message": "Password updated successfully"}


@router.post("/email", status_code=status.HTTP_200_OK)
def change_email(
    request: UpdateEmailRequest,
    nif: str = Query(..., description="Worker NIF (from JWT)"),
    db: Session = Depends(get_db)
):
    """Updates worker's email."""
    updated = update_worker_email(db, nif, request.new_email)
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
        nif=request.nif,
        name=request.name,
        email=request.email,
        password=request.password,
        role=request.role,
        access_level=request.access_level,
        phone=request.phone
    )
    
    if not worker:
        raise HTTPException(status_code=400, detail="Email or NIF already in use")
    
    return {
        "nif": worker.nif,
        "name": worker.name,
        "email": worker.email,
        "role": request.role,
        "active": worker.active
    }


@router.delete("/{nif}", status_code=status.HTTP_200_OK)
def deactivate_worker_endpoint(
    nif: str = Path(...),
    db: Session = Depends(get_db)
):
    """Deactivates a worker."""
    worker = deactivate_worker(db, nif)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    
    return {"message": f"Worker {worker.name} deactivated"}


@router.post("/{nif}/promote", status_code=status.HTTP_200_OK)
def promote_operator_to_manager(
    nif: str = Path(...),
    access_level: str = Query("basic"),
    db: Session = Depends(get_db)
):
    """Promotes an operator to manager."""
    manager = promote_to_manager(db, nif, access_level)
    if not manager:
        raise HTTPException(status_code=400, detail="Worker is not an operator or not found")
    
    return {"message": f"Operator promoted to manager with access level {access_level}"}
