"""Vendor Core Profile & Status API Router."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user, require_permission, resolve_society_context
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session
from apps.api.src.vendor.application.service_catalog_service import VendorCatalogService
from apps.api.src.vendor.application.vendor_service import VendorService
from apps.api.src.vendor.infrastructure.repositories import (
    VendorAssignmentHistoryRepository,
    VendorStatusHistoryRepository,
)
from apps.api.src.vendor.schemas import (
    VendorAssignmentHistoryResponse,
    VendorContactCreate,
    VendorContactResponse,
    VendorProfileCreate,
    VendorProfileListResponse,
    VendorProfileResponse,
    VendorProfileUpdate,
    VendorStatusHistoryResponse,
    VendorStatusUpdate,
)

router = APIRouter(prefix="", tags=["Vendor Profiles"])


@router.post(
    "/",
    response_model=VendorProfileResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("vendor.create"))],
)
async def create_vendor(
    payload: VendorProfileCreate,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    service = VendorService(db)
    return await service.create_vendor(payload, society_id, current_user.id)


@router.get(
    "/",
    response_model=VendorProfileListResponse,
    dependencies=[Depends(require_permission("vendor.view"))],
)
async def list_vendors(
    status: str | None = Query(None),
    category_id: UUID | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    include_archived: bool = Query(False),
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    service = VendorService(db)
    items, total = await service.list_vendors(
        society_id=society_id,
        status=status,
        category_id=category_id,
        search=search,
        page=page,
        page_size=page_size,
        include_archived=include_archived,
    )
    resp_items = [VendorProfileResponse.model_validate(item) for item in items]
    return VendorProfileListResponse(
        items=resp_items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{vendor_id}",
    response_model=VendorProfileResponse,
    dependencies=[Depends(require_permission("vendor.view"))],
)
async def get_vendor(
    vendor_id: UUID,
    include_archived: bool = Query(False),
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    service = VendorService(db)
    return await service.get_vendor(vendor_id, society_id, include_archived=include_archived)


@router.patch(
    "/{vendor_id}",
    response_model=VendorProfileResponse,
    dependencies=[Depends(require_permission("vendor.update"))],
)
async def update_vendor(
    vendor_id: UUID,
    payload: VendorProfileUpdate,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    service = VendorService(db)
    return await service.update_vendor(vendor_id, payload, society_id)


@router.post(
    "/{vendor_id}/status",
    response_model=VendorProfileResponse,
    dependencies=[Depends(require_permission("vendor.status.manage"))],
)
async def update_vendor_status(
    vendor_id: UUID,
    payload: VendorStatusUpdate,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    service = VendorService(db)
    return await service.update_status(vendor_id, payload, society_id, current_user.id)


@router.delete(
    "/{vendor_id}",
    response_model=VendorProfileResponse,
    dependencies=[Depends(require_permission("vendor.archive"))],
)
async def archive_vendor(
    vendor_id: UUID,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    service = VendorService(db)
    return await service.archive_vendor(vendor_id, society_id, current_user.id)


@router.get(
    "/{vendor_id}/status-history",
    response_model=list[VendorStatusHistoryResponse],
    dependencies=[Depends(require_permission("vendor.audit.view"))],
)
async def list_status_history(
    vendor_id: UUID,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    repo = VendorStatusHistoryRepository(db)
    return await repo.list_by_vendor(vendor_id, society_id)


@router.get(
    "/{vendor_id}/assignments",
    response_model=list[VendorAssignmentHistoryResponse],
    dependencies=[Depends(require_permission("vendor.assignment.view"))],
)
async def list_vendor_assignments(
    vendor_id: UUID,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    repo = VendorAssignmentHistoryRepository(db)
    return await repo.list_by_vendor(vendor_id, society_id)


@router.post(
    "/{vendor_id}/contacts",
    response_model=VendorContactResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("vendor.contact.manage"))],
)
async def add_vendor_contact(
    vendor_id: UUID,
    payload: VendorContactCreate,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    catalog_service = VendorCatalogService(db)
    return await catalog_service.add_contact(vendor_id, payload, society_id)


@router.get(
    "/{vendor_id}/contacts",
    response_model=list[VendorContactResponse],
    dependencies=[Depends(require_permission("vendor.view"))],
)
async def list_vendor_contacts(
    vendor_id: UUID,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    catalog_service = VendorCatalogService(db)
    return await catalog_service.list_contacts(vendor_id, society_id)
