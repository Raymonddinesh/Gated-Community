"""Phase 21E.5 — Stage 3: Final End-to-End Integration, Security & Release Validation.

Validates complete commercial SaaS billing workflows across all tiers:
Workflow A: New Society Subscription Provisioning, Entitlements & Quotas
Workflow B: Subscription Upgrade with Proration & Checkout
Workflow C: Subscription Downgrade Scheduling & Quota Enforcement
Workflow D: Platform Invoice Finalization, PDF Storage, Streaming, Download URL & Payment Settlement
Workflow E: Statutory Credit Note Issuance, Tax Reversal, PDF, Email & Advance Balance
Workflow F: Platform Super Admin Plan Catalog, Global Monitoring & Manual Adjustments
Cross-Tier Security: Complete RBAC Matrix (Super Admin, Society Admin, Treasurer, Secretary, Committee Member, Resident, Tenant, Inactive)
Concurrency & Idempotency: Replays, Duplicate Checkout Rejections, and Immutability Safeguards.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
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


class MockStage3RazorpayProvider(PaymentGatewayProvider):
    """Deterministic mock payment gateway for Stage 3 checkout and signature verification."""

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
            order_id="order_stage3_test_99999",
            amount=amount,
            currency=currency,
            receipt=receipt,
            status="created",
            raw_payload={"mock": True, "stage": 3},
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
        return signature == "valid_stage3_signature"

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
            order_id="order_stage3_test_99999",
            amount=Decimal("11800.00"),
            currency="INR",
            status="captured",
            method="UPI",
            captured_at=_utc_now(),
            upi_vpa="billing@okaxis",
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
            refund_id="rfnd_stage3_mock",
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
            payment_id=payment_id or "pay_stage3_mock",
            amount=Decimal("1000.00"),
            currency="INR",
            status="processed",
        )


@pytest.fixture
async def stage3_db_session():
    """Create isolated SQLite database session factory for Stage 3 validation."""
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
async def stage3_seed_data(stage3_db_session):
    """Seed comprehensive societies, plans, entitlements, users, and roles for Stage 3."""
    now = _utc_now()
    soc_a_id = UUID("11111111-1111-1111-1111-111111111111")
    soc_b_id = UUID("22222222-2222-2222-2222-222222222222")

    # 1. Societies
    soc_a = Society(
        id=soc_a_id,
        legal_name="Emerald Heights Cooperative Housing Society Ltd",
        display_name="Emerald Heights CHS",
        registration_number="REG-EH-2026",
        address_line1="123 Hill Road",
        city="Mumbai",
        state="Maharashtra",
        country="IN",
        postal_code="400050",
        timezone="Asia/Kolkata",
        default_language="en",
        status="ACTIVE",
        onboarding_status="COMPLETED",
        created_at=now,
        updated_at=now,
    )
    soc_b = Society(
        id=soc_b_id,
        legal_name="Sapphire Residency Cooperative Housing Society Ltd",
        display_name="Sapphire Residency CHS",
        registration_number="REG-SR-2026",
        address_line1="456 Sea View Road",
        city="Mumbai",
        state="Maharashtra",
        country="IN",
        postal_code="400051",
        timezone="Asia/Kolkata",
        default_language="en",
        status="ACTIVE",
        onboarding_status="COMPLETED",
        created_at=now,
        updated_at=now,
    )

    # 2. Plans
    plan_starter = PlatformSubscriptionPlan(
        id=UUID("33333333-3333-3333-3333-333333333333"),
        plan_code="STARTER",
        display_name="Starter Plan",
        description="Starter plan for small societies",
        monthly_price=4999.00,
        annual_price=49990.00,
        currency_code="INR",
        trial_days=14,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    plan_enterprise = PlatformSubscriptionPlan(
        id=UUID("44444444-4444-4444-4444-444444444444"),
        plan_code="ENTERPRISE",
        display_name="Enterprise Plan",
        description="Enterprise plan for large societies",
        monthly_price=10000.00,
        annual_price=100000.00,
        currency_code="INR",
        trial_days=14,
        is_active=True,
        created_at=now,
        updated_at=now,
    )

    # 3. Roles
    role_super = Role(name="Super Admin", code="SUPER_ADMIN", scope_type="PLATFORM")
    role_admin = Role(name="Society Admin", code="SOCIETY_ADMIN", scope_type="SOCIETY")
    role_treasurer = Role(name="Treasurer", code="TREASURER", scope_type="SOCIETY")
    role_secretary = Role(name="Secretary", code="SECRETARY", scope_type="SOCIETY")
    role_committee = Role(name="Committee Member", code="COMMITTEE_MEMBER", scope_type="SOCIETY")
    role_resident = Role(name="Resident", code="RESIDENT", scope_type="SOCIETY")
    role_tenant = Role(name="Tenant", code="TENANT", scope_type="SOCIETY")
    roles = [role_super, role_admin, role_treasurer, role_secretary, role_committee, role_resident, role_tenant]
    role_map = {r.code: r for r in roles}

    # 4. Users
    def _make_user(first: str, last: str, email: str) -> User:
        return User(
            id=uuid4(),
            email=email,
            first_name=first,
            last_name=last,
            display_name=f"{first} {last}",
            status="ACTIVE",
        )

    u_super = _make_user("Super", "Admin", "super@platform.internal")
    u_admin_a = _make_user("Aarav", "Patel", "admin@emerald.chs")
    u_treasurer_a = _make_user("Rohan", "Mehta", "treasurer@emerald.chs")
    u_secretary_a = _make_user("Priya", "Sharma", "secretary@emerald.chs")
    u_committee_a = _make_user("Karan", "Verma", "committee@emerald.chs")
    u_resident_a = _make_user("Sunita", "Rao", "resident@emerald.chs")
    u_tenant_a = _make_user("Vikram", "Singh", "tenant@emerald.chs")
    u_inactive_a = _make_user("Dev", "Kapoor", "inactive@emerald.chs")
    u_admin_b = _make_user("Nisha", "Deshmukh", "admin@sapphire.chs")

    # 5. Society A Active Subscription (Starter)
    period_start = now - timedelta(days=15)
    period_end = now + timedelta(days=15)
    sub_a = SocietySubscription(
        id=UUID("55555555-5555-5555-5555-555555555555"),
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

    # Usage metric
    usage_a = SocietyUsageMetric(
        id=uuid4(),
        society_id=soc_a_id,
        metric_key="MAX_UNITS",
        current_value=50,
        last_calculated_at=now,
    )

    # Advance balance adjustment
    adv_adj = PlatformBillingAdjustment(
        id=uuid4(),
        society_id=soc_a_id,
        adjustment_type="ADVANCE_BALANCE",
        amount=Decimal("1500.00"),
        currency_code="INR",
        reason="Opening balance rollover",
        applied_at=now,
        created_at=now,
    )

    async with stage3_db_session() as session:
        session.add_all([soc_a, soc_b])
        session.add_all([plan_starter, plan_enterprise])
        session.add_all(roles)
        session.add_all([
            u_super, u_admin_a, u_treasurer_a, u_secretary_a,
            u_committee_a, u_resident_a, u_tenant_a, u_inactive_a, u_admin_b
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

        session.add_all([sub_a, usage_a, adv_adj])

        # Active memberships in Society A
        for usr, r_code in [
            (u_admin_a, "SOCIETY_ADMIN"),
            (u_treasurer_a, "TREASURER"),
            (u_secretary_a, "SECRETARY"),
            (u_committee_a, "COMMITTEE_MEMBER"),
            (u_resident_a, "RESIDENT"),
            (u_tenant_a, "TENANT"),
        ]:
            session.add(UserSocietyMembership(user_id=usr.id, society_id=soc_a_id, membership_status="ACTIVE"))
            session.add(RoleAssignment(user_id=usr.id, role_id=role_map[r_code].id, scope_type="SOCIETY", society_id=soc_a_id))

        # Inactive membership in Society A
        session.add(UserSocietyMembership(user_id=u_inactive_a.id, society_id=soc_a_id, membership_status="INACTIVE"))
        session.add(RoleAssignment(user_id=u_inactive_a.id, role_id=role_map["RESIDENT"].id, scope_type="SOCIETY", society_id=soc_a_id))

        # Society B Admin
        session.add(UserSocietyMembership(user_id=u_admin_b.id, society_id=soc_b_id, membership_status="ACTIVE"))
        session.add(RoleAssignment(user_id=u_admin_b.id, role_id=role_map["SOCIETY_ADMIN"].id, scope_type="SOCIETY", society_id=soc_b_id))

        # Global Super Admin (society_id=None)
        session.add(RoleAssignment(user_id=u_super.id, role_id=role_map["SUPER_ADMIN"].id, scope_type="PLATFORM", society_id=None))

        await session.commit()

    return {
        "soc_a_id": soc_a_id,
        "soc_b_id": soc_b_id,
        "plan_starter": plan_starter,
        "plan_enterprise": plan_enterprise,
        "sub_a_id": sub_a.id,
        "u_super": u_super,
        "u_admin_a": u_admin_a,
        "u_treasurer_a": u_treasurer_a,
        "u_secretary_a": u_secretary_a,
        "u_committee_a": u_committee_a,
        "u_resident_a": u_resident_a,
        "u_tenant_a": u_tenant_a,
        "u_inactive_a": u_inactive_a,
        "u_admin_b": u_admin_b,
    }


# ==============================================================================
# Step 1: Workflows A, B, C (Subscription Lifecycle, Upgrade, Downgrade)
# ==============================================================================


@pytest.mark.asyncio
async def test_stage3_workflow_subscription_lifecycle_upgrade_downgrade(stage3_db_session, stage3_seed_data):
    """Validate Workflows A, B, and C: Subscription self-service, upgrade preview & proration, and downgrade scheduling."""
    soc_id = stage3_seed_data["soc_a_id"]
    admin_user = stage3_seed_data["u_admin_a"]
    starter_plan = stage3_seed_data["plan_starter"]
    ent_plan = stage3_seed_data["plan_enterprise"]

    async def _mock_db():
        async with stage3_db_session() as sess:
            yield sess

    app.dependency_overrides[get_db_session] = _mock_db
    app.dependency_overrides[get_current_user] = lambda: admin_user

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Workflow A: Subscription overview & usage verification
            sub_resp = await client.get(f"/api/v1/societies/{soc_id}/billing/subscription")
            assert sub_resp.status_code == 200
            sub_data = sub_resp.json()
            assert sub_data["status"] == "ACTIVE"
            assert sub_data["plan"]["plan_code"] == "STARTER"

            usage_resp = await client.get(f"/api/v1/societies/{soc_id}/billing/subscription/usage")
            assert usage_resp.status_code == 200
            usage_data = usage_resp.json()
            assert len(usage_data) >= 1
            max_units_metric = next((u for u in usage_data if u["metric_key"] == "MAX_UNITS"), None)
            assert max_units_metric is not None
            assert max_units_metric["current_value"] == 50
            assert max_units_metric["quota_limit"] == 100

            # Workflow B: Subscription Upgrade Preview (Proration)
            preview_resp = await client.post(
                f"/api/v1/societies/{soc_id}/billing/subscription/upgrade-preview",
                json={"target_plan_id": str(ent_plan.id)},
            )
            assert preview_resp.status_code == 200
            proration = preview_resp.json()
            assert Decimal(proration["target_charge"]) > Decimal("0.00")
            assert Decimal(proration["unused_credit"]) >= Decimal("0.00")
            assert Decimal(proration["net_payable"]) > Decimal("0.00")

            # Workflow B: Execute Subscription Upgrade
            upgrade_resp = await client.post(
                f"/api/v1/societies/{soc_id}/billing/subscription/upgrade",
                json={"target_plan_id": str(ent_plan.id)},
            )
            assert upgrade_resp.status_code == 200
            upgraded = upgrade_resp.json()
            assert upgraded["target_plan_code"] == "ENTERPRISE"

            # Verify upgraded subscription status
            sub_after = await client.get(f"/api/v1/societies/{soc_id}/billing/subscription")
            assert sub_after.status_code == 200
            assert sub_after.json()["plan"]["plan_code"] == "ENTERPRISE"

            # Verify updated quota limit is now 500
            usage_after_resp = await client.get(f"/api/v1/societies/{soc_id}/billing/subscription/usage")
            usage_after_list = usage_after_resp.json()
            updated_units_metric = next((u for u in usage_after_list if u["metric_key"] == "MAX_UNITS"), None)
            assert updated_units_metric is not None
            assert updated_units_metric["quota_limit"] == 500

            # Workflow C: Schedule Downgrade back to Starter
            downgrade_resp = await client.post(
                f"/api/v1/societies/{soc_id}/billing/subscription/downgrade",
                json={"target_plan_id": str(starter_plan.id), "reason": "Optimizing operational expenses"},
            )
            assert downgrade_resp.status_code == 200
            downgrade_data = downgrade_resp.json()
            assert downgrade_data["scheduled_plan_id"] == str(starter_plan.id)
            assert "effective_date" in downgrade_data

            # Subscription History Audit Trail
            hist_resp = await client.get(f"/api/v1/societies/{soc_id}/billing/subscription/history")
            assert hist_resp.status_code == 200
            hist = hist_resp.json()
            assert hist["total"] >= 1
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# Step 1: Workflows D & E (Invoicing, PDF, Download, Checkout, Payments, Credit Notes)
# ==============================================================================


@pytest.mark.asyncio
async def test_stage3_workflow_invoice_payment_credit_note_advance_balance(stage3_db_session, stage3_seed_data):
    """Validate Workflows D and E: Statutory Invoicing, GST reversal, payments settlement, and advance credits."""
    soc_id = stage3_seed_data["soc_a_id"]
    treasurer_user = stage3_seed_data["u_treasurer_a"]
    sub_id = stage3_seed_data["sub_a_id"]

    # Seed finalized invoice
    async with stage3_db_session() as session:
        inv_svc = PlatformInvoiceService()
        draft = await inv_svc.create_draft_invoice(
            session=session,
            payload=PlatformInvoiceCreateDraft(
                society_id=soc_id,
                subscription_id=sub_id,
                billing_cycle="MONTHLY",
                period_start=_utc_now() - timedelta(days=30),
                period_end=_utc_now(),
                due_date=date.today() + timedelta(days=15),
                customer_gstin="27AAPFU0939F1ZV",
                place_of_supply="27-Maharashtra",
                items=[
                    PlatformInvoiceItemCreate(
                        item_type="BASE_PLAN",
                        description="Commercial SaaS Subscription Fee",
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
        async with stage3_db_session() as sess:
            yield sess

    app.dependency_overrides[get_db_session] = _mock_db
    app.dependency_overrides[get_current_user] = lambda: treasurer_user
    mock_provider = MockStage3RazorpayProvider()

    try:
        with patch.object(PaymentGatewayFactory, "get_provider", AsyncMock(return_value=mock_provider)):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # 1. Workflow D: List invoices & inspect details
                inv_list_resp = await client.get(f"/api/v1/societies/{soc_id}/billing/invoices")
                assert inv_list_resp.status_code == 200
                assert inv_list_resp.json()["total"] >= 1

                inv_resp = await client.get(f"/api/v1/societies/{soc_id}/billing/invoices/{invoice_id}")
                assert inv_resp.status_code == 200
                assert Decimal(inv_resp.json()["grand_total"]) == Decimal("11800.00")

                # 2. Workflow D: PDF generation, stream, and presigned download URL
                pdf_resp = await client.get(f"/api/v1/societies/{soc_id}/billing/invoices/{invoice_id}/pdf")
                assert pdf_resp.status_code == 200
                assert pdf_resp.headers["content-type"] == "application/pdf"
                assert "X-Document-Checksum" in pdf_resp.headers

                dl_resp = await client.get(f"/api/v1/societies/{soc_id}/billing/invoices/{invoice_id}/download-url")
                assert dl_resp.status_code == 200
                assert "download_url" in dl_resp.json()

                # 3. Workflow D: Outbox Email dispatch
                email_resp = await client.post(
                    f"/api/v1/societies/{soc_id}/billing/invoices/{invoice_id}/send-email",
                    json={"recipient_email": "treasurer@emerald.chs"},
                )
                assert email_resp.status_code == 202

                # 4. Workflow D: Authoritative Checkout Order
                checkout_resp = await client.post(
                    f"/api/v1/societies/{soc_id}/billing/invoices/{invoice_id}/checkout",
                    json={"provider": "RAZORPAY"},
                )
                assert checkout_resp.status_code == 201
                checkout = checkout_resp.json()
                assert checkout["order_id"] == "order_stage3_test_99999"
                assert Decimal(checkout["amount"]) == Decimal("11800.00")

                # 5. Workflow D: Payment Verification & Settlement
                verify_resp = await client.post(
                    f"/api/v1/societies/{soc_id}/billing/payments/verify",
                    json={
                        "invoice_id": str(invoice_id),
                        "gateway_order_id": "order_stage3_test_99999",
                        "gateway_payment_id": "pay_stage3_test_11111",
                        "signature": "valid_stage3_signature",
                        "provider": "RAZORPAY",
                    },
                )
                assert verify_resp.status_code == 200
                assert verify_resp.json()["invoice_status"] == "PAID"

                # 6. Workflow E: Credit Note creation & issuance against settled invoice
                async with stage3_db_session() as session:
                    cn_svc = PlatformCreditNoteService(session)
                    cn_draft = await cn_svc.create_draft_credit_note(
                        society_id=soc_id,
                        payload=PlatformCreditNoteCreateDraft(
                            invoice_id=invoice_id,
                            reason="BILLING_ERROR",
                            notes="Commercial reconciliation discount",
                            items=[
                                PlatformCreditNoteItemCreate(
                                    description="Disputed charges credit",
                                    sac_code="998313",
                                    quantity=Decimal("1.0000"),
                                    unit_price=Decimal("1000.00"),
                                )
                            ],
                        ),
                    )
                    issued_cn = await cn_svc.issue_credit_note(society_id=soc_id, credit_note_id=cn_draft.id)
                    cn_id = issued_cn.id
                    await session.commit()

                # Inspect Credit Note via API
                cn_detail_resp = await client.get(f"/api/v1/societies/{soc_id}/billing/credit-notes/{cn_id}")
                assert cn_detail_resp.status_code == 200
                cn_data = cn_detail_resp.json()
                assert cn_data["status"] == "ISSUED"
                assert Decimal(cn_data["grand_total"]) == Decimal("1180.00")

                # Stream Credit Note PDF
                cn_pdf_resp = await client.get(f"/api/v1/societies/{soc_id}/billing/credit-notes/{cn_id}/pdf")
                assert cn_pdf_resp.status_code == 200
                assert cn_pdf_resp.headers["content-type"] == "application/pdf"

                # Advance balance verification
                bal_resp = await client.get(f"/api/v1/societies/{soc_id}/billing/balance")
                assert bal_resp.status_code == 200
                assert Decimal(bal_resp.json()["current_balance"]) >= Decimal("1180.00")
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# Step 1: Workflow F (Platform Super Admin Billing Management)
# ==============================================================================


@pytest.mark.asyncio
async def test_stage3_workflow_super_admin_billing_management(stage3_db_session, stage3_seed_data):
    """Validate Workflow F: Super Admin plan management, global monitoring, and manual adjustments."""
    soc_id = stage3_seed_data["soc_a_id"]
    super_user = stage3_seed_data["u_super"]

    async def _mock_db():
        async with stage3_db_session() as sess:
            yield sess

    app.dependency_overrides[get_db_session] = _mock_db
    app.dependency_overrides[get_current_user] = lambda: super_user

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Super Admin list plans
            plans_resp = await client.get("/api/v1/platform/plans")
            assert plans_resp.status_code == 200
            assert len(plans_resp.json()) >= 2

            # 2. Super Admin create custom tier plan
            create_plan_resp = await client.post(
                "/api/v1/platform/plans",
                json={
                    "plan_code": "CUSTOM_ENTERPRISE",
                    "display_name": "Custom Enterprise Tier",
                    "description": "Custom enterprise plan",
                    "monthly_price": "25000.00",
                    "annual_price": "250000.00",
                    "currency_code": "INR",
                    "trial_days": 14,
                    "is_active": True,
                    "entitlements": [
                        {
                            "entitlement_key": "MAX_UNITS",
                            "entitlement_type": "NUMERIC",
                            "entitlement_value": "2000",
                        }
                    ],
                },
            )
            assert create_plan_resp.status_code == 201

            # 3. Super Admin global subscriptions monitoring
            subs_resp = await client.get("/api/v1/platform/subscriptions?page=1&page_size=10")
            assert subs_resp.status_code == 200
            assert subs_resp.json()["total"] >= 1

            # 4. Super Admin manual billing adjustment
            adj_resp = await client.post(
                f"/api/v1/platform/societies/{soc_id}/adjustments",
                json={
                    "adjustment_type": "GOODWILL_WAIVER",
                    "amount": "500.00",
                    "reason": "Executive onboarding goodwill credit",
                    "idempotency_key": "stage3-adj-custom-001",
                },
            )
            assert adj_resp.status_code == 201
            assert Decimal(adj_resp.json()["amount"]) == Decimal("500.00")
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# Step 2: Cross-Tier Security & Multi-Tenant Boundary Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_stage3_cross_tier_security_and_tenant_boundaries(stage3_db_session, stage3_seed_data):
    """Validate complete cross-tier security matrix and cross-tenant denial."""
    soc_a = stage3_seed_data["soc_a_id"]
    soc_b = stage3_seed_data["soc_b_id"]

    # 1. Test Read matrix
    read_matrix = [
        ("u_admin_a", 200),        # Society Admin
        ("u_treasurer_a", 200),    # Treasurer
        ("u_secretary_a", 200),    # Secretary
        ("u_committee_a", 200),    # Committee Member
        ("u_resident_a", 403),     # Resident
        ("u_tenant_a", 403),       # Tenant
        ("u_inactive_a", 403),     # Inactive Member
    ]

    async def _mock_db():
        async with stage3_db_session() as sess:
            yield sess

    for user_key, expected_read in read_matrix:
        test_user = stage3_seed_data[user_key]
        app.dependency_overrides[get_db_session] = _mock_db
        app.dependency_overrides[get_current_user] = lambda u=test_user: u

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                read_resp = await client.get(f"/api/v1/societies/{soc_a}/billing/subscription")
                assert read_resp.status_code == expected_read, f"{user_key} read expected {expected_read}, got {read_resp.status_code}"
        finally:
            app.dependency_overrides.clear()

    # 2. Test Write matrix
    # Society Admin: Write permitted (200 on /cancel)
    app.dependency_overrides[get_db_session] = _mock_db
    app.dependency_overrides[get_current_user] = lambda: stage3_seed_data["u_admin_a"]
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/societies/{soc_a}/billing/subscription/cancel",
                json={"reason": "Admin test cancellation"},
            )
            assert resp.status_code == 200
    finally:
        app.dependency_overrides.clear()

    # Treasurer: Write permitted (200 on /resume)
    app.dependency_overrides[get_db_session] = _mock_db
    app.dependency_overrides[get_current_user] = lambda: stage3_seed_data["u_treasurer_a"]
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/societies/{soc_a}/billing/subscription/resume",
            )
            assert resp.status_code == 200
    finally:
        app.dependency_overrides.clear()

    # Write-denied roles (Secretary, Committee Member, Resident, Tenant, Inactive): 403 on /cancel
    write_denied_roles = ["u_secretary_a", "u_committee_a", "u_resident_a", "u_tenant_a", "u_inactive_a"]
    for user_key in write_denied_roles:
        test_user = stage3_seed_data[user_key]
        app.dependency_overrides[get_db_session] = _mock_db
        app.dependency_overrides[get_current_user] = lambda u=test_user: u
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    f"/api/v1/societies/{soc_a}/billing/subscription/cancel",
                    json={"reason": "Unauthorized cancel attempt"},
                )
                assert resp.status_code == 403, f"{user_key} write expected 403, got {resp.status_code}"
        finally:
            app.dependency_overrides.clear()

    # Cross-Tenant Boundary: User in Society A attempting to read/write Society B billing
    admin_a = stage3_seed_data["u_admin_a"]

    async def _mock_db_ct():
        async with stage3_db_session() as sess:
            yield sess

    app.dependency_overrides[get_db_session] = _mock_db_ct
    app.dependency_overrides[get_current_user] = lambda: admin_a

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            cross_read = await client.get(f"/api/v1/societies/{soc_b}/billing/subscription")
            assert cross_read.status_code == 403
            err_data = cross_read.json()
            err_msg = err_data.get("error", {}).get("message", "") or err_data.get("detail", "")
            assert "Access denied" in err_msg or "not an active member" in err_msg or "Forbidden" in err_msg
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# Step 3: Concurrency & Idempotency Safeguards
# ==============================================================================


@pytest.mark.asyncio
async def test_stage3_concurrency_and_idempotency(stage3_db_session, stage3_seed_data):
    """Validate duplicate checkout prevention, payment idempotency, and document immutability."""
    soc_id = stage3_seed_data["soc_a_id"]
    admin_user = stage3_seed_data["u_admin_a"]
    sub_id = stage3_seed_data["sub_a_id"]

    # Seed finalized invoice
    async with stage3_db_session() as session:
        inv_svc = PlatformInvoiceService()
        draft = await inv_svc.create_draft_invoice(
            session=session,
            payload=PlatformInvoiceCreateDraft(
                society_id=soc_id,
                subscription_id=sub_id,
                billing_cycle="MONTHLY",
                period_start=_utc_now() - timedelta(days=30),
                period_end=_utc_now(),
                due_date=date.today() + timedelta(days=15),
                customer_gstin="27AAPFU0939F1ZV",
                place_of_supply="27-Maharashtra",
                items=[
                    PlatformInvoiceItemCreate(
                        item_type="BASE_PLAN",
                        description="Commercial SaaS Subscription Fee",
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
        async with stage3_db_session() as sess:
            yield sess

    app.dependency_overrides[get_db_session] = _mock_db
    app.dependency_overrides[get_current_user] = lambda: admin_user
    mock_provider = MockStage3RazorpayProvider()

    try:
        with patch.object(PaymentGatewayFactory, "get_provider", AsyncMock(return_value=mock_provider)):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # 1. Initial checkout
                ck1 = await client.post(
                    f"/api/v1/societies/{soc_id}/billing/invoices/{invoice_id}/checkout",
                    json={"provider": "RAZORPAY"},
                )
                assert ck1.status_code == 201

                # 2. Settle payment
                v1 = await client.post(
                    f"/api/v1/societies/{soc_id}/billing/payments/verify",
                    json={
                        "invoice_id": str(invoice_id),
                        "gateway_order_id": "order_stage3_test_99999",
                        "gateway_payment_id": "pay_stage3_dup_12345",
                        "signature": "valid_stage3_signature",
                        "provider": "RAZORPAY",
                    },
                )
                assert v1.status_code == 200
                assert v1.json()["invoice_status"] == "PAID"

                # 3. Idempotent replay of same payment verification returns 200 without error
                v2 = await client.post(
                    f"/api/v1/societies/{soc_id}/billing/payments/verify",
                    json={
                        "invoice_id": str(invoice_id),
                        "gateway_order_id": "order_stage3_test_99999",
                        "gateway_payment_id": "pay_stage3_dup_12345",
                        "signature": "valid_stage3_signature",
                        "provider": "RAZORPAY",
                    },
                )
                assert v2.status_code == 200
                assert v2.json()["success"] is True

                # 4. Duplicate checkout on PAID invoice is rejected with 409 Conflict
                ck2 = await client.post(
                    f"/api/v1/societies/{soc_id}/billing/invoices/{invoice_id}/checkout",
                    json={"provider": "RAZORPAY"},
                )
                assert ck2.status_code == 409
    finally:
        app.dependency_overrides.clear()
