"""
Cache helpers — relocated from services/cache_service.py.
"""

import json
import logging
from typing import Optional, Any, Callable
from infrastructure.persistence.redis import redis_client

logger = logging.getLogger(__name__)


def get_or_cache(key: str, ttl: int, fallback: Callable) -> Optional[Any]:
    """Read-through cache pattern."""
    cached = redis_client.get(key)
    if cached:
        try:
            return json.loads(cached)
        except json.JSONDecodeError:
            logger.error("Corrupt cache entry for key %r — evicting and using fallback", key)
            redis_client.delete(key)
    data = fallback()
    if data:
        redis_client.set(key, json.dumps(data), ex=ttl)
    return data


