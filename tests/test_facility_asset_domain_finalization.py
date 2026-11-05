"""Phase 14 — Facility & Asset Domain Finalization & Concurrency Verification Tests."""

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.billing import Invoice, Payment, Receipt
from apps.api.src.database.models.facility_asset import AssetCategory
from apps.api.src.database.models.finance import JournalEntry, JournalEntryLine
from apps.api.src.database.models.identity import User
from apps.api.src.facility_asset.asset_service import AssetService
from apps.api.src.facility_asset.enums import AssetStatus, FacilityType
from apps.api.src.facility_asset.exceptions import FacilityNotFoundError
from apps.api.src.facility_asset.facility_service import FacilityService
from apps.api.src.facility_asset.repositories import AssetCategoryRepository
from apps.api.src.facility_asset.schemas import AssetCreate, AssetStatusUpdate, FacilityCreate


@pytest.mark.asyncio
async def test_sequential_facility_and_asset_code_generation(seeded_session: AsyncSession):
    session = seeded_session
    society_id = uuid.uuid4()

    user = User(
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        first_name="Admin",
        last_name="User",
        display_name="Admin User",
    )
    session.add(user)
    await session.flush()

    facility_service = FacilityService(session)
    f1 = await facility_service.create_facility(
        society_id, FacilityCreate(name="Facility 1", facility_type=FacilityType.CLUBHOUSE)
    )
    f2 = await facility_service.create_facility(
        society_id, FacilityCreate(name="Facility 2", facility_type=FacilityType.GYM)
    )

    assert f1.facility_code.startswith("FAC-")
    assert f2.facility_code.startswith("FAC-")
    assert f1.facility_code != f2.facility_code
    assert int(f2.facility_code.split("-")[-1]) == int(f1.facility_code.split("-")[-1]) + 1

    cat_repo = AssetCategoryRepository(session)
    cat = await cat_repo.create(
        AssetCategory(society_id=society_id, category_code="PUMP", name="Water Pumps")
    )

    asset_service = AssetService(session)
    a1 = await asset_service.create_asset(
        society_id, user.id, AssetCreate(name="Submersible Pump 1", category_id=cat.id)
    )
    a2 = await asset_service.create_asset(
        society_id, user.id, AssetCreate(name="Submersible Pump 2", category_id=cat.id)
    )

    assert a1.asset_code.startswith("AST-")
    assert a2.asset_code.startswith("AST-")
    assert a1.asset_code != a2.asset_code
    assert int(a2.asset_code.split("-")[-1]) == int(a1.asset_code.split("-")[-1]) + 1


@pytest.mark.asyncio
async def test_cross_tenant_facility_asset_isolation(seeded_session: AsyncSession):
    session = seeded_session
    society_a = uuid.uuid4()
    society_b = uuid.uuid4()

    user = User(
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        first_name="Admin",
        last_name="User",
        display_name="Admin User",
    )
    session.add(user)
    await session.flush()

    facility_service = FacilityService(session)
    fac_a = await facility_service.create_facility(
        society_a, FacilityCreate(name="Society A Clubhouse", facility_type=FacilityType.CLUBHOUSE)
    )

    # Society B should NOT be able to view Society A facility
    with pytest.raises(FacilityNotFoundError):
        await facility_service.get_facility(society_b, fac_a.id)

    items_b, total_b = await facility_service.list_facilities(society_b)
    assert total_b == 0
    assert fac_a.id not in [f.id for f in items_b]


@pytest.mark.asyncio
async def test_facility_asset_financial_isolation(seeded_session: AsyncSession):
    session = seeded_session
    society_id = uuid.uuid4()

    # Get baseline count of financial records
    inv_count_before = (await session.scalar(select(func.count(Invoice.id)))) or 0
    pay_count_before = (await session.scalar(select(func.count(Payment.id)))) or 0
    rec_count_before = (await session.scalar(select(func.count(Receipt.id)))) or 0
    je_count_before = (await session.scalar(select(func.count(JournalEntry.id)))) or 0
    jel_count_before = (await session.scalar(select(func.count(JournalEntryLine.id)))) or 0

    user = User(
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        first_name="Admin",
        last_name="User",
        display_name="Admin User",
    )
    session.add(user)
    await session.flush()

    # Perform full facility & asset lifecycle operations
    facility_service = FacilityService(session)
    fac = await facility_service.create_facility(
        society_id, FacilityCreate(name="Community Center", facility_type=FacilityType.COMMUNITY_HALL)
    )

    cat_repo = AssetCategoryRepository(session)
    cat = await cat_repo.create(
        AssetCategory(society_id=society_id, category_code="AUDIO", name="Audio System")
    )

    asset_service = AssetService(session)
    asset = await asset_service.create_asset(
        society_id, user.id, AssetCreate(name="PA Speakers", category_id=cat.id, facility_id=fac.id)
    )

    await asset_service.update_asset_status(
        society_id,
        user.id,
        asset.id,
        AssetStatusUpdate(status=AssetStatus.UNDER_MAINTENANCE, reason="Speaker repair"),
    )

    # Verify baseline count of financial records remains unchanged (zero mutations)
    inv_count_after = (await session.scalar(select(func.count(Invoice.id)))) or 0
    pay_count_after = (await session.scalar(select(func.count(Payment.id)))) or 0
    rec_count_after = (await session.scalar(select(func.count(Receipt.id)))) or 0
    je_count_after = (await session.scalar(select(func.count(JournalEntry.id)))) or 0
    jel_count_after = (await session.scalar(select(func.count(JournalEntryLine.id)))) or 0

    assert inv_count_after == inv_count_before
    assert pay_count_after == pay_count_before
    assert rec_count_after == rec_count_before
    assert je_count_after == je_count_before
    assert jel_count_after == jel_count_before
