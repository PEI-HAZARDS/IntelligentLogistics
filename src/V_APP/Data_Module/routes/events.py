"""DEPRECATED — reads from the legacy events collection (7-day TTL, Phase 9).
Use /api/v1/arrivals or /api/v1/decisions for canonical reads."""
import logging
from fastapi import APIRouter
from typing import List
from application.schemas import EventResponse
from application.queries.event_queries import get_events

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/events", response_model=List[EventResponse])
def list_events(type: str = None, limit: int = 10):
    logger.warning(
        "DEPRECATED: GET /events reads from the legacy events collection "
        "which expires after 7 days. Use /arrivals or /decisions instead."
    )
    return get_events(type, limit)
