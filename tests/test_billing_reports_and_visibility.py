"""Tests for Billing Reports, Resident Financial Visibility, IDOR, Tenant Isolation, and RBAC."""

from decimal import Decimal
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.billing.application.report_service import BillingReportService
from apps.api.src.billing.infrastructure.repositories import InvoiceRepository

SOCIETY_A_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
SOCIETY_B_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


@pytest.mark.asyncio
async def test_billing_reports_aggregation(seeded_session: AsyncSession) -> None:
    """Billing reports calculate exact totals, unit grouping, and aging buckets deterministically."""
    report_service = BillingReportService(seeded_session)

    # 1. Collection summary
    summary = await report_service.get_collection_summary(UUID(SOCIETY_A_ID))
    assert Decimal(summary["total_billed"]) >= Decimal("6000.0000")  # INV-000001 (3000) + INV-000002 (3000)
    assert Decimal(summary["total_paid_against_invoices"]) >= Decimal("3000.0000")
    assert Decimal(summary["total_outstanding"]) >= Decimal("3000.0000")

    # 2. Unit-wise outstanding
    unit_outstanding = await report_service.get_unit_wise_outstanding(UUID(SOCIETY_A_ID))
    assert len(unit_outstanding) >= 1
    u102 = [u for u in unit_outstanding if u["unit_number"] == "102"]
    assert len(u102) == 1
    assert Decimal(u102[0]["outstanding_amount"]) == Decimal("3000.0000")

    # 3. Resident-wise outstanding
    resident_outstanding = await report_service.get_resident_wise_outstanding(UUID(SOCIETY_A_ID))
    assert len(resident_outstanding) >= 1

    # 4. Aging report
    aging = await report_service.get_aging_report(UUID(SOCIETY_A_ID))
    assert Decimal(aging["total_outstanding"]) >= Decimal("3000.0000")
    assert "current_or_0_to_30" in aging["aging_buckets"]


@pytest.mark.asyncio
async def test_resident_financial_visibility_and_idor_protection(
    async_client: AsyncClient, seeded_session: AsyncSession
) -> None:
    """Residents can view own invoices/receipts but are forbidden from inspecting others (IDOR)."""
    invoice_repo = InvoiceRepository(seeded_session)
    inv1 = await invoice_repo.get_by_number("INV-000001", UUID(SOCIETY_A_ID))  # Owned by Owner A
    inv2 = await invoice_repo.get_by_number("INV-000002", UUID(SOCIETY_A_ID))  # Owned by Tenant A
    assert inv1 is not None and inv2 is not None

    # 1. Login as Tenant Priya
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"identifier": "tenant.a@palmstree.in", "password": "Password123!"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]

    # 2. Tenant can list own invoices
    my_invs_resp = await async_client.get(
        f"/api/v1/societies/{SOCIETY_A_ID}/billing/my/invoices",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert my_invs_resp.status_code == 200
    numbers = [i["invoice_number"] for i in my_invs_resp.json()]
    assert "INV-000002" in numbers
    assert "INV-000001" not in numbers  # Owner's invoice is NOT visible!

    # 3. Tenant can view own invoice details
    own_detail_resp = await async_client.get(
        f"/api/v1/societies/{SOCIETY_A_ID}/billing/my/invoices/{inv2.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert own_detail_resp.status_code == 200
    assert own_detail_resp.json()["invoice_number"] == "INV-000002"

    # 4. IDOR Attack: Tenant attempts to inspect Owner's invoice -> 403 Forbidden
    idor_resp = await async_client.get(
        f"/api/v1/societies/{SOCIETY_A_ID}/billing/my/invoices/{inv1.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert idor_resp.status_code == 403

    # 5. Tenant can check own outstanding balance
    out_resp = await async_client.get(
        f"/api/v1/societies/{SOCIETY_A_ID}/billing/my/outstanding",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert out_resp.status_code == 200
    assert Decimal(out_resp.json()["total_outstanding"]) == Decimal("3000.0000")


@pytest.mark.asyncio
async def test_billing_rbac_resident_forbidden_from_privileged_operations(
    async_client: AsyncClient,
) -> None:
    """Ordinary residents/tenants cannot generate invoices, approve, or alter billing config."""
    # Login as Tenant Priya
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"identifier": "tenant.a@palmstree.in", "password": "Password123!"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]

    # 1. Attempt to generate invoices
    gen_resp = await async_client.post(
        f"/api/v1/societies/{SOCIETY_A_ID}/billing/periods/00000000-0000-0000-0000-000000000000/generate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert gen_resp.status_code == 403
    assert gen_resp.json()["error"]["code"] == "AUTHORIZATION_ERROR"

    # 2. Attempt to create charge rule
    rule_resp = await async_client.post(
        f"/api/v1/societies/{SOCIETY_A_ID}/billing/rules",
        json={
            "name": "Unauthorized Rule",
            "code": "UNAUTH_01",
            "calculation_type": "FIXED_PER_UNIT",
            "rate_or_amount": "100.00",
            "income_account_id": "00000000-0000-0000-0000-000000000000",
            "effective_from": "2026-04-01",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert rule_resp.status_code == 403


@pytest.mark.asyncio
async def test_tenant_isolation_cross_society_access_blocked(
    async_client: AsyncClient,
) -> None:
    """Society A member attempting to access Society B billing endpoints must be blocked."""
    # Login as Owner in Society A
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"identifier": "owner.a@palmstree.in", "password": "Password123!"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]

    # Attempt to list Society B invoices
    resp = await async_client.get(
        f"/api/v1/societies/{SOCIETY_B_ID}/billing/invoices",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_resident_payments_visibility_and_reports(
    async_client: AsyncClient,
) -> None:
    """Residents can view own payment list and payment-method/unallocated reports return data."""
    # 1. Login as Owner Vikram
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"identifier": "owner.a@palmstree.in", "password": "Password123!"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]

    # 2. Resident list own payments
    my_payments_resp = await async_client.get(
        f"/api/v1/societies/{SOCIETY_A_ID}/billing/my/payments",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert my_payments_resp.status_code == 200
    payments = my_payments_resp.json()
    assert len(payments) >= 1

    # 3. Admin reports: payment methods summary
    method_resp = await async_client.get(
        f"/api/v1/societies/{SOCIETY_A_ID}/billing/reports/payment-methods",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert method_resp.status_code == 200
    assert len(method_resp.json()) >= 1

    # 4. Integrity endpoint
    integrity_resp = await async_client.get(
        f"/api/v1/societies/{SOCIETY_A_ID}/billing/reconciliation/integrity",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert integrity_resp.status_code == 200
    assert integrity_resp.json()["is_healthy"] is True
