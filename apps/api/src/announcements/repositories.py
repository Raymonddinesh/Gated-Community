"""Phase 16 Announcement Repositories."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.src.announcements.enums import AnnouncementPriority, AnnouncementStatus
from apps.api.src.database.models.announcements import (
    Announcement,
    AnnouncementAcknowledgement,
    AnnouncementAttachment,
    AnnouncementAudience,
    AnnouncementReadReceipt,
    AnnouncementSchedule,
    AnnouncementStatusHistory,
    AnnouncementVersion,
)


class AnnouncementRepository:
    """Repository for Announcement entity."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, announcement: Announcement) -> Announcement:
        self.db.add(announcement)
        await self.db.flush()
        return announcement

    async def get_by_id(self, society_id: UUID, announcement_id: UUID) -> Announcement | None:
        stmt = (
            select(Announcement)
            .options(
                selectinload(Announcement.audiences),
                selectinload(Announcement.attachments),
                selectinload(Announcement.acknowledgements),
                selectinload(Announcement.read_receipts),
            )
            .where(
                Announcement.society_id == society_id,
                Announcement.id == announcement_id,
            )
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def list_announcements(
        self,
        society_id: UUID,
        status: AnnouncementStatus | None = None,
        priority: AnnouncementPriority | None = None,
        is_pinned: bool | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[Announcement], int]:
        filters = [Announcement.society_id == society_id]
        if status:
            filters.append(Announcement.status == status.value)
        if priority:
            filters.append(Announcement.priority == priority.value)
        if is_pinned is not None:
            filters.append(Announcement.is_pinned == is_pinned)

        count_stmt = select(func.count()).select_from(Announcement).where(*filters)
        total_res = await self.db.execute(count_stmt)
        total = total_res.scalar_one()

        offset = (page - 1) * size
        stmt = (
            select(Announcement)
            .options(
                selectinload(Announcement.audiences),
                selectinload(Announcement.attachments),
            )
            .where(*filters)
            .order_by(Announcement.is_pinned.desc(), Announcement.created_at.desc())
            .offset(offset)
            .limit(size)
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all()), total


class AnnouncementAudienceRepository:
    """Repository for Announcement Audiences."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_many(self, audiences: list[AnnouncementAudience]) -> list[AnnouncementAudience]:
        for a in audiences:
            self.db.add(a)
        await self.db.flush()
        return audiences

    async def list_by_announcement(
        self, society_id: UUID, announcement_id: UUID
    ) -> list[AnnouncementAudience]:
        stmt = select(AnnouncementAudience).where(
            AnnouncementAudience.society_id == society_id,
            AnnouncementAudience.announcement_id == announcement_id,
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())


class AnnouncementAttachmentRepository:
    """Repository for Announcement Attachments."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_many(self, attachments: list[AnnouncementAttachment]) -> list[AnnouncementAttachment]:
        for a in attachments:
            self.db.add(a)
        await self.db.flush()
        return attachments

    async def get_by_id(self, society_id: UUID, attachment_id: UUID) -> AnnouncementAttachment | None:
        stmt = select(AnnouncementAttachment).where(
            AnnouncementAttachment.society_id == society_id,
            AnnouncementAttachment.id == attachment_id,
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()


class AnnouncementAcknowledgementRepository:
    """Repository for Announcement Acknowledgements."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, ack: AnnouncementAcknowledgement) -> AnnouncementAcknowledgement:
        self.db.add(ack)
        await self.db.flush()
        return ack

    async def get_user_ack(
        self, society_id: UUID, announcement_id: UUID, user_id: UUID, version_number: int
    ) -> AnnouncementAcknowledgement | None:
        stmt = select(AnnouncementAcknowledgement).where(
            AnnouncementAcknowledgement.society_id == society_id,
            AnnouncementAcknowledgement.announcement_id == announcement_id,
            AnnouncementAcknowledgement.user_id == user_id,
            AnnouncementAcknowledgement.version_number == version_number,
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def count_acknowledgements(self, society_id: UUID, announcement_id: UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(AnnouncementAcknowledgement)
            .where(
                AnnouncementAcknowledgement.society_id == society_id,
                AnnouncementAcknowledgement.announcement_id == announcement_id,
            )
        )
        res = await self.db.execute(stmt)
        return res.scalar_one()


class AnnouncementReadReceiptRepository:
    """Repository for Announcement Read Receipts."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, read_receipt: AnnouncementReadReceipt) -> AnnouncementReadReceipt:
        self.db.add(read_receipt)
        await self.db.flush()
        return read_receipt

    async def get_user_read(
        self, society_id: UUID, announcement_id: UUID, user_id: UUID
    ) -> AnnouncementReadReceipt | None:
        stmt = select(AnnouncementReadReceipt).where(
            AnnouncementReadReceipt.society_id == society_id,
            AnnouncementReadReceipt.announcement_id == announcement_id,
            AnnouncementReadReceipt.user_id == user_id,
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def count_reads(self, society_id: UUID, announcement_id: UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(AnnouncementReadReceipt)
            .where(
                AnnouncementReadReceipt.society_id == society_id,
                AnnouncementReadReceipt.announcement_id == announcement_id,
            )
        )
        res = await self.db.execute(stmt)
        return res.scalar_one()


class AnnouncementScheduleRepository:
    """Repository for Announcement Schedules."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, schedule: AnnouncementSchedule) -> AnnouncementSchedule:
        self.db.add(schedule)
        await self.db.flush()
        return schedule


class AnnouncementStatusHistoryRepository:
    """Repository for Announcement Status Histories."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, history: AnnouncementStatusHistory) -> AnnouncementStatusHistory:
        self.db.add(history)
        await self.db.flush()
        return history

    async def list_by_announcement(
        self, society_id: UUID, announcement_id: UUID
    ) -> list[AnnouncementStatusHistory]:
        stmt = (
            select(AnnouncementStatusHistory)
            .where(
                AnnouncementStatusHistory.society_id == society_id,
                AnnouncementStatusHistory.announcement_id == announcement_id,
            )
            .order_by(AnnouncementStatusHistory.changed_at.asc())
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())


class AnnouncementVersionRepository:
    """Repository for Announcement Versions."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, version: AnnouncementVersion) -> AnnouncementVersion:
        self.db.add(version)
        await self.db.flush()
        return version

    async def list_by_announcement(
        self, society_id: UUID, announcement_id: UUID
    ) -> list[AnnouncementVersion]:
        stmt = (
            select(AnnouncementVersion)
            .where(
                AnnouncementVersion.society_id == society_id,
                AnnouncementVersion.announcement_id == announcement_id,
            )
            .order_by(AnnouncementVersion.version_number.desc())
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())
