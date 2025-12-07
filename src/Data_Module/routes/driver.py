from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from models.pydantic_models import CondutorResponse, ChegadaResponse
from services.driver_service import get_drivers, get_driver_arrivals
from db.postgres import get_db

router = APIRouter()

@router.get("/drivers", response_model=List[CondutorResponse])
def list_drivers(db: Session = Depends(get_db)):
    return get_drivers(db)

@router.get("/drivers/{id}/arrivals", response_model=List[ChegadaResponse])
def get_arrivals_for_driver(id: int, db: Session = Depends(get_db)):
    return get_driver_arrivals(db, id)
