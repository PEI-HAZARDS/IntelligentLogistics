from typing import Optional, List
from datetime import datetime
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base import BaseRepository
from app.models import AIRecognitionEvent, AICorrection


class AIRecognitionRepository(BaseRepository[AIRecognitionEvent]):
    """Repository for AI Recognition operations."""
    
    def __init__(self, db: AsyncSession):
        super().__init__(AIRecognitionEvent, db)
    
    async def get_by_gate(
        self, 
        gate_id: int, 
        skip: int = 0, 
        limit: int = 100
    ) -> List[AIRecognitionEvent]:
        """Get recognition events for a specific gate."""
        result = await self.db.execute(
            select(AIRecognitionEvent)
            .where(AIRecognitionEvent.gate_id == gate_id)
            .order_by(AIRecognitionEvent.timestamp.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_low_confidence(
        self, 
        threshold: float,
        skip: int = 0,
        limit: int = 100
    ) -> List[AIRecognitionEvent]:
        """Get events with confidence below threshold that need review."""
        result = await self.db.execute(
            select(AIRecognitionEvent)
            .where(AIRecognitionEvent.confidence_score < threshold)
            .order_by(AIRecognitionEvent.timestamp.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def create_recognition(
        self,
        gate_id: int,
        object_class: Optional[str] = None,
        detected_text: Optional[str] = None,
        confidence_score: Optional[float] = None,
        bounding_box_json: Optional[dict] = None,
        image_storage_path: Optional[str] = None,
        processing_duration_ms: Optional[int] = None
    ) -> AIRecognitionEvent:
        """Create a new AI recognition event."""
        event = AIRecognitionEvent(
            gate_id=gate_id,
            timestamp=datetime.utcnow(),
            object_class=object_class,
            detected_text=detected_text,
            confidence_score=confidence_score,
            bounding_box_json=bounding_box_json,
            image_storage_path=image_storage_path,
            processing_duration_ms=processing_duration_ms
        )
        self.db.add(event)
        await self.db.flush()
        await self.db.refresh(event)
        return event
    
    async def add_correction(
        self,
        recognition_id: int,
        corrected_value: str,
        operator_id: Optional[int] = None,
        reason_code: Optional[str] = None
    ) -> AICorrection:
        """Add a correction for an AI recognition."""
        correction = AICorrection(
            recognition_id=recognition_id,
            corrected_value=corrected_value,
            operator_id=operator_id,
            reason_code=reason_code,
            is_retrained=False,
            created_at=datetime.utcnow()
        )
        self.db.add(correction)
        await self.db.flush()
        await self.db.refresh(correction)
        return correction
    
    async def get_corrections(self, recognition_id: int) -> List[AICorrection]:
        """Get all corrections for a recognition event."""
        result = await self.db.execute(
            select(AICorrection)
            .where(AICorrection.recognition_id == recognition_id)
            .order_by(AICorrection.created_at)
        )
        return list(result.scalars().all())
