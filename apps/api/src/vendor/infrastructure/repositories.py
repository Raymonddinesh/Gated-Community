"""Vendor Domain Repositories for Async Database Persistence."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from apps.api.src.database.models.vendor import (
    VendorAssignmentHistory,
    VendorCategory,
    VendorContact,
    VendorDocument,
    VendorProfile,
    VendorService,
    VendorStatusHistory,
)


class VendorCategoryRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, category_id: UUID, society_id: UUID) -> VendorCategory | None:
        stmt = (
            select(VendorCategory)
            .where(VendorCategory.id == category_id)
            .where(VendorCategory.society_id == society_id)
        )
        return await self.db.scalar(stmt)

    async def get_by_code(self, code: str, society_id: UUID) -> VendorCategory | None:
        stmt = (
            select(VendorCategory)
            .where(VendorCategory.code == code)
            .where(VendorCategory.society_id == society_id)
        )
        return await self.db.scalar(stmt)

    async def list_categories(self, society_id: UUID, active_only: bool = False) -> list[VendorCategory]:
        stmt = select(VendorCategory).where(VendorCategory.society_id == society_id)
        if active_only:
            stmt = stmt.where(VendorCategory.is_active.is_(True))
        stmt = stmt.order_by(VendorCategory.display_order.asc(), VendorCategory.name.asc())
        res = await self.db.scalars(stmt)
        return list(res.all())

    async def create(self, category: VendorCategory) -> VendorCategory:
        self.db.add(category)
        await self.db.flush()
        return category


class VendorProfileRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(
        self, vendor_id: UUID, society_id: UUID, include_archived: bool = False
    ) -> VendorProfile | None:
        stmt = (
            select(VendorProfile)
            .options(
                joinedload(VendorProfile.primary_category),
                joinedload(VendorProfile.contacts),
                joinedload(VendorProfile.addresses),
                joinedload(VendorProfile.services),
            )
            .where(VendorProfile.id == vendor_id)
            .where(VendorProfile.society_id == society_id)
        )
        if not include_archived:
            stmt = stmt.where(VendorProfile.archived_at.is_(None))
        return await self.db.scalar(stmt)

    async def get_by_code(self, code: str, society_id: UUID) -> VendorProfile | None:
        stmt = (
            select(VendorProfile)
            .where(VendorProfile.vendor_code == code)
            .where(VendorProfile.society_id == society_id)
        )
        return await self.db.scalar(stmt)

    async def list_vendors(
        self,
        society_id: UUID,
        status: str | None = None,
        category_id: UUID | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
        include_archived: bool = False,
    ) -> tuple[list[VendorProfile], int]:
        stmt = select(VendorProfile).where(VendorProfile.society_id == society_id)

        if not include_archived:
            stmt = stmt.where(VendorProfile.archived_at.is_(None))

        if status:
            stmt = stmt.where(VendorProfile.status == status)

        if category_id:
            stmt = stmt.where(VendorProfile.primary_category_id == category_id)

        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(
                (VendorProfile.display_name.ilike(pattern))
                | (VendorProfile.legal_name.ilike(pattern))
                | (VendorProfile.vendor_code.ilike(pattern))
            )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.scalar(count_stmt)) or 0

        stmt = (
            stmt.options(
                joinedload(VendorProfile.primary_category),
                joinedload(VendorProfile.contacts),
                joinedload(VendorProfile.addresses),
                joinedload(VendorProfile.services),
            )
            .order_by(VendorProfile.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        res = await self.db.scalars(stmt)
        items = list(res.unique().all())
        return items, total

    async def create(self, vendor: VendorProfile) -> VendorProfile:
        self.db.add(vendor)
        await self.db.flush()
        return vendor


class VendorContactRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, contact_id: UUID, society_id: UUID) -> VendorContact | None:
        stmt = (
            select(VendorContact)
            .where(VendorContact.id == contact_id)
            .where(VendorContact.society_id == society_id)
        )
        return await self.db.scalar(stmt)

    async def list_by_vendor(self, vendor_id: UUID, society_id: UUID) -> list[VendorContact]:
        stmt = (
            select(VendorContact)
            .where(VendorContact.vendor_id == vendor_id)
            .where(VendorContact.society_id == society_id)
            .order_by(VendorContact.is_primary.desc(), VendorContact.created_at.asc())
        )
        res = await self.db.scalars(stmt)
        return list(res.all())

    async def create(self, contact: VendorContact) -> VendorContact:
        self.db.add(contact)
        await self.db.flush()
        return contact


class VendorServiceRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, service_id: UUID, society_id: UUID) -> VendorService | None:
        stmt = (
            select(VendorService)
            .where(VendorService.id == service_id)
            .where(VendorService.society_id == society_id)
        )
        return await self.db.scalar(stmt)

    async def list_by_vendor(
        self, vendor_id: UUID, society_id: UUID, active_only: bool = False
    ) -> list[VendorService]:
        stmt = (
            select(VendorService)
            .where(VendorService.vendor_id == vendor_id)
            .where(VendorService.society_id == society_id)
        )
        if active_only:
            stmt = stmt.where(VendorService.is_active.is_(True))
        stmt = stmt.order_by(VendorService.service_name.asc())
        res = await self.db.scalars(stmt)
        return list(res.all())

    async def create(self, service: VendorService) -> VendorService:
        self.db.add(service)
        await self.db.flush()
        return service


class VendorDocumentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(
        self, document_id: UUID, society_id: UUID, include_archived: bool = False
    ) -> VendorDocument | None:
        stmt = (
            select(VendorDocument)
            .where(VendorDocument.id == document_id)
            .where(VendorDocument.society_id == society_id)
        )
        if not include_archived:
            stmt = stmt.where(VendorDocument.archived_at.is_(None))
        return await self.db.scalar(stmt)

    async def list_by_vendor(
        self, vendor_id: UUID, society_id: UUID, include_archived: bool = False
    ) -> list[VendorDocument]:
        stmt = (
            select(VendorDocument)
            .where(VendorDocument.vendor_id == vendor_id)
            .where(VendorDocument.society_id == society_id)
        )
        if not include_archived:
            stmt = stmt.where(VendorDocument.archived_at.is_(None))
        stmt = stmt.order_by(VendorDocument.created_at.desc())
        res = await self.db.scalars(stmt)
        return list(res.all())

    async def create(self, doc: VendorDocument) -> VendorDocument:
        self.db.add(doc)
        await self.db.flush()
        return doc


class VendorStatusHistoryRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_by_vendor(self, vendor_id: UUID, society_id: UUID) -> list[VendorStatusHistory]:
        stmt = (
            select(VendorStatusHistory)
            .where(VendorStatusHistory.vendor_id == vendor_id)
            .where(VendorStatusHistory.society_id == society_id)
            .order_by(VendorStatusHistory.created_at.desc())
        )
        res = await self.db.scalars(stmt)
        return list(res.all())

    async def create(self, history: VendorStatusHistory) -> VendorStatusHistory:
        self.db.add(history)
        await self.db.flush()
        return history


class VendorAssignmentHistoryRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_by_vendor(self, vendor_id: UUID, society_id: UUID) -> list[VendorAssignmentHistory]:
        stmt = (
            select(VendorAssignmentHistory)
            .where(VendorAssignmentHistory.vendor_id == vendor_id)
            .where(VendorAssignmentHistory.society_id == society_id)
            .order_by(VendorAssignmentHistory.created_at.desc())
        )
        res = await self.db.scalars(stmt)
        return list(res.all())

    async def create(self, record: VendorAssignmentHistory) -> VendorAssignmentHistory:
        self.db.add(record)
        await self.db.flush()
        return record
