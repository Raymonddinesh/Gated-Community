"""Tests for Insecure Direct Object Reference (IDOR) and Token Tampering Prevention."""

import pytest
from httpx import AsyncClient

SOCIETY_A_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
SOCIETY_B_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
USER_DELEGATE_A = "44444444-4444-4444-4444-44444444444a"


@pytest.mark.asyncio
async def test_tampered_jwt_rejected(async_client: AsyncClient) -> None:
    """Tampered or invalid JWT signatures are unconditionally rejected (401)."""
    fake_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMTExMTExMS0xMTExLTExMTEtMTExMS0xMTExMTExMTExMWEiLCJzaWQiOiIyMjIyMjIyMi0yMjIyLTIyMjItMjIyMi0yMjIyMjIyMjIyMmEiLCJleHAiOjE5OTk5OTk5OTl9.invalid_signature"
    response = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {fake_token}"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_ERROR"


@pytest.mark.asyncio
async def test_idor_cross_tenant_role_assignment_blocked(async_client: AsyncClient) -> None:
    """
    An attacker cannot manipulate the URL path to target another tenant's society
    even if they provide headers matching their own society.
    """
    # 1. Login as owner in Society A
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"identifier": "owner.a@palmstree.in", "password": "Password123!"},
    )
    token = login_resp.json()["access_token"]

    # 2. Try to perform action in Society B with mismatch header
    resp = await async_client.post(
        f"/api/v1/societies/{SOCIETY_B_ID}/roles/assign",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Society-ID": SOCIETY_A_ID,  # Mismatch header
        },
        json={"user_id": USER_DELEGATE_A, "role_code": "RESIDENT"},
    )
    # Must be rejected because URL (B) and header (A) contradict each other!
    assert resp.status_code in (400, 403)


@pytest.mark.asyncio
async def test_unauthenticated_request_to_me_endpoint_rejected(async_client: AsyncClient) -> None:
    """Calling /me without Authorization header returns HTTP 401."""
    resp = await async_client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTHENTICATION_ERROR"
