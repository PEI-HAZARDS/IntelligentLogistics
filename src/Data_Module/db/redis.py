from config import settings
import redis

redis_client = redis.Redis(
    host=settings.redis_host,
    port=settings.redis_port,
    db=getattr(settings, "redis_db", 0),
    decode_responses=True,   # strings legíveis
    socket_timeout=5,
    socket_connect_timeout=5
)
