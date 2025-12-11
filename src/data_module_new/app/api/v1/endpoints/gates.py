from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models import Gate
from app.services.gate_visit import GateVisitService
from app.schemas import GateResponse, GateCheckIn, VisitResponse


router = APIRouter(prefix="/gates", tags=["Gates"])


@router.get("", response_model=List[GateResponse])
async def list_gates(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """Get all gates with pagination."""
    result = await db.execute(select(Gate).offset(skip).limit(limit))
    gates = result.scalars().all()
    return gates


@router.get("/{gate_id}", response_model=GateResponse)
async def get_gate(
    gate_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get a gate by ID."""
    result = await db.execute(select(Gate).where(Gate.gate_id == gate_id))
    gate = result.scalar_one_or_none()
    
    if not gate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Gate with ID {gate_id} not found"
        )
    
    return gate


@router.post("/{gate_id}/check-in", response_model=VisitResponse)
async def gate_check_in(
    gate_id: int,
    check_in_data: GateCheckIn,
    db: AsyncSession = Depends(get_db)
):
    """
    Process gate check-in.
    - Validates truck by license plate
    - Matches against confirmed appointment if available
    - Creates a new visit record
    """
    # Verify gate exists
    result = await db.execute(select(Gate).where(Gate.gate_id == gate_id))
    gate = result.scalar_one_or_none()
    
    if not gate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Gate with ID {gate_id} not found"
        )
    
    if gate.operational_status != 'OPEN':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Gate {gate.gate_label} is not open"
        )
    
    visit_service = GateVisitService(db)
    visit = await visit_service.check_in(gate_id, check_in_data)
    
    # Calculate dwell time
    dwell_time = await visit_service.calculate_dwell_time(visit.visit_id)
    
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
