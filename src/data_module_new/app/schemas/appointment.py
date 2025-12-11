from datetime import datetime
from typing import Optional
from pydantic import BaseModel

from app.schemas.base import BaseSchema


class AppointmentBase(BaseModel):
    """Base appointment schema."""
    scheduled_start_time: datetime
    scheduled_end_time: datetime


class AppointmentCreate(AppointmentBase):
    """Schema for creating an appointment."""
    booking_id: Optional[int] = None
    hauler_id: Optional[int] = None
    truck_id: Optional[int] = None
    driver_id: Optional[int] = None


class AppointmentConfirm(BaseModel):
    """Schema for confirming an appointment."""
    truck_id: int
    driver_id: int


class AppointmentUpdate(BaseModel):
    """Schema for updating an appointment."""
    scheduled_start_time: Optional[datetime] = None
    scheduled_end_time: Optional[datetime] = None
    truck_id: Optional[int] = None
    driver_id: Optional[int] = None


class AppointmentResponse(AppointmentBase, BaseSchema):
    """Schema for appointment response."""
    appointment_id: int
    booking_id: Optional[int] = None
    hauler_id: Optional[int] = None
    truck_id: Optional[int] = None
    driver_id: Optional[int] = None
    appointment_status: str


class AppointmentWindowCheck(BaseModel):
    """Response for appointment window check."""
    appointment_id: int
    is_within_window: bool
    scheduled_start_time: datetime
    scheduled_end_time: datetime
    current_time: datetime
    minutes_early: Optional[int] = None
    minutes_late: Optional[int] = None
