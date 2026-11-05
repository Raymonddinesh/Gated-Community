"""Phase 21E.4A — Live PostgreSQL 16 Tax Calculation & Audit Snapshot Tests.

Validates that:
1. PlatformInvoice and PlatformInvoiceItem tax fields populated by GSTTaxEngine
   persist cleanly in PostgreSQL 16 with exact Decimal precision.
2. TaxSnapshot stored in PlatformSubscriptionAuditLog JSONB under unprivileged
   app_user role enforces PostgreSQL FORCE ROW LEVEL SECURITY (zero cross-tenant leakage).
"""

import logging
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.src.core.tenant_context import tenant_context
from apps.api.src.database.models.platform_billing import (
    PlatformInvoice,
    PlatformInvoiceItem,
    PlatformSubscriptionAuditLog,
)
from apps.api.src.database.models.society import Society
from apps.api.src.database.models.subscription import (
    PlatformSubscriptionPlan,
    SocietySubscription,
)
from apps.api.src.database.session import set_db_tenant_context
from apps.api.src.subscriptions.tax import (
    GSTTaxEngine,
    PlaceOfSupplyInput,
    PlaceOfSupplyService,
    TaxCalculationInput,
    TaxSnapshot,
    TaxSnapshotService,
    tax_config_service,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_phase21e4a_pg")

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
async def ensure_app_user_role(pg_session_factory):
    """Ensure non-superuser app_user role exists with permissions on public schema."""
    async with pg_session_factory() as session:
        await session.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'app_user') THEN
                        CREATE ROLE app_user NOSUPERUSER NOBYPASSRLS;
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


@pytest.mark.asyncio
async def test_pg_tax_calculation_persistence_and_invariants(pg_session_factory):
    """Verify that GSTTaxEngine calculations persist with full Decimal precision into PostgreSQL 16."""
    soc_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    sub_id = uuid.uuid4()
    inv_id = uuid.uuid4()
    now = _utc_now()

    # 1. Compute tax via GSTTaxEngine
    pos_service = PlaceOfSupplyService()
    pos = pos_service.determine_place_of_supply(
        PlaceOfSupplyInput(supplier_state="Karnataka", customer_state="Karnataka")
    )
    engine = GSTTaxEngine(tax_config_service)
    calc_res = engine.calculate_tax(
        TaxCalculationInput(
            base_amount=Decimal("5000.00"),
            sac_code="998313",
            place_of_supply=pos,
            discount_amount=Decimal("500.00"),
        )
    )

    # 2. Persist in PostgreSQL 16
    async with pg_session_factory() as session:
        soc = Society(
            id=soc_id,
            legal_name="Tax Engine Test Society",
            display_name="Tax Soc",
            address_line1="100 Tax Way",
            city="Bengaluru",
            state="Karnataka",
            postal_code="560001",
        )
        plan = PlatformSubscriptionPlan(
            id=plan_id,
            plan_code=f"PLAN_TAX_{uuid.uuid4().hex[:6]}",
            display_name="Tax Test Plan",
            monthly_price=Decimal("5000.00"),
        )
        sub = SocietySubscription(
            id=sub_id,
            society_id=soc_id,
            plan_id=plan_id,
            status="ACTIVE",
            starts_at=now,
            current_period_start=now,
            current_period_end=now,
        )
        inv = PlatformInvoice(
            id=inv_id,
            society_id=soc_id,
            subscription_id=sub_id,
            invoice_number=f"SS-TAX-{uuid.uuid4().hex[:6]}",
            period_start=now,
            period_end=now,
            subtotal=calc_res.base_amount,
            discount_total=calc_res.discount_amount,
            taxable_amount=calc_res.taxable_amount,
            cgst_amount=calc_res.cgst_amount,
            sgst_amount=calc_res.sgst_amount,
            igst_amount=calc_res.igst_amount,
            tax_total=calc_res.tax_total,
            grand_total=calc_res.grand_total,
            amount_due=calc_res.grand_total,
            due_date=date.today(),
            sac_code=calc_res.sac_code,
            place_of_supply=calc_res.tax_snapshot.place_of_supply,
            status="ISSUED",
        )
        item = PlatformInvoiceItem(
            id=uuid.uuid4(),
            society_id=soc_id,
            invoice_id=inv_id,
            item_index=0,
            item_type="BASE_PLAN",
            description="SaaS Subscription Base Plan",
            sac_code=calc_res.sac_code,
            quantity=Decimal("1.0000"),
            unit_price=calc_res.base_amount,
            discount_amount=calc_res.discount_amount,
            taxable_amount=calc_res.taxable_amount,
            tax_rate=calc_res.tax_rate,
            tax_amount=calc_res.tax_total,
            total_amount=calc_res.grand_total,
        )
        session.add_all([soc, plan, sub, inv, item])
        await session.commit()

    # 3. Read back and verify exact Decimal precision and invariants
    async with pg_session_factory() as session:
        inv_db = (await session.execute(select(PlatformInvoice).where(PlatformInvoice.id == inv_id))).scalar_one()
        assert inv_db.subtotal == Decimal("5000.00")
        assert inv_db.discount_total == Decimal("500.00")
        assert inv_db.taxable_amount == Decimal("4500.00")
        assert inv_db.cgst_amount == Decimal("405.00")
        assert inv_db.sgst_amount == Decimal("405.00")
        assert inv_db.igst_amount == Decimal("0.00")
        assert inv_db.tax_total == Decimal("810.00")
        assert inv_db.grand_total == Decimal("5310.00")
        assert inv_db.sac_code == "998313"
        assert inv_db.place_of_supply == "Karnataka"


@pytest.mark.asyncio
async def test_pg_tax_snapshot_in_audit_log_rls_isolation(
    pg_engine, pg_session_factory, ensure_app_user_role
):
    """Verify that TaxSnapshot stored in JSONB under unprivileged app_user obeys PostgreSQL FORCE RLS."""
    soc_a_id = uuid.uuid4()
    soc_b_id = uuid.uuid4()

    # 1. Compute and serialize a tax snapshot for Society A
    pos_service = PlaceOfSupplyService()
    pos = pos_service.determine_place_of_supply(
        PlaceOfSupplyInput(supplier_state="Karnataka", customer_state="Maharashtra")
    )
    engine = GSTTaxEngine(tax_config_service)
    calc_res = engine.calculate_tax(
        TaxCalculationInput(
            base_amount=Decimal("2000.00"),
            sac_code="998313",
            place_of_supply=pos,
        )
    )
    snapshot = calc_res.tax_snapshot
    snapshot_dict = TaxSnapshotService.to_dict(snapshot)

    # 2. Seed Society A and audit log with tax snapshot
    async with pg_session_factory() as session:
        soc_a = Society(
            id=soc_a_id,
            legal_name="Tenant A GST Society",
            display_name="Tenant A",
            address_line1="123 A Road",
            city="Bengaluru",
            state="Karnataka",
            postal_code="560001",
        )
        soc_b = Society(
            id=soc_b_id,
            legal_name="Tenant B GST Society",
            display_name="Tenant B",
            address_line1="456 B Road",
            city="Mumbai",
            state="Maharashtra",
            postal_code="400001",
        )
        audit_log_a = PlatformSubscriptionAuditLog(
            id=uuid.uuid4(),
            society_id=soc_a_id,
            entity_type="TAX_SNAPSHOT",
            entity_id=snapshot.snapshot_id,
            action="TAX_CALCULATED",
            actor_type="SYSTEM",
            before_state=None,
            after_state=snapshot_dict,
        )
        session.add_all([soc_a, soc_b, audit_log_a])
        await session.commit()
        audit_log_a_id = audit_log_a.id

    # 3. Tenant B queries as unprivileged app_user -> MUST RETURN 0 ROWS
    async with pg_session_factory() as session:
        await session.execute(text("SET ROLE app_user"))
        async with tenant_context(soc_b_id):
            await set_db_tenant_context(session, soc_b_id)
            stmt = select(PlatformSubscriptionAuditLog).where(
                PlatformSubscriptionAuditLog.id == audit_log_a_id
            )
            leak = (await session.execute(stmt)).scalar_one_or_none()
            assert leak is None, "FORCE RLS violation: Tenant B accessed Tenant A's tax snapshot!"

    # 4. Tenant A queries as unprivileged app_user -> MUST RETURN EXACT RECORD AND VERIFY HASH
    async with pg_session_factory() as session:
        await session.execute(text("SET ROLE app_user"))
        async with tenant_context(soc_a_id):
            await set_db_tenant_context(session, soc_a_id)
            stmt = select(PlatformSubscriptionAuditLog).where(
                PlatformSubscriptionAuditLog.id == audit_log_a_id
            )
            audit_record = (await session.execute(stmt)).scalar_one_or_none()
            assert audit_record is not None, "Tenant A must access their own tax snapshot"
            assert audit_record.after_state is not None

            # Reconstruct snapshot and verify cryptographic integrity
            restored_snapshot = TaxSnapshot(**audit_record.after_state)
            assert TaxSnapshotService.verify_snapshot_integrity(restored_snapshot) is True
            assert restored_snapshot.tax_rate == Decimal("18.00")
            assert restored_snapshot.igst_amount == Decimal("360.00")
            assert restored_snapshot.grand_total == Decimal("2360.00")
