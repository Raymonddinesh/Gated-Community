"""Facility Management API Router."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user, require_permission, resolve_society_context
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session
from apps.api.src.facility_asset.document_service import DocumentService
from apps.api.src.facility_asset.facility_service import FacilityService
from apps.api.src.facility_asset.maintenance_link_service import MaintenanceLinkService
from apps.api.src.facility_asset.schemas import (
    AssetMaintenanceLinkResponse,
    FacilityAreaCreate,
    FacilityAreaResponse,
    FacilityCreate,
    FacilityDocumentCreate,
    FacilityDocumentResponse,
    FacilityListResponse,
    FacilityResponse,
    FacilityStatusUpdate,
    FacilityUpdate,
)

router = APIRouter(prefix="/facilities", tags=["Facilities"])


@router.post(
    "",
    response_model=FacilityResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("facility.create"))],
)
async def create_facility(
    payload: FacilityCreate,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    service = FacilityService(db)
    return await service.create_facility(society_id, payload)


@router.get(
    "",
    response_model=FacilityListResponse,
    dependencies=[Depends(require_permission("facility.view"))],
)
async def list_facilities(
    facility_type: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
):
    service = FacilityService(db)
    items, total = await service.list_facilities(
        society_id, facility_type=facility_type, status=status, page=page, size=size
    )
    return FacilityListResponse(
        items=[FacilityResponse.model_validate(f) for f in items],
        total=total,
        page=page,
        size=size,
    )


@router.get(
    "/{facility_id}",
    response_model=FacilityResponse,
    dependencies=[Depends(require_permission("facility.view"))],
)
async def get_facility(
    facility_id: UUID,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
):
    service = FacilityService(db)
    return await service.get_facility(society_id, facility_id)


@router.patch(
    "/{facility_id}",
    response_model=FacilityResponse,
    dependencies=[Depends(require_permission("facility.update"))],
)
async def update_facility(
    facility_id: UUID,
    payload: FacilityUpdate,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
):
    service = FacilityService(db)
    return await service.update_facility(society_id, facility_id, payload)


@router.post(
    "/{facility_id}/status",
    response_model=FacilityResponse,
    dependencies=[Depends(require_permission("facility.status.manage"))],
)
async def update_facility_status(
    facility_id: UUID,
    payload: FacilityStatusUpdate,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
):
    service = FacilityService(db)
    return await service.update_facility_status(society_id, facility_id, payload)


@router.post(
    "/{facility_id}/areas",
    response_model=FacilityAreaResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("facility.area.manage"))],
)
async def add_facility_area(
    facility_id: UUID,
    payload: FacilityAreaCreate,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
):
    service = FacilityService(db)
    return await service.add_facility_area(society_id, facility_id, payload)


@router.post(
    "/{facility_id}/documents",
    response_model=FacilityDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("facility.document.manage"))],
)
async def add_facility_document(
    facility_id: UUID,
    payload: FacilityDocumentCreate,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    service = DocumentService(db)
    return await service.add_facility_document(society_id, current_user.id, facility_id, payload)


@router.get(
    "/{facility_id}/documents",
    response_model=list[FacilityDocumentResponse],
    dependencies=[Depends(require_permission("facility.document.view"))],
)
async def list_facility_documents(
    facility_id: UUID,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
):
    service = DocumentService(db)
    return await service.list_facility_documents(society_id, facility_id)


@router.get(
    "/{facility_id}/maintenance-links",
    response_model=list[AssetMaintenanceLinkResponse],
    dependencies=[Depends(require_permission("facility.view"))],
)
async def list_facility_maintenance_links(
    facility_id: UUID,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
):
    service = MaintenanceLinkService(db)
    return await service.list_by_facility(society_id, facility_id)
