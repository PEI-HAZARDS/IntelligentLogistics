from typing import List, Optional, Dict, Any
from db.mongo import events_collection
from bson import ObjectId

def _serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Converte ObjectId para string e garante que o dicionário é JSON-serializável.
    """
    if not doc:
        return doc
    doc = dict(doc)
    _id = doc.get("_id")
    if _id is not None:
        try:
            doc["_id"] = str(_id)
        except Exception:
            doc["_id"] = _id
    return doc

def get_events(type: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Retorna uma lista de eventos da coleção 'events' em MongoDB.
    - type: filtra por campo 'type' (opcional)
    - limit: máximo de documentos a devolver (padrão 10)
    Ordena por timestamp descendente.
    """
    query = {}
    if type:
        query["type"] = type

    cursor = events_collection.find(query).sort("timestamp", -1).limit(max(1, int(limit)))
    return [_serialize(doc) for doc in cursor]

def get_event_by_id(event_id: str) -> Optional[Dict[str, Any]]:
    """
    Busca um evento por _id (string). Retorna None se não existir ou se id inválido.
    """
    try:
        oid = ObjectId(event_id)
    except Exception:
        return None

    doc = events_collection.find_one({"_id": oid})
    return _serialize(doc)
