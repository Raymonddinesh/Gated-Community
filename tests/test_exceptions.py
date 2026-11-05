"""Tests for Centralized Error Handling."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_not_found_error_format(async_client: AsyncClient):
    response = await async_client.get("/non-existent-endpoint")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "NOT_FOUND"
    assert "request_id" in data["error"]
    assert "message" in data["error"]
