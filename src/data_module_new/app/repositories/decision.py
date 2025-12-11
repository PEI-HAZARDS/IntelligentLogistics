from typing import List, Optional
from datetime import datetime
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AccessDecision


class DecisionRepository:
    """Repository for AccessDecision CRUD operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, decision_data: dict) -> AccessDecision:
        """Create a new access decision."""
        decision = AccessDecision(**decision_data)
        self.db.add(decision)
        await self.db.commit()
        await self.db.refresh(decision)
        return decision

    async def get_by_id(self, decision_id: int) -> Optional[AccessDecision]:
        """Get decision by ID."""
        result = await self.db.execute(
            select(AccessDecision).where(AccessDecision.decision_id == decision_id)
        )
        return result.scalar_one_or_none()

    async def get_by_event_id(self, event_id: str) -> Optional[AccessDecision]:
        """Get decision by event ID."""
        result = await self.db.execute(
            select(AccessDecision).where(AccessDecision.event_id == event_id)
        )
        return result.scalar_one_or_none()

    async def get_by_gate(
        self,
        gate_id: int,
        skip: int = 0,
        limit: int = 100,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None
    ) -> List[AccessDecision]:
        """Get decisions for a specific gate with optional date filters."""
        query = select(AccessDecision).where(AccessDecision.gate_id == gate_id)
        
        if from_date:
            query = query.where(AccessDecision.created_at >= from_date)
        if to_date:
            query = query.where(AccessDecision.created_at <= to_date)
        
        query = query.order_by(AccessDecision.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_pending_reviews(self, skip: int = 0, limit: int = 100) -> List[AccessDecision]:
        """Get decisions pending manual review."""
        result = await self.db.execute(
            select(AccessDecision)
            .where(AccessDecision.decision == 'MANUAL_REVIEW')
            .where(AccessDecision.reviewed_by.is_(None))
            .order_by(AccessDecision.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def update(self, decision: AccessDecision, update_data: dict) -> AccessDecision:
        """Update a decision record."""
        for key, value in update_data.items():
            setattr(decision, key, value)
        await self.db.commit()
        await self.db.refresh(decision)
        return decision

    async def get_recent_by_plate(
        self,
        license_plate: str,
        limit: int = 10
    ) -> List[AccessDecision]:
        """Get recent decisions for a specific license plate."""
        result = await self.db.execute(
            select(AccessDecision)
            .where(AccessDecision.license_plate == license_plate)
            .order_by(AccessDecision.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
