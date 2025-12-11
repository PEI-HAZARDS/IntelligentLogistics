from typing import Optional
from pydantic import BaseModel

from app.schemas.base import BaseSchema


class DriverBase(BaseModel):
    """Base driver schema."""
    full_name: str
    license_number: Optional[str] = None
    mobile_device_token: Optional[str] = None


class DriverCreate(DriverBase):
    """Schema for creating a driver."""
    hauler_id: Optional[int] = None


class DriverUpdate(BaseModel):
    """Schema for updating a driver."""
    full_name: Optional[str] = None
    license_number: Optional[str] = None
    mobile_device_token: Optional[str] = None
    is_banned: Optional[bool] = None


class DriverResponse(DriverBase, BaseSchema):
    """Schema for driver response."""
    driver_id: int
    hauler_id: Optional[int] = None
    is_banned: bool = False
