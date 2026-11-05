"""Integration Tests for User Authentication and Login Endpoint."""

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
async def test_login_successful_with_email(async_client: AsyncClient, seeded_session: AsyncSession) -> None:
    """Authenticating with correct email and password returns JWT access token and refresh token."""
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"identifier": "superadmin@societysphere.io", "password": "Password123!"},
    )
    assert response.status_code == 200
    data = response.json()

    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert "refresh_token" in data
    assert data["user"]["email"] == "superadmin@societysphere.io"
    assert data["user"]["status"] == "ACTIVE"

    # Verify audit log was recorded
    audit_res = await seeded_session.execute(select(AuditLog).where(AuditLog.action == "AUTH_LOGIN_SUCCESS"))
    audit = audit_res.scalar_one_or_none()
    assert audit is not None


@pytest.mark.asyncio
async def test_login_successful_with_phone(async_client: AsyncClient) -> None:
    """Authenticating with registered phone number succeeds."""
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"identifier": "+919876543210", "password": "Password123!"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["user"]["email"] == "owner.a@palmstree.in"
    assert len(data["available_societies"]) >= 1


@pytest.mark.asyncio
async def test_login_failed_invalid_password(async_client: AsyncClient, seeded_session: AsyncSession) -> None:
    """Supplying an incorrect password returns 401 and logs failure."""
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"identifier": "superadmin@societysphere.io", "password": "WrongPassword99!"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_ERROR"

    audit_res = await seeded_session.execute(select(AuditLog).where(AuditLog.action == "AUTH_LOGIN_FAILED"))
    audit = audit_res.scalar_one_or_none()
    assert audit is not None


@pytest.mark.asyncio
async def test_login_failed_user_not_found_timing_safe(async_client: AsyncClient) -> None:
    """Querying a non-existent account returns generic 401 error."""
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"identifier": "nonexistent@societysphere.io", "password": "Password123!"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_ERROR"


@pytest.mark.asyncio
async def test_login_rate_limiting_enforced(async_client: AsyncClient) -> None:
    """Excessive rapid failed login attempts trigger HTTP 429 RateLimitException."""
    for _ in range(10):
        await async_client.post(
            "/api/v1/auth/login",
            json={"identifier": "rate-limit-test@societysphere.io", "password": "WrongPassword!"},
        )

    # 11th attempt should be blocked by rate limiter (limit is 10)
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"identifier": "rate-limit-test@societysphere.io", "password": "WrongPassword!"},
    )
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"
