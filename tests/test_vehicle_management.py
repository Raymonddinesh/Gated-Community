"""Comprehensive Test Suite for Phase 8: Vehicle Management & Vehicle Access Foundation.

Covers:
1. Registration & Deterministic Registration Number Normalization
2. Duplicate Active Registration Prevention within Same Society
3. Cross-Tenant Registration Independence (Tenant Isolation)
4. Vehicle-Resident Association & Automatic Primary Demotion
5. Duplicate Active Association Prevention
6. Lifecycle Transitions (ACTIVE, INACTIVE, SOLD, SCRAPPED) & Association Cleanup
7. Vehicle Verification Lifecycle (PENDING, VERIFIED, REJECTED) & Audit History
8. Vehicle Document Metadata Management (RC, Insurance, PUC)
9. Gate Access Control & Hardware Provider Dispatch (MANUAL, RFID_STUB, ANPR_STUB)
10. Access Record Append-Only Immutability
11. Multi-Tenant RLS & Header Isolation
12. Granular RBAC Permission Enforcement
13. Resident Self-Service Endpoints (/vehicles/me and /residents/me/vehicles)
14. Concurrent Registration Race Condition Guard
"""

import asyncio
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.society import Unit
from apps.api.src.vehicles.application.access_service import VehicleAccessService
from apps.api.src.vehicles.domain.exceptions import VehicleAccessRecordImmutableError
from apps.api.src.vehicles.domain.normalization import normalize_registration_number
from infrastructure.scripts.seed_dev_data import (
    UUID_SOCIETY_A,
    UUID_SOCIETY_B,
    UUID_USER_OWNER_A,
)

SOCIETY_A_STR = str(UUID_SOCIETY_A)
SOCIETY_B_STR = str(UUID_SOCIETY_B)


async def get_token(client: AsyncClient, identifier: str) -> str:
    """Helper to authenticate and retrieve JWT access token."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"identifier": identifier, "password": "Password123!"},
    )
    assert resp.status_code == 200, f"Login failed for {identifier}: {resp.text}"
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# 1. Normalization Utility Tests
# ---------------------------------------------------------------------------


def test_registration_normalization():
    assert normalize_registration_number("mh-02 ab 1234") == "MH02AB1234"
    assert normalize_registration_number("TN 38 / CD-9988") == "TN38CD9988"
    assert normalize_registration_number("dl.1c.aa.1111") == "DL1CAA1111"
    assert normalize_registration_number("   ka--05  mm  0007   ") == "KA05MM0007"

    with pytest.raises(ValueError):
        normalize_registration_number("")
    with pytest.raises(ValueError):
        normalize_registration_number("ab")


# ---------------------------------------------------------------------------
# 2. Registration & Normalization via API
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vehicle_registration_and_normalization_api(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    token = await get_token(async_client, "owner.a@palmstree.in")
    headers = {"Authorization": f"Bearer {token}", "x-society-id": SOCIETY_A_STR}

    payload = {
        "registration_number": "mh-12 / qz.4567",
        "vehicle_type": "FOUR_WHEELER",
        "make": "Hyundai",
        "model": "Ioniq 5",
        "color": "Gravity Gold",
        "fuel_type": "ELECTRIC",
        "is_ev": True,
        "battery_capacity_kwh": 72.6,
        "charging_required": True,
        "notes": "Fast charging enabled",
    }

    resp = await async_client.post("/api/v1/vehicles", json=payload, headers=headers)
    assert resp.status_code == 201
    data = resp.json()

    assert data["registration_number"] == "MH-12 / QZ.4567"
    assert data["normalized_registration_number"] == "MH12QZ4567"
    assert data["is_ev"] is True
    assert data["fuel_type"] == "ELECTRIC"
    assert data["status"] == "ACTIVE"
    assert data["verification_status"] == "PENDING"


# ---------------------------------------------------------------------------
# 3. Duplicate Registration Rejection within Same Society
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_registration_same_society_rejected(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    token = await get_token(async_client, "owner.a@palmstree.in")
    headers = {"Authorization": f"Bearer {token}", "x-society-id": SOCIETY_A_STR}

    # First registration
    payload1 = {
        "registration_number": "MH 04 AB 9999",
        "vehicle_type": "FOUR_WHEELER",
    }
    resp1 = await async_client.post("/api/v1/vehicles", json=payload1, headers=headers)
    assert resp1.status_code == 201

    # Second registration with spaces/dashes variations matching same normalized string
    payload2 = {
        "registration_number": "mh-04-ab-9999",
        "vehicle_type": "FOUR_WHEELER",
    }
    resp2 = await async_client.post("/api/v1/vehicles", json=payload2, headers=headers)
    assert resp2.status_code == 409
    assert "already exists" in resp2.json()["error"]["message"]


# ---------------------------------------------------------------------------
# 4. Cross-Society Registration Independence (Tenant Isolation)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_same_plate_permitted_in_different_societies(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    super_token = await get_token(async_client, "superadmin@societysphere.io")

    # Register plate in Society A
    headers_a = {"Authorization": f"Bearer {super_token}", "x-society-id": SOCIETY_A_STR}
    resp_a = await async_client.post(
        "/api/v1/vehicles",
        json={"registration_number": "KA 05 MN 3322", "vehicle_type": "TWO_WHEELER"},
        headers=headers_a,
    )
    assert resp_a.status_code == 201

    # Register identical normalized plate in Society B
    headers_b = {"Authorization": f"Bearer {super_token}", "x-society-id": SOCIETY_B_STR}
    resp_b = await async_client.post(
        "/api/v1/vehicles",
        json={"registration_number": "ka-05-mn-3322", "vehicle_type": "TWO_WHEELER"},
        headers=headers_b,
    )
    assert resp_b.status_code == 201
    assert resp_b.json()["normalized_registration_number"] == "KA05MN3322"


# ---------------------------------------------------------------------------
# 5. Vehicle Association & Primary Demotion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vehicle_association_and_primary_demotion(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    token = await get_token(async_client, "owner.a@palmstree.in")
    headers = {"Authorization": f"Bearer {token}", "x-society-id": SOCIETY_A_STR}

    # Fetch Flat 101 unit ID
    unit_res = await db_session.execute(
        select(Unit).where(Unit.society_id == UUID_SOCIETY_A, Unit.unit_number == "101")
    )
    unit_101 = unit_res.scalar_one()

    # Register Vehicle 1 as Primary
    resp1 = await async_client.post(
        "/api/v1/vehicles",
        json={
            "registration_number": "MH 01 PA 1111",
            "vehicle_type": "FOUR_WHEELER",
            "unit_id": str(unit_101.id),
            "is_primary": True,
            "parking_slot_number": "P-101A",
        },
        headers=headers,
    )
    assert resp1.status_code == 201
    v1_id = resp1.json()["id"]

    # Verify Vehicle 1 is primary
    v1_get = await async_client.get(f"/api/v1/vehicles/{v1_id}", headers=headers)
    assert v1_get.json()["associations"][0]["is_primary"] is True

    # Register Vehicle 2 as Primary for same unit & user
    resp2 = await async_client.post(
        "/api/v1/vehicles",
        json={
            "registration_number": "MH 01 PA 2222",
            "vehicle_type": "TWO_WHEELER",
            "unit_id": str(unit_101.id),
            "is_primary": True,
            "parking_slot_number": "P-101B",
        },
        headers=headers,
    )
    assert resp2.status_code == 201
    v2_id = resp2.json()["id"]

    # Verify Vehicle 2 is primary, and Vehicle 1 has been automatically demoted
    v2_get = await async_client.get(f"/api/v1/vehicles/{v2_id}", headers=headers)
    assert v2_get.json()["associations"][0]["is_primary"] is True

    v1_check = await async_client.get(f"/api/v1/vehicles/{v1_id}", headers=headers)
    assert v1_check.json()["associations"][0]["is_primary"] is False


# ---------------------------------------------------------------------------
# 6. Duplicate Active Association Prevention
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_active_association_prevented(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    token = await get_token(async_client, "owner.a@palmstree.in")
    headers = {"Authorization": f"Bearer {token}", "x-society-id": SOCIETY_A_STR}

    unit_res = await db_session.execute(
        select(Unit).where(Unit.society_id == UUID_SOCIETY_A, Unit.unit_number == "101")
    )
    unit_101 = unit_res.scalar_one()

    # Create vehicle
    resp_v = await async_client.post(
        "/api/v1/vehicles",
        json={"registration_number": "MH 01 DA 3333", "vehicle_type": "FOUR_WHEELER"},
        headers=headers,
    )
    veh_id = resp_v.json()["id"]

    # Add association
    assoc_payload = {
        "user_id": str(UUID_USER_OWNER_A),
        "unit_id": str(unit_101.id),
        "association_type": "OWNER",
        "is_primary": False,
    }
    resp_a1 = await async_client.post(
        f"/api/v1/vehicles/{veh_id}/associations",
        json=assoc_payload,
        headers=headers,
    )
    assert resp_a1.status_code == 201

    # Attempt second identical active association
    resp_a2 = await async_client.post(
        f"/api/v1/vehicles/{veh_id}/associations",
        json=assoc_payload,
        headers=headers,
    )
    assert resp_a2.status_code == 409


# ---------------------------------------------------------------------------
# 7. Status Lifecycle & Association Cleanup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vehicle_lifecycle_and_association_cleanup(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    token = await get_token(async_client, "owner.a@palmstree.in")
    headers = {"Authorization": f"Bearer {token}", "x-society-id": SOCIETY_A_STR}

    unit_res = await db_session.execute(
        select(Unit).where(Unit.society_id == UUID_SOCIETY_A, Unit.unit_number == "101")
    )
    unit_101 = unit_res.scalar_one()

    resp_v = await async_client.post(
        "/api/v1/vehicles",
        json={
            "registration_number": "MH 01 LC 7777",
            "vehicle_type": "FOUR_WHEELER",
            "unit_id": str(unit_101.id),
            "parking_slot_number": "P-77",
        },
        headers=headers,
    )
    veh_id = resp_v.json()["id"]

    # Update specs
    patch_resp = await async_client.patch(
        f"/api/v1/vehicles/{veh_id}",
        json={"make": "Toyota", "model": "Fortuner", "color": "Super White"},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["make"] == "Toyota"

    # Transition status to SOLD
    status_resp = await async_client.patch(
        f"/api/v1/vehicles/{veh_id}/status",
        json={"status": "SOLD", "notes": "Sold to external party"},
        headers=headers,
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "SOLD"

    # Check that associations and parking were ended
    veh_detail = await async_client.get(f"/api/v1/vehicles/{veh_id}", headers=headers)
    v_data = veh_detail.json()
    assert v_data["associations"][0]["status"] == "ENDED"
    assert v_data["parking_associations"][0]["status"] == "ENDED"

    # Scrap vehicle
    await async_client.patch(
        f"/api/v1/vehicles/{veh_id}/status",
        json={"status": "SCRAPPED"},
        headers=headers,
    )

    # Attempt invalid transition from SCRAPPED back to ACTIVE
    invalid_resp = await async_client.patch(
        f"/api/v1/vehicles/{veh_id}/status",
        json={"status": "ACTIVE"},
        headers=headers,
    )
    assert invalid_resp.status_code == 400


# ---------------------------------------------------------------------------
# 8. Vehicle Verification Lifecycle & Audit Log
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vehicle_verification_workflow(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    token = await get_token(async_client, "owner.a@palmstree.in")
    headers = {"Authorization": f"Bearer {token}", "x-society-id": SOCIETY_A_STR}

    # Register vehicle (initial verification: PENDING)
    resp = await async_client.post(
        "/api/v1/vehicles",
        json={"registration_number": "MH 01 VR 8888", "vehicle_type": "FOUR_WHEELER"},
        headers=headers,
    )
    veh_id = resp.json()["id"]
    assert resp.json()["verification_status"] == "PENDING"

    # Verify vehicle as Admin
    verif_resp = await async_client.post(
        f"/api/v1/vehicles/{veh_id}/verify",
        json={
            "verification_status": "VERIFIED",
            "reason": "Physical inspection and RC verified",
            "supporting_document_ref": "RC-DOC-001",
        },
        headers=headers,
    )
    assert verif_resp.status_code == 200
    assert verif_resp.json()["verification_status"] == "VERIFIED"

    # Verify audit history
    veh_detail = await async_client.get(f"/api/v1/vehicles/{veh_id}", headers=headers)
    verifs = veh_detail.json()["verifications"]
    assert len(verifs) == 1
    assert verifs[0]["verification_status"] == "VERIFIED"
    assert verifs[0]["reason"] == "Physical inspection and RC verified"


# ---------------------------------------------------------------------------
# 9. Vehicle Documents Management
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vehicle_document_management(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    token = await get_token(async_client, "owner.a@palmstree.in")
    headers = {"Authorization": f"Bearer {token}", "x-society-id": SOCIETY_A_STR}

    resp = await async_client.post(
        "/api/v1/vehicles",
        json={"registration_number": "MH 01 DC 5555", "vehicle_type": "FOUR_WHEELER"},
        headers=headers,
    )
    veh_id = resp.json()["id"]

    # Upload document metadata
    doc_payload = {
        "document_type": "INSURANCE",
        "document_number": "POL-992211",
        "file_key": "society-a/vehicles/insurance-5555.pdf",
        "file_name": "insurance_policy.pdf",
        "file_size_bytes": 1048576,
        "content_type": "application/pdf",
        "valid_from": "2026-01-01",
        "valid_to": "2027-01-01",
    }
    doc_resp = await async_client.post(
        f"/api/v1/vehicles/{veh_id}/documents",
        json=doc_payload,
        headers=headers,
    )
    assert doc_resp.status_code == 201
    doc_id = doc_resp.json()["id"]

    # List documents
    docs_resp = await async_client.get(f"/api/v1/vehicles/{veh_id}/documents", headers=headers)
    assert docs_resp.status_code == 200
    assert len(docs_resp.json()) == 1
    assert docs_resp.json()[0]["document_type"] == "INSURANCE"

    # Delete document
    del_resp = await async_client.delete(f"/api/v1/vehicles/{veh_id}/documents/{doc_id}", headers=headers)
    assert del_resp.status_code == 204


# ---------------------------------------------------------------------------
# 10. Gate Access Logging & Hardware Provider Abstraction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gate_access_logging_and_providers(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    token = await get_token(async_client, "owner.a@palmstree.in")
    headers = {"Authorization": f"Bearer {token}", "x-society-id": SOCIETY_A_STR}

    # Register known vehicle
    await async_client.post(
        "/api/v1/vehicles",
        json={"registration_number": "MH 02 GT 1000", "vehicle_type": "FOUR_WHEELER"},
        headers=headers,
    )

    # 1. Manual Provider Entry
    access_manual = {
        "registration_number": "mh 02 gt 1000",
        "access_type": "ENTRY",
        "gate_identifier": "MAIN-GATE",
        "source_provider": "MANUAL",
        "notes": "Guard logged entry",
    }
    res_m = await async_client.post("/api/v1/vehicles/access/records", json=access_manual, headers=headers)
    assert res_m.status_code == 201
    data_m = res_m.json()
    assert data_m["normalized_registration_number_snapshot"] == "MH02GT1000"
    assert data_m["detection_method"] == "MANUAL"
    assert data_m["vehicle_id"] is not None  # Matched to registered vehicle

    # 2. RFID Stub Provider Entry
    access_rfid = {
        "registration_number": "MH 02 GT 1000",
        "access_type": "EXIT",
        "gate_identifier": "NORTH-BOOM-01",
        "source_provider": "RFID_STUB",
    }
    res_rfid = await async_client.post("/api/v1/vehicles/access/records", json=access_rfid, headers=headers)
    assert res_rfid.status_code == 201
    assert res_rfid.json()["detection_method"] == "RFID"

    # 3. ANPR Stub Provider Entry
    access_anpr = {
        "registration_number": "MH 02 GT 1000",
        "access_type": "ENTRY",
        "gate_identifier": "ANPR-LANE-1",
        "source_provider": "ANPR_STUB",
        "confidence_score": 0.985,
    }
    res_anpr = await async_client.post("/api/v1/vehicles/access/records", json=access_anpr, headers=headers)
    assert res_anpr.status_code == 201
    data_anpr = res_anpr.json()
    assert data_anpr["detection_method"] == "ANPR"
    assert Decimal(str(data_anpr["confidence_score"])) == Decimal("0.985")

    # 4. Search access records
    search_res = await async_client.get(
        "/api/v1/vehicles/access/records?query=MH02GT1000",
        headers=headers,
    )
    assert search_res.status_code == 200
    assert search_res.json()["total"] >= 3


# ---------------------------------------------------------------------------
# 11. Access Record Immutability
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_access_record_immutability(db_session: AsyncSession):
    service = VehicleAccessService(db_session)
    with pytest.raises(VehicleAccessRecordImmutableError):
        await service.prevent_modification()


# ---------------------------------------------------------------------------
# 12. Multi-Tenancy & Tenant Isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multi_tenant_isolation(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    token_a = await get_token(async_client, "owner.a@palmstree.in")
    super_token = await get_token(async_client, "superadmin@societysphere.io")

    # Create vehicle in Society A
    headers_a = {"Authorization": f"Bearer {token_a}", "x-society-id": SOCIETY_A_STR}
    res = await async_client.post(
        "/api/v1/vehicles",
        json={"registration_number": "MH 01 ISO 9999", "vehicle_type": "FOUR_WHEELER"},
        headers=headers_a,
    )
    veh_a_id = res.json()["id"]

    # Attempt to access this vehicle using Society B header
    headers_b = {"Authorization": f"Bearer {super_token}", "x-society-id": SOCIETY_B_STR}
    res_cross = await async_client.get(f"/api/v1/vehicles/{veh_a_id}", headers=headers_b)
    assert res_cross.status_code == 404


# ---------------------------------------------------------------------------
# 13. Resident Self-Service Endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resident_self_service_endpoints(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    token = await get_token(async_client, "owner.a@palmstree.in")
    headers = {"Authorization": f"Bearer {token}", "x-society-id": SOCIETY_A_STR}

    # /vehicles/me
    resp1 = await async_client.get("/api/v1/vehicles/me", headers=headers)
    assert resp1.status_code == 200
    assert isinstance(resp1.json(), list)

    # /residents/me/vehicles
    resp2 = await async_client.get("/api/v1/residents/me/vehicles", headers=headers)
    assert resp2.status_code == 200
    assert isinstance(resp2.json(), list)


# ---------------------------------------------------------------------------
# 14. Concurrency Safety for Plate Registration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_plate_registration_race(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    token = await get_token(async_client, "owner.a@palmstree.in")
    headers = {"Authorization": f"Bearer {token}", "x-society-id": SOCIETY_A_STR}

    plate = "MH 99 RACE 0001"

    async def register():
        return await async_client.post(
            "/api/v1/vehicles",
            json={"registration_number": plate, "vehicle_type": "FOUR_WHEELER"},
            headers=headers,
        )

    # Launch two concurrent registration attempts with identical plates
    res1, res2 = await asyncio.gather(register(), register())

    statuses = [res1.status_code, res2.status_code]
    assert 201 in statuses, f"Expected one 201, got {statuses}"
    assert 409 in statuses, f"Expected one 409, got {statuses}"


# ---------------------------------------------------------------------------
# 15. Granular RBAC Permission Enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vehicle_rbac_enforcement(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    # Tenant has vehicle.create, but lacks vehicle.verify and vehicle.access.record
    tenant_token = await get_token(async_client, "tenant.a@palmstree.in")
    headers_tenant = {"Authorization": f"Bearer {tenant_token}", "x-society-id": SOCIETY_A_STR}

    # 1. Tenant can register vehicle (vehicle.create)
    resp_reg = await async_client.post(
        "/api/v1/vehicles",
        json={"registration_number": "MH 03 RBAC 1111", "vehicle_type": "TWO_WHEELER"},
        headers=headers_tenant,
    )
    assert resp_reg.status_code == 201
    veh_id = resp_reg.json()["id"]

    # 2. Tenant cannot verify vehicle (lacks vehicle.verify -> 403)
    resp_verif = await async_client.post(
        f"/api/v1/vehicles/{veh_id}/verify",
        json={"verification_status": "VERIFIED"},
        headers=headers_tenant,
    )
    assert resp_verif.status_code == 403

    # 3. Tenant cannot record gate access (lacks vehicle.access.record -> 403)
    resp_gate = await async_client.post(
        "/api/v1/vehicles/access/records",
        json={
            "registration_number": "MH 03 RBAC 1111",
            "access_type": "ENTRY",
            "gate_identifier": "GATE-01",
        },
        headers=headers_tenant,
    )
    assert resp_gate.status_code == 403
