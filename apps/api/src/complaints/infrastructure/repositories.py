"""Repositories for Complaints & Helpdesk Domain."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.src.complaints.domain.concurrency import get_complaint_number_lock
from apps.api.src.database.models.complaint import (
    Complaint,
    ComplaintAssignment,
    ComplaintAttachment,
    ComplaintCategory,
    ComplaintComment,
    ComplaintEscalation,
    ComplaintResolution,
    ComplaintSLAPolicy,
    ComplaintStatusHistory,
    ComplaintSubcategory,
)


class ComplaintCategoryRepository:
    """Repository for ComplaintCategory queries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        category_id: uuid.UUID,
        society_id: uuid.UUID,
    ) -> ComplaintCategory | None:
        stmt = (
            select(ComplaintCategory)
            .options(selectinload(ComplaintCategory.subcategories))
            .where(
                ComplaintCategory.id == category_id,
                ComplaintCategory.society_id == society_id,
            )
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_code(
        self,
        code: str,
        society_id: uuid.UUID,
    ) -> ComplaintCategory | None:
        stmt = select(ComplaintCategory).where(
            ComplaintCategory.code == code.upper().strip(),
            ComplaintCategory.society_id == society_id,
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_categories(
        self,
        society_id: uuid.UUID,
        active_only: bool = True,
    ) -> list[ComplaintCategory]:
        stmt = (
            select(ComplaintCategory)
            .options(selectinload(ComplaintCategory.subcategories))
            .where(ComplaintCategory.society_id == society_id)
        )
        if active_only:
            stmt = stmt.where(ComplaintCategory.is_active.is_(True))
        stmt = stmt.order_by(ComplaintCategory.display_order.asc(), ComplaintCategory.name.asc())
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def save(self, category: ComplaintCategory) -> ComplaintCategory:
        self.session.add(category)
        await self.session.flush()
        return category


class ComplaintSubcategoryRepository:
    """Repository for ComplaintSubcategory queries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        subcategory_id: uuid.UUID,
        society_id: uuid.UUID,
    ) -> ComplaintSubcategory | None:
        stmt = select(ComplaintSubcategory).where(
            ComplaintSubcategory.id == subcategory_id,
            ComplaintSubcategory.society_id == society_id,
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_for_category(
        self,
        category_id: uuid.UUID,
        society_id: uuid.UUID,
        active_only: bool = True,
    ) -> list[ComplaintSubcategory]:
        stmt = select(ComplaintSubcategory).where(
            ComplaintSubcategory.category_id == category_id,
            ComplaintSubcategory.society_id == society_id,
        )
        if active_only:
            stmt = stmt.where(ComplaintSubcategory.is_active.is_(True))
        stmt = stmt.order_by(ComplaintSubcategory.display_order.asc(), ComplaintSubcategory.name.asc())
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def save(self, subcategory: ComplaintSubcategory) -> ComplaintSubcategory:
        self.session.add(subcategory)
        await self.session.flush()
        return subcategory


class ComplaintSLAPolicyRepository:
    """Repository for ComplaintSLAPolicy queries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        policy_id: uuid.UUID,
        society_id: uuid.UUID,
    ) -> ComplaintSLAPolicy | None:
        stmt = select(ComplaintSLAPolicy).where(
            ComplaintSLAPolicy.id == policy_id,
            ComplaintSLAPolicy.society_id == society_id,
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def find_matching_policy(
        self,
        society_id: uuid.UUID,
        category_id: uuid.UUID,
        priority: str,
    ) -> ComplaintSLAPolicy | None:
        """Find category-specific SLA policy or fallback to global priority policy."""
        # 1. Check for category + priority policy
        stmt_cat = select(ComplaintSLAPolicy).where(
            ComplaintSLAPolicy.society_id == society_id,
            ComplaintSLAPolicy.category_id == category_id,
            ComplaintSLAPolicy.priority == priority,
            ComplaintSLAPolicy.is_active.is_(True),
        )
        res_cat = await self.session.execute(stmt_cat)
        policy = res_cat.scalar_one_or_none()
        if policy:
            return policy

        # 2. Fallback to default priority policy (category_id is NULL)
        stmt_default = select(ComplaintSLAPolicy).where(
            ComplaintSLAPolicy.society_id == society_id,
            ComplaintSLAPolicy.category_id.is_(None),
            ComplaintSLAPolicy.priority == priority,
            ComplaintSLAPolicy.is_active.is_(True),
        )
        res_default = await self.session.execute(stmt_default)
        return res_default.scalar_one_or_none()

    async def list_policies(
        self,
        society_id: uuid.UUID,
    ) -> list[ComplaintSLAPolicy]:
        stmt = (
            select(ComplaintSLAPolicy)
            .where(ComplaintSLAPolicy.society_id == society_id)
            .order_by(ComplaintSLAPolicy.priority.asc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def save(self, policy: ComplaintSLAPolicy) -> ComplaintSLAPolicy:
        self.session.add(policy)
        await self.session.flush()
        return policy


class ComplaintRepository:
    """Repository for Complaint queries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def generate_complaint_number(self, society_id: uuid.UUID) -> str:
        """Generate a safe, unique human-readable complaint number per society (e.g. CMP-2026-000001)."""
        year = datetime.now(UTC).year
        prefix = f"CMP-{year}-"

        async with get_complaint_number_lock(society_id):
            stmt = select(func.count()).where(
                Complaint.society_id == society_id,
                Complaint.complaint_number.like(f"{prefix}%"),
            )
            res = await self.session.execute(stmt)
            count = res.scalar_one() or 0
            seq = count + 1
            return f"{prefix}{seq:06d}"

    async def get_by_id(
        self,
        complaint_id: uuid.UUID,
        society_id: uuid.UUID,
    ) -> Complaint | None:
        stmt = (
            select(Complaint)
            .options(
                selectinload(Complaint.category).selectinload(ComplaintCategory.subcategories),
                selectinload(Complaint.subcategory),
                selectinload(Complaint.sla_policy),
                selectinload(Complaint.assignments),
                selectinload(Complaint.resolution),
            )
            .where(
                Complaint.id == complaint_id,
                Complaint.society_id == society_id,
            )
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_number(
        self,
        complaint_number: str,
        society_id: uuid.UUID,
    ) -> Complaint | None:
        stmt = (
            select(Complaint)
            .options(
                selectinload(Complaint.category).selectinload(ComplaintCategory.subcategories),
                selectinload(Complaint.subcategory),
            )
            .where(
                Complaint.complaint_number == complaint_number.strip(),
                Complaint.society_id == society_id,
            )
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def search(
        self,
        society_id: uuid.UUID,
        query: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        category_id: uuid.UUID | None = None,
        subcategory_id: uuid.UUID | None = None,
        unit_id: uuid.UUID | None = None,
        raised_by_user_id: uuid.UUID | None = None,
        assigned_user_id: uuid.UUID | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[Complaint], int]:
        """Search and filter complaints with safe pagination."""
        base_stmt = select(Complaint).where(Complaint.society_id == society_id)

        if query:
            q_clean = query.strip()
            base_stmt = base_stmt.where(
                or_(
                    Complaint.complaint_number.ilike(f"%{q_clean}%"),
                    Complaint.title.ilike(f"%{q_clean}%"),
                    Complaint.description.ilike(f"%{q_clean}%"),
                )
            )

        if status:
            base_stmt = base_stmt.where(Complaint.status == status)
        if priority:
            base_stmt = base_stmt.where(Complaint.priority == priority)
        if category_id:
            base_stmt = base_stmt.where(Complaint.category_id == category_id)
        if subcategory_id:
            base_stmt = base_stmt.where(Complaint.subcategory_id == subcategory_id)
        if unit_id:
            base_stmt = base_stmt.where(Complaint.raised_for_unit_id == unit_id)
        if raised_by_user_id:
            base_stmt = base_stmt.where(Complaint.raised_by_user_id == raised_by_user_id)
        if assigned_user_id:
            base_stmt = base_stmt.join(Complaint.assignments).where(
                ComplaintAssignment.assigned_to_user_id == assigned_user_id,
                ComplaintAssignment.is_current.is_(True),
            )

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total_res = await self.session.execute(count_stmt)
        total = total_res.scalar_one() or 0

        offset = (page - 1) * size
        stmt = (
            base_stmt.options(
                selectinload(Complaint.category).selectinload(ComplaintCategory.subcategories),
                selectinload(Complaint.subcategory),
                selectinload(Complaint.assignments),
            )
            .order_by(Complaint.created_at.desc())
            .offset(offset)
            .limit(size)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all()), total

    async def save(self, complaint: Complaint) -> Complaint:
        self.session.add(complaint)
        await self.session.flush()
        return complaint


class ComplaintAssignmentRepository:
    """Repository for ComplaintAssignment management."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def deactivate_previous_assignments(
        self,
        society_id: uuid.UUID,
        complaint_id: uuid.UUID,
    ) -> None:
        stmt = select(ComplaintAssignment).where(
            ComplaintAssignment.society_id == society_id,
            ComplaintAssignment.complaint_id == complaint_id,
            ComplaintAssignment.is_current.is_(True),
        )
        res = await self.session.execute(stmt)
        for assign in res.scalars().all():
            assign.is_current = False
            self.session.add(assign)
        await self.session.flush()

    async def save(self, assignment: ComplaintAssignment) -> ComplaintAssignment:
        self.session.add(assignment)
        await self.session.flush()
        return assignment


class ComplaintCommentRepository:
    """Repository for ComplaintComment communications."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        comment_id: uuid.UUID,
        society_id: uuid.UUID,
    ) -> ComplaintComment | None:
        stmt = select(ComplaintComment).where(
            ComplaintComment.id == comment_id,
            ComplaintComment.society_id == society_id,
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_for_complaint(
        self,
        society_id: uuid.UUID,
        complaint_id: uuid.UUID,
        include_internal: bool = False,
    ) -> list[ComplaintComment]:
        stmt = select(ComplaintComment).where(
            ComplaintComment.society_id == society_id,
            ComplaintComment.complaint_id == complaint_id,
        )
        if not include_internal:
            stmt = stmt.where(ComplaintComment.comment_type == "PUBLIC")
        stmt = stmt.order_by(ComplaintComment.created_at.asc())
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def save(self, comment: ComplaintComment) -> ComplaintComment:
        self.session.add(comment)
        await self.session.flush()
        return comment


class ComplaintAttachmentRepository:
    """Repository for ComplaintAttachment metadata."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        attachment_id: uuid.UUID,
        society_id: uuid.UUID,
    ) -> ComplaintAttachment | None:
        stmt = select(ComplaintAttachment).where(
            ComplaintAttachment.id == attachment_id,
            ComplaintAttachment.society_id == society_id,
            ComplaintAttachment.archived_at.is_(None),
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_for_complaint(
        self,
        society_id: uuid.UUID,
        complaint_id: uuid.UUID,
    ) -> list[ComplaintAttachment]:
        stmt = (
            select(ComplaintAttachment)
            .where(
                ComplaintAttachment.society_id == society_id,
                ComplaintAttachment.complaint_id == complaint_id,
                ComplaintAttachment.archived_at.is_(None),
            )
            .order_by(ComplaintAttachment.created_at.desc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def save(self, attachment: ComplaintAttachment) -> ComplaintAttachment:
        self.session.add(attachment)
        await self.session.flush()
        return attachment

    async def delete(self, attachment: ComplaintAttachment) -> None:
        """Soft-archive attachment."""
        attachment.archived_at = datetime.now(UTC)
        self.session.add(attachment)
        await self.session.flush()


class ComplaintStatusHistoryRepository:
    """Repository for ComplaintStatusHistory logs."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_history(
        self,
        society_id: uuid.UUID,
        complaint_id: uuid.UUID,
    ) -> list[ComplaintStatusHistory]:
        stmt = (
            select(ComplaintStatusHistory)
            .where(
                ComplaintStatusHistory.society_id == society_id,
                ComplaintStatusHistory.complaint_id == complaint_id,
            )
            .order_by(ComplaintStatusHistory.created_at.asc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def save(self, history: ComplaintStatusHistory) -> ComplaintStatusHistory:
        self.session.add(history)
        await self.session.flush()
        return history


class ComplaintEscalationRepository:
    """Repository for ComplaintEscalation records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_active_escalation(
        self,
        society_id: uuid.UUID,
        complaint_id: uuid.UUID,
    ) -> ComplaintEscalation | None:
        stmt = select(ComplaintEscalation).where(
            ComplaintEscalation.society_id == society_id,
            ComplaintEscalation.complaint_id == complaint_id,
            ComplaintEscalation.status == "ACTIVE",
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_for_complaint(
        self,
        society_id: uuid.UUID,
        complaint_id: uuid.UUID,
    ) -> list[ComplaintEscalation]:
        stmt = (
            select(ComplaintEscalation)
            .where(
                ComplaintEscalation.society_id == society_id,
                ComplaintEscalation.complaint_id == complaint_id,
            )
            .order_by(ComplaintEscalation.created_at.desc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def save(self, escalation: ComplaintEscalation) -> ComplaintEscalation:
        self.session.add(escalation)
        await self.session.flush()
        return escalation


class ComplaintResolutionRepository:
    """Repository for ComplaintResolution records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_for_complaint(
        self,
        society_id: uuid.UUID,
        complaint_id: uuid.UUID,
    ) -> ComplaintResolution | None:
        stmt = select(ComplaintResolution).where(
            ComplaintResolution.society_id == society_id,
            ComplaintResolution.complaint_id == complaint_id,
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def save(self, resolution: ComplaintResolution) -> ComplaintResolution:
        self.session.add(resolution)
        await self.session.flush()
        return resolution
