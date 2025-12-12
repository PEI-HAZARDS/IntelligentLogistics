"""
Alerts Routes - Endpoints for alert management.
Consumed by: Operator frontend, Decision Engine.
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from sqlalchemy.orm import Session
from pydantic import BaseModel

from db.postgres import get_db
from models.pydantic_models import Alert as AlertPydantic, AlertCreate, TypeAlertEnum
from services.alert_service import (
    get_alerts,
    get_alert_by_id,
    get_active_alerts,
    get_alerts_count_by_type,
    get_alerts_for_visit,
    create_alert,
    create_hazmat_alert,
    ADR_CODES,
    KEMLER_CODES
)

router = APIRouter(prefix="/alerts", tags=["Alerts"])


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
    db: Session = Depends(get_db)
):
    """Lists alerts with optional filters."""
    alerts = get_alerts(
        db, skip=skip, limit=limit,
        alert_type=alert_type, visit_id=visit_id
    )
    return [AlertPydantic.model_validate(a) for a in alerts]


@router.get("/active", response_model=List[AlertPydantic])
def list_active_alerts(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """
    Lists active alerts (last 24h) ordered by timestamp.
    Used in operator dashboard.
    """
    alerts = get_active_alerts(db, limit=limit)
    return [AlertPydantic.model_validate(a) for a in alerts]


@router.get("/stats", response_model=Dict[str, int])
def get_alerts_stats(db: Session = Depends(get_db)):
    """Alert statistics by type (last 24h)."""
    return get_alerts_count_by_type(db)


@router.get("/visit/{visit_id}", response_model=List[AlertPydantic])
def get_visit_alerts(
    visit_id: int = Path(..., description="Visit ID (same as appointment_id)"),
    db: Session = Depends(get_db)
):
    """Gets all alerts for a specific visit."""
    alerts = get_alerts_for_visit(db, visit_id)
    return [AlertPydantic.model_validate(a) for a in alerts]


@router.get("/{alert_id}", response_model=AlertPydantic)
def get_single_alert(
    alert_id: int = Path(..., description="Alert ID"),
    db: Session = Depends(get_db)
):
    """Gets details of a specific alert."""
    alert = get_alert_by_id(db, alert_id)
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return AlertPydantic.model_validate(alert)


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
def create_manual_alert(
    request: CreateAlertRequest,
    db: Session = Depends(get_db)
):
    """
    Creates an alert manually.
    Used by operator or Decision Engine.
    """
    alert = create_alert(
        db,
        visit_id=request.visit_id,
        alert_type=request.type,
        description=request.description,
        image_url=request.image_url
    )
    return AlertPydantic.model_validate(alert)


@router.post("/hazmat", response_model=AlertPydantic, status_code=status.HTTP_201_CREATED)
def create_hazmat_adr_alert(
    request: CreateHazmatAlertRequest,
    db: Session = Depends(get_db)
):
    """
    Creates hazmat/ADR specific alert.
    Used by Decision Engine when detecting hazardous cargo.
    
    Parameters:
    - appointment_id: Associated appointment ID
    - un_code: UN code (e.g., "1203" for gasoline)
    - kemler_code: Kemler code (e.g., "33" for flammable)
    - detected_hazmat: Detection description (from Agent C)
    """
    from models.sql_models import Appointment
    
    appointment = db.query(Appointment).filter(
        Appointment.id == request.appointment_id
    ).first()
    
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found"
        )
    
    alert = create_hazmat_alert(
        db,
        appointment=appointment,
        un_code=request.un_code,
        kemler_code=request.kemler_code,
        detected_hazmat=request.detected_hazmat
    )
    
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating hazmat alert"
        )
    
    return AlertPydantic.model_validate(alert)
