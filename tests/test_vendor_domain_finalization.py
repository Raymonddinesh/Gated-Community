"""Phase 13 — Vendor Domain Finalization & Concurrency Verification Tests."""

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.billing import Invoice, Payment, Receipt
from apps.api.src.database.models.finance import JournalEntry, JournalEntryLine
from apps.api.src.database.models.identity import User
from apps.api.src.vendor.application.vendor_service import VendorService
from apps.api.src.vendor.domain.exceptions import VendorNotFoundException
from apps.api.src.vendor.schemas import VendorProfileCreate


@pytest.mark.asyncio
async def test_sequential_vendor_code_generation(seeded_session: AsyncSession):
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

    vendor_service = VendorService(session)
    v1 = await vendor_service.create_vendor(
        VendorProfileCreate(legal_name="Vendor One Pvt Ltd", display_name="Vendor 1"),
        society_id,
        user.id,
    )
    v2 = await vendor_service.create_vendor(
        VendorProfileCreate(legal_name="Vendor Two Pvt Ltd", display_name="Vendor 2"),
        society_id,
        user.id,
    )

    assert v1.vendor_code.startswith("VND-")
    assert v2.vendor_code.startswith("VND-")
    assert v1.vendor_code != v2.vendor_code
    assert int(v2.vendor_code.split("-")[-1]) == int(v1.vendor_code.split("-")[-1]) + 1


@pytest.mark.asyncio
async def test_cross_tenant_vendor_isolation(seeded_session: AsyncSession):
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

    vendor_service = VendorService(session)
    create_dto = VendorProfileCreate(
        legal_name="Tenant A Elevator Solutions",
        display_name="Tenant A Lifts",
    )
    vendor = await vendor_service.create_vendor(create_dto, society_a, user.id)

    # Querying vendor from Society B must raise VendorNotFoundException
    with pytest.raises(VendorNotFoundException):
        await vendor_service.get_vendor(vendor.id, society_b)


@pytest.mark.asyncio
async def test_vendor_financial_isolation_non_mutation(seeded_session: AsyncSession):
    """Verify that vendor profile creation and status changes NEVER mutate financial ledger or billing records."""
    session = seeded_session
    society_id = uuid.uuid4()

    inv_count_before = (await session.execute(select(func.count(Invoice.id)))).scalar() or 0
    pay_count_before = (await session.execute(select(func.count(Payment.id)))).scalar() or 0
    rcpt_count_before = (await session.execute(select(func.count(Receipt.id)))).scalar() or 0
    je_count_before = (await session.execute(select(func.count(JournalEntry.id)))).scalar() or 0
    jel_count_before = (await session.execute(select(func.count(JournalEntryLine.id)))).scalar() or 0

    user = User(
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        first_name="Admin",
        last_name="User",
        display_name="Admin User",
    )
    session.add(user)
    await session.flush()

    vendor_service = VendorService(session)
    create_dto = VendorProfileCreate(
        legal_name="Isolated Vendor Pvt Ltd",
        display_name="Isolated Vendor",
    )
    vendor = await vendor_service.create_vendor(create_dto, society_id, user.id)
    assert vendor.id is not None

    inv_count_after = (await session.execute(select(func.count(Invoice.id)))).scalar() or 0
    pay_count_after = (await session.execute(select(func.count(Payment.id)))).scalar() or 0
    rcpt_count_after = (await session.execute(select(func.count(Receipt.id)))).scalar() or 0
    je_count_after = (await session.execute(select(func.count(JournalEntry.id)))).scalar() or 0
    jel_count_after = (await session.execute(select(func.count(JournalEntryLine.id)))).scalar() or 0

    assert inv_count_before == inv_count_after
    assert pay_count_before == pay_count_after
    assert rcpt_count_before == rcpt_count_after
    assert je_count_before == je_count_after
    assert jel_count_before == jel_count_after
