from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, status, Body
from bson.objectid import ObjectId
from db.mongo import events_collection
from models.pydantic_models import EventResponse
from services.decision_service import process_decision_manual

router = APIRouter()


def _doc_to_event_response(doc: dict) -> EventResponse:
    """
    Converte um documento MongoDB (event) num dict compatível com EventResponse.
    Faz pequenos normalizações (timestamp, remove _id).
    """
    # Normalize timestamp (Mongo may store datetime or epoch)
    ts = doc.get("timestamp")
    if isinstance(ts, (int, float)):
        from datetime import datetime
        try:
            ts_val = datetime.fromtimestamp(float(ts))
        except Exception:
            ts_val = None
    else:
        ts_val = ts

    resp = {
        "timestamp": ts_val,
        "type": doc.get("type"),
        "gate_id": doc.get("gate_id"),
        "user_id": doc.get("user_id"),
        "data": doc.get("data")
    }
    return EventResponse(**resp)


@router.get("/decisions", response_model=List[EventResponse])
def list_decisions(limit: int = 50, decision_type: Optional[str] = None):
    """
    Lista eventos de decisão a partir da coleção `events` no MongoDB.
    Filtra por `type` se fornecido (p.ex. 'decision' ou 'arrival_decision').
    """
    query = {}
    if decision_type:
        query["type"] = decision_type
    else:
        # por defeito, consideramos eventos onde o tipo contenha 'decision' ou explicitamente 'decision'
        # para simplicidade deixamos vazio (filtrar no cliente se necessário) ou podes filtrar por 'decision'
        query = {"type": {"$regex": "decision", "$options": "i"}}

    cursor = events_collection.find(query).sort("timestamp", -1).limit(limit)
    results = []
    for doc in cursor:
        try:
            results.append(_doc_to_event_response(doc))
        except Exception:
            # Skip malformed docs
            continue
    return results


@router.get("/decisions/{event_id}", response_model=EventResponse)
def get_decision(event_id: str):
    """
    Obtém um evento de decisão pelo _id (MongoDB ObjectId).
    """
    try:
        oid = ObjectId(event_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="event_id inválido")

    doc = events_collection.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evento não encontrado")
    return _doc_to_event_response(doc)


@router.post("/decision/{gate_id}/{decision}")
def post_decision(gate_id: int, decision: str, payload: Dict[str, Any] = Body({})):
    """
    Endpoint interno para o Decision Engine enviar decisões.
    - gate_id: identificador do gate
    - decision: 'granted', 'denied', 'pending', etc.
    - payload: dados adicionais (truck_id, matricula, matched_chegada_id, etc.)
    """
    result = process_decision_manual(gate_id=gate_id, decision=decision, data=payload)
    return {"status": "ok", "event_id": result.get("event_id"), "decision": decision}


@router.put("/manual_review/{gate_id}/{truck_id}/{decision}")
def manual_review(gate_id: int, truck_id: str, decision: str, payload: Dict[str, Any] = Body({})):
    """
    Endpoint para revisão manual do operador.
    - gate_id: identificador do gate
    - truck_id: identificador do camião (correlationId ou truckId)
    - decision: 'approved', 'rejected', 'pending_review'
    - payload: observações, motivo, etc.
    """
    payload["truck_id"] = truck_id
    result = process_decision_manual(
        gate_id=gate_id,
        decision=decision,
        data=payload,
        manual=True
    )
    return {"status": "ok", "event_id": result.get("event_id"), "decision": decision}
