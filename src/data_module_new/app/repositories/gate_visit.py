from typing import Optional, List
from datetime import datetime
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base import BaseRepository
from app.models import GateVisit, VisitEventLog


class GateVisitRepository(BaseRepository[GateVisit]):
    """Repository for GateVisit operations."""
    
    def __init__(self, db: AsyncSession):
        super().__init__(GateVisit, db)
    
    async def get_active_visits(self, skip: int = 0, limit: int = 100) -> List[GateVisit]:
        """Get all active visits (not COMPLETE stage)."""
        result = await self.db.execute(
            select(GateVisit)
            .where(GateVisit.visit_stage != 'COMPLETE')
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_by_truck(self, truck_id: int, active_only: bool = False) -> List[GateVisit]:
        """Get visits for a specific truck."""
        query = select(GateVisit).where(GateVisit.truck_id == truck_id)
        if active_only:
            query = query.where(GateVisit.visit_stage != 'COMPLETE')
        result = await self.db.execute(query.order_by(GateVisit.gate_in_time.desc()))
        return list(result.scalars().all())
    
    async def check_in(
        self,
        truck_id: int,
        driver_id: Optional[int],
        entry_gate_id: int,
        appointment_id: Optional[int] = None
    ) -> GateVisit:
        """Create a new visit for gate check-in."""
        visit = GateVisit(
            truck_id=truck_id,
            driver_id=driver_id,
            entry_gate_id=entry_gate_id,
            appointment_id=appointment_id,
            gate_in_time=datetime.utcnow(),
            visit_stage='AT_GATE'
        )
        self.db.add(visit)
        await self.db.flush()
        await self.db.refresh(visit)
        return visit
    
    async def check_out(self, visit_id: int, exit_gate_id: int) -> Optional[GateVisit]:
        """Complete a visit with gate check-out."""
        visit = await self.get_by_id(visit_id)
        if visit:
            visit.exit_gate_id = exit_gate_id
            visit.gate_out_time = datetime.utcnow()
            visit.visit_stage = 'COMPLETE'
            await self.db.flush()
            await self.db.refresh(visit)
        return visit
    
    async def update_stage(self, visit_id: int, new_stage: str) -> Optional[GateVisit]:
        """Update the stage of a visit."""
        visit = await self.get_by_id(visit_id)
        if visit:
            visit.visit_stage = new_stage
            await self.db.flush()
            await self.db.refresh(visit)
        return visit
    
    async def add_event(
        self,
        visit_id: int,
        event_type: str,
        location_id: Optional[int] = None,
        description: Optional[str] = None
    ) -> VisitEventLog:
        """Add an event to the visit log."""
        event = VisitEventLog(
            visit_id=visit_id,
            event_type=event_type,
            location_id=location_id,
            description=description,
            timestamp=datetime.utcnow()
        )
        self.db.add(event)
        await self.db.flush()
        await self.db.refresh(event)
        return event
    
    async def get_events(self, visit_id: int) -> List[VisitEventLog]:
        """Get all events for a visit."""
        result = await self.db.execute(
            select(VisitEventLog)
            .where(VisitEventLog.visit_id == visit_id)
            .order_by(VisitEventLog.timestamp)
        )
        return list(result.scalars().all())
