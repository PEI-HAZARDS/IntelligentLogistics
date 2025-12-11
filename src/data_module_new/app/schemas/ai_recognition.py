from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel

from app.schemas.base import BaseSchema


class AIEventCreate(BaseModel):
    """Schema for creating an AI recognition event."""
    gate_id: int
    object_class: Optional[str] = None
    detected_text: Optional[str] = None
    confidence_score: Optional[float] = None
    bounding_box_json: Optional[Dict[str, Any]] = None
    image_storage_path: Optional[str] = None
    processing_duration_ms: Optional[int] = None


class AIEventResponse(BaseSchema):
    """Schema for AI recognition event response."""
    recognition_id: int
    gate_id: Optional[int] = None
    timestamp: datetime
    object_class: Optional[str] = None
    detected_text: Optional[str] = None
    confidence_score: Optional[float] = None
    bounding_box_json: Optional[Dict[str, Any]] = None
    image_storage_path: Optional[str] = None
    processing_duration_ms: Optional[int] = None
    needs_review: bool = False


class AICorrectionCreate(BaseModel):
    """Schema for creating an AI correction."""
    recognition_id: int
    corrected_value: str
    reason_code: Optional[str] = None


class AICorrectionResponse(BaseSchema):
    """Schema for AI correction response."""
    correction_id: int
    recognition_id: int
    corrected_value: Optional[str] = None
    operator_id: Optional[int] = None
    reason_code: Optional[str] = None
    is_retrained: bool = False
    created_at: Optional[datetime] = None
