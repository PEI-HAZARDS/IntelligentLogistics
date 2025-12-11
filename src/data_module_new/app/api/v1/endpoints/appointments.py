from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.appointment import AppointmentService
from app.schemas import (
    AppointmentCreate, 
    AppointmentConfirm, 
    AppointmentResponse, 
    AppointmentWindowCheck
)


router = APIRouter(prefix="/appointments", tags=["Appointments"])


@router.get("", response_model=List[AppointmentResponse])
async def list_appointments(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """Get all appointments with pagination."""
    appointment_service = AppointmentService(db)
    appointments = await appointment_service.get_all(skip=skip, limit=limit)
    return appointments


@router.post("", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
async def create_appointment(
    appointment_data: AppointmentCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new appointment."""
    appointment_service = AppointmentService(db)
    appointment = await appointment_service.create(appointment_data)
    return appointment


@router.get("/{appointment_id}", response_model=AppointmentResponse)
async def get_appointment(
    appointment_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get an appointment by ID."""
    appointment_service = AppointmentService(db)
    appointment = await appointment_service.get_by_id(appointment_id)
    
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Appointment with ID {appointment_id} not found"
        )
    
    return appointment


@router.put("/{appointment_id}/confirm", response_model=AppointmentResponse)
async def confirm_appointment(
    appointment_id: int,
    confirm_data: AppointmentConfirm,
    db: AsyncSession = Depends(get_db)
):
    """Confirm an appointment with truck and driver assignment."""
    appointment_service = AppointmentService(db)
    appointment = await appointment_service.confirm(appointment_id, confirm_data)
    
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Appointment with ID {appointment_id} not found"
        )
    
    return appointment


@router.get("/{appointment_id}/window", response_model=AppointmentWindowCheck)
async def check_appointment_window(
    appointment_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Check if current time is within the appointment window."""
    appointment_service = AppointmentService(db)
    result = await appointment_service.check_window(appointment_id)
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Appointment with ID {appointment_id} not found"
        )
    
    return result


@router.post("/{appointment_id}/complete", response_model=AppointmentResponse)
async def complete_appointment(
    appointment_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Mark an appointment as completed."""
    appointment_service = AppointmentService(db)
    appointment = await appointment_service.mark_completed(appointment_id)
    
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Appointment with ID {appointment_id} not found"
        )
    
    return appointment
