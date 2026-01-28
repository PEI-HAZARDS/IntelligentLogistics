from fastapi import APIRouter
from typing import List
from models.pydantic_models import EventResponse
from services.event_service import get_events

router = APIRouter()

@router.get("/events", response_model=List[EventResponse])
def list_events(type: str = None, limit: int = 10):
    return get_events(type, limit)
