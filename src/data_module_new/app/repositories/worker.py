from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base import BaseRepository
from app.models import Worker


class WorkerRepository(BaseRepository[Worker]):
    """Repository for Worker operations."""
    
    def __init__(self, db: AsyncSession):
        super().__init__(Worker, db)
    
    async def get_by_email(self, email: str) -> Optional[Worker]:
        """Find a worker by email address."""
        result = await self.db.execute(
            select(Worker).where(Worker.email == email)
        )
        return result.scalar_one_or_none()
    
    async def get_active_workers(self, skip: int = 0, limit: int = 100):
        """Get all active workers."""
        result = await self.db.execute(
            select(Worker)
            .where(Worker.is_active == True)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def create_worker(
        self,
        full_name: str,
        email: str,
        password_hash: str,
        role: str = "operator",
        assigned_gate_id: Optional[int] = None
    ) -> Worker:
        """Create a new worker."""
        worker = Worker(
            full_name=full_name,
            email=email,
            password_hash=password_hash,
            role=role,
            assigned_gate_id=assigned_gate_id,
            is_active=True
        )
        self.db.add(worker)
        await self.db.flush()
        await self.db.refresh(worker)
        return worker
