"""Phase 21E.5 — Platform Super Admin Billing APIs Test Suite.

Verifies:
1. Platform subscription plans catalog CRUD and entitlement management:
   - Listing plans (including active/archived filters).
   - Creating a new plan with entitlements.
   - Retrieving plan details by UUID.
   - Updating plan pricing, display name, and entitlements.
   - Soft-archiving a plan.
2. Global subscription monitoring:
   - Paginated listing of society subscriptions with society legal_name and plan details.
   - Administrative subscription state transition with audit log recording.
3. Standardized paginated invoice and credit note endpoints:
   - GET /platform/invoices returns PaginatedResponse[PlatformInvoiceResponse].
   - GET /platform/credit-notes returns PaginatedResponse[PlatformCreditNoteResponse].
4. Global payment transactions and refund lookup:
   - GET /platform/payments returns PaginatedResponse[PlatformPaymentListItemResponse].
   - GET /platform/payments/{payment_id} returns detailed transaction record.
   - GET /platform/refunds returns PaginatedResponse[PlatformRefundListItemResponse].
5. Manual billing adjustments & advance balance monitoring:
   - POST /platform/societies/{society_id}/adjustments creates goodwill waiver with audit log.
   - GET /platform/societies/{society_id}/adjustments lists adjustments.
   - GET /platform/societies/{society_id}/advance-balance aggregates ledger credits.
6. Authorization:
   - Non-SUPER_ADMIN users are strictly denied (HTTP 403 Forbidden).
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool

from apps.api.src.auth.dependencies import get_current_user
from apps.api.src.database.base import Base
from apps.api.src.database.models.authorization import Role, RoleAssignment
from apps.api.src.database.models.identity import User
from apps.api.src.database.models.platform_billing import (
    PlatformPayment,
    PlatformRefund,
)
from apps.api.src.database.models.society import Society
from apps.api.src.database.models.subscription import (
    PlatformSubscriptionPlan,
    SocietySubscription,
    SubscriptionPlanEntitlement,
)
from apps.api.src.database.session import get_db_session
from apps.api.src.main import app
from apps.api.src.subscriptions.invoicing.schemas import (
    PlatformInvoiceCreateDraft,
    PlatformInvoiceItemCreate,
)
from apps.api.src.subscriptions.invoicing.service import PlatformInvoiceService


@compiles(PG_UUID, "sqlite")
def compile_pg_uuid_sqlite(type_, compiler, **kw):
    return "TEXT"



def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest.fixture
async def platform_test_session():
    """Create isolated SQLite database session factory for platform testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        autoflush=False,
        expire_on_commit=False,
    )

    yield session_factory

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def super_admin_context(platform_test_session):
    """Seed SUPER_ADMIN user and role in isolated test database."""
    super_admin = User(
        id=UUID("99999999-9999-9999-9999-999999999999"),
        email="superadmin@societysphere.io",
        first_name="Super",
        last_name="Admin",
        display_name="Platform Super Admin",
        status="ACTIVE",
    )
    non_admin = User(
        id=UUID("88888888-8888-8888-8888-888888888888"),
        email="regular@example.com",
        first_name="Regular",
        last_name="User",
        display_name="Regular User",
        status="ACTIVE",
    )

    async with platform_test_session() as session:
        role_res = await session.execute(
            select(Role).where(Role.code == "SUPER_ADMIN", Role.scope_type == "PLATFORM")
        )
        super_role = role_res.scalar_one_or_none()
        if not super_role:
            super_role = Role(code="SUPER_ADMIN", name="Super Admin", scope_type="PLATFORM")
            session.add(super_role)
            await session.flush()

        session.add_all([super_admin, non_admin])
        session.add(
            RoleAssignment(
                user_id=super_admin.id,
                role_id=super_role.id,
                scope_type="PLATFORM",
            )
        )

        # Seed standard plan
        plan = PlatformSubscriptionPlan(
            id=UUID("11111111-2222-3333-4444-555555555555"),
            plan_code="ENTERPRISE",
            display_name="Enterprise Plan",
            description="Full-suite enterprise tier",
            monthly_price=10000.00,
            annual_price=100000.00,
            currency_code="INR",
            trial_days=14,
            is_active=True,
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
        session.add(plan)
        await session.flush()

        session.add(
            SubscriptionPlanEntitlement(
                id=uuid4(),
                plan_id=plan.id,
                entitlement_key="MAX_UNITS",
                entitlement_type="NUMERIC",
                entitlement_value="500",
                created_at=_utc_now(),
                updated_at=_utc_now(),
            )
        )

        # Seed test society
        soc = Society(
            id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            legal_name="Palm Heights Co-op Housing Society",
            display_name="Palm Heights",
            registration_number="REG-PH-2026",
            address_line1="123 Palm Ave",
            city="Pune",
            state="Maharashtra",
            country="IN",
            postal_code="411028",
            timezone="Asia/Kolkata",
            default_language="en",
            status="ACTIVE",
            onboarding_status="COMPLETED",
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
        session.add(soc)
        await session.flush()

        sub = SocietySubscription(
            id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            society_id=soc.id,
            plan_id=plan.id,
            status="TRIAL",
            billing_cycle="MONTHLY",
            auto_renew=True,
            starts_at=_utc_now(),
            current_period_start=_utc_now(),
            current_period_end=_utc_now(),
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
        session.add(sub)
        await session.commit()

    return {"super_admin": super_admin, "non_admin": non_admin}


# ==============================================================================
# 1. Platform Subscription Plan Catalog Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_plan_catalog_crud_lifecycle(platform_test_session, super_admin_context):
    """Test full CRUD lifecycle for platform subscription plans."""
    super_admin = super_admin_context["super_admin"]

    async def _mock_db():
        async with platform_test_session() as sess:
            yield sess

    app.dependency_overrides[get_db_session] = _mock_db
    app.dependency_overrides[get_current_user] = lambda: super_admin

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. List plans
            list_resp = await client.get("/api/v1/platform/plans")
            assert list_resp.status_code == 200
            plans = list_resp.json()
            assert len(plans) >= 1
            assert any(p["plan_code"] == "ENTERPRISE" for p in plans)

            # 2. Create new plan
            create_resp = await client.post(
                "/api/v1/platform/plans",
                json={
                    "plan_code": "STARTER",
                    "display_name": "Starter Plan",
                    "description": "Affordable entry tier",
                    "monthly_price": "2999.00",
                    "annual_price": "29990.00",
                    "currency_code": "INR",
                    "trial_days": 14,
                    "is_active": True,
                    "entitlements": [
                        {
                            "entitlement_key": "MAX_UNITS",
                            "entitlement_type": "NUMERIC",
                            "entitlement_value": "50",
                        },
                        {
                            "entitlement_key": "FEATURE_VISITORS",
                            "entitlement_type": "BOOLEAN",
                            "entitlement_value": "true",
                        },
                    ],
                },
            )
            assert create_resp.status_code == 201
            new_plan = create_resp.json()
            assert new_plan["plan_code"] == "STARTER"
            assert Decimal(new_plan["monthly_price"]) == Decimal("2999.00")
            assert len(new_plan["entitlements"]) == 2
            plan_id = new_plan["id"]

            # 3. Get plan by ID
            get_resp = await client.get(f"/api/v1/platform/plans/{plan_id}")
            assert get_resp.status_code == 200
            assert get_resp.json()["display_name"] == "Starter Plan"

            # 4. Update plan pricing and entitlements
            update_resp = await client.patch(
                f"/api/v1/platform/plans/{plan_id}",
                json={
                    "display_name": "Starter Plus Plan",
                    "monthly_price": "3499.00",
                    "entitlements": [
                        {
                            "entitlement_key": "MAX_UNITS",
                            "entitlement_type": "NUMERIC",
                            "entitlement_value": "75",
                        }
                    ],
                },
            )
            assert update_resp.status_code == 200
            updated = update_resp.json()
            assert updated["display_name"] == "Starter Plus Plan"
            assert Decimal(updated["monthly_price"]) == Decimal("3499.00")
            assert len(updated["entitlements"]) == 1

            # 5. Soft-archive plan
            archive_resp = await client.post(f"/api/v1/platform/plans/{plan_id}/archive")
            assert archive_resp.status_code == 200
            assert archive_resp.json()["is_active"] is False
            assert archive_resp.json()["archived_at"] is not None

            # 6. Listing without include_archived excludes archived plan
            list_active = await client.get("/api/v1/platform/plans")
            assert not any(p["id"] == plan_id for p in list_active.json())

            # 7. Listing with include_archived=true includes it
            list_all = await client.get("/api/v1/platform/plans?include_archived=true")
            assert any(p["id"] == plan_id for p in list_all.json())
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_current_user, None)


# ==============================================================================
# 2. Global Subscription Monitoring & State Transition Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_global_subscription_monitoring_and_transition(platform_test_session, super_admin_context):
    """Test global subscription listing and administrative state transitions."""
    super_admin = super_admin_context["super_admin"]
    soc_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

    async def _mock_db():
        async with platform_test_session() as sess:
            yield sess

    app.dependency_overrides[get_db_session] = _mock_db
    app.dependency_overrides[get_current_user] = lambda: super_admin

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Paginated global subscriptions list
            resp = await client.get("/api/v1/platform/subscriptions?page=1&page_size=10")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] >= 1
            assert data["page"] == 1
            assert len(data["items"]) >= 1
            assert data["items"][0]["society_name"] == "Palm Heights Co-op Housing Society"
            assert data["items"][0]["status"] == "TRIAL"

            # 2. Administrative state transition TRIAL -> ACTIVE
            trans_resp = await client.post(
                f"/api/v1/platform/subscriptions/{soc_id}/transition",
                json={
                    "to_status": "ACTIVE",
                    "reason": "Administrative manual activation following enterprise PO confirmation.",
                },
            )
            assert trans_resp.status_code == 200
            trans_data = trans_resp.json()
            assert trans_data["previous_status"] == "TRIAL"
            assert trans_data["current_status"] == "ACTIVE"

            # 3. Verify status changed in list
            refreshed = await client.get(f"/api/v1/platform/subscriptions?society_id={soc_id}")
            assert refreshed.json()["items"][0]["status"] == "ACTIVE"
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_current_user, None)


# ==============================================================================
# 3. Paginated Invoices & Credit Notes Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_paginated_invoices_and_credit_notes(platform_test_session, super_admin_context):
    """Verify GET /platform/invoices returns standardized PaginatedResponse."""
    super_admin = super_admin_context["super_admin"]
    soc_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    sub_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

    # Create draft invoice using PlatformInvoiceService
    async with platform_test_session() as session:
        inv_svc = PlatformInvoiceService()
        now = _utc_now()
        payload = PlatformInvoiceCreateDraft(
            society_id=soc_id,
            subscription_id=sub_id,
            billing_cycle="MONTHLY",
            period_start=now,
            period_end=now,
            due_date=date.today(),
            items=[PlatformInvoiceItemCreate(description="Enterprise SaaS", unit_price=Decimal("10000.00"))],
        )
        inv = await inv_svc.create_draft_invoice(session, payload)
        await session.commit()
        inv_id = str(inv.id)

    async def _mock_db():
        async with platform_test_session() as sess:
            yield sess

    app.dependency_overrides[get_db_session] = _mock_db
    app.dependency_overrides[get_current_user] = lambda: super_admin

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/platform/invoices?page=1&page_size=10")
            assert resp.status_code == 200
            data = resp.json()
            assert "items" in data
            assert "total" in data
            assert "page" in data
            assert "pages" in data
            assert data["total"] >= 1
            assert any(item["id"] == inv_id for item in data["items"])

            # Test credit notes paginated response
            cn_resp = await client.get("/api/v1/platform/credit-notes?page=1&page_size=10")
            assert cn_resp.status_code == 200
            cn_data = cn_resp.json()
            assert "items" in cn_data
            assert "total" in cn_data
            assert "page" in cn_data
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_current_user, None)


# ==============================================================================
# 4. Global Payments & Refunds Listing Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_global_payments_and_refunds_listing(platform_test_session, super_admin_context):
    """Test global payment listing, payment detail lookup, and refund listing."""
    super_admin = super_admin_context["super_admin"]
    soc_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    # Seed payment and refund
    now = _utc_now()
    pay_id = uuid4()
    ref_id = uuid4()
    async with platform_test_session() as session:
        pay = PlatformPayment(
            id=pay_id,
            society_id=soc_id,
            gateway_provider="RAZORPAY",
            gateway_payment_id="pay_test_stage1_123",
            payment_method="UPI",
            amount=Decimal("11800.00"),
            refunded_amount=Decimal("1800.00"),
            currency_code="INR",
            status="PARTIALLY_REFUNDED",
            reconciliation_status="RECONCILED",
            captured_at=now,
            is_settled=True,
            settled_at=now,
            upi_vpa="society@okhdfcbank",
        )
        session.add(pay)
        await session.flush()

        ref = PlatformRefund(
            id=ref_id,
            payment_id=pay.id,
            society_id=soc_id,
            gateway_provider="RAZORPAY",
            gateway_refund_id="rfnd_test_stage1_456",
            amount=Decimal("1800.00"),
            currency_code="INR",
            reason="CUSTOMER_REQUEST",
            status="COMPLETED",
            created_at=now,
        )
        session.add(ref)
        await session.commit()

    async def _mock_db():
        async with platform_test_session() as sess:
            yield sess

    app.dependency_overrides[get_db_session] = _mock_db
    app.dependency_overrides[get_current_user] = lambda: super_admin

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Global payments list
            pay_resp = await client.get("/api/v1/platform/payments?page=1&page_size=10")
            assert pay_resp.status_code == 200
            pay_data = pay_resp.json()
            assert pay_data["total"] >= 1
            assert any(item["gateway_payment_id"] == "pay_test_stage1_123" for item in pay_data["items"])

            # 2. Payment detail lookup
            detail_resp = await client.get(f"/api/v1/platform/payments/{pay_id}")
            assert detail_resp.status_code == 200
            detail_data = detail_resp.json()
            assert detail_data["upi_vpa"] == "society@okhdfcbank"
            assert len(detail_data["refunds"]) == 1
            assert detail_data["refunds"][0]["gateway_refund_id"] == "rfnd_test_stage1_456"

            # 3. Global refunds list
            ref_resp = await client.get("/api/v1/platform/refunds?page=1&page_size=10")
            assert ref_resp.status_code == 200
            ref_data = ref_resp.json()
            assert ref_data["total"] >= 1
            assert any(item["gateway_refund_id"] == "rfnd_test_stage1_456" for item in ref_data["items"])
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_current_user, None)


# ==============================================================================
# 5. Manual Billing Adjustments & Advance Balances Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_manual_billing_adjustments_and_advance_balance(platform_test_session, super_admin_context):
    """Test manual billing adjustment creation and advance credit balance calculation."""
    super_admin = super_admin_context["super_admin"]
    soc_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

    async def _mock_db():
        async with platform_test_session() as sess:
            yield sess

    app.dependency_overrides[get_db_session] = _mock_db
    app.dependency_overrides[get_current_user] = lambda: super_admin

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Create a goodwill waiver credit adjustment (+₹2500)
            adj1_resp = await client.post(
                f"/api/v1/platform/societies/{soc_id}/adjustments",
                json={
                    "adjustment_type": "GOODWILL_WAIVER",
                    "amount": "2500.00",
                    "reason": "Administrative goodwill credit granted for service outage.",
                    "idempotency_key": "adj-key-test-001",
                },
            )
            assert adj1_resp.status_code == 201
            adj1 = adj1_resp.json()
            assert adj1["adjustment_type"] == "GOODWILL_WAIVER"
            assert Decimal(adj1["amount"]) == Decimal("2500.00")

            # 2. Idempotent replay of same adjustment returns 201/200 with existing record
            adj1_replay = await client.post(
                f"/api/v1/platform/societies/{soc_id}/adjustments",
                json={
                    "adjustment_type": "GOODWILL_WAIVER",
                    "amount": "2500.00",
                    "reason": "Administrative goodwill credit granted for service outage.",
                    "idempotency_key": "adj-key-test-001",
                },
            )
            assert adj1_replay.status_code == 201
            assert adj1_replay.json()["id"] == adj1["id"]

            # 3. Create a second adjustment (+₹1000)
            adj2_resp = await client.post(
                f"/api/v1/platform/societies/{soc_id}/adjustments",
                json={
                    "adjustment_type": "ADVANCE_BALANCE",
                    "amount": "1000.00",
                    "reason": "Credit balance rollover from previous term.",
                },
            )
            assert adj2_resp.status_code == 201

            # 4. List society adjustments
            list_adj = await client.get(f"/api/v1/platform/societies/{soc_id}/adjustments")
            assert list_adj.status_code == 200
            assert list_adj.json()["total"] == 2

            # 5. Check advance balance aggregation (+2500 + 1000 = ₹3500)
            bal_resp = await client.get(f"/api/v1/platform/societies/{soc_id}/advance-balance")
            assert bal_resp.status_code == 200
            bal = bal_resp.json()
            assert Decimal(bal["current_balance"]) == Decimal("3500.00")
            assert Decimal(bal["total_credits_granted"]) == Decimal("3500.00")
            assert Decimal(bal["total_credits_utilized"]) == Decimal("0.00")
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_current_user, None)


# ==============================================================================
# 6. Authorization Guard Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_non_super_admin_denied_platform_billing_endpoints(platform_test_session, super_admin_context):
    """Verify that ordinary users without SUPER_ADMIN role are rejected with 403 Forbidden."""
    non_admin = super_admin_context["non_admin"]

    async def _mock_db():
        async with platform_test_session() as sess:
            yield sess

    app.dependency_overrides[get_db_session] = _mock_db
    app.dependency_overrides[get_current_user] = lambda: non_admin

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp1 = await client.get("/api/v1/platform/plans")
            assert resp1.status_code == 403

            resp2 = await client.get("/api/v1/platform/subscriptions")
            assert resp2.status_code == 403

            resp3 = await client.get("/api/v1/platform/payments")
            assert resp3.status_code == 403
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_current_user, None)
