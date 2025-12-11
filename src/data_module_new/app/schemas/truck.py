from datetime import datetime
from typing import Optional
from pydantic import BaseModel

from app.schemas.base import BaseSchema


class TruckBase(BaseModel):
    """Base truck schema."""
    license_plate: str
    country_of_registration: Optional[str] = None
    chassis_type: Optional[str] = None
    emission_standard: Optional[str] = None


class TruckCreate(TruckBase):
    """Schema for creating a truck."""
    hauler_id: Optional[int] = None


class TruckUpdate(BaseModel):
    """Schema for updating a truck."""
    license_plate: Optional[str] = None
    country_of_registration: Optional[str] = None
    chassis_type: Optional[str] = None
    emission_standard: Optional[str] = None
    hauler_id: Optional[int] = None


class TruckResponse(TruckBase, BaseSchema):
    """Schema for truck response."""
    truck_id: int
    hauler_id: Optional[int] = None
    last_seen_date: Optional[datetime] = None
