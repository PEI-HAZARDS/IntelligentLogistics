from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel

from app.schemas.base import BaseSchema


class VisitEventCreate(BaseModel):
    """Schema for creating a visit event."""
    event_type: str
    location_id: Optional[int] = None
    description: Optional[str] = None


class VisitEventResponse(BaseSchema):
    """Schema for visit event response."""
    log_id: int
    visit_id: int
    event_type: str
    timestamp: datetime
    location_id: Optional[int] = None
    description: Optional[str] = None


class VisitResponse(BaseSchema):
    """Schema for visit response."""
    visit_id: int
    appointment_id: Optional[int] = None
    truck_id: Optional[int] = None
    driver_id: Optional[int] = None
    entry_gate_id: Optional[int] = None
    exit_gate_id: Optional[int] = None
    gate_in_time: Optional[datetime] = None
    gate_out_time: Optional[datetime] = None
    visit_stage: str
    dwell_time_minutes: Optional[int] = None


class VisitUpdateStage(BaseModel):
    """Schema for updating visit stage."""
    visit_stage: str
    target_zone_id: Optional[int] = None
