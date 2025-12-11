from typing import Optional, List
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base import BaseRepository
from app.models import Truck


class TruckRepository(BaseRepository[Truck]):
    """Repository for Truck operations."""
    
    def __init__(self, db: AsyncSession):
        super().__init__(Truck, db)
    
    async def get_by_license_plate(self, license_plate: str) -> Optional[Truck]:
        """Find a truck by its license plate."""
        result = await self.db.execute(
            select(Truck).where(Truck.license_plate == license_plate)
        )
        return result.scalar_one_or_none()
    
    async def get_by_hauler(self, hauler_id: int, skip: int = 0, limit: int = 100) -> List[Truck]:
        """Get all trucks for a specific hauler."""
        result = await self.db.execute(
            select(Truck)
            .where(Truck.hauler_id == hauler_id)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def update_last_seen(self, truck_id: int) -> Optional[Truck]:
        """Update the last seen date of a truck."""
        truck = await self.get_by_id(truck_id)
        if truck:
            truck.last_seen_date = datetime.utcnow()
            await self.db.flush()
            await self.db.refresh(truck)
        return truck
