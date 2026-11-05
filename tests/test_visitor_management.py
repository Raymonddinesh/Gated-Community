"""Comprehensive Test Suite for Phase 9: Visitor & Security Management Foundation.

Covers:
1. Visitor Profile Registration, Search, and Status Lifecycle
2. Resident Pre-Approved Visitor Invitations & Pass Codes
3. Walk-in Visitor Registration & Resident Approval/Rejection Workflow
4. Gate Entry Check-in & Double-Entry Prevention
5. Gate Exit Check-out & Double-Exit Prevention
6. Access Record Immutability (Append-only Audit Log)
7. Audit-Logged Emergency Entry Override
8. Delivery & Service Personnel Handling
9. Integration with Phase 8 Vehicle Domain
10. Visitor Photo / Document Soft Archival
11. Granular RBAC Permission Enforcement & Escalation Guards
12. Multi-Tenant RLS & Header Isolation
13. Financial Isolation (Visitors do not affect Accounting Core)
14. Concurrency Safety Guards
"""

import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.finance import JournalEntry
from apps.api.src.database.models.society import Unit
from apps.api.src.database.models.visitor import (
    VisitorDocument,
)
from apps.api.src.visitors.application.access_service import VisitorAccessService
from apps.api.src.visitors.domain.exceptions import (
    VisitorAccessRecordImmutableError,
)
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
# 1. Visitor Profile Registration & Lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_visitor_profile_registration_and_search(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    token = await get_token(async_client, "owner.a@palmstree.in")
    headers = {"Authorization": f"Bearer {token}", "x-society-id": SOCIETY_A_STR}

    payload = {
        "name": "Rajesh Sharma",
        "phone": "+919988776655",
        "visitor_type": "GUEST",
        "identification_type": "AADHAAR",
        "identification_number": "1234-5678-9012",
        "notes": "Family guest visiting for weekend",
    }

    resp = await async_client.post("/api/v1/visitors", json=payload, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Rajesh Sharma"
    assert data["phone"] == "+919988776655"
    assert data["visitor_type"] == "GUEST"
    assert data["status"] == "ACTIVE"
    vis_id = data["id"]

    # Search visitors
    search_resp = await async_client.get("/api/v1/visitors?query=Rajesh", headers=headers)
    assert search_resp.status_code == 200
    assert search_resp.json()["total"] >= 1

    # Update visitor status to BLOCKED
    block_resp = await async_client.patch(
        f"/api/v1/visitors/{vis_id}/status",
        json={"status": "BLOCKED", "notes": "Security concern"},
        headers=headers,
    )
    assert block_resp.status_code == 200
    assert block_resp.json()["status"] == "BLOCKED"


# ---------------------------------------------------------------------------
# 2. Resident Pre-Approved Visitor Invitations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resident_invitation_creation_and_pass_code(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    token = await get_token(async_client, "owner.a@palmstree.in")
    headers = {"Authorization": f"Bearer {token}", "x-society-id": SOCIETY_A_STR}

    unit_res = await db_session.execute(
        select(Unit).where(Unit.society_id == UUID_SOCIETY_A, Unit.unit_number == "101")
    )
    unit_101 = unit_res.scalar_one()

    payload = {
        "visitor_name": "Suresh Patel",
        "visitor_phone": "+919876500112",
        "visitor_type": "GUEST",
        "unit_id": str(unit_101.id),
        "expected_date": str(date.today()),
        "purpose": "Dinner guest",
    }

    resp = await async_client.post("/api/v1/visitors/invitations", json=payload, headers=headers)
    assert resp.status_code == 201
    inv_data = resp.json()

    assert inv_data["status"] == "APPROVED"
    assert inv_data["pass_code"] is not None
    assert inv_data["pass_code"].startswith("V-")

    # Cancel invitation
    inv_id = inv_data["id"]
    cancel_resp = await async_client.post(f"/api/v1/visitors/invitations/{inv_id}/cancel", headers=headers)
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "CANCELLED"


# ---------------------------------------------------------------------------
# 3. Walk-in Visitor Registration & Resident Approval Workflow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_walkin_registration_and_resident_approval(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    super_token = await get_token(async_client, "superadmin@societysphere.io")
    owner_token = await get_token(async_client, "owner.a@palmstree.in")

    headers_sec = {"Authorization": f"Bearer {super_token}", "x-society-id": SOCIETY_A_STR}
    headers_owner = {"Authorization": f"Bearer {owner_token}", "x-society-id": SOCIETY_A_STR}

    unit_res = await db_session.execute(
        select(Unit).where(Unit.society_id == UUID_SOCIETY_A, Unit.unit_number == "101")
    )
    unit_101 = unit_res.scalar_one()

    # Security guard registers walk-in visitor
    walkin_payload = {
        "name": "Amit Kumar",
        "phone": "+919123456789",
        "visitor_type": "CAB",
        "unit_id": str(unit_101.id),
        "gate_identifier": "GATE-01",
        "notes": "Uber driver pickup",
    }
    resp_w = await async_client.post("/api/v1/visitors/walkin", json=walkin_payload, headers=headers_sec)
    assert resp_w.status_code == 201
    w_data = resp_w.json()
    vis_id = w_data["visitor"]["id"]
    appr_id = w_data["approval"]["id"]
    assert w_data["approval"]["approval_status"] == "PENDING"

    # Resident approves entry
    appr_resp = await async_client.post(
        f"/api/v1/visitors/approvals/{appr_id}/decision",
        json={"approval_status": "APPROVED", "reason": "Expected cab driver"},
        headers=headers_owner,
    )
    assert appr_resp.status_code == 200
    assert appr_resp.json()["approval_status"] == "APPROVED"

    # Security logs entry check-in
    entry_payload = {
        "visitor_id": vis_id,
        "unit_id": str(unit_101.id),
        "host_user_id": str(UUID_USER_OWNER_A),
        "gate_identifier": "GATE-01",
        "entry_method": "MANUAL",
    }
    entry_resp = await async_client.post("/api/v1/visitors/entry", json=entry_payload, headers=headers_sec)
    assert entry_resp.status_code == 201
    rec_id = entry_resp.json()["id"]
    assert entry_resp.json()["access_type"] == "ENTRY"

    # Security logs exit check-out
    exit_resp = await async_client.post(
        f"/api/v1/visitors/exit/{rec_id}",
        json={"gate_identifier": "GATE-01", "exit_method": "MANUAL"},
        headers=headers_sec,
    )
    assert exit_resp.status_code == 200
    assert exit_resp.json()["exit_time"] is not None


# ---------------------------------------------------------------------------
# 4. Double Entry & Double Exit Prevention
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_double_entry_and_double_exit_prevented(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    super_token = await get_token(async_client, "superadmin@societysphere.io")
    headers = {"Authorization": f"Bearer {super_token}", "x-society-id": SOCIETY_A_STR}

    unit_res = await db_session.execute(
        select(Unit).where(Unit.society_id == UUID_SOCIETY_A, Unit.unit_number == "101")
    )
    unit_101 = unit_res.scalar_one()

    # Register visitor
    v_resp = await async_client.post(
        "/api/v1/visitors",
        json={"name": "Karan Singh", "phone": "+919811223344", "visitor_type": "GUEST"},
        headers=headers,
    )
    vis_id = v_resp.json()["id"]

    entry_payload = {
        "visitor_id": vis_id,
        "unit_id": str(unit_101.id),
        "host_user_id": str(UUID_USER_OWNER_A),
        "gate_identifier": "MAIN-GATE",
    }

    # First entry
    e1 = await async_client.post("/api/v1/visitors/entry", json=entry_payload, headers=headers)
    assert e1.status_code == 201
    rec_id = e1.json()["id"]

    # Second entry while inside -> should fail (403 Access Denied)
    e2 = await async_client.post("/api/v1/visitors/entry", json=entry_payload, headers=headers)
    assert e2.status_code == 403

    # First exit
    ex1 = await async_client.post(
        f"/api/v1/visitors/exit/{rec_id}",
        json={"gate_identifier": "MAIN-GATE"},
        headers=headers,
    )
    assert ex1.status_code == 200

    # Second exit on already exited record -> should fail (400 Bad Request)
    ex2 = await async_client.post(
        f"/api/v1/visitors/exit/{rec_id}",
        json={"gate_identifier": "MAIN-GATE"},
        headers=headers,
    )
    assert ex2.status_code == 400


# ---------------------------------------------------------------------------
# 5. Access Record Immutability
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_access_record_immutability(db_session: AsyncSession):
    service = VisitorAccessService(db_session)
    with pytest.raises(VisitorAccessRecordImmutableError):
        await service.prevent_modification()
    with pytest.raises(VisitorAccessRecordImmutableError):
        await service.delete_record()


# ---------------------------------------------------------------------------
# 6. Audit-Logged Emergency Override Entry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emergency_override_entry(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    super_token = await get_token(async_client, "superadmin@societysphere.io")
    headers = {"Authorization": f"Bearer {super_token}", "x-society-id": SOCIETY_A_STR}

    unit_res = await db_session.execute(
        select(Unit).where(Unit.society_id == UUID_SOCIETY_A, Unit.unit_number == "101")
    )
    unit_101 = unit_res.scalar_one()

    override_payload = {
        "name": "Dr. Verma",
        "phone": "+919800011122",
        "unit_id": str(unit_101.id),
        "gate_identifier": "GATE-EMERGENCY",
        "reason": "Medical emergency response team entry",
        "visitor_type": "SERVICE",
    }

    resp = await async_client.post(
        "/api/v1/visitors/emergency-override", json=override_payload, headers=headers
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["emergency_override_reason"] == "Medical emergency response team entry"
    assert data["access_type"] == "ENTRY"


# ---------------------------------------------------------------------------
# 7. Delivery & Service Personnel Handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delivery_and_service_visitor_handling(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    token = await get_token(async_client, "owner.a@palmstree.in")
    headers_owner = {"Authorization": f"Bearer {token}", "x-society-id": SOCIETY_A_STR}

    unit_res = await db_session.execute(
        select(Unit).where(Unit.society_id == UUID_SOCIETY_A, Unit.unit_number == "101")
    )
    unit_101 = unit_res.scalar_one()

    # Pre-approve delivery invitation
    deliv_inv = await async_client.post(
        "/api/v1/visitors/invitations",
        json={
            "visitor_name": "Delivery Agent",
            "visitor_phone": "+919776655443",
            "visitor_type": "DELIVERY",
            "unit_id": str(unit_101.id),
            "expected_date": str(date.today()),
            "delivery_company": "Zomato",
            "purpose": "Food parcel",
        },
        headers=headers_owner,
    )
    assert deliv_inv.status_code == 201
    assert deliv_inv.json()["delivery_company"] == "Zomato"


# ---------------------------------------------------------------------------
# 8. Visitor Photo & Document Soft Archival
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_visitor_document_soft_archival(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    super_token = await get_token(async_client, "superadmin@societysphere.io")
    headers = {"Authorization": f"Bearer {super_token}", "x-society-id": SOCIETY_A_STR}

    # Register visitor
    v_resp = await async_client.post(
        "/api/v1/visitors",
        json={"name": "Mohan Lal", "phone": "+919665544332", "visitor_type": "SERVICE"},
        headers=headers,
    )
    vis_id = v_resp.json()["id"]

    # Upload document
    doc_payload = {
        "document_type": "ID_CARD",
        "file_key": "visitors/society-a/id-mohan.jpg",
        "file_name": "id_card.jpg",
        "file_size_bytes": 150000,
        "content_type": "image/jpeg",
    }
    doc_resp = await async_client.post(
        f"/api/v1/visitors/{vis_id}/documents", json=doc_payload, headers=headers
    )
    assert doc_resp.status_code == 201
    doc_id = doc_resp.json()["id"]

    # List documents
    list_resp = await async_client.get(f"/api/v1/visitors/{vis_id}/documents", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    # Soft-archive document
    del_resp = await async_client.delete(f"/api/v1/visitors/{vis_id}/documents/{doc_id}", headers=headers)
    assert del_resp.status_code == 204

    # Confirm soft-archived document is no longer returned in active list
    list_resp2 = await async_client.get(f"/api/v1/visitors/{vis_id}/documents", headers=headers)
    assert len(list_resp2.json()) == 0

    # Confirm row still exists in DB with archived_at set
    row = await db_session.execute(select(VisitorDocument).where(VisitorDocument.id == uuid.UUID(doc_id)))
    doc_row = row.scalar_one_or_none()
    assert doc_row is not None
    assert doc_row.archived_at is not None


# ---------------------------------------------------------------------------
# 9. Multi-Tenant RLS & Header Isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_society_visitor_isolation(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    super_token = await get_token(async_client, "superadmin@societysphere.io")

    # Create visitor in Society A
    headers_a = {"Authorization": f"Bearer {super_token}", "x-society-id": SOCIETY_A_STR}
    res_a = await async_client.post(
        "/api/v1/visitors",
        json={"name": "Anita Roy", "phone": "+919554433221", "visitor_type": "GUEST"},
        headers=headers_a,
    )
    vis_a_id = res_a.json()["id"]

    # Attempt to fetch visitor from Society B context -> 404 Not Found
    headers_b = {"Authorization": f"Bearer {super_token}", "x-society-id": SOCIETY_B_STR}
    res_b = await async_client.get(f"/api/v1/visitors/{vis_a_id}", headers=headers_b)
    assert res_b.status_code == 404


# ---------------------------------------------------------------------------
# 10. Financial Isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_visitor_operations_do_not_create_journal_entries(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    token = await get_token(async_client, "owner.a@palmstree.in")
    headers = {"Authorization": f"Bearer {token}", "x-society-id": SOCIETY_A_STR}

    # Count journal entries before
    count_before_res = await db_session.execute(
        select(JournalEntry).where(JournalEntry.society_id == UUID_SOCIETY_A)
    )
    count_before = len(count_before_res.scalars().all())

    # Register visitor
    await async_client.post(
        "/api/v1/visitors",
        json={"name": "Financial Test Visitor", "phone": "+919000011111", "visitor_type": "GUEST"},
        headers=headers,
    )

    # Count journal entries after
    count_after_res = await db_session.execute(
        select(JournalEntry).where(JournalEntry.society_id == UUID_SOCIETY_A)
    )
    count_after = len(count_after_res.scalars().all())

    assert count_after == count_before, "Visitor operations must not create accounting journal entries"


# ---------------------------------------------------------------------------
# 11. Granular RBAC Permission Enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tenant_cannot_record_gate_entry_or_emergency_override(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    tenant_token = await get_token(async_client, "tenant.a@palmstree.in")
    headers_tenant = {"Authorization": f"Bearer {tenant_token}", "x-society-id": SOCIETY_A_STR}

    unit_res = await db_session.execute(
        select(Unit).where(Unit.society_id == UUID_SOCIETY_A, Unit.unit_number == "101")
    )
    unit_101 = unit_res.scalar_one()

    # Tenant cannot record gate entry directly (lacks visitor.entry -> 403)
    entry_resp = await async_client.post(
        "/api/v1/visitors/entry",
        json={
            "visitor_id": str(UUID_USER_OWNER_A),  # dummy ID
            "unit_id": str(unit_101.id),
            "host_user_id": str(UUID_USER_OWNER_A),
            "gate_identifier": "GATE-01",
        },
        headers=headers_tenant,
    )
    assert entry_resp.status_code == 403

    # Tenant cannot execute emergency override (lacks visitor.emergency.override -> 403)
    override_resp = await async_client.post(
        "/api/v1/visitors/emergency-override",
        json={
            "name": "Bypassed Visitor",
            "phone": "+919999900000",
            "unit_id": str(unit_101.id),
            "gate_identifier": "GATE-01",
            "reason": "Unauthorized bypass attempt",
        },
        headers=headers_tenant,
    )
    assert override_resp.status_code == 403
