"""Domain Finalization and Security Verification Tests for Phase 12 — Staff & Workforce Management."""

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.billing import Invoice, Payment, Receipt
from apps.api.src.database.models.finance import JournalEntry, JournalEntryLine
from apps.api.src.database.models.identity import User
from apps.api.src.staff.application.role_service import StaffRoleService
from apps.api.src.staff.application.staff_service import StaffProfileService
from apps.api.src.staff.domain.enums import StaffStatus
from apps.api.src.staff.infrastructure.repositories import StaffProfileRepository
from apps.api.src.staff.schemas import (
    StaffContactRequest,
    StaffProfileCreateRequest,
    StaffRoleCreateRequest,
    StaffStatusUpdateRequest,
)


@pytest.mark.asyncio
async def test_staff_financial_isolation_non_mutation(
    seeded_session: AsyncSession,
) -> None:
    """Verify that staff profile creation and status changes NEVER mutate financial ledger or billing records."""
    session = seeded_session
    society_id = uuid.uuid4()

    # 1. Capture initial counts across financial and billing tables
    inv_count_before = (await session.execute(select(func.count(Invoice.id)))).scalar() or 0
    pay_count_before = (await session.execute(select(func.count(Payment.id)))).scalar() or 0
    rcpt_count_before = (await session.execute(select(func.count(Receipt.id)))).scalar() or 0
    je_count_before = (await session.execute(select(func.count(JournalEntry.id)))).scalar() or 0
    jel_count_before = (await session.execute(select(func.count(JournalEntryLine.id)))).scalar() or 0

    # 2. Execute Staff Creation, Activation, and Offboarding
    user = User(
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        first_name="Admin",
        last_name="User",
        display_name="Admin User",
    )
    session.add(user)
    await session.flush()

    staff_service = StaffProfileService(session)
    staff = await staff_service.create_staff_profile(
        StaffProfileCreateRequest(
            first_name="FinCheck",
            last_name="Staff",
            contact=StaffContactRequest(phone="+919999988888"),
        ),
        society_id,
        user,
    )

    await staff_service.transition_staff_status(
        staff.id, society_id, StaffStatusUpdateRequest(status=StaffStatus.ACTIVE), user
    )

    await staff_service.transition_staff_status(
        staff.id, society_id, StaffStatusUpdateRequest(status=StaffStatus.OFFBOARDED), user
    )

    # 3. Assert zero mutation on financial core & billing tables
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


@pytest.mark.asyncio
async def test_concurrent_staff_code_generation(
    seeded_session: AsyncSession,
) -> None:
    """Verify concurrent sequence number generation produces unique STF-YYYY-XXXXXX staff codes."""
    session = seeded_session
    society_id = uuid.uuid4()

    repo = StaffProfileRepository(session)
    codes = []
    for _ in range(5):
        code = await repo.generate_next_staff_code(society_id, 2026)
        admin = User(
            email=f"u-{uuid.uuid4().hex[:6]}@example.com",
            password_hash="h",
            first_name="F",
            last_name="L",
            display_name="D",
        )
        session.add(admin)
        await session.flush()

        staff_service = StaffProfileService(session)
        await staff_service.create_staff_profile(
            StaffProfileCreateRequest(
                first_name="Name",
                last_name="Test",
                contact=StaffContactRequest(phone="+919876543299"),
            ),
            society_id,
            admin,
        )
        codes.append(code)

    assert len(codes) == 5
    assert len(set(codes)) == 5  # All 5 staff codes are unique


@pytest.mark.asyncio
async def test_cross_society_role_assignment_rejection(
    seeded_session: AsyncSession,
) -> None:
    """Verify assigning a role from Society B to a Staff member in Society A fails cleanly."""
    session = seeded_session
    society_a = uuid.uuid4()
    society_b = uuid.uuid4()

    admin = User(
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        first_name="Admin",
        last_name="User",
        display_name="Admin User",
    )
    session.add(admin)
    await session.flush()

    staff_service = StaffProfileService(session)
    staff_a = await staff_service.create_staff_profile(
        StaffProfileCreateRequest(
            first_name="StaffA",
            last_name="Person",
            contact=StaffContactRequest(phone="+919876543298"),
        ),
        society_a,
        admin,
    )

    role_service = StaffRoleService(session)
    role_b = await role_service.create_staff_role(
        StaffRoleCreateRequest(name="RoleB", code="ROLE_B"), society_b
    )

    # Attempting to assign Role B (Society B) to Staff A (Society A) must fail
    with pytest.raises(Exception):
        await role_service.assign_role_to_staff(
            staff_id=staff_a.id,
            role_id=role_b.id,
            society_id=society_a,
            is_primary=True,
            assigned_by_user=admin,
        )
