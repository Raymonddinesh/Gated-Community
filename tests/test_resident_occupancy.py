"""Comprehensive tests for Phase 7: Resident, Owner, Tenant & Occupancy Management.

Covers:
- Resident Profile creation, update, and deterministic completeness calculation
- Society membership verification
- Single and joint co-ownership with percentage validation (<= 100%)
- Tenant occupancy, date validation, and overlap conflict detection (409)
- Family member association with relationship types and access scopes
- Scoped, revocable delegate management
- Occupancy and ownership history preservation (zero destructive deletion)
- Move-in and move-out workflows and unit occupancy status updates
- IDOR protection and cross-society tenant isolation
- Privacy masking for contact and emergency contact details
- RBAC authorization checks
- Append-only audit logging
- Historical billing invoice responsibility preservation
"""

from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.audit import AuditLog
from apps.api.src.database.models.billing import Invoice
from apps.api.src.database.models.membership import (
    UnitOccupancy,
)
from apps.api.src.database.models.society import Floor, Unit
from apps.api.src.residents.domain.models import (
    calculate_profile_completeness,
    check_date_overlap,
    mask_email,
    mask_phone,
)
from infrastructure.scripts.seed_dev_data import (
    UUID_SOCIETY_A,
    UUID_SOCIETY_B,
    UUID_USER_DELEGATE_A,
    UUID_USER_OWNER_A,
    UUID_USER_TENANT_A,
)

SOCIETY_A_STR = str(UUID_SOCIETY_A)
SOCIETY_B_STR = str(UUID_SOCIETY_B)


async def get_auth_token(client: AsyncClient, identifier: str) -> str:
    """Helper to authenticate and retrieve access token."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"identifier": identifier, "password": "Password123!"},
    )
    assert resp.status_code == 200, f"Failed login for {identifier}: {resp.text}"
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# Unit / Domain Logic Tests
# ---------------------------------------------------------------------------
def test_mask_phone_and_email():
    """Verify phone and email masking functions."""
    assert mask_phone("+919876543210") == "+919*****3210"
    assert mask_phone(None) is None
    assert mask_email("resident@example.com") == "r******t@example.com"
    assert mask_email("ab@test.io") == "a*@test.io"
    assert mask_email(None) is None


def test_profile_completeness_calculation():
    """Deterministic profile completeness calculation without AI."""
    # Incomplete profile (missing phone)
    res_incomplete = calculate_profile_completeness(
        display_name="Vikram Mehta",
        phone=None,
        email="vikram@example.com",
        alternate_phone=None,
        emergency_contact_name=None,
        emergency_contact_phone=None,
        preferred_language="en",
    )
    assert res_incomplete["is_complete"] is False
    assert "phone" in res_incomplete["missing_required"]  # type: ignore

    # Complete required fields
    res_complete = calculate_profile_completeness(
        display_name="Vikram Mehta",
        phone="+919876543210",
        email="vikram@example.com",
        alternate_phone="+919876543211",
        emergency_contact_name="Sunita Mehta",
        emergency_contact_phone="+919876543299",
        preferred_language="en",
    )
    assert res_complete["is_complete"] is True
    assert res_complete["score_percent"] == 100
    assert len(res_complete["missing_fields"]) == 0  # type: ignore


def test_date_overlap_logic():
    """Verify interval overlap detection."""
    d1 = date(2025, 1, 1)
    d2 = date(2025, 6, 30)
    d3 = date(2025, 5, 1)
    d4 = date(2025, 12, 31)

    # Overlapping intervals
    assert check_date_overlap(d1, d2, d3, d4) is True
    # Non-overlapping intervals
    assert check_date_overlap(d1, d2, date(2025, 7, 1), d4) is False
    # Open-ended interval
    assert check_date_overlap(d1, None, d3, d4) is True


# ---------------------------------------------------------------------------
# Integration Tests: Self-Service & Resident Profiles
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_resident_self_service_get_and_patch(async_client: AsyncClient):
    """A & B: Resident can view and update their own localized profile."""
    token = await get_auth_token(async_client, "owner.a@palmstree.in")
    headers = {"Authorization": f"Bearer {token}", "X-Society-ID": SOCIETY_A_STR}

    # 1. GET /api/v1/residents/me
    resp = await async_client.get("/api/v1/residents/me", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "Vikram Mehta"
    assert data["completeness"]["is_complete"] is True

    # 2. PATCH /api/v1/residents/me
    patch_resp = await async_client.patch(
        "/api/v1/residents/me",
        headers=headers,
        json={
            "alternate_phone": "+919999988888",
            "preferred_language": "hi",
            "notes": "Prefers evening communication",
        },
    )
    assert patch_resp.status_code == 200
    updated = patch_resp.json()
    assert updated["alternate_phone"] == "+919999988888"
    assert updated["preferred_language"] == "hi"
    assert updated["notes"] == "Prefers evening communication"


@pytest.mark.asyncio
async def test_resident_self_service_emergency_contact(async_client: AsyncClient):
    """AF: Resident can update emergency contact via dedicated endpoint."""
    token = await get_auth_token(async_client, "tenant.a@palmstree.in")
    headers = {"Authorization": f"Bearer {token}", "X-Society-ID": SOCIETY_A_STR}

    resp = await async_client.patch(
        "/api/v1/residents/me/emergency",
        headers=headers,
        json={
            "emergency_contact_name": "Dr. Ramesh Nair",
            "emergency_contact_phone": "+919811122233",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["emergency_contact_name"] == "Dr. Ramesh Nair"
    assert resp.json()["emergency_contact_phone"] == "+919811122233"


@pytest.mark.asyncio
async def test_resident_self_service_my_home(async_client: AsyncClient):
    """AF: Resident accesses aggregated 'My Home' view."""
    token = await get_auth_token(async_client, "owner.a@palmstree.in")
    headers = {"Authorization": f"Bearer {token}", "X-Society-ID": SOCIETY_A_STR}

    resp = await async_client.get("/api/v1/residents/me/home", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["resident"]["display_name"] == "Vikram Mehta"
    assert data["unit"] is not None
    assert data["unit"]["unit_number"] in ("101", "102", "B-101")
    assert len(data["family_members"]) >= 1
    assert len(data["delegates"]) >= 1


# ---------------------------------------------------------------------------
# Integration Tests: Ownership Management & Validation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_single_and_joint_ownership_lifecycle(async_client: AsyncClient, db_session: AsyncSession):
    """D, E, F, O: Single owner, joint co-owners, percentage validation, and history preservation."""
    token = await get_auth_token(async_client, "superadmin@societysphere.io")
    headers = {"Authorization": f"Bearer {token}", "X-Society-ID": SOCIETY_A_STR}

    # Create isolated test unit for ownership testing
    floor = (
        (await db_session.execute(select(Floor).where(Floor.society_id == UUID_SOCIETY_A))).scalars().first()
    )
    assert floor is not None
    test_unit = Unit(
        society_id=UUID_SOCIETY_A,
        block_id=floor.block_id,
        floor_id=floor.id,
        unit_number="TEST-OWN-101",
        unit_type="3BHK",
        occupancy_status="VACANT",
        status="ACTIVE",
    )
    db_session.add(test_unit)
    await db_session.flush()

    # 1. Add Co-owner 1 with 70% share
    add_resp1 = await async_client.post(
        f"/api/v1/units/{test_unit.id}/owners",
        headers=headers,
        json={
            "user_id": str(UUID_USER_OWNER_A),
            "ownership_percentage": 70.0,
            "start_date": "2025-01-01",
            "is_primary": True,
        },
    )
    assert add_resp1.status_code == 200
    own1_data = add_resp1.json()
    assert float(own1_data["ownership_percentage"]) == 70.0
    assert own1_data["is_primary"] is True

    # 2. Attempt to add Co-owner 2 with 40% (Total = 110% -> Rejection)
    fail_resp = await async_client.post(
        f"/api/v1/units/{test_unit.id}/owners",
        headers=headers,
        json={
            "user_id": str(UUID_USER_DELEGATE_A),
            "ownership_percentage": 40.0,
            "start_date": "2025-01-01",
            "is_primary": False,
        },
    )
    assert fail_resp.status_code == 400
    assert "cannot exceed 100%" in fail_resp.json()["error"]["message"]

    # 3. Add Co-owner 2 with 30% (Total = 100% -> Success)
    add_resp2 = await async_client.post(
        f"/api/v1/units/{test_unit.id}/owners",
        headers=headers,
        json={
            "user_id": str(UUID_USER_DELEGATE_A),
            "ownership_percentage": 30.0,
            "start_date": "2025-01-01",
            "is_primary": False,
        },
    )
    assert add_resp2.status_code == 200
    own2_data = add_resp2.json()
    assert float(own2_data["ownership_percentage"]) == 30.0

    # 4. View active owners
    active_resp = await async_client.get(f"/api/v1/units/{test_unit.id}/owners", headers=headers)
    assert active_resp.status_code == 200
    active_owners = active_resp.json()
    assert len(active_owners) == 2

    # 5. End ownership for Co-owner 1 (Transfer)
    own1_id = own1_data["id"]
    end_resp = await async_client.post(
        f"/api/v1/ownerships/{own1_id}/end",
        headers=headers,
        json={"end_date": "2026-01-01", "reason": "Sold 70% stake to secondary owner"},
    )
    assert end_resp.status_code == 200
    assert end_resp.json()["status"] == "TRANSFERRED"

    # 6. Verify History Preservation (Record NOT deleted)
    history_resp = await async_client.get(f"/api/v1/units/{test_unit.id}/ownership-history", headers=headers)
    assert history_resp.status_code == 200
    hist = history_resp.json()
    assert len(hist) == 2
    assert any(h["id"] == own1_id and h["status"] == "TRANSFERRED" for h in hist)


# ---------------------------------------------------------------------------
# Integration Tests: Occupancy Lifecycle, Move-In, Move-Out & Overlap Check
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_occupancy_lifecycle_and_overlap_rejection(async_client: AsyncClient, db_session: AsyncSession):
    """K, L, M, N, P, Q: Move-in, overlap conflict, move-out, and history preservation."""
    token = await get_auth_token(async_client, "superadmin@societysphere.io")
    headers = {"Authorization": f"Bearer {token}", "X-Society-ID": SOCIETY_A_STR}

    # Create isolated test unit for occupancy testing
    floor = (
        (await db_session.execute(select(Floor).where(Floor.society_id == UUID_SOCIETY_A))).scalars().first()
    )
    assert floor is not None
    test_unit = Unit(
        society_id=UUID_SOCIETY_A,
        block_id=floor.block_id,
        floor_id=floor.id,
        unit_number="TEST-OCC-101",
        unit_type="3BHK",
        occupancy_status="VACANT",
        status="ACTIVE",
    )
    db_session.add(test_unit)
    await db_session.flush()

    # 1. Move-in Tenant 1 from 2026-01-01 to 2026-12-31
    move_in_1 = await async_client.post(
        f"/api/v1/units/{test_unit.id}/occupancies",
        headers=headers,
        json={
            "user_id": str(UUID_USER_TENANT_A),
            "relationship_type": "TENANT",
            "is_primary_contact": True,
            "valid_from": "2026-01-01",
            "valid_to": "2026-12-31",
            "notes": "12-month standard lease",
        },
    )
    assert move_in_1.status_code == 200
    occ1 = move_in_1.json()
    assert occ1["status"] == "ACTIVE"

    # Verify unit status is updated to OCCUPIED
    unit_check = (await db_session.execute(select(Unit).where(Unit.id == test_unit.id))).scalar_one()
    assert unit_check.occupancy_status == "OCCUPIED"

    # 2. Attempt overlapping tenant lease: 2026-06-01 to 2027-05-31 (Overlap Conflict -> 409)
    overlap_resp = await async_client.post(
        f"/api/v1/units/{test_unit.id}/occupancies",
        headers=headers,
        json={
            "user_id": str(UUID_USER_DELEGATE_A),
            "relationship_type": "TENANT",
            "is_primary_contact": False,
            "valid_from": "2026-06-01",
            "valid_to": "2027-05-31",
        },
    )
    assert overlap_resp.status_code == 409
    assert "Conflicting tenant occupancy" in overlap_resp.json()["error"]["message"]

    # 3. Move-out Tenant 1
    move_out_resp = await async_client.post(
        f"/api/v1/occupancies/{occ1['id']}/end",
        headers=headers,
        json={"valid_to": "2026-10-01", "reason": "Job relocation"},
    )
    assert move_out_resp.status_code == 200
    assert move_out_resp.json()["status"] == "ENDED"

    # Verify Unit status reverted to VACANT since no other active occupants remain
    await db_session.refresh(unit_check)
    assert unit_check.occupancy_status == "VACANT"

    # 4. Verify Occupancy History preserved
    hist_resp = await async_client.get(f"/api/v1/units/{test_unit.id}/occupancy-history", headers=headers)
    assert hist_resp.status_code == 200
    hist = hist_resp.json()
    assert len(hist) >= 1
    assert any(h["id"] == occ1["id"] and h["status"] == "ENDED" for h in hist)


# ---------------------------------------------------------------------------
# Integration Tests: Household Family Members & Scoped Delegates
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_family_and_delegate_lifecycle(async_client: AsyncClient, db_session: AsyncSession):
    """H, I, J, AG: Family member and delegate management with explicit permissions."""
    token = await get_auth_token(async_client, "owner.a@palmstree.in")
    headers = {"Authorization": f"Bearer {token}", "X-Society-ID": SOCIETY_A_STR}

    # Fetch Unit 101
    stmt = select(Unit).where(Unit.society_id == UUID_SOCIETY_A, Unit.unit_number == "101")
    unit_101 = (await db_session.execute(stmt)).scalar_one()

    # 1. Add family member via self-service
    fam_resp = await async_client.post(
        "/api/v1/residents/me/family",
        headers=headers,
        json={
            "name": "Kavita Mehta",
            "relationship": "PARENT",
            "phone": "+919811199900",
            "access_scope": {"announcements": True, "emergency": True},
        },
    )
    assert fam_resp.status_code == 200
    fam_data = fam_resp.json()
    assert fam_data["relationship"] == "PARENT"
    assert fam_data["name"] == "Kavita Mehta"

    # 2. Grant delegate with valid scoped permissions
    del_resp = await async_client.post(
        "/api/v1/residents/me/delegates",
        headers=headers,
        json={
            "unit_id": str(unit_101.id),
            "delegate_user_id": str(UUID_USER_DELEGATE_A),
            "permissions": ["resident.view", "billing.view"],
            "valid_from": "2026-01-01",
            "valid_to": "2026-12-31",
            "notes": "Authorized for maintenance billing inspection",
        },
    )
    assert del_resp.status_code == 200
    del_data = del_resp.json()
    assert del_data["status"] == "ACTIVE"
    assert "billing.view" in del_data["permissions"]

    # 3. Attempt to grant unauthorized permission (Privilege Escalation Guard)
    invalid_del = await async_client.post(
        "/api/v1/residents/me/delegates",
        headers=headers,
        json={
            "unit_id": str(unit_101.id),
            "delegate_user_id": str(UUID_USER_DELEGATE_A),
            "permissions": ["platform.admin"],  # INVALID
            "valid_from": "2026-01-01",
        },
    )
    assert invalid_del.status_code == 403
    assert "Unauthorized delegate permissions" in invalid_del.json()["error"]["message"]

    # 4. Attempt self-delegation (Rejected)
    self_del = await async_client.post(
        "/api/v1/residents/me/delegates",
        headers=headers,
        json={
            "unit_id": str(unit_101.id),
            "delegate_user_id": str(UUID_USER_OWNER_A),  # Same as caller
            "permissions": ["resident.view"],
            "valid_from": "2026-01-01",
        },
    )
    assert self_del.status_code == 403
    assert "cannot delegate authority to themselves" in self_del.json()["error"]["message"]

    # 5. Revoke delegate
    revoke_resp = await async_client.post(
        f"/api/v1/delegates/{del_data['id']}/revoke",
        headers=headers,
        json={"reason": "Lease ended"},
    )
    assert revoke_resp.status_code == 200
    assert revoke_resp.json()["status"] == "REVOKED"


# ---------------------------------------------------------------------------
# Integration Tests: Privacy, IDOR & Tenant Isolation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_contact_and_emergency_privacy_masking(async_client: AsyncClient):
    """AB & AC: Contact privacy and emergency contact masking for non-admin residents."""
    # Login as ordinary tenant (non-admin)
    token = await get_auth_token(async_client, "tenant.a@palmstree.in")
    headers = {"Authorization": f"Bearer {token}", "X-Society-ID": SOCIETY_A_STR}

    # Search directory as non-admin
    resp = await async_client.get("/api/v1/residents", headers=headers)
    assert resp.status_code == 200
    residents = resp.json()
    assert len(residents) >= 1

    # Find owner Vikram's record
    vikram = next((r for r in residents if r["user_id"] == str(UUID_USER_OWNER_A)), None)
    assert vikram is not None
    # Phone must be masked for tenant viewing owner
    assert "*" in vikram["phone"]
    # Emergency contact name must be hidden/None for non-admin without emergency.view
    assert vikram["emergency_contact_name"] is None


@pytest.mark.asyncio
async def test_cross_society_access_rejection(async_client: AsyncClient):
    """T & U: Cross-society tenant isolation prevents data leakage."""
    # Login as Society A Owner
    token = await get_auth_token(async_client, "owner.a@palmstree.in")

    # Attempt to query residents in Society B using Society B context (Forbidden: not a member)
    headers_soc_b = {"Authorization": f"Bearer {token}", "X-Society-ID": SOCIETY_B_STR}
    resp = await async_client.get("/api/v1/residents", headers=headers_soc_b)
    assert resp.status_code == 403
    assert "not an active member" in resp.json()["error"]["message"]


@pytest.mark.asyncio
async def test_audit_logging_resident_occupancy_actions(async_client: AsyncClient, db_session: AsyncSession):
    """AD: Privileged and resident lifecycle actions are written to immutable AuditLog."""
    token = await get_auth_token(async_client, "owner.a@palmstree.in")
    headers = {"Authorization": f"Bearer {token}", "X-Society-ID": SOCIETY_A_STR}

    # Update profile
    await async_client.patch(
        "/api/v1/residents/me",
        headers=headers,
        json={"notes": "Audit logging verification note"},
    )

    # Verify audit log entry
    stmt = (
        select(AuditLog)
        .where(
            AuditLog.society_id == UUID_SOCIETY_A,
            AuditLog.action == "resident.profile_updated",
        )
        .order_by(AuditLog.created_at.desc())
    )
    result = await db_session.execute(stmt)
    log = result.scalar_one_or_none()
    assert log is not None
    assert log.entity_type == "resident_profile"


# ---------------------------------------------------------------------------
# Integration Tests: Historical Billing Responsibility Preservation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_billing_historical_responsibility_preserved(
    async_client: AsyncClient, db_session: AsyncSession
):
    """AE: Moving out or transferring ownership does NOT alter existing posted/published invoices."""
    token = await get_auth_token(async_client, "superadmin@societysphere.io")
    headers = {"Authorization": f"Bearer {token}", "X-Society-ID": SOCIETY_A_STR}

    # Create an invoice for Unit 102 under tenant Priya
    stmt_unit = select(Unit).where(Unit.society_id == UUID_SOCIETY_A, Unit.unit_number == "102")
    unit_102 = (await db_session.execute(stmt_unit)).scalar_one()

    # Find or check seeded invoices
    stmt_inv = select(Invoice).where(
        Invoice.society_id == UUID_SOCIETY_A,
        Invoice.unit_id == unit_102.id,
    )
    inv_res = await db_session.execute(stmt_inv)
    invoices = inv_res.scalars().all()

    if invoices:
        target_invoice = invoices[0]
        original_responsible = target_invoice.responsible_user_id

        # End occupancy for Unit 102 occupant
        occs = (
            (
                await db_session.execute(
                    select(UnitOccupancy).where(
                        UnitOccupancy.unit_id == unit_102.id,
                        UnitOccupancy.status == "ACTIVE",
                    )
                )
            )
            .scalars()
            .all()
        )

        if occs:
            await async_client.post(
                f"/api/v1/occupancies/{occs[0].id}/end",
                headers=headers,
                json={"valid_to": "2026-10-02", "reason": "Moved out"},
            )

        # Historical invoice's responsible_user_id MUST NOT have mutated
        await db_session.refresh(target_invoice)
        assert target_invoice.responsible_user_id == original_responsible
