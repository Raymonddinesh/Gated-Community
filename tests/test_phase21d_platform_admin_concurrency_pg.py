"""Live PostgreSQL 16 Concurrency, Pessimistic Row Locking, Advisory Locks, and FORCE RLS Tests for Phase 21D.

Executes live concurrent multi-session tests against PostgreSQL 16:
1. Pessimistic Row Locking on Suspension:
   - Concurrent suspend requests serialize on SELECT ... FOR UPDATE.
   - Exactly one succeeds (200 OK), the other conflicts (409 Conflict - SOCIETY_ALREADY_SUSPENDED).
   - Atomic AuditLog creation with zero duplicate actions.
2. Pessimistic Row Locking on Reactivation:
   - Concurrent reactivate requests serialize on SELECT ... FOR UPDATE.
   - Exactly one succeeds (200 OK), the other conflicts (409 Conflict - SOCIETY_ALREADY_ACTIVE).
   - Atomic AuditLog creation with zero duplicate actions.
3. Advisory Lock Serialization on Provisioning Retry:
   - Concurrent retries serialize via 64-bit pg_try_advisory_xact_lock.
   - In-progress retry yields 409 Conflict with code PROVISIONING_IN_PROGRESS and Retry-After: 5.
4. Mandatory Condition 1: FORCE RLS Compliance under Unprivileged app_user (NOBYPASSRLS):
   - society_provisioning_logs table enforces FORCE ROW LEVEL SECURITY.
   - Queries without tenant context return 0 rows.
   - PlatformAdminService.get_provisioning_diagnostics establishes transaction-local tenant context
     via set_db_tenant_context(session, society_id) and successfully reads logs under unprivileged app_user.
   - Cross-tenant isolation guarantees Tenant A cannot view Tenant B's provisioning logs.
5. Connection Pool Context Cleanup:
   - Confirms transaction-local parameter (is_local=true) reverts across commit, rollback, and pooling.
"""

import asyncio
import logging
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.src.database.models.audit import AuditLog
from apps.api.src.database.models.authorization import Role
from apps.api.src.database.models.identity import User
from apps.api.src.database.models.society import Society
from apps.api.src.database.models.subscription import (
    PlatformSubscriptionPlan,
    SocietyProvisioningLog,
    SubscriptionPlanEntitlement,
)
from apps.api.src.database.session import set_db_tenant_context
from apps.api.src.subscriptions import (
    FeatureKey,
    InitialAdminPayload,
    InitialSpatialPayload,
    ProvisioningConflictException,
    ProvisionSocietyRequest,
    QuotaKey,
    SocietyAlreadyActiveException,
    SocietyAlreadySuspendedException,
    SocietyProvisioningEngine,
)
from apps.api.src.subscriptions.platform_admin_service import PlatformAdminService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_phase21d_concurrency_pg")

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
async def pg_session_factory(pg_engine):
    """Factory yielding isolated sessions connected to PostgreSQL 16."""
    return async_sessionmaker(bind=pg_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def ensure_pg_baseline_data(pg_session_factory):
    """Ensure baseline roles and plans exist in PostgreSQL database."""
    async with pg_session_factory() as session:
        # Ensure SUPER_ADMIN role
        super_res = await session.execute(
            select(Role).where(Role.code == "SUPER_ADMIN", Role.scope_type == "PLATFORM")
        )
        if not super_res.scalar_one_or_none():
            session.add(
                Role(
                    code="SUPER_ADMIN",
                    name="Platform Super Administrator",
                    scope_type="PLATFORM",
                    is_system_role=True,
                )
            )

        # Ensure SOCIETY_ADMIN role
        role_res = await session.execute(
            select(Role).where(Role.code == "SOCIETY_ADMIN", Role.scope_type == "SOCIETY")
        )
        if not role_res.scalar_one_or_none():
            session.add(
                Role(
                    code="SOCIETY_ADMIN",
                    name="Society Administrator",
                    scope_type="SOCIETY",
                    is_system_role=True,
                )
            )

        # Ensure STANDARD plan
        std_res = await session.execute(
            select(PlatformSubscriptionPlan).where(PlatformSubscriptionPlan.plan_code == "STANDARD")
        )
        std_plan = std_res.scalar_one_or_none()
        if not std_plan:
            std_plan = PlatformSubscriptionPlan(
                plan_code="STANDARD",
                display_name="Standard Plan",
                monthly_price=1999.00,
                annual_price=19990.00,
                currency_code="INR",
                trial_days=14,
                is_active=True,
            )
            session.add(std_plan)
            await session.flush()

            session.add_all([
                SubscriptionPlanEntitlement(
                    plan_id=std_plan.id,
                    entitlement_key=FeatureKey.GOVERNANCE.value,
                    entitlement_type="BOOLEAN",
                    entitlement_value="true",
                ),
                SubscriptionPlanEntitlement(
                    plan_id=std_plan.id,
                    entitlement_key=QuotaKey.UNITS_MAX.value,
                    entitlement_type="NUMERIC",
                    entitlement_value="100",
                ),
            ])

        # Ensure Super Admin User
        admin_user_res = await session.execute(
            select(User).where(User.email == "superadmin-pg@platform.local")
        )
        if not admin_user_res.scalar_one_or_none():
            admin_user = User(
                email="superadmin-pg@platform.local",
                first_name="Platform",
                last_name="SuperAdmin",
                display_name="PG SuperAdmin",
                status="ACTIVE",
            )
            session.add(admin_user)

        await session.commit()


def make_pg_provision_request(legal_name: str | None = None) -> ProvisionSocietyRequest:
    suffix = uuid.uuid4().hex[:6]
    return ProvisionSocietyRequest(
        provisioning_request_id=uuid.uuid4(),
        legal_name=legal_name or f"PG Test Society {suffix}",
        display_name=f"PG Society {suffix}",
        registration_number=f"REG-PG-{suffix}",
        address_line1="456 Database Parkway",
        city="Bengaluru",
        state="Karnataka",
        country="IN",
        postal_code="560001",
        plan_code="STANDARD",
        admin_user=InitialAdminPayload(
            email=f"pgadmin.{suffix}@example.com",
            first_name="Platform",
            last_name="Tester",
        ),
        spatial=InitialSpatialPayload(
            create_default_block=True,
            default_block_name="Tower Alpha",
        ),
    )


# ==============================================================================
# 1. LIVE CONCURRENCY: PESSIMISTIC ROW LOCKING (SUSPEND / REACTIVATE)
# ==============================================================================


@pytest.mark.asyncio
async def test_pg_concurrent_suspend_pessimistic_locking(
    pg_session_factory, ensure_pg_baseline_data: None
):
    """Verify that concurrent suspend requests serialize on SELECT FOR UPDATE row lock.

    Guarantees:
    - Worker 1 and Worker 2 concurrently invoke suspend_society.
    - One worker locks the row, validates ACTIVE status, transitions to SUSPENDED, and commits.
    - The other worker blocks on the row lock, wakes up after commit, re-reads status as SUSPENDED,
      and raises SocietyAlreadySuspendedException (409 Conflict).
    - Exactly one AuditLog record is created.
    """
    req = make_pg_provision_request()
    async with pg_session_factory() as session:
        engine = SocietyProvisioningEngine(session)
        prov_res = await engine.provision_society(req)
        society_id = prov_res.society_id

        admin_res = await session.execute(
            select(User).where(User.email == "superadmin-pg@platform.local")
        )
        admin_user = admin_res.scalar_one()
        actor_id = admin_user.id

    reason = "Concurrent test administrative suspension for compliance check."

    async def attempt_suspend(worker_id: int):
        async with pg_session_factory() as session:
            service = PlatformAdminService(session)
            try:
                res = await service.suspend_society(
                    society_id=society_id,
                    actor_user_id=actor_id,
                    reason=f"{reason} (worker {worker_id})",
                )
                return ("SUCCESS", res)
            except SocietyAlreadySuspendedException as exc:
                return ("CONFLICT", exc)

    results = await asyncio.gather(attempt_suspend(1), attempt_suspend(2))
    statuses = [r[0] for r in results]

    assert "SUCCESS" in statuses
    assert "CONFLICT" in statuses

    # Verify final state in database
    async with pg_session_factory() as session:
        soc = await session.get(Society, society_id)
        assert soc is not None
        assert soc.status == "SUSPENDED"

        # Exactly 1 suspension audit log
        audit_count = (
            await session.execute(
                select(func.count(AuditLog.id)).where(
                    AuditLog.society_id == society_id,
                    AuditLog.action == "SOCIETY_SUSPENDED",
                )
            )
        ).scalar()
        assert audit_count == 1


@pytest.mark.asyncio
async def test_pg_concurrent_reactivate_pessimistic_locking(
    pg_session_factory, ensure_pg_baseline_data: None
):
    """Verify that concurrent reactivate requests serialize on SELECT FOR UPDATE row lock.

    Guarantees:
    - Target society is initially SUSPENDED.
    - Worker 1 and Worker 2 concurrently invoke reactivate_society.
    - One worker locks the row, validates SUSPENDED status, transitions to ACTIVE, and commits.
    - The other worker blocks on the row lock, wakes up after commit, re-reads status as ACTIVE,
      and raises SocietyAlreadyActiveException (409 Conflict).
    - Exactly one AuditLog record is created.
    """
    # 1. Provision and suspend society
    req = make_pg_provision_request()
    async with pg_session_factory() as session:
        engine = SocietyProvisioningEngine(session)
        prov_res = await engine.provision_society(req)
        society_id = prov_res.society_id

        admin_res = await session.execute(
            select(User).where(User.email == "superadmin-pg@platform.local")
        )
        admin_user = admin_res.scalar_one()
        actor_id = admin_user.id

    async with pg_session_factory() as session:
        service = PlatformAdminService(session)
        await service.suspend_society(
            society_id=society_id,
            actor_user_id=actor_id,
            reason="Pre-test suspension for reactivation concurrency test.",
        )

    # 2. Concurrently attempt reactivation
    reason = "Terms violation resolved following committee formal undertaking."

    async def attempt_reactivate(worker_id: int):
        async with pg_session_factory() as session:
            service = PlatformAdminService(session)
            try:
                res = await service.reactivate_society(
                    society_id=society_id,
                    actor_user_id=actor_id,
                    reason=f"{reason} (worker {worker_id})",
                )
                return ("SUCCESS", res)
            except SocietyAlreadyActiveException as exc:
                return ("CONFLICT", exc)

    results = await asyncio.gather(attempt_reactivate(1), attempt_reactivate(2))
    statuses = [r[0] for r in results]

    assert "SUCCESS" in statuses
    assert "CONFLICT" in statuses

    # Verify final state in database
    async with pg_session_factory() as session:
        soc = await session.get(Society, society_id)
        assert soc is not None
        assert soc.status == "ACTIVE"

        # Exactly 1 reactivation audit log
        audit_count = (
            await session.execute(
                select(func.count(AuditLog.id)).where(
                    AuditLog.society_id == society_id,
                    AuditLog.action == "SOCIETY_REACTIVATED",
                )
            )
        ).scalar()
        assert audit_count == 1


# ==============================================================================
# 2. LIVE CONCURRENCY: ADVISORY LOCK SERIALIZATION ON PROVISIONING RETRY
# ==============================================================================


@pytest.mark.asyncio
async def test_pg_advisory_lock_retry_serialization(
    pg_session_factory, ensure_pg_baseline_data: None
):
    """Verify that concurrent provisioning retry attempts serialize via advisory locks.

    Guarantees:
    - Worker 1 holds pg_try_advisory_xact_lock for provisioning_retry:{society_id}.
    - Worker 2 attempts retry concurrently -> pg_try_advisory_xact_lock returns FALSE.
    - Worker 2 immediately rolls back and raises ProvisioningConflictException with
      code PROVISIONING_IN_PROGRESS, HTTP 409, and Retry-After: 5 header.
    """
    society_id = uuid.uuid4()
    barrier = asyncio.Event()
    worker2_result: dict[str, object] = {}

    async def worker1():
        async with pg_session_factory() as session:
            service = PlatformAdminService(session)
            # Worker 1 acquires the advisory lock
            await service._try_acquire_advisory_lock(
                f"provisioning_retry:{society_id}",
                f"provisioning retry for society '{society_id}'",
            )
            # Signal worker 2 that lock is held
            barrier.set()
            # Hold lock while worker 2 attempts
            await asyncio.sleep(0.5)
            # Release on session exit (rollback/commit)

    async def worker2():
        await barrier.wait()
        async with pg_session_factory() as session:
            service = PlatformAdminService(session)
            try:
                await service._try_acquire_advisory_lock(
                    f"provisioning_retry:{society_id}",
                    f"provisioning retry for society '{society_id}'",
                )
                worker2_result["status"] = "UNEXPECTED_LOCK_ACQUIRED"
            except ProvisioningConflictException as exc:
                worker2_result["status"] = "CONFLICT"
                worker2_result["code"] = exc.code
                worker2_result["status_code"] = exc.status_code
                worker2_result["retry_after"] = getattr(exc, "headers", {}).get("Retry-After")

    await asyncio.gather(worker1(), worker2())

    assert worker2_result["status"] == "CONFLICT"
    assert worker2_result["code"] == "PROVISIONING_IN_PROGRESS"
    assert worker2_result["status_code"] == 409
    assert worker2_result["retry_after"] == "5"


# ==============================================================================
# 3. MANDATORY CONDITION 1: FORCE RLS COMPLIANCE UNDER UNPRIVILEGED app_user
# ==============================================================================


@pytest.mark.asyncio
async def test_pg_mandatory_condition_1_force_rls_diagnostics(
    pg_session_factory, ensure_pg_baseline_data: None
):
    """Verify that get_provisioning_diagnostics respects FORCE RLS under unprivileged app_user.

    Guarantees:
    - Table society_provisioning_logs has FORCE ROW LEVEL SECURITY enabled.
    - An unprivileged database user (app_user, NOBYPASSRLS) querying without context sees 0 rows.
    - PlatformAdminService.get_provisioning_diagnostics establishes transaction-local tenant context
      (app.current_society_id) via set_db_tenant_context, successfully reading only target society's logs.
    - After completion, context does not leak.
    """
    # 1. Provision two societies (A and B)
    req_a = make_pg_provision_request()
    req_b = make_pg_provision_request()

    async with pg_session_factory() as session:
        engine = SocietyProvisioningEngine(session)
        resp_a = await engine.provision_society(req_a)
        soc_a_id = resp_a.society_id

    async with pg_session_factory() as session:
        engine = SocietyProvisioningEngine(session)
        resp_b = await engine.provision_society(req_b)
        soc_b_id = resp_b.society_id

    # 2. Raw query without tenant context under app_user -> returns 0 rows (FORCE RLS)
    async with pg_session_factory() as session:
        await session.execute(text("SET ROLE app_user"))
        raw_logs = (
            await session.execute(
                select(SocietyProvisioningLog).where(SocietyProvisioningLog.society_id == soc_a_id)
            )
        ).scalars().all()
        assert len(raw_logs) == 0, "FORCE RLS violation: logs accessible without tenant context!"

    # 3. Call get_provisioning_diagnostics for Society A under app_user
    async with pg_session_factory() as session:
        await session.execute(text("SET ROLE app_user"))
        service = PlatformAdminService(session)
        diag_a = await service.get_provisioning_diagnostics(soc_a_id)

        assert diag_a.society_id == soc_a_id
        assert len(diag_a.steps) >= 8
        assert all(step.status == "COMPLETED" for step in diag_a.steps)
        step_keys = [s.step_key for s in diag_a.steps]
        assert "VALIDATE_INPUT" in step_keys
        assert "FINALIZE_ONBOARDING" in step_keys

        # 4. In the same session, Society B's logs must NOT be visible (cross-tenant isolation)
        raw_b_logs = (
            await session.execute(
                select(SocietyProvisioningLog).where(SocietyProvisioningLog.society_id == soc_b_id)
            )
        ).scalars().all()
        assert len(raw_b_logs) == 0, "Isolation violation: Society A context read Society B logs!"

        # Commit session
        await session.commit()

        # 5. After commit, context is cleared (LOCAL=true)
        raw_a_logs_after = (
            await session.execute(
                select(SocietyProvisioningLog).where(SocietyProvisioningLog.society_id == soc_a_id)
            )
        ).scalars().all()
        assert len(raw_a_logs_after) == 0, "Context leak: tenant context remained after commit!"


# ==============================================================================
# 4. CONNECTION POOL ISOLATION & CLEANUP
# ==============================================================================


@pytest.mark.asyncio
async def test_pg_connection_pool_tenant_context_cleanup(
    pg_session_factory, ensure_pg_baseline_data: None
):
    """Verify that tenant context set with is_local=true never leaks to subsequent pooled connections."""
    soc_id = uuid.uuid4()

    # Session 1: sets tenant context and commits
    async with pg_session_factory() as session1:
        await session1.execute(text("SET ROLE app_user"))
        await set_db_tenant_context(session1, soc_id)
        val = (await session1.execute(text("SELECT current_setting('app.current_society_id', true)"))).scalar()
        assert val == str(soc_id)
        await session1.commit()

    # Session 2: newly acquired session from the pool must NOT have the tenant context
    async with pg_session_factory() as session2:
        await session2.execute(text("SET ROLE app_user"))
        val2 = (await session2.execute(text("SELECT current_setting('app.current_society_id', true)"))).scalar()
        assert val2 == "" or val2 is None, "Security violation: app.current_society_id leaked across pooled sessions!"
