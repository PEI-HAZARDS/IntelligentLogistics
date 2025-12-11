from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr

from app.schemas.base import BaseSchema


class WorkerBase(BaseModel):
    """Base worker schema."""
    full_name: str
    email: str
    role: str = "operator"


class WorkerCreate(WorkerBase):
    """Schema for creating a worker."""
    password: str
    assigned_gate_id: Optional[int] = None


class WorkerUpdate(BaseModel):
    """Schema for updating a worker."""
    full_name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    assigned_gate_id: Optional[int] = None
    is_active: Optional[bool] = None


class WorkerResponse(WorkerBase, BaseSchema):
    """Schema for worker response."""
    worker_id: int
    assigned_gate_id: Optional[int] = None
    is_active: bool = True
    created_at: Optional[datetime] = None


class LoginRequest(BaseModel):
    """Schema for login request."""
    email: str
    password: str


class TokenResponse(BaseModel):
    """Schema for token response."""
    access_token: str
    token_type: str = "bearer"


class CurrentUser(BaseSchema):
    """Schema for current user info."""
    worker_id: int
    full_name: str
    email: str
    role: str
    assigned_gate_id: Optional[int] = None
