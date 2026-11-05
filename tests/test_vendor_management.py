"""Phase 13 — Vendor Management Functional & Integration Unit Tests."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.identity import User
from apps.api.src.vendor.application.category_service import VendorCategoryService
from apps.api.src.vendor.application.vendor_service import VendorService
from apps.api.src.vendor.domain.enums import VendorStatus, VendorType
from apps.api.src.vendor.domain.exceptions import (
    VendorInvalidStatusTransitionException,
)
from apps.api.src.vendor.domain.state_machine import validate_status_transition
from apps.api.src.vendor.schemas import (
    VendorCategoryCreate,
    VendorContactCreate,
    VendorProfileCreate,
    VendorServiceCreate,
    VendorStatusUpdate,
)


def test_vendor_status_state_machine_valid():
    validate_status_transition("ONBOARDING", "ACTIVE")
    validate_status_transition("ACTIVE", "SUSPENDED")
    validate_status_transition("SUSPENDED", "ACTIVE")
    validate_status_transition("ACTIVE", "BLACKLISTED")
    validate_status_transition("BLACKLISTED", "OFFBOARDED")


def test_vendor_status_state_machine_invalid():
    with pytest.raises(VendorInvalidStatusTransitionException):
        validate_status_transition("OFFBOARDED", "ACTIVE")

    with pytest.raises(VendorInvalidStatusTransitionException):
        validate_status_transition("ONBOARDING", "BLACKLISTED")


@pytest.mark.asyncio
async def test_vendor_category_service(seeded_session: AsyncSession):
    society_id = uuid.uuid4()
    service = VendorCategoryService(seeded_session)
    cat_create = VendorCategoryCreate(
        name="Electrical Maintenance",
        code="ELEC_MAINT",
        description="High voltage and DG set maintenance",
    )
    cat = await service.create_category(cat_create, society_id)

    assert cat.id is not None
    assert cat.name == "Electrical Maintenance"
    assert cat.code == "ELEC_MAINT"

    fetched = await service.get_category(cat.id, society_id)
    assert fetched.id == cat.id


@pytest.mark.asyncio
async def test_vendor_profile_lifecycle(seeded_session: AsyncSession):
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

    category_service = VendorCategoryService(session)
    cat = await category_service.create_category(
        VendorCategoryCreate(name="Elevator Services", code="LIFT_SVC"),
        society_id,
    )

    vendor_service = VendorService(session)
    create_dto = VendorProfileCreate(
        legal_name="Apex Elevator Systems Pvt Ltd",
        display_name="Apex Lifts",
        vendor_type=VendorType.COMPANY,
        primary_category_id=cat.id,
        contacts=[
            VendorContactCreate(
                name="Ramesh Kumar",
                phone="+91 98400 12345",
                is_primary=True,
            )
        ],
        services=[
            VendorServiceCreate(
                service_name="Elevator Quarterly AMC",
                category_id=cat.id,
            )
        ],
    )

    vendor = await vendor_service.create_vendor(create_dto, society_id, user.id)

    assert vendor.id is not None
    assert vendor.vendor_code.startswith("VND-")
    assert vendor.status == VendorStatus.ONBOARDING.value
    assert len(vendor.contacts) == 1
    assert len(vendor.services) == 1

    # Transition status: ONBOARDING -> ACTIVE
    updated_vendor = await vendor_service.update_status(
        vendor.id,
        VendorStatusUpdate(target_status=VendorStatus.ACTIVE, reason="Approved docs"),
        society_id,
        user.id,
    )
    assert updated_vendor.status == VendorStatus.ACTIVE.value
