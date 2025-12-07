from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from models.pydantic_models import ChegadaResponse, ChegadaCreate
from services.arrival_service import (
    get_all_arrivals,
    get_arrivals_by_gate,
    get_arrivals_by_gate_and_shift,
    get_arrivals_by_lpate,
    get_arrivals_count,
    get_arrivals_by_status,
    get_arrivals_count_by_status,
    update_arrival
)
from db.postgres import get_db

router = APIRouter()

# GET /api/v1/arrivals - todas as chegadas (opcional: filtro por matricula)
@router.get("/arrivals", response_model=List[ChegadaResponse])
def list_all_arrivals(
    matricula: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Lista todas as chegadas (com paginação opcional e filtro por matrícula)."""
    return get_all_arrivals(db, matricula=matricula, page=page, limit=limit)

# GET /api/v1/arrivals/{gate_id} - chegadas por gate
@router.get("/arrivals/{gate_id}", response_model=List[ChegadaResponse])
def list_arrivals_by_gate(
    gate_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Lista chegadas filtradas por gate."""
    return get_arrivals_by_gate(db, gate_id=gate_id, page=page, limit=limit)

# GET /api/v1/arrivals/{gate_id}/{shift} - chegadas por gate e turno
@router.get("/arrivals/{gate_id}/{shift}", response_model=List[ChegadaResponse])
def list_arrivals_by_gate_shift(
    gate_id: int,
    shift: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Lista chegadas filtradas por gate e turno (shift id)."""
    return get_arrivals_by_gate_and_shift(db, gate_id=gate_id, shift=shift, page=page, limit=limit)

# GET /api/v1/arrivals/{gate_id}/{shift}/total - contador total
@router.get("/arrivals/{gate_id}/{shift}/total")
def count_arrivals_by_gate_shift(gate_id: int, shift: int, db: Session = Depends(get_db)):
    """Retorna o total de chegadas para um gate e turno."""
    total = get_arrivals_count(db, gate_id=gate_id, shift=shift)
    return {"gate_id": gate_id, "shift": shift, "total": total}

# GET /api/v1/arrivals/{gate_id}/pending - chegadas pendentes por gate
@router.get("/arrivals/{gate_id}/pending", response_model=List[ChegadaResponse])
def list_arrivals_pending(
    gate_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Lista chegadas com estado 'em_transito' (pendentes) por gate."""
    return get_arrivals_by_status(db, gate_id=gate_id, status="em_transito", page=page, limit=limit)

# GET /api/v1/arrivals/{gate_id}/{shift}/pending - chegadas pendentes por gate e turno
@router.get("/arrivals/{gate_id}/{shift}/pending", response_model=List[ChegadaResponse])
def list_arrivals_pending_shift(
    gate_id: int,
    shift: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Lista chegadas pendentes por gate e turno."""
    return get_arrivals_by_status(db, gate_id=gate_id, shift=shift, status="em_transito", page=page, limit=limit)

# GET /api/v1/arrivals/{gate_id}/{shift}/pending/total - contador pendentes
@router.get("/arrivals/{gate_id}/{shift}/pending/total")
def count_arrivals_pending(gate_id: int, shift: int, db: Session = Depends(get_db)):
    """Retorna o total de chegadas pendentes para um gate e turno."""
    total = get_arrivals_count_by_status(db, gate_id=gate_id, shift=shift, status="em_transito")
    return {"gate_id": gate_id, "shift": shift, "status": "pending", "total": total}

# GET /api/v1/arrivals/{gate_id}/in_progress - chegadas em progresso por gate
@router.get("/arrivals/{gate_id}/in_progress", response_model=List[ChegadaResponse])
def list_arrivals_in_progress(
    gate_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Lista chegadas com estado 'em_descarga' (in progress) por gate."""
    return get_arrivals_by_status(db, gate_id=gate_id, status="em_descarga", page=page, limit=limit)

# GET /api/v1/arrivals/{gate_id}/{shift}/in_progress - chegadas em progresso por gate e turno
@router.get("/arrivals/{gate_id}/{shift}/in_progress", response_model=List[ChegadaResponse])
def list_arrivals_in_progress_shift(
    gate_id: int,
    shift: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Lista chegadas em progresso por gate e turno."""
    return get_arrivals_by_status(db, gate_id=gate_id, shift=shift, status="em_descarga", page=page, limit=limit)

# GET /api/v1/arrivals/{gate_id}/{shift}/in_progress/total - contador em progresso
@router.get("/arrivals/{gate_id}/{shift}/in_progress/total")
def count_arrivals_in_progress(gate_id: int, shift: int, db: Session = Depends(get_db)):
    """Retorna o total de chegadas em progresso para um gate e turno."""
    total = get_arrivals_count_by_status(db, gate_id=gate_id, shift=shift, status="em_descarga")
    return {"gate_id": gate_id, "shift": shift, "status": "in_progress", "total": total}

# GET /api/v1/arrivals/{gate_id}/finished - chegadas concluídas por gate
@router.get("/arrivals/{gate_id}/finished", response_model=List[ChegadaResponse])
def list_arrivals_finished(
    gate_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Lista chegadas com estado 'concluida' (finished) por gate."""
    return get_arrivals_by_status(db, gate_id=gate_id, status="concluida", page=page, limit=limit)

# GET /api/v1/arrivals/{gate_id}/{shift}/finished - chegadas concluídas por gate e turno
@router.get("/arrivals/{gate_id}/{shift}/finished", response_model=List[ChegadaResponse])
def list_arrivals_finished_shift(
    gate_id: int,
    shift: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Lista chegadas concluídas por gate e turno."""
    return get_arrivals_by_status(db, gate_id=gate_id, shift=shift, status="concluida", page=page, limit=limit)

# GET /api/v1/arrivals/{gate_id}/{shift}/finished/total - contador concluídas
@router.get("/arrivals/{gate_id}/{shift}/finished/total")
def count_arrivals_finished(gate_id: int, shift: int, db: Session = Depends(get_db)):
    """Retorna o total de chegadas concluídas para um gate e turno."""
    total = get_arrivals_count_by_status(db, gate_id=gate_id, shift=shift, status="concluida")
    return {"gate_id": gate_id, "shift": shift, "status": "finished", "total": total}

# PUT /api/v1/arrivals/{id} - atualizar chegada
@router.put("/arrivals/{id}", response_model=ChegadaResponse)
def update_arrival_endpoint(id: int, chegada: ChegadaCreate, db: Session = Depends(get_db)):
    """Atualiza os dados de uma chegada existente."""
    return update_arrival(db, id, chegada)

# Query para o decision engine obter as chegadas com matricula específica
@router.get("/arrivals/query?matricula={matricula}", response_model=List[ChegadaResponse])
def query_arrivals_by_matricula(
    matricula: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Consulta chegadas por matrícula (usado pelo Decision Engine)."""
    return get_arrivals_by_lpate(db, matricula=matricula, page=page, limit=limit)