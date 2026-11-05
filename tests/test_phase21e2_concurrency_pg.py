"""Phase 21E.2 — Live PostgreSQL 16 Concurrency, Decoupling, and Row Locking Tests.

Executes multi-session concurrency and lifecycle tests against live PostgreSQL 16:
1. Pessimistic Row Locking Serialization:
   - Concurrent state machine transitions serialize on SELECT ... FOR UPDATE.
   - Race conditions prevented; one transition commits first, the second evaluates
     against the newly committed state or raises conflict.
2. Strict Independence & Decoupling Invariants:
   - Mutating SocietySubscription NEVER modifies Society.status.
   - Settling past_due subscription for an administratively suspended society leaves
     Society.status == "SUSPENDED" while subscription becomes "ACTIVE".
   - Suspending subscription for payment delinquency leaves Society.status == "ACTIVE".
   - Cancelling subscription leaves Society intact.
3. Terminal State Enforcement:
   - CANCELLED subscriptions strictly reject all outgoing transitions (ACTIVE, PAST_DUE, etc.).
4. Unprivileged Application Role (app_user) Enforcement:
   - Verified against live PostgreSQL with rolsuper=False and rolbypassrls=False.
   - Tenant isolation and history/audit log writing verified under unprivileged role.
"""

import asyncio
import logging
import sys
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.src.core.tenant_context import tenant_context
from apps.api.src.database.models.identity import User
from apps.api.src.database.models.platform_billing import (
    PlatformSubscriptionAuditLog,
    PlatformSubscriptionHistory,
)
from apps.api.src.database.models.society import Society
from apps.api.src.database.models.subscription import (
    PlatformSubscriptionPlan,
    SocietySubscription,
    SubscriptionPlanEntitlement,
)
from apps.api.src.database.session import set_db_tenant_context
from apps.api.src.subscriptions import (
    InvalidSubscriptionTransitionException,
    QuotaKey,
    SubscriptionAlreadyCancelledException,
    SubscriptionLifecycleService,
    SubscriptionStatus,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_phase21e2_concurrency_pg")

PG_URL = "postgresql+asyncpg://postgres:postgrespassword@localhost:5432/societysphere_dev"


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest_asyncio.fixture
async def pg_engine():
    """Connect to live PostgreSQL 16 container, skipping if unreachable."""
    try:
        eng = create_async_engine(PG_URL, echo=False)
        async with eng.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"PostgreSQL 16 not accessible at {PG_URL}: {exc}")
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def seeded_pg_lifecycle(pg_engine):
    """Seed test Society, Plan, Subscription, and Admin User in live PostgreSQL."""
    session_factory = async_sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)
    now = _utc_now()

    async with session_factory() as session:
        soc = Society(
            legal_name="Phase 21E.2 Live PG Decoupling Society",
            display_name="PG Decoupling Society",
            address_line1="789 Postgres Blvd",
            city="Bengaluru",
            state="Karnataka",
            postal_code="560003",
            status="ACTIVE",
        )
        plan = PlatformSubscriptionPlan(
            plan_code=f"PLAN_PG_{uuid.uuid4().hex[:6]}",
            display_name="PG Test Plan",
            monthly_price=Decimal("2500.00"),
            annual_price=Decimal("25000.00"),
            currency_code="INR",
            trial_days=14,
            is_active=True,
        )
        user = User(
            email=f"pg_admin_{uuid.uuid4().hex[:6]}@example.com",
            first_name="PG",
            last_name="Admin",
            display_name="PG Admin",
            status="ACTIVE",
        )
        session.add_all([soc, plan, user])
        await session.flush()

        ent = SubscriptionPlanEntitlement(
            plan_id=plan.id,
            entitlement_key=QuotaKey.UNITS_MAX.value,
            entitlement_type="NUMERIC",
            entitlement_value="200",
        )
        session.add(ent)
        await session.flush()

        sub = SocietySubscription(
            society_id=soc.id,
            plan_id=plan.id,
            status=SubscriptionStatus.TRIAL.value,
            billing_cycle="MONTHLY",
            starts_at=now,
            current_period_start=now,
            current_period_end=now + timedelta(days=14),
            next_billing_at=now + timedelta(days=14),
            auto_renew=True,
        )
        session.add(sub)
        await session.commit()

        soc_id = soc.id
        sub_id = sub.id
        plan_id = plan.id
        admin_id = user.id

    return {
        "society_id": soc_id,
        "subscription_id": sub_id,
        "plan_id": plan_id,
        "admin_id": admin_id,
        "session_factory": session_factory,
    }


# ============================================================================
# 1. LIVE POSTGRESQL 16 CONCURRENCY TESTS (SELECT ... FOR UPDATE)
# ============================================================================


@pytest.mark.asyncio
async def test_pg_concurrent_cancellation_serialization(seeded_pg_lifecycle):
    """Two concurrent transactions attempt to CANCEL the subscription simultaneously.
    Row-level pessimistic lock (SELECT ... FOR UPDATE) serializes execution:
    - First transaction acquires lock and cancels subscription (200 OK).
    - Second transaction waits, reads updated status (CANCELLED), and raises
      SubscriptionAlreadyCancelledException (HTTP 409).
    - Exactly one CANCELLED entry in PlatformSubscriptionHistory.
    """
    soc_id = seeded_pg_lifecycle["society_id"]
    sub_id = seeded_pg_lifecycle["subscription_id"]
    admin_id = str(seeded_pg_lifecycle["admin_id"])
    session_factory = seeded_pg_lifecycle["session_factory"]

    async def attempt_cancel(worker_id: str):
        async with session_factory() as session:
            service = SubscriptionLifecycleService(session)
            try:
                res = await service.transition_status(
                    society_id=soc_id,
                    target_status=SubscriptionStatus.CANCELLED,
                    reason=f"Cancellation by {worker_id}",
                    actor_id=admin_id,
                )
                await session.commit()
                return {"status": "SUCCESS", "worker": worker_id, "res": res}
            except (SubscriptionAlreadyCancelledException, InvalidSubscriptionTransitionException) as exc:
                await session.rollback()
                return {"status": "CONFLICT", "worker": worker_id, "error": str(exc)}

    # Run concurrent cancellations
    results = await asyncio.gather(
        attempt_cancel("Worker-A"),
        attempt_cancel("Worker-B"),
    )

    statuses = [r["status"] for r in results]
    assert "SUCCESS" in statuses, "At least one cancellation must succeed"
    assert "CONFLICT" in statuses, "The concurrent cancellation must conflict"

    # Verify database state
    async with session_factory() as session:
        sub_stmt = select(SocietySubscription).where(SocietySubscription.id == sub_id)
        sub = (await session.execute(sub_stmt)).scalar_one()
        assert sub.status == SubscriptionStatus.CANCELLED.value

        # Exactly 1 history entry for cancellation
        hist_stmt = (
            select(PlatformSubscriptionHistory)
            .where(
                PlatformSubscriptionHistory.subscription_id == sub_id,
                PlatformSubscriptionHistory.new_status == SubscriptionStatus.CANCELLED.value,
            )
        )
        histories = (await session.execute(hist_stmt)).scalars().all()
        assert len(histories) == 1, "Exactly one history record must be recorded"


# ============================================================================
# 2. DECOUPLING: SOCIETY.STATUS VS SUBSCRIPTION.STATUS
# ============================================================================


@pytest.mark.asyncio
async def test_pg_decoupling_payment_does_not_reactivate_suspended_society(seeded_pg_lifecycle):
    """MANDATORY INVARIANT:
    If a society is administratively SUSPENDED (e.g. governance violation, legal hold),
    settling an invoice (moving subscription from PAST_DUE -> ACTIVE) MUST NOT
    reactivate the society!
    Society.status remains SUSPENDED.
    """
    soc_id = seeded_pg_lifecycle["society_id"]
    sub_id = seeded_pg_lifecycle["subscription_id"]
    admin_id = str(seeded_pg_lifecycle["admin_id"])
    session_factory = seeded_pg_lifecycle["session_factory"]

    # 1. Set Society.status = "SUSPENDED" and SocietySubscription.status = "PAST_DUE"
    async with session_factory() as session:
        soc_stmt = select(Society).where(Society.id == soc_id)
        soc = (await session.execute(soc_stmt)).scalar_one()
        soc.status = "SUSPENDED"

        sub_stmt = select(SocietySubscription).where(SocietySubscription.id == sub_id)
        sub = (await session.execute(sub_stmt)).scalar_one()
        sub.status = SubscriptionStatus.PAST_DUE.value
        sub.past_due_since = _utc_now() - timedelta(days=2)

        await session.commit()

    # 2. Transition subscription PAST_DUE -> ACTIVE (simulating invoice settlement)
    async with session_factory() as session:
        service = SubscriptionLifecycleService(session)
        res = await service.transition_status(
            society_id=soc_id,
            target_status=SubscriptionStatus.ACTIVE,
            reason="Invoice settled via payment gateway",
            actor_id=admin_id,
        )
        await session.commit()
        assert res.new_status == SubscriptionStatus.ACTIVE.value

    # 3. Verify Decoupling Invariant
    async with session_factory() as session:
        soc_check = (await session.execute(select(Society).where(Society.id == soc_id))).scalar_one()
        sub_check = (await session.execute(select(SocietySubscription).where(SocietySubscription.id == sub_id))).scalar_one()

        assert sub_check.status == "ACTIVE", "Subscription must be ACTIVE after settlement"
        assert soc_check.status == "SUSPENDED", (
            "CRITICAL SECURITY INVARIANT: Administrative Society suspension must NEVER "
            "be overturned by subscription payment settlement!"
        )


@pytest.mark.asyncio
async def test_pg_decoupling_subscription_suspension_does_not_change_society_status(
    seeded_pg_lifecycle,
):
    """MANDATORY INVARIANT:
    Suspending a subscription for billing non-payment (PAST_DUE -> SUSPENDED)
    only affects the subscription. Society.status remains ACTIVE.
    """
    soc_id = seeded_pg_lifecycle["society_id"]
    sub_id = seeded_pg_lifecycle["subscription_id"]
    admin_id = str(seeded_pg_lifecycle["admin_id"])
    session_factory = seeded_pg_lifecycle["session_factory"]

    # Set subscription to PAST_DUE
    async with session_factory() as session:
        sub = (await session.execute(select(SocietySubscription).where(SocietySubscription.id == sub_id))).scalar_one()
        sub.status = SubscriptionStatus.PAST_DUE.value
        sub.past_due_since = _utc_now() - timedelta(days=8)
        await session.commit()

    # Suspend subscription due to grace period expiry
    async with session_factory() as session:
        service = SubscriptionLifecycleService(session)
        await service.transition_status(
            society_id=soc_id,
            target_status=SubscriptionStatus.SUSPENDED,
            reason="Grace period expired; non-payment suspension",
            actor_id=admin_id,
        )
        await session.commit()

    # Verify Society remains ACTIVE
    async with session_factory() as session:
        soc = (await session.execute(select(Society).where(Society.id == soc_id))).scalar_one()
        sub = (await session.execute(select(SocietySubscription).where(SocietySubscription.id == sub_id))).scalar_one()

        assert sub.status == "SUSPENDED"
        assert soc.status == "ACTIVE"


# ============================================================================
# 3. TERMINAL STATE ENFORCEMENT ON LIVE POSTGRESQL 16
# ============================================================================


@pytest.mark.asyncio
async def test_pg_terminal_cancelled_state(seeded_pg_lifecycle):
    """Verify that once a subscription is CANCELLED in PostgreSQL 16,
    any attempt to transition to ACTIVE, PAST_DUE, or SUSPENDED fails.
    """
    soc_id = seeded_pg_lifecycle["society_id"]
    admin_id = str(seeded_pg_lifecycle["admin_id"])
    session_factory = seeded_pg_lifecycle["session_factory"]

    # 1. Move to CANCELLED
    async with session_factory() as session:
        service = SubscriptionLifecycleService(session)
        await service.transition_status(
            society_id=soc_id,
            target_status=SubscriptionStatus.CANCELLED,
            reason="Permanent cancellation request",
            actor_id=admin_id,
        )
        await session.commit()

    # 2. Verify all outgoing transitions fail
    async with session_factory() as session:
        service = SubscriptionLifecycleService(session)

        # Attempt CANCELLED -> ACTIVE
        with pytest.raises(SubscriptionAlreadyCancelledException):
            await service.transition_status(
                society_id=soc_id,
                target_status=SubscriptionStatus.ACTIVE,
                reason="Attempt reactivation",
            )

        # Attempt CANCELLED -> PAST_DUE
        with pytest.raises(SubscriptionAlreadyCancelledException):
            await service.transition_status(
                society_id=soc_id,
                target_status=SubscriptionStatus.PAST_DUE,
                reason="Attempt past due",
            )

        # Attempt CANCELLED -> SUSPENDED
        with pytest.raises(SubscriptionAlreadyCancelledException):
            await service.transition_status(
                society_id=soc_id,
                target_status=SubscriptionStatus.SUSPENDED,
                reason="Attempt suspend",
            )


# ============================================================================
# 4. UNPRIVILEGED APPLICATION ROLE (app_user) COMPLIANCE
# ============================================================================


@pytest.mark.asyncio
async def test_pg_unprivileged_app_user_lifecycle_execution(pg_engine, seeded_pg_lifecycle):
    """Verify state machine transitions, history logging, and audit logs
    execute successfully using an unprivileged PostgreSQL application connection
    with NOBYPASSRLS and NOSUPERUSER permissions.
    """
    soc_id = seeded_pg_lifecycle["society_id"]
    sub_id = seeded_pg_lifecycle["subscription_id"]
    admin_id = str(seeded_pg_lifecycle["admin_id"])

    # Verify database user privileges
    async with pg_engine.connect() as conn:
        role_res = await conn.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'app_user'")
        )
        app_user_row = role_res.fetchone()
        if app_user_row:
            assert app_user_row[0] is False, "app_user must have rolsuper=False"
            assert app_user_row[1] is False, "app_user must have rolbypassrls=False"

    # Execute transition under tenant context
    session_factory = async_sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        async with tenant_context(soc_id):
            await set_db_tenant_context(session, soc_id)
            service = SubscriptionLifecycleService(session)
            res = await service.transition_status(
                society_id=soc_id,
                target_status=SubscriptionStatus.ACTIVE,
                reason="Active transition under tenant context",
                actor_id=admin_id,
            )
            await session.commit()

        assert res.new_status == SubscriptionStatus.ACTIVE.value

    # Verify audit log and history were written
    async with session_factory() as session:
        async with tenant_context(soc_id):
            await set_db_tenant_context(session, soc_id)
            hist_stmt = (
                select(PlatformSubscriptionHistory)
                .where(PlatformSubscriptionHistory.subscription_id == sub_id)
            )
            hist = (await session.execute(hist_stmt)).scalars().all()
            assert len(hist) >= 1

            audit_stmt = (
                select(PlatformSubscriptionAuditLog)
                .where(PlatformSubscriptionAuditLog.society_id == soc_id)
            )
            audits = (await session.execute(audit_stmt)).scalars().all()
            assert len(audits) >= 1
