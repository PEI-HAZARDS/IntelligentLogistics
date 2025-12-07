import json
import time
import httpx
from typing import Optional, Dict, Any
from datetime import datetime as dt
from config import settings
from db.mongo import detections_collection, events_collection
from db.postgres import SessionLocal
from models.sql_models import ChegadaDiaria
from models.pydantic_models import DetectionCreate

# Dedup / cache config
DEDUP_TTL = 300         # 5 minutos para impedir reprocessamento imediato
BUCKET_SECONDS = 30     # janela de agrupamento
DECISION_CACHE_TTL = 3600  # cache da decisão por 1 hora

# Redis client (importado de db.redis)
from db.redis import redis_client

def time_bucket(ts: float, bucket_seconds: int = BUCKET_SECONDS) -> int:
    return int(ts // bucket_seconds) * bucket_seconds

def dedup_key(matricula: Optional[str], gate_id: Optional[int], ts: float) -> Optional[str]:
    if not matricula or gate_id is None:
        return None
    tb = time_bucket(ts)
    return f"plate:{matricula}:gate:{gate_id}:tb:{tb}"

def decision_cache_key(matricula: Optional[str], gate_id: Optional[int], ts: float) -> Optional[str]:
    k = dedup_key(matricula, gate_id, ts)
    if not k:
        return None
    return "decision:" + k

def get_cached_decision(matricula: Optional[str], gate_id: Optional[int], ts: float) -> Optional[dict]:
    key = decision_cache_key(matricula, gate_id, ts)
    if not key:
        return None
    v = redis_client.get(key)
    if v:
        try:
            return json.loads(v)
        except Exception:
            return None
    return None

def cache_decision(matricula: Optional[str], gate_id: Optional[int], ts: float, decision: dict):
    key = decision_cache_key(matricula, gate_id, ts)
    if not key:
        return
    try:
        redis_client.set(key, json.dumps(decision), ex=DECISION_CACHE_TTL)
    except Exception:
        pass

def is_duplicate_and_mark(matricula: Optional[str], gate_id: Optional[int], ts: float) -> bool:
    """
    Tenta marcar a deteção como processada usando SET NX EX.
    Retorna True se já existia (é duplicado), False se conseguiu marcar (não duplicado).
    """
    key = dedup_key(matricula, gate_id, ts)
    if not key:
        return False
    # SET NX: only set if not exists. If set returns True -> we set and it's NOT duplicate.
    try:
        set_ok = redis_client.set(key, "1", nx=True, ex=DEDUP_TTL)
        if set_ok:
            return False
        else:
            return True
    except Exception:
        # Em caso de falha Redis, assume não duplicado para não perder eventos (degradação graciosa)
        return False

def call_decision_engine(detection: dict) -> dict:
    """
    Chama o Decision Engine via HTTP. Expectativa de resposta:
    {
      "decision": "granted" | "denied" | "pending",
      "matched_chegada_id": 123 | null,
      "estado_entrega": "em_descarga" | ...,
      "notify_channel": "notifications:driver:123"  # optional
    }
    """
    url = f"{settings.decision_engine_url.rstrip('/')}/process-detection"
    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.post(url, json=detection)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        # fallback: marca como pending e inclui erro
        return {"decision": "pending", "reason": str(e)}

def publish_notification(channel: Optional[str], payload: dict):
    try:
        ch = channel or "notifications:global"
        redis_client.publish(ch, json.dumps(payload))
    except Exception:
        # fallback: optionally POST to API Gateway notify URL if configured
        try:
            gw = getattr(settings, "api_gateway_notify_url", None)
            if gw:
                with httpx.Client(timeout=2.0) as client:
                    client.post(gw, json=payload)
        except Exception:
            pass

def _find_detection_doc(matricula: Optional[str], gate_id: Optional[int], tb: int):
    """Procura na coleção detections um doc que combine matricula/gate/time_bucket."""
    if not matricula or gate_id is None:
        return None
    try:
        query = {"matricula_detectada": matricula, "gate_id": gate_id, "time_bucket": tb}
        doc = detections_collection.find_one(query, sort=[("_id", -1)])
        if not doc:
            return None
        # Convert _id to str for JSON serializability
        try:
            doc["_id"] = str(doc["_id"])
        except Exception:
            pass
        return doc
    except Exception:
        return None

def _make_synthetic_detection(matricula: Optional[str], gate_id: Optional[int], ts_float: float, tb: int, decision: dict):
    """Cria um documento mínimo compatível com DetectionResponse (fallback)."""
    return {
        "_id": None,
        "timestamp": dt.utcfromtimestamp(ts_float),
        "gate_id": gate_id,
        "matricula_detectada": matricula,
        "confidence": float(decision.get("confidence", 0.0)) if isinstance(decision, dict) and "confidence" in decision else 0.0,
        "source": "cache",
        "image_path": None,
        "processed": True,
        "matched_chegada_id": decision.get("matched_chegada_id") if isinstance(decision, dict) else None,
        "alert_generated": False,
        "metadata": None,
        "time_bucket": tb,
        "decision": decision
    }

def process_detection(detection: dict) -> dict:
    """
    Fluxo:
     - calcula bucket + dedup
     - se existir cached decision -> retorna documento de deteção existente com 'decision' anexada
     - se duplicado -> retorna documento de deteção existente com indicador 'duplicate'
     - grava raw detection em MongoDB
     - chama Decision Engine (DE) para matching (DE faz a comparação com Postgres)
     - grava evento em MongoDB (events_collection)
     - se DE retornou matched_chegada_id -> atualiza tabela chegadas em Postgres
     - cacheia decisão e publica notificação
    """
    # normaliza timestamp
    ts = detection.get("timestamp")
    if isinstance(ts, (int, float)):
        ts_float = float(ts)
    else:
        # se é datetime vindo via pydantic, transforma para epoch
        try:
            ts_float = detection.get("timestamp").timestamp()
        except Exception:
            ts_float = time.time()

    matricula = detection.get("matricula_detectada")
    gate_id = detection.get("gate_id")

    tb = time_bucket(ts_float)

    # 1) Check cached decision (idempotency)
    cached = get_cached_decision(matricula, gate_id, ts_float)
    if cached:
        # tentar recuperar documento gravado em Mongo e anexar a decisão
        doc = _find_detection_doc(matricula, gate_id, tb)
        if doc:
            doc["decision"] = cached
            return doc
        # se não encontramos, devolve um synthetic doc com os campos mínimos
        return _make_synthetic_detection(matricula, gate_id, ts_float, tb, cached)

    # 2) Dedup: marca e detecta se outro processo já tratou
    if is_duplicate_and_mark(matricula, gate_id, ts_float):
        # se for duplicado, tenta devolver cached decision se existir e documento associado
        doc = _find_detection_doc(matricula, gate_id, tb)
        dup_decision = {"decision": "duplicate", "cached": cached}
        if doc:
            doc["decision"] = dup_decision
            return doc
        return _make_synthetic_detection(matricula, gate_id, ts_float, tb, dup_decision)

    # 3) Persist raw detection in MongoDB (include time_bucket for index)
    detection_doc = detection.copy()
    detection_doc["time_bucket"] = tb
    detection_doc["processed"] = False
    insert_res = detections_collection.insert_one(detection_doc)

    # Convert and attach _id for later return
    try:
        detection_doc["_id"] = str(insert_res.inserted_id)
    except Exception:
        detection_doc["_id"] = None

    # 4) Call Decision Engine (DE does matching)
    decision_result = call_decision_engine(detection_doc)

    # 5) Persist event in MongoDB
    event_doc = {
        "timestamp": decision_result.get("timestamp", ts_float),
        "type": "decision",
        "data": {
            "detection_id": str(insert_res.inserted_id),
            "detection": detection_doc,
            "decision": decision_result
        }
    }
    try:
        events_collection.insert_one(event_doc)
    except Exception:
        # não falhar o fluxo caso o insert de evento falhe
        pass

    # 6) If DE matched an arrival -> update Postgres
    matched_id = decision_result.get("matched_chegada_id")
    if matched_id:
        db = SessionLocal()
        try:
            chegada = db.query(ChegadaDiaria).filter(ChegadaDiaria.id_chegada == matched_id).first()
            if chegada:
                # DE indicates new state (e.g., estado_entrega)
                new_estado = decision_result.get("estado_entrega")
                if new_estado:
                    chegada.estado_entrega = new_estado
                db.commit()
                db.refresh(chegada)
        except Exception:
            # falha não crítica
            pass
        finally:
            db.close()

    # 7) Cache decision for idempotency
    cache_decision(matricula, gate_id, ts_float, decision_result)

    # 8) Publish notification (Redis pub/sub or API Gateway)
    payload = {
        "type": "arrival_decision",
        "decision": decision_result,
        "detection_id": str(insert_res.inserted_id),
        "event_id": None
    }
    publish_notification(decision_result.get("notify_channel"), payload)

    # Attach decision for convenience (the Pydantic model will ignore extras)
    detection_doc["decision"] = decision_result

    return detection_doc


def process_decision_manual(gate_id: int, decision: str, data: Dict[str, Any], manual: bool = False) -> Dict[str, Any]:
    """
    Processa uma decisão manual (operador) ou automática (decision engine).
    Grava evento no MongoDB e opcionalmente atualiza Postgres.
    
    Args:
        gate_id: ID do gate
        decision: 'granted', 'denied', 'approved', 'rejected', etc.
        data: payload adicional (truck_id, matricula, matched_chegada_id, observações, etc.)
        manual: True se é revisão manual do operador
    
    Returns:
        Dict com event_id e status
    """
    ts_float = time.time()
    
    # Criar evento no MongoDB
    event_doc = {
        "timestamp": dt.utcfromtimestamp(ts_float),
        "type": "manual_review" if manual else "decision",
        "gate_id": gate_id,
        "user_id": data.get("user_id"),
        "data": {
            "decision": decision,
            "truck_id": data.get("truck_id"),
            "matricula": data.get("matricula"),
            "matched_chegada_id": data.get("matched_chegada_id"),
            "observacoes": data.get("observacoes"),
            "reason": data.get("reason"),
            "manual": manual,
            "payload": data
        }
    }
    
    try:
        insert_res = events_collection.insert_one(event_doc)
        event_id = str(insert_res.inserted_id)
    except Exception as e:
        event_id = None
    
    # Se há matched_chegada_id e decisão é 'approved' ou 'granted', atualizar Postgres
    matched_id = data.get("matched_chegada_id")
    if matched_id and decision in ["approved", "granted"]:
        db = SessionLocal()
        try:
            chegada = db.query(ChegadaDiaria).filter(ChegadaDiaria.id_chegada == matched_id).first()
            if chegada:
                # Atualizar estado conforme decisão
                if decision == "approved" or decision == "granted":
                    chegada.estado_entrega = "em_descarga"
                # Adicionar observações se fornecidas
                obs = data.get("observacoes")
                if obs:
                    if chegada.observacoes:
                        chegada.observacoes += f" | {obs}"
                    else:
                        chegada.observacoes = obs
                db.commit()
        except Exception:
            pass
        finally:
            db.close()
    
    # Publicar notificação
    payload = {
        "type": "manual_review" if manual else "decision",
        "decision": decision,
        "gate_id": gate_id,
        "event_id": event_id,
        "data": data
    }
    publish_notification(data.get("notify_channel"), payload)
    
    return {"event_id": event_id, "status": "ok", "decision": decision}
