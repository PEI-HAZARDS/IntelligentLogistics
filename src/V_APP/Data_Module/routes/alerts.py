"""
Alerts Routes - Endpoints for alert management.
Consumed by: Operator frontend, Decision Engine.

CQRS: GET endpoints read from MongoDB (alerts_read_collection).
POST endpoints write via UoW + Outbox (Guardrails 2, 3, 6).
"""

from typing import List, Optional, Dict, Any
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

router = APIRouter(prefix="/alerts", tags=["Alerts"])

_uow_factory = SqlAlchemyUnitOfWork


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


# ==================== QUERY ENDPOINTS ====================

@router.get("", response_model=List[AlertPydantic])
def list_alerts(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    alert_type: Optional[str] = Query(None, description="Filter by type (safety, problem, etc.)"),
    visit_id: Optional[int] = Query(None, description="Filter by visit"),
):
    """Lists alerts with optional filters."""
    alerts = get_alerts(skip=skip, limit=limit, alert_type=alert_type, visit_id=visit_id)
    return alerts


@router.get("/active", response_model=List[AlertPydantic])
def list_active_alerts(
    limit: int = Query(50, ge=1, le=200),
):
    """
    Lists active alerts (last 24h) ordered by timestamp.
    Used in operator dashboard.
    """
    return get_active_alerts(limit=limit)


@router.get("/stats", response_model=Dict[str, int])
def get_alerts_stats():
    """Alert statistics by type (last 24h)."""
    return get_alerts_count_by_type()


@router.get("/visit/{visit_id}", response_model=List[AlertPydantic])
def get_visit_alerts(
    visit_id: int = Path(..., description="Visit ID (same as appointment_id)"),
):
    """Gets all alerts for a specific visit."""
    return get_alerts_for_visit(visit_id)


@router.get("/{alert_id}", response_model=AlertPydantic)
def get_single_alert(
    alert_id: int = Path(..., description="Alert ID"),
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
    """
    alert = create_hazmat_alert(
        _uow_factory,
        appointment_id=request.appointment_id,
        un_code=request.un_code,
        kemler_code=request.kemler_code,
        detected_hazmat=request.detected_hazmat,
    )

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating hazmat alert",
        )

    return alert
