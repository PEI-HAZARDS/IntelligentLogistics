"""
Redis caching layer for Intelligent Logistics.
Implements:
- Deduplication (legacy)
- Decision caching (legacy)
- Hot data caching (appointments, license plates)
- Real-time counters and metrics
- Rate limiting
- Operator session management
"""

import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, timedelta
from config import settings
import redis

logger = logging.getLogger("redis")

# Redis client initialization
redis_client = redis.Redis(
    host=settings.redis_host,
    port=settings.redis_port,
    db=getattr(settings, "redis_db", 0),
    decode_responses=True, # strings legible in Redis CLI
    socket_timeout=5,
    socket_connect_timeout=5
)

# ==================== TTL CONFIGURATION ====================

TTL_DEDUP = 300                    # 5 minutes - deduplication keys
TTL_DECISION_CACHE = 3600          # 1 hour - decision caching
TTL_APPOINTMENT_HOT = 1800         # 30 minutes - hot appointment data
TTL_LICENSE_PLATE_LOOKUP = 600     # 10 minutes - license plate → appointment mapping
TTL_COUNTER_REALTIME = 7200        # 2 hours - real-time counters
TTL_RATE_LIMIT = 60                # 1 minute - rate limiting window
TTL_OPERATOR_SESSION = 3600        # 1 hour - operator session state


# ==================== KEY PATTERNS ==================== (NameSpaces for Redis keys)

def dedup_key(license_plate: str, gate_id: int, time_bucket: int) -> str:
    """Deduplication key pattern."""
    return f"plate:{license_plate}:gate:{gate_id}:tb:{time_bucket}"


def decision_cache_key(license_plate: str, gate_id: int, time_bucket: int) -> str:
    """Decision cache key pattern."""
    return f"decision:plate:{license_plate}:gate:{gate_id}:tb:{time_bucket}"


def appointment_cache_key(appointment_id: int) -> str:
    """Hot appointment cache key pattern."""
    return f"appointment:{appointment_id}:details"


def license_plate_lookup_key(license_plate: str) -> str:
    """License plate to appointments mapping key pattern."""
    return f"lp_lookup:{license_plate}:appointments"


def counter_key(gate_id: int, metric: str, timestamp: datetime = None) -> str:
    """Real-time counter key pattern."""
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
    hour_str = timestamp.strftime("%Y%m%d%H")
    return f"counter:gate:{gate_id}:hour:{hour_str}:{metric}"


def rate_limit_key(endpoint: str, client_id: str) -> str:
    """Rate limiting key pattern."""
    return f"ratelimit:api:{endpoint}:{client_id}"


def operator_session_key(operator_id: str) -> str:
    """Operator session state key pattern."""
    return f"operator:{operator_id}:session"


# ==================== DEDUPLICATION ====================

def is_duplicate_event(event_id: str) -> bool:
    """
    Event-id based idempotency check using SET NX.
    Returns True if event_id was already seen (duplicate), False if new.
    Key: ``dedup:event:{event_id}``
    """
    key = f"dedup:event:{event_id}"
    try:
        set_ok = redis_client.set(key, "1", nx=True, ex=TTL_DEDUP)
        return not set_ok  # True if already existed
    except Exception as e:
        logger.error(f"Event dedup check failed for {event_id}: {e}")
        return False  # Assume not duplicate on error


def is_duplicate_and_mark(license_plate: str, gate_id: int, time_bucket: int) -> bool:
    """
    Legacy time-window dedup using SET NX.
    Returns True if already existed (duplicate), False if marked (not duplicate).

    .. deprecated:: Use ``is_duplicate_event`` with an explicit event_id instead.
    """
    key = dedup_key(license_plate, gate_id, time_bucket)
    try:
        set_ok = redis_client.set(key, "1", nx=True, ex=TTL_DEDUP)
        return not set_ok  # True if already existed
    except Exception as e:
        logger.error(f"Deduplication check failed: {e}")
        return False  # Assume not duplicate on error


# ==================== DECISION CACHE ====================

def get_cached_decision(license_plate: str, gate_id: int, time_bucket: int) -> Optional[dict]:
    """Get cached decision if exists."""
    key = decision_cache_key(license_plate, gate_id, time_bucket)
    try:
        value = redis_client.get(key)
        if value:
            return json.loads(value)
    except Exception as e:
        logger.error(f"Failed to get cached decision: {e}")
    return None


def cache_decision(license_plate: str, gate_id: int, time_bucket: int, decision: dict):
    """Store decision in cache."""
    key = decision_cache_key(license_plate, gate_id, time_bucket)
    try:
        redis_client.setex(key, TTL_DECISION_CACHE, json.dumps(decision))
    except Exception as e:
        logger.error(f"Failed to cache decision: {e}")


# ==================== HOT APPOINTMENT CACHE ====================

def cache_appointment(appointment_id: int, appointment_data: Dict[str, Any]):
    """
    Cache frequently accessed appointment data with related entities.
    
    Args:
        appointment_id: Appointment ID
        appointment_data: Dict containing appointment, driver, truck data
    """
    key = appointment_cache_key(appointment_id)
    try:
        redis_client.setex(key, TTL_APPOINTMENT_HOT, json.dumps(appointment_data))
        logger.debug(f"Cached appointment {appointment_id}")
    except Exception as e:
        logger.error(f"Failed to cache appointment {appointment_id}: {e}")


def get_cached_appointment(appointment_id: int) -> Optional[Dict[str, Any]]:
    """
    Get cached appointment data.
    
    Args:
        appointment_id: Appointment ID
        
    Returns:
        Appointment data dict or None
    """
    key = appointment_cache_key(appointment_id)
    try:
        value = redis_client.get(key)
        if value:
            logger.debug(f"Cache HIT for appointment {appointment_id}")
            return json.loads(value)
        logger.debug(f"Cache MISS for appointment {appointment_id}")
    except Exception as e:
        logger.error(f"Failed to get cached appointment: {e}")
    return None


def invalidate_appointment_cache(appointment_id: int):
    """
    Invalidate appointment cache when data changes.
    
    Args:
        appointment_id: Appointment ID
    """
    key = appointment_cache_key(appointment_id)
    try:
        redis_client.delete(key)
        logger.debug(f"Invalidated cache for appointment {appointment_id}")
    except Exception as e:
        logger.error(f"Failed to invalidate appointment cache: {e}")


# ==================== LICENSE PLATE LOOKUP CACHE ====================

def cache_license_plate_appointments(license_plate: str, appointment_ids: List[int]):
    """
    Cache mapping from license plate to appointment IDs.
    
    Args:
        license_plate: License plate string
        appointment_ids: List of appointment IDs
    """
    key = license_plate_lookup_key(license_plate)
    try:
        # Use Redis Set for O(1) membership checks
        redis_client.delete(key)  # Clear existing
        if appointment_ids:
            redis_client.sadd(key, *[str(aid) for aid in appointment_ids])
        redis_client.expire(key, TTL_LICENSE_PLATE_LOOKUP)
        logger.debug(f"Cached {len(appointment_ids)} appointments for LP {license_plate}")
    except Exception as e:
        logger.error(f"Failed to cache license plate lookup: {e}")


def get_cached_license_plate_appointments(license_plate: str) -> Optional[List[int]]:
    """
    Get appointment IDs for a license plate.
    
    Args:
        license_plate: License plate string
        
    Returns:
        List of appointment IDs or None
    """
    key = license_plate_lookup_key(license_plate)
    try:
        members = redis_client.smembers(key)
        if members:
            logger.debug(f"Cache HIT for LP {license_plate}")
            return [int(aid) for aid in members]
        logger.debug(f"Cache MISS for LP {license_plate}")
    except Exception as e:
        logger.error(f"Failed to get cached license plate appointments: {e}")
    return None


def invalidate_license_plate_cache(license_plate: str):
    """
    Invalidate license plate lookup cache.
    
    Args:
        license_plate: License plate string
    """
    key = license_plate_lookup_key(license_plate)
    try:
        redis_client.delete(key)
        logger.debug(f"Invalidated LP cache for {license_plate}")
    except Exception as e:
        logger.error(f"Failed to invalidate LP cache: {e}")


# ==================== REAL-TIME COUNTERS ====================

def increment_counter(gate_id: int, metric: str, amount: int = 1):
    """
    Increment a real-time counter.
    
    Args:
        gate_id: Gate identifier
        metric: Metric name (e.g., "detections", "decisions:accepted")
        amount: Amount to increment
    """
    key = counter_key(gate_id, metric)
    try:
        redis_client.incrby(key, amount)
        redis_client.expire(key, TTL_COUNTER_REALTIME)
    except Exception as e:
        logger.error(f"Failed to increment counter {key}: {e}")


def get_counter(gate_id: int, metric: str, timestamp: datetime = None) -> int:
    """
    Get current value of a counter.
    
    Args:
        gate_id: Gate identifier
        metric: Metric name
        timestamp: Specific hour to query (default: current hour)
        
    Returns:
        Counter value
    """
    key = counter_key(gate_id, metric, timestamp)
    try:
        value = redis_client.get(key)
        return int(value) if value else 0
    except Exception as e:
        logger.error(f"Failed to get counter {key}: {e}")
        return 0


def get_counter_range(gate_id: int, metric: str, hours_ago: int = 24) -> Dict[str, int]:
    """
    Get counter values for the last N hours.
    
    Args:
        gate_id: Gate identifier
        metric: Metric name
        hours_ago: Number of hours to look back
        
    Returns:
        Dict mapping hour string to counter value
    """
    result = {}
    now = datetime.now(timezone.utc)
    
    for i in range(hours_ago):
        timestamp = now - timedelta(hours=i)
        value = get_counter(gate_id, metric, timestamp)
        hour_str = timestamp.strftime("%Y-%m-%d %H:00")
        result[hour_str] = value
    
    return result


# ==================== RATE LIMITING ====================

def check_rate_limit(endpoint: str, client_id: str, limit: int = 60) -> bool:
    """
    Check if request is within rate limit.
    
    Args:
        endpoint: API endpoint name
        client_id: Client identifier
        limit: Maximum requests per minute
        
    Returns:
        True if allowed, False if rate limited
    """
    key = rate_limit_key(endpoint, client_id)
    try:
        current = redis_client.get(key)
        if current is None:
            # First request in window
            redis_client.setex(key, TTL_RATE_LIMIT, "1")
            return True
        
        current_count = int(current)
        if current_count >= limit:
            logger.warning(f"Rate limit exceeded for {endpoint} by {client_id}")
            return False
        
        redis_client.incr(key)
        return True
    except Exception as e:
        logger.error(f"Rate limit check failed: {e}")
        return True  # Allow on error


def get_rate_limit_remaining(endpoint: str, client_id: str, limit: int = 60) -> int:
    """
    Get remaining requests in current window.
    
    Args:
        endpoint: API endpoint name
        client_id: Client identifier
        limit: Maximum requests per minute
        
    Returns:
        Number of remaining requests
    """
    key = rate_limit_key(endpoint, client_id)
    try:
        current = redis_client.get(key)
        if current is None:
            return limit
        return max(0, limit - int(current))
    except Exception as e:
        logger.error(f"Failed to get rate limit remaining: {e}")
        return limit


# ==================== OPERATOR SESSION ====================

def set_operator_session(operator_id: str, session_data: Dict[str, Any]):
    """
    Set operator session state.
    
    Args:
        operator_id: Operator identifier
        session_data: Session data (current_truck_id, etc.)
    """
    key = operator_session_key(operator_id)
    try:
        redis_client.setex(key, TTL_OPERATOR_SESSION, json.dumps(session_data))
        logger.debug(f"Set session for operator {operator_id}")
    except Exception as e:
        logger.error(f"Failed to set operator session: {e}")


def get_operator_session(operator_id: str) -> Optional[Dict[str, Any]]:
    """
    Get operator session state.
    
    Args:
        operator_id: Operator identifier
        
    Returns:
        Session data or None
    """
    key = operator_session_key(operator_id)
    try:
        value = redis_client.get(key)
        if value:
            return json.loads(value)
    except Exception as e:
        logger.error(f"Failed to get operator session: {e}")
    return None


def clear_operator_session(operator_id: str):
    """
    Clear operator session state.
    
    Args:
        operator_id: Operator identifier
    """
    key = operator_session_key(operator_id)
    try:
        redis_client.delete(key)
        logger.debug(f"Cleared session for operator {operator_id}")
    except Exception as e:
        logger.error(f"Failed to clear operator session: {e}")


# ==================== CACHE STATISTICS ====================

def get_cache_statistics() -> Dict[str, Any]:
    """
    Get Redis cache statistics.
    
    Returns:
        Dict with cache metrics
    """
    try:
        info = redis_client.info("stats")
        memory = redis_client.info("memory")
        
        return {
            "total_commands_processed": info.get("total_commands_processed", 0),
            "keyspace_hits": info.get("keyspace_hits", 0),
            "keyspace_misses": info.get("keyspace_misses", 0),
            "hit_rate": _calculate_hit_rate(
                info.get("keyspace_hits", 0),
                info.get("keyspace_misses", 0)
            ),
            "used_memory_mb": memory.get("used_memory", 0) / 1024 / 1024,
            "used_memory_peak_mb": memory.get("used_memory_peak", 0) / 1024 / 1024,
            "connected_clients": redis_client.info("clients").get("connected_clients", 0)
        }
    except Exception as e:
        logger.error(f"Failed to get cache statistics: {e}")
        return {}


def _calculate_hit_rate(hits: int, misses: int) -> float:
    """Calculate cache hit rate."""
    total = hits + misses
    if total == 0:
        return 0.0
    return round(hits / total, 4)


# ==================== BULK OPERATIONS ====================

def invalidate_all_appointment_caches():
    """
    Invalidate all appointment caches (use after bulk updates).
    """
    try:
        pattern = "appointment:*:details"
        cursor = 0
        count = 0
        
        while True:
            cursor, keys = redis_client.scan(cursor, match=pattern, count=100)
            if keys:
                redis_client.delete(*keys)
                count += len(keys)
            if cursor == 0:
                break
        
        logger.info(f"Invalidated {count} appointment caches")
    except Exception as e:
        logger.error(f"Failed to invalidate all appointment caches: {e}")


def get_all_active_counters(gate_id: int) -> Dict[str, int]:
    """
    Get all active counters for a gate (current hour).
    
    Args:
        gate_id: Gate identifier
        
    Returns:
        Dict mapping metric name to value
    """
    try:
        pattern = counter_key(gate_id, "*")
        cursor = 0
        counters = {}
        
        while True:
            cursor, keys = redis_client.scan(cursor, match=pattern, count=100)
            for key in keys:
                value = redis_client.get(key)
                if value:
                    # Extract metric name from key
                    metric = key.split(":")[-1]
                    counters[metric] = int(value)
            if cursor == 0:
                break
        
        return counters
    except Exception as e:
        logger.error(f"Failed to get active counters: {e}")
        return {}


# ==================== HEALTH CHECK ====================

def redis_health_check() -> bool:
    """
    Check if Redis is available.
    
    Returns:
        True if Redis is healthy
    """
    try:
        return redis_client.ping()
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return False
