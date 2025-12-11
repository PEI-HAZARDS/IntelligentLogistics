from datetime import datetime
from typing import Optional
from pydantic import BaseModel

from app.schemas.base import BaseSchema


class GateBase(BaseModel):
    """Base gate schema."""
    gate_label: str
    direction: str
    camera_rtsp_url: Optional[str] = None
    barrier_device_id: Optional[str] = None


class GateResponse(GateBase, BaseSchema):
    """Schema for gate response."""
    gate_id: int
    zone_id: int
    operational_status: str


class GateCheckIn(BaseModel):
    """Schema for gate check-in request."""
    license_plate: str
    driver_license_number: Optional[str] = None
    appointment_id: Optional[int] = None


class GateCheckOut(BaseModel):
    """Schema for gate check-out request."""
    visit_id: int
    exit_gate_id: Optional[int] = None
