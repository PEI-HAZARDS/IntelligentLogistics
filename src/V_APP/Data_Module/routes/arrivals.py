"""
Arrivals Routes - Endpoints for appointment and visit management.
Consumed by: Operator frontend, Decision Engine, Driver app.

Reads directly from PostgreSQL (source of truth) with Redis caching.
"""

from typing import Annotated, List, Optional, Dict, Any, Generic, TypeVar
from datetime import date, datetime, timezone, timedelta
import csv, io, uuid
from fastapi import APIRouter, Depends, File, HTTPException, Query, Path, UploadFile
from sqlalchemy.orm import Session, selectinload, joinedload
from pydantic import BaseModel
from loguru import logger

from application.schemas import (
    Appointment, AppointmentManagerView, AppointmentStatusUpdate, Visit, VisitStatusUpdate, ShiftTypeEnum
)
from application.queries.arrival_queries import (
    get_all_appointments,
    count_all_appointments,
    get_appointment_by_id,
    get_appointment_detail,
    get_appointment_by_arrival_id,
    get_appointments_by_license_plate,
    get_appointments_count_by_status,
    get_next_appointments,
    get_avg_permanence_minutes,
)
from application.queries.manager_statistics_queries import (
    get_transport_stats as _get_transport_stats_canonical,
)
from application.use_cases.appointment_commands import (
    cmd_update_status,
    cmd_process_decision,
    cmd_flag_highway_infraction,
    cmd_create_visit,
    cmd_update_visit_state,
    cmd_review_infraction,
)
from application.queries.cache_queries import get_or_cache
from application.queries.arrival_queries import _APPOINTMENT_EAGER_LOADS
from infrastructure.persistence.redis import get_cached_appointment, cache_appointment
from infrastructure.persistence.sql_models import Visit as VisitORM, Shift as ShiftORM, Operator, Manager, Appointment as AppointmentORM

T = TypeVar("T")

class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    limit: int
    pages: int
from infrastructure.persistence.sql_models import ShiftType
from infrastructure.persistence.postgres import get_db, SessionLocal
from infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from utils.shift_utils import parse_shift_type


def _uow_factory():
    """Return a new UoW context manager (Guardrail 6)."""
    return SqlAlchemyUnitOfWork(SessionLocal)


def _load_visit(db: Session, appointment_id: int) -> VisitORM:
    return (
        db.query(VisitORM)
        .options(
            selectinload(VisitORM.appointment).options(*_APPOINTMENT_EAGER_LOADS),
            selectinload(VisitORM.shift).options(
                joinedload(ShiftORM.gate),
                joinedload(ShiftORM.operator).joinedload(Operator.worker),
                joinedload(ShiftORM.manager).joinedload(Manager.worker),
            ),
        )
        .filter(VisitORM.appointment_id == appointment_id)
        .first()
    )

router = APIRouter(prefix="/arrivals", tags=["Arrivals"])


def _mask_driver_if_infraction(appt: Appointment) -> Appointment:
    """Privacy by Design — infraction is associated with the truck, not the driver.
    Nullifies driver identity fields so the logistics manager cannot correlate an
    infraction with a specific driver through the port-facing API."""
    if appt.highway_infraction:
        return appt.model_copy(update={"driver_license": None, "driver": None})
    return appt


# ==================== LOCAL MODELS ====================

class CreateVisitRequest(BaseModel):
    """Request to create a visit with composite shift FK."""
    shift_gate_id: int
    shift_type: str  # "MORNING", "AFTERNOON", "NIGHT"
    shift_date: date


# ==================== GET ENDPOINTS ====================

@router.get("", response_model=PaginatedResponse[AppointmentManagerView], responses={400: {"description": "Invalid shift type"}})
def list_arrivals(
    page: Annotated[int, Query(ge=1, description="Page number (1-based)")] = 1,
    limit: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
    gate_id: Annotated[Optional[int], Query(description="Filter by entry gate")] = None,
    shift_gate_id: Annotated[Optional[int], Query(description="Filter by shift gate")] = None,
    shift_type: Annotated[Optional[str], Query(description="Filter by shift type")] = None,
    shift_date: Annotated[Optional[date], Query(description="Filter by shift date")] = None,
    status: Annotated[Optional[str], Query(description="Filter by single status")] = None,
    statuses: Annotated[Optional[str], Query(description="Filter by multiple statuses (comma-separated)")] = None,
    scheduled_date: Annotated[Optional[date], Query(description="Filter by scheduled date")] = None,
    search: Annotated[Optional[str], Query(description="Search by license plate or driver name")] = None,
    highway_infraction: Annotated[Optional[bool], Query(description="Filter by highway infraction flag")] = None,
    db: Annotated[Session, Depends(get_db)] = None,
):
    """Lists appointments with server-side pagination, filtering and search."""
    parsed_shift_type = None
    if shift_type:
        try:
            parsed_shift_type = parse_shift_type(shift_type)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    skip = (page - 1) * limit

    final_status = status
    if statuses:
        if status:
            logger.warning(
                "Both status and statuses provided. Using statuses='%s', ignoring status='%s'",
                statuses, status,
            )
        final_status = statuses

    filter_kwargs = {
        "gate_id": gate_id, "shift_gate_id": shift_gate_id,
        "shift_type": parsed_shift_type, "shift_date": shift_date,
        "status": final_status, "scheduled_date": scheduled_date,
        "search": search, "highway_infraction": highway_infraction,
    }
    total = count_all_appointments(db, **filter_kwargs)
    appointments = get_all_appointments(db, skip=skip, limit=limit, **filter_kwargs)

    return PaginatedResponse(
        items=[_mask_driver_if_infraction(Appointment.model_validate(a)) for a in appointments],
        total=total, page=page, limit=limit,
        pages=max(1, -(-total // limit)),
    )


@router.get("/stats", response_model=Dict[str, int])
def get_arrivals_stats(
    gate_id: Annotated[Optional[int], Query(description="Filter by gate")] = None,
    target_date: Annotated[Optional[date], Query(description="Date to query (default: today)")] = None,
    db: Annotated[Session, Depends(get_db)] = None,
):
    """Arrival statistics by status. Result cached 30s in Redis."""
    today = (target_date or date.today()).isoformat()
    cache_key = f"stats:gate:{gate_id or 'all'}:{today}"

    def _compute():
        return get_appointments_count_by_status(db, gate_id=gate_id, target_date=target_date)

    return get_or_cache(key=cache_key, ttl=30, fallback=_compute)


@router.get("/avg-permanence", response_model=Dict[str, Any])
def get_avg_permanence(
    gate_id: Annotated[Optional[int], Query(description="Filter by gate")] = None,
    target_date: Annotated[Optional[date], Query(description="Date (default: today)")] = None,
    db: Annotated[Session, Depends(get_db)] = None,
):
    """
    Average permanence (minutes) for completed visits.
    Called by API Gateway to compose /statistics/summary.
    """
    avg = get_avg_permanence_minutes(db, target_date=target_date or date.today())
    return {"avgPermanenceMinutes": avg}


@router.get("/transport-stats", response_model=List[Dict[str, Any]])
def get_transport_stats(
    from_date: Annotated[Optional[str], Query(description="Start date (YYYY-MM-DD)")] = None,
    to_date: Annotated[Optional[str], Query(description="End date (YYYY-MM-DD)")] = None,
):
    """
    Per-company transport statistics.
    Called by API Gateway to serve /statistics/by-company.
    """
    return _get_transport_stats_canonical(from_date=from_date, to_date=to_date)


@router.get("/next/{gate_id}", response_model=List[Appointment])
def get_upcoming_arrivals(
    gate_id: Annotated[int, Path(description="Gate ID")],
    limit: Annotated[int, Query(ge=1, le=20, description="Number of arrivals")] = 5,
    status: Annotated[Optional[str], Query(description="Filter by status")] = None,
    db: Annotated[Session, Depends(get_db)] = None,
):
    """Next scheduled arrivals for a gate (operator sidebar)."""
    appointments = get_next_appointments(db, gate_id=gate_id, limit=limit, status=status)
    return [_mask_driver_if_infraction(Appointment.model_validate(a)) for a in appointments]


@router.get("/{appointment_id}/detail", response_model=Dict[str, Any], responses={404: {"description": "Appointment not found"}})
def get_arrival_detail(
    appointment_id: Annotated[int, Path(description="Appointment ID")],
    db: Annotated[Session, Depends(get_db)] = None,
):
    """Enriched appointment details (driver, company, booking, cargo, gates, visit)."""
    cache_key = f"detail:{appointment_id}"

    def _compute():
        detail = get_appointment_detail(db, appointment_id)
        if not detail:
            return None
        return detail

    result = get_or_cache(key=cache_key, ttl=60, fallback=_compute)
    if not result:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return result


@router.get("/{appointment_id}", response_model=Appointment, responses={404: {"description": "Appointment not found"}})
def get_arrival(
    appointment_id: Annotated[int, Path(description="Appointment ID")],
    db: Annotated[Session, Depends(get_db)] = None,
):
    """
    Gets details of a specific appointment.
    Read order: Redis → PostgreSQL.

    Scale-up note (BR-29): for high-volume deployments a MongoDB
    appointments_read middle tier can be inserted between Redis and PG to
    reduce primary-DB read pressure.  The collection and its indexes are
    already declared in mongo.py; the outbox worker can be extended to
    project AppointmentStateChanged events into it.  At current port volume
    (hundreds of appointments/day) the two-tier path is sufficient.
    """
    # ── 1) Redis hot cache (written by outbox worker on every state change) ──
    cached = get_cached_appointment(appointment_id)
    if cached:
        logger.debug("CACHE HIT  appointment_id=%s", appointment_id)
        return cached

    # ── 2) PostgreSQL (source of truth) ──────────────────────────────────────
    logger.debug("PG READ  appointment_id=%s", appointment_id)
    appointment = get_appointment_by_id(db, appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    result = Appointment.model_validate(appointment)
    snapshot = result.model_dump(mode="json")
    cache_appointment(appointment_id, snapshot)

    return result


@router.get("/pin/{arrival_id}", response_model=Appointment, responses={404: {"description": "Invalid PIN or appointment not found"}})
def get_arrival_by_pin_code(
    arrival_id: Annotated[str, Path(description="Arrival ID / PIN")],
    db: Annotated[Session, Depends(get_db)] = None,
):
    """Gets appointment by arrival_id/PIN (driver mobile app)."""
    appointment = get_appointment_by_arrival_id(db, arrival_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Invalid PIN or appointment not found")
    return Appointment.model_validate(appointment)


# ==================== DECISION ENGINE ENDPOINTS ====================

@router.get("/query/license-plate/{license_plate}", response_model=List[Appointment], responses={400: {"description": "Invalid shift type"}})
def query_arrivals_by_license_plate(
    license_plate: Annotated[str, Path(description="Truck license plate")],
    shift_gate_id: Annotated[Optional[int], Query(description="Filter by shift gate")] = None,
    shift_type: Annotated[Optional[str], Query(description="Filter by shift type")] = None,
    shift_date: Annotated[Optional[date], Query(description="Filter by shift date")] = None,
    status: Annotated[Optional[str], Query(description="Filter by status")] = None,
    scheduled_date: Annotated[Optional[date], Query(description="Date (default: today)")] = None,
    db: Annotated[Session, Depends(get_db)] = None,
):
    """Query appointments by license plate (Decision Engine)."""
    from utils.plate_validation import is_valid_plate_relaxed
    if not is_valid_plate_relaxed(license_plate):
        raise HTTPException(status_code=400, detail=f"Invalid license plate format: {license_plate!r}")

    parsed_shift_type = None
    if shift_type:
        try:
            parsed_shift_type = parse_shift_type(shift_type)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    appointments = get_appointments_by_license_plate(
        db, license_plate=license_plate,
        shift_gate_id=shift_gate_id,
        shift_type=parsed_shift_type,
        shift_date=shift_date,
        status=status,
        scheduled_date=scheduled_date
    )
    return [Appointment.model_validate(a) for a in appointments]


# ==================== HIGHWAY INFRACTION ====================

@router.patch("/{appointment_id}/highway-infraction", response_model=Appointment, responses={404: {"description": "Appointment not found"}, 409: {"description": "Truck already inside port — infraction not applicable"}})
def flag_highway_infraction(
    appointment_id: Annotated[int, Path(description="Appointment ID")],
    db: Annotated[Session, Depends(get_db)] = None,
):
    """
    Flag an appointment as highway infraction.
    Only allowed while the truck is in transit (scheduled or in_transit status).
    A truck already inside the port (in_process, completed) cannot receive this flag.
    """
    try:
        result = cmd_flag_highway_infraction(_uow_factory, appointment_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail="Appointment not found")
    appointment = get_appointment_by_id(db, appointment_id)
    return Appointment.model_validate(appointment)


class InfractionReviewRequest(BaseModel):
    note: Optional[str] = None
    reviewed_by: str  # num_worker of the reviewing manager


@router.patch(
    "/{appointment_id}/review",
    status_code=200,
    responses={
        404: {"description": "Appointment not found"},
        409: {"description": "Appointment has no highway infraction"},
    },
)
def review_infraction(
    appointment_id: Annotated[int, Path(description="Appointment ID")],
    body: InfractionReviewRequest,
    db: Annotated[Session, Depends(get_db)] = None,
):
    """
    Mark a highway infraction as reviewed by a manager.
    Records reviewed_at (UTC), reviewed_by (num_worker), and an optional note.
    Idempotent — re-reviewing overwrites the previous review record.
    """
    appt = db.query(AppointmentORM).filter(AppointmentORM.id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if not appt.highway_infraction:
        raise HTTPException(status_code=409, detail="Appointment has no highway infraction")

    aggregate = {
        "id": appt.id,
        "highway_infraction": appt.highway_infraction,
    }
    try:
        updated = cmd_review_infraction(aggregate, body.reviewed_by, body.note)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    appt.reviewed_at = updated["reviewed_at"]
    appt.reviewed_by = updated["reviewed_by"]
    appt.review_note = updated["review_note"]
    db.commit()

    return {
        "id": appt.id,
        "reviewed_at": appt.reviewed_at.isoformat() if appt.reviewed_at else None,
        "reviewed_by": appt.reviewed_by,
        "review_note": appt.review_note,
    }


# ==================== UPDATE ENDPOINTS ====================

@router.patch("/{appointment_id}/status", response_model=Appointment, responses={404: {"description": "Appointment not found"}})
def update_status(
    appointment_id: Annotated[int, Path(description="Appointment ID")],
    update_data: AppointmentStatusUpdate = ...,
    db: Annotated[Session, Depends(get_db)] = None,
):
    """Updates appointment status via UoW + Outbox."""
    result = cmd_update_status(
        _uow_factory, appointment_id,
        new_status=update_data.status,
        notes=update_data.notes,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Appointment not found")
    appointment = get_appointment_by_id(db, appointment_id)
    return Appointment.model_validate(appointment)


@router.post("/{appointment_id}/decision", response_model=Appointment, responses={404: {"description": "Appointment not found"}})
def process_decision(
    appointment_id: Annotated[int, Path(description="Appointment ID")],
    decision: Dict[str, Any] = ...,
    db: Annotated[Session, Depends(get_db)] = None,
):
    """
    Processes Decision Engine decision via UoW + Outbox.
    Updates status and creates alerts if needed.

    Expected payload:
    {
        "decision": "approved",
        "status": "in_transit",
        "notes": "Approved automatically",
        "alerts": [
            {"type": "safety", "description": "UN 1203 - Gasoline"}
        ]
    }
    """
    result = cmd_process_decision(
        _uow_factory, appointment_id,
        decision_payload=decision,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Appointment not found")
    appointment = get_appointment_by_id(db, appointment_id)
    return Appointment.model_validate(appointment)


# ==================== VISIT ENDPOINTS ====================

@router.post("/{appointment_id}/visit", response_model=Visit, responses={400: {"description": "Invalid shift type"}, 404: {"description": "Appointment not found or visit already exists"}})
def create_visit(
    appointment_id: Annotated[int, Path(description="Appointment ID")],
    request: CreateVisitRequest = ...,
    db: Annotated[Session, Depends(get_db)] = None,
):
    """
    Creates a visit when truck arrives via UoW + Outbox.
    Called when appointment starts execution.
    Uses composite FK to Shift.
    """
    try:
        shift_type_enum = parse_shift_type(request.shift_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    result = cmd_create_visit(
        _uow_factory,
        appointment_id,
        shift_gate_id=request.shift_gate_id,
        shift_type=shift_type_enum,
        shift_date=request.shift_date,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Appointment not found or visit already exists")
    return Visit.model_validate(_load_visit(db, appointment_id))


# ==================== CSV BULK IMPORT ====================

# Only truck_license_plate and terminal_name are required — booking_reference is auto-generated.
_BULK_REQUIRED_COLS = {"truck_license_plate", "terminal_name"}
_VALID_DIRECTIONS = {"inbound", "outbound"}
_VALID_CARGO_STATES = {"liquid", "solid", "gaseous", "hybrid"}


@router.post(
    "/bulk",
    status_code=201,
    summary="Bulk-import appointments from CSV (no driver — RGPD flow)",
    responses={400: {"description": "Invalid or empty CSV"}},
)
def bulk_import_arrivals(
    file: UploadFile = File(...),
    db: Annotated[Session, Depends(get_db)] = None,
):
    """
    Import appointments from a CSV file.  Driver is NOT included in the CSV;
    drivers associate later via POST /drivers/claim with the arrival_id PIN.

    Required columns: truck_license_plate, terminal_name
    Optional columns:
      scheduled_start_time (ISO-8601), expected_duration (minutes), notes,
      direction (inbound|outbound, default: inbound),
      gate_label (entry gate, e.g. 'Portaria 1' — needed for the appointment to
        appear on that gate operator's dashboard),
      cargo_description, cargo_type (liquid|solid|gaseous|hybrid), cargo_quantity (decimal)

    Booking references are auto-generated (CSV-XXXXXXXX format).
    Terminals are looked up by name (case-insensitive); gates by label (case-insensitive, active only).

    Returns: { created, skipped, errors: [{row, reason}] }
    """
    content = file.file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded")

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise HTTPException(status_code=400, detail="Empty or unreadable CSV")

    headers = {h.strip().lower() for h in reader.fieldnames}
    missing = _BULK_REQUIRED_COLS - headers
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required columns: {', '.join(sorted(missing))}",
        )

    from infrastructure.persistence.sql_models import (
        Appointment as AppointmentORM,
        Booking as BookingORM,
        Gate as GateORM,
        Truck as TruckORM,
        Terminal as TerminalORM,
    )
    from sqlalchemy import func as sql_func

    created = skipped = 0
    errors: List[Dict[str, Any]] = []

    for row_num, raw in enumerate(reader, start=2):
        row = {k.strip().lower(): (v or "").strip() for k, v in raw.items()}

        plate = row.get("truck_license_plate", "")
        terminal_name = row.get("terminal_name", "")

        if not plate or not terminal_name:
            errors.append({"row": row_num, "reason": "Missing required field (truck_license_plate or terminal_name)"})
            skipped += 1
            continue

        # Resolve terminal by name (case-insensitive)
        terminal = db.query(TerminalORM).filter(
            sql_func.lower(TerminalORM.name) == terminal_name.lower()
        ).first()
        if not terminal:
            errors.append({"row": row_num, "reason": f"Terminal {terminal_name!r} not found"})
            skipped += 1
            continue

        # Resolve entry gate by label (optional). Without it the appointment is created
        # but stays invisible on gate operator dashboards (which filter by gate_in_id).
        gate_in_id = None
        gate_label = row.get("gate_label", "").strip()
        if gate_label:
            needle = gate_label.lower()
            # Seeded gate labels carry a descriptive suffix (e.g.
            # "Portaria 1 — Entrada Principal"), so an exact match on a short
            # value like "Portaria 1" would never resolve. Try exact first, then
            # fall back to a prefix match; reject only when the prefix is
            # ambiguous (matches more than one active gate).
            active_gates = db.query(GateORM).filter(GateORM.estado == "Ativo").all()
            exact = [g for g in active_gates if g.label.strip().lower() == needle]
            if exact:
                gate_in_id = exact[0].id
            else:
                prefix = [g for g in active_gates if g.label.strip().lower().startswith(needle)]
                if len(prefix) == 1:
                    gate_in_id = prefix[0].id
                elif len(prefix) > 1:
                    matched = ", ".join(repr(g.label) for g in prefix)
                    errors.append({"row": row_num, "reason": f"Gate {gate_label!r} is ambiguous — matches {matched}"})
                    skipped += 1
                    continue
                else:
                    errors.append({"row": row_num, "reason": f"Gate {gate_label!r} not found or inactive"})
                    skipped += 1
                    continue

        # Validate truck
        if not db.query(TruckORM).filter(TruckORM.license_plate == plate).first():
            errors.append({"row": row_num, "reason": f"Truck {plate!r} not registered in the system"})
            skipped += 1
            continue

        # Conflict check: reject if truck already has an active appointment within ±4 h of the given time
        # (or any active appointment today if no time provided)
        _active_statuses = ('scheduled', 'in_transit', 'in_process')
        raw_time_for_conflict = row.get("scheduled_start_time", "")
        if raw_time_for_conflict:
            try:
                ref_time = datetime.fromisoformat(raw_time_for_conflict)
                window_start = ref_time - timedelta(hours=4)
                window_end   = ref_time + timedelta(hours=4)
                conflict = (
                    db.query(AppointmentORM)
                    .filter(
                        AppointmentORM.truck_license_plate == plate,
                        AppointmentORM.status.in_(_active_statuses),
                        AppointmentORM.scheduled_start_time >= window_start,
                        AppointmentORM.scheduled_start_time <= window_end,
                    )
                    .first()
                )
                if conflict:
                    conflict_time = conflict.scheduled_start_time.strftime("%Y-%m-%d %H:%M") if conflict.scheduled_start_time else "unknown time"
                    errors.append({"row": row_num, "reason": f"Truck {plate!r} already has an active appointment at {conflict_time} (status: {conflict.status}) — within 4 h window"})
                    skipped += 1
                    continue
            except ValueError:
                pass  # invalid time format caught later in the parsing block
        else:
            # No time given: check for any active appointment today
            today_start = datetime.combine(date.today(), datetime.min.time())
            today_end   = datetime.combine(date.today(), datetime.max.time())
            conflict = (
                db.query(AppointmentORM)
                .filter(
                    AppointmentORM.truck_license_plate == plate,
                    AppointmentORM.status.in_(_active_statuses),
                    AppointmentORM.scheduled_start_time >= today_start,
                    AppointmentORM.scheduled_start_time <= today_end,
                )
                .first()
            )
            if conflict:
                conflict_time = conflict.scheduled_start_time.strftime("%H:%M") if conflict.scheduled_start_time else "unknown time"
                errors.append({"row": row_num, "reason": f"Truck {plate!r} already has an active appointment today at {conflict_time} (status: {conflict.status})"})
                skipped += 1
                continue

        # direction (optional, default inbound)
        raw_dir = row.get("direction", "").lower() or "inbound"
        if raw_dir not in _VALID_DIRECTIONS:
            errors.append({"row": row_num, "reason": f"direction must be 'inbound' or 'outbound', got {raw_dir!r}"})
            skipped += 1
            continue

        # scheduled_start_time (optional)
        scheduled_start = None
        raw_time = row.get("scheduled_start_time", "")
        if raw_time:
            try:
                scheduled_start = datetime.fromisoformat(raw_time)
            except ValueError:
                errors.append({"row": row_num, "reason": f"Invalid scheduled_start_time: {raw_time!r} (expected ISO-8601)"})
                skipped += 1
                continue

        # expected_duration (optional, integer minutes)
        expected_dur = None
        raw_dur = row.get("expected_duration", "")
        if raw_dur:
            try:
                expected_dur = int(raw_dur)
            except ValueError:
                errors.append({"row": row_num, "reason": f"expected_duration must be integer minutes, got {raw_dur!r}"})
                skipped += 1
                continue

        # cargo_quantity (optional, decimal)
        cargo_qty = None
        raw_qty = row.get("cargo_quantity", "")
        if raw_qty:
            try:
                cargo_qty = float(raw_qty)
            except ValueError:
                errors.append({"row": row_num, "reason": f"cargo_quantity must be a number, got {raw_qty!r}"})
                skipped += 1
                continue

        # cargo_type validation (optional)
        cargo_type = row.get("cargo_type", "").lower() or None
        if cargo_type and cargo_type not in _VALID_CARGO_STATES:
            errors.append({"row": row_num, "reason": f"cargo_type must be one of {sorted(_VALID_CARGO_STATES)}, got {cargo_type!r}"})
            skipped += 1
            continue

        # Auto-generate a unique booking reference
        booking_ref = f"CSV-{uuid.uuid4().hex[:8].upper()}"
        booking = BookingORM(reference=booking_ref, direction=raw_dir)
        db.add(booking)
        db.flush()  # ensure the booking FK is available before appointment and cargo

        # Create cargo row if any cargo field is provided
        cargo_description = row.get("cargo_description") or None
        if cargo_description or cargo_type or cargo_qty is not None:
            from infrastructure.persistence.sql_models import Cargo as CargoORM
            cargo_row = CargoORM(
                booking_reference=booking_ref,
                description=cargo_description,
                state=cargo_type or "solid",
                quantity=cargo_qty if cargo_qty is not None else 0,
            )
            db.add(cargo_row)

        appt = AppointmentORM(
            booking_reference=booking_ref,
            driver_license=None,
            truck_license_plate=plate,
            terminal_id=terminal.id,
            gate_in_id=gate_in_id,
            scheduled_start_time=scheduled_start,
            expected_duration=expected_dur,
            notes=row.get("notes") or None,
            highway_infraction=False,
            status="scheduled",
        )
        db.add(appt)
        created += 1

    db.commit()
    return {"created": created, "skipped": skipped, "errors": errors}


@router.patch("/{appointment_id}/visit", response_model=Visit, responses={404: {"description": "Visit not found"}})
def update_visit(
    appointment_id: Annotated[int, Path(description="Appointment ID")],
    update_data: VisitStatusUpdate = ...,
    db: Annotated[Session, Depends(get_db)] = None,
):
    """Updates visit status via UoW + Outbox. E.g., to 'completed' when truck leaves."""
    result = cmd_update_visit_state(
        _uow_factory, appointment_id,
        new_state=update_data.state,
        out_time=update_data.out_time,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Visit not found")
    return Visit.model_validate(_load_visit(db, appointment_id))
