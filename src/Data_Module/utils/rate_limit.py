# utils/rate_limit.py
from db.redis import redis_client

def rate_limit(key: str, max_requests: int, window_seconds: int) -> bool:
    """Rate limiting usando Redis."""
    current = redis_client.incr(key)
    if current == 1:
        redis_client.expire(key, window_seconds)
    return current <= max_requests

# Uso:
""" if not rate_limit(f"gate:{gate_id}:detections", 10, 60):
    raise HTTPException(429, "Too many detections") """