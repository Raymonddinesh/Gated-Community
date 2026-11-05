"""Integration tests for Society and Spatial Hierarchy API Endpoints."""

import uuid

import pytest
from httpx import AsyncClient

from infrastructure.scripts.seed_dev_data import UUID_SOCIETY_A, UUID_SOCIETY_B


@pytest.mark.asyncio
async def test_list_societies_endpoint(async_client: AsyncClient):
    """GET /api/v1/societies returns all active societies."""
    response = await async_client.get("/api/v1/societies")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 2
    ids = {soc["id"] for soc in data}
    assert str(UUID_SOCIETY_A) in ids
    assert str(UUID_SOCIETY_B) in ids


@pytest.mark.asyncio
async def test_get_society_by_id(async_client: AsyncClient):
    """GET /api/v1/societies/{id} returns society metadata."""
    response = await async_client.get(f"/api/v1/societies/{UUID_SOCIETY_A}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(UUID_SOCIETY_A)
    assert "Palm Meadows" in data["legal_name"]
    assert data["country"] == "IN"


@pytest.mark.asyncio
async def test_get_nonexistent_society_returns_404(async_client: AsyncClient):
    """GET /api/v1/societies/{id} with unknown ID returns 404."""
    random_id = uuid.uuid4()
    response = await async_client.get(f"/api/v1/societies/{random_id}")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "NOT_FOUND"
    assert "not found" in data["error"]["message"].lower()


@pytest.mark.asyncio
async def test_get_society_blocks(async_client: AsyncClient):
    """GET /api/v1/societies/{id}/blocks lists blocks belonging to that society."""
    response = await async_client.get(f"/api/v1/societies/{UUID_SOCIETY_A}/blocks")
    assert response.status_code == 200
    blocks = response.json()
    assert len(blocks) >= 1
    assert any(b["code"] == "BLK-A" for b in blocks)
    assert all(b["society_id"] == str(UUID_SOCIETY_A) for b in blocks)


@pytest.mark.asyncio
async def test_list_society_blocks_url_and_header_mismatch_returns_400(async_client: AsyncClient):
    """
    Providing an X-Society-ID header that contradicts the URL society parameter
    must return HTTP 400 Bad Request with code TENANT_CONTEXT_MISMATCH.
    """
    response = await async_client.get(
        f"/api/v1/societies/{UUID_SOCIETY_A}/blocks",
        headers={"X-Society-ID": str(UUID_SOCIETY_B)},
    )
    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "TENANT_CONTEXT_MISMATCH"
    assert "mismatch" in data["error"]["message"].lower()


@pytest.mark.asyncio
async def test_get_block_floors_and_units_hierarchy(async_client: AsyncClient):
    """End-to-end traversal: Society -> Blocks -> Floors -> Units."""
    # 1. Fetch blocks
    blocks_res = await async_client.get(f"/api/v1/societies/{UUID_SOCIETY_A}/blocks")
    assert blocks_res.status_code == 200
    block_a = blocks_res.json()[0]
    block_id = block_a["id"]

    # 2. Fetch floors for block
    floors_res = await async_client.get(
        f"/api/v1/blocks/{block_id}/floors",
        headers={"X-Society-ID": str(UUID_SOCIETY_A)},
    )
    assert floors_res.status_code == 200
    floors = floors_res.json()
    assert len(floors) >= 1
    floor_id = floors[0]["id"]

    # 3. Fetch units on floor
    units_res = await async_client.get(
        f"/api/v1/floors/{floor_id}/units",
        headers={"X-Society-ID": str(UUID_SOCIETY_A)},
    )
    assert units_res.status_code == 200
    units = units_res.json()
    assert len(units) >= 1
    assert any(u["unit_number"] in ["101", "102"] for u in units)


@pytest.mark.asyncio
async def test_spatial_traversal_with_mismatched_tenant_hint_returns_404(async_client: AsyncClient):
    """
    Attempting to access a Block belonging to Society A while providing
    X-Society-ID hint of Society B must return 404 (preventing cross-tenant leakage).
    """
    blocks_res = await async_client.get(f"/api/v1/societies/{UUID_SOCIETY_A}/blocks")
    block_a_id = blocks_res.json()[0]["id"]

    # Supply Society B's header hint on Society A's block
    mismatched_res = await async_client.get(
        f"/api/v1/blocks/{block_a_id}/floors",
        headers={"X-Society-ID": str(UUID_SOCIETY_B)},
    )
    assert mismatched_res.status_code == 404
