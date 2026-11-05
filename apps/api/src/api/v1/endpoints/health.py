"""Health and Readiness Probes."""

import time
from typing import Any

from fastapi import APIRouter, Response, status

from apps.api.src.cache.redis_client import check_redis_health
from apps.api.src.core.config import get_settings
from apps.api.src.database.session import check_database_health
from apps.api.src.events.broker import check_broker_health

router = APIRouter(tags=["Health"])

STARTUP_TIME = time.time()


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check() -> dict[str, Any]:
    """High-level health and application runtime information."""
    settings = get_settings()
    uptime_seconds = int(time.time() - STARTUP_TIME)
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "uptime_seconds": uptime_seconds,
    }


@router.get("/health/live", status_code=status.HTTP_200_OK)
async def liveness_probe() -> dict[str, str]:
    """Kubernetes/Container liveness probe verifying application process is responsive."""
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness_probe(response: Response) -> dict[str, Any]:
    """
    Readiness probe verifying all backing dependencies (PostgreSQL, Redis, RabbitMQ).
    Returns 200 if dependencies are ready, or 503 if any mandatory dependency is failing.
    """
    db_ok = await check_database_health()
    redis_ok = await check_redis_health()
    broker_ok = await check_broker_health()

    dependencies = {
        "database": "connected" if db_ok else "unreachable",
        "redis": "connected" if redis_ok else "unreachable",
        "message_broker": "connected" if broker_ok else "unreachable",
    }

    # Readiness Contract:
    # 1. In Production/Staging: Any required dependency failure MUST return HTTP 503.
    # 2. In Development: Permissive HTTP 200 returning 'degraded' status is allowed for inspectability.
    settings = get_settings()
    is_ready = db_ok and redis_ok and broker_ok
    if not is_ready:
        if settings.APP_ENV in ("production", "staging"):
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        else:
            response.status_code = status.HTTP_200_OK

    return {
        "status": "ready" if is_ready else "degraded",
        "environment": settings.APP_ENV,
        "dependencies": dependencies,
    }
