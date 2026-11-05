"""Vendor Categories API Router."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user, require_permission, resolve_society_context
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session
from apps.api.src.vendor.application.category_service import VendorCategoryService
from apps.api.src.vendor.schemas import (
    VendorCategoryCreate,
    VendorCategoryResponse,
    VendorCategoryUpdate,
)

router = APIRouter(prefix="/categories", tags=["Vendor Categories"])


@router.post(
    "/",
    response_model=VendorCategoryResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("vendor.category.manage"))],
)
async def create_category(
    payload: VendorCategoryCreate,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    service = VendorCategoryService(db)
    return await service.create_category(payload, society_id)


@router.get(
    "/",
    response_model=list[VendorCategoryResponse],
    dependencies=[Depends(require_permission("vendor.view"))],
)
async def list_categories(
    active_only: bool = Query(False),
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    service = VendorCategoryService(db)
    return await service.list_categories(society_id, active_only=active_only)


@router.get(
    "/{category_id}",
    response_model=VendorCategoryResponse,
    dependencies=[Depends(require_permission("vendor.view"))],
)
async def get_category(
    category_id: UUID,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    service = VendorCategoryService(db)
    return await service.get_category(category_id, society_id)


@router.patch(
    "/{category_id}",
    response_model=VendorCategoryResponse,
    dependencies=[Depends(require_permission("vendor.category.manage"))],
)
async def update_category(
    category_id: UUID,
    payload: VendorCategoryUpdate,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    service = VendorCategoryService(db)
    return await service.update_category(category_id, payload, society_id)
