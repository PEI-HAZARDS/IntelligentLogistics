from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from models.pydantic_models import ChegadaResponse, ChegadaCreate
from services.arrival_service import get_arrivals, update_arrival
from db.postgres import get_db

router = APIRouter()

@router.get("/arrivals", response_model=List[ChegadaResponse])
def list_arrivals(matricula: str = None, db: Session = Depends(get_db)):
    return get_arrivals(db, matricula)

@router.put("/arrivals/{id}", response_model=ChegadaResponse)
def update_arrival_endpoint(id: int, chegada: ChegadaCreate, db: Session = Depends(get_db)):
    return update_arrival(db, id, chegada)
