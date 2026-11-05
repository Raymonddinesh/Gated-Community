"""Phase 15 Facility Booking Domain Service."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.facility_asset import Facility
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
from apps.api.src.facility_booking.concurrency import (
    acquire_booking_code_lock,
    acquire_facility_slot_lock,
)
from apps.api.src.facility_booking.enums import BlackoutStatus, BookingApprovalDecision, BookingStatus
from apps.api.src.facility_booking.event_hooks import FacilityBookingEventHooks
from apps.api.src.facility_booking.exceptions import (
    AdvanceBookingWindowExceededError,
    BookingCapacityExceededError,
    BookingDurationViolationError,
    BookingNotFoundError,
    BookingSlotConflictError,
    CancellationNoticePeriodViolationError,
    FacilityBlackoutConflictError,
    FacilityNotBookableError,
    FacilityNotFoundError,
    OutsideOperatingHoursError,
)
from apps.api.src.facility_booking.repositories import (
    FacilityAvailabilityWindowRepository,
    FacilityBlackoutPeriodRepository,
    FacilityBookingApprovalRepository,
    FacilityBookingCancellationRepository,
    FacilityBookingConfigRepository,
    FacilityBookingParticipantRepository,
    FacilityBookingRepository,
    FacilityBookingStatusHistoryRepository,
)
from apps.api.src.facility_booking.schemas import (
    FacilityAvailabilityWindowCreate,
    FacilityBlackoutPeriodCreate,
    FacilityBookingConfigCreate,
    FacilityBookingConfigUpdate,
    FacilityBookingCreate,
)
from apps.api.src.facility_booking.state_machine import FacilityBookingStateMachine


class FacilityBookingService:
    """Core domain service for facility booking lifecycle and availability."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.config_repo = FacilityBookingConfigRepository(db)
        self.window_repo = FacilityAvailabilityWindowRepository(db)
        self.blackout_repo = FacilityBlackoutPeriodRepository(db)
        self.booking_repo = FacilityBookingRepository(db)
        self.participant_repo = FacilityBookingParticipantRepository(db)
        self.approval_repo = FacilityBookingApprovalRepository(db)
        self.cancellation_repo = FacilityBookingCancellationRepository(db)
        self.history_repo = FacilityBookingStatusHistoryRepository(db)

    # ---------------------------------------------------------------------------
    # Facility Lookup & Config Management
    # ---------------------------------------------------------------------------

    async def _get_facility(self, society_id: UUID, facility_id: UUID) -> Facility:
        stmt = select(Facility).where(
            Facility.society_id == society_id,
            Facility.id == facility_id,
        )
        res = await self.db.execute(stmt)
        facility = res.scalar_one_or_none()
        if not facility:
            raise FacilityNotFoundError(f"Facility {facility_id} not found in society {society_id}")
        return facility

    async def get_or_create_config(self, society_id: UUID, facility_id: UUID) -> FacilityBookingConfig:
        await self._get_facility(society_id, facility_id)
        config = await self.config_repo.get_by_facility_id(society_id, facility_id)
        if not config:
            config = FacilityBookingConfig(
                society_id=society_id,
                facility_id=facility_id,
                is_bookable=True,
                requires_approval=False,
                max_capacity=None,
                min_duration_minutes=30,
                max_duration_minutes=480,
                advance_booking_days=30,
                min_cancellation_notice_hours=24,
                buffer_before_minutes=0,
                buffer_after_minutes=0,
                allow_recurring=False,
                allow_delegate_booking=True,
                admin_override_enabled=True,
            )
            config = await self.config_repo.upsert(config)
        return config

    async def upsert_config(
        self,
        society_id: UUID,
        facility_id: UUID,
        payload: FacilityBookingConfigCreate | FacilityBookingConfigUpdate,
    ) -> FacilityBookingConfig:
        config = await self.get_or_create_config(society_id, facility_id)
        update_data = payload.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if value is not None:
                setattr(config, field, value)
        return await self.config_repo.upsert(config)

    # ---------------------------------------------------------------------------
    # Availability Windows Management
    # ---------------------------------------------------------------------------

    async def set_availability_windows(
        self,
        society_id: UUID,
        facility_id: UUID,
        windows_data: list[FacilityAvailabilityWindowCreate],
    ) -> list[FacilityAvailabilityWindow]:
        await self._get_facility(society_id, facility_id)
        models = [
            FacilityAvailabilityWindow(
                society_id=society_id,
                facility_id=facility_id,
                day_of_week=w.day_of_week,
                start_time=w.start_time,
                end_time=w.end_time,
                is_active=w.is_active,
            )
            for w in windows_data
        ]
        return await self.window_repo.replace_windows(society_id, facility_id, models)

    async def get_availability_windows(
        self, society_id: UUID, facility_id: UUID
    ) -> list[FacilityAvailabilityWindow]:
        await self._get_facility(society_id, facility_id)
        return await self.window_repo.get_by_facility_id(society_id, facility_id)

    # ---------------------------------------------------------------------------
    # Blackout Period Management
    # ---------------------------------------------------------------------------

    async def create_blackout(
        self,
        society_id: UUID,
        facility_id: UUID,
        user_id: UUID,
        payload: FacilityBlackoutPeriodCreate,
    ) -> FacilityBlackoutPeriod:
        await self._get_facility(society_id, facility_id)
        blackout = FacilityBlackoutPeriod(
            society_id=society_id,
            facility_id=facility_id,
            title=payload.title,
            start_at=payload.start_at,
            end_at=payload.end_at,
            reason=payload.reason,
            status=BlackoutStatus.SCHEDULED.value,
            created_by_user_id=user_id,
        )
        return await self.blackout_repo.create(blackout)

    async def cancel_blackout(
        self, society_id: UUID, facility_id: UUID, blackout_id: UUID
    ) -> FacilityBlackoutPeriod:
        blackout = await self.blackout_repo.get_by_id(society_id, blackout_id)
        if not blackout or blackout.facility_id != facility_id:
            raise BookingNotFoundError(f"Blackout period {blackout_id} not found")
        blackout.status = BlackoutStatus.CANCELLED.value
        await self.db.flush()
        return blackout

    async def list_blackouts(
        self, society_id: UUID, facility_id: UUID, status: BlackoutStatus | None = None
    ) -> list[FacilityBlackoutPeriod]:
        await self._get_facility(society_id, facility_id)
        return await self.blackout_repo.list_by_facility(society_id, facility_id, status)

    # ---------------------------------------------------------------------------
    # Booking Code Generator
    # ---------------------------------------------------------------------------

    async def _generate_booking_code(self, society_id: UUID, created_at: datetime) -> str:
        await acquire_booking_code_lock(self.db, society_id)
        year = created_at.year
        count = await self.booking_repo.count_year_bookings(society_id, year)
        seq = count + 1
        return f"BK-{year}-{seq:06d}"

    # ---------------------------------------------------------------------------
    # Booking Validation Helpers
    # ---------------------------------------------------------------------------

    async def _validate_booking_request(
        self,
        society_id: UUID,
        facility: Facility,
        config: FacilityBookingConfig,
        payload: FacilityBookingCreate,
    ):
        now = datetime.now(UTC)

        # Ensure tz awareness consistency if incoming datetimes are naive
        start_at = payload.start_at
        end_at = payload.end_at
        if start_at.tzinfo is None:
            start_at = start_at.replace(tzinfo=UTC)
        if end_at.tzinfo is None:
            end_at = end_at.replace(tzinfo=UTC)

        # 1. Facility & Config bookability
        if not config.is_bookable:
            raise FacilityNotBookableError(f"Facility '{facility.name}' is currently not open for bookings")

        # 2. Advance booking window
        days_ahead = (start_at - now).total_seconds() / 86400
        if days_ahead > config.advance_booking_days:
            raise AdvanceBookingWindowExceededError(
                f"Booking date exceeds maximum advance booking window of {config.advance_booking_days} days"
            )

        # 3. Duration rules
        duration_minutes = (end_at - start_at).total_seconds() / 60
        if duration_minutes < config.min_duration_minutes or duration_minutes > config.max_duration_minutes:
            raise BookingDurationViolationError(
                f"Booking duration ({duration_minutes:.0f} mins) must be between "
                f"{config.min_duration_minutes} and {config.max_duration_minutes} minutes"
            )

        # 4. Capacity rules
        effective_capacity = config.max_capacity or facility.capacity
        if effective_capacity and payload.participant_count > effective_capacity:
            raise BookingCapacityExceededError(
                f"Requested capacity ({payload.participant_count}) exceeds max allowed ({effective_capacity})"
            )

        # 5. Availability Windows
        windows = await self.window_repo.get_by_facility_id(society_id, facility.id)
        if windows:
            # day_of_week: 0=Monday ... 6=Sunday
            day_of_week = start_at.weekday()
            day_windows = [w for w in windows if w.day_of_week == day_of_week]
            if not day_windows:
                raise OutsideOperatingHoursError(f"Facility is closed on day {day_of_week}")

            start_time_str = start_at.strftime("%H:%M")
            end_time_str = end_at.strftime("%H:%M")
            valid_slot = any(
                w.start_time <= start_time_str and w.end_time >= end_time_str for w in day_windows
            )
            if not valid_slot:
                raise OutsideOperatingHoursError(
                    f"Requested slot ({start_time_str}-{end_time_str}) is outside facility operating hours"
                )

        # 6. Blackout Periods
        blackouts = await self.blackout_repo.check_blackout_overlap(society_id, facility.id, start_at, end_at)
        if blackouts:
            raise FacilityBlackoutConflictError(
                f"Requested time slot conflicts with blackout period: '{blackouts[0].title}'"
            )

    # ---------------------------------------------------------------------------
    # Booking Lifecycle
    # ---------------------------------------------------------------------------

    async def create_booking(
        self,
        society_id: UUID,
        user_id: UUID,
        payload: FacilityBookingCreate,
    ) -> FacilityBooking:
        # Idempotency check
        if payload.idempotency_key:
            existing = await self.booking_repo.get_by_idempotency_key(society_id, payload.idempotency_key)
            if existing:
                return existing

        facility = await self._get_facility(society_id, payload.facility_id)
        config = await self.get_or_create_config(society_id, payload.facility_id)

        # Acquire transaction-level lock on facility_id to eliminate double booking race conditions
        await acquire_facility_slot_lock(self.db, payload.facility_id)

        # Perform domain validations
        await self._validate_booking_request(society_id, facility, config, payload)

        # Check existing overlapping active reservations
        overlapping = await self.booking_repo.check_overlapping_active_bookings(
            society_id, payload.facility_id, payload.start_at, payload.end_at
        )
        if overlapping:
            raise BookingSlotConflictError(
                f"Requested slot overlaps with existing active booking '{overlapping[0].booking_code}'"
            )

        now = datetime.now(UTC)
        booking_code = await self._generate_booking_code(society_id, now)

        initial_status = (
            BookingStatus.PENDING_APPROVAL if config.requires_approval else BookingStatus.APPROVED
        )

        booking = FacilityBooking(
            society_id=society_id,
            facility_id=payload.facility_id,
            facility_area_id=payload.facility_area_id,
            booking_code=booking_code,
            title=payload.title,
            description=payload.description,
            user_id=user_id,
            delegate_user_id=payload.delegate_user_id,
            start_at=payload.start_at,
            end_at=payload.end_at,
            status=initial_status.value,
            participant_count=payload.participant_count,
            idempotency_key=payload.idempotency_key,
        )
        booking = await self.booking_repo.create(booking)

        # Add participants if provided
        if payload.participants:
            participant_models = [
                FacilityBookingParticipant(
                    society_id=society_id,
                    booking_id=booking.id,
                    name=p.name,
                    contact_phone=p.contact_phone,
                    role_or_type=p.role_or_type.value if p.role_or_type else None,
                )
                for p in payload.participants
            ]
            await self.participant_repo.create_many(participant_models)

        # Add initial status history log
        history = FacilityBookingStatusHistory(
            society_id=society_id,
            booking_id=booking.id,
            old_status="",
            new_status=initial_status.value,
            changed_by_user_id=user_id,
            reason="Initial booking creation",
        )
        await self.history_repo.create(history)

        # Emit event hook
        FacilityBookingEventHooks.on_booking_created(
            booking_id=booking.id,
            society_id=society_id,
            facility_id=booking.facility_id,
            user_id=user_id,
            booking_code=booking_code,
            status=initial_status.value,
        )

        # Re-fetch with relationships loaded
        return await self.booking_repo.get_by_id(society_id, booking.id)  # type: ignore[return-value]

    async def approve_booking(
        self,
        society_id: UUID,
        booking_id: UUID,
        approver_user_id: UUID,
        decision: BookingApprovalDecision,
        reason: str | None = None,
    ) -> FacilityBooking:
        booking = await self.booking_repo.get_by_id(society_id, booking_id)
        if not booking:
            raise BookingNotFoundError(f"Booking {booking_id} not found")

        target_status = (
            BookingStatus.APPROVED if decision == BookingApprovalDecision.APPROVED else BookingStatus.REJECTED
        )

        old_status = BookingStatus(booking.status)
        FacilityBookingStateMachine.validate_transition(old_status, target_status)

        approval = FacilityBookingApproval(
            society_id=society_id,
            booking_id=booking.id,
            approver_user_id=approver_user_id,
            decision=decision.value,
            reason=reason,
        )
        await self.approval_repo.create(approval)

        booking.status = target_status.value
        await self.db.flush()

        history = FacilityBookingStatusHistory(
            society_id=society_id,
            booking_id=booking.id,
            old_status=old_status.value,
            new_status=target_status.value,
            changed_by_user_id=approver_user_id,
            reason=reason or f"Approval decision: {decision.value}",
        )
        await self.history_repo.create(history)

        if target_status == BookingStatus.APPROVED:
            FacilityBookingEventHooks.on_booking_approved(
                booking_id=booking.id,
                society_id=society_id,
                user_id=booking.user_id,
                booking_code=booking.booking_code,
            )
        else:
            FacilityBookingEventHooks.on_booking_rejected(
                booking_id=booking.id,
                society_id=society_id,
                user_id=booking.user_id,
                booking_code=booking.booking_code,
                reason=reason,
            )

        return await self.booking_repo.get_by_id(society_id, booking.id)  # type: ignore[return-value]

    async def cancel_booking(
        self,
        society_id: UUID,
        booking_id: UUID,
        cancelled_by_user_id: UUID,
        reason: str | None = None,
        admin_override: bool = False,
    ) -> FacilityBooking:
        booking = await self.booking_repo.get_by_id(society_id, booking_id)
        if not booking:
            raise BookingNotFoundError(f"Booking {booking_id} not found")

        old_status = BookingStatus(booking.status)
        FacilityBookingStateMachine.validate_transition(old_status, BookingStatus.CANCELLED)

        config = await self.get_or_create_config(society_id, booking.facility_id)

        now = datetime.now(UTC)
        start_at = booking.start_at
        if start_at.tzinfo is None:
            start_at = start_at.replace(tzinfo=UTC)

        hours_until_start = (start_at - now).total_seconds() / 3600
        is_within_notice_period = hours_until_start >= config.min_cancellation_notice_hours

        if not is_within_notice_period and not admin_override:
            raise CancellationNoticePeriodViolationError(
                f"Cancellation requires at least {config.min_cancellation_notice_hours} hours notice. "
                f"Remaining notice: {hours_until_start:.1f} hours"
            )

        cancellation = FacilityBookingCancellation(
            society_id=society_id,
            booking_id=booking.id,
            cancelled_by_user_id=cancelled_by_user_id,
            cancellation_reason=reason,
            is_within_notice_period=is_within_notice_period,
        )
        await self.cancellation_repo.create(cancellation)

        booking.status = BookingStatus.CANCELLED.value
        await self.db.flush()

        history = FacilityBookingStatusHistory(
            society_id=society_id,
            booking_id=booking.id,
            old_status=old_status.value,
            new_status=BookingStatus.CANCELLED.value,
            changed_by_user_id=cancelled_by_user_id,
            reason=reason or "Booking cancelled",
        )
        await self.history_repo.create(history)

        FacilityBookingEventHooks.on_booking_cancelled(
            booking_id=booking.id,
            society_id=society_id,
            user_id=booking.user_id,
            booking_code=booking.booking_code,
            reason=reason,
        )

        return await self.booking_repo.get_by_id(society_id, booking.id)  # type: ignore[return-value]

    async def update_booking_status(
        self,
        society_id: UUID,
        booking_id: UUID,
        changed_by_user_id: UUID,
        target_status: BookingStatus,
        reason: str | None = None,
    ) -> FacilityBooking:
        booking = await self.booking_repo.get_by_id(society_id, booking_id)
        if not booking:
            raise BookingNotFoundError(f"Booking {booking_id} not found")

        old_status = BookingStatus(booking.status)
        FacilityBookingStateMachine.validate_transition(old_status, target_status)

        booking.status = target_status.value
        await self.db.flush()

        history = FacilityBookingStatusHistory(
            society_id=society_id,
            booking_id=booking.id,
            old_status=old_status.value,
            new_status=target_status.value,
            changed_by_user_id=changed_by_user_id,
            reason=reason,
        )
        await self.history_repo.create(history)

        if target_status == BookingStatus.CHECKED_IN:
            FacilityBookingEventHooks.on_booking_checked_in(booking.id, society_id, booking.booking_code)
        elif target_status == BookingStatus.COMPLETED:
            FacilityBookingEventHooks.on_booking_completed(booking.id, society_id, booking.booking_code)
        elif target_status == BookingStatus.NO_SHOW:
            FacilityBookingEventHooks.on_booking_no_show(booking.id, society_id, booking.booking_code)

        return await self.booking_repo.get_by_id(society_id, booking.id)  # type: ignore[return-value]

    # ---------------------------------------------------------------------------
    # Queries & Reports
    # ---------------------------------------------------------------------------

    async def get_booking(self, society_id: UUID, booking_id: UUID) -> FacilityBooking:
        booking = await self.booking_repo.get_by_id(society_id, booking_id)
        if not booking:
            raise BookingNotFoundError(f"Booking {booking_id} not found")
        return booking

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
        return await self.booking_repo.list_bookings(
            society_id=society_id,
            facility_id=facility_id,
            user_id=user_id,
            status=status,
            start_date=start_date,
            end_date=end_date,
            page=page,
            size=size,
        )

    async def get_status_history(
        self, society_id: UUID, booking_id: UUID
    ) -> list[FacilityBookingStatusHistory]:
        await self.get_booking(society_id, booking_id)
        return await self.history_repo.list_by_booking(society_id, booking_id)
