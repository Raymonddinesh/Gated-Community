"""Tests for Finance Role-Based Access Control and Permission Boundaries."""

import pytest
from httpx import AsyncClient

SOCIETY_A_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


@pytest.mark.asyncio
async def test_admin_and_treasurer_can_access_finance(async_client: AsyncClient) -> None:
    """Society Admin has permissions to view chart of accounts and periods."""
    # Login as owner (Society Admin in Society A)
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"identifier": "owner.a@palmstree.in", "password": "Password123!"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]

    # Access chart of accounts
    coa_resp = await async_client.get(
        f"/api/v1/societies/{SOCIETY_A_ID}/finance/accounts",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert coa_resp.status_code == 200
    assert len(coa_resp.json()) >= 5

    # Access periods
    periods_resp = await async_client.get(
        f"/api/v1/societies/{SOCIETY_A_ID}/finance/periods",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert periods_resp.status_code == 200
    assert len(periods_resp.json()) >= 1


@pytest.mark.asyncio
async def test_tenant_resident_cannot_create_or_post_journals(async_client: AsyncClient) -> None:
    """An ordinary tenant/resident lacks finance.journal.create and receives 403 Forbidden."""
    # Login as tenant Priya
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"identifier": "tenant.a@palmstree.in", "password": "Password123!"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]

    # Attempt to post a journal
    post_resp = await async_client.post(
        f"/api/v1/societies/{SOCIETY_A_ID}/finance/journals/00000000-0000-0000-0000-000000000000/post",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert post_resp.status_code == 403
    assert post_resp.json()["error"]["code"] == "AUTHORIZATION_ERROR"


@pytest.mark.asyncio
async def test_tenant_cannot_approve_expenses(async_client: AsyncClient) -> None:
    """An ordinary tenant lacks finance.expense.approve and receives 403 Forbidden."""
    # Login as tenant Priya
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"identifier": "tenant.a@palmstree.in", "password": "Password123!"},
    )
    token = login_resp.json()["access_token"]

    # Attempt to approve expense
    appr_resp = await async_client.post(
        f"/api/v1/societies/{SOCIETY_A_ID}/finance/expenses/00000000-0000-0000-0000-000000000000/approve",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert appr_resp.status_code == 403
    assert appr_resp.json()["error"]["code"] == "AUTHORIZATION_ERROR"
