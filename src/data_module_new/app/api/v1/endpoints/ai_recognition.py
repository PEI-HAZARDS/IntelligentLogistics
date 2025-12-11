from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.services.ai_recognition import AIRecognitionService
from app.schemas import (
    AIEventCreate,
    AIEventResponse,
    AICorrectionCreate,
    AICorrectionResponse
)


router = APIRouter(prefix="/ai", tags=["AI Recognition"])


@router.post("/recognitions", response_model=AIEventResponse, status_code=status.HTTP_201_CREATED)
async def ingest_recognition(
    event_data: AIEventCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Ingest a new AI recognition event.
    If confidence is below threshold, a pending correction is automatically created.
    """
    ai_service = AIRecognitionService(db)
    event = await ai_service.ingest_event(event_data)
    
    return AIEventResponse(
        recognition_id=event.recognition_id,
        gate_id=event.gate_id,
        timestamp=event.timestamp,
        object_class=event.object_class,
        detected_text=event.detected_text,
        confidence_score=event.confidence_score,
        bounding_box_json=event.bounding_box_json,
        image_storage_path=event.image_storage_path,
        processing_duration_ms=event.processing_duration_ms,
        needs_review=ai_service.needs_review(event)
    )


@router.get("/recognitions/{recognition_id}", response_model=AIEventResponse)
async def get_recognition(
    recognition_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get an AI recognition event by ID."""
    ai_service = AIRecognitionService(db)
    event = await ai_service.get_by_id(recognition_id)
    
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recognition event with ID {recognition_id} not found"
        )
    
    return AIEventResponse(
        recognition_id=event.recognition_id,
        gate_id=event.gate_id,
        timestamp=event.timestamp,
        object_class=event.object_class,
        detected_text=event.detected_text,
        confidence_score=event.confidence_score,
        bounding_box_json=event.bounding_box_json,
        image_storage_path=event.image_storage_path,
        processing_duration_ms=event.processing_duration_ms,
        needs_review=ai_service.needs_review(event)
    )


@router.get("/recognitions/gate/{gate_id}", response_model=List[AIEventResponse])
async def get_gate_recognitions(
    gate_id: int,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """Get all recognition events for a specific gate."""
    ai_service = AIRecognitionService(db)
    events = await ai_service.get_by_gate(gate_id, skip, limit)
    
    return [
        AIEventResponse(
            recognition_id=e.recognition_id,
            gate_id=e.gate_id,
            timestamp=e.timestamp,
            object_class=e.object_class,
            detected_text=e.detected_text,
            confidence_score=e.confidence_score,
            bounding_box_json=e.bounding_box_json,
            image_storage_path=e.image_storage_path,
            processing_duration_ms=e.processing_duration_ms,
            needs_review=ai_service.needs_review(e)
        )
        for e in events
    ]


@router.get("/pending-reviews", response_model=List[AIEventResponse])
async def get_pending_reviews(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """Get recognition events that need human review (low confidence)."""
    ai_service = AIRecognitionService(db)
    events = await ai_service.get_pending_reviews(skip, limit)
    
    return [
        AIEventResponse(
            recognition_id=e.recognition_id,
            gate_id=e.gate_id,
            timestamp=e.timestamp,
            object_class=e.object_class,
            detected_text=e.detected_text,
            confidence_score=e.confidence_score,
            bounding_box_json=e.bounding_box_json,
            image_storage_path=e.image_storage_path,
            processing_duration_ms=e.processing_duration_ms,
            needs_review=True
        )
        for e in events
    ]


@router.post("/corrections", response_model=AICorrectionResponse, status_code=status.HTTP_201_CREATED)
async def submit_correction(
    correction_data: AICorrectionCreate,
    worker_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Submit a correction for an AI recognition event.
    Requires authentication.
    """
    ai_service = AIRecognitionService(db)
    
    # Verify recognition exists
    event = await ai_service.get_by_id(correction_data.recognition_id)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recognition event with ID {correction_data.recognition_id} not found"
        )
    
    correction = await ai_service.submit_correction(correction_data, operator_id=worker_id)
    return correction


@router.get("/corrections/{recognition_id}", response_model=List[AICorrectionResponse])
async def get_corrections(
    recognition_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get all corrections for a recognition event."""
    ai_service = AIRecognitionService(db)
    
    # Verify recognition exists
    event = await ai_service.get_by_id(recognition_id)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recognition event with ID {recognition_id} not found"
        )
    
    corrections = await ai_service.get_corrections(recognition_id)
    return corrections
