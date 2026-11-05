"""Tests for Session Lifecycle, Token Rotation, Replay Detection, and Revocation."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.security.rate_limiter import clear_in_memory_rate_limits
from apps.api.src.database.models.audit import AuditLog


@pytest.fixture(autouse=True)
def reset_rate_limits():
    clear_in_memory_rate_limits()
    yield
    clear_in_memory_rate_limits()


@pytest.mark.asyncio
async def test_refresh_token_rotation_success(
    async_client: AsyncClient, seeded_session: AsyncSession
) -> None:
    """Refreshing session yields a new access token and rotating refresh token."""
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"identifier": "owner.a@palmstree.in", "password": "Password123!"},
    )
    assert login_resp.status_code == 200
    original_refresh = login_resp.json()["refresh_token"]

    refresh_resp = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": original_refresh},
    )
    assert refresh_resp.status_code == 200
    refresh_data = refresh_resp.json()

    assert "access_token" in refresh_data
    assert "refresh_token" in refresh_data
    # Must be rotated to a new token
    assert refresh_data["refresh_token"] != original_refresh


@pytest.mark.asyncio
async def test_refresh_token_replay_attack_neutralization(
    async_client: AsyncClient,
    seeded_session: AsyncSession,
) -> None:
    """
    CRITICAL SECURITY TEST:
    If a previously rotated refresh token is presented again (replay attack),
    the backend immediately invalidates the entire token family and logs an alert.
    """
    # 1. Login to obtain initial token T1
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"identifier": "owner.a@palmstree.in", "password": "Password123!"},
    )
    t1 = login_resp.json()["refresh_token"]

    # 2. Legitimate refresh: T1 -> T2
    refresh1_resp = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": t1},
    )
    assert refresh1_resp.status_code == 200
    t2 = refresh1_resp.json()["refresh_token"]

    # 3. Attacker replays compromised token T1
    replay_resp = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": t1},
    )
    assert replay_resp.status_code == 401
    assert replay_resp.json()["error"]["code"] == "AUTHENTICATION_ERROR"

    # 4. Legitimate user tries to use T2: MUST FAIL because entire family was revoked!
    t2_resp = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": t2},
    )
    assert t2_resp.status_code == 401

    # 5. Verify high-severity audit log
    audit_res = await seeded_session.execute(
        select(AuditLog).where(AuditLog.action == "AUTH_REFRESH_REPLAY_DETECTED")
    )
    replay_audits = audit_res.scalars().all()
    assert len(replay_audits) >= 1


@pytest.mark.asyncio
async def test_logout_revokes_current_session(async_client: AsyncClient) -> None:
    """Logging out revokes session; subsequent requests with access token fail."""
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"identifier": "owner.a@palmstree.in", "password": "Password123!"},
    )
    token = login_resp.json()["access_token"]

    # Verify access works before logout
    me_resp = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200

    # Logout
    logout_resp = await async_client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert logout_resp.status_code == 200

    # Subsequent access fails
    me_after = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_after.status_code == 401
    assert me_after.json()["error"]["code"] == "AUTHENTICATION_ERROR"


@pytest.mark.asyncio
async def test_logout_all_terminates_multiple_sessions(async_client: AsyncClient) -> None:
    """Logout-all terminates all active sessions across devices."""
    login1 = await async_client.post(
        "/api/v1/auth/login",
        json={"identifier": "owner.a@palmstree.in", "password": "Password123!"},
    )
    login2 = await async_client.post(
        "/api/v1/auth/login",
        json={"identifier": "owner.a@palmstree.in", "password": "Password123!"},
    )

    token1 = login1.json()["access_token"]
    token2 = login2.json()["access_token"]

    # Call logout-all using token1
    logout_all_resp = await async_client.post(
        "/api/v1/auth/logout-all",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert logout_all_resp.status_code == 200

    # Both tokens must now be rejected
    res1 = await async_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token1}"})
    assert res1.status_code == 401

    res2 = await async_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token2}"})
    assert res2.status_code == 401
