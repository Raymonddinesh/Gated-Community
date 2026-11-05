"""Phase 14 Facility & Asset Repository Layer."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.src.database.models.facility_asset import (
    Asset,
    AssetAssignmentHistory,
    AssetCategory,
    AssetDocument,
    AssetLocation,
    AssetMaintenanceLink,
    AssetStatusHistory,
    Facility,
    FacilityArea,
    FacilityDocument,
)


class FacilityRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, society_id: UUID, facility_id: UUID) -> Facility | None:
        stmt = (
            select(Facility)
            .where(Facility.society_id == society_id, Facility.id == facility_id)
            .options(selectinload(Facility.areas), selectinload(Facility.documents))
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_by_code(self, society_id: UUID, facility_code: str) -> Facility | None:
        stmt = select(Facility).where(
            Facility.society_id == society_id, Facility.facility_code == facility_code
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def list_facilities(
        self,
        society_id: UUID,
        facility_type: str | None = None,
        status: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[Facility], int]:
        stmt = select(Facility).where(Facility.society_id == society_id)
        if facility_type:
            stmt = stmt.where(Facility.facility_type == facility_type)
        if status:
            stmt = stmt.where(Facility.status == status)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.scalar(count_stmt)) or 0

        stmt = stmt.options(selectinload(Facility.areas)).offset(skip).limit(limit)
        items = list((await self.db.execute(stmt)).scalars().all())
        return items, total

    async def create(self, facility: Facility) -> Facility:
        self.db.add(facility)
        await self.db.flush()
        return facility

    async def create_area(self, area: FacilityArea) -> FacilityArea:
        self.db.add(area)
        await self.db.flush()
        return area

    async def get_area_by_id(self, society_id: UUID, area_id: UUID) -> FacilityArea | None:
        stmt = select(FacilityArea).where(FacilityArea.society_id == society_id, FacilityArea.id == area_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()


class AssetCategoryRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, society_id: UUID, category_id: UUID) -> AssetCategory | None:
        stmt = select(AssetCategory).where(
            AssetCategory.society_id == society_id, AssetCategory.id == category_id
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_by_code(self, society_id: UUID, category_code: str) -> AssetCategory | None:
        stmt = select(AssetCategory).where(
            AssetCategory.society_id == society_id, AssetCategory.category_code == category_code
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def list_categories(self, society_id: UUID) -> list[AssetCategory]:
        stmt = select(AssetCategory).where(AssetCategory.society_id == society_id)
        return list((await self.db.execute(stmt)).scalars().all())

    async def create(self, category: AssetCategory) -> AssetCategory:
        self.db.add(category)
        await self.db.flush()
        return category


class AssetRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, society_id: UUID, asset_id: UUID) -> Asset | None:
        stmt = (
            select(Asset)
            .where(Asset.society_id == society_id, Asset.id == asset_id)
            .options(
                selectinload(Asset.category),
                selectinload(Asset.facility),
                selectinload(Asset.facility_area),
                selectinload(Asset.documents),
                selectinload(Asset.status_history),
            )
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_by_code(self, society_id: UUID, asset_code: str) -> Asset | None:
        stmt = select(Asset).where(Asset.society_id == society_id, Asset.asset_code == asset_code)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def list_assets(
        self,
        society_id: UUID,
        category_id: UUID | None = None,
        facility_id: UUID | None = None,
        status: str | None = None,
        criticality: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[Asset], int]:
        stmt = select(Asset).where(Asset.society_id == society_id)
        if category_id:
            stmt = stmt.where(Asset.category_id == category_id)
        if facility_id:
            stmt = stmt.where(Asset.facility_id == facility_id)
        if status:
            stmt = stmt.where(Asset.status == status)
        if criticality:
            stmt = stmt.where(Asset.criticality == criticality)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.scalar(count_stmt)) or 0

        stmt = stmt.offset(skip).limit(limit)
        items = list((await self.db.execute(stmt)).scalars().all())
        return items, total

    async def create(self, asset: Asset) -> Asset:
        self.db.add(asset)
        await self.db.flush()
        return asset


class AssetLocationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, loc: AssetLocation) -> AssetLocation:
        self.db.add(loc)
        await self.db.flush()
        return loc

    async def list_by_asset(self, society_id: UUID, asset_id: UUID) -> list[AssetLocation]:
        stmt = (
            select(AssetLocation)
            .where(AssetLocation.society_id == society_id, AssetLocation.asset_id == asset_id)
            .order_by(AssetLocation.moved_at.desc())
        )
        return list((await self.db.execute(stmt)).scalars().all())


class AssetStatusHistoryRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, history: AssetStatusHistory) -> AssetStatusHistory:
        self.db.add(history)
        await self.db.flush()
        return history

    async def list_by_asset(self, society_id: UUID, asset_id: UUID) -> list[AssetStatusHistory]:
        stmt = (
            select(AssetStatusHistory)
            .where(
                AssetStatusHistory.society_id == society_id,
                AssetStatusHistory.asset_id == asset_id,
            )
            .order_by(AssetStatusHistory.changed_at.desc())
        )
        return list((await self.db.execute(stmt)).scalars().all())


class AssetAssignmentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, assign: AssetAssignmentHistory) -> AssetAssignmentHistory:
        self.db.add(assign)
        await self.db.flush()
        return assign

    async def list_by_asset(self, society_id: UUID, asset_id: UUID) -> list[AssetAssignmentHistory]:
        stmt = (
            select(AssetAssignmentHistory)
            .where(
                AssetAssignmentHistory.society_id == society_id,
                AssetAssignmentHistory.asset_id == asset_id,
            )
            .order_by(AssetAssignmentHistory.assigned_at.desc())
        )
        return list((await self.db.execute(stmt)).scalars().all())


class AssetDocumentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, doc: AssetDocument) -> AssetDocument:
        self.db.add(doc)
        await self.db.flush()
        return doc

    async def list_by_asset(self, society_id: UUID, asset_id: UUID) -> list[AssetDocument]:
        stmt = (
            select(AssetDocument)
            .where(AssetDocument.society_id == society_id, AssetDocument.asset_id == asset_id)
            .order_by(AssetDocument.uploaded_at.desc())
        )
        return list((await self.db.execute(stmt)).scalars().all())


class FacilityDocumentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, doc: FacilityDocument) -> FacilityDocument:
        self.db.add(doc)
        await self.db.flush()
        return doc

    async def list_by_facility(self, society_id: UUID, facility_id: UUID) -> list[FacilityDocument]:
        stmt = (
            select(FacilityDocument)
            .where(
                FacilityDocument.society_id == society_id,
                FacilityDocument.facility_id == facility_id,
            )
            .order_by(FacilityDocument.uploaded_at.desc())
        )
        return list((await self.db.execute(stmt)).scalars().all())


class AssetMaintenanceLinkRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, link: AssetMaintenanceLink) -> AssetMaintenanceLink:
        self.db.add(link)
        await self.db.flush()
        return link

    async def list_by_asset(self, society_id: UUID, asset_id: UUID) -> list[AssetMaintenanceLink]:
        stmt = (
            select(AssetMaintenanceLink)
            .where(
                AssetMaintenanceLink.society_id == society_id,
                AssetMaintenanceLink.asset_id == asset_id,
            )
            .order_by(AssetMaintenanceLink.linked_at.desc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def list_by_facility(self, society_id: UUID, facility_id: UUID) -> list[AssetMaintenanceLink]:
        stmt = (
            select(AssetMaintenanceLink)
            .where(
                AssetMaintenanceLink.society_id == society_id,
                AssetMaintenanceLink.facility_id == facility_id,
            )
            .order_by(AssetMaintenanceLink.linked_at.desc())
        )
        return list((await self.db.execute(stmt)).scalars().all())
