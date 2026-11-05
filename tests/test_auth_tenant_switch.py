"""Tests for Multi-Tenant Context Switching and Membership Verification."""

import pytest
from httpx import AsyncClient

SOCIETY_A_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
SOCIETY_B_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


@pytest.mark.asyncio
async def test_tenant_switch_success(async_client: AsyncClient) -> None:
    """User holding membership in Society A successfully switches to Society A."""
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"identifier": "owner.a@palmstree.in", "password": "Password123!"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]

    switch_resp = await async_client.post(
        f"/api/v1/auth/societies/{SOCIETY_A_ID}/switch",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert switch_resp.status_code == 200
    data = switch_resp.json()
    assert data["society_id"] == SOCIETY_A_ID
    assert "Palm Meadows" in data["display_name"]
    assert isinstance(data["roles"], list)
    assert isinstance(data["permissions"], list)


@pytest.mark.asyncio
async def test_tenant_switch_unauthorized_society_rejected(async_client: AsyncClient) -> None:
    """User attempting to switch to a society where they are NOT a member is forbidden (403)."""
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"identifier": "owner.a@palmstree.in", "password": "Password123!"},
    )
    token = login_resp.json()["access_token"]

    # owner.a is NOT a member of Society B
    switch_resp = await async_client.post(
        f"/api/v1/auth/societies/{SOCIETY_B_ID}/switch",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert switch_resp.status_code == 403
    assert switch_resp.json()["error"]["code"] == "AUTHORIZATION_ERROR"
