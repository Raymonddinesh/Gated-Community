"""SQLAlchemy Async Repositories for Maintenance & Work Order Management Domain."""

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.src.database.models.maintenance import (
    MaintenanceCategory,
    MaintenanceSubcategory,
    MaintenanceWorkOrder,
    WorkOrderActivity,
    WorkOrderAssignment,
    WorkOrderAttachment,
    WorkOrderComment,
    WorkOrderEscalation,
    WorkOrderMaterialUsage,
    WorkOrderResolution,
)
from apps.api.src.maintenance.domain.concurrency import acquire_work_order_number_lock


class MaintenanceCategoryRepository:
    """Repository for maintenance categories and subcategories."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_category_by_id(
        self, category_id: uuid.UUID, society_id: uuid.UUID
    ) -> MaintenanceCategory | None:
        query = (
            select(MaintenanceCategory)
            .where(
                MaintenanceCategory.id == category_id,
                MaintenanceCategory.society_id == society_id,
            )
            .options(selectinload(MaintenanceCategory.subcategories))
        )
        res = await self.session.execute(query)
        cat = res.scalar_one_or_none()
        if cat and cat.subcategories is None:
            cat.subcategories = []
        return cat

    async def get_category_by_code(self, code: str, society_id: uuid.UUID) -> MaintenanceCategory | None:
        query = select(MaintenanceCategory).where(
            MaintenanceCategory.code == code,
            MaintenanceCategory.society_id == society_id,
        )
        res = await self.session.execute(query)
        return res.scalar_one_or_none()

    async def list_categories(
        self, society_id: uuid.UUID, include_inactive: bool = False
    ) -> list[MaintenanceCategory]:
        query = select(MaintenanceCategory).where(MaintenanceCategory.society_id == society_id)
        if not include_inactive:
            query = query.where(MaintenanceCategory.is_active.is_(True))
        query = query.options(selectinload(MaintenanceCategory.subcategories)).order_by(
            MaintenanceCategory.display_order, MaintenanceCategory.name
        )
        res = await self.session.execute(query)
        categories = list(res.scalars().all())
        for cat in categories:
            if cat.subcategories is None:
                cat.subcategories = []
        return categories

    async def create_category(self, category: MaintenanceCategory) -> MaintenanceCategory:
        self.session.add(category)
        await self.session.flush()
        if category.subcategories is None:
            category.subcategories = []
        return category

    async def get_subcategory_by_id(
        self, subcategory_id: uuid.UUID, society_id: uuid.UUID
    ) -> MaintenanceSubcategory | None:
        query = select(MaintenanceSubcategory).where(
            MaintenanceSubcategory.id == subcategory_id,
            MaintenanceSubcategory.society_id == society_id,
        )
        res = await self.session.execute(query)
        return res.scalar_one_or_none()

    async def create_subcategory(self, subcategory: MaintenanceSubcategory) -> MaintenanceSubcategory:
        self.session.add(subcategory)
        await self.session.flush()
        return subcategory


class MaintenanceWorkOrderRepository:
    """Repository for core Maintenance Work Orders."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def generate_next_work_order_number(self, society_id: uuid.UUID, year: int | None = None) -> str:
        """Generate next sequence number WO-YYYY-XXXXXX under advisory lock."""
        current_year = year or datetime.utcnow().year
        await acquire_work_order_number_lock(self.session, society_id, current_year)

        prefix = f"WO-{current_year}-"
        query = select(func.count(MaintenanceWorkOrder.id)).where(
            MaintenanceWorkOrder.society_id == society_id,
            MaintenanceWorkOrder.work_order_number.like(f"{prefix}%"),
        )
        res = await self.session.execute(query)
        count = res.scalar() or 0
        seq = count + 1
        return f"{prefix}{seq:06d}"

    async def get_by_id(self, work_order_id: uuid.UUID, society_id: uuid.UUID) -> MaintenanceWorkOrder | None:
        query = (
            select(MaintenanceWorkOrder)
            .where(
                MaintenanceWorkOrder.id == work_order_id,
                MaintenanceWorkOrder.society_id == society_id,
            )
            .options(
                selectinload(MaintenanceWorkOrder.category).selectinload(MaintenanceCategory.subcategories),
                selectinload(MaintenanceWorkOrder.subcategory),
                selectinload(MaintenanceWorkOrder.resolution),
                selectinload(MaintenanceWorkOrder.assignments),
                selectinload(MaintenanceWorkOrder.materials),
                selectinload(MaintenanceWorkOrder.attachments),
                selectinload(MaintenanceWorkOrder.comments),
                selectinload(MaintenanceWorkOrder.activities),
            )
        )
        res = await self.session.execute(query)
        wo = res.scalar_one_or_none()
        if wo and wo.category and wo.category.subcategories is None:
            wo.category.subcategories = []
        return wo

    async def get_by_number(
        self, work_order_number: str, society_id: uuid.UUID
    ) -> MaintenanceWorkOrder | None:
        query = (
            select(MaintenanceWorkOrder)
            .where(
                MaintenanceWorkOrder.work_order_number == work_order_number,
                MaintenanceWorkOrder.society_id == society_id,
            )
            .options(
                selectinload(MaintenanceWorkOrder.category).selectinload(MaintenanceCategory.subcategories),
                selectinload(MaintenanceWorkOrder.subcategory),
                selectinload(MaintenanceWorkOrder.resolution),
            )
        )
        res = await self.session.execute(query)
        wo = res.scalar_one_or_none()
        if wo and wo.category and wo.category.subcategories is None:
            wo.category.subcategories = []
        return wo

    async def create(self, work_order: MaintenanceWorkOrder) -> MaintenanceWorkOrder:
        self.session.add(work_order)
        await self.session.flush()
        return work_order

    async def update(self, work_order: MaintenanceWorkOrder) -> MaintenanceWorkOrder:
        work_order.updated_at = datetime.utcnow()
        await self.session.flush()
        return work_order

    async def list_work_orders(
        self,
        society_id: uuid.UUID,
        status: str | None = None,
        priority: str | None = None,
        category_id: uuid.UUID | None = None,
        requested_by_user_id: uuid.UUID | None = None,
        assigned_user_id: uuid.UUID | None = None,
        complaint_id: uuid.UUID | None = None,
        is_overdue: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[MaintenanceWorkOrder], int]:
        query = select(MaintenanceWorkOrder).where(MaintenanceWorkOrder.society_id == society_id)

        if status:
            query = query.where(MaintenanceWorkOrder.status == status)
        if priority:
            query = query.where(MaintenanceWorkOrder.priority == priority)
        if category_id:
            query = query.where(MaintenanceWorkOrder.category_id == category_id)
        if requested_by_user_id:
            query = query.where(MaintenanceWorkOrder.requested_by_user_id == requested_by_user_id)
        if complaint_id:
            query = query.where(MaintenanceWorkOrder.complaint_id == complaint_id)
        if is_overdue:
            now = datetime.utcnow()
            query = query.where(
                MaintenanceWorkOrder.due_at.is_not(None),
                MaintenanceWorkOrder.due_at < now,
                MaintenanceWorkOrder.status.notin_(["COMPLETED", "VERIFIED", "CLOSED", "CANCELLED"]),
            )

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_res = await self.session.execute(count_query)
        total = total_res.scalar() or 0

        # Execute paginated query
        query = (
            query.options(
                selectinload(MaintenanceWorkOrder.category).selectinload(MaintenanceCategory.subcategories),
                selectinload(MaintenanceWorkOrder.subcategory),
                selectinload(MaintenanceWorkOrder.resolution),
            )
            .order_by(MaintenanceWorkOrder.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        res = await self.session.execute(query)
        work_orders = list(res.scalars().all())
        for wo in work_orders:
            if wo.category and wo.category.subcategories is None:
                wo.category.subcategories = []
        return work_orders, total


class WorkOrderAssignmentRepository:
    """Repository for work order assignments."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, assignment: WorkOrderAssignment) -> WorkOrderAssignment:
        self.session.add(assignment)
        await self.session.flush()
        return assignment

    async def list_by_work_order(
        self, work_order_id: uuid.UUID, society_id: uuid.UUID
    ) -> list[WorkOrderAssignment]:
        query = (
            select(WorkOrderAssignment)
            .where(
                WorkOrderAssignment.work_order_id == work_order_id,
                WorkOrderAssignment.society_id == society_id,
            )
            .order_by(WorkOrderAssignment.assigned_at.desc())
        )
        res = await self.session.execute(query)
        return list(res.scalars().all())


class WorkOrderCommentRepository:
    """Repository for work order comments."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, comment: WorkOrderComment) -> WorkOrderComment:
        self.session.add(comment)
        await self.session.flush()
        return comment

    async def list_by_work_order(
        self, work_order_id: uuid.UUID, society_id: uuid.UUID, include_internal: bool = False
    ) -> list[WorkOrderComment]:
        query = select(WorkOrderComment).where(
            WorkOrderComment.work_order_id == work_order_id,
            WorkOrderComment.society_id == society_id,
        )
        if not include_internal:
            query = query.where(WorkOrderComment.is_internal.is_(False))
        query = query.order_by(WorkOrderComment.created_at.asc())
        res = await self.session.execute(query)
        return list(res.scalars().all())


class WorkOrderAttachmentRepository:
    """Repository for work order attachments."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, attachment: WorkOrderAttachment) -> WorkOrderAttachment:
        self.session.add(attachment)
        await self.session.flush()
        return attachment

    async def get_by_id(self, attachment_id: uuid.UUID, society_id: uuid.UUID) -> WorkOrderAttachment | None:
        query = select(WorkOrderAttachment).where(
            WorkOrderAttachment.id == attachment_id,
            WorkOrderAttachment.society_id == society_id,
            WorkOrderAttachment.is_archived.is_(False),
        )
        res = await self.session.execute(query)
        return res.scalar_one_or_none()

    async def list_by_work_order(
        self, work_order_id: uuid.UUID, society_id: uuid.UUID
    ) -> list[WorkOrderAttachment]:
        query = (
            select(WorkOrderAttachment)
            .where(
                WorkOrderAttachment.work_order_id == work_order_id,
                WorkOrderAttachment.society_id == society_id,
                WorkOrderAttachment.is_archived.is_(False),
            )
            .order_by(WorkOrderAttachment.created_at.desc())
        )
        res = await self.session.execute(query)
        return list(res.scalars().all())


class WorkOrderMaterialUsageRepository:
    """Repository for work order material usages."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, material: WorkOrderMaterialUsage) -> WorkOrderMaterialUsage:
        self.session.add(material)
        await self.session.flush()
        return material

    async def list_by_work_order(
        self, work_order_id: uuid.UUID, society_id: uuid.UUID
    ) -> list[WorkOrderMaterialUsage]:
        query = (
            select(WorkOrderMaterialUsage)
            .where(
                WorkOrderMaterialUsage.work_order_id == work_order_id,
                WorkOrderMaterialUsage.society_id == society_id,
            )
            .order_by(WorkOrderMaterialUsage.created_at.asc())
        )
        res = await self.session.execute(query)
        return list(res.scalars().all())


class WorkOrderResolutionRepository:
    """Repository for work order resolution details."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, resolution: WorkOrderResolution) -> WorkOrderResolution:
        self.session.add(resolution)
        await self.session.flush()
        return resolution

    async def get_by_work_order(
        self, work_order_id: uuid.UUID, society_id: uuid.UUID
    ) -> WorkOrderResolution | None:
        query = select(WorkOrderResolution).where(
            WorkOrderResolution.work_order_id == work_order_id,
            WorkOrderResolution.society_id == society_id,
        )
        res = await self.session.execute(query)
        return res.scalar_one_or_none()


class WorkOrderEscalationRepository:
    """Repository for work order SLA escalations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, escalation: WorkOrderEscalation) -> WorkOrderEscalation:
        self.session.add(escalation)
        await self.session.flush()
        return escalation

    async def get_active_escalation(
        self, work_order_id: uuid.UUID, society_id: uuid.UUID
    ) -> WorkOrderEscalation | None:
        query = select(WorkOrderEscalation).where(
            WorkOrderEscalation.work_order_id == work_order_id,
            WorkOrderEscalation.society_id == society_id,
            WorkOrderEscalation.status == "PENDING",
        )
        res = await self.session.execute(query)
        return res.scalar_one_or_none()


class WorkOrderActivityRepository:
    """Repository for activity timeline log."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, activity: WorkOrderActivity) -> WorkOrderActivity:
        self.session.add(activity)
        await self.session.flush()
        return activity

    async def list_by_work_order(
        self, work_order_id: uuid.UUID, society_id: uuid.UUID
    ) -> list[WorkOrderActivity]:
        query = (
            select(WorkOrderActivity)
            .where(
                WorkOrderActivity.work_order_id == work_order_id,
                WorkOrderActivity.society_id == society_id,
            )
            .order_by(WorkOrderActivity.created_at.asc())
        )
        res = await self.session.execute(query)
        return list(res.scalars().all())
