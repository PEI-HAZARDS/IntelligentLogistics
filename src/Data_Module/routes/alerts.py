"""
Alerts Routes - Endpoints para gestão de alertas.
Consumido por: Frontend operador, Decision Engine.
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from sqlalchemy.orm import Session
from pydantic import BaseModel

from db.postgres import get_db
from models.pydantic_models import Alerta as AlertaPydantic, AlertaCreate
from services.alert_service import (
    get_alerts,
    get_alert_by_id,
    get_alerts_by_historico,
    get_active_alerts,
    get_alerts_count_by_type,
    create_alert,
    create_adr_alert,
    ADR_CODES,
    KEMLER_CODES
)

router = APIRouter(prefix="/alerts", tags=["Alerts"])


# ==================== PYDANTIC MODELS ====================

class CreateAlertRequest(BaseModel):
    """Request para criar alerta manualmente."""
    id_historico_ocorrencia: int
    id_carga: int
    tipo: str
    severidade: int  # 1-5
    descricao: str


class CreateADRAlertRequest(BaseModel):
    """Request para criar alerta ADR específico."""
    id_chegada: int
    un_code: Optional[str] = None
    kemler_code: Optional[str] = None
    detected_hazmat: Optional[str] = None


# ==================== QUERY ENDPOINTS ====================

@router.get("", response_model=List[AlertaPydantic])
def list_alerts(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    tipo: Optional[str] = Query(None, description="Filtrar por tipo (ADR, delay, etc.)"),
    severidade_min: Optional[int] = Query(None, ge=1, le=5, description="Severidade mínima"),
    id_carga: Optional[int] = Query(None, description="Filtrar por carga"),
    db: Session = Depends(get_db)
):
    """Lista alertas com filtros opcionais."""
    alerts = get_alerts(
        db, skip=skip, limit=limit,
        tipo=tipo, severidade_min=severidade_min, id_carga=id_carga
    )
    return [AlertaPydantic.model_validate(a) for a in alerts]


@router.get("/active", response_model=List[AlertaPydantic])
def list_active_alerts(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """
    Lista alertas ativos (últimas 24h) ordenados por severidade.
    Usado no dashboard do operador.
    """
    alerts = get_active_alerts(db, limit=limit)
    return [AlertaPydantic.model_validate(a) for a in alerts]


@router.get("/stats", response_model=Dict[str, int])
def get_alerts_stats(db: Session = Depends(get_db)):
    """Estatísticas de alertas por tipo (últimas 24h)."""
    return get_alerts_count_by_type(db)


@router.get("/historico/{id_historico}", response_model=List[AlertaPydantic])
def get_alerts_for_historico(
    id_historico: int = Path(..., description="ID do histórico de ocorrência"),
    db: Session = Depends(get_db)
):
    """Lista alertas de um histórico de ocorrência específico."""
    alerts = get_alerts_by_historico(db, id_historico)
    return [AlertaPydantic.model_validate(a) for a in alerts]


@router.get("/{id_alerta}", response_model=AlertaPydantic)
def get_single_alert(
    id_alerta: int = Path(..., description="ID do alerta"),
    db: Session = Depends(get_db)
):
    """Obtém detalhes de um alerta específico."""
    alert = get_alert_by_id(db, id_alerta)
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alerta não encontrado")
    return AlertaPydantic.model_validate(alert)


# ==================== REFERENCE DATA ====================

@router.get("/reference/adr-codes")
def get_adr_codes():
    """
    Lista códigos ADR/UN disponíveis.
    Usado para referência pelo Decision Engine e frontend.
    """
    return ADR_CODES


@router.get("/reference/kemler-codes")
def get_kemler_codes():
    """
    Lista códigos Kemler disponíveis.
    Usado para referência pelo Decision Engine e frontend.
    """
    return KEMLER_CODES


# ==================== CREATE ENDPOINTS ====================

@router.post("", response_model=AlertaPydantic, status_code=status.HTTP_201_CREATED)
def create_manual_alert(
    request: CreateAlertRequest,
    db: Session = Depends(get_db)
):
    """
    Cria um alerta manualmente.
    Usado pelo operador ou Decision Engine.
    """
    alert = create_alert(
        db,
        id_historico_ocorrencia=request.id_historico_ocorrencia,
        id_carga=request.id_carga,
        tipo=request.tipo,
        severidade=request.severidade,
        descricao=request.descricao
    )
    return AlertaPydantic.model_validate(alert)


@router.post("/adr", response_model=AlertaPydantic, status_code=status.HTTP_201_CREATED)
def create_adr_hazmat_alert(
    request: CreateADRAlertRequest,
    db: Session = Depends(get_db)
):
    """
    Cria alerta ADR/hazmat específico.
    Usado pelo Decision Engine quando detecta carga perigosa.
    
    Parâmetros:
    - id_chegada: ID da chegada associada
    - un_code: Código UN (ex: "1203" para gasolina)
    - kemler_code: Código Kemler (ex: "33" para inflamável)
    - detected_hazmat: Descrição da detecção (do Agent C)
    """
    from models.sql_models import ChegadaDiaria
    
    chegada = db.query(ChegadaDiaria).filter(
        ChegadaDiaria.id_chegada == request.id_chegada
    ).first()
    
    if not chegada:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chegada não encontrada"
        )
    
    alert = create_adr_alert(
        db,
        chegada=chegada,
        un_code=request.un_code,
        kemler_code=request.kemler_code,
        detected_hazmat=request.detected_hazmat
    )
    
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao criar alerta ADR"
        )
    
    return AlertaPydantic.model_validate(alert)

