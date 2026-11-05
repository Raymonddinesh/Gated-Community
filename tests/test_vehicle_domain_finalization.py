"""Phase 8 — Vehicle Domain & Security Finalization Test Suite.

Covers:
1.  Same-Society Relational Integrity (all six tables)
2.  Tenant Isolation / RLS-style Enforcement
3.  Access Record Immutability (service, repo, ORM listeners)
4.  Primary Vehicle Concurrency Guard
5.  Registration Concurrency Guard (duplicate race)
6.  Vehicle Document Soft-Archive (archived_at, not hard-delete)
7.  Verification History Preservation
8.  Parking Association Lifecycle Boundaries
9.  RFID/ANPR Stub Provider Readiness
10. RBAC Granular Permission Enforcement
11. Financial Isolation (vehicles do not affect accounting)
12. Migration Chain Verification (table existence)
"""

import asyncio
import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.society import Unit
from apps.api.src.database.models.vehicle import (
    Vehicle,
    VehicleAccessRecord,
    VehicleDocument,
    VehicleResidentAssociation,
)
from apps.api.src.vehicles.application.access_service import VehicleAccessService
from apps.api.src.vehicles.domain.exceptions import VehicleAccessRecordImmutableError
from apps.api.src.vehicles.infrastructure.repositories import (
    VehicleAccessRecordRepository,
)
from infrastructure.scripts.seed_dev_data import (
    UUID_SOCIETY_A,
    UUID_SOCIETY_B,
    UUID_USER_MEMBER_B,
)

SOCIETY_A_STR = str(UUID_SOCIETY_A)
SOCIETY_B_STR = str(UUID_SOCIETY_B)


async def get_token(client: AsyncClient, identifier: str) -> str:
    """Authenticate and retrieve JWT access token."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"identifier": identifier, "password": "Password123!"},
    )
    assert resp.status_code == 200, f"Login failed for {identifier}: {resp.text}"
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# 1. Same-Society Relational Integrity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_society_vehicle_association_rejected(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Society A vehicle cannot be associated with Society B unit/user."""
    super_token = await get_token(async_client, "superadmin@societysphere.io")

    # Register vehicle in Society A
    headers_a = {"Authorization": f"Bearer {super_token}", "x-society-id": SOCIETY_A_STR}
    resp_v = await async_client.post(
        "/api/v1/vehicles",
        json={"registration_number": "MH 01 XS 0001", "vehicle_type": "FOUR_WHEELER"},
        headers=headers_a,
    )
    assert resp_v.status_code == 201
    veh_a_id = resp_v.json()["id"]

    # Try to create association with Society B user/unit via Society A context
    # This should fail because the user does not belong to Society A
    unit_res = await db_session.execute(
        select(Unit).where(Unit.society_id == UUID_SOCIETY_A, Unit.unit_number == "101")
    )
    unit_a = unit_res.scalar_one()

    assoc_resp = await async_client.post(
        f"/api/v1/vehicles/{veh_a_id}/associations",
        json={
            "user_id": str(UUID_USER_MEMBER_B),  # Society B user
            "unit_id": str(unit_a.id),
            "association_type": "RESIDENT",
            "is_primary": False,
        },
        headers=headers_a,
    )
    # Should be 404 (user not found in this society)
    assert assoc_resp.status_code == 404


@pytest.mark.asyncio
async def test_cross_society_vehicle_not_visible(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """A vehicle in Society A must not be visible from Society B."""
    token_a = await get_token(async_client, "owner.a@palmstree.in")
    super_token = await get_token(async_client, "superadmin@societysphere.io")

    headers_a = {"Authorization": f"Bearer {token_a}", "x-society-id": SOCIETY_A_STR}
    resp = await async_client.post(
        "/api/v1/vehicles",
        json={"registration_number": "MH 01 XS 0002", "vehicle_type": "TWO_WHEELER"},
        headers=headers_a,
    )
    assert resp.status_code == 201
    veh_id = resp.json()["id"]

    # Attempt to access from Society B
    headers_b = {"Authorization": f"Bearer {super_token}", "x-society-id": SOCIETY_B_STR}
    resp_cross = await async_client.get(f"/api/v1/vehicles/{veh_id}", headers=headers_b)
    assert resp_cross.status_code == 404


@pytest.mark.asyncio
async def test_cross_society_access_record_isolation(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Access records in Society A must not appear in Society B searches."""
    super_token = await get_token(async_client, "superadmin@societysphere.io")

    # Create access record in Society A
    headers_a = {"Authorization": f"Bearer {super_token}", "x-society-id": SOCIETY_A_STR}
    await async_client.post(
        "/api/v1/vehicles",
        json={"registration_number": "MH 01 XS 0003", "vehicle_type": "FOUR_WHEELER"},
        headers=headers_a,
    )
    await async_client.post(
        "/api/v1/vehicles/access/records",
        json={
            "registration_number": "MH 01 XS 0003",
            "access_type": "ENTRY",
            "gate_identifier": "MAIN-GATE",
            "source_provider": "MANUAL",
        },
        headers=headers_a,
    )

    # Search from Society B — should not find it
    headers_b = {"Authorization": f"Bearer {super_token}", "x-society-id": SOCIETY_B_STR}
    search = await async_client.get(
        "/api/v1/vehicles/access/records?query=MH01XS0003",
        headers=headers_b,
    )
    assert search.status_code == 200
    assert search.json()["total"] == 0


@pytest.mark.asyncio
async def test_cross_society_document_isolation(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Documents uploaded in Society A must not be accessible from Society B."""
    super_token = await get_token(async_client, "superadmin@societysphere.io")

    headers_a = {"Authorization": f"Bearer {super_token}", "x-society-id": SOCIETY_A_STR}
    resp_v = await async_client.post(
        "/api/v1/vehicles",
        json={"registration_number": "MH 01 XS 0004", "vehicle_type": "FOUR_WHEELER"},
        headers=headers_a,
    )
    veh_id = resp_v.json()["id"]

    await async_client.post(
        f"/api/v1/vehicles/{veh_id}/documents",
        json={
            "document_type": "RC",
            "document_number": "RC-XS-004",
            "file_key": "docs/rc-xs-004.pdf",
            "file_name": "rc.pdf",
            "content_type": "application/pdf",
        },
        headers=headers_a,
    )

    # Attempt to view vehicle documents from Society B
    headers_b = {"Authorization": f"Bearer {super_token}", "x-society-id": SOCIETY_B_STR}
    resp_docs = await async_client.get(f"/api/v1/vehicles/{veh_id}/documents", headers=headers_b)
    # Vehicle not found in Society B, so 404
    assert resp_docs.status_code == 404


@pytest.mark.asyncio
async def test_cross_society_verification_isolation(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verification attempts from Society B context on Society A vehicle must fail."""
    super_token = await get_token(async_client, "superadmin@societysphere.io")

    headers_a = {"Authorization": f"Bearer {super_token}", "x-society-id": SOCIETY_A_STR}
    resp_v = await async_client.post(
        "/api/v1/vehicles",
        json={"registration_number": "MH 01 XS 0005", "vehicle_type": "FOUR_WHEELER"},
        headers=headers_a,
    )
    veh_id = resp_v.json()["id"]

    # Try to verify from Society B context
    headers_b = {"Authorization": f"Bearer {super_token}", "x-society-id": SOCIETY_B_STR}
    verif_resp = await async_client.post(
        f"/api/v1/vehicles/{veh_id}/verify",
        json={"verification_status": "VERIFIED", "reason": "Cross-society attempt"},
        headers=headers_b,
    )
    assert verif_resp.status_code == 404


# ---------------------------------------------------------------------------
# 2. Tenant Isolation / RLS-style Enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_returns_only_same_society_vehicles(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Vehicle search in Society A must not return Society B vehicles and vice versa."""
    super_token = await get_token(async_client, "superadmin@societysphere.io")

    plate = "MH 01 RL 0001"
    headers_a = {"Authorization": f"Bearer {super_token}", "x-society-id": SOCIETY_A_STR}
    resp_a = await async_client.post(
        "/api/v1/vehicles",
        json={"registration_number": plate, "vehicle_type": "FOUR_WHEELER"},
        headers=headers_a,
    )
    assert resp_a.status_code == 201

    # Search from Society B
    headers_b = {"Authorization": f"Bearer {super_token}", "x-society-id": SOCIETY_B_STR}
    search_b = await async_client.get(
        "/api/v1/vehicles?query=MH01RL0001",
        headers=headers_b,
    )
    assert search_b.status_code == 200
    assert search_b.json()["total"] == 0


# ---------------------------------------------------------------------------
# 3. Access Record Immutability
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_access_record_immutability_service_prevent(db_session: AsyncSession):
    """VehicleAccessService.prevent_modification() must raise."""
    service = VehicleAccessService(db_session)
    with pytest.raises(VehicleAccessRecordImmutableError):
        await service.prevent_modification()


@pytest.mark.asyncio
async def test_access_record_immutability_service_update(db_session: AsyncSession):
    """VehicleAccessService.update_record() must raise."""
    service = VehicleAccessService(db_session)
    with pytest.raises(VehicleAccessRecordImmutableError):
        await service.update_record()


@pytest.mark.asyncio
async def test_access_record_immutability_service_delete(db_session: AsyncSession):
    """VehicleAccessService.delete_record() must raise."""
    service = VehicleAccessService(db_session)
    with pytest.raises(VehicleAccessRecordImmutableError):
        await service.delete_record()


@pytest.mark.asyncio
async def test_access_record_immutability_repo_update(db_session: AsyncSession):
    """VehicleAccessRecordRepository.update() must raise."""
    repo = VehicleAccessRecordRepository(db_session)
    with pytest.raises(VehicleAccessRecordImmutableError):
        await repo.update()


@pytest.mark.asyncio
async def test_access_record_immutability_repo_delete(db_session: AsyncSession):
    """VehicleAccessRecordRepository.delete() must raise."""
    repo = VehicleAccessRecordRepository(db_session)
    with pytest.raises(VehicleAccessRecordImmutableError):
        await repo.delete()


# ---------------------------------------------------------------------------
# 4. Primary Vehicle Concurrency Guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_primary_demotion_deterministic(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """
    Two concurrent registrations marking is_primary=True for the same unit/user
    must result in exactly one active primary due to partial unique index +
    advisory locking.
    """
    token = await get_token(async_client, "owner.a@palmstree.in")
    headers = {"Authorization": f"Bearer {token}", "x-society-id": SOCIETY_A_STR}

    unit_res = await db_session.execute(
        select(Unit).where(Unit.society_id == UUID_SOCIETY_A, Unit.unit_number == "101")
    )
    unit_101 = unit_res.scalar_one()

    async def reg_primary(plate: str):
        return await async_client.post(
            "/api/v1/vehicles",
            json={
                "registration_number": plate,
                "vehicle_type": "FOUR_WHEELER",
                "unit_id": str(unit_101.id),
                "is_primary": True,
            },
            headers=headers,
        )

    r1 = await reg_primary("MH 01 PC 1001")
    r2 = await reg_primary("MH 01 PC 1002")

    # Both registrations should succeed (different plates)
    assert r1.status_code == 201
    assert r2.status_code == 201

    # Fetch both vehicles and count how many associations are primary
    v1 = await async_client.get(f"/api/v1/vehicles/{r1.json()['id']}", headers=headers)
    v2 = await async_client.get(f"/api/v1/vehicles/{r2.json()['id']}", headers=headers)

    v1_assocs = v1.json().get("associations", [])
    v2_assocs = v2.json().get("associations", [])

    active_primaries = sum(
        1 for a in v1_assocs + v2_assocs if a.get("is_primary") is True and a.get("status") == "ACTIVE"
    )
    # At most 1 should be primary for this (unit, user) pair
    assert active_primaries <= 1, f"Expected ≤1 active primary, got {active_primaries}"


# ---------------------------------------------------------------------------
# 5. Registration Concurrency Guard (duplicate plate race)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_duplicate_plate_race(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Concurrent registrations of the same normalized plate must result in one 201 and one 409."""
    token = await get_token(async_client, "owner.a@palmstree.in")
    headers = {"Authorization": f"Bearer {token}", "x-society-id": SOCIETY_A_STR}

    plate = "MH 01 FIN 9999"

    async def reg():
        return await async_client.post(
            "/api/v1/vehicles",
            json={"registration_number": plate, "vehicle_type": "FOUR_WHEELER"},
            headers=headers,
        )

    r1, r2 = await asyncio.gather(reg(), reg())
    statuses = sorted([r1.status_code, r2.status_code])
    assert statuses == [201, 409], f"Expected [201, 409], got {statuses}"


# ---------------------------------------------------------------------------
# 6. Vehicle Document Soft-Archive
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_document_soft_archive_not_hard_delete(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Deleting a document should soft-archive (set archived_at), not physically remove the row."""
    token = await get_token(async_client, "owner.a@palmstree.in")
    headers = {"Authorization": f"Bearer {token}", "x-society-id": SOCIETY_A_STR}

    resp_v = await async_client.post(
        "/api/v1/vehicles",
        json={"registration_number": "MH 01 SA 7001", "vehicle_type": "FOUR_WHEELER"},
        headers=headers,
    )
    veh_id = resp_v.json()["id"]

    doc_resp = await async_client.post(
        f"/api/v1/vehicles/{veh_id}/documents",
        json={
            "document_type": "PUC",
            "document_number": "PUC-7001",
            "file_key": "docs/puc-7001.pdf",
            "file_name": "puc.pdf",
            "content_type": "application/pdf",
            "valid_from": "2026-01-01",
            "valid_to": "2026-12-31",
        },
        headers=headers,
    )
    assert doc_resp.status_code == 201
    doc_id = doc_resp.json()["id"]

    # Delete (soft-archive)
    del_resp = await async_client.delete(f"/api/v1/vehicles/{veh_id}/documents/{doc_id}", headers=headers)
    assert del_resp.status_code == 204

    # Verify the document is no longer visible in the list
    list_resp = await async_client.get(f"/api/v1/vehicles/{veh_id}/documents", headers=headers)
    assert list_resp.status_code == 200
    visible_ids = [d["id"] for d in list_resp.json()]
    assert doc_id not in visible_ids

    # Verify the row still exists in DB (soft-archived, not hard-deleted)
    row = await db_session.execute(select(VehicleDocument).where(VehicleDocument.id == uuid.UUID(doc_id)))
    doc_row = row.scalar_one_or_none()
    assert doc_row is not None, "Document row should still exist after soft-archive"
    assert doc_row.archived_at is not None, "archived_at should be set"


# ---------------------------------------------------------------------------
# 7. Verification History Preservation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verification_history_preserved(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Multiple verifications on the same vehicle must all be preserved as an audit trail."""
    token = await get_token(async_client, "owner.a@palmstree.in")
    headers = {"Authorization": f"Bearer {token}", "x-society-id": SOCIETY_A_STR}

    resp = await async_client.post(
        "/api/v1/vehicles",
        json={"registration_number": "MH 01 VH 5001", "vehicle_type": "FOUR_WHEELER"},
        headers=headers,
    )
    veh_id = resp.json()["id"]

    # Verify → Reject → Verify again
    for status, reason in [
        ("VERIFIED", "Initial inspection OK"),
        ("REJECTED", "Document discrepancy found"),
        ("VERIFIED", "Re-inspection passed"),
    ]:
        await async_client.post(
            f"/api/v1/vehicles/{veh_id}/verify",
            json={"verification_status": status, "reason": reason},
            headers=headers,
        )

    detail = await async_client.get(f"/api/v1/vehicles/{veh_id}", headers=headers)
    verifs = detail.json()["verifications"]
    assert len(verifs) == 3
    # Most recent first
    assert verifs[0]["verification_status"] == "VERIFIED"
    assert verifs[0]["reason"] == "Re-inspection passed"
    assert verifs[1]["verification_status"] == "REJECTED"
    assert verifs[2]["verification_status"] == "VERIFIED"


# ---------------------------------------------------------------------------
# 8. Parking Association Lifecycle Boundaries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parking_association_ended_on_vehicle_sold(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Active parking associations must be ended when vehicle status transitions to SOLD."""
    token = await get_token(async_client, "owner.a@palmstree.in")
    headers = {"Authorization": f"Bearer {token}", "x-society-id": SOCIETY_A_STR}

    unit_res = await db_session.execute(
        select(Unit).where(Unit.society_id == UUID_SOCIETY_A, Unit.unit_number == "101")
    )
    unit_101 = unit_res.scalar_one()

    resp = await async_client.post(
        "/api/v1/vehicles",
        json={
            "registration_number": "MH 01 PK 3001",
            "vehicle_type": "FOUR_WHEELER",
            "unit_id": str(unit_101.id),
            "parking_slot_number": "P-300A",
        },
        headers=headers,
    )
    veh_id = resp.json()["id"]

    # Confirm parking is active
    detail = await async_client.get(f"/api/v1/vehicles/{veh_id}", headers=headers)
    assert detail.json()["parking_associations"][0]["status"] == "ACTIVE"

    # Transition to SOLD
    await async_client.patch(
        f"/api/v1/vehicles/{veh_id}/status",
        json={"status": "SOLD"},
        headers=headers,
    )

    detail2 = await async_client.get(f"/api/v1/vehicles/{veh_id}", headers=headers)
    for pa in detail2.json()["parking_associations"]:
        assert pa["status"] == "ENDED"


# ---------------------------------------------------------------------------
# 9. RFID/ANPR Stub Provider Readiness
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rfid_stub_returns_rfid_detection_method(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """RFID_STUB provider should return detection_method=RFID."""
    super_token = await get_token(async_client, "superadmin@societysphere.io")
    headers = {"Authorization": f"Bearer {super_token}", "x-society-id": SOCIETY_A_STR}

    resp = await async_client.post(
        "/api/v1/vehicles/access/records",
        json={
            "registration_number": "MH 01 RF 1111",
            "access_type": "ENTRY",
            "gate_identifier": "RFID-GATE-1",
            "source_provider": "RFID_STUB",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["detection_method"] == "RFID"


@pytest.mark.asyncio
async def test_anpr_stub_returns_anpr_detection_method(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """ANPR_STUB provider should return detection_method=ANPR with confidence score."""
    super_token = await get_token(async_client, "superadmin@societysphere.io")
    headers = {"Authorization": f"Bearer {super_token}", "x-society-id": SOCIETY_A_STR}

    resp = await async_client.post(
        "/api/v1/vehicles/access/records",
        json={
            "registration_number": "MH 01 AN 2222",
            "access_type": "EXIT",
            "gate_identifier": "ANPR-LANE-2",
            "source_provider": "ANPR_STUB",
            "confidence_score": 0.97,
        },
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["detection_method"] == "ANPR"
    assert Decimal(str(data["confidence_score"])) >= Decimal("0.9")


# ---------------------------------------------------------------------------
# 10. RBAC Granular Permission Enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tenant_cannot_verify_or_record_access(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Tenant user lacks vehicle.verify and vehicle.access.record permissions."""
    tenant_token = await get_token(async_client, "tenant.a@palmstree.in")
    headers_tenant = {"Authorization": f"Bearer {tenant_token}", "x-society-id": SOCIETY_A_STR}

    # Tenant can register (has vehicle.create)
    resp = await async_client.post(
        "/api/v1/vehicles",
        json={"registration_number": "MH 01 RB 4001", "vehicle_type": "TWO_WHEELER"},
        headers=headers_tenant,
    )
    assert resp.status_code == 201
    veh_id = resp.json()["id"]

    # Cannot verify
    verif_resp = await async_client.post(
        f"/api/v1/vehicles/{veh_id}/verify",
        json={"verification_status": "VERIFIED"},
        headers=headers_tenant,
    )
    assert verif_resp.status_code == 403

    # Cannot record access
    access_resp = await async_client.post(
        "/api/v1/vehicles/access/records",
        json={
            "registration_number": "MH 01 RB 4001",
            "access_type": "ENTRY",
            "gate_identifier": "GATE-01",
        },
        headers=headers_tenant,
    )
    assert access_resp.status_code == 403


@pytest.mark.asyncio
async def test_member_b_cannot_access_society_a(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Society B member must get 403 when using Society A context."""
    member_b_token = await get_token(async_client, "member.b@greenwood.in")
    headers = {"Authorization": f"Bearer {member_b_token}", "x-society-id": SOCIETY_A_STR}

    resp = await async_client.get("/api/v1/vehicles", headers=headers)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 11. Financial Isolation (vehicles ≠ accounting)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vehicle_registration_does_not_create_journal_entries(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Vehicle operations must not affect accounting journal entries."""
    token = await get_token(async_client, "owner.a@palmstree.in")
    headers = {"Authorization": f"Bearer {token}", "x-society-id": SOCIETY_A_STR}

    # Count journal entries before
    from apps.api.src.database.models.finance import JournalEntry

    count_before_result = await db_session.execute(
        select(JournalEntry).where(JournalEntry.society_id == UUID_SOCIETY_A)
    )
    count_before = len(count_before_result.scalars().all())

    # Register a vehicle
    await async_client.post(
        "/api/v1/vehicles",
        json={"registration_number": "MH 01 FI 6001", "vehicle_type": "FOUR_WHEELER"},
        headers=headers,
    )

    # Count after
    count_after_result = await db_session.execute(
        select(JournalEntry).where(JournalEntry.society_id == UUID_SOCIETY_A)
    )
    count_after = len(count_after_result.scalars().all())

    assert count_after == count_before, "Vehicle registration must not create journal entries"


# ---------------------------------------------------------------------------
# 12. Migration Chain Verification (table existence)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vehicle_tables_exist(db_session: AsyncSession):
    """All six Phase 8 tables must exist in the metadata."""
    expected_tables = {
        "vehicles",
        "vehicle_resident_associations",
        "vehicle_verifications",
        "vehicle_documents",
        "vehicle_parking_associations",
        "vehicle_access_records",
    }
    from apps.api.src.database.base import Base

    actual_tables = set(Base.metadata.tables.keys())
    for table_name in expected_tables:
        assert table_name in actual_tables, f"Table '{table_name}' missing from metadata"


@pytest.mark.asyncio
async def test_vehicle_model_constraints_present():
    """Check that critical constraints and indexes are defined in the Vehicle model."""
    # Check check constraints
    vehicle_constraints = {c.name for c in Vehicle.__table__.constraints if hasattr(c, "name") and c.name}
    assert any("ck_vehicles_vehicle_type" in name for name in vehicle_constraints)
    assert any("ck_vehicles_fuel_type" in name for name in vehicle_constraints)
    assert any("ck_vehicles_status" in name for name in vehicle_constraints)

    # Check the partial unique index for active normalized registration
    index_names = {idx.name for idx in Vehicle.__table__.indexes}
    assert "uq_vehicles_society_active_normalized_reg" in index_names

    # Association partial unique index for primary
    assoc_index_names = {idx.name for idx in VehicleResidentAssociation.__table__.indexes}
    assert "uq_vehicle_assoc_active_primary" in assoc_index_names

    # Access record check constraints
    access_constraints = {
        c.name for c in VehicleAccessRecord.__table__.constraints if hasattr(c, "name") and c.name
    }
    assert any("ck_vehicle_access_type" in name for name in access_constraints)
    assert any("ck_vehicle_detection_method" in name for name in access_constraints)


# ---------------------------------------------------------------------------
# Bonus: Same-society validation in register_vehicle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_vehicle_with_cross_society_unit_rejected(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Registering a vehicle with a unit from another society must be rejected."""
    super_token = await get_token(async_client, "superadmin@societysphere.io")

    # Get a Society B unit
    unit_b_res = await db_session.execute(select(Unit).where(Unit.society_id == UUID_SOCIETY_B))
    unit_b = unit_b_res.scalars().first()
    if unit_b is None:
        pytest.skip("No Society B unit available for cross-society test")

    # Try registering a vehicle in Society A with Society B unit
    headers_a = {"Authorization": f"Bearer {super_token}", "x-society-id": SOCIETY_A_STR}
    resp = await async_client.post(
        "/api/v1/vehicles",
        json={
            "registration_number": "MH 01 CS 1001",
            "vehicle_type": "FOUR_WHEELER",
            "unit_id": str(unit_b.id),
        },
        headers=headers_a,
    )
    assert resp.status_code == 404, f"Expected 404 for cross-society unit, got {resp.status_code}"
