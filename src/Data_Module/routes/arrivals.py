"""
Arrivals Routes - Endpoints para gestão de chegadas diárias.
Consumido por: Frontend operador, Decision Engine, App motorista.
"""

from typing import List, Optional, Dict, Any
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session

from models.pydantic_models import (
    Chegada, ArrivalStatusUpdate, ArrivalDecisionUpdate
)
from services.arrival_service import (
    get_all_arrivals,
    get_arrival_by_id,
    get_arrival_by_pin,
    get_arrivals_by_matricula,
    get_arrivals_for_decision,
    get_arrivals_count_by_status,
    update_arrival_status,
    update_arrival_from_decision,
    get_next_arrivals
)
from db.postgres import get_db

router = APIRouter(prefix="/arrivals", tags=["Arrivals"])


# ==================== GET ENDPOINTS ====================

@router.get("", response_model=List[Chegada])
def list_arrivals(
    skip: int = Query(0, ge=0, description="Número de registos a saltar"),
    limit: int = Query(100, ge=1, le=500, description="Máximo de registos"),
    id_gate: Optional[int] = Query(None, description="Filtrar por gate de entrada"),
    id_turno: Optional[int] = Query(None, description="Filtrar por turno"),
    estado_entrega: Optional[str] = Query(None, description="Filtrar por estado"),
    data_prevista: Optional[date] = Query(None, description="Filtrar por data prevista"),
    db: Session = Depends(get_db)
):
    """
    Lista chegadas com filtros opcionais.
    Usado pelo frontend do operador para listar chegadas do dia/turno.
    """
    chegadas = get_all_arrivals(
        db, skip=skip, limit=limit,
        id_gate=id_gate, id_turno=id_turno,
        estado_entrega=estado_entrega, data_prevista=data_prevista
    )
    return [Chegada.model_validate(c) for c in chegadas]


@router.get("/stats", response_model=Dict[str, int])
def get_arrivals_stats(
    id_gate: Optional[int] = Query(None, description="Filtrar por gate"),
    data: Optional[date] = Query(None, description="Data a consultar (default: hoje)"),
    db: Session = Depends(get_db)
):
    """
    Estatísticas de chegadas por estado.
    Usado no dashboard do operador.
    """
    return get_arrivals_count_by_status(db, id_gate=id_gate, data=data)


@router.get("/next/{id_gate}", response_model=List[Chegada])
def get_upcoming_arrivals(
    id_gate: int = Path(..., description="ID do gate"),
    limit: int = Query(5, ge=1, le=20, description="Número de chegadas"),
    db: Session = Depends(get_db)
):
    """
    Próximas chegadas previstas para um gate.
    Usado no painel lateral do operador.
    """
    chegadas = get_next_arrivals(db, id_gate=id_gate, limit=limit)
    return [Chegada.model_validate(c) for c in chegadas]


@router.get("/{id_chegada}", response_model=Chegada)
def get_arrival(
    id_chegada: int = Path(..., description="ID da chegada"),
    db: Session = Depends(get_db)
):
    """Obtém detalhes de uma chegada específica."""
    chegada = get_arrival_by_id(db, id_chegada)
    if not chegada:
        raise HTTPException(status_code=404, detail="Chegada não encontrada")
    return Chegada.model_validate(chegada)


@router.get("/pin/{pin_acesso}", response_model=Chegada)
def get_arrival_by_pin_code(
    pin_acesso: str = Path(..., description="PIN de acesso"),
    db: Session = Depends(get_db)
):
    """
    Obtém chegada pelo PIN de acesso.
    Usado pelo motorista para consultar sua chegada.
    """
    chegada = get_arrival_by_pin(db, pin_acesso)
    if not chegada:
        raise HTTPException(status_code=404, detail="PIN inválido ou chegada não encontrada")
    return Chegada.model_validate(chegada)


# ==================== DECISION ENGINE ENDPOINTS ====================

@router.get("/query/matricula/{matricula}", response_model=List[Chegada])
def query_arrivals_by_matricula(
    matricula: str = Path(..., description="Matrícula do veículo"),
    id_turno: Optional[int] = Query(None, description="Filtrar por turno"),
    estado_entrega: Optional[str] = Query(None, description="Filtrar por estado"),
    data_prevista: Optional[date] = Query(None, description="Data (default: hoje)"),
    db: Session = Depends(get_db)
):
    """
    Consulta chegadas por matrícula.
    Usado pelo Decision Engine para encontrar chegadas candidatas.
    """
    chegadas = get_arrivals_by_matricula(
        db, matricula=matricula,
        id_turno=id_turno, estado_entrega=estado_entrega,
        data_prevista=data_prevista
    )
    return [Chegada.model_validate(c) for c in chegadas]


@router.get("/decision/candidates/{id_gate}/{matricula}")
def get_decision_candidates(
    id_gate: int = Path(..., description="ID do gate"),
    matricula: str = Path(..., description="Matrícula detectada"),
    db: Session = Depends(get_db)
) -> List[Dict[str, Any]]:
    """
    Obtém chegadas candidatas para decisão.
    Retorna dados enriquecidos (carga, cais, ADR status).
    
    Usado pelo Decision Engine após detecção de matrícula.
    """
    return get_arrivals_for_decision(db, matricula=matricula, id_gate=id_gate)


# ==================== UPDATE ENDPOINTS ====================

@router.patch("/{id_chegada}/status", response_model=Chegada)
def update_status(
    id_chegada: int = Path(..., description="ID da chegada"),
    update_data: ArrivalStatusUpdate = ...,
    db: Session = Depends(get_db)
):
    """
    Atualiza estado de uma chegada.
    Usado pelo operador ou sistema para atualizar manualmente.
    """
    chegada = update_arrival_status(
        db, id_chegada=id_chegada,
        novo_estado=update_data.estado_entrega,
        data_hora_chegada=update_data.data_hora_chegada,
        id_gate_saida=update_data.id_gate_saida,
        observacoes=update_data.observacoes
    )
    if not chegada:
        raise HTTPException(status_code=404, detail="Chegada não encontrada")
    return Chegada.model_validate(chegada)


@router.post("/{id_chegada}/decision", response_model=Chegada)
def process_decision(
    id_chegada: int = Path(..., description="ID da chegada"),
    decision: ArrivalDecisionUpdate = ...,
    db: Session = Depends(get_db)
):
    """
    Processa decisão do Decision Engine.
    Atualiza estado e cria alertas se necessário.
    
    Payload esperado:
    {
        "decision": "approved",
        "estado_entrega": "unloading",
        "observacoes": "Aprovado automaticamente",
        "alertas": [
            {"tipo": "ADR", "severidade": 3, "descricao": "UN 1203 - Gasolina"}
        ]
    }
    """
    chegada = update_arrival_from_decision(
        db, id_chegada=id_chegada,
        decision_payload=decision.model_dump()
    )
    if not chegada:
        raise HTTPException(status_code=404, detail="Chegada não encontrada")
    return Chegada.model_validate(chegada)