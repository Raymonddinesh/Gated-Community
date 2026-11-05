"""Data access repositories for Visitor profiles, Invitations, Approvals, Access Records, and Documents."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.src.database.models.visitor import (
    Visitor,
    VisitorAccessRecord,
    VisitorApproval,
    VisitorDocument,
    VisitorInvitation,
)
from apps.api.src.visitors.domain.exceptions import VisitorAccessRecordImmutableError


class VisitorRepository:
    """Repository for Visitor profile queries and management."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, visitor_id: uuid.UUID, society_id: uuid.UUID) -> Visitor | None:
        """Fetch visitor by ID within tenant boundary."""
        stmt = (
            select(Visitor)
            .options(
                selectinload(Visitor.invitations),
                selectinload(Visitor.approvals),
                selectinload(Visitor.documents),
            )
            .where(
                Visitor.id == visitor_id,
                Visitor.society_id == society_id,
            )
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_phone(self, society_id: uuid.UUID, phone: str) -> Visitor | None:
        """Fetch active visitor by phone number."""
        stmt = select(Visitor).where(
            Visitor.society_id == society_id,
            Visitor.phone == phone.strip(),
            Visitor.status == "ACTIVE",
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def search(
        self,
        society_id: uuid.UUID,
        query: str | None = None,
        visitor_type: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[Visitor], int]:
        """Search and filter visitors with pagination."""
        base_stmt = select(Visitor).where(Visitor.society_id == society_id)

        if query:
            q_clean = query.strip()
            base_stmt = base_stmt.where(
                or_(
                    Visitor.name.ilike(f"%{q_clean}%"),
                    Visitor.phone.ilike(f"%{q_clean}%"),
                    Visitor.identification_number.ilike(f"%{q_clean}%"),
                )
            )

        if visitor_type:
            base_stmt = base_stmt.where(Visitor.visitor_type == visitor_type)
        if status:
            base_stmt = base_stmt.where(Visitor.status == status)

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total_res = await self.session.execute(count_stmt)
        total = total_res.scalar_one() or 0

        offset = (page - 1) * size
        stmt = (
            base_stmt.options(
                selectinload(Visitor.invitations),
                selectinload(Visitor.approvals),
                selectinload(Visitor.documents),
            )
            .order_by(Visitor.created_at.desc())
            .offset(offset)
            .limit(size)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all()), total

    async def save(self, visitor: Visitor) -> Visitor:
        self.session.add(visitor)
        await self.session.flush()
        return visitor


class VisitorInvitationRepository:
    """Repository for VisitorInvitation queries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        invitation_id: uuid.UUID,
        society_id: uuid.UUID,
    ) -> VisitorInvitation | None:
        stmt = (
            select(VisitorInvitation)
            .options(
                selectinload(VisitorInvitation.visitor),
                selectinload(VisitorInvitation.unit),
                selectinload(VisitorInvitation.host),
            )
            .where(
                VisitorInvitation.id == invitation_id,
                VisitorInvitation.society_id == society_id,
            )
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_pass_code(
        self,
        society_id: uuid.UUID,
        pass_code: str,
    ) -> VisitorInvitation | None:
        stmt = (
            select(VisitorInvitation)
            .options(
                selectinload(VisitorInvitation.visitor),
                selectinload(VisitorInvitation.unit),
                selectinload(VisitorInvitation.host),
            )
            .where(
                VisitorInvitation.society_id == society_id,
                VisitorInvitation.pass_code == pass_code.strip().upper(),
            )
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def search(
        self,
        society_id: uuid.UUID,
        unit_id: uuid.UUID | None = None,
        host_user_id: uuid.UUID | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[VisitorInvitation], int]:
        base_stmt = select(VisitorInvitation).where(VisitorInvitation.society_id == society_id)

        if unit_id:
            base_stmt = base_stmt.where(VisitorInvitation.unit_id == unit_id)
        if host_user_id:
            base_stmt = base_stmt.where(VisitorInvitation.host_user_id == host_user_id)
        if status:
            base_stmt = base_stmt.where(VisitorInvitation.status == status)

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total_res = await self.session.execute(count_stmt)
        total = total_res.scalar_one() or 0

        offset = (page - 1) * size
        stmt = (
            base_stmt.options(
                selectinload(VisitorInvitation.visitor),
                selectinload(VisitorInvitation.unit),
                selectinload(VisitorInvitation.host),
            )
            .order_by(VisitorInvitation.created_at.desc())
            .offset(offset)
            .limit(size)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all()), total

    async def save(self, invitation: VisitorInvitation) -> VisitorInvitation:
        self.session.add(invitation)
        await self.session.flush()
        return invitation


class VisitorApprovalRepository:
    """Repository for VisitorApproval queries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        approval_id: uuid.UUID,
        society_id: uuid.UUID,
    ) -> VisitorApproval | None:
        stmt = select(VisitorApproval).where(
            VisitorApproval.id == approval_id,
            VisitorApproval.society_id == society_id,
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_latest_for_visitor(
        self,
        society_id: uuid.UUID,
        visitor_id: uuid.UUID,
        unit_id: uuid.UUID,
    ) -> VisitorApproval | None:
        stmt = (
            select(VisitorApproval)
            .where(
                VisitorApproval.society_id == society_id,
                VisitorApproval.visitor_id == visitor_id,
                VisitorApproval.unit_id == unit_id,
            )
            .order_by(VisitorApproval.created_at.desc())
        )
        res = await self.session.execute(stmt)
        return res.scalars().first()

    async def save(self, approval: VisitorApproval) -> VisitorApproval:
        self.session.add(approval)
        await self.session.flush()
        return approval


class VisitorAccessRecordRepository:
    """Repository for append-only VisitorAccessRecord logs."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        record_id: uuid.UUID,
        society_id: uuid.UUID,
    ) -> VisitorAccessRecord | None:
        stmt = select(VisitorAccessRecord).where(
            VisitorAccessRecord.id == record_id,
            VisitorAccessRecord.society_id == society_id,
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_active_inside_visit(
        self,
        society_id: uuid.UUID,
        visitor_id: uuid.UUID,
        unit_id: uuid.UUID,
    ) -> VisitorAccessRecord | None:
        """Find active entry log where visitor has entered but not yet exited."""
        stmt = select(VisitorAccessRecord).where(
            VisitorAccessRecord.society_id == society_id,
            VisitorAccessRecord.visitor_id == visitor_id,
            VisitorAccessRecord.unit_id == unit_id,
            VisitorAccessRecord.access_type == "ENTRY",
            VisitorAccessRecord.exit_time.is_(None),
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def search(
        self,
        society_id: uuid.UUID,
        query: str | None = None,
        visitor_id: uuid.UUID | None = None,
        unit_id: uuid.UUID | None = None,
        access_type: str | None = None,
        gate_identifier: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[VisitorAccessRecord], int]:
        base_stmt = select(VisitorAccessRecord).where(VisitorAccessRecord.society_id == society_id)

        if query:
            q_clean = query.strip()
            base_stmt = base_stmt.where(
                or_(
                    VisitorAccessRecord.visitor_name_snapshot.ilike(f"%{q_clean}%"),
                    VisitorAccessRecord.visitor_phone_snapshot.ilike(f"%{q_clean}%"),
                    VisitorAccessRecord.gate_identifier.ilike(f"%{q_clean}%"),
                )
            )

        if visitor_id:
            base_stmt = base_stmt.where(VisitorAccessRecord.visitor_id == visitor_id)
        if unit_id:
            base_stmt = base_stmt.where(VisitorAccessRecord.unit_id == unit_id)
        if access_type:
            base_stmt = base_stmt.where(VisitorAccessRecord.access_type == access_type)
        if gate_identifier:
            base_stmt = base_stmt.where(VisitorAccessRecord.gate_identifier == gate_identifier)

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total_res = await self.session.execute(count_stmt)
        total = total_res.scalar_one() or 0

        offset = (page - 1) * size
        stmt = base_stmt.order_by(VisitorAccessRecord.access_time.desc()).offset(offset).limit(size)
        res = await self.session.execute(stmt)
        return list(res.scalars().all()), total

    async def save(self, record: VisitorAccessRecord) -> VisitorAccessRecord:
        """Append new access record or record exit timestamp."""
        self.session.add(record)
        await self.session.flush()
        return record

    async def delete(self, *args, **kwargs) -> None:
        """Access records are immutable audit logs and cannot be deleted."""
        raise VisitorAccessRecordImmutableError()


class VisitorDocumentRepository:
    """Repository for VisitorDocument queries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        document_id: uuid.UUID,
        society_id: uuid.UUID,
    ) -> VisitorDocument | None:
        stmt = select(VisitorDocument).where(
            VisitorDocument.id == document_id,
            VisitorDocument.society_id == society_id,
            VisitorDocument.archived_at.is_(None),
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_for_visitor(
        self,
        society_id: uuid.UUID,
        visitor_id: uuid.UUID,
    ) -> list[VisitorDocument]:
        stmt = (
            select(VisitorDocument)
            .where(
                VisitorDocument.society_id == society_id,
                VisitorDocument.visitor_id == visitor_id,
                VisitorDocument.archived_at.is_(None),
            )
            .order_by(VisitorDocument.created_at.desc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def save(self, document: VisitorDocument) -> VisitorDocument:
        self.session.add(document)
        await self.session.flush()
        return document

    async def delete(self, document: VisitorDocument) -> None:
        """Soft-archive document record without deleting physical file."""
        document.archived_at = datetime.now(UTC)
        self.session.add(document)
        await self.session.flush()
