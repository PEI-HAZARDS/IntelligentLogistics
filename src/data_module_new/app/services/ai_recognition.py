from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.repositories.ai_recognition import AIRecognitionRepository
from app.models import AIRecognitionEvent, AICorrection
from app.schemas import AIEventCreate, AICorrectionCreate

settings = get_settings()


class AIRecognitionService:
    """Service for AI recognition operations with confidence handling."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.recognition_repo = AIRecognitionRepository(db)
        self.confidence_threshold = settings.AI_CONFIDENCE_THRESHOLD
    
    async def get_by_id(self, recognition_id: int) -> Optional[AIRecognitionEvent]:
        """Get recognition event by ID."""
        return await self.recognition_repo.get_by_id(recognition_id)
    
    async def get_by_gate(
        self, 
        gate_id: int, 
        skip: int = 0, 
        limit: int = 100
    ) -> List[AIRecognitionEvent]:
        """Get recognition events for a gate."""
        return await self.recognition_repo.get_by_gate(gate_id, skip, limit)
    
    async def ingest_event(self, event_data: AIEventCreate) -> AIRecognitionEvent:
        """
        Ingest an AI recognition event.
        Automatically creates a pending correction if confidence is below threshold.
        """
        event = await self.recognition_repo.create_recognition(
            gate_id=event_data.gate_id,
            object_class=event_data.object_class,
            detected_text=event_data.detected_text,
            confidence_score=event_data.confidence_score,
            bounding_box_json=event_data.bounding_box_json,
            image_storage_path=event_data.image_storage_path,
            processing_duration_ms=event_data.processing_duration_ms
        )
        
        # Auto-create correction if confidence is low
        if event_data.confidence_score and event_data.confidence_score < self.confidence_threshold:
            await self.recognition_repo.add_correction(
                recognition_id=event.recognition_id,
                corrected_value="",  # Empty, awaiting operator input
                operator_id=None,
                reason_code=None
            )
        
        return event
    
    async def get_pending_reviews(
        self, 
        skip: int = 0, 
        limit: int = 100
    ) -> List[AIRecognitionEvent]:
        """Get events that need human review (low confidence)."""
        return await self.recognition_repo.get_low_confidence(
            threshold=self.confidence_threshold,
            skip=skip,
            limit=limit
        )
    
    async def submit_correction(
        self, 
        correction_data: AICorrectionCreate,
        operator_id: Optional[int] = None
    ) -> AICorrection:
        """Submit a correction from an operator."""
        return await self.recognition_repo.add_correction(
            recognition_id=correction_data.recognition_id,
            corrected_value=correction_data.corrected_value,
            operator_id=operator_id,
            reason_code=correction_data.reason_code
        )
    
    async def get_corrections(self, recognition_id: int) -> List[AICorrection]:
        """Get all corrections for a recognition event."""
        return await self.recognition_repo.get_corrections(recognition_id)
    
    def needs_review(self, event: AIRecognitionEvent) -> bool:
        """Check if an event needs human review."""
        if event.confidence_score is None:
            return True
        return event.confidence_score < self.confidence_threshold
