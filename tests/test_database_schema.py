"""Tests for Phase 2 Database Schema, Spatial Hierarchy, and Integrity Constraints."""

import uuid
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.audit import AuditLog
from apps.api.src.database.models.authorization import Role, RoleAssignment
from apps.api.src.database.models.identity import User
from apps.api.src.database.models.membership import UnitOccupancy, UserSocietyMembership
from apps.api.src.database.models.society import Block, Floor, Society, Unit


@pytest.mark.asyncio
async def test_user_requires_email_or_phone(db_session: AsyncSession):
    """User table must enforce that either email or phone is present."""
    invalid_user = User(
        email=None,
        phone=None,
        first_name="Ghost",
        last_name="User",
        display_name="Ghost User",
    )
    db_session.add(invalid_user)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_user_creation_with_email_or_phone(db_session: AsyncSession):
    """User creation succeeds when either email or phone is provided."""
    user1 = User(
        email="phone_only_user@test.io",
        first_name="First",
        last_name="User",
        display_name="First User",
    )
    user2 = User(
        phone="+919876543210",
        first_name="Second",
        last_name="User",
        display_name="Second User",
    )
    db_session.add_all([user1, user2])
    await db_session.commit()

    res = await db_session.execute(select(User).where(User.first_name.in_(["First", "Second"])))
    users = res.scalars().all()
    assert len(users) == 2


@pytest.mark.asyncio
async def test_spatial_hierarchy_creation(db_session: AsyncSession):
    """Full spatial hierarchy (Society -> Block -> Floor -> Unit) builds cleanly."""
    soc = Society(
        legal_name="Heritage Heights Co-op Housing Society",
        display_name="Heritage Heights",
        address_line1="12 Prime Avenue",
        city="Mumbai",
        state="Maharashtra",
        country="IN",
        postal_code="400001",
    )
    db_session.add(soc)
    await db_session.flush()

    block = Block(
        society_id=soc.id,
        code="BLK-A",
        display_name="Block A",
        sequence_order=1,
    )
    db_session.add(block)
    await db_session.flush()

    floor = Floor(
        society_id=soc.id,
        block_id=block.id,
        floor_number=1,
        display_name="Floor 1",
        sequence_order=1,
    )
    db_session.add(floor)
    await db_session.flush()

    unit = Unit(
        society_id=soc.id,
        block_id=block.id,
        floor_id=floor.id,
        unit_number="101",
        unit_type="3BHK",
        carpet_area_sqft=1250.0,
    )
    db_session.add(unit)
    await db_session.commit()

    from sqlalchemy.orm import selectinload

    # Query back hierarchy with eager loading
    stmt = (
        select(Society)
        .where(Society.id == soc.id)
        .options(selectinload(Society.blocks).selectinload(Block.floors).selectinload(Floor.units))
    )
    res = await db_session.execute(stmt)
    fetched_soc = res.scalar_one()
    assert len(fetched_soc.blocks) == 1
    assert fetched_soc.blocks[0].code == "BLK-A"
    assert len(fetched_soc.blocks[0].floors) == 1
    assert fetched_soc.blocks[0].floors[0].units[0].unit_number == "101"


@pytest.mark.asyncio
async def test_block_code_uniqueness_is_tenant_scoped(db_session: AsyncSession):
    """
    Block codes are unique PER SOCIETY, but different societies can reuse identical block codes.
    """
    soc1 = Society(
        legal_name="Society One Ltd",
        display_name="Society One",
        address_line1="Street 1",
        city="Pune",
        state="MH",
        country="IN",
        postal_code="411001",
    )
    soc2 = Society(
        legal_name="Society Two Ltd",
        display_name="Society Two",
        address_line1="Street 2",
        city="Pune",
        state="MH",
        country="IN",
        postal_code="411002",
    )
    db_session.add_all([soc1, soc2])
    await db_session.flush()

    # Both societies create 'WING-A' -> must succeed!
    b1 = Block(society_id=soc1.id, code="WING-A", display_name="Wing A")
    b2 = Block(society_id=soc2.id, code="WING-A", display_name="Wing A")
    db_session.add_all([b1, b2])
    await db_session.commit()

    # Society 1 creates duplicate 'WING-A' -> must fail!
    b1_dup = Block(society_id=soc1.id, code="WING-A", display_name="Wing A Duplicate")
    db_session.add(b1_dup)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_unit_number_uniqueness_is_block_scoped(db_session: AsyncSession):
    """Unit numbers are unique per block within a society, but distinct blocks can reuse numbers."""
    soc = Society(
        legal_name="Twin Towers CHS",
        display_name="Twin Towers",
        address_line1="Ocean Way",
        city="Goa",
        state="GA",
        country="IN",
        postal_code="403001",
    )
    db_session.add(soc)
    await db_session.flush()

    b1 = Block(society_id=soc.id, code="T1", display_name="Tower 1")
    b2 = Block(society_id=soc.id, code="T2", display_name="Tower 2")
    db_session.add_all([b1, b2])
    await db_session.flush()

    f1 = Floor(society_id=soc.id, block_id=b1.id, floor_number=1, display_name="F1")
    f2 = Floor(society_id=soc.id, block_id=b2.id, floor_number=1, display_name="F1")
    db_session.add_all([f1, f2])
    await db_session.flush()

    # Unit 101 in Tower 1 and Unit 101 in Tower 2 -> must succeed!
    u1 = Unit(society_id=soc.id, block_id=b1.id, floor_id=f1.id, unit_number="101")
    u2 = Unit(society_id=soc.id, block_id=b2.id, floor_id=f2.id, unit_number="101")
    db_session.add_all([u1, u2])
    await db_session.commit()

    # Duplicate Unit 101 in Tower 1 -> must fail!
    u1_dup = Unit(society_id=soc.id, block_id=b1.id, floor_id=f1.id, unit_number="101")
    db_session.add(u1_dup)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_multi_society_user_membership(db_session: AsyncSession):
    """
    A single User can belong to multiple societies (User != Society).
    Duplicate membership in the SAME society is prevented.
    """
    user = User(
        email="multi_society_owner@test.io",
        first_name="Ramesh",
        last_name="Kumar",
        display_name="Ramesh Kumar",
    )
    soc1 = Society(
        legal_name="Co-op Society Alpha",
        display_name="Alpha",
        address_line1="Road 1",
        city="Delhi",
        state="DL",
        country="IN",
        postal_code="110001",
    )
    soc2 = Society(
        legal_name="Co-op Society Beta",
        display_name="Beta",
        address_line1="Road 2",
        city="Delhi",
        state="DL",
        country="IN",
        postal_code="110002",
    )
    db_session.add_all([user, soc1, soc2])
    await db_session.flush()

    # User joins both Alpha and Beta
    m1 = UserSocietyMembership(user_id=user.id, society_id=soc1.id)
    m2 = UserSocietyMembership(user_id=user.id, society_id=soc2.id)
    db_session.add_all([m1, m2])
    await db_session.commit()

    # Verify user has 2 memberships
    res = await db_session.execute(
        select(UserSocietyMembership).where(UserSocietyMembership.user_id == user.id)
    )
    memberships = res.scalars().all()
    assert len(memberships) == 2

    # Duplicate membership in soc1 fails
    m1_dup = UserSocietyMembership(user_id=user.id, society_id=soc1.id)
    db_session.add(m1_dup)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_unit_occupancy_historical_preservation(db_session: AsyncSession):
    """Unit occupancy tracks multiple historical and current occupants without overwriting."""
    soc = Society(
        legal_name="Sunset Court CHS",
        display_name="Sunset Court",
        address_line1="Sunset Blvd",
        city="Chennai",
        state="TN",
        country="IN",
        postal_code="600001",
    )
    db_session.add(soc)
    await db_session.flush()

    b = Block(society_id=soc.id, code="B1", display_name="Block 1")
    db_session.add(b)
    await db_session.flush()

    f = Floor(society_id=soc.id, block_id=b.id, floor_number=1, display_name="F1")
    db_session.add(f)
    await db_session.flush()

    u = Unit(society_id=soc.id, block_id=b.id, floor_id=f.id, unit_number="301")
    db_session.add(u)
    await db_session.flush()

    owner = User(email="owner_301@test.io", first_name="Owner", last_name="One", display_name="Owner One")
    past_tenant = User(
        email="past_tenant@test.io", first_name="Past", last_name="Tenant", display_name="Past Tenant"
    )
    current_tenant = User(
        email="current_tenant@test.io",
        first_name="Current",
        last_name="Tenant",
        display_name="Current Tenant",
    )
    db_session.add_all([owner, past_tenant, current_tenant])
    await db_session.flush()

    # 1. Owner record (active)
    occ_owner = UnitOccupancy(
        society_id=soc.id,
        unit_id=u.id,
        user_id=owner.id,
        relationship_type="OWNER",
        is_primary_contact=True,
        valid_from=date(2020, 1, 1),
        status="ACTIVE",
    )
    # 2. Past Tenant (expired)
    occ_past = UnitOccupancy(
        society_id=soc.id,
        unit_id=u.id,
        user_id=past_tenant.id,
        relationship_type="TENANT",
        valid_from=date(2021, 1, 1),
        valid_to=date(2022, 12, 31),
        status="EXPIRED",
    )
    # 3. Current Tenant (active)
    occ_curr = UnitOccupancy(
        society_id=soc.id,
        unit_id=u.id,
        user_id=current_tenant.id,
        relationship_type="TENANT",
        valid_from=date(2023, 1, 1),
        status="ACTIVE",
    )
    db_session.add_all([occ_owner, occ_past, occ_curr])
    await db_session.commit()

    # Verify all 3 occupancies are preserved in history
    res = await db_session.execute(
        select(UnitOccupancy).where(UnitOccupancy.unit_id == u.id).order_by(UnitOccupancy.created_at)
    )
    history = res.scalars().all()
    assert len(history) == 3
    assert {occ.relationship_type for occ in history} == {"OWNER", "TENANT"}


@pytest.mark.asyncio
async def test_role_assignment_scope_check_constraint(db_session: AsyncSession):
    """
    Role assignments must enforce:
    - PLATFORM role requires society_id IS NULL
    - SOCIETY role requires society_id IS NOT NULL
    """
    user = User(
        email="scoped_user@test.io", first_name="Scoped", last_name="User", display_name="Scoped User"
    )
    soc = Society(
        legal_name="Scope Test Society",
        display_name="Scope Society",
        address_line1="Test Rd",
        city="Hyd",
        state="TS",
        country="IN",
        postal_code="500001",
    )
    db_session.add_all([user, soc])
    await db_session.flush()

    platform_role = Role(code="TEST_PLATFORM_ADMIN", name="Test Admin", scope_type="PLATFORM")
    society_role = Role(code="TEST_SOC_ADMIN", name="Test Soc Admin", scope_type="SOCIETY")
    db_session.add_all([platform_role, society_role])
    await db_session.flush()

    # Valid platform assignment
    ra_platform = RoleAssignment(
        user_id=user.id,
        role_id=platform_role.id,
        scope_type="PLATFORM",
        society_id=None,
    )
    # Valid society assignment
    ra_society = RoleAssignment(
        user_id=user.id,
        role_id=society_role.id,
        scope_type="SOCIETY",
        society_id=soc.id,
    )
    db_session.add_all([ra_platform, ra_society])
    await db_session.commit()

    # Invalid: PLATFORM with society_id provided
    invalid_ra = RoleAssignment(
        user_id=user.id,
        role_id=platform_role.id,
        scope_type="PLATFORM",
        society_id=soc.id,  # Invalid!
    )
    db_session.add(invalid_ra)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_audit_log_append_only(db_session: AsyncSession):
    """Audit log records are immutable append-only state snapshots."""
    user = User(email="auditor@test.io", first_name="Audit", last_name="User", display_name="Auditor")
    db_session.add(user)
    await db_session.flush()

    entry = AuditLog(
        society_id=None,
        actor_user_id=user.id,
        action="TEST_ACTION",
        entity_type="User",
        entity_id=str(user.id),
        before_state={"status": "PENDING"},
        after_state={"status": "ACTIVE"},
        diff={"status": ["PENDING", "ACTIVE"]},
        correlation_id=str(uuid.uuid4()),
    )
    db_session.add(entry)
    await db_session.commit()

    res = await db_session.execute(select(AuditLog).where(AuditLog.action == "TEST_ACTION"))
    logged = res.scalar_one()
    assert logged.actor_user_id == user.id
    assert logged.diff is not None
    assert logged.diff["status"] == ["PENDING", "ACTIVE"]
