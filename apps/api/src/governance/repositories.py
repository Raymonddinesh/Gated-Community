"""Phase 18 Governance Repositories."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.governance import (
    Committee,
    CommitteeMember,
    GovernanceAttachment,
    Meeting,
    MeetingActionItem,
    MeetingAgendaItem,
    MeetingAttendance,
    MeetingMinutes,
    MeetingQuorum,
    Resolution,
    ResolutionStatusHistory,
    ResolutionVote,
)


class CommitteeRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, committee: Committee) -> Committee:
        self.db.add(committee)
        await self.db.flush()
        return committee

    async def get_by_id(self, society_id: UUID, committee_id: UUID) -> Committee | None:
        stmt = select(Committee).where(Committee.society_id == society_id, Committee.id == committee_id)
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def list_committees(
        self, society_id: UUID, status: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[Committee]:
        stmt = select(Committee).where(Committee.society_id == society_id)
        if status:
            stmt = stmt.where(Committee.status == status)
        stmt = stmt.order_by(Committee.created_at.desc()).offset(offset).limit(limit)
        res = await self.db.execute(stmt)
        return list(res.scalars().all())


class CommitteeMemberRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, member: CommitteeMember) -> CommitteeMember:
        self.db.add(member)
        await self.db.flush()
        return member

    async def list_by_committee(self, society_id: UUID, committee_id: UUID) -> list[CommitteeMember]:
        stmt = select(CommitteeMember).where(
            CommitteeMember.society_id == society_id,
            CommitteeMember.committee_id == committee_id,
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())


class MeetingRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, meeting: Meeting) -> Meeting:
        self.db.add(meeting)
        await self.db.flush()
        return meeting

    async def get_by_id(self, society_id: UUID, meeting_id: UUID) -> Meeting | None:
        stmt = select(Meeting).where(Meeting.society_id == society_id, Meeting.id == meeting_id)
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def list_meetings(
        self, society_id: UUID, status: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[Meeting]:
        stmt = select(Meeting).where(Meeting.society_id == society_id)
        if status:
            stmt = stmt.where(Meeting.status == status)
        stmt = stmt.order_by(Meeting.scheduled_at.desc()).offset(offset).limit(limit)
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def get_next_meeting_number(self, society_id: UUID) -> str:
        stmt = select(func.count(1)).select_from(Meeting).where(Meeting.society_id == society_id)
        res = await self.db.execute(stmt)
        count = (res.scalar() or 0) + 1
        year = datetime.now().year
        return f"MTG-{year}-{count:06d}"


class MeetingAgendaItemRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, item: MeetingAgendaItem) -> MeetingAgendaItem:
        self.db.add(item)
        await self.db.flush()
        return item

    async def list_by_meeting(self, society_id: UUID, meeting_id: UUID) -> list[MeetingAgendaItem]:
        stmt = (
            select(MeetingAgendaItem)
            .where(MeetingAgendaItem.society_id == society_id, MeetingAgendaItem.meeting_id == meeting_id)
            .order_by(MeetingAgendaItem.sequence_number.asc())
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())


class MeetingAttendanceRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, attendance: MeetingAttendance) -> MeetingAttendance:
        self.db.add(attendance)
        await self.db.flush()
        return attendance

    async def get_by_user_meeting(
        self, society_id: UUID, meeting_id: UUID, user_id: UUID
    ) -> MeetingAttendance | None:
        stmt = select(MeetingAttendance).where(
            MeetingAttendance.society_id == society_id,
            MeetingAttendance.meeting_id == meeting_id,
            MeetingAttendance.user_id == user_id,
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def list_by_meeting(self, society_id: UUID, meeting_id: UUID) -> list[MeetingAttendance]:
        stmt = select(MeetingAttendance).where(
            MeetingAttendance.society_id == society_id,
            MeetingAttendance.meeting_id == meeting_id,
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def count_present(self, society_id: UUID, meeting_id: UUID) -> int:
        stmt = (
            select(func.count(1))
            .select_from(MeetingAttendance)
            .where(
                MeetingAttendance.society_id == society_id,
                MeetingAttendance.meeting_id == meeting_id,
                MeetingAttendance.status.in_(["PRESENT", "LATE"]),
            )
        )
        res = await self.db.execute(stmt)
        return res.scalar() or 0


class MeetingQuorumRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, quorum: MeetingQuorum) -> MeetingQuorum:
        self.db.add(quorum)
        await self.db.flush()
        return quorum

    async def get_latest_by_meeting(self, society_id: UUID, meeting_id: UUID) -> MeetingQuorum | None:
        stmt = (
            select(MeetingQuorum)
            .where(MeetingQuorum.society_id == society_id, MeetingQuorum.meeting_id == meeting_id)
            .order_by(MeetingQuorum.calculated_at.desc())
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()


class ResolutionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, resolution: Resolution) -> Resolution:
        self.db.add(resolution)
        await self.db.flush()
        return resolution

    async def get_by_id(self, society_id: UUID, resolution_id: UUID) -> Resolution | None:
        stmt = select(Resolution).where(Resolution.society_id == society_id, Resolution.id == resolution_id)
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def list_resolutions(
        self, society_id: UUID, status: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[Resolution]:
        stmt = select(Resolution).where(Resolution.society_id == society_id)
        if status:
            stmt = stmt.where(Resolution.status == status)
        stmt = stmt.order_by(Resolution.created_at.desc()).offset(offset).limit(limit)
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def get_next_resolution_number(self, society_id: UUID) -> str:
        stmt = select(func.count(1)).select_from(Resolution).where(Resolution.society_id == society_id)
        res = await self.db.execute(stmt)
        count = (res.scalar() or 0) + 1
        year = datetime.now().year
        return f"RES-{year}-{count:06d}"


class ResolutionVoteRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, vote: ResolutionVote) -> ResolutionVote:
        self.db.add(vote)
        await self.db.flush()
        return vote

    async def get_by_user_resolution(
        self, society_id: UUID, resolution_id: UUID, user_id: UUID
    ) -> ResolutionVote | None:
        stmt = select(ResolutionVote).where(
            ResolutionVote.society_id == society_id,
            ResolutionVote.resolution_id == resolution_id,
            ResolutionVote.user_id == user_id,
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def list_by_resolution(self, society_id: UUID, resolution_id: UUID) -> list[ResolutionVote]:
        stmt = select(ResolutionVote).where(
            ResolutionVote.society_id == society_id,
            ResolutionVote.resolution_id == resolution_id,
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def count_by_vote_value(self, society_id: UUID, resolution_id: UUID, vote_value: str) -> int:
        stmt = (
            select(func.count(1))
            .select_from(ResolutionVote)
            .where(
                ResolutionVote.society_id == society_id,
                ResolutionVote.resolution_id == resolution_id,
                ResolutionVote.vote == vote_value,
            )
        )
        res = await self.db.execute(stmt)
        return res.scalar() or 0


class ResolutionStatusHistoryRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, history: ResolutionStatusHistory) -> ResolutionStatusHistory:
        self.db.add(history)
        await self.db.flush()
        return history

    async def list_by_resolution(
        self, society_id: UUID, resolution_id: UUID
    ) -> list[ResolutionStatusHistory]:
        stmt = (
            select(ResolutionStatusHistory)
            .where(
                ResolutionStatusHistory.society_id == society_id,
                ResolutionStatusHistory.resolution_id == resolution_id,
            )
            .order_by(ResolutionStatusHistory.changed_at.asc())
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())


class MeetingMinutesRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, minutes: MeetingMinutes) -> MeetingMinutes:
        self.db.add(minutes)
        await self.db.flush()
        return minutes

    async def get_latest_by_meeting(self, society_id: UUID, meeting_id: UUID) -> MeetingMinutes | None:
        stmt = (
            select(MeetingMinutes)
            .where(MeetingMinutes.society_id == society_id, MeetingMinutes.meeting_id == meeting_id)
            .order_by(MeetingMinutes.version.desc())
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()


class MeetingActionItemRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, item: MeetingActionItem) -> MeetingActionItem:
        self.db.add(item)
        await self.db.flush()
        return item

    async def get_by_id(self, society_id: UUID, item_id: UUID) -> MeetingActionItem | None:
        stmt = select(MeetingActionItem).where(
            MeetingActionItem.society_id == society_id, MeetingActionItem.id == item_id
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def list_by_meeting(self, society_id: UUID, meeting_id: UUID) -> list[MeetingActionItem]:
        stmt = select(MeetingActionItem).where(
            MeetingActionItem.society_id == society_id,
            MeetingActionItem.meeting_id == meeting_id,
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())


class GovernanceAttachmentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, attachment: GovernanceAttachment) -> GovernanceAttachment:
        self.db.add(attachment)
        await self.db.flush()
        return attachment

    async def list_by_entity(
        self, society_id: UUID, entity_type: str, entity_id: UUID
    ) -> list[GovernanceAttachment]:
        stmt = select(GovernanceAttachment).where(
            GovernanceAttachment.society_id == society_id,
            GovernanceAttachment.entity_type == entity_type,
            GovernanceAttachment.entity_id == entity_id,
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())
