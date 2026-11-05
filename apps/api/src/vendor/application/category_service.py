"""Vendor Category Application Service."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.vendor import VendorCategory
from apps.api.src.vendor.domain.exceptions import (
    VendorCategoryNotFoundException,
    VendorDuplicateCategoryCodeException,
)
from apps.api.src.vendor.infrastructure.repositories import VendorCategoryRepository
from apps.api.src.vendor.schemas import VendorCategoryCreate, VendorCategoryUpdate


class VendorCategoryService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = VendorCategoryRepository(db)

    async def create_category(self, data: VendorCategoryCreate, society_id: UUID) -> VendorCategory:
        existing = await self.repo.get_by_code(data.code, society_id)
        if existing:
            raise VendorDuplicateCategoryCodeException(data.code)

        category = VendorCategory(
            society_id=society_id,
            name=data.name,
            code=data.code,
            description=data.description,
            is_active=data.is_active,
            display_order=data.display_order,
        )
        return await self.repo.create(category)

    async def get_category(self, category_id: UUID, society_id: UUID) -> VendorCategory:
        category = await self.repo.get_by_id(category_id, society_id)
        if not category:
            raise VendorCategoryNotFoundException(str(category_id))
        return category

    async def list_categories(self, society_id: UUID, active_only: bool = False) -> list[VendorCategory]:
        return await self.repo.list_categories(society_id, active_only=active_only)

    async def update_category(
        self, category_id: UUID, data: VendorCategoryUpdate, society_id: UUID
    ) -> VendorCategory:
        category = await self.get_category(category_id, society_id)
        if data.name is not None:
            category.name = data.name
        if data.description is not None:
            category.description = data.description
        if data.is_active is not None:
            category.is_active = data.is_active
        if data.display_order is not None:
            category.display_order = data.display_order

        await self.db.flush()
        return category
