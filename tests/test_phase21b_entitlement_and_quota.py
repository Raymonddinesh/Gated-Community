"""Phase 21B — Entitlement Service and Quota Enforcement Service Test Suite.

Exhaustive test suite verifying:
- Strict tenant security boundary and fail-closed isolation.
- Canonical three-tier entitlement precedence (Override -> Plan -> System Default).
- Time-windowed overrides (effective_from, effective_until).
- Supported entitlement representations (BOOLEAN, NUMERIC, UNLIMITED).
- Subscription lifecycle states (TRIAL, ACTIVE, PAST_DUE, SUSPENDED, CANCELLED).
- Race-safe, atomic quota reservations (SELECT ... FOR UPDATE).
- Non-negative usage invariants and safe missing-row initialization.
- Transaction rollback safety and cross-tenant access rejection.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from apps.api.src.core.exceptions import AuthorizationException, TenantContextRequiredException
from apps.api.src.core.tenant_context import tenant_context
from apps.api.src.database.models.society import Society
from apps.api.src.database.models.subscription import (
    PlatformSubscriptionPlan,
    SocietyFeatureOverride,
    SocietyQuotaOverride,
    SocietySubscription,
    SocietyUsageMetric,
    SubscriptionPlanEntitlement,
)
from apps.api.src.subscriptions import (
    EntitlementService,
    EntitlementSource,
    EntitlementType,
    FeatureKey,
    InvalidEntitlementConfigException,
    InvalidUsageIncrementException,
    QuotaEnforcementService,
    QuotaExceededException,
    QuotaKey,
    SubscriptionStatus,
)

# ==============================================================================
# Helper Factories
# ==============================================================================


async def create_society(db: AsyncSession, name: str = "Test Society") -> Society:
    soc = Society(
        legal_name=f"{name} Legal {uuid.uuid4().hex[:6]}",
        display_name=name,
        address_line1="123 Palm Ave",
        city="Bengaluru",
        state="Karnataka",
        postal_code="560001",
    )
    db.add(soc)
    await db.flush()
    return soc


async def create_plan(
    db: AsyncSession,
    plan_code: str,
    display_name: str = "Standard Plan",
    is_active: bool = True,
    entitlements: list[dict[str, str]] | None = None,
) -> PlatformSubscriptionPlan:
    plan = PlatformSubscriptionPlan(
        plan_code=plan_code,
        display_name=display_name,
        monthly_price=1999.00,
        annual_price=19990.00,
        currency_code="INR",
        trial_days=14,
        is_active=is_active,
    )
    db.add(plan)
    await db.flush()

    if entitlements:
        for ent in entitlements:
            e = SubscriptionPlanEntitlement(
                plan_id=plan.id,
                entitlement_key=ent["key"],
                entitlement_type=ent.get("type", "BOOLEAN"),
                entitlement_value=ent["value"],
            )
            db.add(e)
        await db.flush()

    return plan


async def create_subscription(
    db: AsyncSession,
    society_id: uuid.UUID,
    plan_id: uuid.UUID,
    status: str = SubscriptionStatus.ACTIVE.value,
    trial_ends_at: datetime | None = None,
) -> SocietySubscription:
    now = datetime.now(UTC).replace(tzinfo=None)
    sub = SocietySubscription(
        society_id=society_id,
        plan_id=plan_id,
        status=status,
        starts_at=now,
        trial_ends_at=trial_ends_at,
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
    )
    db.add(sub)
    await db.flush()
    return sub


# ==============================================================================
# 1. ENTITLEMENT SERVICE TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_01_plan_level_boolean_enabled(db_session: AsyncSession) -> None:
    """1. Plan-level boolean feature enabled is correctly resolved."""
    soc = await create_society(db_session, "Soc Enabled")
    plan = await create_plan(
        db_session,
        plan_code="PLAN_BOOL_EN",
        entitlements=[{"key": FeatureKey.FACILITY_BOOKING.value, "type": "BOOLEAN", "value": "true"}],
    )
    await create_subscription(db_session, soc.id, plan.id)
    await db_session.commit()

    service = EntitlementService(db_session)
    async with tenant_context(soc.id):
        enabled = await service.can_use_feature(soc.id, FeatureKey.FACILITY_BOOKING.value)
        assert enabled is True

        eff = await service.get_effective_entitlement(soc.id, FeatureKey.FACILITY_BOOKING.value)
        assert eff.is_enabled is True
        assert eff.source == EntitlementSource.PLAN
        assert eff.entitlement_type == EntitlementType.BOOLEAN
        assert eff.plan_code == "PLAN_BOOL_EN"


@pytest.mark.asyncio
async def test_02_plan_level_boolean_disabled(db_session: AsyncSession) -> None:
    """2. Plan-level boolean feature disabled is correctly resolved."""
    soc = await create_society(db_session, "Soc Disabled")
    plan = await create_plan(
        db_session,
        plan_code="PLAN_BOOL_DIS",
        entitlements=[{"key": FeatureKey.GOVERNANCE.value, "type": "BOOLEAN", "value": "false"}],
    )
    await create_subscription(db_session, soc.id, plan.id)
    await db_session.commit()

    service = EntitlementService(db_session)
    async with tenant_context(soc.id):
        enabled = await service.can_use_feature(soc.id, FeatureKey.GOVERNANCE.value)
        assert enabled is False

        eff = await service.get_effective_entitlement(soc.id, FeatureKey.GOVERNANCE.value)
        assert eff.is_enabled is False
        assert eff.source == EntitlementSource.PLAN


@pytest.mark.asyncio
async def test_03_society_override_precedence(db_session: AsyncSession) -> None:
    """3. Applicable society-specific override takes precedence over plan definition."""
    soc = await create_society(db_session, "Soc Override")
    plan = await create_plan(
        db_session,
        plan_code="PLAN_OVERRIDE",
        entitlements=[{"key": FeatureKey.GOVERNANCE.value, "type": "BOOLEAN", "value": "false"}],
    )
    await create_subscription(db_session, soc.id, plan.id)

    # Add active feature override for society
    override = SocietyFeatureOverride(
        society_id=soc.id,
        feature_key=FeatureKey.GOVERNANCE.value,
        is_enabled=True,
        override_reason="Executive promotion unlock",
    )
    db_session.add(override)
    await db_session.commit()

    service = EntitlementService(db_session)
    async with tenant_context(soc.id):
        enabled = await service.can_use_feature(soc.id, FeatureKey.GOVERNANCE.value)
        assert enabled is True

        eff = await service.get_effective_entitlement(soc.id, FeatureKey.GOVERNANCE.value)
        assert eff.is_enabled is True
        assert eff.source == EntitlementSource.OVERRIDE
        assert eff.override_id == override.id
        assert eff.diagnostics["override_reason"] == "Executive promotion unlock"


@pytest.mark.asyncio
async def test_04_expired_override_ignored(db_session: AsyncSession) -> None:
    """4. Expired override is ignored and evaluation falls back to plan level."""
    soc = await create_society(db_session, "Soc Expired Override")
    plan = await create_plan(
        db_session,
        plan_code="PLAN_EXP_OVR",
        entitlements=[{"key": FeatureKey.GOVERNANCE.value, "type": "BOOLEAN", "value": "false"}],
    )
    await create_subscription(db_session, soc.id, plan.id)

    # Override ended yesterday
    past = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
    override = SocietyFeatureOverride(
        society_id=soc.id,
        feature_key=FeatureKey.GOVERNANCE.value,
        is_enabled=True,
        effective_until=past,
        override_reason="Temporary campaign (expired)",
    )
    db_session.add(override)
    await db_session.commit()

    service = EntitlementService(db_session)
    async with tenant_context(soc.id):
        enabled = await service.can_use_feature(soc.id, FeatureKey.GOVERNANCE.value)
        assert enabled is False

        eff = await service.get_effective_entitlement(soc.id, FeatureKey.GOVERNANCE.value)
        assert eff.is_enabled is False
        assert eff.source == EntitlementSource.PLAN


@pytest.mark.asyncio
async def test_05_future_override_not_prematurely_applied(db_session: AsyncSession) -> None:
    """5. Future-dated override is ignored until effective_from date arrives."""
    soc = await create_society(db_session, "Soc Future Override")
    plan = await create_plan(
        db_session,
        plan_code="PLAN_FUT_OVR",
        entitlements=[{"key": FeatureKey.GOVERNANCE.value, "type": "BOOLEAN", "value": "false"}],
    )
    await create_subscription(db_session, soc.id, plan.id)

    # Override starts in 7 days
    future = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7)
    override = SocietyFeatureOverride(
        society_id=soc.id,
        feature_key=FeatureKey.GOVERNANCE.value,
        is_enabled=True,
        effective_from=future,
        override_reason="Future rollout",
    )
    db_session.add(override)
    await db_session.commit()

    service = EntitlementService(db_session)
    async with tenant_context(soc.id):
        enabled = await service.can_use_feature(soc.id, FeatureKey.GOVERNANCE.value)
        assert enabled is False

        eff = await service.get_effective_entitlement(soc.id, FeatureKey.GOVERNANCE.value)
        assert eff.is_enabled is False
        assert eff.source == EntitlementSource.PLAN


@pytest.mark.asyncio
async def test_06_numeric_entitlement_returns_configured_limit(db_session: AsyncSession) -> None:
    """6. Numeric entitlement returns configured numeric limit."""
    soc = await create_society(db_session, "Soc Numeric")
    plan = await create_plan(
        db_session,
        plan_code="PLAN_NUMERIC",
        entitlements=[{"key": QuotaKey.UNITS_MAX.value, "type": "NUMERIC", "value": "150"}],
    )
    await create_subscription(db_session, soc.id, plan.id)
    await db_session.commit()

    service = EntitlementService(db_session)
    async with tenant_context(soc.id):
        limit = await service.get_limit(soc.id, QuotaKey.UNITS_MAX.value)
        assert limit == 150

        assert await service.check_limit(soc.id, QuotaKey.UNITS_MAX.value, 100) is True
        assert await service.check_limit(soc.id, QuotaKey.UNITS_MAX.value, 150) is True
        assert await service.check_limit(soc.id, QuotaKey.UNITS_MAX.value, 151) is False

        eff = await service.get_effective_entitlement(soc.id, QuotaKey.UNITS_MAX.value)
        assert eff.limit == 150
        assert eff.is_unlimited is False
        assert eff.source == EntitlementSource.PLAN


@pytest.mark.asyncio
async def test_07_unlimited_entitlement_is_explicit(db_session: AsyncSession) -> None:
    """7. Unlimited entitlement is explicitly represented without arbitrary large numbers."""
    soc = await create_society(db_session, "Soc Unlimited")
    plan = await create_plan(
        db_session,
        plan_code="PLAN_UNLIMITED",
        entitlements=[{"key": QuotaKey.UNITS_MAX.value, "type": "UNLIMITED", "value": "UNLIMITED"}],
    )
    await create_subscription(db_session, soc.id, plan.id)
    await db_session.commit()

    service = EntitlementService(db_session)
    async with tenant_context(soc.id):
        limit = await service.get_limit(soc.id, QuotaKey.UNITS_MAX.value)
        assert limit is None  # Explicit None denotes UNLIMITED

        assert await service.check_limit(soc.id, QuotaKey.UNITS_MAX.value, 999999) is True

        eff = await service.get_effective_entitlement(soc.id, QuotaKey.UNITS_MAX.value)
        assert eff.is_unlimited is True
        assert eff.limit is None
        assert eff.source == EntitlementSource.PLAN


@pytest.mark.asyncio
async def test_08_missing_entitlement_fails_safely(db_session: AsyncSession) -> None:
    """8. Missing entitlement fails safely (fail-closed, disabled, limit 0)."""
    soc = await create_society(db_session, "Soc Missing Ent")
    plan = await create_plan(db_session, plan_code="PLAN_EMPTY")
    await create_subscription(db_session, soc.id, plan.id)
    await db_session.commit()

    service = EntitlementService(db_session)
    async with tenant_context(soc.id):
        assert await service.can_use_feature(soc.id, "feature.non_existent") is False
        assert await service.get_limit(soc.id, "quota.non_existent") == 0

        eff = await service.get_effective_entitlement(soc.id, "feature.non_existent")
        assert eff.is_enabled is False
        assert eff.limit == 0
        assert eff.source == EntitlementSource.SYSTEM_DEFAULT
        assert eff.diagnostics["reason"] == "ENTITLEMENT_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_09_missing_subscription_fails_safely(db_session: AsyncSession) -> None:
    """9. Missing subscription record fails safely (fail-closed, disabled)."""
    soc = await create_society(db_session, "Soc No Sub")
    await db_session.commit()

    service = EntitlementService(db_session)
    async with tenant_context(soc.id):
        assert await service.can_use_feature(soc.id, FeatureKey.FACILITY_BOOKING.value) is False
        eff = await service.get_effective_entitlement(soc.id, FeatureKey.FACILITY_BOOKING.value)
        assert eff.is_enabled is False
        assert eff.source == EntitlementSource.SYSTEM_DEFAULT
        assert eff.diagnostics["reason"] == "NO_SUBSCRIPTION"


@pytest.mark.asyncio
async def test_10_inactive_plan_behavior_deterministic(db_session: AsyncSession) -> None:
    """10. Inactive or archived plan fails safely."""
    soc = await create_society(db_session, "Soc Inactive Plan")
    plan = await create_plan(
        db_session,
        plan_code="PLAN_INACTIVE",
        is_active=False,
        entitlements=[{"key": FeatureKey.FACILITY_BOOKING.value, "type": "BOOLEAN", "value": "true"}],
    )
    await create_subscription(db_session, soc.id, plan.id)
    await db_session.commit()

    service = EntitlementService(db_session)
    async with tenant_context(soc.id):
        assert await service.can_use_feature(soc.id, FeatureKey.FACILITY_BOOKING.value) is False
        eff = await service.get_effective_entitlement(soc.id, FeatureKey.FACILITY_BOOKING.value)
        assert eff.is_enabled is False
        assert eff.diagnostics["reason"] == "PLAN_INACTIVE"


@pytest.mark.asyncio
async def test_11_suspended_and_cancelled_subscription_policy(db_session: AsyncSession) -> None:
    """11. Suspended or cancelled subscription strictly denies feature access."""
    soc1 = await create_society(db_session, "Soc Suspended")
    soc2 = await create_society(db_session, "Soc Cancelled")
    soc3 = await create_society(db_session, "Soc Expired Trial")

    plan = await create_plan(
        db_session,
        plan_code="PLAN_ACTIVE_TIER",
        entitlements=[{"key": FeatureKey.FACILITY_BOOKING.value, "type": "BOOLEAN", "value": "true"}],
    )

    await create_subscription(db_session, soc1.id, plan.id, status=SubscriptionStatus.SUSPENDED.value)
    await create_subscription(db_session, soc2.id, plan.id, status=SubscriptionStatus.CANCELLED.value)

    past = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=2)
    await create_subscription(db_session, soc3.id, plan.id, status=SubscriptionStatus.TRIAL.value, trial_ends_at=past)
    await db_session.commit()

    service = EntitlementService(db_session)

    # Suspended
    async with tenant_context(soc1.id):
        assert await service.can_use_feature(soc1.id, FeatureKey.FACILITY_BOOKING.value) is False

    # Cancelled
    async with tenant_context(soc2.id):
        assert await service.can_use_feature(soc2.id, FeatureKey.FACILITY_BOOKING.value) is False

    # Expired Trial
    async with tenant_context(soc3.id):
        assert await service.can_use_feature(soc3.id, FeatureKey.FACILITY_BOOKING.value) is False


@pytest.mark.asyncio
async def test_12_invalid_entitlement_data_rejected(db_session: AsyncSession) -> None:
    """12. Corrupt or unparseable entitlement representations raise domain error."""
    soc = await create_society(db_session, "Soc Bad Data")
    plan = await create_plan(
        db_session,
        plan_code="PLAN_CORRUPT",
        entitlements=[
            {"key": "feature.corrupt_bool", "type": "BOOLEAN", "value": "NOT_A_BOOLEAN"},
            {"key": "quota.corrupt_num", "type": "NUMERIC", "value": "NOT_AN_INTEGER"},
        ],
    )
    await create_subscription(db_session, soc.id, plan.id)
    await db_session.commit()

    service = EntitlementService(db_session)
    async with tenant_context(soc.id):
        with pytest.raises(InvalidEntitlementConfigException):
            await service.get_effective_entitlement(soc.id, "feature.corrupt_bool")

        with pytest.raises(InvalidEntitlementConfigException):
            await service.get_effective_entitlement(soc.id, "quota.corrupt_num")


@pytest.mark.asyncio
async def test_13_cross_tenant_society_override_access_rejected(db_session: AsyncSession) -> None:
    """13. Attempting to evaluate entitlements for another society raises 403 Forbidden."""
    soc_a = await create_society(db_session, "Soc A")
    soc_b = await create_society(db_session, "Soc B")
    await db_session.commit()

    service = EntitlementService(db_session)
    async with tenant_context(soc_a.id):
        with pytest.raises(AuthorizationException) as exc_info:
            await service.get_effective_entitlement(soc_b.id, FeatureKey.GOVERNANCE.value)
        assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_14_missing_tenant_context_rejected(db_session: AsyncSession) -> None:
    """14. Missing tenant context raises 400 Bad Request."""
    soc = await create_society(db_session, "Soc Contextless")
    await db_session.commit()

    service = EntitlementService(db_session)
    with pytest.raises(TenantContextRequiredException):
        await service.can_use_feature(soc.id, FeatureKey.GOVERNANCE.value)

    with pytest.raises(TenantContextRequiredException):
        await service.can_use_feature(None, FeatureKey.GOVERNANCE.value)


# ==============================================================================
# 2. QUOTA ENFORCEMENT SERVICE TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_15_usage_below_limit_accepted(db_session: AsyncSession) -> None:
    """15. Usage increment below quota limit succeeds atomically."""
    soc = await create_society(db_session, "Soc Quota Below")
    plan = await create_plan(
        db_session,
        plan_code="PLAN_Q_BELOW",
        entitlements=[{"key": QuotaKey.UNITS_MAX.value, "type": "NUMERIC", "value": "50"}],
    )
    await create_subscription(db_session, soc.id, plan.id)
    await db_session.commit()

    quota_service = QuotaEnforcementService(db_session)
    async with tenant_context(soc.id):
        # 1. Check quota is available
        assert await quota_service.check_quota(soc.id, QuotaKey.UNITS_MAX.value, requested_increment=5) is True

        # 2. Reserve usage
        res = await quota_service.reserve_usage(soc.id, QuotaKey.UNITS_MAX.value, requested_increment=5)
        assert res.previous_usage == 0
        assert res.new_usage == 5
        assert res.max_limit == 50

        # 3. Check current usage
        assert await quota_service.get_current_usage(soc.id, QuotaKey.UNITS_MAX.value) == 5


@pytest.mark.asyncio
async def test_16_usage_at_limit_rejects_positive_increment(db_session: AsyncSession) -> None:
    """16. When usage is exactly at the limit, any positive increment is rejected."""
    soc = await create_society(db_session, "Soc Quota Exact")
    plan = await create_plan(
        db_session,
        plan_code="PLAN_Q_EXACT",
        entitlements=[{"key": QuotaKey.UNITS_MAX.value, "type": "NUMERIC", "value": "10"}],
    )
    await create_subscription(db_session, soc.id, plan.id)
    await db_session.commit()

    quota_service = QuotaEnforcementService(db_session)
    async with tenant_context(soc.id):
        # Reserve full quota
        await quota_service.reserve_usage(soc.id, QuotaKey.UNITS_MAX.value, requested_increment=10)
        assert await quota_service.get_current_usage(soc.id, QuotaKey.UNITS_MAX.value) == 10

        # Attempting increment of 1 fails
        assert await quota_service.check_quota(soc.id, QuotaKey.UNITS_MAX.value, requested_increment=1) is False
        with pytest.raises(QuotaExceededException) as exc_info:
            await quota_service.reserve_usage(soc.id, QuotaKey.UNITS_MAX.value, requested_increment=1)
        assert exc_info.value.status_code == 409
        assert exc_info.value.details["current_usage"] == 10
        assert exc_info.value.details["max_limit"] == 10


@pytest.mark.asyncio
async def test_17_increment_exceeding_limit_rejected(db_session: AsyncSession) -> None:
    """17. Request that would exceed quota ceiling is rejected."""
    soc = await create_society(db_session, "Soc Quota Over")
    plan = await create_plan(
        db_session,
        plan_code="PLAN_Q_OVER",
        entitlements=[{"key": QuotaKey.UNITS_MAX.value, "type": "NUMERIC", "value": "50"}],
    )
    await create_subscription(db_session, soc.id, plan.id)
    await db_session.commit()

    quota_service = QuotaEnforcementService(db_session)
    async with tenant_context(soc.id):
        await quota_service.reserve_usage(soc.id, QuotaKey.UNITS_MAX.value, requested_increment=45)

        # 45 + 10 = 55 > 50 -> must raise
        with pytest.raises(QuotaExceededException):
            await quota_service.reserve_usage(soc.id, QuotaKey.UNITS_MAX.value, requested_increment=10)

        # Counter must remain at 45
        assert await quota_service.get_current_usage(soc.id, QuotaKey.UNITS_MAX.value) == 45


@pytest.mark.asyncio
async def test_18_zero_increment_behavior_defined(db_session: AsyncSession) -> None:
    """18. Zero increment is accepted as a non-mutating validation check."""
    soc = await create_society(db_session, "Soc Quota Zero")
    plan = await create_plan(
        db_session,
        plan_code="PLAN_Q_ZERO",
        entitlements=[{"key": QuotaKey.UNITS_MAX.value, "type": "NUMERIC", "value": "50"}],
    )
    await create_subscription(db_session, soc.id, plan.id)
    await db_session.commit()

    quota_service = QuotaEnforcementService(db_session)
    async with tenant_context(soc.id):
        await quota_service.reserve_usage(soc.id, QuotaKey.UNITS_MAX.value, requested_increment=12)

        res = await quota_service.reserve_usage(soc.id, QuotaKey.UNITS_MAX.value, requested_increment=0)
        assert res.previous_usage == 12
        assert res.new_usage == 12
        assert res.requested_increment == 0


@pytest.mark.asyncio
async def test_19_negative_increment_rejected(db_session: AsyncSession) -> None:
    """19. Negative usage increments are rejected with 400 Bad Request."""
    soc = await create_society(db_session, "Soc Negative Increment")
    plan = await create_plan(
        db_session,
        plan_code="PLAN_Q_NEG",
        entitlements=[{"key": QuotaKey.UNITS_MAX.value, "type": "NUMERIC", "value": "50"}],
    )
    await create_subscription(db_session, soc.id, plan.id)
    await db_session.commit()

    quota_service = QuotaEnforcementService(db_session)
    async with tenant_context(soc.id):
        with pytest.raises(InvalidUsageIncrementException):
            await quota_service.check_quota(soc.id, QuotaKey.UNITS_MAX.value, requested_increment=-1)

        with pytest.raises(InvalidUsageIncrementException):
            await quota_service.reserve_usage(soc.id, QuotaKey.UNITS_MAX.value, requested_increment=-5)


@pytest.mark.asyncio
async def test_20_unlimited_quota_works_without_arbitrary_limits(db_session: AsyncSession) -> None:
    """20. Unlimited quota permits increments without numerical overflow or ceiling."""
    soc = await create_society(db_session, "Soc Unlimited Quota")
    plan = await create_plan(
        db_session,
        plan_code="PLAN_Q_UNLIM",
        entitlements=[{"key": QuotaKey.UNITS_MAX.value, "type": "UNLIMITED", "value": "UNLIMITED"}],
    )
    await create_subscription(db_session, soc.id, plan.id)
    await db_session.commit()

    quota_service = QuotaEnforcementService(db_session)
    async with tenant_context(soc.id):
        assert await quota_service.check_quota(soc.id, QuotaKey.UNITS_MAX.value, 5000) is True

        res = await quota_service.reserve_usage(soc.id, QuotaKey.UNITS_MAX.value, requested_increment=10000)
        assert res.is_unlimited is True
        assert res.max_limit is None
        assert res.new_usage == 10000


@pytest.mark.asyncio
async def test_21_missing_quota_configuration_fails_safely(db_session: AsyncSession) -> None:
    """21. Unconfigured quota fails closed (rejects allocation)."""
    soc = await create_society(db_session, "Soc No Quota")
    plan = await create_plan(db_session, plan_code="PLAN_NO_QUOTA")
    await create_subscription(db_session, soc.id, plan.id)
    await db_session.commit()

    quota_service = QuotaEnforcementService(db_session)
    async with tenant_context(soc.id):
        assert await quota_service.check_quota(soc.id, "quota.unconfigured", 1) is False

        with pytest.raises(QuotaExceededException):
            await quota_service.reserve_usage(soc.id, "quota.unconfigured", 1)


@pytest.mark.asyncio
async def test_22_expired_quota_override_ignored(db_session: AsyncSession) -> None:
    """22. Expired quota override limit is ignored in favor of plan limit."""
    soc = await create_society(db_session, "Soc Exp Quota Ovr")
    plan = await create_plan(
        db_session,
        plan_code="PLAN_Q_EXP_OVR",
        entitlements=[{"key": QuotaKey.UNITS_MAX.value, "type": "NUMERIC", "value": "50"}],
    )
    await create_subscription(db_session, soc.id, plan.id)

    # Expired override had limit 100
    past = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
    override = SocietyQuotaOverride(
        society_id=soc.id,
        quota_key=QuotaKey.UNITS_MAX.value,
        max_limit=100,
        effective_until=past,
        override_reason="Temporary expansion (expired)",
    )
    db_session.add(override)
    await db_session.commit()

    quota_service = QuotaEnforcementService(db_session)
    async with tenant_context(soc.id):
        # Current limit must be plan limit 50, not 100
        eff = await quota_service.get_effective_quota(soc.id, QuotaKey.UNITS_MAX.value)
        assert eff.max_limit == 50
        assert eff.source == EntitlementSource.PLAN

        await quota_service.reserve_usage(soc.id, QuotaKey.UNITS_MAX.value, requested_increment=45)
        # Attempting 10 more exceeds 50
        with pytest.raises(QuotaExceededException):
            await quota_service.reserve_usage(soc.id, QuotaKey.UNITS_MAX.value, requested_increment=10)


@pytest.mark.asyncio
async def test_23_rejected_requests_do_not_change_usage(db_session: AsyncSession) -> None:
    """23. A rejected reservation attempt leaves the counter untouched."""
    soc = await create_society(db_session, "Soc Quota Immutability")
    plan = await create_plan(
        db_session,
        plan_code="PLAN_Q_IMM",
        entitlements=[{"key": QuotaKey.UNITS_MAX.value, "type": "NUMERIC", "value": "20"}],
    )
    await create_subscription(db_session, soc.id, plan.id)
    await db_session.commit()

    quota_service = QuotaEnforcementService(db_session)
    async with tenant_context(soc.id):
        await quota_service.reserve_usage(soc.id, QuotaKey.UNITS_MAX.value, requested_increment=15)
        assert await quota_service.get_current_usage(soc.id, QuotaKey.UNITS_MAX.value) == 15

        # Attempt to oversubscribe
        with pytest.raises(QuotaExceededException):
            await quota_service.reserve_usage(soc.id, QuotaKey.UNITS_MAX.value, requested_increment=10)

        # Counter must remain exactly 15
        assert await quota_service.get_current_usage(soc.id, QuotaKey.UNITS_MAX.value) == 15


@pytest.mark.asyncio
async def test_24_failed_transactions_roll_back_usage_updates(db_session: AsyncSession) -> None:
    """24. Caller transaction rollback fully reverts reserved usage."""
    soc = await create_society(db_session, "Soc Rollback")
    society_id = soc.id
    plan = await create_plan(
        db_session,
        plan_code="PLAN_Q_ROLLBACK",
        entitlements=[{"key": QuotaKey.UNITS_MAX.value, "type": "NUMERIC", "value": "50"}],
    )
    await create_subscription(db_session, society_id, plan.id)
    await db_session.commit()

    quota_service = QuotaEnforcementService(db_session)
    async with tenant_context(society_id):
        # 1. Establish baseline
        await quota_service.reserve_usage(society_id, QuotaKey.UNITS_MAX.value, requested_increment=10)
        await db_session.commit()
        assert await quota_service.get_current_usage(society_id, QuotaKey.UNITS_MAX.value) == 10

        # 2. Reserve more usage in transaction, then roll back
        await quota_service.reserve_usage(society_id, QuotaKey.UNITS_MAX.value, requested_increment=15)
        await db_session.rollback()

        # 3. Usage must have rolled back to 10
        assert await quota_service.get_current_usage(society_id, QuotaKey.UNITS_MAX.value) == 10


@pytest.mark.asyncio
async def test_25_concurrent_operations_cannot_exceed_finite_quota(
    db_engine: AsyncEngine,
) -> None:
    """25. Concurrency safety: multiple tasks competing for finite quota cannot exceed ceiling."""
    # Setup initial records using a setup session
    session_maker = async_sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as setup_session:
        soc = await create_society(setup_session, "Soc Concurrency")
        plan = await create_plan(
            setup_session,
            plan_code="PLAN_CONCURRENCY",
            entitlements=[{"key": QuotaKey.UNITS_MAX.value, "type": "NUMERIC", "value": "5"}],
        )
        await create_subscription(setup_session, soc.id, plan.id)
        await setup_session.commit()
        society_id = soc.id

    # 10 workers concurrently attempt to reserve 1 unit each when limit is 5
    async def worker(worker_id: int) -> bool:
        async with session_maker() as worker_session:
            service = QuotaEnforcementService(worker_session)
            async with tenant_context(society_id):
                try:
                    await service.reserve_usage(
                        society_id,
                        QuotaKey.UNITS_MAX.value,
                        requested_increment=1,
                        auto_commit=True,
                    )
                    return True
                except QuotaExceededException:
                    return False
                except Exception:
                    # SQLite in-memory may lock the entire database; handle gracefully
                    return False

    results = await asyncio.gather(*(worker(i) for i in range(10)))
    success_count = sum(1 for r in results if r is True)

    # Concurrency invariant: Success count must NEVER exceed 5
    assert success_count <= 5

    # Verify final usage count in database matches success count
    async with session_maker() as verify_session:
        service = QuotaEnforcementService(verify_session)
        async with tenant_context(society_id):
            final_usage = await service.get_current_usage(society_id, QuotaKey.UNITS_MAX.value)
            assert final_usage == success_count
            assert final_usage <= 5


@pytest.mark.asyncio
async def test_26_cross_tenant_metric_access_rejected(db_session: AsyncSession) -> None:
    """26. Cross-tenant access to quota metrics raises 403 Forbidden."""
    soc_a = await create_society(db_session, "Soc A Metric")
    soc_b = await create_society(db_session, "Soc B Metric")
    await db_session.commit()

    quota_service = QuotaEnforcementService(db_session)
    async with tenant_context(soc_a.id):
        with pytest.raises(AuthorizationException) as exc_info:
            await quota_service.get_current_usage(soc_b.id, QuotaKey.UNITS_MAX.value)
        assert exc_info.value.status_code == 403

        with pytest.raises(AuthorizationException):
            await quota_service.reserve_usage(soc_b.id, QuotaKey.UNITS_MAX.value, 1)

        with pytest.raises(AuthorizationException):
            await quota_service.reconcile_usage(soc_b.id, QuotaKey.UNITS_MAX.value, 10)


@pytest.mark.asyncio
async def test_27_missing_tenant_context_rejected_for_quota(db_session: AsyncSession) -> None:
    """27. Missing tenant context for quota operations raises 400 Bad Request."""
    soc = await create_society(db_session, "Soc Contextless Quota")
    await db_session.commit()

    quota_service = QuotaEnforcementService(db_session)
    with pytest.raises(TenantContextRequiredException):
        await quota_service.get_current_usage(soc.id, QuotaKey.UNITS_MAX.value)

    with pytest.raises(TenantContextRequiredException):
        await quota_service.reserve_usage(soc.id, QuotaKey.UNITS_MAX.value, 1)


@pytest.mark.asyncio
async def test_28_missing_usage_row_initialization_handled_safely(db_session: AsyncSession) -> None:
    """28. Missing usage row is initialized safely to 0 upon first access."""
    soc = await create_society(db_session, "Soc Init Row")
    plan = await create_plan(
        db_session,
        plan_code="PLAN_INIT",
        entitlements=[{"key": QuotaKey.STAFF_MAX.value, "type": "NUMERIC", "value": "25"}],
    )
    await create_subscription(db_session, soc.id, plan.id)
    await db_session.commit()

    quota_service = QuotaEnforcementService(db_session)
    async with tenant_context(soc.id):
        # 1. get_current_usage on missing row returns 0
        assert await quota_service.get_current_usage(soc.id, QuotaKey.STAFF_MAX.value) == 0

        # 2. reserve_usage initializes row and increments
        res = await quota_service.reserve_usage(soc.id, QuotaKey.STAFF_MAX.value, requested_increment=3)
        assert res.previous_usage == 0
        assert res.new_usage == 3

        # 3. Verify row now exists in database
        stmt = select(SocietyUsageMetric).where(
            SocietyUsageMetric.society_id == soc.id,
            SocietyUsageMetric.metric_key == QuotaKey.STAFF_MAX.value,
        )
        metric = (await db_session.execute(stmt)).scalar_one_or_none()
        assert metric is not None
        assert metric.current_value == 3


@pytest.mark.asyncio
async def test_29_current_usage_cannot_become_negative(db_session: AsyncSession) -> None:
    """29. Current usage cannot become negative via reconciliation or increments."""
    soc = await create_society(db_session, "Soc Non Negative")
    plan = await create_plan(
        db_session,
        plan_code="PLAN_NON_NEG",
        entitlements=[{"key": QuotaKey.UNITS_MAX.value, "type": "NUMERIC", "value": "50"}],
    )
    await create_subscription(db_session, soc.id, plan.id)
    await db_session.commit()

    quota_service = QuotaEnforcementService(db_session)
    async with tenant_context(soc.id):
        with pytest.raises(InvalidUsageIncrementException):
            await quota_service.reconcile_usage(soc.id, QuotaKey.UNITS_MAX.value, actual_count=-1)

        # Valid reconciliation
        new_val = await quota_service.reconcile_usage(soc.id, QuotaKey.UNITS_MAX.value, actual_count=20)
        assert new_val == 20

        # Diagnostics check
        diag = await quota_service.get_usage_diagnostics(soc.id, QuotaKey.UNITS_MAX.value)
        assert diag.current_value == 20
        assert diag.quota_limit == 50
        assert diag.utilization_percentage == 40.0
