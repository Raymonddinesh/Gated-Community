"""Phase 15 Facility Booking Repositories."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.src.database.models.facility_booking import (
    FacilityAvailabilityWindow,
    FacilityBlackoutPeriod,
    FacilityBooking,
    FacilityBookingApproval,
    FacilityBookingCancellation,
    FacilityBookingConfig,
    FacilityBookingParticipant,
    FacilityBookingStatusHistory,
)
from apps.api.src.facility_booking.enums import BlackoutStatus, BookingStatus
from apps.api.src.facility_booking.state_machine import ACTIVE_RESERVATION_STATES


class FacilityBookingConfigRepository:
    """Repository for Facility Booking Configuration."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_facility_id(self, society_id: UUID, facility_id: UUID) -> FacilityBookingConfig | None:
        stmt = select(FacilityBookingConfig).where(
            FacilityBookingConfig.society_id == society_id,
            FacilityBookingConfig.facility_id == facility_id,
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def upsert(self, config: FacilityBookingConfig) -> FacilityBookingConfig:
        self.db.add(config)
        await self.db.flush()
        return config


class FacilityAvailabilityWindowRepository:
    """Repository for Facility Availability Windows."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_facility_id(
        self, society_id: UUID, facility_id: UUID
    ) -> list[FacilityAvailabilityWindow]:
        stmt = (
            select(FacilityAvailabilityWindow)
            .where(
                FacilityAvailabilityWindow.society_id == society_id,
                FacilityAvailabilityWindow.facility_id == facility_id,
                FacilityAvailabilityWindow.is_active == True,  # noqa: E712
            )
            .order_by(FacilityAvailabilityWindow.day_of_week)
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def replace_windows(
        self, society_id: UUID, facility_id: UUID, windows: list[FacilityAvailabilityWindow]
    ) -> list[FacilityAvailabilityWindow]:
        # Delete existing windows
        existing = await self.get_by_facility_id(society_id, facility_id)
        for w in existing:
            await self.db.delete(w)
        await self.db.flush()

        for w in windows:
            self.db.add(w)
        await self.db.flush()
        return windows


class FacilityBlackoutPeriodRepository:
    """Repository for Facility Blackout Periods."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, blackout: FacilityBlackoutPeriod) -> FacilityBlackoutPeriod:
        self.db.add(blackout)
        await self.db.flush()
        return blackout

    async def get_by_id(self, society_id: UUID, blackout_id: UUID) -> FacilityBlackoutPeriod | None:
        stmt = select(FacilityBlackoutPeriod).where(
            FacilityBlackoutPeriod.society_id == society_id,
            FacilityBlackoutPeriod.id == blackout_id,
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def list_by_facility(
        self, society_id: UUID, facility_id: UUID, status: BlackoutStatus | None = None
    ) -> list[FacilityBlackoutPeriod]:
        filters = [
            FacilityBlackoutPeriod.society_id == society_id,
            FacilityBlackoutPeriod.facility_id == facility_id,
        ]
        if status:
            filters.append(FacilityBlackoutPeriod.status == status.value)
        stmt = select(FacilityBlackoutPeriod).where(*filters).order_by(FacilityBlackoutPeriod.start_at.desc())
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def check_blackout_overlap(
        self, society_id: UUID, facility_id: UUID, start_at: datetime, end_at: datetime
    ) -> list[FacilityBlackoutPeriod]:
        """Find active blackouts overlapping [start_at, end_at)."""
        stmt = select(FacilityBlackoutPeriod).where(
            FacilityBlackoutPeriod.society_id == society_id,
            FacilityBlackoutPeriod.facility_id == facility_id,
            FacilityBlackoutPeriod.status.in_([BlackoutStatus.SCHEDULED.value, BlackoutStatus.ACTIVE.value]),
            # Overlap logic: start_at < blackout.end_at AND end_at > blackout.start_at
            FacilityBlackoutPeriod.start_at < end_at,
            FacilityBlackoutPeriod.end_at > start_at,
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())


class FacilityBookingRepository:
    """Repository for Facility Bookings."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, booking: FacilityBooking) -> FacilityBooking:
        self.db.add(booking)
        await self.db.flush()
        return booking

    async def get_by_id(self, society_id: UUID, booking_id: UUID) -> FacilityBooking | None:
        stmt = (
            select(FacilityBooking)
            .options(
                selectinload(FacilityBooking.participants),
                selectinload(FacilityBooking.approvals),
                selectinload(FacilityBooking.cancellations),
            )
            .where(
                FacilityBooking.society_id == society_id,
                FacilityBooking.id == booking_id,
            )
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_idempotency_key(self, society_id: UUID, idempotency_key: str) -> FacilityBooking | None:
        stmt = (
            select(FacilityBooking)
            .options(
                selectinload(FacilityBooking.participants),
                selectinload(FacilityBooking.approvals),
                selectinload(FacilityBooking.cancellations),
            )
            .where(
                FacilityBooking.society_id == society_id,
                FacilityBooking.idempotency_key == idempotency_key,
            )
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def check_overlapping_active_bookings(
        self,
        society_id: UUID,
        facility_id: UUID,
        start_at: datetime,
        end_at: datetime,
        exclude_booking_id: UUID | None = None,
    ) -> list[FacilityBooking]:
        active_statuses = [s.value for s in ACTIVE_RESERVATION_STATES]
        filters = [
            FacilityBooking.society_id == society_id,
            FacilityBooking.facility_id == facility_id,
            FacilityBooking.status.in_(active_statuses),
            FacilityBooking.start_at < end_at,
            FacilityBooking.end_at > start_at,
        ]
        if exclude_booking_id:
            filters.append(FacilityBooking.id != exclude_booking_id)

        stmt = select(FacilityBooking).where(*filters)
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def list_bookings(
        self,
        society_id: UUID,
        facility_id: UUID | None = None,
        user_id: UUID | None = None,
        status: BookingStatus | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[FacilityBooking], int]:
        filters = [FacilityBooking.society_id == society_id]
        if facility_id:
            filters.append(FacilityBooking.facility_id == facility_id)
        if user_id:
            filters.append(
                or_(
                    FacilityBooking.user_id == user_id,
                    FacilityBooking.delegate_user_id == user_id,
                )
            )
        if status:
            filters.append(FacilityBooking.status == status.value)
        if start_date:
            filters.append(FacilityBooking.start_at >= start_date)
        if end_date:
            filters.append(FacilityBooking.end_at <= end_date)

        count_stmt = select(func.count()).select_from(FacilityBooking).where(*filters)
        total_res = await self.db.execute(count_stmt)
        total = total_res.scalar_one()

        offset = (page - 1) * size
        stmt = (
            select(FacilityBooking)
            .options(
                selectinload(FacilityBooking.participants),
                selectinload(FacilityBooking.approvals),
                selectinload(FacilityBooking.cancellations),
            )
            .where(*filters)
            .order_by(FacilityBooking.created_at.desc())
            .offset(offset)
            .limit(size)
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all()), total

    async def count_year_bookings(self, society_id: UUID, year: int) -> int:
        start_of_year = datetime(year, 1, 1)
        end_of_year = datetime(year, 12, 31, 23, 59, 59)
        stmt = (
            select(func.count())
            .select_from(FacilityBooking)
            .where(
                FacilityBooking.society_id == society_id,
                FacilityBooking.created_at >= start_of_year,
                FacilityBooking.created_at <= end_of_year,
            )
        )
        res = await self.db.execute(stmt)
        return res.scalar_one()


class FacilityBookingParticipantRepository:
    """Repository for Facility Booking Participants."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_many(
        self, participants: list[FacilityBookingParticipant]
    ) -> list[FacilityBookingParticipant]:
        for p in participants:
            self.db.add(p)
        await self.db.flush()
        return participants


class FacilityBookingApprovalRepository:
    """Repository for Facility Booking Approvals."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, approval: FacilityBookingApproval) -> FacilityBookingApproval:
        self.db.add(approval)
        await self.db.flush()
        return approval


class FacilityBookingCancellationRepository:
    """Repository for Facility Booking Cancellations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, cancellation: FacilityBookingCancellation) -> FacilityBookingCancellation:
        self.db.add(cancellation)
        await self.db.flush()
        return cancellation


class FacilityBookingStatusHistoryRepository:
    """Repository for Facility Booking Status History."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, history: FacilityBookingStatusHistory) -> FacilityBookingStatusHistory:
        self.db.add(history)
        await self.db.flush()
        return history

    async def list_by_booking(self, society_id: UUID, booking_id: UUID) -> list[FacilityBookingStatusHistory]:
        stmt = (
            select(FacilityBookingStatusHistory)
            .where(
                FacilityBookingStatusHistory.society_id == society_id,
                FacilityBookingStatusHistory.booking_id == booking_id,
            )
            .order_by(FacilityBookingStatusHistory.changed_at.asc())
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())
