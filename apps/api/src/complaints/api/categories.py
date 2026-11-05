"""API Router for Complaint Categories and Subcategories."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import (
    require_permission,
    resolve_society_context,
)
from apps.api.src.complaints.application.complaint_service import ComplaintService
from apps.api.src.complaints.schemas import (
    ComplaintCategoryCreateRequest,
    ComplaintCategoryResponse,
    ComplaintSubcategoryCreateRequest,
    ComplaintSubcategoryResponse,
)
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session

router = APIRouter(tags=["Complaint Categories & Subcategories"])


@router.post(
    "/complaint-categories",
    response_model=ComplaintCategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_category(
    data: ComplaintCategoryCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("complaint.category.manage")),
) -> ComplaintCategoryResponse:
    """Create a new complaint category for society."""
    service = ComplaintService(db)
    category = await service.create_category(society_id, data)
    return ComplaintCategoryResponse.model_validate(category)


@router.get(
    "/complaint-categories",
    response_model=list[ComplaintCategoryResponse],
)
async def list_categories(
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("complaint.create")),
) -> list[ComplaintCategoryResponse]:
    """List complaint categories in society."""
    service = ComplaintService(db)
    categories = await service.list_categories(society_id, active_only)
    return [ComplaintCategoryResponse.model_validate(c) for c in categories]


@router.post(
    "/complaint-categories/subcategories",
    response_model=ComplaintSubcategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_subcategory(
    data: ComplaintSubcategoryCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("complaint.category.manage")),
) -> ComplaintSubcategoryResponse:
    """Create a new complaint subcategory."""
    service = ComplaintService(db)
    subcategory = await service.create_subcategory(society_id, data)
    return ComplaintSubcategoryResponse.model_validate(subcategory)
