"""Async Redis Client Foundation."""

import logging
from typing import Any

import redis.asyncio as aioredis
from redis.asyncio.client import Redis

from apps.api.src.core.config import get_settings

logger = logging.getLogger("societysphere.redis")

_redis_client: Redis | None = None


def get_redis_client() -> Redis | None:
    """Get the active singleton Redis client."""
    return _redis_client


async def init_redis() -> Redis | None:
    """Initialize Redis connection pool at application startup."""
    global _redis_client
    settings = get_settings()
    try:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            max_connections=settings.REDIS_POOL_SIZE,
            socket_timeout=settings.REDIS_TIMEOUT,
            socket_connect_timeout=settings.REDIS_TIMEOUT,
            decode_responses=True,
        )
        # Attempt initial ping
        await _redis_client.ping()
        logger.info("Redis connection established successfully.")
        return _redis_client
    except Exception as exc:
        logger.warning(f"Redis initialization warning (service may be offline in local development): {exc}")
        return _redis_client


async def close_redis() -> None:
    """Close Redis client connections at application shutdown."""
    global _redis_client
    if _redis_client is not None:
        logger.info("Closing Redis connection pool...")
        await _redis_client.close()
        _redis_client = None


async def check_redis_health() -> bool:
    """Execute a lightweight Redis PING health probe."""
    global _redis_client
    if _redis_client is None:
        # Attempt on-demand initialization if not yet created
        try:
            settings = get_settings()
            temp_client = aioredis.from_url(
                settings.REDIS_URL,
                socket_timeout=settings.REDIS_TIMEOUT,
                decode_responses=True,
            )
            is_ok = await temp_client.ping()
            await temp_client.close()
            return bool(is_ok)
        except Exception:
            return False
    try:
        return bool(await _redis_client.ping())
    except Exception as exc:
        logger.warning(f"Redis health probe failed: {exc}")
        return False


class CacheManager:
    """Clean caching abstraction wrapper."""

    def __init__(self, client: Redis | None = None) -> None:
        self.client = client or get_redis_client()

    async def get(self, key: str) -> str | None:
        if not self.client:
            return None
        try:
            return await self.client.get(key)
        except Exception as exc:
            logger.error(f"Redis GET error on key '{key}': {exc}")
            return None

    async def set(self, key: str, value: Any, expire_seconds: int | None = None) -> bool:
        if not self.client:
            return False
        try:
            await self.client.set(key, value, ex=expire_seconds)
            return True
        except Exception as exc:
            logger.error(f"Redis SET error on key '{key}': {exc}")
            return False

    async def delete(self, key: str) -> bool:
        if not self.client:
            return False
        try:
            await self.client.delete(key)
            return True
        except Exception as exc:
            logger.error(f"Redis DELETE error on key '{key}': {exc}")
            return False

    async def incr(self, key: str, expire_seconds: int | None = None) -> int:
        """Atomic increment with TTL initiation on first key creation."""
        if not self.client:
            return 0
        try:
            val = await self.client.incr(key)
            if val == 1 and expire_seconds is not None:
                await self.client.expire(key, expire_seconds)
            return int(val)
        except Exception as exc:
            logger.error(f"Redis INCR error on key '{key}': {exc}")
            return 0
