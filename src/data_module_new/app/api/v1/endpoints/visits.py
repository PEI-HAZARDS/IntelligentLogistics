from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.gate_visit import GateVisitService
from app.schemas import (
    VisitResponse,
    VisitEventCreate,
    VisitEventResponse,
    VisitUpdateStage,
    GateCheckOut
)


router = APIRouter(prefix="/visits", tags=["Visits"])


@router.get("", response_model=List[VisitResponse])
async def list_active_visits(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """Get all active visits (not completed)."""
    visit_service = GateVisitService(db)
    visits = await visit_service.get_active_visits(skip=skip, limit=limit)
    
    result = []
    for visit in visits:
        dwell_time = await visit_service.calculate_dwell_time(visit.visit_id)
        result.append(VisitResponse(
            visit_id=visit.visit_id,
            appointment_id=visit.appointment_id,
            truck_id=visit.truck_id,
            driver_id=visit.driver_id,
            entry_gate_id=visit.entry_gate_id,
            exit_gate_id=visit.exit_gate_id,
            gate_in_time=visit.gate_in_time,
            gate_out_time=visit.gate_out_time,
            visit_stage=visit.visit_stage,
            dwell_time_minutes=dwell_time
        ))
    
    return result


@router.get("/{visit_id}", response_model=VisitResponse)
async def get_visit(
    visit_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get a visit by ID with dwell time calculation."""
    visit_service = GateVisitService(db)
    visit = await visit_service.get_by_id(visit_id)
    
    if not visit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Visit with ID {visit_id} not found"
        )
    
    dwell_time = await visit_service.calculate_dwell_time(visit_id)
    
    return VisitResponse(
        visit_id=visit.visit_id,
        appointment_id=visit.appointment_id,
        truck_id=visit.truck_id,
        driver_id=visit.driver_id,
        entry_gate_id=visit.entry_gate_id,
        exit_gate_id=visit.exit_gate_id,
        gate_in_time=visit.gate_in_time,
        gate_out_time=visit.gate_out_time,
        visit_stage=visit.visit_stage,
        dwell_time_minutes=dwell_time
    )


@router.post("/{visit_id}/check-out", response_model=VisitResponse)
async def visit_check_out(
    visit_id: int,
    check_out_data: GateCheckOut,
    db: AsyncSession = Depends(get_db)
):
    """Process gate check-out for a visit."""
    visit_service = GateVisitService(db)
    
    exit_gate_id = check_out_data.exit_gate_id or check_out_data.visit_id
    visit = await visit_service.check_out(visit_id, exit_gate_id)
    
    if not visit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Visit with ID {visit_id} not found"
        )
    
    dwell_time = await visit_service.calculate_dwell_time(visit_id)
    
    return VisitResponse(
        visit_id=visit.visit_id,
        appointment_id=visit.appointment_id,
        truck_id=visit.truck_id,
        driver_id=visit.driver_id,
        entry_gate_id=visit.entry_gate_id,
        exit_gate_id=visit.exit_gate_id,
        gate_in_time=visit.gate_in_time,
        gate_out_time=visit.gate_out_time,
        visit_stage=visit.visit_stage,
        dwell_time_minutes=dwell_time
    )


@router.put("/{visit_id}/stage", response_model=VisitResponse)
async def update_visit_stage(
    visit_id: int,
    stage_data: VisitUpdateStage,
    db: AsyncSession = Depends(get_db)
):
    """
    Update the stage of a visit.
    """
    visit_service = GateVisitService(db)
    visit = await visit_service.update_stage(visit_id, stage_data)
    
    if not visit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Visit with ID {visit_id} not found"
        )
    
    dwell_time = await visit_service.calculate_dwell_time(visit_id)
    
    return VisitResponse(
        visit_id=visit.visit_id,
        appointment_id=visit.appointment_id,
        truck_id=visit.truck_id,
        driver_id=visit.driver_id,
        entry_gate_id=visit.entry_gate_id,
        exit_gate_id=visit.exit_gate_id,
        gate_in_time=visit.gate_in_time,
        gate_out_time=visit.gate_out_time,
        visit_stage=visit.visit_stage,
        dwell_time_minutes=dwell_time
    )


@router.post("/{visit_id}/events", response_model=VisitEventResponse, status_code=status.HTTP_201_CREATED)
async def add_visit_event(
    visit_id: int,
    event_data: VisitEventCreate,
    db: AsyncSession = Depends(get_db)
):
    """Add an event to the visit log."""
    visit_service = GateVisitService(db)
    
    # Verify visit exists
    visit = await visit_service.get_by_id(visit_id)
    if not visit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Visit with ID {visit_id} not found"
        )
    
    event = await visit_service.add_event(visit_id, event_data)
    return event


@router.get("/{visit_id}/events", response_model=List[VisitEventResponse])
async def get_visit_events(
    visit_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get all events for a visit."""
    visit_service = GateVisitService(db)
    
    # Verify visit exists
    visit = await visit_service.get_by_id(visit_id)
    if not visit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Visit with ID {visit_id} not found"
        )
    
    events = await visit_service.get_events(visit_id)
    return events
