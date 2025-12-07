from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db.postgres import get_db
from models.sql_models import Alerta
from models.pydantic_models import AlertaResponse, AlertaBase

router = APIRouter()


@router.get("/alerts", response_model=List[AlertaResponse])
def list_alerts(severidade: Optional[int] = None, limit: int = 50, db: Session = Depends(get_db)):
    """
    Lista alertas (PostgreSQL). Filtros por severidade.
    """
    query = db.query(Alerta)
    if severidade is not None:
        query = query.filter(Alerta.severidade == severidade)
    query = query.order_by(Alerta.data_hora.desc()).limit(limit)
    results = query.all()
    return [AlertaResponse.from_orm(a) for a in results]


@router.get("/alerts/{alert_id}", response_model=AlertaResponse)
def get_alert(alert_id: int, db: Session = Depends(get_db)):
    alerta = db.query(Alerta).filter(Alerta.id_alerta == alert_id).first()
    if not alerta:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alerta não encontrado")
    return AlertaResponse.from_orm(alerta)


@router.post("/alerts", response_model=AlertaResponse, status_code=status.HTTP_201_CREATED)
def create_alert(payload: AlertaBase, db: Session = Depends(get_db)):
    """
    Cria um alerta no Postgres. Usado por serviços internos -> decision engine.
    """
    nova = Alerta(
        tipo=payload.tipo,
        severidade=payload.severidade,
        descricao=payload.descricao
    )
    db.add(nova)
    db.commit()
    db.refresh(nova)
    return AlertaResponse.from_orm(nova)
