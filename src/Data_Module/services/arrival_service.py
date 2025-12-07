from typing import List, Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from models.sql_models import ChegadaDiaria
from models.pydantic_models import ChegadaResponse, ChegadaCreate

def get_all_arrivals(
    db: Session,
    matricula: Optional[str] = None,
    page: int = 1,
    limit: int = 20
) -> List[ChegadaResponse]:
    """
    Retorna lista paginada de todas as chegadas.
    Se matricula for fornecida, filtra por ela.
    """
    offset = (page - 1) * limit
    query = db.query(ChegadaDiaria)
    if matricula:
        query = query.filter(ChegadaDiaria.matricula_pesado == matricula)
    items = query.order_by(ChegadaDiaria.data_prevista.desc()).offset(offset).limit(limit).all()
    return [ChegadaResponse.model_validate(i) for i in items]

def get_arrivals_by_gate(
    db: Session,
    gate_id: int,
    page: int = 1,
    limit: int = 20
) -> List[ChegadaResponse]:
    """
    Retorna lista paginada de chegadas filtradas por gate de entrada.
    """
    offset = (page - 1) * limit
    items = (
        db.query(ChegadaDiaria)
        .filter(ChegadaDiaria.id_gate_entrada == gate_id)
        .order_by(ChegadaDiaria.data_prevista.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [ChegadaResponse.model_validate(i) for i in items]

def get_arrivals_by_gate_and_shift(
    db: Session,
    gate_id: int,
    shift: int,
    page: int = 1,
    limit: int = 20
) -> List[ChegadaResponse]:
    """
    Retorna lista paginada de chegadas filtradas por gate e turno (shift).
    """
    offset = (page - 1) * limit
    items = (
        db.query(ChegadaDiaria)
        .filter(
            ChegadaDiaria.id_gate_entrada == gate_id,
            ChegadaDiaria.id_turno == shift
        )
        .order_by(ChegadaDiaria.data_prevista.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [ChegadaResponse.model_validate(i) for i in items]

def get_arrivals_count(
    db: Session,
    gate_id: Optional[int] = None,
    shift: Optional[int] = None
) -> int:
    """
    Retorna o total de chegadas (count) com filtros opcionais por gate_id e shift.
    """
    query = db.query(func.count(ChegadaDiaria.id_chegada))
    if gate_id is not None:
        query = query.filter(ChegadaDiaria.id_gate_entrada == gate_id)
    if shift is not None:
        query = query.filter(ChegadaDiaria.id_turno == shift)
    return query.scalar()

def get_arrivals_by_status(
    db: Session,
    gate_id: int,
    status: str,
    shift: Optional[int] = None,
    page: int = 1,
    limit: int = 20
) -> List[ChegadaResponse]:
    """
    Retorna lista paginada de chegadas filtradas por gate, estado e opcionalmente shift.
    status pode ser: 'em_transito', 'em_descarga', 'concluida', 'atrasada'
    """
    offset = (page - 1) * limit
    query = db.query(ChegadaDiaria).filter(
        ChegadaDiaria.id_gate_entrada == gate_id,
        ChegadaDiaria.estado_entrega == status
    )
    if shift is not None:
        query = query.filter(ChegadaDiaria.id_turno == shift)
    items = query.order_by(ChegadaDiaria.data_prevista.desc()).offset(offset).limit(limit).all()
    return [ChegadaResponse.model_validate(i) for i in items]

def get_arrivals_count_by_status(
    db: Session,
    gate_id: int,
    status: str,
    shift: Optional[int] = None
) -> int:
    """
    Retorna o total de chegadas (count) filtradas por gate, estado e opcionalmente shift.
    """
    query = db.query(func.count(ChegadaDiaria.id_chegada)).filter(
        ChegadaDiaria.id_gate_entrada == gate_id,
        ChegadaDiaria.estado_entrega == status
    )
    if shift is not None:
        query = query.filter(ChegadaDiaria.id_turno == shift)
    return query.scalar()

def update_arrival(db: Session, id: int, chegada: ChegadaCreate) -> ChegadaResponse:
    """
    Atualiza a chegada com os campos fornecidos no ChegadaCreate.
    Só altera campos que não são None.
    """
    chegada_sql = db.query(ChegadaDiaria).filter(ChegadaDiaria.id_chegada == id).first()
    if not chegada_sql:
        raise HTTPException(status_code=404, detail="Chegada not found")
    for key, value in chegada.model_dump(exclude_unset=True).items():
        setattr(chegada_sql, key, value)
    db.commit()
    db.refresh(chegada_sql)
    return ChegadaResponse.model_validate(chegada_sql)

def get_arrivals_by_lpate(
    db: Session,
    matricula: str,
    page: int = 1,
    limit: int = 20
) -> List[ChegadaResponse]:
    """
    Retorna lista paginada de chegadas filtradas por matrícula do pesado.
    """
    offset = (page - 1) * limit
    items = (
        db.query(ChegadaDiaria)
        .filter(ChegadaDiaria.matricula_pesado == matricula)
        .order_by(ChegadaDiaria.data_prevista.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [ChegadaResponse.model_validate(i) for i in items]