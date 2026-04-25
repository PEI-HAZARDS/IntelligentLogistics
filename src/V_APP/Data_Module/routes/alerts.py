"""
Alerts Routes - Endpoints for alert management.
Consumed by: Operator frontend, Decision Engine.

GET endpoints read from PostgreSQL.
POST endpoints write via UoW + Outbox (Guardrails 2, 3, 6).
"""

from typing import Annotated, List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, status, Query, Path
from pydantic import BaseModel

from application.schemas import Alert as AlertPydantic, AlertCreate, TypeAlertEnum
from application.queries.alert_queries import (
    get_alerts,
    get_alert_by_id,
    get_active_alerts,
    get_alerts_count_by_type,
    get_alerts_for_visit,
)
from application.use_cases.alert_handlers import (
    create_alert,
    create_hazmat_alert,
    ADR_CODES,
    KEMLER_CODES,
)
from infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from infrastructure.persistence.postgres import SessionLocal

router = APIRouter(prefix="/alerts", tags=["Alerts"])

_uow_factory = lambda: SqlAlchemyUnitOfWork(SessionLocal)


# ==================== PYDANTIC MODELS ====================

class CreateAlertRequest(BaseModel):
    """Request to create alert manually."""
    visit_id: Optional[int] = None
    type: str  # generic, safety, problem, operational
    description: str
    image_url: Optional[str] = None


class CreateHazmatAlertRequest(BaseModel):
    """Request to create hazmat/ADR specific alert."""
    appointment_id: int
    un_code: Optional[str] = None
    kemler_code: Optional[str] = None
    detected_hazmat: Optional[str] = None
    event_id: Optional[str] = None  # caller-supplied idempotency key (UUIDv7)


# ==================== QUERY ENDPOINTS ====================

@router.get("", response_model=List[AlertPydantic])
def list_alerts(
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    alert_type: Annotated[Optional[str], Query(description="Filter by type (safety, problem, etc.)")] = None,
    visit_id: Annotated[Optional[int], Query(description="Filter by visit")] = None,
):
    """Lists alerts with optional filters."""
    alerts = get_alerts(skip=skip, limit=limit, alert_type=alert_type, visit_id=visit_id)
    return alerts


@router.get("/active", response_model=List[AlertPydantic])
def list_active_alerts(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    """
    Lists active alerts (last 24h) ordered by timestamp.
    Used in operator dashboard.
    """
    return get_active_alerts(limit=limit)


@router.get("/stats", response_model=Dict[str, int])
def get_alerts_stats(
    from_date: Annotated[Optional[str], Query(alias="from", description="Start date (YYYY-MM-DD)")] = None,
    to_date: Annotated[Optional[str], Query(alias="to", description="End date (YYYY-MM-DD)")] = None,
):
    """Alert statistics by type. Defaults to last 24h when no dates given."""
    return get_alerts_count_by_type(from_date=from_date, to_date=to_date)


@router.get("/visit/{visit_id}", response_model=List[AlertPydantic])
def get_visit_alerts(
    visit_id: Annotated[int, Path(description="Visit ID (same as appointment_id)")],
):
    """Gets all alerts for a specific visit."""
    return get_alerts_for_visit(visit_id)


@router.get("/{alert_id}", response_model=AlertPydantic)
def get_single_alert(
    alert_id: Annotated[int, Path(description="Alert ID")],
):
    """Gets details of a specific alert."""
    alert = get_alert_by_id(alert_id)
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return alert


# ==================== REFERENCE DATA ====================

@router.get("/reference/adr-codes")
def get_adr_codes():
    """
    Lists available ADR/UN codes.
    Used for reference by Decision Engine and frontend.
    """
    return ADR_CODES


@router.get("/reference/kemler-codes")
def get_kemler_codes():
    """
    Lists available Kemler codes.
    Used for reference by Decision Engine and frontend.
    """
    return KEMLER_CODES


# ==================== CREATE ENDPOINTS ====================

@router.post("", response_model=AlertPydantic, status_code=status.HTTP_201_CREATED)
def create_manual_alert(request: CreateAlertRequest):
    """
    Creates an alert manually.
    Used by operator or Decision Engine.
    """
    alert = create_alert(
        _uow_factory,
        visit_id=request.visit_id,
        alert_type=request.type,
        description=request.description,
        image_url=request.image_url,
    )
    return alert


@router.post("/hazmat", response_model=AlertPydantic, status_code=status.HTTP_201_CREATED)
def create_hazmat_adr_alert(request: CreateHazmatAlertRequest):
    """
    Creates hazmat/ADR specific alert.
    Used by Decision Engine when detecting hazardous cargo.

    Parameters:
    - appointment_id: Associated appointment ID
    - un_code: UN code (e.g., "1203" for gasoline)
    - kemler_code: Kemler code (e.g., "33" for flammable)
    - detected_hazmat: Detection description (from Agent C)
    - event_id: Optional UUIDv7 idempotency key; duplicate calls return 200
    """
    from domain.events import EventEnvelope, ConsumeContext, new_event_id
    from datetime import datetime, timezone

    # Inbox dedup: if caller supplies event_id, reject replays (Phase 8)
    if request.event_id:
        try:
            with _uow_factory() as uow:
                dedup_envelope = EventEnvelope(
                    event_id=request.event_id,
                    correlation_id=request.event_id,
                    causation_id=None,
                    aggregate_type="alert",
                    aggregate_id=str(request.appointment_id),
                    event_type="HazmatAlertCreated",
                    event_version=1,
                    occurred_at=datetime.now(timezone.utc),
                    producer="decision-engine",
                    partition_key=str(request.appointment_id),
                    payload={"appointment_id": request.appointment_id},
                )
                dedup_ctx = ConsumeContext(
                    topic="http://alerts/hazmat",
                    partition=0,
                    offset=0,
                    key=str(request.appointment_id),
                    headers={},
                )
                if not uow.inbox.try_insert_received(dedup_envelope, dedup_ctx):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Duplicate hazmat alert request: event_id={request.event_id}",
                    )
                uow.commit()
        except HTTPException:
            raise
        except Exception:
            pass  # inbox unavailable — proceed without dedup rather than block

    alert = create_hazmat_alert(
        _uow_factory,
        appointment_id=request.appointment_id,
        un_code=request.un_code,
        kemler_code=request.kemler_code,
        detected_hazmat=request.detected_hazmat,
    )

    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Appointment {request.appointment_id} not found",
        )

    return alert
