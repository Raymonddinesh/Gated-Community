"""Tests for Correlation ID and Security Headers."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_correlation_id_generated_automatically(async_client: AsyncClient):
    response = await async_client.get("/health")
    assert response.status_code == 200
    assert "X-Correlation-ID" in response.headers
    assert len(response.headers["X-Correlation-ID"]) > 10


@pytest.mark.asyncio
async def test_correlation_id_propagated_from_request(async_client: AsyncClient):
    custom_id = "test-custom-correlation-12345"
    response = await async_client.get("/health", headers={"X-Correlation-ID": custom_id})
    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == custom_id


@pytest.mark.asyncio
async def test_security_headers_present(async_client: AsyncClient):
    response = await async_client.get("/health")
    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-XSS-Protection"] == "1; mode=block"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
