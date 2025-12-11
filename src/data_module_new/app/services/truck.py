from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.truck import TruckRepository
from app.models import Truck
from app.schemas import TruckCreate, TruckUpdate


class TruckService:
    """Service for truck operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.truck_repo = TruckRepository(db)
    
    async def get_all(self, skip: int = 0, limit: int = 100) -> List[Truck]:
        """Get all trucks with pagination."""
        return await self.truck_repo.get_all(skip=skip, limit=limit)
    
    async def get_by_id(self, truck_id: int) -> Optional[Truck]:
        """Get truck by ID."""
        return await self.truck_repo.get_by_id(truck_id)
    
    async def get_by_plate(self, license_plate: str) -> Optional[Truck]:
        """Get truck by license plate."""
        return await self.truck_repo.get_by_license_plate(license_plate)
    
    async def create(self, truck_data: TruckCreate) -> Truck:
        """Create a new truck."""
        return await self.truck_repo.create(truck_data.model_dump())
    
    async def update(self, truck_id: int, truck_data: TruckUpdate) -> Optional[Truck]:
        """Update an existing truck."""
        return await self.truck_repo.update(
            truck_id, 
            truck_data.model_dump(exclude_unset=True)
        )
    
    async def delete(self, truck_id: int) -> bool:
        """Delete a truck."""
        return await self.truck_repo.delete(truck_id)
    
    async def count(self) -> int:
        """Get total truck count."""
        return await self.truck_repo.count()
