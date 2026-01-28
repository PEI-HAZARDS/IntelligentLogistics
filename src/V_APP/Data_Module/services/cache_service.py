import json
from typing import Optional, Any, Callable
from db.redis import redis_client

def get_or_cache(key: str, ttl: int, fallback: Callable) -> Optional[Any]:
    """Read-through cache pattern."""
    cached = redis_client.get(key)
    if cached:
        try:
            return json.loads(cached)
        except:
            pass
    
    # Cache miss → buscar origem
    data = fallback()
    if data:
        redis_client.set(key, json.dumps(data), ex=ttl)
    return data

def cache_detection(detection_id: str, data: dict, ttl: int = 300):
    """Cache individual detection."""
    redis_client.set(f"detection:{detection_id}", json.dumps(data), ex=ttl)

def get_cached_detection(detection_id: str) -> Optional[dict]:
    """Get detection from cache."""
    v = redis_client.get(f"detection:{detection_id}")
    return json.loads(v) if v else None