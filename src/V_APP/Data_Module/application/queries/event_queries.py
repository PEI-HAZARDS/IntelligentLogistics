"""
Event queries — reads directly from MongoDB events collection.
Moved from services/event_service.py.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from bson import ObjectId

from infrastructure.persistence.mongo import events_collection


def _serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
    if not doc:
        return doc
    doc = dict(doc)
    _id = doc.get("_id")
    if _id is not None:
        try:
            doc["_id"] = str(_id)
        except Exception:
            pass
    return doc


def get_events(type: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
    query: dict = {}
    if type:
        query["type"] = type
    cursor = events_collection.find(query).sort("timestamp", -1).limit(max(1, int(limit)))
    return [_serialize(doc) for doc in cursor]


def get_event_by_id(event_id: str) -> Optional[Dict[str, Any]]:
    try:
        oid = ObjectId(event_id)
    except Exception:
        return None
    doc = events_collection.find_one({"_id": oid})
    return _serialize(doc)
