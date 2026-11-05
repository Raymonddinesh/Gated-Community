"""Tests for Health and Readiness Probes."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from apps.api.src.core.config import EnvironmentType, Settings


@pytest.mark.asyncio
async def test_health_endpoint(async_client: AsyncClient):
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["app"] == "SocietySphere"
    assert "uptime_seconds" in data


@pytest.mark.asyncio
async def test_liveness_probe(async_client: AsyncClient):
    response = await async_client.get("/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "alive"


@pytest.mark.asyncio
async def test_readiness_probe_default(async_client: AsyncClient):
    response = await async_client.get("/health/ready")
    assert response.status_code in (200, 503)
    data = response.json()
    assert "status" in data
    assert "dependencies" in data
    assert "database" in data["dependencies"]
    assert "redis" in data["dependencies"]
    assert "message_broker" in data["dependencies"]


@pytest.mark.asyncio
async def test_readiness_probe_production_failure_returns_503(async_client: AsyncClient):
    """Production readiness contract: required dependency failure MUST return HTTP 503."""
    prod_settings = Settings(
        APP_ENV=EnvironmentType.PRODUCTION,
        DEBUG=False,
        SECRET_KEY="a-sufficiently-secure-secret-key-32-chars-long",
        CORS_ALLOWED_ORIGINS=["https://app.societysphere.com"],
    )

    with (
        patch("apps.api.src.api.v1.endpoints.health.get_settings", return_value=prod_settings),
        patch(
            "apps.api.src.api.v1.endpoints.health.check_database_health",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch(
            "apps.api.src.api.v1.endpoints.health.check_redis_health",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "apps.api.src.api.v1.endpoints.health.check_broker_health",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        response = await async_client.get("/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["dependencies"]["database"] == "unreachable"


@pytest.mark.asyncio
async def test_readiness_probe_production_healthy_returns_200(async_client: AsyncClient):
    """Production readiness contract: all dependencies healthy returns HTTP 200 ready."""
    prod_settings = Settings(
        APP_ENV=EnvironmentType.PRODUCTION,
        DEBUG=False,
        SECRET_KEY="a-sufficiently-secure-secret-key-32-chars-long",
        CORS_ALLOWED_ORIGINS=["https://app.societysphere.com"],
    )

    with (
        patch("apps.api.src.api.v1.endpoints.health.get_settings", return_value=prod_settings),
        patch(
            "apps.api.src.api.v1.endpoints.health.check_database_health",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "apps.api.src.api.v1.endpoints.health.check_redis_health",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "apps.api.src.api.v1.endpoints.health.check_broker_health",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        response = await async_client.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["dependencies"]["database"] == "connected"
        assert data["dependencies"]["redis"] == "connected"
        assert data["dependencies"]["message_broker"] == "connected"


@pytest.mark.asyncio
async def test_readiness_probe_development_permissive_behavior(async_client: AsyncClient):
    """Development readiness contract: allows inspectability with HTTP 200 even if degraded."""
    dev_settings = Settings(
        APP_ENV=EnvironmentType.DEVELOPMENT,
        DEBUG=True,
    )

    with (
        patch("apps.api.src.api.v1.endpoints.health.get_settings", return_value=dev_settings),
        patch(
            "apps.api.src.api.v1.endpoints.health.check_database_health",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch(
            "apps.api.src.api.v1.endpoints.health.check_redis_health",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch(
            "apps.api.src.api.v1.endpoints.health.check_broker_health",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
        response = await async_client.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"


@pytest.mark.asyncio
async def test_api_v1_version_endpoint(async_client: AsyncClient):
    response = await async_client.get("/api/v1/version")
    assert response.status_code == 200
    data = response.json()
    assert data["api_version"] == "v1"
    assert data["app_name"] == "SocietySphere"
