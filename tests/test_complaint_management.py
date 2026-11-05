"""Comprehensive Test Suite for Phase 10: Complaints & Helpdesk Management Foundation.

Covers:
1. Category & Subcategory Management (CRUD, activation)
2. SLA Policy Configuration (Response, Resolution, Escalation targets)
3. Complaint Creation & Auto-Generated Human-Readable Complaint Numbering (CMP-YYYY-XXXXXX)
4. Explicit State Machine Transitions (OPEN -> ACKNOWLEDGED -> ASSIGNED -> IN_PROGRESS -> RESOLVED -> CLOSED)
5. Reopening Flow (RESOLVED/CLOSED -> REOPENED)
6. Cancellation Flow (OPEN -> CANCELLED)
7. Public Comments & Internal Staff Notes (RBAC Visibility Filtering)
8. Attachment Upload & Soft Archival
9. Priority Management & SLA Due-Date Calculation
10. Escalation Logging and SLA tracking
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.scripts.seed_dev_data import (
    UUID_SOCIETY_A,
    UUID_SOCIETY_B,
    UUID_SUPER_ADMIN,
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
# 1. Category & Subcategory Management
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_category_and_subcategory_lifecycle(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    token = await get_token(async_client, "owner.a@palmstree.in")
    headers = {"Authorization": f"Bearer {token}", "x-society-id": SOCIETY_A_STR}

    # Create Category
    cat_payload = {
        "name": "HVAC & Air Conditioning",
        "code": "HVAC",
        "description": "Air conditioning unit and ventilation complaints",
        "display_order": 5,
    }
    cat_resp = await async_client.post("/api/v1/complaint-categories", json=cat_payload, headers=headers)
    assert cat_resp.status_code == 201
    cat_data = cat_resp.json()
    cat_id = cat_data["id"]
    assert cat_data["code"] == "HVAC"

    # Create Subcategory
    sub_payload = {
        "category_id": cat_id,
        "name": "AC Gas Leakage",
        "code": "AC_GAS_LEAK",
        "description": "Refrigerant gas leak or cooling failure",
        "display_order": 1,
    }
    sub_resp = await async_client.post(
        "/api/v1/complaint-categories/subcategories",
        json=sub_payload,
        headers=headers,
    )
    assert sub_resp.status_code == 201
    sub_data = sub_resp.json()
    assert sub_data["code"] == "AC_GAS_LEAK"

    # List Categories with Subcategories
    list_resp = await async_client.get("/api/v1/complaint-categories", headers=headers)
    assert list_resp.status_code == 200
    categories = list_resp.json()
    hvac_cat = next((c for c in categories if c["code"] == "HVAC"), None)
    assert hvac_cat is not None
    assert len(hvac_cat["subcategories"]) >= 1


# ---------------------------------------------------------------------------
# 2. SLA Policy Configuration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sla_policy_configuration(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    token = await get_token(async_client, "owner.a@palmstree.in")
    headers = {"Authorization": f"Bearer {token}", "x-society-id": SOCIETY_A_STR}

    # List SLA Policies
    list_resp = await async_client.get("/api/v1/complaint-sla-policies", headers=headers)
    assert list_resp.status_code == 200
    policies = list_resp.json()
    assert len(policies) >= 1

    # Upsert SLA Policy for HIGH priority
    upsert_payload = {
        "priority": "HIGH",
        "acknowledgement_target_hours": 3,
        "resolution_target_hours": 10,
        "is_active": True,
    }
    up_resp = await async_client.post("/api/v1/complaint-sla-policies", json=upsert_payload, headers=headers)
    assert up_resp.status_code in (200, 201)
    high_policy = up_resp.json()
    assert high_policy["acknowledgement_target_hours"] == 3
    assert high_policy["resolution_target_hours"] == 10


# ---------------------------------------------------------------------------
# 3. Complaint Creation & Complaint Numbering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complaint_creation_and_numbering(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    token = await get_token(async_client, "owner.a@palmstree.in")
    headers = {"Authorization": f"Bearer {token}", "x-society-id": SOCIETY_A_STR}

    # Fetch Categories
    cat_resp = await async_client.get("/api/v1/complaint-categories", headers=headers)
    categories = cat_resp.json()
    cat_plumbing = next(c for c in categories if c["code"] == "PLUMBING")
    sub_pipe = cat_plumbing["subcategories"][0]

    payload = {
        "category_id": cat_plumbing["id"],
        "subcategory_id": sub_pipe["id"],
        "title": "Kitchen Sink Drain Clogged",
        "description": "Water backing up into the kitchen sink from main drain pipe.",
        "priority": "MEDIUM",
        "source": "WEB",
    }

    resp = await async_client.post("/api/v1/complaints", json=payload, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["complaint_number"].startswith("CMP-")
    assert data["status"] == "OPEN"
    assert data["priority"] == "MEDIUM"
    assert data["ack_due_at"] is not None
    assert data["due_at"] is not None


# ---------------------------------------------------------------------------
# 4. Explicit State Machine & Lifecycle Transitions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complaint_lifecycle_state_machine(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await get_token(async_client, "owner.a@palmstree.in")
    owner_token = await get_token(async_client, "owner.a@palmstree.in")

    admin_headers = {"Authorization": f"Bearer {admin_token}", "x-society-id": SOCIETY_A_STR}
    owner_headers = {"Authorization": f"Bearer {owner_token}", "x-society-id": SOCIETY_A_STR}

    # 1. Create Complaint as Resident
    cat_resp = await async_client.get("/api/v1/complaint-categories", headers=owner_headers)
    cat_plumbing = cat_resp.json()[0]

    create_payload = {
        "category_id": cat_plumbing["id"],
        "title": "Corridor Light Fixture Broken",
        "description": "Light flickering and buzzing near unit 101",
        "priority": "LOW",
    }
    c_resp = await async_client.post("/api/v1/complaints", json=create_payload, headers=owner_headers)
    assert c_resp.status_code == 201
    comp_id = c_resp.json()["id"]

    # 2. Acknowledge as Admin
    ack_resp = await async_client.post(
        f"/api/v1/complaints/{comp_id}/status",
        json={"status": "ACKNOWLEDGED", "reason": "Acknowledged by helpdesk team"},
        headers=admin_headers,
    )
    assert ack_resp.status_code == 200
    assert ack_resp.json()["status"] == "ACKNOWLEDGED"

    # 3. Assign to Staff
    assign_resp = await async_client.post(
        f"/api/v1/complaints/{comp_id}/assign",
        json={"assigned_to_user_id": str(UUID_SUPER_ADMIN), "notes": "Assigned to electrician lead"},
        headers=admin_headers,
    )
    assert assign_resp.status_code in (200, 201)
    comp_get = await async_client.get(f"/api/v1/complaints/{comp_id}", headers=admin_headers)
    assert comp_get.json()["status"] == "ASSIGNED"

    # 4. Transition to IN_PROGRESS
    prog_resp = await async_client.post(
        f"/api/v1/complaints/{comp_id}/status",
        json={"status": "IN_PROGRESS", "reason": "Work started on site"},
        headers=admin_headers,
    )
    assert prog_resp.status_code == 200
    assert prog_resp.json()["status"] == "IN_PROGRESS"

    # 5. Resolve Complaint
    res_resp = await async_client.post(
        f"/api/v1/complaints/{comp_id}/resolve",
        json={
            "resolution_summary": "Replaced damaged choke valve and LED tube fixture.",
            "resolution_code": "HARDWARE_REPLACEMENT",
        },
        headers=admin_headers,
    )
    assert res_resp.status_code == 200
    assert res_resp.json()["status"] == "RESOLVED"

    # 6. Close Complaint
    close_resp = await async_client.post(
        f"/api/v1/complaints/{comp_id}/status",
        json={"status": "CLOSED", "reason": "Confirmed by resident"},
        headers=admin_headers,
    )
    assert close_resp.status_code == 200
    assert close_resp.json()["status"] == "CLOSED"


# ---------------------------------------------------------------------------
# 5. Reopening & Cancellation Flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complaint_reopen_and_cancel(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await get_token(async_client, "owner.a@palmstree.in")
    owner_token = await get_token(async_client, "owner.a@palmstree.in")

    admin_headers = {"Authorization": f"Bearer {admin_token}", "x-society-id": SOCIETY_A_STR}
    owner_headers = {"Authorization": f"Bearer {owner_token}", "x-society-id": SOCIETY_A_STR}

    cat_resp = await async_client.get("/api/v1/complaint-categories", headers=owner_headers)
    cat_id = cat_resp.json()[0]["id"]

    # Test Cancellation
    c1 = await async_client.post(
        "/api/v1/complaints",
        json={
            "category_id": cat_id,
            "title": "Duplicated Complaint Test",
            "description": "Accidental duplicate",
        },
        headers=owner_headers,
    )
    c1_id = c1.json()["id"]

    cancel_resp = await async_client.post(
        f"/api/v1/complaints/{c1_id}/status",
        json={"status": "CANCELLED", "reason": "Created by mistake"},
        headers=owner_headers,
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "CANCELLED"

    # Test Reopening
    c2 = await async_client.post(
        "/api/v1/complaints",
        json={
            "category_id": cat_id,
            "title": "Water Pressure Low",
            "description": "Low pressure in master tap",
        },
        headers=owner_headers,
    )
    c2_id = c2.json()["id"]

    # Admin resolves
    await async_client.post(
        f"/api/v1/complaints/{c2_id}/resolve",
        json={
            "resolution_summary": "Cleaned tap aerator filter.",
            "resolution_code": "CLEANING",
        },
        headers=admin_headers,
    )

    # Resident reopens
    reopen_resp = await async_client.post(
        f"/api/v1/complaints/{c2_id}/status",
        json={"status": "REOPENED", "reason": "Pressure dropped again after 10 mins"},
        headers=owner_headers,
    )
    assert reopen_resp.status_code == 200
    assert reopen_resp.json()["status"] == "REOPENED"


# ---------------------------------------------------------------------------
# 6. Comments & Internal Notes (Public vs Internal Visibility)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complaint_comments_and_internal_notes(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await get_token(async_client, "owner.a@palmstree.in")
    tenant_token = await get_token(async_client, "tenant.a@palmstree.in")

    admin_headers = {"Authorization": f"Bearer {admin_token}", "x-society-id": SOCIETY_A_STR}
    tenant_headers = {"Authorization": f"Bearer {tenant_token}", "x-society-id": SOCIETY_A_STR}

    cat_resp = await async_client.get("/api/v1/complaint-categories", headers=tenant_headers)
    cat_id = cat_resp.json()[0]["id"]

    c = await async_client.post(
        "/api/v1/complaints",
        json={
            "category_id": cat_id,
            "title": "Comment test complaint",
            "description": "Testing comment filtering",
        },
        headers=tenant_headers,
    )
    cid = c.json()["id"]

    # Public comment by resident
    p_com = await async_client.post(
        f"/api/v1/complaints/{cid}/comments",
        json={"body": "Please hurry, water is leaking onto carpet.", "comment_type": "PUBLIC"},
        headers=tenant_headers,
    )
    assert p_com.status_code == 201
    assert p_com.json()["comment_type"] == "PUBLIC"

    # Internal note by admin
    i_com = await async_client.post(
        f"/api/v1/complaints/{cid}/comments",
        json={"body": "Vendor vendor-xyz requires PO approval before visiting.", "comment_type": "INTERNAL"},
        headers=admin_headers,
    )
    assert i_com.status_code == 201
    assert i_com.json()["comment_type"] == "INTERNAL"

    # Admin reads comments -> sees 2 comments (public + internal)
    admin_comments = await async_client.get(f"/api/v1/complaints/{cid}/comments", headers=admin_headers)
    assert admin_comments.status_code == 200
    assert len(admin_comments.json()) == 2

    # Resident reads comments -> sees ONLY 1 public comment
    resident_comments = await async_client.get(f"/api/v1/complaints/{cid}/comments", headers=tenant_headers)
    assert resident_comments.status_code == 200
    res_list = resident_comments.json()
    assert len(res_list) == 1
    assert res_list[0]["comment_type"] == "PUBLIC"


# ---------------------------------------------------------------------------
# 7. Attachment Soft Archival & Upload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complaint_attachments_and_soft_delete(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    owner_token = await get_token(async_client, "owner.a@palmstree.in")
    owner_headers = {"Authorization": f"Bearer {owner_token}", "x-society-id": SOCIETY_A_STR}

    cat_resp = await async_client.get("/api/v1/complaint-categories", headers=owner_headers)
    cat_id = cat_resp.json()[0]["id"]

    c = await async_client.post(
        "/api/v1/complaints",
        json={"category_id": cat_id, "title": "Photo attachment test", "description": "Testing attachments"},
        headers=owner_headers,
    )
    cid = c.json()["id"]

    # Upload attachment metadata
    att_payload = {
        "original_filename": "leakage_photo.jpg",
        "file_key": "complaints/society-a/leakage_photo.jpg",
        "file_size_bytes": 102400,
        "content_type": "image/jpeg",
        "attachment_type": "PHOTO",
    }
    att_resp = await async_client.post(
        f"/api/v1/complaints/{cid}/attachments", json=att_payload, headers=owner_headers
    )
    assert att_resp.status_code == 201
    att_data = att_resp.json()
    att_id = att_data["id"]

    # List attachments
    list_att = await async_client.get(f"/api/v1/complaints/{cid}/attachments", headers=owner_headers)
    assert list_att.status_code == 200
    assert len(list_att.json()) == 1

    # Soft Delete attachment
    del_resp = await async_client.delete(
        f"/api/v1/complaints/{cid}/attachments/{att_id}", headers=owner_headers
    )
    assert del_resp.status_code == 204

    # List again -> 0 active attachments
    list_att_after = await async_client.get(f"/api/v1/complaints/{cid}/attachments", headers=owner_headers)
    assert list_att_after.status_code == 200
    assert len(list_att_after.json()) == 0


# ---------------------------------------------------------------------------
# 8. Escalation & Priority Updates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complaint_escalation_and_priority(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await get_token(async_client, "owner.a@palmstree.in")
    admin_headers = {"Authorization": f"Bearer {admin_token}", "x-society-id": SOCIETY_A_STR}

    cat_resp = await async_client.get("/api/v1/complaint-categories", headers=admin_headers)
    cat_id = cat_resp.json()[0]["id"]

    c = await async_client.post(
        "/api/v1/complaints",
        json={"category_id": cat_id, "title": "Escalation test", "description": "Testing SLA escalation"},
        headers=admin_headers,
    )
    cid = c.json()["id"]

    # Update Priority to CRITICAL
    prio_resp = await async_client.patch(
        f"/api/v1/complaints/{cid}/priority",
        json={"priority": "CRITICAL"},
        headers=admin_headers,
    )
    assert prio_resp.status_code == 200
    assert prio_resp.json()["priority"] == "CRITICAL"

    # Escalate Complaint
    esc_resp = await async_client.post(
        f"/api/v1/complaints/{cid}/escalate",
        json={"escalation_reason": "SLA response breached", "target_user_id": str(UUID_SUPER_ADMIN)},
        headers=admin_headers,
    )
    assert esc_resp.status_code == 201
    assert esc_resp.json()["escalation_level"] == 1
