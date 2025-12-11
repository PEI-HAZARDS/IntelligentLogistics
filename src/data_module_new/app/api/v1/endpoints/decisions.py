from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.services.decision import DecisionService
from app.schemas.decision import (
    QueryArrivalsRequest,
    QueryArrivalsResponse,
    DecisionCreate,
    DecisionResponse,
    ManualReviewRequest,
)


router = APIRouter(prefix="/decisions", tags=["Decisions"])


@router.post("/query-arrivals", response_model=QueryArrivalsResponse)
async def query_arrivals(
    request: QueryArrivalsRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Query appointments for a given license plate and gate.
    Called by the Decision Engine to validate incoming vehicles.
    
    Returns matching appointment candidates within the time window.
    """
    decision_service = DecisionService(db)
    result = await decision_service.query_arrivals(request)
    return result


@router.post("", response_model=DecisionResponse, status_code=status.HTTP_201_CREATED)
async def create_decision(
    decision_data: DecisionCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new access decision.
    Called when the Decision Engine publishes a decision (via Kafka consumer or direct API).
    """
    decision_service = DecisionService(db)
    
    # Check if decision already exists
    existing = await decision_service.get_decision_by_event(decision_data.event_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Decision with event_id '{decision_data.event_id}' already exists"
        )
    
    decision = await decision_service.create_decision(decision_data)
    
    return DecisionResponse(
        decision_id=decision.decision_id,
        event_id=decision.event_id,
        gate_id=decision.gate_id,
        decision=decision.decision,
        reason=decision.reason,
        license_plate=decision.license_plate,
        un_number=decision.un_number,
        kemler_code=decision.kemler_code,
        plate_image_url=decision.plate_image_url,
        hazard_image_url=decision.hazard_image_url,
        route=decision.route,
        alerts=decision.alerts,
        lp_confidence=decision.lp_confidence,
        hz_confidence=decision.hz_confidence,
        reviewed_by=decision.reviewed_by,
        reviewed_at=decision.reviewed_at,
        original_decision=decision.original_decision,
        created_at=decision.created_at
    )


@router.get("/{decision_id}", response_model=DecisionResponse)
async def get_decision(
    decision_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get a decision by ID."""
    decision_service = DecisionService(db)
    decision = await decision_service.get_decision(decision_id)
    
    if not decision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Decision with ID {decision_id} not found"
        )
    
    return DecisionResponse(
        decision_id=decision.decision_id,
        event_id=decision.event_id,
        gate_id=decision.gate_id,
        decision=decision.decision,
        reason=decision.reason,
        license_plate=decision.license_plate,
        un_number=decision.un_number,
        kemler_code=decision.kemler_code,
        plate_image_url=decision.plate_image_url,
        hazard_image_url=decision.hazard_image_url,
        route=decision.route,
        alerts=decision.alerts,
        lp_confidence=decision.lp_confidence,
        hz_confidence=decision.hz_confidence,
        reviewed_by=decision.reviewed_by,
        reviewed_at=decision.reviewed_at,
        original_decision=decision.original_decision,
        created_at=decision.created_at
    )


@router.get("/event/{event_id}", response_model=DecisionResponse)
async def get_decision_by_event(
    event_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get a decision by event ID."""
    decision_service = DecisionService(db)
    decision = await decision_service.get_decision_by_event(event_id)
    
    if not decision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Decision with event_id '{event_id}' not found"
        )
    
    return DecisionResponse(
        decision_id=decision.decision_id,
        event_id=decision.event_id,
        gate_id=decision.gate_id,
        decision=decision.decision,
        reason=decision.reason,
        license_plate=decision.license_plate,
        un_number=decision.un_number,
        kemler_code=decision.kemler_code,
        plate_image_url=decision.plate_image_url,
        hazard_image_url=decision.hazard_image_url,
        route=decision.route,
        alerts=decision.alerts,
        lp_confidence=decision.lp_confidence,
        hz_confidence=decision.hz_confidence,
        reviewed_by=decision.reviewed_by,
        reviewed_at=decision.reviewed_at,
        original_decision=decision.original_decision,
        created_at=decision.created_at
    )


@router.get("/gate/{gate_id}", response_model=List[DecisionResponse])
async def get_decisions_by_gate(
    gate_id: int,
    skip: int = 0,
    limit: int = 100,
    from_date: Optional[datetime] = Query(None),
    to_date: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Get all decisions for a specific gate with optional date filters."""
    decision_service = DecisionService(db)
    decisions = await decision_service.get_decisions_by_gate(
        gate_id, skip, limit, from_date, to_date
    )
    
    return [
        DecisionResponse(
            decision_id=d.decision_id,
            event_id=d.event_id,
            gate_id=d.gate_id,
            decision=d.decision,
            reason=d.reason,
            license_plate=d.license_plate,
            un_number=d.un_number,
            kemler_code=d.kemler_code,
            plate_image_url=d.plate_image_url,
            hazard_image_url=d.hazard_image_url,
            route=d.route,
            alerts=d.alerts,
            lp_confidence=d.lp_confidence,
            hz_confidence=d.hz_confidence,
            reviewed_by=d.reviewed_by,
            reviewed_at=d.reviewed_at,
            original_decision=d.original_decision,
            created_at=d.created_at
        )
        for d in decisions
    ]


@router.get("/pending-reviews", response_model=List[DecisionResponse])
async def get_pending_reviews(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """Get decisions that need manual review."""
    decision_service = DecisionService(db)
    decisions = await decision_service.get_pending_reviews(skip, limit)
    
    return [
        DecisionResponse(
            decision_id=d.decision_id,
            event_id=d.event_id,
            gate_id=d.gate_id,
            decision=d.decision,
            reason=d.reason,
            license_plate=d.license_plate,
            un_number=d.un_number,
            kemler_code=d.kemler_code,
            plate_image_url=d.plate_image_url,
            hazard_image_url=d.hazard_image_url,
            route=d.route,
            alerts=d.alerts,
            lp_confidence=d.lp_confidence,
            hz_confidence=d.hz_confidence,
            reviewed_by=d.reviewed_by,
            reviewed_at=d.reviewed_at,
            original_decision=d.original_decision,
            created_at=d.created_at
        )
        for d in decisions
    ]


@router.post("/{decision_id}/manual-review", response_model=DecisionResponse)
async def submit_manual_review(
    decision_id: int,
    review_data: ManualReviewRequest,
    worker_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Submit a manual review for a decision.
    Requires authentication. The operator can override the decision.
    """
    decision_service = DecisionService(db)
    
    decision = await decision_service.submit_manual_review(
        decision_id, worker_id, review_data
    )
    
    if not decision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Decision with ID {decision_id} not found"
        )
    
    return DecisionResponse(
        decision_id=decision.decision_id,
        event_id=decision.event_id,
        gate_id=decision.gate_id,
        decision=decision.decision,
        reason=decision.reason,
        license_plate=decision.license_plate,
        un_number=decision.un_number,
        kemler_code=decision.kemler_code,
        plate_image_url=decision.plate_image_url,
        hazard_image_url=decision.hazard_image_url,
        route=decision.route,
        alerts=decision.alerts,
        lp_confidence=decision.lp_confidence,
        hz_confidence=decision.hz_confidence,
        reviewed_by=decision.reviewed_by,
        reviewed_at=decision.reviewed_at,
        original_decision=decision.original_decision,
        created_at=decision.created_at
    )
