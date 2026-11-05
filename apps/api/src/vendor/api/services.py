"""Vendor Offered Services API Router."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user, require_permission, resolve_society_context
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session
from apps.api.src.vendor.application.service_catalog_service import VendorCatalogService
from apps.api.src.vendor.schemas import VendorServiceCreate, VendorServiceResponse

router = APIRouter(prefix="", tags=["Vendor Services Catalog"])


@router.post(
    "/{vendor_id}/services",
    response_model=VendorServiceResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("vendor.service.manage"))],
)
async def add_vendor_service(
    vendor_id: UUID,
    payload: VendorServiceCreate,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    catalog_service = VendorCatalogService(db)
    return await catalog_service.add_service(vendor_id, payload, society_id)


@router.get(
    "/{vendor_id}/services",
    response_model=list[VendorServiceResponse],
    dependencies=[Depends(require_permission("vendor.view"))],
)
async def list_vendor_services(
    vendor_id: UUID,
    active_only: bool = Query(False),
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    catalog_service = VendorCatalogService(db)
    return await catalog_service.list_services(vendor_id, society_id, active_only=active_only)
