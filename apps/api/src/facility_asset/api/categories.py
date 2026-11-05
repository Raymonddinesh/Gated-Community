"""Asset Categories API Router."""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import require_permission, resolve_society_context
from apps.api.src.database.models.facility_asset import AssetCategory
from apps.api.src.database.session import get_db_session
from apps.api.src.facility_asset.repositories import AssetCategoryRepository
from apps.api.src.facility_asset.schemas import AssetCategoryCreate, AssetCategoryResponse

router = APIRouter(prefix="/asset-categories", tags=["Asset Categories"])


@router.post(
    "",
    response_model=AssetCategoryResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("asset.category.manage"))],
)
async def create_asset_category(
    payload: AssetCategoryCreate,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
):
    repo = AssetCategoryRepository(db)
    cat = AssetCategory(
        society_id=society_id,
        category_code=payload.category_code,
        name=payload.name,
        description=payload.description,
        parent_id=payload.parent_id,
        is_critical=payload.is_critical,
    )
    return await repo.create(cat)


@router.get(
    "",
    response_model=list[AssetCategoryResponse],
    dependencies=[Depends(require_permission("asset.view"))],
)
async def list_asset_categories(
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
):
    repo = AssetCategoryRepository(db)
    return await repo.list_categories(society_id)
