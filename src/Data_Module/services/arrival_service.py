from typing import List, Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.sql_models import ChegadaDiaria
from models.pydantic_models import ChegadaResponse, ChegadaCreate

def get_arrivals(db: Session, matricula: Optional[str] = None, page: int = 1, limit: int = 20) -> List[ChegadaResponse]:
    """
    Retorna lista paginada de chegadas. Se matricula for fornecida, filtra por ela.
    """
    offset = (page - 1) * limit
    query = db.query(ChegadaDiaria)
    if matricula:
        query = query.filter(ChegadaDiaria.matricula_pesado == matricula)
    items = query.order_by(ChegadaDiaria.data_prevista.desc()).offset(offset).limit(limit).all()
    return [ChegadaResponse.from_orm(i) for i in items]

def update_arrival(db: Session, id: int, chegada: ChegadaCreate) -> ChegadaResponse:
    """
    Atualiza a chegada com os campos fornecidos no ChegadaCreate.
    Só altera campos que não são None.
    """
    chegada_sql = db.query(ChegadaDiaria).filter(ChegadaDiaria.id_chegada == id).first()
    if not chegada_sql:
        raise HTTPException(status_code=404, detail="Chegada not found")
    for key, value in chegada.dict().items():
        # Apenas atualiza se o campo foi fornecido (não None)
        if value is not None:
            setattr(chegada_sql, key, value)
    db.commit()
    db.refresh(chegada_sql)
    return ChegadaResponse.from_orm(chegada_sql)
