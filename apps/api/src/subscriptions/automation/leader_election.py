"""Phase 21E.6 Stage 3 — Distributed Redis Leader Election with PostgreSQL Fencing.

Implements:
- Distributed mutual exclusion using Redis SET NX PX leases (30s TTL, 10s heartbeat).
- Unique owner tokens per worker instance.
- Atomic compare-and-renew Lua script.
- Atomic compare-and-release Lua script.
- Session-level PostgreSQL advisory locking on dedicated connection as split-brain fencing.
- Immediate leadership loss handling (forfeits scheduling coroutines instantly).
- Safe cleanup and lock release on graceful worker shutdown.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from uuid import uuid4

from redis.asyncio.client import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from apps.api.src.cache.redis_client import get_redis_client
from apps.api.src.database.session import get_engine
from apps.api.src.subscriptions.automation.scheduler_service import compute_advisory_lock_key

logger = logging.getLogger("societysphere.subscriptions.automation.leader")

# Atomic Compare-and-Renew Lua Script
COMPARE_AND_RENEW_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('pexpire', KEYS[1], ARGV[2])
else
    return 0
end
"""

# Atomic Compare-and-Release Lua Script
COMPARE_AND_RELEASE_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""

DEFAULT_LEASE_KEY = "societysphere:scheduler:leader"
DEFAULT_LEASE_TTL_MS = 30000  # 30 seconds
DEFAULT_HEARTBEAT_SECONDS = 10.0  # 10 seconds


class RedisLeaderElector:
    """Manages distributed leader election with dual-layer Redis lease + PostgreSQL fencing."""

    def __init__(
        self,
        redis_client: Redis | None = None,
        engine: AsyncEngine | None = None,
        lease_key: str = DEFAULT_LEASE_KEY,
        lease_ttl_ms: int = DEFAULT_LEASE_TTL_MS,
        heartbeat_interval: float = DEFAULT_HEARTBEAT_SECONDS,
        on_leadership_acquired: Callable[[], Awaitable[None]] | None = None,
        on_leadership_lost: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self.redis = redis_client
        self.engine = engine
        self.lease_key = lease_key
        self.lease_ttl_ms = lease_ttl_ms
        self.heartbeat_interval = heartbeat_interval
        self.owner_token: str = f"worker-{uuid4().hex}"
        self.on_leadership_acquired = on_leadership_acquired
        self.on_leadership_lost = on_leadership_lost

        self._is_leader: bool = False
        self._running: bool = False
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._pg_conn: AsyncConnection | None = None
        self._advisory_lock_key: int = compute_advisory_lock_key(self.lease_key)

    @property
    def is_leader(self) -> bool:
        """Return True if this instance currently holds the verified leader lease."""
        return self._is_leader

    async def _get_redis(self) -> Redis | None:
        if self.redis is not None:
            return self.redis
        return get_redis_client()

    async def _get_engine(self) -> AsyncEngine:
        if self.engine is not None:
            return self.engine
        return get_engine()

    async def acquire_leadership(self) -> bool:
        """Attempt to acquire distributed leadership via Redis lease + PG advisory lock."""
        redis = await self._get_redis()
        if not redis:
            logger.warning("Redis client unavailable; cannot participate in leader election.")
            return False

        # 1. Acquire Redis Lease with SET NX PX
        try:
            acquired = await redis.set(
                self.lease_key,
                self.owner_token,
                nx=True,
                px=self.lease_ttl_ms,
            )
            if not acquired:
                return False
        except Exception as exc:
            logger.warning("Redis error during leader lease acquisition: %s", exc)
            return False

        # 2. Acquire PostgreSQL Session-Level Advisory Lock (Split-Brain Protection)
        try:
            engine = await self._get_engine()
            # Must use a dedicated connection for session-level advisory locks
            self._pg_conn = await engine.connect()
            res = await self._pg_conn.execute(
                text("SELECT pg_try_advisory_lock(:lock_key)"),
                {"lock_key": self._advisory_lock_key},
            )
            pg_locked = bool(res.scalar())
            if not pg_locked:
                logger.warning(
                    "Redis lease acquired by %s, but PG advisory lock failed (split-brain detected). Releasing lease.",
                    self.owner_token,
                )
                await self._release_redis_lease()
                await self._close_pg_conn()
                return False
        except Exception as exc:
            logger.error("PostgreSQL advisory lock acquisition error: %s", exc)
            await self._release_redis_lease()
            await self._close_pg_conn()
            return False

        # 3. Leadership fully secured
        self._is_leader = True
        logger.info(
            "Leadership ACQUIRED by instance '%s' (Lease key: %s, TTL: %dms, Advisory key: %d)",
            self.owner_token,
            self.lease_key,
            self.lease_ttl_ms,
            self._advisory_lock_key,
        )

        # 4. Launch Heartbeat Coroutine
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        # 5. Invoke Callback
        if self.on_leadership_acquired:
            try:
                await self.on_leadership_acquired()
            except Exception as exc:
                logger.error("Error in on_leadership_acquired callback: %s", exc, exc_info=True)

        return True

    async def _heartbeat_loop(self) -> None:
        """Continuous heartbeat coroutine renewing Redis lease."""
        while self._is_leader:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                if not self._is_leader:
                    break

                redis = await self._get_redis()
                if not redis:
                    logger.warning("Redis client became None during heartbeat; forfeiting leadership.")
                    await self._forfeit_leadership()
                    break

                # Atomic compare-and-renew
                renewed = await redis.eval(
                    COMPARE_AND_RENEW_LUA,
                    1,
                    self.lease_key,
                    self.owner_token,
                    self.lease_ttl_ms,
                )

                if renewed != 1:
                    logger.warning(
                        "Leader lease renewal failed for owner '%s' (lease expired or usurped). Forfeiting.",
                        self.owner_token,
                    )
                    await self._forfeit_leadership()
                    break

                # Also verify PG connection is alive
                if self._pg_conn:
                    try:
                        await self._pg_conn.execute(text("SELECT 1"))
                    except Exception as pg_exc:
                        logger.error("PG dedicated connection died during leader heartbeat: %s", pg_exc)
                        await self._forfeit_leadership()
                        break

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Unexpected error in leader heartbeat loop: %s", exc)
                await self._forfeit_leadership()
                break

    async def _release_redis_lease(self) -> None:
        """Atomic compare-and-release Redis lease."""
        try:
            redis = await self._get_redis()
            if redis:
                await redis.eval(
                    COMPARE_AND_RELEASE_LUA,
                    1,
                    self.lease_key,
                    self.owner_token,
                )
        except Exception as exc:
            logger.warning("Error releasing Redis leader lease: %s", exc)

    async def _close_pg_conn(self) -> None:
        """Safely unlock session-level PG advisory lock and close dedicated connection."""
        if self._pg_conn:
            try:
                await self._pg_conn.execute(
                    text("SELECT pg_advisory_unlock(:lock_key)"),
                    {"lock_key": self._advisory_lock_key},
                )
            except Exception as exc:
                logger.debug("Advisory unlock returned/failed: %s", exc)
            finally:
                try:
                    await self._pg_conn.close()
                except Exception:
                    pass
                self._pg_conn = None

    async def _forfeit_leadership(self) -> None:
        """Immediately drop leader status and trigger forfeiture callback."""
        if not self._is_leader:
            return

        self._is_leader = False
        logger.warning("Leadership FORFEITED by instance '%s'.", self.owner_token)

        # Cancel heartbeat task if not current task
        if self._heartbeat_task and not self._heartbeat_task.done():
            if asyncio.current_task() != self._heartbeat_task:
                self._heartbeat_task.cancel()

        # Unlock and close PG
        await self._close_pg_conn()

        # Invoke callback immediately so scheduling halts
        if self.on_leadership_lost:
            try:
                await self.on_leadership_lost()
            except Exception as exc:
                logger.error("Error in on_leadership_lost callback: %s", exc, exc_info=True)

    async def step_down(self) -> None:
        """Voluntarily step down from leadership during graceful worker shutdown."""
        if not self._is_leader:
            return

        logger.info("Instance '%s' voluntarily stepping down from leadership.", self.owner_token)
        self._is_leader = False

        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except (asyncio.CancelledError, Exception):
                pass

        # Release both locks cleanly
        await self._release_redis_lease()
        await self._close_pg_conn()

        if self.on_leadership_lost:
            try:
                await self.on_leadership_lost()
            except Exception as exc:
                logger.error("Error in on_leadership_lost callback: %s", exc)
