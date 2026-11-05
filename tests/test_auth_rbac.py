"""Tests for Role-Based Access Control, Permission Resolution, and Privilege Escalation Prevention."""

import pytest
from httpx import AsyncClient

SOCIETY_A_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
SOCIETY_B_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
USER_TENANT_A = "33333333-3333-3333-3333-33333333333a"
USER_DELEGATE_A = "44444444-4444-4444-4444-44444444444a"
USER_MEMBER_B = "55555555-5555-5555-5555-55555555555b"


@pytest.mark.asyncio
async def test_super_admin_can_assign_roles(async_client: AsyncClient) -> None:
    """Super Admin has full authority to assign society roles to verified members."""
    # 1. Login as Super Admin
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"identifier": "superadmin@societysphere.io", "password": "Password123!"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]

    # 2. Assign COMMITTEE_MEMBER role to tenant.a (verified member) in Society A
    assign_resp = await async_client.post(
        f"/api/v1/societies/{SOCIETY_A_ID}/roles/assign",
        headers={"Authorization": f"Bearer {token}"},
        json={"user_id": USER_TENANT_A, "role_code": "COMMITTEE_MEMBER"},
    )
    assert assign_resp.status_code == 200
    assert assign_resp.json()["role_code"] == "COMMITTEE_MEMBER"


@pytest.mark.asyncio
async def test_unauthorized_user_cannot_assign_roles(async_client: AsyncClient) -> None:
    """A standard resident/tenant lacks role.assign permission and is forbidden (403)."""
    # 1. Login as ordinary tenant
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"identifier": "tenant.a@palmstree.in", "password": "Password123!"},
    )
    token = login_resp.json()["access_token"]

    # 2. Attempt to assign role
    assign_resp = await async_client.post(
        f"/api/v1/societies/{SOCIETY_A_ID}/roles/assign",
        headers={"Authorization": f"Bearer {token}"},
        json={"user_id": USER_DELEGATE_A, "role_code": "SECRETARY"},
    )
    assert assign_resp.status_code == 403
    assert assign_resp.json()["error"]["code"] == "AUTHORIZATION_ERROR"


@pytest.mark.asyncio
async def test_privilege_escalation_guard_cannot_assign_super_admin(
    async_client: AsyncClient,
) -> None:
    """Non-SUPER_ADMIN users cannot escalate privileges or assign SUPER_ADMIN role."""
    # Login as owner (who does not possess platform SUPER_ADMIN)
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"identifier": "owner.a@palmstree.in", "password": "Password123!"},
    )
    token = login_resp.json()["access_token"]

    # Attempt to assign SUPER_ADMIN
    resp = await async_client.post(
        f"/api/v1/societies/{SOCIETY_A_ID}/roles/assign",
        headers={"Authorization": f"Bearer {token}"},
        json={"user_id": USER_DELEGATE_A, "role_code": "SUPER_ADMIN"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_cannot_assign_role_to_non_member(async_client: AsyncClient) -> None:
    """Assigning a role to a user who does not belong to the society is rejected (403)."""
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"identifier": "superadmin@societysphere.io", "password": "Password123!"},
    )
    token = login_resp.json()["access_token"]

    # USER_MEMBER_B only belongs to Society B, NOT Society A
    resp = await async_client.post(
        f"/api/v1/societies/{SOCIETY_A_ID}/roles/assign",
        headers={"Authorization": f"Bearer {token}"},
        json={"user_id": USER_MEMBER_B, "role_code": "RESIDENT"},
    )
    assert resp.status_code == 403
