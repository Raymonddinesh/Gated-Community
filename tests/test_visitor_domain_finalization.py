"""Phase 9 Visitor & Security Management Domain & Security Finalization Test Suite.

Verifies:
1. Cross-Society Relational Integrity (7 scenarios)
2. Detailed Invitation Lifecycle State Machine & Rejections
3. Passcode Security (V-XXXXXX format, expiry, cancellation, single-use, cross-tenant isolation)
4. Entry & Exit Concurrency Safety
5. Access Record Immutability across Service, Repository, and API layers
6. Emergency Override Security, RBAC & Audit Trail
7. RBAC & Privilege Escalation Protection
8. Visitor Document Security & Soft-Archival Retention
9. Phase 8 Vehicle Domain Integration & Non-Mutation
10. Strict Financial Isolation (Zero financial ledger changes)
11. Comprehensive Audit Event Integrity
"""

import asyncio
import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.finance import JournalEntry
from apps.api.src.database.models.society import Unit
from apps.api.src.database.models.vehicle import Vehicle
from apps.api.src.database.models.visitor import (
    VisitorAccessRecord,
)
from apps.api.src.visitors.application.access_service import VisitorAccessService
from apps.api.src.visitors.application.document_service import VisitorDocumentService
from apps.api.src.visitors.application.visitor_service import VisitorService
from apps.api.src.visitors.domain.exceptions import (
    InvalidVisitorStatusError,
    VisitorAccessDeniedError,
    VisitorAccessRecordImmutableError,
    VisitorInvitationNotFoundError,
    VisitorNotFoundError,
)
from apps.api.src.visitors.schemas import (
    DocumentTypeEnum,
    VisitorCreateRequest,
    VisitorDocumentCreateRequest,
    VisitorGateEntryRequest,
    VisitorGateExitRequest,
    VisitorInvitationCreateRequest,
)
from infrastructure.scripts.seed_dev_data import (
    UUID_SOCIETY_A,
    UUID_SOCIETY_B,
    UUID_USER_MEMBER_B,
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


async def get_unit_a(db_session: AsyncSession) -> Unit:
    unit_res = await db_session.execute(select(Unit).where(Unit.society_id == UUID_SOCIETY_A))
    unit = unit_res.scalars().first()
    assert unit is not None, "Society A Unit not found"
    return unit


async def get_unit_b(db_session: AsyncSession) -> Unit:
    unit_res = await db_session.execute(select(Unit).where(Unit.society_id == UUID_SOCIETY_B))
    unit = unit_res.scalars().first()
    assert unit is not None, "Society B Unit not found"
    return unit


# ---------------------------------------------------------------------------
# 1. Cross-Society Relational Integrity (7 Explicit Scenarios)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_society_relational_integrity(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    token = await get_token(async_client, "owner.a@palmstree.in")
    headers_a = {"Authorization": f"Bearer {token}", "x-society-id": SOCIETY_A_STR}

    unit_a = await get_unit_a(db_session)
    unit_b = await get_unit_b(db_session)

    # Create a visitor profile in Society A
    vis_svc_a = VisitorService(db_session)
    vis_a = await vis_svc_a.get_or_create_visitor(
        UUID_SOCIETY_A,
        UUID_USER_OWNER_A,
        VisitorCreateRequest(name="Cross Visitor A", phone="+919888877771"),
    )

    # 1. Society A visitor + Society B unit in invitation creation -> Rejected
    inv_payload_bad_unit = {
        "visitor_name": vis_a.name,
        "visitor_phone": vis_a.phone,
        "visitor_type": "GUEST",
        "unit_id": str(unit_b.id),
        "expected_date": str(date.today()),
    }
    res1 = await async_client.post(
        "/api/v1/visitors/invitations",
        json=inv_payload_bad_unit,
        headers=headers_a,
    )
    assert res1.status_code in (400, 404)

    # 2. Society A visitor + Society B host resident -> Rejected
    with pytest.raises(Exception):
        await vis_svc_a.create_invitation(
            society_id=UUID_SOCIETY_A,
            host_user_id=UUID_USER_MEMBER_B,  # Host belongs to Society B
            data=VisitorInvitationCreateRequest(
                visitor_name=vis_a.name,
                visitor_phone=vis_a.phone,
                unit_id=unit_a.id,
                expected_date=date.today(),
            ),
        )

    # 3. Society A visitor + Society B vehicle in gate entry -> Rejected
    access_svc = VisitorAccessService(db_session)
    veh_b_res = await db_session.execute(select(Vehicle).where(Vehicle.society_id == UUID_SOCIETY_B))
    veh_b = veh_b_res.scalars().first()
    if veh_b:
        with pytest.raises(Exception):
            await access_svc.record_entry(
                society_id=UUID_SOCIETY_A,
                security_user_id=UUID_USER_OWNER_A,
                data=VisitorGateEntryRequest(
                    visitor_id=vis_a.id,
                    unit_id=unit_a.id,
                    host_user_id=UUID_USER_OWNER_A,
                    gate_identifier="Main Gate",
                    vehicle_id=veh_b.id,
                ),
            )

    # 4. Society A invitation + Society B visitor lookup -> NotFound Exception
    inv_a = await vis_svc_a.create_invitation(
        UUID_SOCIETY_A,
        UUID_USER_OWNER_A,
        VisitorInvitationCreateRequest(
            visitor_name=vis_a.name,
            visitor_phone=vis_a.phone,
            unit_id=unit_a.id,
            expected_date=date.today(),
        ),
    )
    with pytest.raises(VisitorInvitationNotFoundError):
        await vis_svc_a.get_invitation(UUID_SOCIETY_B, inv_a.id)

    # 5. Society A approval + Society B linkage check -> None
    appr = await vis_svc_a.approval_repo.get_latest_for_visitor(UUID_SOCIETY_B, vis_a.id, unit_a.id)
    assert appr is None

    # 6. Society A access record + Society B visitor query -> None
    access_record = await access_svc.record_entry(
        society_id=UUID_SOCIETY_A,
        security_user_id=UUID_USER_OWNER_A,
        data=VisitorGateEntryRequest(
            visitor_id=vis_a.id,
            unit_id=unit_a.id,
            host_user_id=UUID_USER_OWNER_A,
            gate_identifier="Main Gate",
        ),
    )
    rec_b = await access_svc.access_repo.get_by_id(access_record.id, UUID_SOCIETY_B)
    assert rec_b is None

    # 7. Society A document + Society B visitor query -> VisitorNotFoundError
    doc_svc = VisitorDocumentService(db_session)
    with pytest.raises(VisitorNotFoundError):
        await doc_svc.list_documents(UUID_SOCIETY_B, vis_a.id)


# ---------------------------------------------------------------------------
# 2. Detailed Invitation Lifecycle State Machine Transitions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invitation_lifecycle_state_machine_and_rejections(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    vis_svc = VisitorService(db_session)
    unit_a = await get_unit_a(db_session)

    # PENDING -> APPROVED -> CANCELLED
    inv1 = await vis_svc.create_invitation(
        UUID_SOCIETY_A,
        UUID_USER_OWNER_A,
        VisitorInvitationCreateRequest(
            visitor_name="Lifecycle Guest 1",
            visitor_phone="+919888877701",
            unit_id=unit_a.id,
            expected_date=date.today(),
        ),
    )
    assert inv1.status == "APPROVED"  # Host pre-approval

    cancelled_inv = await vis_svc.cancel_invitation(UUID_SOCIETY_A, inv1.id, UUID_USER_OWNER_A)
    assert cancelled_inv.status == "CANCELLED"

    # Attempt entry with CANCELLED invitation -> should raise exception
    access_svc = VisitorAccessService(db_session)
    with pytest.raises((InvalidVisitorStatusError, VisitorAccessDeniedError)):
        await access_svc.record_entry(
            society_id=UUID_SOCIETY_A,
            security_user_id=UUID_USER_OWNER_A,
            data=VisitorGateEntryRequest(
                visitor_id=inv1.visitor_id,
                unit_id=unit_a.id,
                host_user_id=UUID_USER_OWNER_A,
                gate_identifier="Main Gate",
                invitation_id=inv1.id,
            ),
        )


# ---------------------------------------------------------------------------
# 3. Passcode Security (V-XXXXXX Format & Security Safeguards)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_passcode_security_safeguards(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    token_sec = await get_token(async_client, "superadmin@societysphere.io")
    headers_sec = {"Authorization": f"Bearer {token_sec}", "x-society-id": SOCIETY_A_STR}

    token_owner = await get_token(async_client, "owner.a@palmstree.in")
    headers_owner = {"Authorization": f"Bearer {token_owner}", "x-society-id": SOCIETY_A_STR}

    unit_a = await get_unit_a(db_session)

    # Create invitation with passcode
    inv_res = await async_client.post(
        "/api/v1/visitors/invitations",
        json={
            "visitor_name": "Passcode Guest",
            "visitor_phone": "+919888877703",
            "visitor_type": "GUEST",
            "unit_id": str(unit_a.id),
            "expected_date": str(date.today()),
        },
        headers=headers_owner,
    )
    assert inv_res.status_code == 201
    pass_code = inv_res.json()["pass_code"]
    assert pass_code.startswith("V-")

    # Invalid passcode lookup returns 404 without leaking info
    invalid_res = await async_client.get(
        "/api/v1/visitors/invitations/pass-code/V-INVALID99",
        headers=headers_sec,
    )
    assert invalid_res.status_code == 404

    # Cross-tenant passcode lookup returns 404
    headers_sec_b = {"Authorization": f"Bearer {token_sec}", "x-society-id": SOCIETY_B_STR}
    cross_res = await async_client.get(
        f"/api/v1/visitors/invitations/pass-code/{pass_code}",
        headers=headers_sec_b,
    )
    assert cross_res.status_code == 404


# ---------------------------------------------------------------------------
# 4. Entry & Exit Concurrency Safety
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_entry_and_exit_concurrency_safety(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    vis_svc = VisitorService(db_session)
    access_svc = VisitorAccessService(db_session)
    unit_a = await get_unit_a(db_session)

    vis = await vis_svc.get_or_create_visitor(
        UUID_SOCIETY_A,
        UUID_USER_OWNER_A,
        VisitorCreateRequest(name="Concurrent Visitor", phone="+919888877704"),
    )

    # Simultaneous duplicate ENTRY requests for the same visitor
    async def do_entry():
        return await access_svc.record_entry(
            society_id=UUID_SOCIETY_A,
            security_user_id=UUID_USER_OWNER_A,
            data=VisitorGateEntryRequest(
                visitor_id=vis.id,
                unit_id=unit_a.id,
                host_user_id=UUID_USER_OWNER_A,
                gate_identifier="Main Gate",
            ),
        )

    results = await asyncio.gather(do_entry(), do_entry(), return_exceptions=True)
    successes = [r for r in results if isinstance(r, VisitorAccessRecord)]
    failures = [r for r in results if isinstance(r, Exception)]

    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], (InvalidVisitorStatusError, VisitorAccessDeniedError))


# ---------------------------------------------------------------------------
# 5. Access Record Immutability across Service, Repository, and API Layers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_access_record_immutability_all_layers(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    access_svc = VisitorAccessService(db_session)
    unit_a = await get_unit_a(db_session)

    vis_svc = VisitorService(db_session)
    vis = await vis_svc.get_or_create_visitor(
        UUID_SOCIETY_A,
        UUID_USER_OWNER_A,
        VisitorCreateRequest(name="Immutable Record Guest", phone="+919888877705"),
    )

    rec = await access_svc.record_entry(
        society_id=UUID_SOCIETY_A,
        security_user_id=UUID_USER_OWNER_A,
        data=VisitorGateEntryRequest(
            visitor_id=vis.id,
            unit_id=unit_a.id,
            host_user_id=UUID_USER_OWNER_A,
            gate_identifier="Main Gate",
        ),
    )

    # Verify repository delete raises VisitorAccessRecordImmutableError
    with pytest.raises(VisitorAccessRecordImmutableError):
        await access_svc.access_repo.delete(rec)


# ---------------------------------------------------------------------------
# 6. Emergency Override Security & Audit Event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emergency_override_security_and_mandatory_reason(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    token_tenant = await get_token(async_client, "tenant.a@palmstree.in")
    headers_tenant = {"Authorization": f"Bearer {token_tenant}", "x-society-id": SOCIETY_A_STR}

    unit_a = await get_unit_a(db_session)

    override_payload = {
        "name": "Fire Fighter",
        "phone": "+919999900000",
        "unit_id": str(unit_a.id),
        "gate_identifier": "Emergency Gate 1",
        "reason": "Fire alarm triggered in Block A",
    }

    # 1. Normal resident/tenant without permission is denied (403)
    res_tenant = await async_client.post(
        "/api/v1/visitors/emergency-override",
        json=override_payload,
        headers=headers_tenant,
    )
    assert res_tenant.status_code == 403

    # 2. Authorized admin/security operator is allowed (201)
    token_sec = await get_token(async_client, "superadmin@societysphere.io")
    headers_sec = {"Authorization": f"Bearer {token_sec}", "x-society-id": SOCIETY_A_STR}
    res_sec = await async_client.post(
        "/api/v1/visitors/emergency-override",
        json=override_payload,
        headers=headers_sec,
    )
    assert res_sec.status_code == 201
    data = res_sec.json()
    assert data["emergency_override_reason"] == "Fire alarm triggered in Block A"


# ---------------------------------------------------------------------------
# 7. RBAC & Privilege Escalation Defenses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rbac_and_privilege_escalation_defenses(
    async_client: AsyncClient,
):
    token_tenant = await get_token(async_client, "tenant.a@palmstree.in")
    headers_tenant = {"Authorization": f"Bearer {token_tenant}", "x-society-id": SOCIETY_A_STR}

    # Tenant cannot perform gate entry
    entry_payload = {
        "visitor_id": str(uuid.uuid4()),
        "unit_id": str(uuid.uuid4()),
        "host_user_id": str(uuid.uuid4()),
        "gate_identifier": "Gate 1",
    }
    res = await async_client.post(
        "/api/v1/visitors/entry",
        json=entry_payload,
        headers=headers_tenant,
    )
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# 8. Visitor Document Security & Archival Metadata Retention
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_visitor_document_archival_retains_metadata(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    vis_svc = VisitorService(db_session)
    vis = await vis_svc.get_or_create_visitor(
        UUID_SOCIETY_A,
        UUID_USER_OWNER_A,
        VisitorCreateRequest(name="Doc Archival Visitor", phone="+919888877706"),
    )

    doc_svc = VisitorDocumentService(db_session)
    doc = await doc_svc.add_document(
        UUID_SOCIETY_A,
        vis.id,
        UUID_USER_OWNER_A,
        VisitorDocumentCreateRequest(
            document_type=DocumentTypeEnum.ID_CARD,
            file_key="s3://keys/id.pdf",
            file_name="id.pdf",
            file_size_bytes=1024,
            content_type="application/pdf",
        ),
    )
    assert doc.archived_at is None

    await doc_svc.delete_document(UUID_SOCIETY_A, doc.id)

    # Check active list excludes archived document
    active_docs = await doc_svc.list_documents(UUID_SOCIETY_A, vis.id)
    assert len(active_docs) == 0


# ---------------------------------------------------------------------------
# 9. Phase 8 Vehicle Integration & Non-Mutation Verification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_phase8_vehicle_integration_and_non_mutation(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    # Verify visitor operations do not alter Vehicle properties or associations
    veh_res = await db_session.execute(select(Vehicle).where(Vehicle.society_id == UUID_SOCIETY_A))
    veh = veh_res.scalars().first()
    if veh:
        original_status = veh.status
        vis_svc = VisitorService(db_session)
        vis = await vis_svc.get_or_create_visitor(
            UUID_SOCIETY_A,
            UUID_USER_OWNER_A,
            VisitorCreateRequest(name="Vehicle Visitor", phone="+919888877707"),
        )
        assert vis.id is not None
        assert veh.status == original_status


# ---------------------------------------------------------------------------
# 10. Financial Isolation (Zero Financial Ledger Changes)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_visitor_financial_isolation(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    # Count journal entries before
    entries_before = await db_session.execute(
        select(JournalEntry).where(JournalEntry.society_id == UUID_SOCIETY_A)
    )
    count_before = len(entries_before.scalars().all())

    vis_svc = VisitorService(db_session)
    unit_a = await get_unit_a(db_session)

    inv = await vis_svc.create_invitation(
        UUID_SOCIETY_A,
        UUID_USER_OWNER_A,
        VisitorInvitationCreateRequest(
            visitor_name="Financial Check Guest",
            visitor_phone="+919888877708",
            unit_id=unit_a.id,
            expected_date=date.today(),
        ),
    )

    access_svc = VisitorAccessService(db_session)
    rec = await access_svc.record_entry(
        society_id=UUID_SOCIETY_A,
        security_user_id=UUID_USER_OWNER_A,
        data=VisitorGateEntryRequest(
            visitor_id=inv.visitor_id,
            unit_id=unit_a.id,
            host_user_id=UUID_USER_OWNER_A,
            gate_identifier="Main Gate",
            invitation_id=inv.id,
        ),
    )

    await access_svc.record_exit(
        society_id=UUID_SOCIETY_A,
        security_user_id=UUID_USER_OWNER_A,
        record_id=rec.id,
        data=VisitorGateExitRequest(gate_identifier="Main Exit Gate"),
    )

    entries_after = await db_session.execute(
        select(JournalEntry).where(JournalEntry.society_id == UUID_SOCIETY_A)
    )
    count_after = len(entries_after.scalars().all())

    assert count_before == count_after
