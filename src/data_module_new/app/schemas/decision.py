from typing import Optional, List, Any
from datetime import datetime
from pydantic import BaseModel, Field

from app.schemas.base import BaseSchema


# ---------- Query Arrivals (Decision Engine -> API) ----------
class QueryArrivalsRequest(BaseSchema):
    """Request from Decision Engine to query appointments by license plate."""
    license_plate: str = Field(..., alias="matricula", description="Vehicle license plate")
    gate_id: int = Field(..., description="Gate ID where truck arrived")


class AppointmentCandidate(BaseSchema):
    """Appointment candidate returned to Decision Engine."""
    appointment_id: int
    booking_ref: Optional[str] = None
    scheduled_start_time: datetime
    scheduled_end_time: datetime
    truck_id: Optional[int] = None
    driver_id: Optional[int] = None
    direction: Optional[str] = None


class QueryArrivalsResponse(BaseSchema):
    """Response to Decision Engine with matching appointments."""
    found: bool
    message: Optional[str] = None
    candidates: List[AppointmentCandidate] = []


# ---------- Access Decision CRUD ----------
class DecisionCreate(BaseSchema):
    """Schema for creating a new access decision."""
    event_id: str = Field(..., description="Unique event ID from agents")
    gate_id: int
    decision: str = Field(..., description="APPROVED, REJECTED, or MANUAL_REVIEW")
    reason: Optional[str] = None
    license_plate: Optional[str] = None
    un_number: Optional[str] = None
    kemler_code: Optional[str] = None
    plate_image_url: Optional[str] = None
    hazard_image_url: Optional[str] = None
    route: Optional[dict] = None
    alerts: Optional[List[str]] = None
    lp_confidence: Optional[float] = None
    hz_confidence: Optional[float] = None


class DecisionResponse(BaseSchema):
    """Response schema for access decision."""
    decision_id: int
    event_id: str
    gate_id: int
    decision: str
    reason: Optional[str] = None
    license_plate: Optional[str] = None
    un_number: Optional[str] = None
    kemler_code: Optional[str] = None
    plate_image_url: Optional[str] = None
    hazard_image_url: Optional[str] = None
    route: Optional[dict] = None
    alerts: Optional[List[str]] = None
    lp_confidence: Optional[float] = None
    hz_confidence: Optional[float] = None
    reviewed_by: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    original_decision: Optional[str] = None
    created_at: datetime


class ManualReviewRequest(BaseSchema):
    """Request for manual review override."""
    new_decision: str = Field(..., description="New decision: APPROVED, REJECTED, or OVERRIDDEN")
    reason: str = Field(..., description="Reason for override")


class DecisionListFilters(BaseSchema):
    """Filters for listing decisions."""
    gate_id: Optional[int] = None
    decision: Optional[str] = None
    license_plate: Optional[str] = None
    from_date: Optional[datetime] = None
    to_date: Optional[datetime] = None
