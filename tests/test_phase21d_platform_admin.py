"""Phase 21D — SaaS Platform Administration API Test Suite.

Comprehensive tests covering:
1. Platform Administrator Authorization & RBAC enforcement (SUPER_ADMIN vs tenant users).
2. Society Directory listing, multi-field searching, status filtering, and pagination.
3. Detailed society inspection with subscription brief and primary admin metadata.
4. Independent lifecycle state transitions (suspend, reactivate) with reason validation.
5. Mandatory Condition 2: Strict decoupling of Society and Subscription lifecycles:
   - Reactivating a suspended society preserves CANCELLED subscription status.
   - Reactivating a suspended society preserves PAST_DUE subscription status.
   - Duplicate suspension and reactivation return 409 Conflict.
6. Mandatory Condition 1: Provisioning diagnostics under tenant context and FORCE RLS.
7. Mandatory Condition 3: Concurrency-safe provisioning retry rules and eligibility.
8. Subscription overview integration delegating to Phase 21B Entitlement & Quota services.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.core.exceptions import NotFoundException
from apps.api.src.core.tenant_context import tenant_context
from apps.api.src.database.models.audit import AuditLog
from apps.api.src.database.models.authorization import Role, RoleAssignment
from apps.api.src.database.models.identity import User
from apps.api.src.database.models.society import Society
from apps.api.src.database.models.subscription import (
    PlatformSubscriptionPlan,
    SocietyProvisioningLog,
    SocietySubscription,
    SocietyUsageMetric,
    SubscriptionPlanEntitlement,
)
from apps.api.src.database.session import set_db_tenant_context
from apps.api.src.subscriptions import (
    FeatureKey,
    ProvisioningRetryIneligibleException,
    QuotaKey,
    SocietyAlreadyActiveException,
    SocietyAlreadySuspendedException,
    SocietyLifecycleValidationException,
    SubscriptionStatus,
)
from apps.api.src.subscriptions.platform_admin_service import PlatformAdminService


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest.fixture
async def setup_platform_test_data(db_session: AsyncSession):
    """Seed test data for platform administration tests."""
    now = _utc_now()

    # 1. Ensure SUPER_ADMIN platform role
    role_stmt = select(Role).where(Role.code == "SUPER_ADMIN", Role.scope_type == "PLATFORM")
    res = await db_session.execute(role_stmt)
    super_admin_role = res.scalar_one_or_none()
    if not super_admin_role:
        super_admin_role = Role(
            id=uuid.uuid4(),
            code="SUPER_ADMIN",
            name="Platform Super Administrator",
            scope_type="PLATFORM",
            is_system_role=True,
        )
        db_session.add(super_admin_role)

    # Ensure SOCIETY_ADMIN role
    soc_admin_role_stmt = select(Role).where(Role.code == "SOCIETY_ADMIN", Role.scope_type == "SOCIETY")
    res2 = await db_session.execute(soc_admin_role_stmt)
    soc_admin_role = res2.scalar_one_or_none()
    if not soc_admin_role:
        soc_admin_role = Role(
            id=uuid.uuid4(),
            code="SOCIETY_ADMIN",
            name="Society Administrator",
            scope_type="SOCIETY",
            is_system_role=True,
        )
        db_session.add(soc_admin_role)

    # 2. Ensure Super Admin User
    admin_user = User(
        id=uuid.uuid4(),
        email=f"superadmin-{uuid.uuid4().hex[:6]}@platform.local",
        first_name="Platform",
        last_name="SuperAdmin",
        display_name="Platform SuperAdmin",
        status="ACTIVE",
    )
    db_session.add(admin_user)
    await db_session.flush()

    # Platform Role Assignment
    admin_assignment = RoleAssignment(
        id=uuid.uuid4(),
        user_id=admin_user.id,
        role_id=super_admin_role.id,
        society_id=None,
        scope_type="PLATFORM",
        status="ACTIVE",
        assigned_at=now,
    )
    db_session.add(admin_assignment)

    # 3. Ensure Standard Subscription Plan
    plan_stmt = select(PlatformSubscriptionPlan).where(PlatformSubscriptionPlan.plan_code == "STANDARD")
    plan_res = await db_session.execute(plan_stmt)
    plan = plan_res.scalar_one_or_none()
    if not plan:
        plan = PlatformSubscriptionPlan(
            id=uuid.uuid4(),
            plan_code="STANDARD",
            display_name="Standard Tier",
            monthly_price=1999.00,
            annual_price=19990.00,
            trial_days=14,
            is_active=True,
        )
        db_session.add(plan)
        await db_session.flush()

        # Add entitlements for standard plan
        ent1 = SubscriptionPlanEntitlement(
            id=uuid.uuid4(),
            plan_id=plan.id,
            entitlement_key=FeatureKey.GOVERNANCE.value,
            entitlement_type="BOOLEAN",
            entitlement_value="true",
        )
        ent2 = SubscriptionPlanEntitlement(
            id=uuid.uuid4(),
            plan_id=plan.id,
            entitlement_key=QuotaKey.UNITS_MAX.value,
            entitlement_type="NUMERIC",
            entitlement_value="100",
        )
        db_session.add_all([ent1, ent2])

    await db_session.commit()

    return {
        "super_admin": admin_user,
        "super_admin_role": super_admin_role,
        "soc_admin_role": soc_admin_role,
        "plan": plan,
    }


# ==============================================================================
# 1. Society Directory & Search Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_platform_admin_list_societies_pagination_and_search(
    db_session: AsyncSession, setup_platform_test_data
):
    """Verify society directory search, filtering, and pagination."""
    now = _utc_now()
    unique_suffix = uuid.uuid4().hex[:6]

    # Create 3 test societies
    soc1 = Society(
        id=uuid.uuid4(),
        legal_name=f"Lotus Court {unique_suffix}",
        display_name="Lotus Court",
        registration_number=f"REG-LC-{unique_suffix}",
        address_line1="101 Lotus Way",
        city="Mumbai",
        state="Maharashtra",
        postal_code="400001",
        status="ACTIVE",
        onboarding_status="COMPLETED",
        created_at=now - timedelta(days=2),
        updated_at=now - timedelta(days=2),
    )
    soc2 = Society(
        id=uuid.uuid4(),
        legal_name=f"Orchid Residency {unique_suffix}",
        display_name="Orchid Residency",
        registration_number=f"REG-OR-{unique_suffix}",
        address_line1="202 Orchid Blvd",
        city="Bengaluru",
        state="Karnataka",
        postal_code="560001",
        status="SUSPENDED",
        onboarding_status="COMPLETED",
        created_at=now - timedelta(days=1),
        updated_at=now - timedelta(days=1),
    )
    soc3 = Society(
        id=uuid.uuid4(),
        legal_name=f"Rosewood Enclave {unique_suffix}",
        display_name="Rosewood Enclave",
        registration_number=f"REG-RE-{unique_suffix}",
        address_line1="303 Rosewood Rd",
        city="Pune",
        state="Maharashtra",
        postal_code="411001",
        status="ACTIVE",
        onboarding_status="IN_PROGRESS",
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([soc1, soc2, soc3])
    await db_session.commit()

    service = PlatformAdminService(db_session)

    # 1. Search by legal name
    res = await service.list_societies(search=f"Lotus Court {unique_suffix}")
    assert res.total == 1
    assert res.items[0].legal_name == f"Lotus Court {unique_suffix}"

    # 2. Filter by status
    res = await service.list_societies(status="SUSPENDED", search=unique_suffix)
    assert res.total == 1
    assert res.items[0].legal_name == f"Orchid Residency {unique_suffix}"

    # 3. Filter by state
    res = await service.list_societies(state="Maharashtra", search=unique_suffix)
    assert res.total == 2

    # 4. Filter by onboarding status
    res = await service.list_societies(onboarding_status="IN_PROGRESS", search=unique_suffix)
    assert res.total == 1
    assert res.items[0].legal_name == f"Rosewood Enclave {unique_suffix}"

    # 5. Pagination test
    res = await service.list_societies(search=unique_suffix, page=1, page_size=2, sort_by="created_at", sort_order="asc")
    assert res.page == 1
    assert res.page_size == 2
    assert res.total == 3
    assert res.pages == 2
    assert len(res.items) == 2
    assert res.items[0].legal_name == f"Lotus Court {unique_suffix}"
    assert res.items[1].legal_name == f"Orchid Residency {unique_suffix}"


# ==============================================================================
# 2. Society Metadata & Inspection Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_platform_admin_get_society_detail(db_session: AsyncSession, setup_platform_test_data):
    """Verify detailed society inspection with subscription brief and primary admin masking."""
    plan = setup_platform_test_data["plan"]
    soc_admin_role = setup_platform_test_data["soc_admin_role"]
    now = _utc_now()
    society_id = uuid.uuid4()

    # Create society
    society = Society(
        id=society_id,
        legal_name="Magnolia Gardens Co-op",
        display_name="Magnolia Gardens",
        registration_number="REG-MG-2026",
        address_line1="12 Palm Grove",
        city="Hyderabad",
        state="Telangana",
        postal_code="500001",
        status="ACTIVE",
        onboarding_status="COMPLETED",
        created_at=now,
        updated_at=now,
    )
    db_session.add(society)
    await db_session.flush()

    # Create subscription within tenant context
    async with tenant_context(society_id):
        await set_db_tenant_context(db_session, society_id)
        sub = SocietySubscription(
            id=uuid.uuid4(),
            society_id=society_id,
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE.value,
            starts_at=now,
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        db_session.add(sub)

        # Create primary admin user
        primary_admin = User(
            id=uuid.uuid4(),
            email="suresh.patil@example.com",
            phone="+919876543210",
            first_name="Suresh",
            last_name="Patil",
            display_name="Suresh Patil",
            status="ACTIVE",
        )
        db_session.add(primary_admin)
        await db_session.flush()

        role_assign = RoleAssignment(
            id=uuid.uuid4(),
            user_id=primary_admin.id,
            role_id=soc_admin_role.id,
            society_id=society_id,
            scope_type="SOCIETY",
            status="ACTIVE",
            assigned_at=now,
        )
        db_session.add(role_assign)

    await db_session.commit()

    service = PlatformAdminService(db_session)
    detail = await service.get_society_detail(society_id)

    assert detail.id == society_id
    assert detail.legal_name == "Magnolia Gardens Co-op"
    assert detail.status == "ACTIVE"
    assert detail.subscription is not None
    assert detail.subscription.plan_code == "STANDARD"
    assert detail.subscription.status == "ACTIVE"
    assert detail.primary_admin is not None
    assert detail.primary_admin.name == "Suresh Patil"
    assert detail.primary_admin.email_masked.startswith("s*")
    assert detail.primary_admin.email_masked.endswith("@example.com")
    assert detail.primary_admin.phone_masked == "+91******3210"


@pytest.mark.asyncio
async def test_platform_admin_get_society_detail_not_found(db_session: AsyncSession):
    """Verify 404 behavior when society does not exist."""
    service = PlatformAdminService(db_session)
    with pytest.raises(NotFoundException):
        await service.get_society_detail(uuid.uuid4())


# ==============================================================================
# 3. Society Lifecycle State Transitions (Mandatory Condition 2)
# ==============================================================================


@pytest.mark.asyncio
async def test_society_suspension_and_reactivation_lifecycle(
    db_session: AsyncSession, setup_platform_test_data
):
    """Verify ACTIVE -> SUSPENDED -> ACTIVE state transitions and audit logging."""
    admin_user = setup_platform_test_data["super_admin"]
    plan = setup_platform_test_data["plan"]
    now = _utc_now()
    society_id = uuid.uuid4()

    society = Society(
        id=society_id,
        legal_name="Palm Grove Society",
        display_name="Palm Grove",
        address_line1="Palm St",
        city="Pune",
        state="Maharashtra",
        postal_code="411001",
        status="ACTIVE",
        onboarding_status="COMPLETED",
        created_at=now,
        updated_at=now,
    )
    db_session.add(society)
    await db_session.flush()

    async with tenant_context(society_id):
        await set_db_tenant_context(db_session, society_id)
        sub = SocietySubscription(
            id=uuid.uuid4(),
            society_id=society_id,
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE.value,
            starts_at=now,
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        db_session.add(sub)
    await db_session.commit()

    service = PlatformAdminService(db_session)

    # 1. Suspend Society
    suspend_reason = "Administrative freeze due to terms of service violation investigation."
    res = await service.suspend_society(
        society_id=society_id,
        actor_user_id=admin_user.id,
        reason=suspend_reason,
    )
    assert res.current_status == "SUSPENDED"
    assert res.previous_status == "ACTIVE"
    assert res.reason == suspend_reason

    # Verify society state and audit log in database
    soc_db = await db_session.get(Society, society_id)
    assert soc_db.status == "SUSPENDED"

    audit_res = await db_session.execute(
        select(AuditLog).where(
            AuditLog.society_id == society_id,
            AuditLog.action == "SOCIETY_SUSPENDED",
        )
    )
    audit = audit_res.scalar_one_or_none()
    assert audit is not None
    assert audit.actor_user_id == admin_user.id
    assert audit.after_state["status"] == "SUSPENDED"

    # 2. Duplicate Suspension -> 409 Conflict
    with pytest.raises(SocietyAlreadySuspendedException):
        await service.suspend_society(
            society_id=society_id,
            actor_user_id=admin_user.id,
            reason="Another suspension attempt that must fail.",
        )

    # 3. Reactivate Society
    reactivate_reason = "Terms violation resolved following committee formal undertaking."
    reactivate_res = await service.reactivate_society(
        society_id=society_id,
        actor_user_id=admin_user.id,
        reason=reactivate_reason,
    )
    assert reactivate_res.current_status == "ACTIVE"
    assert reactivate_res.previous_status == "SUSPENDED"

    soc_db = await db_session.get(Society, society_id)
    assert soc_db.status == "ACTIVE"

    # 4. Duplicate Reactivation -> 409 Conflict
    with pytest.raises(SocietyAlreadyActiveException):
        await service.reactivate_society(
            society_id=society_id,
            actor_user_id=admin_user.id,
            reason="Duplicate reactivation attempt that must fail.",
        )


@pytest.mark.asyncio
async def test_lifecycle_reason_validation_rejection(db_session: AsyncSession, setup_platform_test_data):
    """Verify rejection when administrative reason is too short (< 10 chars)."""
    admin_user = setup_platform_test_data["super_admin"]
    society_id = uuid.uuid4()
    now = _utc_now()

    society = Society(
        id=society_id,
        legal_name="Test Society",
        display_name="Test",
        address_line1="123 Road",
        city="Pune",
        state="MH",
        postal_code="411001",
        status="ACTIVE",
        onboarding_status="COMPLETED",
        created_at=now,
        updated_at=now,
    )
    db_session.add(society)
    await db_session.commit()

    service = PlatformAdminService(db_session)

    # Short reason (< 10 chars)
    with pytest.raises(SocietyLifecycleValidationException):
        await service.suspend_society(
            society_id=society_id,
            actor_user_id=admin_user.id,
            reason="Too short",
        )


@pytest.mark.asyncio
async def test_mandatory_condition_2_decoupling_cancelled_subscription(
    db_session: AsyncSession, setup_platform_test_data
):
    """CRITICAL: Reactivating a society must NEVER automatically reactivate a CANCELLED subscription."""
    admin_user = setup_platform_test_data["super_admin"]
    plan = setup_platform_test_data["plan"]
    now = _utc_now()
    society_id = uuid.uuid4()

    # Create suspended society with a CANCELLED subscription
    society = Society(
        id=society_id,
        legal_name="Cedar Pines Co-op",
        display_name="Cedar Pines",
        address_line1="10 Cedar St",
        city="Pune",
        state="Maharashtra",
        postal_code="411001",
        status="SUSPENDED",
        onboarding_status="COMPLETED",
        created_at=now,
        updated_at=now,
    )
    db_session.add(society)
    await db_session.flush()

    async with tenant_context(society_id):
        await set_db_tenant_context(db_session, society_id)
        sub = SocietySubscription(
            id=uuid.uuid4(),
            society_id=society_id,
            plan_id=plan.id,
            status=SubscriptionStatus.CANCELLED.value,
            starts_at=now - timedelta(days=60),
            current_period_start=now - timedelta(days=60),
            current_period_end=now - timedelta(days=30),
            cancelled_at=now - timedelta(days=30),
            cancellation_reason="Society requested offboarding",
        )
        db_session.add(sub)
    await db_session.commit()

    service = PlatformAdminService(db_session)

    # Reactivate the society
    res = await service.reactivate_society(
        society_id=society_id,
        actor_user_id=admin_user.id,
        reason="Administrative reactivation to allow historical record access.",
    )

    assert res.current_status == "ACTIVE"
    # Subscription status MUST REMAIN CANCELLED
    assert res.subscription_status == SubscriptionStatus.CANCELLED.value

    # Verify directly in database under tenant context
    async with tenant_context(society_id):
        await set_db_tenant_context(db_session, society_id)
        sub_stmt = select(SocietySubscription).where(SocietySubscription.society_id == society_id)
        sub_res = await db_session.execute(sub_stmt)
        sub_db = sub_res.scalar_one()
        assert sub_db.status == SubscriptionStatus.CANCELLED.value


@pytest.mark.asyncio
async def test_mandatory_condition_2_decoupling_past_due_subscription(
    db_session: AsyncSession, setup_platform_test_data
):
    """CRITICAL: Reactivating a society must NEVER bypass PAST_DUE subscription restrictions."""
    admin_user = setup_platform_test_data["super_admin"]
    plan = setup_platform_test_data["plan"]
    now = _utc_now()
    society_id = uuid.uuid4()

    society = Society(
        id=society_id,
        legal_name="Maple Court Housing",
        display_name="Maple Court",
        address_line1="88 Maple Rd",
        city="Mumbai",
        state="Maharashtra",
        postal_code="400001",
        status="SUSPENDED",
        onboarding_status="COMPLETED",
        created_at=now,
        updated_at=now,
    )
    db_session.add(society)
    await db_session.flush()

    async with tenant_context(society_id):
        await set_db_tenant_context(db_session, society_id)
        sub = SocietySubscription(
            id=uuid.uuid4(),
            society_id=society_id,
            plan_id=plan.id,
            status=SubscriptionStatus.PAST_DUE.value,
            starts_at=now - timedelta(days=45),
            current_period_start=now - timedelta(days=15),
            current_period_end=now + timedelta(days=15),
            past_due_since=now - timedelta(days=5),
        )
        db_session.add(sub)
    await db_session.commit()

    service = PlatformAdminService(db_session)

    res = await service.reactivate_society(
        society_id=society_id,
        actor_user_id=admin_user.id,
        reason="Administrative lift of suspension; billing dispute under mediation.",
    )

    assert res.current_status == "ACTIVE"
    # Subscription status MUST REMAIN PAST_DUE
    assert res.subscription_status == SubscriptionStatus.PAST_DUE.value


# ==============================================================================
# 4. Provisioning Diagnostics (Mandatory Condition 1: FORCE RLS Compliance)
# ==============================================================================


@pytest.mark.asyncio
async def test_mandatory_condition_1_provisioning_diagnostics_rls(
    db_session: AsyncSession, setup_platform_test_data
):
    """Verify get_provisioning_diagnostics executes under tenant context to respect FORCE RLS."""
    now = _utc_now()
    society_id = uuid.uuid4()
    req_id = uuid.uuid4()

    society = Society(
        id=society_id,
        legal_name="Willow Crest",
        display_name="Willow Crest",
        address_line1="Willow Way",
        city="Delhi",
        state="Delhi",
        postal_code="110001",
        status="ACTIVE",
        onboarding_status="COMPLETED",
        created_at=now,
        updated_at=now,
    )
    db_session.add(society)
    await db_session.flush()

    # Seed provisioning step logs within tenant context
    async with tenant_context(society_id):
        await set_db_tenant_context(db_session, society_id)
        log1 = SocietyProvisioningLog(
            id=uuid.uuid4(),
            society_id=society_id,
            provisioning_request_id=req_id,
            step_key="VALIDATE_INPUT",
            status="COMPLETED",
            message="Payload validated successfully.",
            started_at=now,
            completed_at=now + timedelta(milliseconds=10),
        )
        log2 = SocietyProvisioningLog(
            id=uuid.uuid4(),
            society_id=society_id,
            provisioning_request_id=req_id,
            step_key="CREATE_SOCIETY_ROOT",
            status="COMPLETED",
            message="Created society root.",
            started_at=now + timedelta(milliseconds=10),
            completed_at=now + timedelta(milliseconds=25),
        )
        db_session.add_all([log1, log2])
    await db_session.commit()

    service = PlatformAdminService(db_session)
    diagnostics = await service.get_provisioning_diagnostics(society_id)

    assert diagnostics.society_id == society_id
    assert diagnostics.onboarding_status == "COMPLETED"
    assert diagnostics.is_retryable is False
    assert len(diagnostics.steps) == 2
    assert diagnostics.steps[0].step_key == "VALIDATE_INPUT"
    assert diagnostics.steps[1].step_key == "CREATE_SOCIETY_ROOT"


# ==============================================================================
# 5. Provisioning Retry Eligibility & Safety (Mandatory Condition 3)
# ==============================================================================


@pytest.mark.asyncio
async def test_mandatory_condition_3_retry_completed_provisioning_ineligible(
    db_session: AsyncSession, setup_platform_test_data
):
    """Verify that retrying a COMPLETED onboarding is rejected with 409 Conflict."""
    admin_user = setup_platform_test_data["super_admin"]
    now = _utc_now()
    society_id = uuid.uuid4()

    society = Society(
        id=society_id,
        legal_name="Silver Oak Society",
        display_name="Silver Oak",
        address_line1="Silver St",
        city="Pune",
        state="Maharashtra",
        postal_code="411001",
        status="ACTIVE",
        onboarding_status="COMPLETED",
        created_at=now,
        updated_at=now,
    )
    db_session.add(society)
    await db_session.commit()

    service = PlatformAdminService(db_session)

    with pytest.raises(ProvisioningRetryIneligibleException) as exc_info:
        await service.retry_provisioning(
            society_id=society_id,
            current_user_id=admin_user.id,
        )
    assert exc_info.value.code == "PROVISIONING_ALREADY_COMPLETED"
    assert exc_info.value.status_code == 409


# ==============================================================================
# 6. Subscription Overview (Phase 21B Integration)
# ==============================================================================


@pytest.mark.asyncio
async def test_platform_admin_subscription_overview(db_session: AsyncSession, setup_platform_test_data):
    """Verify consolidated subscription overview directly delegates to Phase 21B services."""
    plan = setup_platform_test_data["plan"]
    now = _utc_now()
    society_id = uuid.uuid4()

    society = Society(
        id=society_id,
        legal_name="Apex Enclave",
        display_name="Apex Enclave",
        address_line1="Apex Ave",
        city="Bengaluru",
        state="Karnataka",
        postal_code="560001",
        status="ACTIVE",
        onboarding_status="COMPLETED",
        created_at=now,
        updated_at=now,
    )
    db_session.add(society)
    await db_session.flush()

    async with tenant_context(society_id):
        await set_db_tenant_context(db_session, society_id)
        sub = SocietySubscription(
            id=uuid.uuid4(),
            society_id=society_id,
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE.value,
            starts_at=now,
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        # Add baseline usage metric for quota evaluation
        metric = SocietyUsageMetric(
            id=uuid.uuid4(),
            society_id=society_id,
            metric_key=QuotaKey.UNITS_MAX.value,
            current_value=42,
            last_calculated_at=now,
        )
        db_session.add_all([sub, metric])
    await db_session.commit()

    service = PlatformAdminService(db_session)
    overview = await service.get_subscription_overview(society_id)

    assert overview.society_id == society_id
    assert overview.plan_code == "STANDARD"
    assert overview.subscription_status == "ACTIVE"

    # Verify governance feature resolved via EntitlementService
    gov_feature = next((f for f in overview.features if f.entitlement_key == FeatureKey.GOVERNANCE.value), None)
    assert gov_feature is not None
    assert gov_feature.is_enabled is True

    # Verify units quota resolved via QuotaEnforcementService
    units_quota = next((q for q in overview.quotas if q.quota_key == QuotaKey.UNITS_MAX.value), None)
    assert units_quota is not None
    assert units_quota.max_limit == 100


# ==============================================================================
# 7. FastAPI Endpoint & Platform RBAC Authorization Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_api_platform_endpoints_require_super_admin(async_client):
    """Platform endpoints reject unauthenticated and non-SUPER_ADMIN users safely."""
    # 1. Unauthenticated request -> 401
    res = await async_client.get("/api/v1/platform/societies")
    assert res.status_code == 401

    # 2. Login as regular tenant
    tenant_login = await async_client.post(
        "/api/v1/auth/login",
        json={"identifier": "tenant.a@palmstree.in", "password": "Password123!"},
    )
    assert tenant_login.status_code == 200
    tenant_token = tenant_login.json()["access_token"]

    # 3. Authenticated as non-super-admin -> 403 Forbidden
    res_forbidden = await async_client.get(
        "/api/v1/platform/societies",
        headers={"Authorization": f"Bearer {tenant_token}"},
    )
    assert res_forbidden.status_code == 403


@pytest.mark.asyncio
async def test_api_platform_admin_full_flow(async_client, setup_platform_test_data):
    """Full HTTP workflow: provision, list, detail, suspend, duplicate suspend, reactivate, diagnostics, overview, retry."""
    # Login as Super Admin
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"identifier": "superadmin@societysphere.io", "password": "Password123!"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Provision a society
    unique_suffix = uuid.uuid4().hex[:6]
    req_id = str(uuid.uuid4())
    prov_payload = {
        "provisioning_request_id": req_id,
        "legal_name": f"API Test Enclave {unique_suffix}",
        "display_name": f"API Test {unique_suffix}",
        "registration_number": f"REG-API-{unique_suffix}",
        "address_line1": "100 API Way",
        "city": "Bengaluru",
        "state": "Karnataka",
        "country": "IN",
        "postal_code": "560001",
        "plan_code": "STANDARD",
        "admin_user": {
            "email": f"admin.{unique_suffix}@example.com",
            "first_name": "API",
            "last_name": "Admin",
        },
        "spatial": {
            "create_default_block": True,
            "default_block_name": "Tower A",
        },
    }
    prov_res = await async_client.post(
        "/api/v1/platform/societies/provision",
        headers=headers,
        json=prov_payload,
    )
    assert prov_res.status_code == 201
    target_society_id = prov_res.json()["society_id"]

    # 2. List societies (filtered by search)
    list_res = await async_client.get(
        f"/api/v1/platform/societies?search={unique_suffix}",
        headers=headers,
    )
    assert list_res.status_code == 200
    data = list_res.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == target_society_id

    # 3. Get society detail
    detail_res = await async_client.get(f"/api/v1/platform/societies/{target_society_id}", headers=headers)
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["id"] == target_society_id
    assert detail["status"] == "ACTIVE"
    assert detail["subscription"] is not None
    assert detail["subscription"]["plan_code"] == "STANDARD"

    # 4. Suspend society
    suspend_res = await async_client.post(
        f"/api/v1/platform/societies/{target_society_id}/suspend",
        headers=headers,
        json={"reason": "Administrative suspension for compliance audit verification."},
    )
    assert suspend_res.status_code == 200
    assert suspend_res.json()["current_status"] == "SUSPENDED"

    # 5. Duplicate suspend -> 409 Conflict
    dup_suspend = await async_client.post(
        f"/api/v1/platform/societies/{target_society_id}/suspend",
        headers=headers,
        json={"reason": "Attempting duplicate suspension."},
    )
    assert dup_suspend.status_code == 409
    assert dup_suspend.json()["error"]["code"] == "SOCIETY_ALREADY_SUSPENDED"

    # 6. Reactivate society
    reactivate_res = await async_client.post(
        f"/api/v1/platform/societies/{target_society_id}/reactivate",
        headers=headers,
        json={"reason": "Audit verification successfully completed."},
    )
    assert reactivate_res.status_code == 200
    assert reactivate_res.json()["current_status"] == "ACTIVE"

    # 7. Duplicate reactivate -> 409 Conflict
    dup_reactivate = await async_client.post(
        f"/api/v1/platform/societies/{target_society_id}/reactivate",
        headers=headers,
        json={"reason": "Attempting duplicate reactivation."},
    )
    assert dup_reactivate.status_code == 409
    assert dup_reactivate.json()["error"]["code"] == "SOCIETY_ALREADY_ACTIVE"

    # 8. Provisioning diagnostics
    diag_res = await async_client.get(
        f"/api/v1/platform/societies/{target_society_id}/provisioning-logs",
        headers=headers,
    )
    assert diag_res.status_code == 200
    assert "steps" in diag_res.json()
    assert len(diag_res.json()["steps"]) > 0

    # 9. Subscription overview
    sub_res = await async_client.get(
        f"/api/v1/platform/societies/{target_society_id}/subscription-overview",
        headers=headers,
    )
    assert sub_res.status_code == 200
    sub_data = sub_res.json()
    assert sub_data["plan_code"] == "STANDARD"
    assert "features" in sub_data
    assert "quotas" in sub_data

    # 10. Retry completed provisioning -> 409 Conflict
    retry_res = await async_client.post(
        f"/api/v1/platform/societies/{target_society_id}/provisioning-retry",
        headers=headers,
    )
    assert retry_res.status_code == 409
    assert retry_res.json()["error"]["code"] == "PROVISIONING_ALREADY_COMPLETED"

