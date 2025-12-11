from typing import Optional, List
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.repositories.gate_visit import GateVisitRepository
from app.repositories.truck import TruckRepository
from app.repositories.appointment import AppointmentRepository
from app.models import GateVisit, VisitEventLog
from app.schemas import GateCheckIn, VisitEventCreate, VisitUpdateStage


class GateVisitService:
    """Service for gate visit operations with business logic."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.visit_repo = GateVisitRepository(db)
        self.truck_repo = TruckRepository(db)
        self.appointment_repo = AppointmentRepository(db)
    
    async def get_by_id(self, visit_id: int) -> Optional[GateVisit]:
        """Get visit by ID."""
        return await self.visit_repo.get_by_id(visit_id)
    
    async def get_active_visits(
        self, 
        skip: int = 0, 
        limit: int = 100
    ) -> List[GateVisit]:
        """Get all active visits."""
        return await self.visit_repo.get_active_visits(skip=skip, limit=limit)
    
    async def check_in(
        self, 
        gate_id: int, 
        check_in_data: GateCheckIn
    ) -> GateVisit:
        """
        Process gate check-in.
        - Look up truck by license plate
        - Validate against confirmed appointment if applicable
        - Create visit record
        """
        # Find or create truck
        truck = await self.truck_repo.get_by_license_plate(check_in_data.license_plate)
        if not truck:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Truck with plate {check_in_data.license_plate} not found"
            )
        
        # Update last seen
        await self.truck_repo.update_last_seen(truck.truck_id)
        
        # Validate appointment if provided
        appointment_id = check_in_data.appointment_id
        driver_id = None
        
        if appointment_id:
            appointment = await self.appointment_repo.get_by_id(appointment_id)
            if not appointment:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Appointment {appointment_id} not found"
                )
            if appointment.appointment_status != 'CONFIRMED':
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Appointment is not confirmed"
                )
            if appointment.truck_id != truck.truck_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Truck does not match appointment"
                )
            driver_id = appointment.driver_id
        else:
            # Try to find valid appointment automatically
            valid_appointment = await self.appointment_repo.find_valid_arrival_appointment(
                truck_id=truck.truck_id,
                current_time=datetime.utcnow()
            )
            if valid_appointment:
                appointment_id = valid_appointment.appointment_id
                driver_id = valid_appointment.driver_id
        
        # Create visit
        visit = await self.visit_repo.check_in(
            truck_id=truck.truck_id,
            driver_id=driver_id,
            entry_gate_id=gate_id,
            appointment_id=appointment_id
        )
        
        # Log check-in event
        await self.visit_repo.add_event(
            visit_id=visit.visit_id,
            event_type='GATE_CHECK_IN',
            description=f"Check-in at gate {gate_id}"
        )
        
        return visit
    
    async def check_out(
        self, 
        visit_id: int, 
        exit_gate_id: int
    ) -> Optional[GateVisit]:
        """Process gate check-out."""
        visit = await self.visit_repo.check_out(visit_id, exit_gate_id)
        if visit:
            # Log check-out event
            await self.visit_repo.add_event(
                visit_id=visit_id,
                event_type='GATE_OUT',
                description=f"Check-out at gate {exit_gate_id}"
            )
            # Mark appointment as completed if exists
            if visit.appointment_id:
                await self.appointment_repo.mark_completed(visit.appointment_id)
        return visit
    
    async def update_stage(
        self, 
        visit_id: int, 
        update_data: VisitUpdateStage
    ) -> Optional[GateVisit]:
        """Update visit stage."""
        visit = await self.visit_repo.get_by_id(visit_id)
        if not visit:
            return None
        
        return await self.visit_repo.update_stage(visit_id, update_data.visit_stage)

    
    async def add_event(
        self, 
        visit_id: int, 
        event_data: VisitEventCreate
    ) -> VisitEventLog:
        """Add an event to the visit log."""
        return await self.visit_repo.add_event(
            visit_id=visit_id,
            event_type=event_data.event_type,
            location_id=event_data.location_id,
            description=event_data.description
        )
    
    async def get_events(self, visit_id: int) -> List[VisitEventLog]:
        """Get all events for a visit."""
        return await self.visit_repo.get_events(visit_id)
    
    async def calculate_dwell_time(self, visit_id: int) -> Optional[int]:
        """Calculate dwell time in minutes for a visit."""
        visit = await self.visit_repo.get_by_id(visit_id)
        if not visit or not visit.gate_in_time:
            return None
        
        end_time = visit.gate_out_time or datetime.utcnow()
        delta = end_time - visit.gate_in_time
        return int(delta.total_seconds() / 60)
