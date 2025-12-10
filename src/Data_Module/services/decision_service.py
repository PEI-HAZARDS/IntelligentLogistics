"""
Decision Service - Processamento de decisões do Decision Engine.
Responsabilidades:
- Deduplicação via Redis (SET NX)
- Cache de decisões em Redis
- Persistência de eventos em MongoDB
- Atualização de chegadas em PostgreSQL (via arrival_service)
- Criação de alertas ADR (via alert_service)
"""

import json
import time
from typing import Optional, Dict, Any, List
from datetime import datetime as dt
from db.mongo import detections_collection, events_collection
from db.redis import redis_client


# ==================== CONFIGURAÇÃO ====================

DEDUP_TTL = 300             # 5 minutos para impedir reprocessamento imediato
BUCKET_SECONDS = 30         # janela de agrupamento
DECISION_CACHE_TTL = 3600   # cache da decisão por 1 hora


# ==================== REDIS KEY HELPERS ====================

def time_bucket(ts: float, bucket_seconds: int = BUCKET_SECONDS) -> int:
    """Agrupa timestamps em buckets para dedup."""
    return int(ts // bucket_seconds) * bucket_seconds


def dedup_key(matricula: Optional[str], gate_id: Optional[int], ts: float) -> Optional[str]:
    """Gera chave Redis para deduplicação."""
    if not matricula or gate_id is None:
        return None
    tb = time_bucket(ts)
    return f"plate:{matricula}:gate:{gate_id}:tb:{tb}"


def decision_cache_key(matricula: Optional[str], gate_id: Optional[int], ts: float) -> Optional[str]:
    """Gera chave Redis para cache de decisão."""
    k = dedup_key(matricula, gate_id, ts)
    if not k:
        return None
    return "decision:" + k


# ==================== DEDUPLICAÇÃO ====================

def is_duplicate_and_mark(matricula: Optional[str], gate_id: Optional[int], ts: float) -> bool:
    """
    Tenta marcar a deteção como processada usando SET NX EX.
    Retorna True se já existia (é duplicado), False se conseguiu marcar (não duplicado).
    """
    key = dedup_key(matricula, gate_id, ts)
    if not key:
        return False
    try:
        set_ok = redis_client.set(key, "1", nx=True, ex=DEDUP_TTL)
        return not set_ok  # True se já existia
    except Exception:
        # Degradação graciosa: assume não duplicado
        return False


# ==================== CACHE DE DECISÕES ====================

def get_cached_decision(matricula: Optional[str], gate_id: Optional[int], ts: float) -> Optional[dict]:
    """Obtém decisão em cache se existir."""
    key = decision_cache_key(matricula, gate_id, ts)
    if not key:
        return None
    try:
        v = redis_client.get(key)
        if v:
            return json.loads(v)
    except Exception:
        pass
    return None


def cache_decision(matricula: Optional[str], gate_id: Optional[int], ts: float, decision: dict):
    """Guarda decisão em cache Redis."""
    key = decision_cache_key(matricula, gate_id, ts)
    if not key:
        return
    try:
        redis_client.set(key, json.dumps(decision), ex=DECISION_CACHE_TTL)
    except Exception:
        pass


# ==================== PERSISTÊNCIA MONGODB ====================

def persist_detection_event(event_data: Dict[str, Any]) -> str:
    """
    Persiste evento de deteção no MongoDB (para estatísticas futuras).
    
    event_data esperado:
    {
        "type": "license_plate_detection" | "hazmat_detection" | "truck_detection",
        "matricula": "XX-XX-XX",
        "gate_id": 1,
        "timestamp": "2025-12-09T10:30:00",
        "confidence": 0.95,
        "agent": "AgentB",
        "raw_data": {...}
    }
    """
    doc = {
        **event_data,
        "created_at": dt.utcnow().isoformat(),
        "processed": False
    }
    result = detections_collection.insert_one(doc)
    return str(result.inserted_id)


def persist_decision_event(
    matricula: str,
    gate_id: int,
    id_chegada: Optional[int],
    decision: str,
    decision_data: Dict[str, Any]
) -> str:
    """
    Persiste evento de decisão no MongoDB (para auditoria e estatísticas).
    """
    doc = {
        "type": "decision",
        "matricula": matricula,
        "gate_id": gate_id,
        "id_chegada": id_chegada,
        "decision": decision,  # "approved", "rejected", "manual_review", "not_found"
        "decision_data": decision_data,
        "created_at": dt.utcnow().isoformat()
    }
    result = events_collection.insert_one(doc)
    return str(result.inserted_id)


def get_detection_events(
    matricula: Optional[str] = None,
    gate_id: Optional[int] = None,
    event_type: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """Consulta eventos de deteção no MongoDB."""
    query = {}
    if matricula:
        query["matricula"] = matricula
    if gate_id:
        query["gate_id"] = gate_id
    if event_type:
        query["type"] = event_type
    
    cursor = detections_collection.find(query).sort("created_at", -1).limit(limit)
    return list(cursor)


def get_decision_events(
    matricula: Optional[str] = None,
    gate_id: Optional[int] = None,
    decision: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """Consulta eventos de decisão no MongoDB."""
    query = {"type": "decision"}
    if matricula:
        query["matricula"] = matricula
    if gate_id:
        query["gate_id"] = gate_id
    if decision:
        query["decision"] = decision
    
    cursor = events_collection.find(query).sort("created_at", -1).limit(limit)
    return list(cursor)


# ==================== PROCESSAMENTO DE DECISÃO (ORQUESTRADOR) ====================

def process_incoming_decision(
    matricula: str,
    gate_id: int,
    id_chegada: int,
    decision: str,
    estado_entrega: str,
    alertas: Optional[List[Dict[str, Any]]] = None,
    observacoes: Optional[str] = None,
    extra_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Processa uma decisão vinda do Decision Engine.
    
    Fluxo:
    1. Verificar se é duplicado (Redis dedup)
    2. Verificar cache de decisão anterior
    3. Atualizar chegada no PostgreSQL (via arrival_service)
    4. Criar alertas se necessário (via alert_service)
    5. Persistir evento no MongoDB
    6. Cachear decisão no Redis
    
    Retorna dict com status do processamento.
    """
    from db.postgres import SessionLocal
    from services.arrival_service import update_arrival_from_decision
    
    ts = time.time()
    
    # 1. Verificar duplicado
    if is_duplicate_and_mark(matricula, gate_id, ts):
        return {
            "status": "skipped",
            "reason": "duplicate_detection",
            "matricula": matricula,
            "gate_id": gate_id
        }
    
    # 2. Verificar cache
    cached = get_cached_decision(matricula, gate_id, ts)
    if cached:
        return {
            "status": "cached",
            "decision": cached,
            "matricula": matricula,
            "gate_id": gate_id
        }
    
    # 3. Atualizar chegada no PostgreSQL
    db = SessionLocal()
    try:
        decision_payload = {
            "decision": decision,
            "estado_entrega": estado_entrega,
            "observacoes": observacoes,
            "alertas": alertas or []
        }
        
        chegada = update_arrival_from_decision(db, id_chegada, decision_payload)
        
        if not chegada:
            # Persistir evento de chegada não encontrada
            persist_decision_event(
                matricula=matricula,
                gate_id=gate_id,
                id_chegada=id_chegada,
                decision="not_found",
                decision_data={"error": "Chegada não encontrada"}
            )
            return {
                "status": "error",
                "reason": "chegada_not_found",
                "id_chegada": id_chegada
            }
        
        # 4. Persistir evento de decisão
        event_id = persist_decision_event(
            matricula=matricula,
            gate_id=gate_id,
            id_chegada=id_chegada,
            decision=decision,
            decision_data={
                "estado_entrega": estado_entrega,
                "alertas_criados": len(alertas) if alertas else 0,
                "observacoes": observacoes,
                **(extra_data or {})
            }
        )
        
        # 5. Cachear decisão
        result = {
            "status": "processed",
            "decision": decision,
            "id_chegada": id_chegada,
            "estado_entrega": estado_entrega,
            "event_id": event_id
        }
        cache_decision(matricula, gate_id, ts, result)
        
        return result
        
    finally:
        db.close()


def query_arrivals_for_decision(matricula: str, gate_id: int) -> Dict[str, Any]:
    """
    Consulta chegadas candidatas para o Decision Engine.
    Usado quando o Decision Engine precisa saber que chegadas existem
    para uma matrícula detectada.
    
    Retorna:
    {
        "found": True/False,
        "candidates": [...],
        "message": "..."
    }
    """
    from db.postgres import SessionLocal
    from services.arrival_service import get_arrivals_for_decision
    
    db = SessionLocal()
    try:
        candidates = get_arrivals_for_decision(db, matricula=matricula, id_gate=gate_id)
        
        return {
            "found": len(candidates) > 0,
            "candidates": candidates,
            "message": f"Encontradas {len(candidates)} chegada(s) candidata(s)" if candidates else "Nenhuma chegada encontrada"
        }
    finally:
        db.close()
