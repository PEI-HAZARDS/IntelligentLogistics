from datetime import datetime
from typing import Optional
from pydantic import BaseModel

from app.schemas.base import BaseSchema


class ResourceMetricCreate(BaseModel):
    """Schema for creating a resource metric."""
    node_id: str
    cpu_usage_pct: Optional[float] = None
    gpu_usage_pct: Optional[float] = None
    power_consumption_watts: Optional[float] = None
    active_camera_streams: Optional[int] = None
    traffic_volume_in_gate: Optional[int] = None


class ResourceMetricResponse(BaseSchema):
    """Schema for resource metric response."""
    metric_id: int
    timestamp: datetime
    node_id: str
    cpu_usage_pct: Optional[float] = None
    gpu_usage_pct: Optional[float] = None
    power_consumption_watts: Optional[float] = None
    active_camera_streams: Optional[int] = None
    traffic_volume_in_gate: Optional[int] = None
