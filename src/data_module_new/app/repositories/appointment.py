from typing import Optional, List
from datetime import datetime, timedelta
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base import BaseRepository
from app.models import Appointment


class AppointmentRepository(BaseRepository[Appointment]):
    """Repository for Appointment operations."""
    
    def __init__(self, db: AsyncSession):
        super().__init__(Appointment, db)
    
    async def get_by_truck_and_status(
        self, 
        truck_id: int, 
        status: str
    ) -> List[Appointment]:
        """Find appointments for a truck with specific status."""
        result = await self.db.execute(
            select(Appointment).where(
                and_(
                    Appointment.truck_id == truck_id,
                    Appointment.appointment_status == status
                )
            )
        )
        return list(result.scalars().all())
    
    async def find_valid_arrival_appointment(
        self, 
        truck_id: int, 
        current_time: datetime,
        tolerance_minutes: int = 30
    ) -> Optional[Appointment]:
        """
        Find a CONFIRMED appointment for the truck within the time window.
        Returns the earliest scheduled appointment if multiple exist.
        """
        window_start = current_time - timedelta(minutes=tolerance_minutes)
        window_end = current_time + timedelta(minutes=tolerance_minutes)
        
        result = await self.db.execute(
            select(Appointment).where(
                and_(
                    Appointment.truck_id == truck_id,
                    Appointment.appointment_status == 'CONFIRMED',
                    Appointment.scheduled_start_time <= window_end,
                    Appointment.scheduled_end_time >= window_start
                )
            ).order_by(Appointment.scheduled_start_time)
        )
        return result.scalars().first()
    
    async def confirm_appointment(
        self, 
        appointment_id: int, 
        truck_id: int, 
        driver_id: int
    ) -> Optional[Appointment]:
        """Confirm an appointment with truck and driver assignment."""
        appointment = await self.get_by_id(appointment_id)
        if appointment:
            appointment.appointment_status = 'CONFIRMED'
            appointment.truck_id = truck_id
            appointment.driver_id = driver_id
            await self.db.flush()
            await self.db.refresh(appointment)
        return appointment
    
    async def mark_completed(self, appointment_id: int) -> Optional[Appointment]:
        """Mark an appointment as completed."""
        appointment = await self.get_by_id(appointment_id)
        if appointment:
            appointment.appointment_status = 'COMPLETED'
            await self.db.flush()
            await self.db.refresh(appointment)
        return appointment
