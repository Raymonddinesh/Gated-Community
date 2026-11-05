"""Phase 17 Event Repositories."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.events import (
    Event,
    EventApproval,
    EventAttachment,
    EventAttendance,
    EventParticipant,
    EventRegistration,
    EventSchedule,
    EventStatusHistory,
)


class EventRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, event: Event) -> Event:
        self.db.add(event)
        await self.db.flush()
        return event

    async def get_by_id(self, society_id: UUID, event_id: UUID) -> Event | None:
        stmt = select(Event).where(Event.society_id == society_id, Event.id == event_id)
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def list_events(
        self,
        society_id: UUID,
        status: str | None = None,
        event_type: str | None = None,
        facility_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Event]:
        stmt = select(Event).where(Event.society_id == society_id)
        if status:
            stmt = stmt.where(Event.status == status)
        if event_type:
            stmt = stmt.where(Event.event_type == event_type)
        if facility_id:
            stmt = stmt.where(Event.facility_id == facility_id)
        stmt = stmt.order_by(Event.starts_at.asc()).offset(offset).limit(limit)
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def get_next_event_number(self, society_id: UUID) -> str:
        stmt = select(func.count(Event.id)).where(Event.society_id == society_id)
        res = await self.db.execute(stmt)
        count = (res.scalar() or 0) + 1
        year = datetime.now().year
        return f"EVT-{year}-{count:06d}"


class EventParticipantRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, participant: EventParticipant) -> EventParticipant:
        self.db.add(participant)
        await self.db.flush()
        return participant

    async def list_by_event(self, society_id: UUID, event_id: UUID) -> list[EventParticipant]:
        stmt = select(EventParticipant).where(
            EventParticipant.society_id == society_id,
            EventParticipant.event_id == event_id,
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())


class EventRegistrationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, registration: EventRegistration) -> EventRegistration:
        self.db.add(registration)
        await self.db.flush()
        return registration

    async def get_by_id(self, society_id: UUID, registration_id: UUID) -> EventRegistration | None:
        stmt = select(EventRegistration).where(
            EventRegistration.society_id == society_id,
            EventRegistration.id == registration_id,
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_user_event(
        self, society_id: UUID, event_id: UUID, user_id: UUID
    ) -> EventRegistration | None:
        stmt = select(EventRegistration).where(
            EventRegistration.society_id == society_id,
            EventRegistration.event_id == event_id,
            EventRegistration.user_id == user_id,
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def list_by_event(
        self,
        society_id: UUID,
        event_id: UUID,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[EventRegistration]:
        stmt = select(EventRegistration).where(
            EventRegistration.society_id == society_id,
            EventRegistration.event_id == event_id,
        )
        if status:
            stmt = stmt.where(EventRegistration.status == status)
        stmt = stmt.order_by(EventRegistration.registered_at.asc()).offset(offset).limit(limit)
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def count_by_status(self, society_id: UUID, event_id: UUID, status: str) -> int:
        stmt = select(func.count(EventRegistration.id)).where(
            EventRegistration.society_id == society_id,
            EventRegistration.event_id == event_id,
            EventRegistration.status == status,
        )
        res = await self.db.execute(stmt)
        return res.scalar() or 0

    async def get_next_registration_number(self, society_id: UUID, event_id: UUID) -> str:
        stmt = select(func.count(EventRegistration.id)).where(
            EventRegistration.society_id == society_id,
            EventRegistration.event_id == event_id,
        )
        res = await self.db.execute(stmt)
        count = (res.scalar() or 0) + 1
        return f"REG-{count:05d}"


class EventApprovalRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, approval: EventApproval) -> EventApproval:
        self.db.add(approval)
        await self.db.flush()
        return approval

    async def list_by_event(self, society_id: UUID, event_id: UUID) -> list[EventApproval]:
        stmt = (
            select(EventApproval)
            .where(
                EventApproval.society_id == society_id,
                EventApproval.event_id == event_id,
            )
            .order_by(EventApproval.decided_at.desc())
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())


class EventScheduleRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, schedule: EventSchedule) -> EventSchedule:
        self.db.add(schedule)
        await self.db.flush()
        return schedule


class EventAttendanceRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, attendance: EventAttendance) -> EventAttendance:
        self.db.add(attendance)
        await self.db.flush()
        return attendance

    async def get_by_user_event(
        self, society_id: UUID, event_id: UUID, user_id: UUID
    ) -> EventAttendance | None:
        stmt = select(EventAttendance).where(
            EventAttendance.society_id == society_id,
            EventAttendance.event_id == event_id,
            EventAttendance.user_id == user_id,
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def list_by_event(self, society_id: UUID, event_id: UUID) -> list[EventAttendance]:
        stmt = select(EventAttendance).where(
            EventAttendance.society_id == society_id,
            EventAttendance.event_id == event_id,
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())


class EventAttachmentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, attachment: EventAttachment) -> EventAttachment:
        self.db.add(attachment)
        await self.db.flush()
        return attachment

    async def get_by_id(self, society_id: UUID, attachment_id: UUID) -> EventAttachment | None:
        stmt = select(EventAttachment).where(
            EventAttachment.society_id == society_id,
            EventAttachment.id == attachment_id,
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def list_by_event(self, society_id: UUID, event_id: UUID) -> list[EventAttachment]:
        stmt = select(EventAttachment).where(
            EventAttachment.society_id == society_id,
            EventAttachment.event_id == event_id,
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())


class EventStatusHistoryRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, history: EventStatusHistory) -> EventStatusHistory:
        self.db.add(history)
        await self.db.flush()
        return history

    async def list_by_event(self, society_id: UUID, event_id: UUID) -> list[EventStatusHistory]:
        stmt = (
            select(EventStatusHistory)
            .where(
                EventStatusHistory.society_id == society_id,
                EventStatusHistory.event_id == event_id,
            )
            .order_by(EventStatusHistory.changed_at.asc())
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())
