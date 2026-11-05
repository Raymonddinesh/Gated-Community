"""Tests for Cryptographic Single-Use Password Reset and Session Revocation."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_password_reset_flow_complete(async_client: AsyncClient) -> None:
    """Complete password reset lifecycle: request -> confirm -> login with new password."""
    # 1. Login initially with current password
    login_init = await async_client.post(
        "/api/v1/auth/login",
        json={"identifier": "tenant.a@palmstree.in", "password": "Password123!"},
    )
    assert login_init.status_code == 200
    old_session_token = login_init.json()["access_token"]

    # 2. Request reset
    req_resp = await async_client.post(
        "/api/v1/auth/password-reset/request",
        json={"identifier": "tenant.a@palmstree.in"},
    )
    assert req_resp.status_code == 200
    reset_token = req_resp.json()["reset_token"]
    assert reset_token is not None

    # 3. Confirm reset with new strong password
    new_password = "BrandNewSecurePassword2026!"
    confirm_resp = await async_client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": reset_token, "new_password": new_password},
    )
    assert confirm_resp.status_code == 200

    # 4. Existing session MUST be terminated
    old_session_check = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {old_session_token}"},
    )
    assert old_session_check.status_code == 401

    # 5. Old password MUST fail
    failed_login = await async_client.post(
        "/api/v1/auth/login",
        json={"identifier": "tenant.a@palmstree.in", "password": "Password123!"},
    )
    assert failed_login.status_code == 401

    # 6. New password MUST succeed
    new_login = await async_client.post(
        "/api/v1/auth/login",
        json={"identifier": "tenant.a@palmstree.in", "password": new_password},
    )
    assert new_login.status_code == 200


@pytest.mark.asyncio
async def test_password_reset_single_use_enforcement(async_client: AsyncClient) -> None:
    """Reset token cannot be reused once consumed."""
    req_resp = await async_client.post(
        "/api/v1/auth/password-reset/request",
        json={"identifier": "tenant.a@palmstree.in"},
    )
    token = req_resp.json()["reset_token"]

    # First consumption succeeds
    first_resp = await async_client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": "NewValidPassword1!"},
    )
    assert first_resp.status_code == 200

    # Second consumption MUST fail (replay prevention)
    second_resp = await async_client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": "AnotherNewPassword2!"},
    )
    assert second_resp.status_code == 400
    assert second_resp.json()["error"]["code"] == "INVALID_RESET_TOKEN"


@pytest.mark.asyncio
async def test_password_reset_enumeration_protection(async_client: AsyncClient) -> None:
    """Requesting reset for non-existent account returns identical success response."""
    resp = await async_client.post(
        "/api/v1/auth/password-reset/request",
        json={"identifier": "doesnotexist@nowhere.com"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "If an account matches this identifier" in data["message"]
    # Token must NOT be provided for non-existent accounts
    assert data.get("reset_token") is None
