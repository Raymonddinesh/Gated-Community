"""API Router for Maintenance Categories & Subcategories."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user, resolve_society_context
from apps.api.src.database.models.identity import User
from apps.api.src.database.models.maintenance import MaintenanceCategory, MaintenanceSubcategory
from apps.api.src.database.repositories.authorization_repository import AuthorizationRepository
from apps.api.src.database.session import get_db_session
from apps.api.src.maintenance.infrastructure.repositories import MaintenanceCategoryRepository
from apps.api.src.maintenance.schemas import (
    MaintenanceCategoryCreateRequest,
    MaintenanceCategoryResponse,
    MaintenanceSubcategoryCreateRequest,
    MaintenanceSubcategoryResponse,
)

router = APIRouter(prefix="/categories", tags=["Maintenance Categories"])


@router.get("", response_model=list[MaintenanceCategoryResponse])
async def list_categories(
    include_inactive: bool = Query(False),
    society_id: uuid.UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> list[MaintenanceCategory]:
    repo = MaintenanceCategoryRepository(db)
    return await repo.list_categories(society_id, include_inactive=include_inactive)


@router.post("", response_model=MaintenanceCategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    request: MaintenanceCategoryCreateRequest,
    society_id: uuid.UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> MaintenanceCategory:
    auth_repo = AuthorizationRepository(db)
    perms = await auth_repo.get_user_permission_codes(current_user.id, society_id)
    if "maintenance.category.manage" not in perms:
        raise HTTPException(status_code=403, detail="Permission denied to manage categories.")

    repo = MaintenanceCategoryRepository(db)
    existing = await repo.get_category_by_code(request.code, society_id)
    if existing:
        raise HTTPException(status_code=400, detail=f"Category code '{request.code}' already exists.")

    cat = MaintenanceCategory(
        society_id=society_id,
        name=request.name,
        code=request.code,
        description=request.description,
        icon=request.icon,
        display_order=request.display_order,
    )
    return await repo.create_category(cat)


@router.post(
    "/{category_id}/subcategories",
    response_model=MaintenanceSubcategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_subcategory(
    category_id: uuid.UUID,
    request: MaintenanceSubcategoryCreateRequest,
    society_id: uuid.UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> MaintenanceSubcategory:
    auth_repo = AuthorizationRepository(db)
    perms = await auth_repo.get_user_permission_codes(current_user.id, society_id)
    if "maintenance.category.manage" not in perms:
        raise HTTPException(status_code=403, detail="Permission denied to manage categories.")

    repo = MaintenanceCategoryRepository(db)
    cat = await repo.get_category_by_id(category_id, society_id)
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found.")

    subcat = MaintenanceSubcategory(
        society_id=society_id,
        category_id=category_id,
        name=request.name,
        code=request.code,
        description=request.description,
        display_order=request.display_order,
    )
    return await repo.create_subcategory(subcat)
