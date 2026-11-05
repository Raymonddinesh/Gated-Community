"""Rate Limiting and Abuse Protection Service for Authentication Endpoints."""

import asyncio
import time
from collections import defaultdict

from apps.api.src.cache.redis_client import CacheManager, get_redis_client
from apps.api.src.core.exceptions import RateLimitException

# In-memory fallback tracking for testing or environments where Redis is offline
_in_memory_counters: dict[str, list[float]] = defaultdict(list)
_in_memory_lock = asyncio.Lock()


async def check_rate_limit(key: str, max_requests: int, window_seconds: int = 60) -> None:
    """
    Evaluate rate limit threshold for a specific action key (e.g., 'login:192.168.1.1').
    Uses Redis atomic counter with window TTL if available; otherwise falls back to sliding in-memory window.
    Raises RateLimitException (HTTP 429) if exceeded.
    """
    redis_client = get_redis_client()
    if redis_client is not None:
        cache = CacheManager(redis_client)
        count = await cache.incr(f"ratelimit:{key}", expire_seconds=window_seconds)
        if count > max_requests:
            raise RateLimitException(
                message="Too many attempts. Please wait before retrying.",
                details={"action_key": key, "window_seconds": window_seconds},
            )
        return

    # In-memory sliding window fallback
    async with _in_memory_lock:
        now = time.monotonic()
        timestamps = _in_memory_counters[key]

        # Prune entries older than window
        cutoff = now - window_seconds
        _in_memory_counters[key] = [t for t in timestamps if t > cutoff]

        if len(_in_memory_counters[key]) >= max_requests:
            raise RateLimitException(
                message="Too many attempts. Please wait before retrying.",
                details={"action_key": key, "window_seconds": window_seconds},
            )

        _in_memory_counters[key].append(now)


def clear_in_memory_rate_limits() -> None:
    """Helper to reset rate limits between automated test runs."""
    _in_memory_counters.clear()
