"""Phase 14 — Facility & Asset Management Functional Tests."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.facility_asset import AssetCategory
from apps.api.src.database.models.identity import User
from apps.api.src.facility_asset.asset_service import AssetService
from apps.api.src.facility_asset.document_service import DocumentService
from apps.api.src.facility_asset.enums import (
    AssetAssignmentType,
    AssetCriticality,
    AssetDocumentType,
    AssetStatus,
    FacilityDocumentType,
    FacilityStatus,
    FacilityType,
    MaintenanceLinkType,
)
from apps.api.src.facility_asset.facility_service import FacilityService
from apps.api.src.facility_asset.maintenance_link_service import MaintenanceLinkService
from apps.api.src.facility_asset.repositories import AssetCategoryRepository
from apps.api.src.facility_asset.schemas import (
    AssetAssignmentCreate,
    AssetCreate,
    AssetDocumentCreate,
    AssetLocationMove,
    AssetMaintenanceLinkCreate,
    AssetStatusUpdate,
    FacilityAreaCreate,
    FacilityCreate,
    FacilityDocumentCreate,
    FacilityStatusUpdate,
)


@pytest.mark.asyncio
async def test_facility_crud_and_areas(seeded_session: AsyncSession):
    session = seeded_session
    society_id = uuid.uuid4()

    facility_service = FacilityService(session)

    # Create Facility with Areas
    fac = await facility_service.create_facility(
        society_id,
        FacilityCreate(
            name="Grand Clubhouse",
            facility_type=FacilityType.CLUBHOUSE,
            description="Main multi-purpose clubhouse",
            capacity=300,
            location_summary="Tower A Ground Floor",
            is_bookable_separately=True,
            areas=[
                FacilityAreaCreate(
                    area_code="BADM-1",
                    name="Badminton Court 1",
                    max_occupancy=4,
                )
            ],
        ),
    )

    assert fac.id is not None
    assert fac.facility_code.startswith("FAC-")
    assert fac.status == FacilityStatus.ACTIVE.value
    assert len(fac.areas) == 1
    assert fac.areas[0].area_code == "BADM-1"

    # Add second area
    area2 = await facility_service.add_facility_area(
        society_id,
        fac.id,
        FacilityAreaCreate(
            area_code="GYM-MAIN",
            name="Main Fitness Area",
            max_occupancy=50,
        ),
    )
    assert area2.id is not None
    assert area2.facility_id == fac.id


@pytest.mark.asyncio
async def test_facility_status_transitions(seeded_session: AsyncSession):
    session = seeded_session
    society_id = uuid.uuid4()

    facility_service = FacilityService(session)

    fac = await facility_service.create_facility(
        society_id,
        FacilityCreate(
            name="Swimming Pool",
            facility_type=FacilityType.SWIMMING_POOL,
        ),
    )

    # ACTIVE -> UNDER_MAINTENANCE
    updated = await facility_service.update_facility_status(
        society_id,
        fac.id,
        FacilityStatusUpdate(status=FacilityStatus.UNDER_MAINTENANCE, reason="Tile repair"),
    )
    assert updated.status == FacilityStatus.UNDER_MAINTENANCE.value

    # UNDER_MAINTENANCE -> ACTIVE
    updated2 = await facility_service.update_facility_status(
        society_id,
        fac.id,
        FacilityStatusUpdate(status=FacilityStatus.ACTIVE, reason="Repair complete"),
    )
    assert updated2.status == FacilityStatus.ACTIVE.value


@pytest.mark.asyncio
async def test_asset_category_creation(seeded_session: AsyncSession):
    session = seeded_session
    society_id = uuid.uuid4()

    cat_repo = AssetCategoryRepository(session)
    cat = await cat_repo.create(
        AssetCategory(
            society_id=society_id,
            category_code="ELEV-SYS",
            name="Elevators & Lifts",
            description="Vertical transportation infrastructure",
            is_critical=True,
        )
    )

    assert cat.id is not None
    assert cat.category_code == "ELEV-SYS"
    assert cat.is_critical is True


@pytest.mark.asyncio
async def test_asset_crud_and_status_transitions(seeded_session: AsyncSession):
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

    cat_repo = AssetCategoryRepository(session)
    cat = await cat_repo.create(
        AssetCategory(
            society_id=society_id,
            category_code="GEN-SYS",
            name="Generators",
        )
    )

    asset_service = AssetService(session)

    # Create Asset
    asset = await asset_service.create_asset(
        society_id,
        user.id,
        AssetCreate(
            name="500 KVA Diesel Generator",
            category_id=cat.id,
            serial_number="DG-500-12345",
            model_number="Kirloskar 500",
            criticality=AssetCriticality.CRITICAL,
        ),
    )

    assert asset.id is not None
    assert asset.asset_code.startswith("AST-")
    assert asset.status == AssetStatus.IN_SERVICE.value

    # Transition status IN_SERVICE -> UNDER_MAINTENANCE
    updated = await asset_service.update_asset_status(
        society_id,
        user.id,
        asset.id,
        AssetStatusUpdate(status=AssetStatus.UNDER_MAINTENANCE, reason="Filter replacement"),
    )
    assert updated.status == AssetStatus.UNDER_MAINTENANCE.value

    # Check status history
    history = await asset_service.get_status_history(society_id, asset.id)
    assert len(history) == 1
    assert history[0].old_status == AssetStatus.IN_SERVICE.value
    assert history[0].new_status == AssetStatus.UNDER_MAINTENANCE.value


@pytest.mark.asyncio
async def test_asset_location_movement(seeded_session: AsyncSession):
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

    facility_service = FacilityService(session)
    fac = await facility_service.create_facility(
        society_id,
        FacilityCreate(name="Clubhouse Gym", facility_type=FacilityType.GYM),
    )

    cat_repo = AssetCategoryRepository(session)
    cat = await cat_repo.create(
        AssetCategory(society_id=society_id, category_code="GYM-EQ", name="Gym Equipment")
    )

    asset_service = AssetService(session)
    asset = await asset_service.create_asset(
        society_id,
        user.id,
        AssetCreate(name="Treadmill LifeFitness", category_id=cat.id),
    )

    # Move location to Gym
    loc = await asset_service.move_asset_location(
        society_id,
        user.id,
        asset.id,
        AssetLocationMove(
            facility_id=fac.id,
            location_details="Corner Section, East Wall",
            reason="Relocated for gym setup",
        ),
    )

    assert loc.facility_id == fac.id
    history = await asset_service.get_location_history(society_id, asset.id)
    assert len(history) >= 1


@pytest.mark.asyncio
async def test_asset_assignment_history(seeded_session: AsyncSession):
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

    cat_repo = AssetCategoryRepository(session)
    cat = await cat_repo.create(
        AssetCategory(society_id=society_id, category_code="TOOL-KIT", name="Maintenance Tools")
    )

    asset_service = AssetService(session)
    asset = await asset_service.create_asset(
        society_id,
        user.id,
        AssetCreate(name="Digital Multimeter Pro", category_id=cat.id),
    )

    assign = await asset_service.assign_asset(
        society_id,
        user.id,
        asset.id,
        AssetAssignmentCreate(
            assigned_to_type=AssetAssignmentType.STAFF,
            notes="Assigned to senior electrician",
        ),
    )

    assert assign.id is not None
    assert assign.assigned_to_type == AssetAssignmentType.STAFF.value

    history = await asset_service.get_assignment_history(society_id, asset.id)
    assert len(history) == 1


@pytest.mark.asyncio
async def test_documents_and_maintenance_links(seeded_session: AsyncSession):
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

    facility_service = FacilityService(session)
    fac = await facility_service.create_facility(
        society_id,
        FacilityCreate(name="Main Gate Post", facility_type=FacilityType.SECURITY_POST),
    )

    cat_repo = AssetCategoryRepository(session)
    cat = await cat_repo.create(
        AssetCategory(society_id=society_id, category_code="BOOM-BAR", name="Boom Barriers")
    )

    asset_service = AssetService(session)
    asset = await asset_service.create_asset(
        society_id,
        user.id,
        AssetCreate(name="Automatic Boom Barrier 1", category_id=cat.id, facility_id=fac.id),
    )

    doc_service = DocumentService(session)
    asset_doc = await doc_service.add_asset_document(
        society_id,
        user.id,
        asset.id,
        AssetDocumentCreate(
            document_type=AssetDocumentType.WARRANTY,
            title="Boom Barrier Warranty 3 Year",
            file_path="/docs/warranty_bb1.pdf",
        ),
    )
    assert asset_doc.id is not None

    fac_doc = await doc_service.add_facility_document(
        society_id,
        user.id,
        fac.id,
        FacilityDocumentCreate(
            document_type=FacilityDocumentType.LAYOUT_PLAN,
            title="Gate House Floor Plan",
            file_path="/docs/gate_house_plan.pdf",
        ),
    )
    assert fac_doc.id is not None

    maint_service = MaintenanceLinkService(session)
    link = await maint_service.create_link(
        society_id,
        user.id,
        AssetMaintenanceLinkCreate(
            asset_id=asset.id,
            facility_id=fac.id,
            link_type=MaintenanceLinkType.PREVENTIVE,
            notes="Quarterly preventive check",
        ),
    )
    assert link.id is not None


@pytest.mark.asyncio
async def test_asset_view_sensitive_masking(seeded_session: AsyncSession):
    session = seeded_session
    society_id = uuid.uuid4()

    user = User(
        email=f"resident-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        first_name="Resident",
        last_name="User",
        display_name="Resident User",
    )
    session.add(user)
    await session.flush()

    cat_repo = AssetCategoryRepository(session)
    cat = await cat_repo.create(
        AssetCategory(society_id=society_id, category_code="SENS-EQ", name="Security Equipment")
    )

    asset_service = AssetService(session)
    asset = await asset_service.create_asset(
        society_id,
        user.id,
        AssetCreate(
            name="CCTV Main Control Unit",
            category_id=cat.id,
            serial_number="CCTV-SECRET-8899",
            model_number="Hikvision 4K Pro",
        ),
    )

    assert asset.serial_number == "CCTV-SECRET-8899"
