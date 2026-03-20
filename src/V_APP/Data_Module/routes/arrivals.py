"""
Arrivals Routes - Endpoints for appointment and visit management.
Consumed by: Operator frontend, Decision Engine, Driver app.

CQRS Query Side: GET endpoints read from MongoDB/Redis first.
PostgreSQL fallback is allowed only on projection miss (Guardrail 5).
"""

from typing import List, Optional, Dict, Any, Generic, TypeVar
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session
from pydantic import BaseModel
from loguru import logger

from application.schemas import (
    Appointment, AppointmentStatusUpdate, Visit, VisitStatusUpdate, ShiftTypeEnum
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
    get_transport_stats_by_company,
)
from application.use_cases.appointment_commands import (
    cmd_update_status,
    cmd_process_decision,
    cmd_flag_highway_infraction,
    cmd_create_visit,
    cmd_update_visit_state,
)
from application.queries.cache_queries import get_or_cache
from infrastructure.persistence.redis import get_cached_appointment, cache_appointment
from infrastructure.persistence.mongo import appointments_read_collection

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

router = APIRouter(prefix="/arrivals", tags=["Arrivals"])


# ==================== LOCAL MODELS ====================

class CreateVisitRequest(BaseModel):
    """Request to create a visit with composite shift FK."""
    shift_gate_id: int
    shift_type: str  # "MORNING", "AFTERNOON", "NIGHT"
    shift_date: date


# ==================== CQRS READ MODEL HELPERS ====================

_MONGO_WARM: Optional[bool] = None


def _mongo_has_data() -> bool:
    """Check if MongoDB appointments read model has been populated."""
    global _MONGO_WARM
    if _MONGO_WARM:
        return True
    try:
        _MONGO_WARM = appointments_read_collection.estimated_document_count() > 0
        return _MONGO_WARM
    except Exception:
        return False


def _clean_mongo_doc(doc: dict) -> dict:
    """Remove MongoDB internal fields before Pydantic validation."""
    doc.pop("_id", None)
    doc.pop("projected_at", None)
    doc.pop("_visit", None)
    doc.pop("_detail", None)
    return doc


def _build_mongo_filter(
    gate_id=None, shift_gate_id=None, shift_type=None, shift_date=None,
    status=None, scheduled_date=None, search=None, highway_infraction=None,
) -> dict:
    """Build MongoDB query filter mirroring _apply_appointment_filters."""
    query: dict = {}
    if gate_id:
        query["gate_in_id"] = gate_id
    if shift_gate_id and shift_type and shift_date:
        query["_visit.shift_gate_id"] = shift_gate_id
        query["_visit.shift_type"] = (
            shift_type.name if hasattr(shift_type, "name") else str(shift_type)
        )
        query["_visit.shift_date"] = shift_date.isoformat()
    if status:
        if "," in status:
            statuses = [s.strip() for s in status.split(",") if s.strip()]
            if statuses:
                query["status"] = {"$in": statuses}
        else:
            query["status"] = status
    if scheduled_date:
        prefix = scheduled_date.isoformat()
        query["scheduled_start_time"] = {
            "$gte": f"{prefix}T00:00:00",
            "$lte": f"{prefix}T23:59:59.999999",
        }
    if search:
        query["truck_license_plate"] = {"$regex": search.upper(), "$options": "i"}
    if highway_infraction is not None:
        query["highway_infraction"] = highway_infraction
    return query


def _get_stats_from_mongo(
    gate_id: Optional[int] = None,
    target_date: Optional[date] = None,
) -> Optional[Dict[str, int]]:
    """Compute appointment status counts via MongoDB aggregation."""
    if not _mongo_has_data():
        return None
    try:
        today = target_date or date.today()
        day_start = f"{today.isoformat()}T00:00:00"
        day_end = f"{today.isoformat()}T23:59:59.999999"

        or_conditions: list = [
            {"scheduled_start_time": {"$gte": day_start, "$lte": day_end}},
            {"status": "delayed", "scheduled_start_time": {"$lt": day_start}},
            {"status": "in_process", "scheduled_start_time": {"$lt": day_start}},
        ]
        match_filter: dict = {"$or": or_conditions}
        if gate_id:
            match_filter["gate_in_id"] = gate_id

        pipeline = [
            {"$match": match_filter},
            {"$facet": {
                "by_status": [
                    {"$group": {"_id": "$status", "count": {"$sum": 1}}}
                ],
                "infractions": [
                    {"$match": {"highway_infraction": True}},
                    {"$count": "total"},
                ],
            }},
        ]

        result = list(appointments_read_collection.aggregate(pipeline))
        if not result:
            return None

        facets = result[0]
        counts: Dict[str, int] = {
            "in_transit": 0, "in_process": 0, "delayed": 0,
            "canceled": 0, "completed": 0, "total": 0, "infractions": 0,
        }

        for item in facets.get("by_status", []):
            s = item["_id"]
            if s in counts:
                counts[s] = item["count"]
            counts["total"] += item["count"]

        counts["infractions"] = (
            facets["infractions"][0]["total"]
            if facets.get("infractions")
            else 0
        )

        # $facet always returns a result even with 0 matches — treat
        # an all-zero result as a projection miss so PG fallback runs.
        if counts["total"] == 0:
            return None

        return counts
    except Exception as e:
        logger.warning("MongoDB stats aggregation failed: %s", e)
        return None


# ==================== GET ENDPOINTS ====================

@router.get("", response_model=PaginatedResponse[Appointment])
def list_arrivals(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    gate_id: Optional[int] = Query(None, description="Filter by entry gate"),
    shift_gate_id: Optional[int] = Query(None, description="Filter by shift gate"),
    shift_type: Optional[str] = Query(None, description="Filter by shift type"),
    shift_date: Optional[date] = Query(None, description="Filter by shift date"),
    status: Optional[str] = Query(None, description="Filter by single status"),
    statuses: Optional[str] = Query(None, description="Filter by multiple statuses (comma-separated)"),
    scheduled_date: Optional[date] = Query(None, description="Filter by scheduled date"),
    search: Optional[str] = Query(None, description="Search by license plate or driver name"),
    highway_infraction: Optional[bool] = Query(None, description="Filter by highway infraction flag"),
    db: Session = Depends(get_db),
):
    """
    Lists appointments with server-side pagination, filtering and search.

    **CQRS Query Side** — reads from MongoDB read model first.
    Falls back to PostgreSQL only when projection is cold (Guardrail 5).
    """
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

    # ── CQRS: MongoDB read model first ─────────────────────
    if _mongo_has_data():
        try:
            mongo_filter = _build_mongo_filter(
                gate_id=gate_id, shift_gate_id=shift_gate_id,
                shift_type=parsed_shift_type, shift_date=shift_date,
                status=final_status, scheduled_date=scheduled_date,
                search=search, highway_infraction=highway_infraction,
            )
            total = appointments_read_collection.count_documents(mongo_filter)
            cursor = (
                appointments_read_collection
                .find(mongo_filter)
                .sort("scheduled_start_time", 1)
                .skip(skip)
                .limit(limit)
            )
            items = [_clean_mongo_doc(doc) for doc in cursor]

            logger.debug("list_arrivals served from MongoDB (%d items)", len(items))
            return PaginatedResponse(
                items=[Appointment.model_validate(a) for a in items],
                total=total, page=page, limit=limit,
                pages=max(1, -(-total // limit)),
            )
        except Exception as e:
            logger.warning("MongoDB read failed for list_arrivals: %s — PG fallback", e)

    # ── PostgreSQL fallback (observable — Guardrail 5) ─────
    logger.info("PROJECTION MISS list_arrivals — PostgreSQL fallback (Guardrail 5)")

    filter_kwargs = dict(
        gate_id=gate_id, shift_gate_id=shift_gate_id,
        shift_type=parsed_shift_type, shift_date=shift_date,
        status=final_status, scheduled_date=scheduled_date,
        search=search, highway_infraction=highway_infraction,
    )
    total = count_all_appointments(db, **filter_kwargs)
    appointments = get_all_appointments(db, skip=skip, limit=limit, **filter_kwargs)

    return PaginatedResponse(
        items=[Appointment.model_validate(a) for a in appointments],
        total=total, page=page, limit=limit,
        pages=max(1, -(-total // limit)),
    )


@router.get("/stats", response_model=Dict[str, int])
def get_arrivals_stats(
    gate_id: Optional[int] = Query(None, description="Filter by gate"),
    target_date: Optional[date] = Query(None, description="Date to query (default: today)"),
    db: Session = Depends(get_db),
):
    """
    Arrival statistics by status.

    **CQRS Query Side** — tries MongoDB aggregation, then Redis cache,
    then PostgreSQL fallback.  Result cached 30 s in Redis.
    """
    today = (target_date or date.today()).isoformat()
    cache_key = f"stats:gate:{gate_id or 'all'}:{today}"

    def _fallback():
        mongo_stats = _get_stats_from_mongo(gate_id=gate_id, target_date=target_date)
        if mongo_stats:
            logger.debug("stats served from MongoDB aggregation")
            return mongo_stats
        logger.info("PROJECTION MISS stats — PostgreSQL fallback (Guardrail 5)")
        return get_appointments_count_by_status(db, gate_id=gate_id, target_date=target_date)

    return get_or_cache(key=cache_key, ttl=30, fallback=_fallback)


@router.get("/avg-permanence", response_model=Dict[str, Any])
def get_avg_permanence(
    gate_id: Optional[int] = Query(None, description="Filter by gate"),
    target_date: Optional[date] = Query(None, description="Date (default: today)"),
    db: Session = Depends(get_db),
):
    """
    Average permanence (minutes) for completed visits.
    Called by API Gateway to compose /statistics/summary.
    """
    avg = get_avg_permanence_minutes(db, target_date=target_date or date.today())
    return {"avgPermanenceMinutes": avg}


@router.get("/transport-stats", response_model=List[Dict[str, Any]])
def get_transport_stats(
    days: int = Query(30, ge=1, le=365, description="Lookback period in days"),
    db: Session = Depends(get_db),
):
    """
    Per-company transport statistics.
    Called by API Gateway to serve /statistics/by-company.
    Returns: [{companyName, companyNif, avgUnloadingTime, avgWaitingTime,
               operationsCount, slaAttendedRate}]
    """
    return get_transport_stats_by_company(db, days=days)


@router.get("/next/{gate_id}", response_model=List[Appointment])
def get_upcoming_arrivals(
    gate_id: int = Path(..., description="Gate ID"),
    limit: int = Query(5, ge=1, le=20, description="Number of arrivals"),
    status: Optional[str] = Query(None, description="Filter by status"),
    db: Session = Depends(get_db)
):
    """
    Next scheduled arrivals for a gate (operator sidebar).

    **CQRS Query Side** — MongoDB aggregate with priority sort
    (delayed first), PostgreSQL fallback on projection miss.
    """
    # ── CQRS: MongoDB read model ──────────────────────────
    if _mongo_has_data():
        try:
            today = date.today()
            day_start = f"{today.isoformat()}T00:00:00"
            day_end = f"{today.isoformat()}T23:59:59.999999"

            match: dict = {
                "gate_in_id": gate_id,
                "scheduled_start_time": {"$gte": day_start, "$lte": day_end},
            }
            if status:
                match["status"] = status
            else:
                match["status"] = {"$in": ["in_transit", "delayed"]}

            pipeline = [
                {"$match": match},
                {"$addFields": {
                    "_priority": {"$cond": [{"$eq": ["$status", "delayed"]}, 0, 1]}
                }},
                {"$sort": {"_priority": 1, "scheduled_start_time": 1}},
                {"$limit": limit},
                {"$project": {
                    "_priority": 0, "_id": 0, "projected_at": 0,
                    "_visit": 0, "_detail": 0,
                }},
            ]

            docs = list(appointments_read_collection.aggregate(pipeline))
            if docs:
                logger.debug("next_arrivals served from MongoDB (%d items)", len(docs))
                return [Appointment.model_validate(d) for d in docs]
        except Exception as e:
            logger.warning("MongoDB read failed for next_arrivals: %s — PG fallback", e)

    # ── PostgreSQL fallback ────────────────────────────────
    logger.info(
        "PROJECTION MISS next_arrivals gate=%s — PostgreSQL fallback (Guardrail 5)",
        gate_id,
    )
    appointments = get_next_appointments(db, gate_id=gate_id, limit=limit, status=status)
    return [Appointment.model_validate(a) for a in appointments]


@router.get("/{appointment_id}/detail", response_model=Dict[str, Any])
def get_arrival_detail(
    appointment_id: int = Path(..., description="Appointment ID"),
    db: Session = Depends(get_db)
):
    """
    Enriched appointment details (driver, company, booking, cargo, gates, visit).

    **CQRS Query Side** — reads pre-built ``_detail`` from MongoDB projection.
    Falls back to PostgreSQL on projection miss.
    """
    # ── CQRS: MongoDB enriched detail ─────────────────────
    try:
        doc = appointments_read_collection.find_one({"id": appointment_id})
        if doc and doc.get("_detail"):
            logger.debug("detail served from MongoDB for appointment_id=%s", appointment_id)
            return doc["_detail"]
    except Exception as e:
        logger.warning("MongoDB read failed for detail: %s — PG fallback", e)

    # ── PostgreSQL fallback ────────────────────────────────
    logger.info(
        "PROJECTION MISS detail appointment_id=%s — PostgreSQL fallback (Guardrail 5)",
        appointment_id,
    )
    detail = get_appointment_detail(db, appointment_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return detail


@router.get("/{appointment_id}", response_model=Appointment)
def get_arrival(
    appointment_id: int = Path(..., description="Appointment ID"),
    db: Session = Depends(get_db),
):
    """
    Gets details of a specific appointment.

    **CQRS Query Side** — reads from Redis hot cache first (O(1)).
    Falls back to PostgreSQL only on projection miss (Guardrail 5).

    The outbox worker keeps this cache warm: every
    ``AppointmentStateChanged`` event writes a full snapshot into
    ``appointment:{id}:details``.
    """
    # ── 1) Redis hot cache (written by outbox worker) ─────────
    cached = get_cached_appointment(appointment_id)
    if cached:
        logger.debug("CACHE HIT  appointment_id=%s", appointment_id)
        return cached

    # ── 2) Projection miss → PostgreSQL fallback (observable) ─
    logger.info(
        "CACHE MISS appointment_id=%s — PostgreSQL fallback (Guardrail 5)",
        appointment_id,
    )
    appointment = get_appointment_by_id(db, appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    # ── 3) Warm cache for subsequent reads ────────────────────
    result = Appointment.model_validate(appointment)
    cache_appointment(appointment_id, result.model_dump(mode="json"))

    return result


@router.get("/pin/{arrival_id}", response_model=Appointment)
def get_arrival_by_pin_code(
    arrival_id: str = Path(..., description="Arrival ID / PIN"),
    db: Session = Depends(get_db)
):
    """
    Gets appointment by arrival_id/PIN (driver mobile app).

    **CQRS Query Side** — MongoDB lookup by ``arrival_id`` index.
    Falls back to PostgreSQL on projection miss.
    """
    # ── CQRS: MongoDB read model ──────────────────────────
    try:
        doc = appointments_read_collection.find_one({"arrival_id": arrival_id})
        if doc:
            logger.debug("PIN lookup served from MongoDB for arrival_id=%s", arrival_id)
            return Appointment.model_validate(_clean_mongo_doc(doc))
    except Exception as e:
        logger.warning("MongoDB read failed for PIN lookup: %s — PG fallback", e)

    # ── PostgreSQL fallback ────────────────────────────────
    logger.info(
        "PROJECTION MISS pin=%s — PostgreSQL fallback (Guardrail 5)",
        arrival_id,
    )
    appointment = get_appointment_by_arrival_id(db, arrival_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Invalid PIN or appointment not found")
    return Appointment.model_validate(appointment)


# ==================== DECISION ENGINE ENDPOINTS ====================

@router.get("/query/license-plate/{license_plate}", response_model=List[Appointment])
def query_arrivals_by_license_plate(
    license_plate: str = Path(..., description="Truck license plate"),
    shift_gate_id: Optional[int] = Query(None, description="Filter by shift gate"),
    shift_type: Optional[str] = Query(None, description="Filter by shift type"),
    shift_date: Optional[date] = Query(None, description="Filter by shift date"),
    status: Optional[str] = Query(None, description="Filter by status"),
    scheduled_date: Optional[date] = Query(None, description="Date (default: today)"),
    db: Session = Depends(get_db)
):
    """
    Query appointments by license plate (Decision Engine).

    **CQRS Query Side** — MongoDB read model first, PostgreSQL fallback.
    """
    parsed_shift_type = None
    if shift_type:
        try:
            parsed_shift_type = parse_shift_type(shift_type)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    # ── CQRS: MongoDB read model ──────────────────────────
    if _mongo_has_data():
        try:
            query: dict = {"truck_license_plate": license_plate}
            if shift_gate_id and parsed_shift_type and shift_date:
                query["_visit.shift_gate_id"] = shift_gate_id
                query["_visit.shift_type"] = (
                    parsed_shift_type.name
                    if hasattr(parsed_shift_type, "name")
                    else str(parsed_shift_type)
                )
                query["_visit.shift_date"] = shift_date.isoformat()
            if status:
                query["status"] = status
            target = scheduled_date or date.today()
            prefix = target.isoformat()
            query["scheduled_start_time"] = {
                "$gte": f"{prefix}T00:00:00",
                "$lte": f"{prefix}T23:59:59.999999",
            }

            docs = list(
                appointments_read_collection
                .find(query)
                .sort("scheduled_start_time", 1)
            )
            if docs:
                logger.debug(
                    "license_plate query served from MongoDB (%d items)", len(docs),
                )
                return [Appointment.model_validate(_clean_mongo_doc(d)) for d in docs]
        except Exception as e:
            logger.warning(
                "MongoDB read failed for license_plate query: %s — PG fallback", e,
            )

    # ── PostgreSQL fallback ────────────────────────────────
    logger.info(
        "PROJECTION MISS license_plate=%s — PostgreSQL fallback (Guardrail 5)",
        license_plate,
    )
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

@router.patch("/{appointment_id}/highway-infraction", response_model=Appointment)
def flag_highway_infraction(
    appointment_id: int = Path(..., description="Appointment ID"),
    db: Session = Depends(get_db)
):
    """
    Flag an appointment as highway infraction.
    Hazmat truck detected on restricted highway route before port entry.
    """
    result = cmd_flag_highway_infraction(_uow_factory, appointment_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Appointment not found")
    # CQRS read-after-write: re-query for full ORM response
    appointment = get_appointment_by_id(db, appointment_id)
    return Appointment.model_validate(appointment)


# ==================== UPDATE ENDPOINTS ====================

@router.patch("/{appointment_id}/status", response_model=Appointment)
def update_status(
    appointment_id: int = Path(..., description="Appointment ID"),
    update_data: AppointmentStatusUpdate = ...,
    db: Session = Depends(get_db)
):
    """
    Updates appointment status via UoW + Outbox (Guardrails 2, 3, 6).
    Used by operator or system for manual updates.
    """
    result = cmd_update_status(
        _uow_factory, appointment_id,
        new_status=update_data.status,
        notes=update_data.notes,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Appointment not found")
    # CQRS read-after-write
    appointment = get_appointment_by_id(db, appointment_id)
    return Appointment.model_validate(appointment)


@router.post("/{appointment_id}/decision", response_model=Appointment)
def process_decision(
    appointment_id: int = Path(..., description="Appointment ID"),
    decision: Dict[str, Any] = ...,
    db: Session = Depends(get_db)
):
    """
    Processes Decision Engine decision via UoW + Outbox (Guardrails 2, 3, 6).
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
    # CQRS read-after-write
    appointment = get_appointment_by_id(db, appointment_id)
    return Appointment.model_validate(appointment)


# ==================== VISIT ENDPOINTS ====================

@router.post("/{appointment_id}/visit", response_model=Visit)
def create_visit(
    appointment_id: int = Path(..., description="Appointment ID"),
    request: CreateVisitRequest = ...,
    db: Session = Depends(get_db)
):
    """
    Creates a visit when truck arrives via UoW + Outbox (Guardrails 2, 3, 6).
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
    # CQRS read-after-write
    from infrastructure.persistence.sql_models import Visit as VisitORM
    visit_orm = db.query(VisitORM).filter(VisitORM.appointment_id == appointment_id).first()
    return Visit.model_validate(visit_orm)


@router.patch("/{appointment_id}/visit", response_model=Visit)
def update_visit(
    appointment_id: int = Path(..., description="Appointment ID"),
    update_data: VisitStatusUpdate = ...,
    db: Session = Depends(get_db)
):
    """
    Updates visit status via UoW + Outbox (Guardrails 2, 3, 6).
    E.g., to 'completed' when truck leaves.
    """
    result = cmd_update_visit_state(
        _uow_factory, appointment_id,
        new_state=update_data.state,
        out_time=update_data.out_time,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Visit not found")
    # CQRS read-after-write
    from infrastructure.persistence.sql_models import Visit as VisitORM
    visit_orm = db.query(VisitORM).filter(VisitORM.appointment_id == appointment_id).first()
    return Visit.model_validate(visit_orm)
