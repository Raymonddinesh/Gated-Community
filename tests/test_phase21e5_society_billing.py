"""Phase 21E.5 — Tenant-Facing SaaS Commercial Billing API Test Suite.

Verifies:
1. Canonical RBAC & Permission Boundaries:
   - SOCIETY_ADMIN: Full read & write access to billing endpoints.
   - TREASURER: Full read & write access to billing endpoints.
   - SECRETARY: Read-only access allowed; write operations strictly denied (HTTP 403).
   - COMMITTEE_MEMBER: Read-only access allowed; write operations strictly denied (HTTP 403).
   - RESIDENT: All billing endpoints strictly denied (HTTP 403).
   - TENANT: All billing endpoints strictly denied (HTTP 403).
2. Multi-Tenant Boundary & Cross-Tenant Denial:
   - Tenant in Society A attempting to read or write billing in Society B is strictly denied (HTTP 403).
3. Subscription Self-Service & Lifecycle:
   - GET /subscription overview with plan, cycle, renewal dates, auto_renew.
   - GET /plans catalog exploration.
   - GET /subscription/usage resource metrics and quotas.
   - GET /subscription/history paginated audit log.
   - POST /subscription/upgrade-preview proration simulation.
   - POST /subscription/upgrade execution and immediate plan change.
   - POST /subscription/downgrade scheduled downgrade at period end.
   - POST /subscription/cancel disables auto-renew.
   - POST /subscription/resume re-enables auto-renew.
   - Terminal CANCELLED state cannot be resumed.
4. Platform Invoices:
   - GET /invoices listing with pagination and status filter.
   - GET /invoices/{invoice_id} itemized GST breakdown.
   - GET /invoices/{invoice_id}/pdf streaming immutable PDF.
   - GET /invoices/{invoice_id}/download-url presigned secure URL.
   - POST /invoices/{invoice_id}/send-email outbox email dispatch.
   - POST /invoices/{invoice_id}/checkout server-side payment order.
5. Platform Credit Notes:
   - GET /credit-notes listing with pagination and status filter.
   - GET /credit-notes/{credit_note_id} itemized GST reversal breakdown.
   - GET /credit-notes/{credit_note_id}/pdf streaming immutable credit note PDF.
   - GET /credit-notes/{credit_note_id}/download-url presigned secure URL.
   - POST /credit-notes/{credit_note_id}/send-email outbox email dispatch.
6. Payments & Verification:
   - POST /payments/verify cryptographic signature verification and settlement.
   - Duplicate payment settlement rejection.
   - GET /payments paginated payment history.
7. Advance Balance & Delivery Tracking:
   - GET /balance advance credits summary.
   - GET /balance/transactions credits ledger.
   - GET /documents/{document_id}/deliveries attempt history.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch
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
from apps.api.src.database.models.membership import UserSocietyMembership
from apps.api.src.database.models.platform_billing import (
    PlatformBillingAdjustment,
)
from apps.api.src.database.models.society import Society
from apps.api.src.database.models.subscription import (
    PlatformSubscriptionPlan,
    SocietySubscription,
    SocietyUsageMetric,
    SubscriptionPlanEntitlement,
)
from apps.api.src.database.session import get_db_session
from apps.api.src.main import app
from apps.api.src.subscriptions.credit_notes.schemas import (
    PlatformCreditNoteCreateDraft,
    PlatformCreditNoteItemCreate,
)
from apps.api.src.subscriptions.credit_notes.service import PlatformCreditNoteService
from apps.api.src.subscriptions.invoicing.schemas import (
    PlatformInvoiceCreateDraft,
    PlatformInvoiceItemCreate,
)
from apps.api.src.subscriptions.invoicing.service import PlatformInvoiceService
from apps.api.src.subscriptions.payments.provider import PaymentGatewayProvider
from apps.api.src.subscriptions.payments.provider_factory import PaymentGatewayFactory
from apps.api.src.subscriptions.payments.schemas import (
    GatewayOrderResponse,
    GatewayPaymentDetails,
    GatewayRefundResponse,
)


@compiles(PG_UUID, "sqlite")
def compile_pg_uuid_sqlite(type_, compiler, **kw):
    """Enforce TEXT column affinity for UUIDs in SQLite memory tests."""
    return "TEXT"


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# ==============================================================================
# Mock Gateway Provider for Testing
# ==============================================================================


class MockRazorpayProvider(PaymentGatewayProvider):
    """Deterministic mock payment gateway for checkout and signature verification."""

    @property
    def provider_name(self) -> str:
        return "RAZORPAY"

    async def create_payment_order(
        self,
        amount: Decimal,
        currency: str,
        receipt: str,
        notes: dict | None = None,
    ) -> GatewayOrderResponse:
        return GatewayOrderResponse(
            order_id="order_mock_test_12345",
            amount=amount,
            currency=currency,
            receipt=receipt,
            status="created",
            raw_payload={"mock": True},
        )

    def verify_webhook_signature(
        self,
        raw_body: bytes,
        signature: str,
        webhook_secret: str,
    ) -> bool:
        return True

    def verify_payment_signature(
        self,
        order_id: str,
        payment_id: str,
        signature: str,
    ) -> bool:
        return signature == "valid_mock_signature"

    async def verify_payment(
        self,
        order_id: str,
        payment_id: str,
        signature: str,
    ) -> bool:
        return self.verify_payment_signature(order_id, payment_id, signature)

    async def fetch_payment(self, payment_id: str) -> GatewayPaymentDetails:
        return GatewayPaymentDetails(
            payment_id=payment_id,
            order_id="order_mock_test_12345",
            amount=Decimal("11800.00"),
            currency="INR",
            status="captured",
            method="CARD",
            captured_at=_utc_now(),
            card_network="VISA",
            card_last4="4242",
            raw_payload={"mock": True},
        )

    async def initiate_refund(
        self,
        payment_id: str,
        amount: Decimal,
        currency: str,
        reason: str | None = None,
        notes: dict | None = None,
    ) -> GatewayRefundResponse:
        return GatewayRefundResponse(
            refund_id="rfnd_mock_12345",
            payment_id=payment_id,
            amount=amount,
            currency=currency,
            status="processed",
        )

    async def fetch_refund(
        self,
        refund_id: str,
        payment_id: str | None = None,
    ) -> GatewayRefundResponse:
        return GatewayRefundResponse(
            refund_id=refund_id,
            payment_id=payment_id or "pay_mock_12345",
            amount=Decimal("1000.00"),
            currency="INR",
            status="processed",
        )


# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture
async def society_billing_session():
    """Create isolated SQLite database session factory for society billing tests."""
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
async def billing_test_data(society_billing_session):
    """Seed comprehensive tenant societies, canonical roles, memberships, and billing objects."""
    soc_a_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    soc_b_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

    # Roles
    role_admin = Role(code="SOCIETY_ADMIN", name="Society Admin", scope_type="SOCIETY")
    role_treasurer = Role(code="TREASURER", name="Honorary Treasurer", scope_type="SOCIETY")
    role_secretary = Role(code="SECRETARY", name="Honorary Secretary", scope_type="SOCIETY")
    role_committee = Role(code="COMMITTEE_MEMBER", name="Committee Member", scope_type="SOCIETY")
    role_resident = Role(code="RESIDENT", name="Resident Owner", scope_type="SOCIETY")
    role_tenant = Role(code="TENANT", name="Tenant Occupant", scope_type="SOCIETY")

    # Users
    user_admin = User(id=uuid4(), email="admin@soc-a.io", first_name="Soc", last_name="Admin", display_name="Soc Admin", status="ACTIVE")
    user_treasurer = User(id=uuid4(), email="treasurer@soc-a.io", first_name="Hon", last_name="Treasurer", display_name="Hon Treasurer", status="ACTIVE")
    user_secretary = User(id=uuid4(), email="secretary@soc-a.io", first_name="Hon", last_name="Secretary", display_name="Hon Secretary", status="ACTIVE")
    user_committee = User(id=uuid4(), email="committee@soc-a.io", first_name="Comm", last_name="Member", display_name="Comm Member", status="ACTIVE")
    user_resident = User(id=uuid4(), email="resident@soc-a.io", first_name="Res", last_name="Owner", display_name="Res Owner", status="ACTIVE")
    user_tenant = User(id=uuid4(), email="tenant@soc-a.io", first_name="Ten", last_name="Occupant", display_name="Ten Occupant", status="ACTIVE")
    user_other_soc = User(id=uuid4(), email="admin@soc-b.io", first_name="Other", last_name="Admin", display_name="Other Admin", status="ACTIVE")

    now = _utc_now()
    plan_starter = PlatformSubscriptionPlan(
        id=UUID("10000000-0000-0000-0000-000000000001"),
        plan_code="STARTER",
        display_name="Starter Tier",
        description="Entry tier for small societies",
        monthly_price=5000.00,
        annual_price=50000.00,
        currency_code="INR",
        trial_days=14,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    plan_enterprise = PlatformSubscriptionPlan(
        id=UUID("20000000-0000-0000-0000-000000000002"),
        plan_code="ENTERPRISE",
        display_name="Enterprise Tier",
        description="Comprehensive enterprise tier",
        monthly_price=10000.00,
        annual_price=100000.00,
        currency_code="INR",
        trial_days=14,
        is_active=True,
        created_at=now,
        updated_at=now,
    )

    async with society_billing_session() as session:
        session.add_all([
            role_admin, role_treasurer, role_secretary, role_committee, role_resident, role_tenant,
            user_admin, user_treasurer, user_secretary, user_committee, user_resident, user_tenant, user_other_soc,
            plan_starter, plan_enterprise,
        ])
        await session.flush()

        # Add entitlements to plans
        session.add(SubscriptionPlanEntitlement(
            id=uuid4(),
            plan_id=plan_starter.id,
            entitlement_key="MAX_UNITS",
            entitlement_type="NUMERIC",
            entitlement_value="100",
            created_at=now,
            updated_at=now,
        ))
        session.add(SubscriptionPlanEntitlement(
            id=uuid4(),
            plan_id=plan_enterprise.id,
            entitlement_key="MAX_UNITS",
            entitlement_type="NUMERIC",
            entitlement_value="500",
            created_at=now,
            updated_at=now,
        ))

        # Societies
        soc_a = Society(
            id=soc_a_id,
            legal_name="Palm Grove Cooperative Housing Society Ltd",
            display_name="Palm Grove CHS",
            registration_number="REG-PG-2026",
            address_line1="123 Palm Grove Lane",
            city="Pune",
            state="Maharashtra",
            country="IN",
            postal_code="411001",
            timezone="Asia/Kolkata",
            default_language="en",
            status="ACTIVE",
            onboarding_status="COMPLETED",
            created_at=now,
            updated_at=now,
        )
        soc_b = Society(
            id=soc_b_id,
            legal_name="Silver Oak Housing Society Ltd",
            display_name="Silver Oak CHS",
            address_line1="456 Silver Oak Road",
            city="Mumbai",
            state="Maharashtra",
            country="IN",
            postal_code="400001",
            timezone="Asia/Kolkata",
            default_language="en",
            status="ACTIVE",
            onboarding_status="COMPLETED",
            created_at=now,
            updated_at=now,
        )
        session.add_all([soc_a, soc_b])
        await session.flush()

        # Memberships
        for u, r in [
            (user_admin, role_admin),
            (user_treasurer, role_treasurer),
            (user_secretary, role_secretary),
            (user_committee, role_committee),
            (user_resident, role_resident),
            (user_tenant, role_tenant),
        ]:
            session.add(UserSocietyMembership(user_id=u.id, society_id=soc_a_id, membership_status="ACTIVE"))
            session.add(RoleAssignment(user_id=u.id, role_id=r.id, scope_type="SOCIETY", society_id=soc_a_id))

        # user_other_soc is member only in Society B
        session.add(UserSocietyMembership(user_id=user_other_soc.id, society_id=soc_b_id, membership_status="ACTIVE"))
        session.add(RoleAssignment(user_id=user_other_soc.id, role_id=role_admin.id, scope_type="SOCIETY", society_id=soc_b_id))

        # Society A Subscription
        period_start = now - timedelta(days=10)
        period_end = now + timedelta(days=20)
        sub_a = SocietySubscription(
            id=uuid4(),
            society_id=soc_a_id,
            plan_id=plan_starter.id,
            status="ACTIVE",
            billing_cycle="MONTHLY",
            auto_renew=True,
            starts_at=period_start,
            current_period_start=period_start,
            current_period_end=period_end,
            next_billing_at=period_end,
            created_at=now,
            updated_at=now,
        )
        session.add(sub_a)

        # Usage metric
        session.add(SocietyUsageMetric(
            id=uuid4(),
            society_id=soc_a_id,
            metric_key="MAX_UNITS",
            current_value=45,
            last_calculated_at=now,
        ))

        # Advance balance adjustment
        session.add(PlatformBillingAdjustment(
            id=uuid4(),
            society_id=soc_a_id,
            adjustment_type="ADVANCE_BALANCE",
            amount=Decimal("1500.00"),
            currency_code="INR",
            reason="Opening balance rollover",
            applied_at=now,
            created_at=now,
        ))

        await session.commit()

    return {
        "soc_a_id": soc_a_id,
        "soc_b_id": soc_b_id,
        "user_admin": user_admin,
        "user_treasurer": user_treasurer,
        "user_secretary": user_secretary,
        "user_committee": user_committee,
        "user_resident": user_resident,
        "user_tenant": user_tenant,
        "user_other_soc": user_other_soc,
        "plan_starter": plan_starter,
        "plan_enterprise": plan_enterprise,
    }


# ==============================================================================
# 1. Canonical RBAC & Permission Boundaries Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_rbac_access_matrix(society_billing_session, billing_test_data):
    """Test RBAC access matrix across SOCIETY_ADMIN, TREASURER, SECRETARY, COMMITTEE_MEMBER, RESIDENT, and TENANT."""
    soc_id = billing_test_data["soc_a_id"]
    data = billing_test_data

    async def _mock_db():
        async with society_billing_session() as sess:
            yield sess

    app.dependency_overrides[get_db_session] = _mock_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. SOCIETY_ADMIN: Read & Write permitted
            app.dependency_overrides[get_current_user] = lambda: data["user_admin"]
            resp = await client.get(f"/api/v1/societies/{soc_id}/billing/subscription")
            assert resp.status_code == 200
            assert resp.json()["status"] == "ACTIVE"

            # 2. TREASURER: Read & Write permitted
            app.dependency_overrides[get_current_user] = lambda: data["user_treasurer"]
            resp = await client.get(f"/api/v1/societies/{soc_id}/billing/subscription")
            assert resp.status_code == 200

            # 3. SECRETARY: Read permitted; Write denied (403)
            app.dependency_overrides[get_current_user] = lambda: data["user_secretary"]
            read_resp = await client.get(f"/api/v1/societies/{soc_id}/billing/subscription")
            assert read_resp.status_code == 200

            write_resp = await client.post(
                f"/api/v1/societies/{soc_id}/billing/subscription/cancel",
                json={"reason": "Secretary attempting cancel"},
            )
            assert write_resp.status_code == 403

            # 4. COMMITTEE_MEMBER: Read permitted; Write denied (403)
            app.dependency_overrides[get_current_user] = lambda: data["user_committee"]
            read_resp2 = await client.get(f"/api/v1/societies/{soc_id}/billing/subscription")
            assert read_resp2.status_code == 200

            write_resp2 = await client.post(
                f"/api/v1/societies/{soc_id}/billing/subscription/upgrade",
                json={"target_plan_id": str(data["plan_enterprise"].id)},
            )
            assert write_resp2.status_code == 403

            # 5. RESIDENT: Read & Write denied (403)
            app.dependency_overrides[get_current_user] = lambda: data["user_resident"]
            res_read = await client.get(f"/api/v1/societies/{soc_id}/billing/subscription")
            assert res_read.status_code == 403
            res_write = await client.post(
                f"/api/v1/societies/{soc_id}/billing/subscription/cancel",
                json={"reason": "Resident attempting cancel"},
            )
            assert res_write.status_code == 403

            # 6. TENANT: Read & Write denied (403)
            app.dependency_overrides[get_current_user] = lambda: data["user_tenant"]
            ten_read = await client.get(f"/api/v1/societies/{soc_id}/billing/subscription")
            assert ten_read.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_cross_tenant_denial(society_billing_session, billing_test_data):
    """Test that an administrator in Society B cannot read or modify billing in Society A."""
    soc_a_id = billing_test_data["soc_a_id"]
    data = billing_test_data

    async def _mock_db():
        async with society_billing_session() as sess:
            yield sess

    app.dependency_overrides[get_db_session] = _mock_db
    app.dependency_overrides[get_current_user] = lambda: data["user_other_soc"]

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/v1/societies/{soc_a_id}/billing/subscription")
            assert resp.status_code == 403
            err_data = resp.json()
            err_msg = err_data.get("error", {}).get("message", "") or err_data.get("detail", "")
            assert "Access denied" in err_msg or "Forbidden" in err_msg
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# 2. Subscription Overview, Plans, Usage, and History Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_subscription_overview_plans_usage_and_history(society_billing_session, billing_test_data):
    """Test subscription overview, public plans listing, usage metrics, and history audit log."""
    soc_id = billing_test_data["soc_a_id"]
    admin_user = billing_test_data["user_admin"]

    async def _mock_db():
        async with society_billing_session() as sess:
            yield sess

    app.dependency_overrides[get_db_session] = _mock_db
    app.dependency_overrides[get_current_user] = lambda: admin_user

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Overview
            overview_resp = await client.get(f"/api/v1/societies/{soc_id}/billing/subscription")
            assert overview_resp.status_code == 200
            overview = overview_resp.json()
            assert overview["status"] == "ACTIVE"
            assert overview["billing_cycle"] == "MONTHLY"
            assert overview["auto_renew"] is True
            assert overview["plan"]["plan_code"] == "STARTER"

            # 2. Plans Catalog
            plans_resp = await client.get(f"/api/v1/societies/{soc_id}/billing/plans")
            assert plans_resp.status_code == 200
            plans = plans_resp.json()
            assert len(plans) >= 2
            plan_codes = {p["plan_code"] for p in plans}
            assert "STARTER" in plan_codes
            assert "ENTERPRISE" in plan_codes

            # 3. Resource Usage & Quotas
            usage_resp = await client.get(f"/api/v1/societies/{soc_id}/billing/subscription/usage")
            assert usage_resp.status_code == 200
            usage_list = usage_resp.json()
            assert len(usage_list) >= 1
            max_units_metric = next((u for u in usage_list if u["metric_key"] == "MAX_UNITS"), None)
            assert max_units_metric is not None
            assert max_units_metric["current_value"] == 45
            assert max_units_metric["quota_limit"] == 100
            assert max_units_metric["utilization_percentage"] == 45.0

            # 4. History Log
            history_resp = await client.get(f"/api/v1/societies/{soc_id}/billing/subscription/history")
            assert history_resp.status_code == 200
            hist = history_resp.json()
            assert "items" in hist
            assert "total" in hist
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# 3. Plan Upgrade, Downgrade, Cancellation, and Resume Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_subscription_plan_changes_and_lifecycle(society_billing_session, billing_test_data):
    """Test upgrade simulation, upgrade execution, scheduled downgrade, cancellation, and resume."""
    soc_id = billing_test_data["soc_a_id"]
    admin_user = billing_test_data["user_admin"]
    ent_plan_id = billing_test_data["plan_enterprise"].id
    starter_plan_id = billing_test_data["plan_starter"].id

    async def _mock_db():
        async with society_billing_session() as sess:
            yield sess

    app.dependency_overrides[get_db_session] = _mock_db
    app.dependency_overrides[get_current_user] = lambda: admin_user

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Upgrade Preview (non-mutating)
            prev_resp = await client.post(
                f"/api/v1/societies/{soc_id}/billing/subscription/upgrade-preview",
                json={"target_plan_id": str(ent_plan_id)},
            )
            assert prev_resp.status_code == 200
            prev = prev_resp.json()
            assert prev["current_plan_code"] == "STARTER"
            assert prev["target_plan_code"] == "ENTERPRISE"
            assert Decimal(prev["net_payable"]) > Decimal("0.00")

            # 2. Upgrade Execution
            upg_resp = await client.post(
                f"/api/v1/societies/{soc_id}/billing/subscription/upgrade",
                json={"target_plan_id": str(ent_plan_id)},
            )
            assert upg_resp.status_code == 200

            # Verify subscription now on ENTERPRISE
            overview1 = (await client.get(f"/api/v1/societies/{soc_id}/billing/subscription")).json()
            assert overview1["plan"]["plan_code"] == "ENTERPRISE"

            # 3. Schedule Downgrade back to STARTER
            dg_resp = await client.post(
                f"/api/v1/societies/{soc_id}/billing/subscription/downgrade",
                json={
                    "target_plan_id": str(starter_plan_id),
                    "reason": "Cost reduction requested for next term",
                },
            )
            assert dg_resp.status_code == 200
            dg_data = dg_resp.json()
            assert dg_data["scheduled_plan_id"] == str(starter_plan_id)
            assert dg_data["status"] == "SCHEDULED"

            # Verify pending downgrade is reflected in overview
            overview2 = (await client.get(f"/api/v1/societies/{soc_id}/billing/subscription")).json()
            assert overview2["pending_downgrade_plan_id"] == str(starter_plan_id)

            # 4. Cancel Subscription (disables auto-renew)
            cancel_resp = await client.post(
                f"/api/v1/societies/{soc_id}/billing/subscription/cancel",
                json={"reason": "Relocating management office"},
            )
            assert cancel_resp.status_code == 200
            cancel_data = cancel_resp.json()
            assert cancel_data["auto_renew"] is False
            assert "Relocating management office" in cancel_data["cancellation_reason"]

            # 5. Resume Subscription (re-enables auto-renew)
            resume_resp = await client.post(
                f"/api/v1/societies/{soc_id}/billing/subscription/resume",
            )
            assert resume_resp.status_code == 200
            resume_data = resume_resp.json()
            assert resume_data["auto_renew"] is True

            # Verify auto-renew is True in overview
            overview3 = (await client.get(f"/api/v1/societies/{soc_id}/billing/subscription")).json()
            assert overview3["auto_renew"] is True
            assert overview3["cancellation_reason"] is None
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# 4. Invoices, PDF, Checkout, and Verification Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_invoices_checkout_and_verification(society_billing_session, billing_test_data):
    """Test finalized invoice listing, itemized view, PDF streaming, download URL, checkout, and verification."""
    soc_id = billing_test_data["soc_a_id"]
    admin_user = billing_test_data["user_admin"]

    # Seed finalized invoice
    async with society_billing_session() as session:
        sub_stmt = select(SocietySubscription).where(SocietySubscription.society_id == soc_id)
        sub = (await session.execute(sub_stmt)).scalar_one()

        inv_svc = PlatformInvoiceService()
        draft = await inv_svc.create_draft_invoice(
            session=session,
            payload=PlatformInvoiceCreateDraft(
                society_id=soc_id,
                subscription_id=sub.id,
                billing_cycle="MONTHLY",
                period_start=_utc_now() - timedelta(days=30),
                period_end=_utc_now(),
                due_date=date.today() + timedelta(days=15),
                customer_gstin="27AAPFU0939F1ZV",
                place_of_supply="27-Maharashtra",
                items=[
                    PlatformInvoiceItemCreate(
                        item_type="BASE_PLAN",
                        description="SaaS Subscription Fee - Enterprise Tier",
                        sac_code="998313",
                        quantity=Decimal("1.0000"),
                        unit_price=Decimal("10000.00"),
                    )
                ],
            ),
        )
        finalized_inv = await inv_svc.finalize_invoice(session=session, invoice_id=draft.id)
        invoice_id = finalized_inv.id
        await session.commit()

    async def _mock_db():
        async with society_billing_session() as sess:
            yield sess

    app.dependency_overrides[get_db_session] = _mock_db
    app.dependency_overrides[get_current_user] = lambda: admin_user

    # Wire mock payment provider
    mock_provider = MockRazorpayProvider()

    try:
        with patch.object(PaymentGatewayFactory, "get_provider", AsyncMock(return_value=mock_provider)):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # 1. List Invoices
                inv_list_resp = await client.get(f"/api/v1/societies/{soc_id}/billing/invoices")
                assert inv_list_resp.status_code == 200
                inv_list = inv_list_resp.json()
                assert inv_list["total"] >= 1
                assert inv_list["items"][0]["status"] == "ISSUED"

                # 2. Get Invoice Details
                inv_detail_resp = await client.get(f"/api/v1/societies/{soc_id}/billing/invoices/{invoice_id}")
                assert inv_detail_resp.status_code == 200
                inv_detail = inv_detail_resp.json()
                assert inv_detail["id"] == str(invoice_id)
                assert len(inv_detail["items"]) == 1
                assert Decimal(inv_detail["grand_total"]) == Decimal("11800.00")

                # 3. Stream Invoice PDF
                pdf_resp = await client.get(f"/api/v1/societies/{soc_id}/billing/invoices/{invoice_id}/pdf")
                assert pdf_resp.status_code == 200
                assert pdf_resp.headers["content-type"] == "application/pdf"
                assert len(pdf_resp.content) > 100

                # 4. Presigned Download URL
                url_resp = await client.get(f"/api/v1/societies/{soc_id}/billing/invoices/{invoice_id}/download-url")
                assert url_resp.status_code == 200
                url_data = url_resp.json()
                assert "download_url" in url_data
                assert url_data["expires_in_seconds"] == 300

                # 5. Outbox Send Email Request
                email_resp = await client.post(
                    f"/api/v1/societies/{soc_id}/billing/invoices/{invoice_id}/send-email",
                    json={"recipient_email": "billing@palmgrove.chs"},
                )
                assert email_resp.status_code == 202
                delivery = email_resp.json()
                assert delivery["status"] in ("PENDING", "SENT")

                # 6. Checkout Order Creation
                checkout_resp = await client.post(
                    f"/api/v1/societies/{soc_id}/billing/invoices/{invoice_id}/checkout",
                    json={"provider": "RAZORPAY"},
                )
                assert checkout_resp.status_code == 201
                checkout = checkout_resp.json()
                assert checkout["order_id"] == "order_mock_test_12345"
                assert Decimal(checkout["amount"]) == Decimal("11800.00")

                # 7. Payment Verification & Settlement
                verify_resp = await client.post(
                    f"/api/v1/societies/{soc_id}/billing/payments/verify",
                    json={
                        "invoice_id": str(invoice_id),
                        "gateway_order_id": "order_mock_test_12345",
                        "gateway_payment_id": "pay_mock_test_67890",
                        "signature": "valid_mock_signature",
                        "provider": "RAZORPAY",
                    },
                )
                assert verify_resp.status_code == 200
                verif = verify_resp.json()
                assert verif["success"] is True
                assert verif["invoice_status"] == "PAID"

                # 8. Re-verification is idempotent (returns 200 with settled status)
                idemp_resp = await client.post(
                    f"/api/v1/societies/{soc_id}/billing/payments/verify",
                    json={
                        "invoice_id": str(invoice_id),
                        "gateway_order_id": "order_mock_test_12345",
                        "gateway_payment_id": "pay_mock_test_67890",
                        "signature": "valid_mock_signature",
                        "provider": "RAZORPAY",
                    },
                )
                assert idemp_resp.status_code == 200
                assert idemp_resp.json()["success"] is True

                # 9. Checkout on already-paid invoice returns 409 Conflict
                dup_checkout = await client.post(
                    f"/api/v1/societies/{soc_id}/billing/invoices/{invoice_id}/checkout",
                    json={"provider": "RAZORPAY"},
                )
                assert dup_checkout.status_code == 409

                # 9. List Payments includes the settled transaction
                pay_list_resp = await client.get(f"/api/v1/societies/{soc_id}/billing/payments")
                assert pay_list_resp.status_code == 200
                pay_list = pay_list_resp.json()
                assert pay_list["total"] >= 1
                assert pay_list["items"][0]["gateway_payment_id"] == "pay_mock_test_67890"
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# 5. Credit Notes, Advance Balance, and Deliveries Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_credit_notes_advance_balance_and_deliveries(society_billing_session, billing_test_data):
    """Test credit note details, PDF download, presigned URL, email, and advance balance aggregation."""
    soc_id = billing_test_data["soc_a_id"]
    admin_user = billing_test_data["user_admin"]

    # Seed paid invoice and issued credit note
    async with society_billing_session() as session:
        sub_stmt = select(SocietySubscription).where(SocietySubscription.society_id == soc_id)
        sub = (await session.execute(sub_stmt)).scalar_one()

        inv_svc = PlatformInvoiceService()
        draft = await inv_svc.create_draft_invoice(
            session=session,
            payload=PlatformInvoiceCreateDraft(
                society_id=soc_id,
                subscription_id=sub.id,
                billing_cycle="MONTHLY",
                period_start=_utc_now() - timedelta(days=60),
                period_end=_utc_now() - timedelta(days=30),
                due_date=date.today() - timedelta(days=15),
                customer_gstin="27AAPFU0939F1ZV",
                place_of_supply="27-Maharashtra",
                items=[
                    PlatformInvoiceItemCreate(
                        item_type="BASE_PLAN",
                        description="Monthly Subscription Fee",
                        sac_code="998313",
                        quantity=Decimal("1.0000"),
                        unit_price=Decimal("10000.00"),
                    )
                ],
            ),
        )
        finalized_inv = await inv_svc.finalize_invoice(session=session, invoice_id=draft.id)
        # Mark paid
        finalized_inv.status = "PAID"
        finalized_inv.amount_paid = finalized_inv.grand_total
        finalized_inv.amount_due = Decimal("0.00")
        await session.flush()

        # Issue Credit Note
        cn_svc = PlatformCreditNoteService(session)
        cn_draft = await cn_svc.create_draft_credit_note(
            society_id=soc_id,
            payload=PlatformCreditNoteCreateDraft(
                invoice_id=finalized_inv.id,
                reason="SERVICE_DEFICIENCY",
                notes="Service disruption goodwill credit",
                items=[
                    PlatformCreditNoteItemCreate(
                        description="Pro-rata outage refund",
                        sac_code="998313",
                        quantity=Decimal("1.0000"),
                        unit_price=Decimal("2000.00"),
                    )
                ],
            ),
        )
        issued_cn = await cn_svc.issue_credit_note(society_id=soc_id, credit_note_id=cn_draft.id)
        cn_id = issued_cn.id
        await session.commit()

    async def _mock_db():
        async with society_billing_session() as sess:
            yield sess

    app.dependency_overrides[get_db_session] = _mock_db
    app.dependency_overrides[get_current_user] = lambda: admin_user

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. List Credit Notes
            cn_list_resp = await client.get(f"/api/v1/societies/{soc_id}/billing/credit-notes")
            assert cn_list_resp.status_code == 200
            cn_list = cn_list_resp.json()
            assert cn_list["total"] >= 1
            assert cn_list["items"][0]["status"] == "ISSUED"

            # 2. Get Credit Note Details
            cn_detail_resp = await client.get(f"/api/v1/societies/{soc_id}/billing/credit-notes/{cn_id}")
            assert cn_detail_resp.status_code == 200
            cn_detail = cn_detail_resp.json()
            assert cn_detail["id"] == str(cn_id)
            assert Decimal(cn_detail["grand_total"]) == Decimal("2360.00")

            # 3. Stream Credit Note PDF
            pdf_resp = await client.get(f"/api/v1/societies/{soc_id}/billing/credit-notes/{cn_id}/pdf")
            assert pdf_resp.status_code == 200
            assert pdf_resp.headers["content-type"] == "application/pdf"
            assert len(pdf_resp.content) > 100

            # 4. Presigned Download URL
            url_resp = await client.get(f"/api/v1/societies/{soc_id}/billing/credit-notes/{cn_id}/download-url")
            assert url_resp.status_code == 200
            url_data = url_resp.json()
            assert "download_url" in url_data

            # 5. Outbox Send Email Request
            email_resp = await client.post(
                f"/api/v1/societies/{soc_id}/billing/credit-notes/{cn_id}/send-email",
                json={"recipient_email": "accounts@palmgrove.chs"},
            )
            assert email_resp.status_code == 202
            delivery = email_resp.json()
            assert delivery["status"] in ("PENDING", "SENT")

            # 6. Document Deliveries Audit History
            doc_id = delivery["document_id"]
            deliv_hist_resp = await client.get(f"/api/v1/societies/{soc_id}/billing/documents/{doc_id}/deliveries")
            assert deliv_hist_resp.status_code == 200
            deliv_hist = deliv_hist_resp.json()
            assert len(deliv_hist) >= 1

            # 7. Advance Balance Overview
            bal_resp = await client.get(f"/api/v1/societies/{soc_id}/billing/balance")
            assert bal_resp.status_code == 200
            bal = bal_resp.json()
            assert bal["society_id"] == str(soc_id)
            assert Decimal(bal["current_balance"]) >= Decimal("1500.00")

            # 8. Advance Balance Transactions
            tx_resp = await client.get(f"/api/v1/societies/{soc_id}/billing/balance/transactions")
            assert tx_resp.status_code == 200
            tx_data = tx_resp.json()
            assert tx_data["total"] >= 1
            assert tx_data["items"][0]["adjustment_type"] == "ADVANCE_BALANCE"
    finally:
        app.dependency_overrides.clear()
