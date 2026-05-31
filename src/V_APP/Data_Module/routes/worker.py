"""
Worker Routes - Endpoints for operators and managers.
Consumed by: Backoffice frontend, API Gateway (authentication).

CQRS: GET endpoints read from MongoDB. POST/PATCH/DELETE use UoW + Outbox.
Shift queries use PostgreSQL (shift data not yet projected to MongoDB).
"""

from typing import Annotated, List, Optional, Dict, Any
from datetime import date, datetime
import csv, io
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path, UploadFile, File
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
from infrastructure.persistence.sql_models import Shift as ShiftORM, Visit as VisitORM, Operator, Manager, Gate as GateORM, ShiftType, ShiftTemplate as ShiftTemplateORM
from sqlalchemy.exc import IntegrityError
from utils.auth_token import generate_internal_jwt, require_role
from infrastructure.persistence.redis import set_session
from utils.shift_utils import current_shift_type, parse_shift_type, active_shift_window, shift_order_key
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


class ShiftCreateRequest(BaseModel):
    gate_id: int
    shift_type: str  # MORNING | AFTERNOON | NIGHT
    date: date
    operator_num_worker: Optional[str] = None
    manager_num_worker: Optional[str] = None


class ShiftUpdateRequest(BaseModel):
    operator_num_worker: Optional[str] = None
    manager_num_worker: Optional[str] = None


# ==================== AUTH ENDPOINTS ====================

@router.post("/login", response_model=WorkerLoginResponse, responses={401: {"description": "Invalid credentials or account deactivated"}})
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

@router.get("/by-email/{email}", responses={404: {"description": "Worker not found or deactivated"}})
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
    date_from: Annotated[Optional[date], Query(description="Range start (inclusive) — for the calendar")] = None,
    date_to: Annotated[Optional[date], Query(description="Range end (inclusive) — for the calendar")] = None,
    shift_type: Annotated[Optional[str], Query(description="Filter by shift type (MORNING/AFTERNOON/NIGHT)")] = None,
    gate_id: Annotated[Optional[int], Query(description="Filter by gate")] = None,
):
    """
    Lists shifts with operator/gate details. Used by the Manager ShiftsPage.

    Pass ``date_from``/``date_to`` for a date range (calendar month view), or
    ``target_date`` (default today) for a single day.

    PostgreSQL — shift data not yet projected to MongoDB (Guardrail 5).
    """
    use_range = date_from is not None and date_to is not None
    query = (
        db.query(ShiftORM)
        .options(
            joinedload(ShiftORM.gate),
            joinedload(ShiftORM.operator).joinedload(Operator.worker),
            joinedload(ShiftORM.manager).joinedload(Manager.worker),
        )
    )
    if use_range:
        query = query.filter(ShiftORM.date >= date_from, ShiftORM.date <= date_to)
    else:
        target = target_date or date.today()
        query = query.filter(ShiftORM.date == target)

    if gate_id is not None:
        query = query.filter(ShiftORM.gate_id == gate_id)
    if shift_type:
        from utils.shift_utils import parse_shift_type
        try:
            parsed = parse_shift_type(shift_type)
            query = query.filter(ShiftORM.shift_type == parsed)
        except ValueError:
            pass

    shifts = query.order_by(ShiftORM.date, ShiftORM.gate_id, ShiftORM.shift_type).all()

    # Single GROUP BY query for all visit counts (replaces per-shift COUNT)
    visit_q = db.query(
        VisitORM.shift_gate_id,
        VisitORM.shift_type,
        VisitORM.shift_date,
        sa_func.count().label("cnt"),
    )
    if use_range:
        visit_q = visit_q.filter(VisitORM.shift_date >= date_from, VisitORM.shift_date <= date_to)
    else:
        visit_q = visit_q.filter(VisitORM.shift_date == (target_date or date.today()))
    visit_counts_rows = visit_q.group_by(
        VisitORM.shift_gate_id, VisitORM.shift_type, VisitORM.shift_date
    ).all()
    visit_count_map = {(r.shift_gate_id, r.shift_type, r.shift_date): r.cnt for r in visit_counts_rows}

    active_date, active_type = active_shift_window()
    active_key = shift_order_key(active_date, active_type)

    result = []
    for s in shifts:
        visit_count = visit_count_map.get((s.gate_id, s.shift_type, s.date), 0)
        status = _shift_status(s, active_date, active_type, active_key)
        result.append(_serialize_shift_row(s, status, visit_count))

    return result


def _shift_status(s, active_date, active_type, active_key) -> str:
    """Lifecycle label for a shift relative to the window running now.

    Midnight-aware via ``active_shift_window`` — a NIGHT shift in progress after
    midnight is matched against its real (previous-day) start date, not today.
    """
    if not s.operator_num_worker:
        return "inactive"
    if s.date == active_date and s.shift_type == active_type:
        return "active"
    if shift_order_key(s.date, s.shift_type) < active_key:
        return "completed"
    return "pending"


def _serialize_shift_row(s, status: str, visit_count: int) -> Dict[str, Any]:
    return {
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
        "status": status,
    }


@router.get("/shifts/active", response_model=List[Dict[str, Any]])
def list_active_shifts(db: Annotated[Session, Depends(get_db)]):
    """Shifts running *right now* across all gates — midnight-aware.

    Unlike ``GET /shifts`` (a single calendar date), this resolves the NIGHT
    shift that spans midnight to its real start date, so the manager dashboard
    always shows the shift actually in progress (not yesterday's marked done).
    """
    active_date, active_type = active_shift_window()
    shifts = (
        db.query(ShiftORM)
        .options(
            joinedload(ShiftORM.gate),
            joinedload(ShiftORM.operator).joinedload(Operator.worker),
            joinedload(ShiftORM.manager).joinedload(Manager.worker),
        )
        .filter(ShiftORM.date == active_date, ShiftORM.shift_type == active_type)
        .order_by(ShiftORM.gate_id)
        .all()
    )
    visit_rows = (
        db.query(VisitORM.shift_gate_id, sa_func.count().label("cnt"))
        .filter(VisitORM.shift_date == active_date, VisitORM.shift_type == active_type)
        .group_by(VisitORM.shift_gate_id)
        .all()
    )
    visit_count_map = {r.shift_gate_id: r.cnt for r in visit_rows}

    return [
        _serialize_shift_row(s, "active" if s.operator_num_worker else "inactive",
                         visit_count_map.get(s.gate_id, 0))
        for s in shifts
    ]


# ==================== GATES LISTING ====================

@router.get("/gates", response_model=List[Dict[str, Any]])
def list_gates(db: Annotated[Session, Depends(get_db)]):
    """Lists all active gates. Used by shift creation modals."""
    gates = db.query(GateORM).filter(GateORM.estado == "Ativo").order_by(GateORM.id).all()
    return [{"id": g.id, "label": g.label} for g in gates]


# ==================== SHIFT CRUD ====================

@router.post("/shifts", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED, responses={400: {"description": "Invalid shift_type"}, 404: {"description": "Gate not found or inactive"}, 409: {"description": "Shift already exists or operator already assigned"}})
def create_shift(
    body: ShiftCreateRequest,
    db: Annotated[Session, Depends(get_db)],
):
    """
    Creates a new shift. Validates:
    - Gate exists and is active.
    - No existing shift for (gate_id, shift_type, date).
    - Operator not already assigned to any shift on the same date.
    """
    try:
        parsed_type = parse_shift_type(body.shift_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid shift_type: {body.shift_type}")

    gate = db.query(GateORM).filter(GateORM.id == body.gate_id, GateORM.estado == "Ativo").first()
    if not gate:
        raise HTTPException(status_code=404, detail=f"Gate {body.gate_id} not found or inactive")

    existing = db.query(ShiftORM).filter(
        ShiftORM.gate_id == body.gate_id,
        ShiftORM.shift_type == parsed_type,
        ShiftORM.date == body.date,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Shift already exists for this gate/type/date")

    if body.operator_num_worker:
        conflict = db.query(ShiftORM).filter(
            ShiftORM.date == body.date,
            ShiftORM.operator_num_worker == body.operator_num_worker,
        ).first()
        if conflict:
            raise HTTPException(
                status_code=409,
                detail=f"Operator {body.operator_num_worker} already assigned to a shift on {body.date}",
            )

    shift = ShiftORM(
        gate_id=body.gate_id,
        shift_type=parsed_type,
        date=body.date,
        operator_num_worker=body.operator_num_worker or None,
        manager_num_worker=body.manager_num_worker or None,
    )
    db.add(shift)
    db.commit()
    db.refresh(shift)

    db.expire_all()
    shift = db.query(ShiftORM).options(
        joinedload(ShiftORM.gate),
        joinedload(ShiftORM.operator).joinedload(Operator.worker),
    ).filter(
        ShiftORM.gate_id == body.gate_id,
        ShiftORM.shift_type == parsed_type,
        ShiftORM.date == body.date,
    ).first()

    return {
        "id": f"{shift.gate_id}-{shift.shift_type.name}-{shift.date.isoformat()}",
        "gateId": shift.gate_id,
        "gateName": shift.gate.label if shift.gate else f"Gate {shift.gate_id}",
        "shiftType": shift.shift_type.name,
        "date": shift.date.isoformat(),
        "operatorId": shift.operator_num_worker or "",
        "operatorName": shift.operator.worker.name if shift.operator and shift.operator.worker else "",
        "managerId": shift.manager_num_worker or "",
        "status": "pending",
    }


@router.put("/shifts/{gate_id}/{shift_type}/{shift_date}", response_model=Dict[str, Any], responses={400: {"description": "Invalid shift_type"}, 404: {"description": "Shift not found"}, 409: {"description": "Operator already assigned to another shift on this date"}})
def update_shift(
    gate_id: Annotated[int, Path()],
    shift_type: Annotated[str, Path()],
    shift_date: Annotated[date, Path()],
    body: ShiftUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
):
    """
    Updates operator/manager assignment for an existing shift.
    Validates operator not already assigned elsewhere on the same date.
    """
    try:
        parsed_type = parse_shift_type(shift_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid shift_type: {shift_type}")

    shift = db.query(ShiftORM).filter(
        ShiftORM.gate_id == gate_id,
        ShiftORM.shift_type == parsed_type,
        ShiftORM.date == shift_date,
    ).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")

    new_op = body.operator_num_worker if body.operator_num_worker is not None else shift.operator_num_worker
    if new_op and new_op != shift.operator_num_worker:
        conflict = db.query(ShiftORM).filter(
            ShiftORM.date == shift_date,
            ShiftORM.operator_num_worker == new_op,
            ~((ShiftORM.gate_id == gate_id) & (ShiftORM.shift_type == parsed_type)),
        ).first()
        if conflict:
            raise HTTPException(
                status_code=409,
                detail=f"Operator {new_op} already assigned to a shift on {shift_date}",
            )

    if body.operator_num_worker is not None:
        shift.operator_num_worker = body.operator_num_worker or None
    if body.manager_num_worker is not None:
        shift.manager_num_worker = body.manager_num_worker or None

    db.commit()
    db.refresh(shift)

    db.expire_all()
    shift = db.query(ShiftORM).options(
        joinedload(ShiftORM.gate),
        joinedload(ShiftORM.operator).joinedload(Operator.worker),
    ).filter(
        ShiftORM.gate_id == gate_id,
        ShiftORM.shift_type == parsed_type,
        ShiftORM.date == shift_date,
    ).first()

    return {
        "id": f"{shift.gate_id}-{shift.shift_type.name}-{shift.date.isoformat()}",
        "gateId": shift.gate_id,
        "gateName": shift.gate.label if shift.gate else f"Gate {shift.gate_id}",
        "shiftType": shift.shift_type.name,
        "date": shift.date.isoformat(),
        "operatorId": shift.operator_num_worker or "",
        "operatorName": shift.operator.worker.name if shift.operator and shift.operator.worker else "",
        "managerId": shift.manager_num_worker or "",
    }


@router.delete("/shifts/{gate_id}/{shift_type}/{shift_date}", status_code=status.HTTP_204_NO_CONTENT, responses={400: {"description": "Invalid shift_type"}, 404: {"description": "Shift not found"}, 409: {"description": "Cannot delete an active shift"}})
def delete_shift(
    gate_id: Annotated[int, Path()],
    shift_type: Annotated[str, Path()],
    shift_date: Annotated[date, Path()],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Deletes a shift. Refuses if shift is currently active (today + current shift type).
    """
    try:
        parsed_type = parse_shift_type(shift_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid shift_type: {shift_type}")

    shift = db.query(ShiftORM).filter(
        ShiftORM.gate_id == gate_id,
        ShiftORM.shift_type == parsed_type,
        ShiftORM.date == shift_date,
    ).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")

    if shift.date == date.today() and shift.shift_type == current_shift_type():
        raise HTTPException(status_code=409, detail="Cannot delete an active shift")

    db.delete(shift)
    db.commit()


# ==================== RECURRING SHIFT TEMPLATES ====================

class ShiftTemplateRequest(BaseModel):
    gate_id: int
    shift_type: str
    weekdays: str = "1111100"               # Mon–Fri by default
    operator_num_worker: Optional[str] = None
    manager_num_worker: Optional[str] = None
    valid_from: Optional[date] = None        # default: today
    valid_until: Optional[date] = None
    active: bool = True


class ShiftTemplateUpdate(BaseModel):
    weekdays: Optional[str] = None
    operator_num_worker: Optional[str] = None
    manager_num_worker: Optional[str] = None
    valid_until: Optional[date] = None
    active: Optional[bool] = None


def _serialize_template(t: ShiftTemplateORM) -> Dict[str, Any]:
    return {
        "id": t.id,
        "gate_id": t.gate_id,
        "gate_name": t.gate.label if t.gate else f"Gate {t.gate_id}",
        "shift_type": t.shift_type.name,
        "weekdays": t.weekdays,
        "operator_num_worker": t.operator_num_worker or "",
        "manager_num_worker": t.manager_num_worker or "",
        "valid_from": t.valid_from.isoformat() if t.valid_from else None,
        "valid_until": t.valid_until.isoformat() if t.valid_until else None,
        "active": t.active,
    }


def _validate_weekdays(mask: str) -> None:
    if not isinstance(mask, str) or len(mask) != 7 or any(c not in "01" for c in mask):
        raise HTTPException(status_code=400, detail="weekdays must be a 7-char '0'/'1' mask (Mon..Sun)")


@router.get("/shifts/templates", response_model=List[Dict[str, Any]])
def list_shift_templates(
    db: Annotated[Session, Depends(get_db)],
    include_inactive: Annotated[bool, Query()] = False,
):
    """List recurring-shift templates (active only unless include_inactive)."""
    q = db.query(ShiftTemplateORM).options(joinedload(ShiftTemplateORM.gate))
    if not include_inactive:
        q = q.filter(ShiftTemplateORM.active.is_(True))
    rows = q.order_by(ShiftTemplateORM.gate_id, ShiftTemplateORM.shift_type).all()
    return [_serialize_template(t) for t in rows]


@router.post("/shifts/templates", status_code=status.HTTP_201_CREATED, responses={400: {"description": "Invalid shift_type or weekdays mask"}, 404: {"description": "Gate not found or inactive"}, 409: {"description": "Matching template already exists"}})
def create_shift_template(
    body: ShiftTemplateRequest,
    db: Annotated[Session, Depends(get_db)],
):
    """Create a recurring-shift template. The scheduler expands it into Shift rows."""
    try:
        parsed_type = parse_shift_type(body.shift_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid shift_type: {body.shift_type}")
    _validate_weekdays(body.weekdays)

    gate = db.query(GateORM).filter(GateORM.id == body.gate_id, GateORM.estado == "Ativo").first()
    if not gate:
        raise HTTPException(status_code=404, detail=f"Gate {body.gate_id} not found or inactive")

    tpl = ShiftTemplateORM(
        gate_id=body.gate_id,
        shift_type=parsed_type,
        weekdays=body.weekdays,
        operator_num_worker=body.operator_num_worker or None,
        manager_num_worker=body.manager_num_worker or None,
        valid_from=body.valid_from or date.today(),
        valid_until=body.valid_until,
        active=body.active,
    )
    db.add(tpl)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A matching template already exists for this gate/type/operator/start date")
    db.refresh(tpl)
    db.refresh(tpl, attribute_names=["gate"])
    return _serialize_template(tpl)


@router.patch("/shifts/templates/{template_id}", responses={400: {"description": "Invalid weekdays mask"}, 404: {"description": "Template not found"}})
def update_shift_template(
    template_id: Annotated[int, Path()],
    body: ShiftTemplateUpdate,
    db: Annotated[Session, Depends(get_db)],
):
    """Update a template (toggle active, change staffing, end it, edit weekdays)."""
    tpl = db.query(ShiftTemplateORM).options(joinedload(ShiftTemplateORM.gate)).filter(ShiftTemplateORM.id == template_id).first()
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")

    if body.weekdays is not None:
        _validate_weekdays(body.weekdays)
        tpl.weekdays = body.weekdays
    if body.operator_num_worker is not None:
        tpl.operator_num_worker = body.operator_num_worker or None
    if body.manager_num_worker is not None:
        tpl.manager_num_worker = body.manager_num_worker or None
    if body.valid_until is not None:
        tpl.valid_until = body.valid_until
    if body.active is not None:
        tpl.active = body.active

    db.commit()
    db.refresh(tpl)
    return _serialize_template(tpl)


@router.delete("/shifts/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT, responses={404: {"description": "Template not found"}})
def delete_shift_template(
    template_id: Annotated[int, Path()],
    db: Annotated[Session, Depends(get_db)],
):
    """Delete a template. Already-generated shifts are left untouched."""
    tpl = db.query(ShiftTemplateORM).filter(ShiftTemplateORM.id == template_id).first()
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    db.delete(tpl)
    db.commit()


@router.post("/shifts/generate", status_code=status.HTTP_200_OK)
def generate_shifts(
    horizon_days: Annotated[int, Query(ge=1, le=90, description="Days ahead to materialise")] = 14,
):
    """Materialise concrete shifts from active templates for the next N days.

    Idempotent — existing shifts are skipped. Called on-demand here and on a
    schedule by ``scripts/shift_scheduler.py``.
    """
    from application.use_cases.shift_scheduler import generate_shifts_from_templates
    return generate_shifts_from_templates(horizon_days)


@router.post("/shifts/bulk", status_code=status.HTTP_200_OK, responses={400: {"description": "File not UTF-8 encoded or missing required CSV columns"}})
def bulk_create_shifts(
    file: Annotated[UploadFile, File(description="CSV: gate_id,shift_type,date,operator_num_worker,manager_num_worker")],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Bulk-create shifts from a CSV file.
    Required columns: gate_id, shift_type, date
    Optional columns: operator_num_worker, manager_num_worker

    Returns { created, skipped, errors } — never aborts the whole batch on a single bad row.
    """
    content = file.file.read()
    try:
        text = content.decode("utf-8-sig")  # handle BOM from Excel exports
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded")

    reader = csv.DictReader(io.StringIO(text))
    required = {"gate_id", "shift_type", "date"}
    if not required.issubset(set(reader.fieldnames or [])):
        raise HTTPException(
            status_code=400,
            detail=f"CSV must contain columns: {', '.join(sorted(required))}",
        )

    created, skipped = 0, 0
    errors: list[dict] = []

    for row_num, row in enumerate(reader, start=2):  # start=2: row 1 is header
        gate_id_raw    = row.get("gate_id", "").strip()
        shift_type_raw = row.get("shift_type", "").strip().upper()
        date_raw       = row.get("date", "").strip()
        operator_raw   = row.get("operator_num_worker", "").strip() or None
        manager_raw    = row.get("manager_num_worker", "").strip() or None

        # Basic validation
        if not gate_id_raw or not shift_type_raw or not date_raw:
            errors.append({"row": row_num, "reason": "Missing required field (gate_id, shift_type, or date)"})
            continue

        try:
            gate_id = int(gate_id_raw)
        except ValueError:
            errors.append({"row": row_num, "reason": f"gate_id must be an integer, got '{gate_id_raw}'"})
            continue

        try:
            parsed_type = parse_shift_type(shift_type_raw)
        except ValueError:
            errors.append({"row": row_num, "reason": f"Invalid shift_type '{shift_type_raw}' — use MORNING, AFTERNOON, or NIGHT"})
            continue

        try:
            parsed_date = date.fromisoformat(date_raw)
        except ValueError:
            errors.append({"row": row_num, "reason": f"Invalid date '{date_raw}' — use YYYY-MM-DD"})
            continue

        # Gate must exist and be active
        gate = db.query(GateORM).filter(GateORM.id == gate_id, GateORM.estado == "Ativo").first()
        if not gate:
            errors.append({"row": row_num, "reason": f"Gate {gate_id} not found or inactive"})
            continue

        # Skip duplicate (gate, type, date)
        existing = db.query(ShiftORM).filter(
            ShiftORM.gate_id == gate_id,
            ShiftORM.shift_type == parsed_type,
            ShiftORM.date == parsed_date,
        ).first()
        if existing:
            skipped += 1
            continue

        # Operator conflict (same operator, same date)
        if operator_raw:
            conflict = db.query(ShiftORM).filter(
                ShiftORM.date == parsed_date,
                ShiftORM.operator_num_worker == operator_raw,
            ).first()
            if conflict:
                errors.append({
                    "row": row_num,
                    "reason": f"Operator {operator_raw} already assigned to a shift on {date_raw}",
                })
                continue

        db.add(ShiftORM(
            gate_id=gate_id,
            shift_type=parsed_type,
            date=parsed_date,
            operator_num_worker=operator_raw,
            manager_num_worker=manager_raw,
        ))
        created += 1

    if created > 0:
        db.commit()

    return {"created": created, "skipped": skipped, "errors": errors}


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
    email: Annotated[str, Query(description="Worker email from JWT sub claim")],
):
    """Gets authenticated operator information by email (resolved from JWT by the gateway)."""
    with _uow_factory() as uow:
        worker = uow.workers.get_by_email_active(email)
    if not worker:
        raise HTTPException(status_code=404, detail="Operator not found")
    info = get_operator_info(worker["num_worker"])
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
    email: Annotated[str, Query(description="Worker email from JWT sub claim")],
):
    """Gets authenticated manager information by email (resolved from JWT by the gateway)."""
    with _uow_factory() as uow:
        worker = uow.workers.get_by_email_active(email)
    if not worker:
        raise HTTPException(status_code=404, detail="Manager not found")
    info = get_manager_info(worker["num_worker"])
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


@router.post("/password", status_code=status.HTTP_200_OK, responses={401: {"description": "Current password is incorrect"}, 404: {"description": "Worker not found"}})
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
