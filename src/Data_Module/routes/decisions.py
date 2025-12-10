"""
Decisions Routes - Endpoints para processamento de decisões.
Consumido por: Decision Engine (microserviço), Frontend operador.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, HTTPException, status, Body, Query, Path
from bson.objectid import ObjectId
from pydantic import BaseModel

from db.mongo import events_collection
from services.decision_service import (
    process_incoming_decision,
    query_arrivals_for_decision,
    get_detection_events,
    get_decision_events,
    persist_detection_event
)

router = APIRouter(prefix="/decisions", tags=["Decisions"])


# ==================== PYDANTIC MODELS ====================

class DecisionIncomingRequest(BaseModel):
    """Request do Decision Engine para processar uma decisão."""
    matricula: str
    gate_id: int
    id_chegada: int
    decision: str  # "approved", "rejected", "manual_review"
    estado_entrega: str  # "unloading", "delayed", etc.
    observacoes: Optional[str] = None
    alertas: Optional[List[Dict[str, Any]]] = None
    extra_data: Optional[Dict[str, Any]] = None


class DetectionEventRequest(BaseModel):
    """Request para registar evento de deteção (Agent A/B/C)."""
    type: str  # "license_plate_detection", "hazmat_detection", "truck_detection"
    matricula: Optional[str] = None
    gate_id: int
    confidence: Optional[float] = None
    agent: str  # "AgentA", "AgentB", "AgentC"
    raw_data: Optional[Dict[str, Any]] = None


class QueryArrivalsRequest(BaseModel):
    """Request do Decision Engine para consultar chegadas."""
    matricula: str
    gate_id: int


class EventResponse(BaseModel):
    """Response genérico para eventos."""
    id: Optional[str] = None
    type: str
    timestamp: Optional[datetime] = None
    gate_id: Optional[int] = None
    matricula: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


# ==================== DECISION ENGINE ENDPOINTS ====================

@router.post("/process")
def process_decision(request: DecisionIncomingRequest):
    """
    Endpoint principal para o Decision Engine enviar decisões.
    
    Fluxo:
    1. Verifica duplicado (Redis)
    2. Atualiza chegada no PostgreSQL
    3. Cria alertas se necessário
    4. Persiste evento no MongoDB
    5. Cache resultado no Redis
    
    Payload esperado:
    {
        "matricula": "XX-XX-XX",
        "gate_id": 1,
        "id_chegada": 123,
        "decision": "approved",
        "estado_entrega": "unloading",
        "observacoes": "Aprovado automaticamente",
        "alertas": [{"tipo": "ADR", "severidade": 3, "descricao": "UN 1203"}]
    }
    """
    result = process_incoming_decision(
        matricula=request.matricula,
        gate_id=request.gate_id,
        id_chegada=request.id_chegada,
        decision=request.decision,
        estado_entrega=request.estado_entrega,
        alertas=request.alertas,
        observacoes=request.observacoes,
        extra_data=request.extra_data
    )
    
    return result


@router.post("/query-arrivals")
def query_arrivals(request: QueryArrivalsRequest):
    """
    Decision Engine consulta chegadas candidatas para uma matrícula.
    Usado após deteção de matrícula pelo Agent B.
    
    Retorna chegadas com estado 'in_transit' ou 'delayed' que 
    correspondem à matrícula e gate.
    """
    result = query_arrivals_for_decision(
        matricula=request.matricula,
        gate_id=request.gate_id
    )
    return result


@router.post("/detection-event")
def register_detection_event(request: DetectionEventRequest):
    """
    Registra evento de deteção dos Agents (A/B/C).
    Usado para persistência e estatísticas futuras.
    
    Payload esperado:
    {
        "type": "license_plate_detection",
        "matricula": "XX-XX-XX",
        "gate_id": 1,
        "confidence": 0.95,
        "agent": "AgentB",
        "raw_data": {...}
    }
    """
    event_data = {
        "type": request.type,
        "matricula": request.matricula,
        "gate_id": request.gate_id,
        "confidence": request.confidence,
        "agent": request.agent,
        "raw_data": request.raw_data,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    event_id = persist_detection_event(event_data)
    
    return {"status": "ok", "event_id": event_id}


# ==================== QUERY ENDPOINTS (MongoDB) ====================

@router.get("/events/detections", response_model=List[Dict[str, Any]])
def list_detection_events(
    matricula: Optional[str] = Query(None),
    gate_id: Optional[int] = Query(None),
    event_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500)
):
    """Lista eventos de deteção do MongoDB."""
    events = get_detection_events(
        matricula=matricula,
        gate_id=gate_id,
        event_type=event_type,
        limit=limit
    )
    # Converter ObjectId para string
    for e in events:
        if "_id" in e:
            e["_id"] = str(e["_id"])
    return events


@router.get("/events/decisions", response_model=List[Dict[str, Any]])
def list_decision_events(
    matricula: Optional[str] = Query(None),
    gate_id: Optional[int] = Query(None),
    decision: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500)
):
    """Lista eventos de decisão do MongoDB."""
    events = get_decision_events(
        matricula=matricula,
        gate_id=gate_id,
        decision=decision,
        limit=limit
    )
    # Converter ObjectId para string
    for e in events:
        if "_id" in e:
            e["_id"] = str(e["_id"])
    return events


@router.get("/events/{event_id}")
def get_event(event_id: str = Path(...)):
    """Obtém um evento específico pelo ID (MongoDB ObjectId)."""
    try:
        oid = ObjectId(event_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="event_id inválido")
    
    # Tentar em ambas as coleções
    doc = events_collection.find_one({"_id": oid})
    
    if not doc:
        from db.mongo import detections_collection
        doc = detections_collection.find_one({"_id": oid})
    
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evento não encontrado")
    
    doc["_id"] = str(doc["_id"])
    return doc


# ==================== MANUAL REVIEW (Operador) ====================

@router.post("/manual-review/{id_chegada}")
def manual_review(
    id_chegada: int = Path(..., description="ID da chegada"),
    decision: str = Query(..., description="Decisão: approved, rejected"),
    observacoes: Optional[str] = Query(None, description="Observações do operador")
):
    """
    Endpoint para revisão manual do operador.
    Usado quando o Decision Engine não consegue decidir automaticamente.
    """
    result = process_incoming_decision(
        matricula="MANUAL",  # Indicador de revisão manual
        gate_id=0,
        id_chegada=id_chegada,
        decision=decision,
        estado_entrega="unloading" if decision == "approved" else "delayed",
        observacoes=f"[REVISÃO MANUAL] {observacoes or ''}",
        extra_data={"manual_review": True}
    )
    
    return result

