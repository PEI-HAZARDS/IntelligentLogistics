from typing import List, Optional
from datetime import datetime, timedelta
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Appointment, Truck, Booking, AccessDecision
from app.repositories.decision import DecisionRepository
from app.schemas.decision import (
    QueryArrivalsRequest,
    QueryArrivalsResponse,
    AppointmentCandidate,
    DecisionCreate,
    DecisionResponse,
    ManualReviewRequest,
)


class DecisionService:
    """Service for handling access decisions and arrival queries."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repository = DecisionRepository(db)

    async def query_arrivals(
        self,
        request: QueryArrivalsRequest,
        time_window_minutes: int = 60
    ) -> QueryArrivalsResponse:
        """
        Query appointments matching a license plate within a time window.
        Called by the Decision Engine to validate incoming vehicles.
        """
        license_plate = request.license_plate
        
        # Find truck by license plate
        truck_result = await self.db.execute(
            select(Truck).where(Truck.license_plate == license_plate)
        )
        truck = truck_result.scalar_one_or_none()

        if not truck:
            return QueryArrivalsResponse(
                found=False,
                message=f"Truck with license plate '{license_plate}' not found in system"
            )

        # Find appointments for this truck within time window
        now = datetime.now()
        window_start = now - timedelta(minutes=time_window_minutes)
        window_end = now + timedelta(minutes=time_window_minutes)

        appointments_result = await self.db.execute(
            select(Appointment)
            .where(
                and_(
                    Appointment.truck_id == truck.truck_id,
                    Appointment.scheduled_start_time <= window_end,
                    Appointment.scheduled_end_time >= window_start,
                    Appointment.appointment_status.in_(['CREATED', 'CONFIRMED'])
                )
            )
            .order_by(Appointment.scheduled_start_time.asc())
        )
        appointments = appointments_result.scalars().all()

        if not appointments:
            return QueryArrivalsResponse(
                found=False,
                message=f"No scheduled appointments found for plate '{license_plate}' within time window"
            )

        # Build candidate list
        candidates = []
        for apt in appointments:
            # Get booking reference if exists
            booking_ref = None
            if apt.booking_id:
                booking_result = await self.db.execute(
                    select(Booking).where(Booking.booking_id == apt.booking_id)
                )
                booking = booking_result.scalar_one_or_none()
                if booking:
                    booking_ref = booking.booking_ref

            candidates.append(AppointmentCandidate(
                appointment_id=apt.appointment_id,
                booking_ref=booking_ref,
                scheduled_start_time=apt.scheduled_start_time,
                scheduled_end_time=apt.scheduled_end_time,
                truck_id=apt.truck_id,
                driver_id=apt.driver_id,
                direction=apt.booking.direction if apt.booking else None
            ))

        return QueryArrivalsResponse(
            found=True,
            candidates=candidates
        )

    async def create_decision(self, data: DecisionCreate) -> AccessDecision:
        """Create a new access decision."""
        decision_data = {
            "event_id": data.event_id,
            "gate_id": data.gate_id,
            "decision": data.decision,
            "reason": data.reason,
            "license_plate": data.license_plate,
            "un_number": data.un_number,
            "kemler_code": data.kemler_code,
            "plate_image_url": data.plate_image_url,
            "hazard_image_url": data.hazard_image_url,
            "route": data.route,
            "alerts": data.alerts,
            "lp_confidence": data.lp_confidence,
            "hz_confidence": data.hz_confidence,
        }
        return await self.repository.create(decision_data)

    async def get_decision(self, decision_id: int) -> Optional[AccessDecision]:
        """Get a decision by ID."""
        return await self.repository.get_by_id(decision_id)

    async def get_decision_by_event(self, event_id: str) -> Optional[AccessDecision]:
        """Get a decision by event ID."""
        return await self.repository.get_by_event_id(event_id)

    async def get_decisions_by_gate(
        self,
        gate_id: int,
        skip: int = 0,
        limit: int = 100,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None
    ) -> List[AccessDecision]:
        """Get decisions for a gate."""
        return await self.repository.get_by_gate(gate_id, skip, limit, from_date, to_date)

    async def get_pending_reviews(self, skip: int = 0, limit: int = 100) -> List[AccessDecision]:
        """Get decisions pending manual review."""
        return await self.repository.get_pending_reviews(skip, limit)

    async def submit_manual_review(
        self,
        decision_id: int,
        operator_id: int,
        review_data: ManualReviewRequest
    ) -> Optional[AccessDecision]:
        """Submit manual review for a decision."""
        decision = await self.repository.get_by_id(decision_id)
        if not decision:
            return None

        update_data = {
            "original_decision": decision.decision,
            "decision": review_data.new_decision,
            "reason": f"Manual review: {review_data.reason}",
            "reviewed_by": operator_id,
            "reviewed_at": datetime.now(),
        }
        
        return await self.repository.update(decision, update_data)
