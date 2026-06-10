import logging
import redis
from typing import Optional

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Initialize a single, persistent Redis client with an internal connection pool.
# Instantiating this at the module level prevents the app from spawning a new
# TCP connection on every single function call.
settings = get_settings()
_redis_client = redis.from_url(settings.redis_url, decode_responses=True)


def get_redis() -> redis.Redis:
    """
    Returns the synchronous Redis client instance connected to REDIS_URL.
    Required by Celery workers and your synchronous/polling application flows.
    """
    return _redis_client


def redis_get(key: str) -> Optional[str]:
    """
    Safely fetch a value from Redis.
    Catches Redis errors and logs them to avoid breaking the request lifecycle.
    """
    try:
        return _redis_client.get(key)
    except redis.RedisError as e:
        logger.error(f"Redis GET exception for key '{key}': {e}")
        return None


def redis_set(key: str, value: str, expire_seconds: Optional[int] = None) -> bool:
    """
    Safely write a value to Redis with an optional TTL (expiration time).
    Catches Redis errors and returns a boolean status indicator.
    """
    try:
        _redis_client.set(key, value, ex=expire_seconds)
        return True
    except redis.RedisError as e:
        logger.error(f"Redis SET exception for key '{key}': {e}")
        return False


def redis_delete(key: str) -> bool:
    """
    Safely evict a key from Redis.
    Catches Redis errors and returns True if successful, False otherwise.
    """
    try:
        return bool(_redis_client.delete(key))
    except redis.RedisError as e:
        logger.error(f"Redis DELETE exception for key '{key}': {e}")
        return False