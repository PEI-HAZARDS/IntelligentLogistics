from typing import Optional, List
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.appointment import AppointmentRepository
from app.models import Appointment
from app.schemas import AppointmentCreate, AppointmentConfirm, AppointmentWindowCheck


class AppointmentService:
    """Service for appointment operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.appointment_repo = AppointmentRepository(db)
    
    async def get_all(self, skip: int = 0, limit: int = 100) -> List[Appointment]:
        """Get all appointments with pagination."""
        return await self.appointment_repo.get_all(skip=skip, limit=limit)
    
    async def get_by_id(self, appointment_id: int) -> Optional[Appointment]:
        """Get appointment by ID."""
        return await self.appointment_repo.get_by_id(appointment_id)
    
    async def create(self, appointment_data: AppointmentCreate) -> Appointment:
        """Create a new appointment."""
        data = appointment_data.model_dump()
        data['appointment_status'] = 'CREATED'
        return await self.appointment_repo.create(data)
    
    async def confirm(
        self, 
        appointment_id: int, 
        confirm_data: AppointmentConfirm
    ) -> Optional[Appointment]:
        """Confirm an appointment with truck and driver."""
        return await self.appointment_repo.confirm_appointment(
            appointment_id=appointment_id,
            truck_id=confirm_data.truck_id,
            driver_id=confirm_data.driver_id
        )
    
    async def check_window(
        self, 
        appointment_id: int, 
        current_time: Optional[datetime] = None
    ) -> Optional[AppointmentWindowCheck]:
        """Check if current time is within appointment window."""
        appointment = await self.appointment_repo.get_by_id(appointment_id)
        if not appointment:
            return None
        
        now = current_time or datetime.utcnow()
        is_within = (
            appointment.scheduled_start_time <= now <= appointment.scheduled_end_time
        )
        
        result = AppointmentWindowCheck(
            appointment_id=appointment.appointment_id,
            is_within_window=is_within,
            scheduled_start_time=appointment.scheduled_start_time,
            scheduled_end_time=appointment.scheduled_end_time,
            current_time=now
        )
        
        if now < appointment.scheduled_start_time:
            delta = appointment.scheduled_start_time - now
            result.minutes_early = int(delta.total_seconds() / 60)
        elif now > appointment.scheduled_end_time:
            delta = now - appointment.scheduled_end_time
            result.minutes_late = int(delta.total_seconds() / 60)
        
        return result
    
    async def validate_arrival(
        self, 
        truck_id: int, 
        tolerance_minutes: int = 30
    ) -> Optional[Appointment]:
        """Validate truck arrival against confirmed appointments."""
        return await self.appointment_repo.find_valid_arrival_appointment(
            truck_id=truck_id,
            current_time=datetime.utcnow(),
            tolerance_minutes=tolerance_minutes
        )
    
    async def mark_completed(self, appointment_id: int) -> Optional[Appointment]:
        """Mark an appointment as completed."""
        return await self.appointment_repo.mark_completed(appointment_id)
