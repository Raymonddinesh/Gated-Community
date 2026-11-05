"""Targeted tests for Phase 7 Domain & Security Finalization.

Covers:
1. Ownership aggregate concurrency protection (<= 100%)
2. Domain separation:
   - Delegate does not imply occupancy
   - Occupancy does not imply delegation
   - Independent coexistence
   - Delegate revocation does not end occupancy
   - Move-out does not revoke delegation
3. Auto-membership security & zero privileged roles
4. Delegate permission escalation prevention (delegates cannot delegate)
5. Canonical RBAC gate evaluation (unreleased modules return False)
6. Same-society relational integrity (cross-society unit rejections)
7. Concurrent tenant move-in overlap rejection (409)
8. Atomic ownership transfer (100% and partial share transfer)
9. Open business rule validation (active ownership total < 100%)
10. Historical billing, payment, receipt, and General Ledger immutability
"""

import asyncio
import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.audit import AuditLog
from apps.api.src.database.models.authorization import RoleAssignment
from apps.api.src.database.models.billing import Invoice, Payment, Receipt
from apps.api.src.database.models.finance import JournalEntry
from apps.api.src.database.models.identity import User
from apps.api.src.database.models.membership import (
    ResidentDelegate,
    UnitOccupancy,
    UnitOwnership,
    UserSocietyMembership,
)
from apps.api.src.database.models.society import Floor, Unit
from apps.api.src.residents.application.household_service import HouseholdService
from infrastructure.scripts.seed_dev_data import (
    UUID_SOCIETY_A,
    UUID_SOCIETY_B,
    UUID_USER_DELEGATE_A,
    UUID_USER_OWNER_A,
    UUID_USER_TENANT_A,
)

SOCIETY_A_STR = str(UUID_SOCIETY_A)
SOCIETY_B_STR = str(UUID_SOCIETY_B)


async def get_token(client: AsyncClient, identifier: str) -> str:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"identifier": identifier, "password": "Password123!"},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


async def create_isolated_unit(db: AsyncSession, society_id: uuid.UUID, unit_number: str) -> Unit:
    stmt = select(Floor).where(Floor.society_id == society_id)
    res = await db.execute(stmt)
    floor = res.scalars().first()
    assert floor is not None

    unit = Unit(
        id=uuid.uuid4(),
        society_id=society_id,
        block_id=floor.block_id,
        floor_id=floor.id,
        unit_number=unit_number,
        unit_type="2BHK",
        occupancy_status="VACANT",
        status="ACTIVE",
    )
    db.add(unit)
    await db.flush()
    return unit


async def create_test_user(db: AsyncSession, username: str) -> User:
    from apps.api.src.auth.security.password import hash_password

    u = User(
        id=uuid.uuid4(),
        email=f"{username}@example.com",
        phone=f"+9199{uuid.uuid4().int % 100000000:08d}",
        password_hash=hash_password("Password123!"),
        first_name="Test",
        last_name=username,
        display_name=f"Test {username}",
        status="ACTIVE",
    )
    db.add(u)
    await db.flush()
    return u


# ---------------------------------------------------------------------------
# 1. Ownership Aggregate Concurrency Protection
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_concurrent_ownership_percentage_limit(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    """
    Scenario:
    Owner A holds 60%.
    Two concurrent requests try to add Owner B (25%) and Owner C (25%).
    Total attempted = 110%.
    Protection: Exactly ONE succeeds, ONE fails (400).
    Final state: <= 100% (specifically 85%).
    """
    admin_token = await get_token(async_client, "superadmin@societysphere.io")
    headers = {"Authorization": f"Bearer {admin_token}", "X-Society-ID": SOCIETY_A_STR}

    unit = await create_isolated_unit(db_session, UUID_SOCIETY_A, "CONC-OWN-101")
    user_b = await create_test_user(db_session, f"user_b_{uuid.uuid4().hex[:6]}")
    user_c = await create_test_user(db_session, f"user_c_{uuid.uuid4().hex[:6]}")

    # Add initial Owner A with 60%
    init_resp = await async_client.post(
        f"/api/v1/units/{unit.id}/owners",
        headers=headers,
        json={
            "user_id": str(UUID_USER_OWNER_A),
            "ownership_percentage": 60.0,
            "start_date": "2025-01-01",
            "is_primary": True,
        },
    )
    assert init_resp.status_code == 200

    # Launch concurrent additions of 25% each
    async def try_add_owner(target_user_id: uuid.UUID):
        return await async_client.post(
            f"/api/v1/units/{unit.id}/owners",
            headers=headers,
            json={
                "user_id": str(target_user_id),
                "ownership_percentage": 25.0,
                "start_date": "2025-01-01",
                "is_primary": False,
            },
        )

    res1, res2 = await asyncio.gather(
        try_add_owner(user_b.id),
        try_add_owner(user_c.id),
        return_exceptions=False,
    )

    statuses = [res1.status_code, res2.status_code]
    assert 200 in statuses, f"Expected at least one success: {statuses}"
    assert 400 in statuses, f"Expected one rejection due to percentage limit: {statuses}"

    # Verify database active sum
    stmt = select(func.sum(UnitOwnership.ownership_percentage)).where(
        UnitOwnership.unit_id == unit.id,
        UnitOwnership.status == "ACTIVE",
    )
    total_active = await db_session.scalar(stmt)
    assert Decimal(str(total_active)) == Decimal("85.00"), f"Expected 85%, got {total_active}"


# ---------------------------------------------------------------------------
# 2. Domain Separation: Ownership != Occupancy != Delegation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_domain_separation_delegate_does_not_imply_occupancy(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    owner_token = await get_token(async_client, "owner.a@palmstree.in")
    owner_headers = {"Authorization": f"Bearer {owner_token}", "X-Society-ID": SOCIETY_A_STR}
    admin_token = await get_token(async_client, "superadmin@societysphere.io")
    admin_headers = {"Authorization": f"Bearer {admin_token}", "X-Society-ID": SOCIETY_A_STR}

    unit = await create_isolated_unit(db_session, UUID_SOCIETY_A, "DOM-SEP-101")
    delegate_user = await create_test_user(db_session, f"dlg_{uuid.uuid4().hex[:6]}")

    # Set up active owner so delegation can be granted
    await async_client.post(
        f"/api/v1/units/{unit.id}/owners",
        headers=admin_headers,
        json={
            "user_id": str(UUID_USER_OWNER_A),
            "ownership_percentage": 100.0,
            "start_date": "2025-01-01",
        },
    )

    # Designate delegate via /api/v1/residents/me/delegates
    dlg_resp = await async_client.post(
        "/api/v1/residents/me/delegates",
        headers=owner_headers,
        json={
            "unit_id": str(unit.id),
            "delegate_user_id": str(delegate_user.id),
            "permissions": ["billing.view"],
            "valid_from": "2025-01-01",
        },
    )
    assert dlg_resp.status_code == 200

    # Verify no occupancy record exists
    stmt = select(UnitOccupancy).where(
        UnitOccupancy.unit_id == unit.id,
        UnitOccupancy.user_id == delegate_user.id,
    )
    res = await db_session.execute(stmt)
    assert res.scalar_one_or_none() is None, "Delegate must NOT automatically have occupancy!"


@pytest.mark.asyncio
async def test_domain_separation_occupancy_does_not_imply_delegation(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin_token = await get_token(async_client, "superadmin@societysphere.io")
    headers = {"Authorization": f"Bearer {admin_token}", "X-Society-ID": SOCIETY_A_STR}

    unit = await create_isolated_unit(db_session, UUID_SOCIETY_A, "DOM-SEP-102")
    tenant_user = await create_test_user(db_session, f"ten_{uuid.uuid4().hex[:6]}")

    # Move in tenant
    move_resp = await async_client.post(
        f"/api/v1/units/{unit.id}/occupancies",
        headers=headers,
        json={
            "user_id": str(tenant_user.id),
            "relationship_type": "TENANT",
            "valid_from": "2025-01-01",
        },
    )
    assert move_resp.status_code == 200

    # Verify no delegate record exists
    stmt = select(ResidentDelegate).where(
        ResidentDelegate.unit_id == unit.id,
        ResidentDelegate.delegate_user_id == tenant_user.id,
    )
    res = await db_session.execute(stmt)
    assert res.scalar_one_or_none() is None, "Occupant must NOT automatically have delegation!"


@pytest.mark.asyncio
async def test_domain_separation_independent_coexistence(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    owner_token = await get_token(async_client, "owner.a@palmstree.in")
    owner_headers = {"Authorization": f"Bearer {owner_token}", "X-Society-ID": SOCIETY_A_STR}
    admin_token = await get_token(async_client, "superadmin@societysphere.io")
    admin_headers = {"Authorization": f"Bearer {admin_token}", "X-Society-ID": SOCIETY_A_STR}

    unit = await create_isolated_unit(db_session, UUID_SOCIETY_A, "DOM-SEP-103")
    user = await create_test_user(db_session, f"dual_{uuid.uuid4().hex[:6]}")

    # Give unit an owner
    await async_client.post(
        f"/api/v1/units/{unit.id}/owners",
        headers=admin_headers,
        json={"user_id": str(UUID_USER_OWNER_A), "ownership_percentage": 100.0, "start_date": "2025-01-01"},
    )

    # User is moved in as occupant
    await async_client.post(
        f"/api/v1/units/{unit.id}/occupancies",
        headers=admin_headers,
        json={"user_id": str(user.id), "relationship_type": "TENANT", "valid_from": "2025-01-01"},
    )

    # Same user is also granted delegation
    dlg_res = await async_client.post(
        "/api/v1/residents/me/delegates",
        headers=owner_headers,
        json={
            "unit_id": str(unit.id),
            "delegate_user_id": str(user.id),
            "permissions": ["billing.view"],
            "valid_from": "2025-01-01",
        },
    )
    assert dlg_res.status_code == 200

    # Both records exist independently
    occ_res = await db_session.execute(
        select(UnitOccupancy).where(UnitOccupancy.unit_id == unit.id, UnitOccupancy.user_id == user.id)
    )
    dlg_res_db = await db_session.execute(
        select(ResidentDelegate).where(
            ResidentDelegate.unit_id == unit.id, ResidentDelegate.delegate_user_id == user.id
        )
    )
    assert occ_res.scalar_one_or_none() is not None
    assert dlg_res_db.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_domain_separation_revoking_delegate_does_not_end_occupancy(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    owner_token = await get_token(async_client, "owner.a@palmstree.in")
    owner_headers = {"Authorization": f"Bearer {owner_token}", "X-Society-ID": SOCIETY_A_STR}
    admin_token = await get_token(async_client, "superadmin@societysphere.io")
    admin_headers = {"Authorization": f"Bearer {admin_token}", "X-Society-ID": SOCIETY_A_STR}

    unit = await create_isolated_unit(db_session, UUID_SOCIETY_A, "DOM-SEP-104")
    user = await create_test_user(db_session, f"rev_{uuid.uuid4().hex[:6]}")

    await async_client.post(
        f"/api/v1/units/{unit.id}/owners",
        headers=admin_headers,
        json={"user_id": str(UUID_USER_OWNER_A), "ownership_percentage": 100.0, "start_date": "2025-01-01"},
    )
    occ_res = await async_client.post(
        f"/api/v1/units/{unit.id}/occupancies",
        headers=admin_headers,
        json={"user_id": str(user.id), "relationship_type": "TENANT", "valid_from": "2025-01-01"},
    )
    occ_id = occ_res.json()["id"]

    dlg_res = await async_client.post(
        "/api/v1/residents/me/delegates",
        headers=owner_headers,
        json={
            "unit_id": str(unit.id),
            "delegate_user_id": str(user.id),
            "permissions": ["billing.view"],
            "valid_from": "2025-01-01",
        },
    )
    assert dlg_res.status_code == 200
    dlg_id = dlg_res.json()["id"]

    # Revoke delegation
    revoke_resp = await async_client.post(
        f"/api/v1/delegates/{dlg_id}/revoke",
        headers=owner_headers,
        json={"reason": "Revoking delegate authority"},
    )
    assert revoke_resp.status_code == 200

    # Verify occupancy remains ACTIVE
    occ_db = await db_session.get(UnitOccupancy, uuid.UUID(occ_id))
    assert occ_db is not None
    assert occ_db.status == "ACTIVE", "Revoking delegation must NOT end occupancy!"


@pytest.mark.asyncio
async def test_domain_separation_move_out_does_not_revoke_delegation(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    owner_token = await get_token(async_client, "owner.a@palmstree.in")
    owner_headers = {"Authorization": f"Bearer {owner_token}", "X-Society-ID": SOCIETY_A_STR}
    admin_token = await get_token(async_client, "superadmin@societysphere.io")
    admin_headers = {"Authorization": f"Bearer {admin_token}", "X-Society-ID": SOCIETY_A_STR}

    unit = await create_isolated_unit(db_session, UUID_SOCIETY_A, "DOM-SEP-105")
    user = await create_test_user(db_session, f"mout_{uuid.uuid4().hex[:6]}")

    await async_client.post(
        f"/api/v1/units/{unit.id}/owners",
        headers=admin_headers,
        json={"user_id": str(UUID_USER_OWNER_A), "ownership_percentage": 100.0, "start_date": "2025-01-01"},
    )
    occ_res = await async_client.post(
        f"/api/v1/units/{unit.id}/occupancies",
        headers=admin_headers,
        json={"user_id": str(user.id), "relationship_type": "TENANT", "valid_from": "2025-01-01"},
    )
    occ_id = occ_res.json()["id"]

    dlg_res = await async_client.post(
        "/api/v1/residents/me/delegates",
        headers=owner_headers,
        json={
            "unit_id": str(unit.id),
            "delegate_user_id": str(user.id),
            "permissions": ["billing.view"],
            "valid_from": "2025-01-01",
        },
    )
    assert dlg_res.status_code == 200
    dlg_id = dlg_res.json()["id"]

    # Occupant moves out
    move_out_resp = await async_client.post(
        f"/api/v1/occupancies/{occ_id}/end",
        headers=admin_headers,
        json={"reason": "Lease ended"},
    )
    assert move_out_resp.status_code == 200

    # Verify delegation remains ACTIVE
    dlg_db = await db_session.get(ResidentDelegate, uuid.UUID(dlg_id))
    assert dlg_db is not None
    assert dlg_db.status == "ACTIVE", "Moving out must NOT revoke delegation!"


# ---------------------------------------------------------------------------
# 3. Auto-Membership Security Review
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_auto_membership_security_and_zero_roles(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin_token = await get_token(async_client, "superadmin@societysphere.io")
    headers = {"Authorization": f"Bearer {admin_token}", "X-Society-ID": SOCIETY_A_STR}

    unit = await create_isolated_unit(db_session, UUID_SOCIETY_A, "AUTO-MEM-101")
    brand_new_user = await create_test_user(db_session, f"automem_{uuid.uuid4().hex[:6]}")

    # Ensure no prior membership
    mem_stmt = select(UserSocietyMembership).where(
        UserSocietyMembership.user_id == brand_new_user.id,
        UserSocietyMembership.society_id == UUID_SOCIETY_A,
    )
    assert (await db_session.execute(mem_stmt)).scalar_one_or_none() is None

    # Move-in
    move_resp = await async_client.post(
        f"/api/v1/units/{unit.id}/occupancies",
        headers=headers,
        json={
            "user_id": str(brand_new_user.id),
            "relationship_type": "TENANT",
            "valid_from": "2025-01-01",
        },
    )
    assert move_resp.status_code == 200

    # 1. Membership created
    mem_created = (await db_session.execute(mem_stmt)).scalar_one_or_none()
    assert mem_created is not None
    assert mem_created.membership_status == "ACTIVE"

    # 2. ZERO roles assigned (cannot escalate privileges)
    role_stmt = select(RoleAssignment).where(
        RoleAssignment.user_id == brand_new_user.id,
        RoleAssignment.society_id == UUID_SOCIETY_A,
    )
    assigned_roles = (await db_session.execute(role_stmt)).scalars().all()
    assert len(assigned_roles) == 0, f"Auto-membership must NOT grant any roles! Found: {assigned_roles}"

    # 3. Audit log recorded
    audit_stmt = select(AuditLog).where(
        AuditLog.action == "membership.auto_enrolled",
        AuditLog.entity_id == str(brand_new_user.id),
        AuditLog.society_id == UUID_SOCIETY_A,
    )
    audit_event = (await db_session.execute(audit_stmt)).scalar_one_or_none()
    assert audit_event is not None, "Auto-membership must record audit event 'membership.auto_enrolled'!"


# ---------------------------------------------------------------------------
# 4. Delegate Permission Escalation & Canonical RBAC Gate
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_delegate_cannot_delegate(async_client: AsyncClient, db_session: AsyncSession) -> None:
    from apps.api.src.residents.domain.exceptions import UnauthorizedDelegateError
    from apps.api.src.residents.schemas import DelegateCreate

    unit = await create_isolated_unit(db_session, UUID_SOCIETY_A, "NO-DEL-101")
    delegate_user = await create_test_user(db_session, f"dlg_only_{uuid.uuid4().hex[:6]}")
    target_user = await create_test_user(db_session, f"target_{uuid.uuid4().hex[:6]}")

    household_service = HouseholdService(db_session)

    # Attempt to have delegate_user delegate to target_user (delegates cannot delegate)
    with pytest.raises(UnauthorizedDelegateError) as exc_info:
        await household_service.create_delegate(
            society_id=UUID_SOCIETY_A,
            unit_id=unit.id,
            delegator_user_id=delegate_user.id,
            data=DelegateCreate(
                unit_id=unit.id,
                delegate_user_id=target_user.id,
                permissions=["billing.view"],
                valid_from=date(2025, 1, 1),
            ),
            actor_user_id=delegate_user.id,
        )
    assert "not an active occupant or owner" in str(exc_info.value)


@pytest.mark.asyncio
async def test_delegate_authorization_canonical_rbac_gate(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    owner_token = await get_token(async_client, "owner.a@palmstree.in")
    owner_headers = {"Authorization": f"Bearer {owner_token}", "X-Society-ID": SOCIETY_A_STR}
    admin_token = await get_token(async_client, "superadmin@societysphere.io")
    admin_headers = {"Authorization": f"Bearer {admin_token}", "X-Society-ID": SOCIETY_A_STR}

    household_service = HouseholdService(db_session)
    unit = await create_isolated_unit(db_session, UUID_SOCIETY_A, "RBAC-GATE-101")
    user = await create_test_user(db_session, f"dlg_gate_{uuid.uuid4().hex[:6]}")

    await async_client.post(
        f"/api/v1/units/{unit.id}/owners",
        headers=admin_headers,
        json={"user_id": str(UUID_USER_OWNER_A), "ownership_percentage": 100.0, "start_date": "2025-01-01"},
    )
    dlg_res = await async_client.post(
        "/api/v1/residents/me/delegates",
        headers=owner_headers,
        json={
            "unit_id": str(unit.id),
            "delegate_user_id": str(user.id),
            "permissions": ["billing.view", "complaint.create"],
            "valid_from": "2025-01-01",
        },
    )
    assert dlg_res.status_code == 200
    dlg_id = dlg_res.json()["id"]

    # 1. Canonical implemented module permission -> True
    auth_billing = await household_service.is_delegate_authorized(
        society_id=UUID_SOCIETY_A,
        delegate_user_id=user.id,
        unit_id=unit.id,
        permission_code="billing.view",
    )
    assert auth_billing is True

    # 2. Unreleased future module permission (complaint.create) -> returns False
    auth_complaint = await household_service.is_delegate_authorized(
        society_id=UUID_SOCIETY_A,
        delegate_user_id=user.id,
        unit_id=unit.id,
        permission_code="complaint.create",
    )
    assert auth_complaint is False, "Unreleased permissions must return False until Phase 8+!"

    # 3. Revoked delegate -> returns False
    await async_client.post(
        f"/api/v1/delegates/{dlg_id}/revoke",
        headers=owner_headers,
        json={"reason": "Revoked test"},
    )
    auth_after_revoke = await household_service.is_delegate_authorized(
        society_id=UUID_SOCIETY_A,
        delegate_user_id=user.id,
        unit_id=unit.id,
        permission_code="billing.view",
    )
    assert auth_after_revoke is False


# ---------------------------------------------------------------------------
# 5. Same-Society Relational Integrity
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_same_society_relational_integrity(async_client: AsyncClient, db_session: AsyncSession) -> None:
    admin_token = await get_token(async_client, "superadmin@societysphere.io")
    # Context is Society A
    headers = {"Authorization": f"Bearer {admin_token}", "X-Society-ID": SOCIETY_A_STR}

    # Create Unit belonging to Society B
    unit_b = await create_isolated_unit(db_session, UUID_SOCIETY_B, "SOC-B-UNIT-101")

    # 1. Add owner across society boundary -> 404
    own_resp = await async_client.post(
        f"/api/v1/units/{unit_b.id}/owners",
        headers=headers,
        json={"user_id": str(UUID_USER_OWNER_A), "ownership_percentage": 100.0, "start_date": "2025-01-01"},
    )
    assert own_resp.status_code == 404

    # 2. Move-in across society boundary -> 404
    move_resp = await async_client.post(
        f"/api/v1/units/{unit_b.id}/occupants/move-in",
        headers=headers,
        json={"user_id": str(UUID_USER_TENANT_A), "relationship_type": "TENANT", "valid_from": "2025-01-01"},
    )
    assert move_resp.status_code == 404

    # 3. Add family member across society boundary -> 404
    fam_resp = await async_client.post(
        f"/api/v1/units/{unit_b.id}/family-members",
        headers=headers,
        json={
            "primary_resident_user_id": str(UUID_USER_OWNER_A),
            "name": "Relative",
            "relationship": "SPOUSE",
        },
    )
    assert fam_resp.status_code == 404

    # 4. Delegate across society boundary -> 404
    dlg_resp = await async_client.post(
        f"/api/v1/units/{unit_b.id}/delegates",
        headers=headers,
        json={
            "delegator_user_id": str(UUID_USER_OWNER_A),
            "delegate_user_id": str(UUID_USER_DELEGATE_A),
            "permissions": ["billing.view"],
            "valid_from": "2025-01-01",
        },
    )
    assert dlg_resp.status_code == 404


# ---------------------------------------------------------------------------
# 6. Concurrent Tenant Move-in Overlap Protection
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_concurrent_tenant_move_in_overlap_protection(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin_token = await get_token(async_client, "superadmin@societysphere.io")
    headers = {"Authorization": f"Bearer {admin_token}", "X-Society-ID": SOCIETY_A_STR}

    unit = await create_isolated_unit(db_session, UUID_SOCIETY_A, "CONC-TEN-101")
    tenant1 = await create_test_user(db_session, f"t1_{uuid.uuid4().hex[:6]}")
    tenant2 = await create_test_user(db_session, f"t2_{uuid.uuid4().hex[:6]}")

    async def try_move_in(tenant_id: uuid.UUID):
        return await async_client.post(
            f"/api/v1/units/{unit.id}/occupancies",
            headers=headers,
            json={
                "user_id": str(tenant_id),
                "relationship_type": "TENANT",
                "valid_from": "2026-06-01",
                "valid_to": "2027-05-31",
            },
        )

    res1, res2 = await asyncio.gather(
        try_move_in(tenant1.id),
        try_move_in(tenant2.id),
        return_exceptions=False,
    )

    statuses = [res1.status_code, res2.status_code]
    assert 200 in statuses, f"Expected one successful move-in: {statuses}"
    assert 409 in statuses, f"Expected one rejection due to tenant lease overlap (409): {statuses}"

    # Verify database has exactly 1 active tenant
    active_tenants = (
        (
            await db_session.execute(
                select(UnitOccupancy).where(
                    UnitOccupancy.unit_id == unit.id,
                    UnitOccupancy.relationship_type == "TENANT",
                    UnitOccupancy.status == "ACTIVE",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(active_tenants) == 1


# ---------------------------------------------------------------------------
# 7. Atomic Ownership Transfer Workflow
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_atomic_ownership_transfer_100_percent(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin_token = await get_token(async_client, "superadmin@societysphere.io")
    headers = {"Authorization": f"Bearer {admin_token}", "X-Society-ID": SOCIETY_A_STR}

    unit = await create_isolated_unit(db_session, UUID_SOCIETY_A, "XFER-100-101")
    owner_a = await create_test_user(db_session, f"src_own_{uuid.uuid4().hex[:6]}")
    owner_b = await create_test_user(db_session, f"dst_own_{uuid.uuid4().hex[:6]}")

    # Create 100% initial ownership
    init_res = await async_client.post(
        f"/api/v1/units/{unit.id}/owners",
        headers=headers,
        json={
            "user_id": str(owner_a.id),
            "ownership_percentage": 100.0,
            "start_date": "2024-01-01",
            "is_primary": True,
        },
    )
    src_own_id = init_res.json()["id"]

    # Execute 100% transfer
    transfer_res = await async_client.post(
        f"/api/v1/ownerships/{src_own_id}/transfer",
        headers=headers,
        json={
            "new_owner_user_id": str(owner_b.id),
            "transfer_percentage": 100.0,
            "transfer_date": "2026-01-01",
            "reason": "Sale Deed Registered",
            "is_primary": True,
        },
    )
    assert transfer_res.status_code == 200
    data = transfer_res.json()

    # Source ownership checks
    src = data["source_ownership"]
    assert src["status"] == "TRANSFERRED"
    assert src["is_primary"] is False
    assert src["end_date"] == "2026-01-01"

    # Destination ownership checks
    dst = data["new_ownership"]
    assert dst["status"] == "ACTIVE"
    assert dst["is_primary"] is True
    assert float(dst["ownership_percentage"]) == 100.0
    assert dst["user_id"] == str(owner_b.id)

    # History preservation: both records present
    hist_res = await async_client.get(f"/api/v1/units/{unit.id}/ownership-history", headers=headers)
    assert hist_res.status_code == 200
    assert len(hist_res.json()) == 2

    # Audit events
    xfer_audit = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "ownership.transferred",
                AuditLog.entity_id == src_own_id,
            )
        )
    ).scalar_one_or_none()
    assert xfer_audit is not None


@pytest.mark.asyncio
async def test_atomic_ownership_transfer_partial(async_client: AsyncClient, db_session: AsyncSession) -> None:
    admin_token = await get_token(async_client, "superadmin@societysphere.io")
    headers = {"Authorization": f"Bearer {admin_token}", "X-Society-ID": SOCIETY_A_STR}

    unit = await create_isolated_unit(db_session, UUID_SOCIETY_A, "XFER-PART-101")
    owner_a = await create_test_user(db_session, f"part_src_{uuid.uuid4().hex[:6]}")
    owner_b = await create_test_user(db_session, f"part_dst_{uuid.uuid4().hex[:6]}")

    init_res = await async_client.post(
        f"/api/v1/units/{unit.id}/owners",
        headers=headers,
        json={
            "user_id": str(owner_a.id),
            "ownership_percentage": 100.0,
            "start_date": "2024-01-01",
            "is_primary": True,
        },
    )
    src_own_id = init_res.json()["id"]

    # Transfer 35% to Owner B
    transfer_res = await async_client.post(
        f"/api/v1/ownerships/{src_own_id}/transfer",
        headers=headers,
        json={
            "new_owner_user_id": str(owner_b.id),
            "transfer_percentage": 35.0,
            "transfer_date": "2026-02-01",
            "reason": "Gift deed of 35% co-ownership",
            "is_primary": False,
        },
    )
    assert transfer_res.status_code == 200
    data = transfer_res.json()

    # Source retains 65% and remains ACTIVE
    assert float(data["source_ownership"]["ownership_percentage"]) == 65.0
    assert data["source_ownership"]["status"] == "ACTIVE"

    # Destination receives 35%
    assert float(data["new_ownership"]["ownership_percentage"]) == 35.0
    assert data["new_ownership"]["status"] == "ACTIVE"

    # Total active ownership percentage is exactly 100%
    active_owners = (await async_client.get(f"/api/v1/units/{unit.id}/owners", headers=headers)).json()
    assert len(active_owners) == 2
    total = sum(float(o["ownership_percentage"]) for o in active_owners)
    assert total == 100.0


# ---------------------------------------------------------------------------
# 8. Open Business Rule: Active Ownership Total < 100%
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_open_business_rule_partial_ownership_less_than_100(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    """
    Validates that active ownership total < 100% is explicitly allowed
    (e.g., unsold developer inventory or ongoing probate).
    """
    admin_token = await get_token(async_client, "superadmin@societysphere.io")
    headers = {"Authorization": f"Bearer {admin_token}", "X-Society-ID": SOCIETY_A_STR}

    unit = await create_isolated_unit(db_session, UUID_SOCIETY_A, "OPEN-RULE-101")
    owner = await create_test_user(db_session, f"builder_buyer_{uuid.uuid4().hex[:6]}")

    # Add single owner with 40% (remaining 60% with builder)
    res = await async_client.post(
        f"/api/v1/units/{unit.id}/owners",
        headers=headers,
        json={
            "user_id": str(owner.id),
            "ownership_percentage": 40.0,
            "start_date": "2025-01-01",
            "notes": "40% fractional title; 60% builder inventory",
        },
    )
    assert res.status_code == 200
    assert float(res.json()["ownership_percentage"]) == 40.0

    # Total active ownership is 40%, which is < 100% and completely valid
    active_owners = (await async_client.get(f"/api/v1/units/{unit.id}/owners", headers=headers)).json()
    total = sum(float(o["ownership_percentage"]) for o in active_owners)
    assert total == 40.0


# ---------------------------------------------------------------------------
# 9. Historical Billing, Payment, Receipt, and General Ledger Immutability
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_historical_billing_and_payment_immutability(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    """
    Verifies that resident lifecycle transitions (move-out, ownership transfer)
    NEVER alter historical invoices, payments, receipts, or General Ledger entries.
    """
    admin_token = await get_token(async_client, "superadmin@societysphere.io")
    headers = {"Authorization": f"Bearer {admin_token}", "X-Society-ID": SOCIETY_A_STR}

    # Record baseline counts and financial metrics for Society A
    inv_count_before = (
        await db_session.execute(select(func.count(Invoice.id)).where(Invoice.society_id == UUID_SOCIETY_A))
    ).scalar_one()
    inv_sum_before = (
        await db_session.execute(
            select(func.sum(Invoice.grand_total)).where(Invoice.society_id == UUID_SOCIETY_A)
        )
    ).scalar_one()

    pay_count_before = (
        await db_session.execute(select(func.count(Payment.id)).where(Payment.society_id == UUID_SOCIETY_A))
    ).scalar_one()
    pay_sum_before = (
        await db_session.execute(select(func.sum(Payment.amount)).where(Payment.society_id == UUID_SOCIETY_A))
    ).scalar_one()

    rec_count_before = (
        await db_session.execute(select(func.count(Receipt.id)).where(Receipt.society_id == UUID_SOCIETY_A))
    ).scalar_one()

    gl_count_before = (
        await db_session.execute(
            select(func.count(JournalEntry.id)).where(JournalEntry.society_id == UUID_SOCIETY_A)
        )
    ).scalar_one()

    # Now perform resident lifecycle events:
    # 1. Create a unit with owner and occupant
    unit = await create_isolated_unit(db_session, UUID_SOCIETY_A, "HIST-FIN-101")
    owner = await create_test_user(db_session, f"fin_own_{uuid.uuid4().hex[:6]}")
    tenant = await create_test_user(db_session, f"fin_ten_{uuid.uuid4().hex[:6]}")
    new_owner = await create_test_user(db_session, f"fin_new_own_{uuid.uuid4().hex[:6]}")

    own_res = await async_client.post(
        f"/api/v1/units/{unit.id}/owners",
        headers=headers,
        json={"user_id": str(owner.id), "ownership_percentage": 100.0, "start_date": "2024-01-01"},
    )
    own_id = own_res.json()["id"]

    move_in_res = await async_client.post(
        f"/api/v1/units/{unit.id}/occupancies",
        headers=headers,
        json={"user_id": str(tenant.id), "relationship_type": "TENANT", "valid_from": "2025-01-01"},
    )
    occ_id = move_in_res.json()["id"]

    # 2. Perform Move-out
    await async_client.post(
        f"/api/v1/occupancies/{occ_id}/end",
        headers=headers,
        json={"reason": "Moved to another city"},
    )

    # 3. Perform Ownership Transfer
    await async_client.post(
        f"/api/v1/ownerships/{own_id}/transfer",
        headers=headers,
        json={"new_owner_user_id": str(new_owner.id), "transfer_percentage": 100.0, "reason": "Sold unit"},
    )

    # Re-evaluate all baseline metrics for Society A
    inv_count_after = (
        await db_session.execute(select(func.count(Invoice.id)).where(Invoice.society_id == UUID_SOCIETY_A))
    ).scalar_one()
    inv_sum_after = (
        await db_session.execute(
            select(func.sum(Invoice.grand_total)).where(Invoice.society_id == UUID_SOCIETY_A)
        )
    ).scalar_one()

    pay_count_after = (
        await db_session.execute(select(func.count(Payment.id)).where(Payment.society_id == UUID_SOCIETY_A))
    ).scalar_one()
    pay_sum_after = (
        await db_session.execute(select(func.sum(Payment.amount)).where(Payment.society_id == UUID_SOCIETY_A))
    ).scalar_one()

    rec_count_after = (
        await db_session.execute(select(func.count(Receipt.id)).where(Receipt.society_id == UUID_SOCIETY_A))
    ).scalar_one()

    gl_count_after = (
        await db_session.execute(
            select(func.count(JournalEntry.id)).where(JournalEntry.society_id == UUID_SOCIETY_A)
        )
    ).scalar_one()

    # Historical financial invariants MUST match exactly
    assert inv_count_after == inv_count_before, "Invoices must remain immutable!"
    assert inv_sum_after == inv_sum_before, "Invoice totals must remain immutable!"
    assert pay_count_after == pay_count_before, "Payments must remain immutable!"
    assert pay_sum_after == pay_sum_before, "Payment totals must remain immutable!"
    assert rec_count_after == rec_count_before, "Receipts must remain immutable!"
    assert gl_count_after == gl_count_before, "General Ledger journal entries must remain immutable!"
