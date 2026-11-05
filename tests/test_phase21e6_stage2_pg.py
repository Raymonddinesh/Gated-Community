"""Phase 21E.6 — Stage 2: PostgreSQL 16 Advisory Locks, RLS & Horizontal Concurrency Tests.

Validates on live PostgreSQL 16:
1. 64-bit Transaction Advisory Locking:
   - Verifies pg_try_advisory_xact_lock(bigint) with compute_advisory_lock_key.
   - Proves mutual exclusion across concurrent PostgreSQL sessions.
2. PostgreSQL 16 FORCE ROW LEVEL SECURITY:
   - Verifies relrowsecurity=True and relforcerowsecurity=True on platform_dunning_attempts.
   - Unprivileged app_user (NOSUPERUSER, NOBYPASSRLS) fails closed without tenant context.
   - Enforces strict tenant isolation: Tenant A cannot read or write Tenant B's dunning attempts.
3. Multi-Worker Dunning Concurrency:
   - 4 concurrent workers executing process_dunning_batch against overdue subscriptions.
   - Proves zero deadlocks, zero duplicate attempts, and atomic milestone evaluation via
     SELECT ... FOR UPDATE SKIP LOCKED and advisory locks.
4. Multi-Worker Day 7 Suspension Concurrency:
   - 4 concurrent workers executing suspension on expired subscriptions.
   - Proves exactly one suspension transition per subscription, zero duplicate transitions.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.src.database.models.notifications import Notification
from apps.api.src.database.models.platform_billing import (
    PlatformDunningAttempt,
    PlatformInvoice,
)
from apps.api.src.database.models.society import Society
from apps.api.src.database.models.subscription import (
    PlatformSubscriptionPlan,
    SocietySubscription,
)
from apps.api.src.database.session import set_db_tenant_context
from apps.api.src.subscriptions.automation.dunning_service import (
    DunningEngineService,
    DunningStage,
    compute_advisory_lock_key,
)
from apps.api.src.subscriptions.automation.renewal_service import (
    AutomatedRenewalInvoicingService,
)
from apps.api.src.subscriptions.enums import SubscriptionStatus
from apps.api.src.subscriptions.invoicing.numbering import InvoiceNumberingService
from apps.api.src.subscriptions.invoicing.service import PlatformInvoiceService
from apps.api.src.subscriptions.tax import (
    GSTTaxEngine,
    PlaceOfSupplyService,
    tax_config_service,
)

PG_URL = "postgresql+asyncpg://postgres:postgrespassword@localhost:5432/societysphere_dev"


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest_asyncio.fixture
async def pg_engine():
    """Connect to live PostgreSQL 16, skipping if unavailable."""
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
async def ensure_app_user_role(pg_session_factory):
    """Ensure non-superuser app_user role exists with permissions on public schema."""
    async with pg_session_factory() as session:
        await session.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'app_user') THEN
                        CREATE ROLE app_user WITH LOGIN PASSWORD 'app_user_password' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
                    ELSE
                        ALTER ROLE app_user WITH LOGIN PASSWORD 'app_user_password' NOSUPERUSER NOBYPASSRLS;
                    END IF;
                    GRANT USAGE ON SCHEMA public TO app_user;
                    GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO app_user;
                    GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO app_user;
                END
                $$;
                """
            )
        )
        await session.commit()


@pytest_asyncio.fixture
def renewal_service():
    pos_service = PlaceOfSupplyService()
    tax_engine = GSTTaxEngine(tax_config_service)
    num_service = InvoiceNumberingService()
    invoice_service = PlatformInvoiceService(
        tax_engine=tax_engine,
        pos_service=pos_service,
        numbering_service=num_service,
    )
    return AutomatedRenewalInvoicingService(invoice_service=invoice_service)


async def _seed_overdue_pg_tenant(
    session: AsyncSession,
    renewal_service: AutomatedRenewalInvoicingService,
    past_due_hours_ago: float = 2.0,
    society_status: str = "ACTIVE",
    plan_price: Decimal = Decimal("2000.00"),
) -> tuple[Society, PlatformSubscriptionPlan, SocietySubscription, PlatformInvoice]:
    now = _utc_now()
    soc_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    sub_id = uuid.uuid4()

    soc = Society(
        id=soc_id,
        legal_name=f"PG Dunning Soc {soc_id.hex[:6]}",
        display_name=f"PG Dunning {soc_id.hex[:6]}",
        address_line1="789 Residency Rd",
        city="Bengaluru",
        state="Karnataka",
        postal_code="560025",
        status=society_status,
        registration_number=f"REG-PG-{soc_id.hex[:6]}",
    )
    plan = PlatformSubscriptionPlan(
        id=plan_id,
        plan_code=f"PG_DUNNING_{plan_id.hex[:6]}",
        display_name="PG Dunning Plan",
        monthly_price=plan_price,
        annual_price=plan_price * 10,
        is_active=True,
    )

    past_due_since = now - timedelta(hours=past_due_hours_ago)
    sub = SocietySubscription(
        id=sub_id,
        society_id=soc_id,
        plan_id=plan_id,
        status=SubscriptionStatus.PAST_DUE.value,
        billing_cycle="MONTHLY",
        auto_renew=True,
        starts_at=past_due_since - timedelta(days=30),
        current_period_start=past_due_since - timedelta(days=30),
        current_period_end=past_due_since,
        next_billing_at=past_due_since,
        past_due_since=past_due_since,
    )

    session.add_all([soc, plan, sub])
    await session.commit()

    inv_res = await renewal_service.generate_renewal_invoice(
        session=session,
        subscription=sub,
        society=soc,
        period_start=sub.current_period_start,
        period_end=sub.current_period_end,
    )
    stmt_inv = select(PlatformInvoice).where(PlatformInvoice.id == inv_res.id)
    invoice = (await session.execute(stmt_inv)).scalar_one()
    invoice.status = "OVERDUE"
    await session.commit()
    await session.refresh(sub)
    await session.refresh(soc)
    await session.refresh(invoice)

    return soc, plan, sub, invoice


# =============================================================================
# 1. 64-bit Advisory Locking on PostgreSQL 16
# =============================================================================
@pytest.mark.asyncio
async def test_pg_advisory_locking_mutual_exclusion(pg_session_factory):
    """Verify that compute_advisory_lock_key produces valid 64-bit bigints that provide mutual exclusion."""
    resource_id = f"society:{uuid.uuid4()}"
    lock_key = compute_advisory_lock_key(resource_id)

    # Connection 1 acquires lock
    async with pg_session_factory() as session1:
        res1 = await session1.execute(
            text("SELECT pg_try_advisory_xact_lock(:key)"),
            {"key": lock_key},
        )
        assert res1.scalar() is True, "Session 1 should acquire advisory lock"

        # Connection 2 attempts to acquire same lock -> should fail
        async with pg_session_factory() as session2:
            res2 = await session2.execute(
                text("SELECT pg_try_advisory_xact_lock(:key)"),
                {"key": lock_key},
            )
            assert res2.scalar() is False, "Session 2 should be denied lock while Session 1 holds it"

        # Session 1 commits, releasing transaction-scoped advisory lock
        await session1.commit()

    # Now Session 2 can acquire it
    async with pg_session_factory() as session3:
        res3 = await session3.execute(
            text("SELECT pg_try_advisory_xact_lock(:key)"),
            {"key": lock_key},
        )
        assert res3.scalar() is True, "Session 3 should acquire lock after Session 1 committed"
        await session3.commit()


# =============================================================================
# 2. PostgreSQL 16 FORCE ROW LEVEL SECURITY on platform_dunning_attempts
# =============================================================================
@pytest.mark.asyncio
async def test_pg_dunning_attempts_force_rls(pg_session_factory, ensure_app_user_role, renewal_service):
    """Verify FORCE RLS on platform_dunning_attempts with non-superuser app_user.

    Validates:
    1. relrowsecurity=True, relforcerowsecurity=True in pg_class.
    2. app_user has NOSUPERUSER and NOBYPASSRLS.
    3. Missing tenant context returns 0 rows (fail-closed).
    4. Tenant A context reveals only Tenant A records.
    5. Cross-tenant insertion by Tenant A into Tenant B is rejected.
    """
    async with pg_session_factory() as admin_session:
        # Check pg_class RLS flags
        res = await admin_session.execute(
            text(
                """
                SELECT relname, relrowsecurity, relforcerowsecurity
                FROM pg_class
                WHERE relname = 'platform_dunning_attempts';
                """
            )
        )
        row = res.fetchone()
        assert row is not None
        assert row[1] is True, "platform_dunning_attempts must enforce RLS"
        assert row[2] is True, "platform_dunning_attempts must FORCE RLS"

        # Check app_user permissions
        res_role = await admin_session.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'app_user'")
        )
        role_row = res_role.fetchone()
        assert role_row is not None
        assert role_row[0] is False, "app_user must not be superuser"
        assert role_row[1] is False, "app_user must not bypass RLS"

        # Seed Tenant A and Tenant B with dunning attempts
        soc_a, _, sub_a, inv_a = await _seed_overdue_pg_tenant(admin_session, renewal_service)
        soc_b, _, sub_b, inv_b = await _seed_overdue_pg_tenant(admin_session, renewal_service)

        att_a = PlatformDunningAttempt(
            id=uuid.uuid4(),
            society_id=soc_a.id,
            subscription_id=sub_a.id,
            invoice_id=inv_a.id,
            attempt_type=DunningStage.DAY_0_REMINDER.value,
            status="SUCCEEDED",
            idempotency_key=f"dunning:{sub_a.id}:{inv_a.id}:DAY_0_REMINDER",
            scheduled_at=_utc_now(),
            executed_at=_utc_now(),
            grace_days_remaining=7,
            metadata_json={"stage": "DAY_0_REMINDER"},
            created_at=_utc_now(),
        )
        att_b = PlatformDunningAttempt(
            id=uuid.uuid4(),
            society_id=soc_b.id,
            subscription_id=sub_b.id,
            invoice_id=inv_b.id,
            attempt_type=DunningStage.DAY_0_REMINDER.value,
            status="SUCCEEDED",
            idempotency_key=f"dunning:{sub_b.id}:{inv_b.id}:DAY_0_REMINDER",
            scheduled_at=_utc_now(),
            executed_at=_utc_now(),
            grace_days_remaining=7,
            metadata_json={"stage": "DAY_0_REMINDER"},
            created_at=_utc_now(),
        )
        admin_session.add_all([att_a, att_b])
        await admin_session.commit()

    # Query under unprivileged app_user
    app_engine = create_async_engine(
        "postgresql+asyncpg://app_user:app_user_password@localhost:5432/societysphere_dev",
        echo=False,
    )
    app_session_factory = async_sessionmaker(bind=app_engine, class_=AsyncSession, expire_on_commit=False)

    try:
        # A. Missing tenant context -> fail-closed (0 rows)
        async with app_session_factory() as session:
            stmt = select(PlatformDunningAttempt)
            attempts = (await session.execute(stmt)).scalars().all()
            assert len(attempts) == 0, "Queries without tenant context must fail closed (0 rows)"

        # B. Tenant A context -> only Tenant A rows visible
        async with app_session_factory() as session:
            await set_db_tenant_context(session, soc_a.id)
            stmt = select(PlatformDunningAttempt)
            attempts = (await session.execute(stmt)).scalars().all()
            assert len(attempts) >= 1
            assert all(a.society_id == soc_a.id for a in attempts)
            assert not any(a.society_id == soc_b.id for a in attempts)

        # C. Cross-tenant write denial -> Tenant A cannot write into Tenant B
        async with app_session_factory() as session:
            await set_db_tenant_context(session, soc_a.id)
            tamper_att = PlatformDunningAttempt(
                id=uuid.uuid4(),
                society_id=soc_b.id,  # Spoofed Tenant B ID
                subscription_id=sub_b.id,
                invoice_id=inv_b.id,
                attempt_type=DunningStage.DAY_2_REMINDER.value,
                status="SUCCEEDED",
                idempotency_key=f"tamper:{uuid.uuid4()}",
                scheduled_at=_utc_now(),
                executed_at=_utc_now(),
                grace_days_remaining=5,
                metadata_json={},
                created_at=_utc_now(),
            )
            session.add(tamper_att)
            with pytest.raises(Exception):
                await session.commit()
    finally:
        await app_engine.dispose()


# =============================================================================
# 3. Horizontal Concurrency: Multi-Worker Dunning Reminders
# =============================================================================
@pytest.mark.asyncio
async def test_concurrent_dunning_reminder_workers_pg(pg_session_factory, renewal_service):
    """Run 4 concurrent dunning workers processing overdue subscriptions.

    Verifies:
    1. Zero deadlocks.
    2. Zero duplicate attempts.
    3. Exactly 1 reminder attempt per candidate subscription.
    """
    now = _utc_now()
    num_subs = 4
    num_workers = 4

    # Seed 4 candidate subscriptions at Day 0
    sub_ids: list[uuid.UUID] = []
    async with pg_session_factory() as session:
        for idx in range(num_subs):
            soc, plan, sub, inv = await _seed_overdue_pg_tenant(
                session=session,
                renewal_service=renewal_service,
                past_due_hours_ago=1.0 + (idx * 0.5),  # All Day 0
            )
            sub_ids.append(sub.id)

    # Worker function executing batch with isolated candidate subscriptions
    async def _worker(worker_id: int):
        async with pg_session_factory() as worker_session:
            svc = DunningEngineService(session=worker_session)
            return await svc.process_dunning_batch(
                cutoff_utc=now,
                batch_size=10,
                subscription_ids=sub_ids,
                execution_id=f"pg-worker-{worker_id}-{uuid.uuid4().hex[:6]}",
            )

    # Run workers concurrently
    batch_results = await asyncio.gather(*[_worker(i) for i in range(num_workers)])

    total_succeeded = sum(r.succeeded_count for r in batch_results)
    total_failed = sum(r.failed_count for r in batch_results)

    assert total_failed == 0, "No worker should fail with deadlock or unhandled exception"
    assert total_succeeded == num_subs, f"Expected exactly {num_subs} successful attempts"

    # Verify attempt records in DB for our seeded subscriptions
    async with pg_session_factory() as session:
        stmt = select(PlatformDunningAttempt).where(
            PlatformDunningAttempt.subscription_id.in_(sub_ids),
            PlatformDunningAttempt.attempt_type == DunningStage.DAY_0_REMINDER.value,
        )
        attempts = (await session.execute(stmt)).scalars().all()

        # Each subscription must have exactly 1 attempt
        assert len(attempts) == num_subs, f"Expected {num_subs} attempts, found {len(attempts)}"
        seen_subs = set()
        for a in attempts:
            assert a.subscription_id not in seen_subs, f"Duplicate attempt for sub {a.subscription_id}!"
            seen_subs.add(a.subscription_id)


# =============================================================================
# 4. Horizontal Concurrency: Multi-Worker Day 7 Suspension
# =============================================================================
@pytest.mark.asyncio
async def test_concurrent_dunning_suspension_workers_pg(pg_session_factory, renewal_service):
    """Run 4 concurrent workers on subscriptions reaching Day 7 grace expiry.

    Verifies:
    1. Zero deadlocks during pessimistic row locks and advisory locks.
    2. Zero duplicate suspension attempts.
    3. All candidate subscriptions transition to SUSPENDED.
    """
    now = _utc_now()
    num_subs = 4
    num_workers = 4

    # Seed 4 candidate subscriptions at Day 7 (170 hours overdue)
    sub_ids: list[uuid.UUID] = []
    soc_ids: list[uuid.UUID] = []
    async with pg_session_factory() as session:
        for idx in range(num_subs):
            soc, plan, sub, inv = await _seed_overdue_pg_tenant(
                session=session,
                renewal_service=renewal_service,
                past_due_hours_ago=170.0 + idx,  # Day 7 (168h+)
            )
            sub_ids.append(sub.id)
            soc_ids.append(soc.id)

    async def _suspension_worker(worker_id: int):
        async with pg_session_factory() as worker_session:
            svc = DunningEngineService(session=worker_session)
            return await svc.process_dunning_batch(
                cutoff_utc=now,
                batch_size=10,
                subscription_ids=sub_ids,
                execution_id=f"pg-suspend-worker-{worker_id}-{uuid.uuid4().hex[:6]}",
            )

    batch_results = await asyncio.gather(*[_suspension_worker(i) for i in range(num_workers)])

    total_failed = sum(r.failed_count for r in batch_results)
    assert total_failed == 0, "No worker should encounter suspension deadlock or failure"

    # Verify all subscriptions transitioned to SUSPENDED
    async with pg_session_factory() as session:
        stmt_subs = select(SocietySubscription).where(SocietySubscription.id.in_(sub_ids))
        subs = (await session.execute(stmt_subs)).scalars().all()
        assert len(subs) == num_subs
        for s in subs:
            assert s.status == SubscriptionStatus.SUSPENDED.value, f"Sub {s.id} should be SUSPENDED, was {s.status}"
            assert s.suspended_at is not None

        # Verify society statuses are still ACTIVE (Decoupling)
        stmt_socs = select(Society).where(Society.id.in_(soc_ids))
        socs = (await session.execute(stmt_socs)).scalars().all()
        for sc in socs:
            assert sc.status == "ACTIVE", f"Society {sc.id} status should remain ACTIVE"

        # Verify exactly 1 DAY_7_SUSPENSION attempt per subscription
        stmt_att = select(PlatformDunningAttempt).where(
            PlatformDunningAttempt.subscription_id.in_(sub_ids),
            PlatformDunningAttempt.attempt_type == DunningStage.DAY_7_SUSPENSION.value,
        )
        attempts = (await session.execute(stmt_att)).scalars().all()
        assert len(attempts) == num_subs


# =============================================================================
# 5. Horizontal Concurrency: Multi-Worker Transactional Outbox Drainage
# =============================================================================
@pytest.mark.asyncio
async def test_concurrent_dunning_outbox_workers_pg(pg_session_factory, renewal_service):
    """Run 4 concurrent outbox workers draining queued dunning notifications.

    Verifies:
    1. Zero deadlocks during SELECT ... FOR UPDATE SKIP LOCKED.
    2. Zero duplicate notification dispatches.
    3. All queued outbox records transition to SENT.
    """
    now = _utc_now()
    num_subs = 4
    num_workers = 4

    # Seed 4 candidate subscriptions with auto_drain_outbox=False
    sub_ids: list[uuid.UUID] = []
    soc_ids: list[uuid.UUID] = []
    async with pg_session_factory() as session:
        for idx in range(num_subs):
            soc, plan, sub, inv = await _seed_overdue_pg_tenant(
                session=session,
                renewal_service=renewal_service,
                past_due_hours_ago=2.0 + (idx * 0.5),
            )
            sub_ids.append(sub.id)
            soc_ids.append(soc.id)

        # Execute dunning batch without in-line outbox draining
        svc = DunningEngineService(session=session)
        batch_res = await svc.process_dunning_batch(
            cutoff_utc=now,
            batch_size=10,
            subscription_ids=sub_ids,
            auto_drain_outbox=False,
        )
        assert batch_res.succeeded_count == num_subs

        # Query the exact outbox notification IDs created for this test batch
        stmt_notifs = select(Notification.id).where(
            Notification.society_id.in_(soc_ids),
            Notification.source_domain == "DUNNING",
            Notification.status == "QUEUED",
        )
        notif_ids = list((await session.execute(stmt_notifs)).scalars().all())
        assert len(notif_ids) == num_subs

    # 4 concurrent outbox workers draining pending outbox events targeting this test's notification_ids
    async def _outbox_worker(worker_id: int):
        async with pg_session_factory() as worker_session:
            svc = DunningEngineService(session=worker_session)
            return await svc.drain_pending_outbox(batch_size=10, notification_ids=notif_ids)

    drain_results = await asyncio.gather(*[_outbox_worker(i) for i in range(num_workers)])
    total_drained = sum(drain_results)
    assert total_drained == num_subs, f"Expected {num_subs} drained outbox items, got {total_drained}"

