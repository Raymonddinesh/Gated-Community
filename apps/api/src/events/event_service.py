"""Phase 17 Event Core Domain Service."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.events import (
    Event,
    EventApproval,
    EventAttachment,
    EventAttendance,
    EventParticipant,
    EventRegistration,
    EventStatusHistory,
)
from apps.api.src.database.models.facility_asset import Facility
from apps.api.src.database.models.membership import ResidentDelegate
from apps.api.src.events.concurrency import (
    acquire_event_capacity_lock,
    acquire_event_number_lock,
)
from apps.api.src.events.enums import (
    EventAttendanceStatus,
    EventRegistrationStatus,
    EventStatus,
    ParticipantType,
)
from apps.api.src.events.event_hooks import EventDomainHooks
from apps.api.src.events.exceptions import (
    AttendanceNotAllowedError,
    DelegateAccessDeniedError,
    DuplicateRegistrationError,
    EventNotFoundError,
    FacilityAccessDeniedError,
    FacilityBookingConflictError,
    FacilityNotFoundError,
    InvalidEventStateError,
)
from apps.api.src.events.repositories import (
    EventApprovalRepository,
    EventAttachmentRepository,
    EventAttendanceRepository,
    EventParticipantRepository,
    EventRegistrationRepository,
    EventRepository,
    EventScheduleRepository,
    EventStatusHistoryRepository,
)
from apps.api.src.events.schemas import (
    EventAttachmentCreate,
    EventCreate,
    EventMetricsResponse,
    EventRegistrationCreate,
    EventUpdate,
)
from apps.api.src.events.state_machine import EventStateMachine
from apps.api.src.facility_booking.booking_service import FacilityBookingService
from apps.api.src.facility_booking.schemas import FacilityBookingCreate


class EventService:
    """Core domain service for Event lifecycle, registration, capacity concurrency, and facility integration."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.event_repo = EventRepository(db)
        self.participant_repo = EventParticipantRepository(db)
        self.registration_repo = EventRegistrationRepository(db)
        self.approval_repo = EventApprovalRepository(db)
        self.schedule_repo = EventScheduleRepository(db)
        self.attendance_repo = EventAttendanceRepository(db)
        self.attachment_repo = EventAttachmentRepository(db)
        self.history_repo = EventStatusHistoryRepository(db)
        self.facility_booking_service = FacilityBookingService(db)

    async def _get_event(self, society_id: UUID, event_id: UUID) -> Event:
        event = await self.event_repo.get_by_id(society_id, event_id)
        if not event:
            raise EventNotFoundError(f"Event {event_id} not found in society {society_id}")
        return event

    async def _validate_facility_association(
        self, society_id: UUID, facility_id: UUID, starts_at: datetime, ends_at: datetime
    ) -> None:
        stmt = select(Facility).where(Facility.society_id == society_id, Facility.id == facility_id)
        res = await self.db.execute(stmt)
        facility = res.scalar_one_or_none()
        if not facility:
            raise FacilityNotFoundError(f"Facility {facility_id} not found in society {society_id}")

        # Check facility booking conflict via Phase 15 booking service availability check
        config = await self.facility_booking_service.get_or_create_config(society_id, facility_id)
        if not config.is_bookable:
            raise FacilityAccessDeniedError(f"Facility {facility_id} is not configured as bookable")

    async def create_event(self, society_id: UUID, creator_id: UUID, data: EventCreate) -> Event:
        # Acquire event number advisory lock for sequential numbering
        await acquire_event_number_lock(self.db, society_id)

        if data.facility_id:
            await self._validate_facility_association(
                society_id, data.facility_id, data.starts_at, data.ends_at
            )

        event_number = await self.event_repo.get_next_event_number(society_id)

        event = Event(
            society_id=society_id,
            event_number=event_number,
            title=data.title,
            description=data.description,
            event_type=data.event_type.value,
            status=EventStatus.DRAFT.value,
            organizer_id=creator_id,
            facility_id=data.facility_id,
            capacity=data.capacity,
            registration_required=data.registration_required,
            registration_open_at=data.registration_open_at,
            registration_close_at=data.registration_close_at,
            starts_at=data.starts_at,
            ends_at=data.ends_at,
            timezone=data.timezone,
            created_by=creator_id,
        )
        created = await self.event_repo.create(event)

        # Audit status history
        history = EventStatusHistory(
            society_id=society_id,
            event_id=created.id,
            old_status="NONE",
            new_status=EventStatus.DRAFT.value,
            changed_by_user_id=creator_id,
            reason="Event draft created",
        )
        await self.history_repo.create(history)

        await EventDomainHooks.emit_event_created(society_id, created.id, created.title, creator_id)
        return created

    async def update_event(
        self, society_id: UUID, event_id: UUID, actor_id: UUID, data: EventUpdate
    ) -> Event:
        event = await self._get_event(society_id, event_id)
        if event.status in {
            EventStatus.CANCELLED.value,
            EventStatus.COMPLETED.value,
            EventStatus.REJECTED.value,
        }:
            raise InvalidEventStateError(f"Cannot update event in '{event.status}' state")

        if data.title is not None:
            event.title = data.title
        if data.description is not None:
            event.description = data.description
        if data.event_type is not None:
            event.event_type = data.event_type.value
        if data.capacity is not None:
            event.capacity = data.capacity
        if data.registration_required is not None:
            event.registration_required = data.registration_required
        if data.registration_open_at is not None:
            event.registration_open_at = data.registration_open_at
        if data.registration_close_at is not None:
            event.registration_close_at = data.registration_close_at
        if data.starts_at is not None:
            event.starts_at = data.starts_at
        if data.ends_at is not None:
            event.ends_at = data.ends_at
        if data.facility_id is not None:
            if data.facility_id:
                await self._validate_facility_association(
                    society_id, data.facility_id, event.starts_at, event.ends_at
                )
            event.facility_id = data.facility_id

        event.updated_by = actor_id
        await self.db.flush()
        return event

    async def submit_event(self, society_id: UUID, event_id: UUID, actor_id: UUID) -> Event:
        event = await self._get_event(society_id, event_id)
        EventStateMachine.validate_transition(event.status, EventStatus.PENDING_APPROVAL)

        old_status = event.status
        event.status = EventStatus.PENDING_APPROVAL.value
        event.updated_by = actor_id
        await self.db.flush()

        await self.history_repo.create(
            EventStatusHistory(
                society_id=society_id,
                event_id=event.id,
                old_status=old_status,
                new_status=EventStatus.PENDING_APPROVAL.value,
                changed_by_user_id=actor_id,
                reason="Submitted for approval",
            )
        )
        return event

    async def approve_event(
        self, society_id: UUID, event_id: UUID, approver_id: UUID, comments: str | None = None
    ) -> Event:
        event = await self._get_event(society_id, event_id)

        # Self-approval restriction check
        if event.organizer_id == approver_id:
            raise InvalidEventStateError("Event creator cannot self-approve event")

        EventStateMachine.validate_transition(event.status, EventStatus.APPROVED)

        old_status = event.status
        event.status = EventStatus.APPROVED.value
        event.updated_by = approver_id
        await self.db.flush()

        await self.approval_repo.create(
            EventApproval(
                society_id=society_id,
                event_id=event.id,
                approver_id=approver_id,
                action="APPROVED",
                comments=comments,
            )
        )
        await self.history_repo.create(
            EventStatusHistory(
                society_id=society_id,
                event_id=event.id,
                old_status=old_status,
                new_status=EventStatus.APPROVED.value,
                changed_by_user_id=approver_id,
                reason=comments or "Event approved",
            )
        )
        await EventDomainHooks.emit_event_approved(society_id, event.id, approver_id)
        return event

    async def reject_event(
        self, society_id: UUID, event_id: UUID, approver_id: UUID, comments: str | None = None
    ) -> Event:
        event = await self._get_event(society_id, event_id)
        EventStateMachine.validate_transition(event.status, EventStatus.REJECTED)

        old_status = event.status
        event.status = EventStatus.REJECTED.value
        event.updated_by = approver_id
        await self.db.flush()

        await self.approval_repo.create(
            EventApproval(
                society_id=society_id,
                event_id=event.id,
                approver_id=approver_id,
                action="REJECTED",
                comments=comments,
            )
        )
        await self.history_repo.create(
            EventStatusHistory(
                society_id=society_id,
                event_id=event.id,
                old_status=old_status,
                new_status=EventStatus.REJECTED.value,
                changed_by_user_id=approver_id,
                reason=comments or "Event rejected",
            )
        )
        return event

    async def publish_event(self, society_id: UUID, event_id: UUID, actor_id: UUID) -> Event:
        event = await self._get_event(society_id, event_id)
        target_status = EventStatus.PUBLISHED
        if event.registration_required:
            now = datetime.now(UTC)
            if event.registration_open_at and event.registration_open_at <= now:
                target_status = EventStatus.REGISTRATION_OPEN

        EventStateMachine.validate_transition(event.status, target_status)

        # If event references a facility, reserve facility using Phase 15 booking service
        if event.facility_id:
            try:
                await self.facility_booking_service.create_booking(
                    society_id,
                    actor_id,
                    FacilityBookingCreate(
                        facility_id=event.facility_id,
                        title=f"Event: {event.title}",
                        description=f"Auto-reservation for Event {event.event_number}",
                        start_at=event.starts_at,
                        end_at=event.ends_at,
                    ),
                )
            except Exception as e:
                # Catch booking conflict or error
                raise FacilityBookingConflictError(f"Could not reserve facility: {e}") from e

        old_status = event.status
        event.status = target_status.value
        event.published_at = datetime.now(UTC)
        event.updated_by = actor_id
        await self.db.flush()

        await self.history_repo.create(
            EventStatusHistory(
                society_id=society_id,
                event_id=event.id,
                old_status=old_status,
                new_status=target_status.value,
                changed_by_user_id=actor_id,
                reason="Event published",
            )
        )
        await EventDomainHooks.emit_event_published(society_id, event.id, event.title)
        if target_status == EventStatus.REGISTRATION_OPEN:
            await EventDomainHooks.emit_registration_opened(society_id, event.id)
        return event

    async def cancel_event(self, society_id: UUID, event_id: UUID, actor_id: UUID, reason: str) -> Event:
        event = await self._get_event(society_id, event_id)
        EventStateMachine.validate_transition(event.status, EventStatus.CANCELLED)

        old_status = event.status
        event.status = EventStatus.CANCELLED.value
        event.cancellation_reason = reason
        event.updated_by = actor_id
        await self.db.flush()

        await self.history_repo.create(
            EventStatusHistory(
                society_id=society_id,
                event_id=event.id,
                old_status=old_status,
                new_status=EventStatus.CANCELLED.value,
                changed_by_user_id=actor_id,
                reason=reason,
            )
        )
        await EventDomainHooks.emit_event_cancelled(society_id, event.id, reason)
        return event

    # ---------------------------------------------------------------------------
    # Participant Registration & Capacity Concurrency
    # ---------------------------------------------------------------------------

    async def register_participant(
        self, society_id: UUID, event_id: UUID, user_id: UUID, data: EventRegistrationCreate
    ) -> EventRegistration:
        # Acquire capacity lock transactionally
        await acquire_event_capacity_lock(self.db, event_id)

        event = await self._get_event(society_id, event_id)

        if event.status in {
            EventStatus.CANCELLED.value,
            EventStatus.COMPLETED.value,
            EventStatus.REJECTED.value,
            EventStatus.DRAFT.value,
        }:
            raise InvalidEventStateError(f"Cannot register for event in '{event.status}' state")

        # Check existing registration
        existing = await self.registration_repo.get_by_user_event(society_id, event_id, user_id)
        if existing and existing.status in {
            EventRegistrationStatus.REGISTERED.value,
            EventRegistrationStatus.CONFIRMED.value,
            EventRegistrationStatus.WAITLISTED.value,
        }:
            raise DuplicateRegistrationError(f"User {user_id} is already registered for event {event_id}")

        # Delegate validation if registering as delegate
        if data.participant_type == ParticipantType.AUTHORIZED_DELEGATE:
            stmt = select(ResidentDelegate).where(
                ResidentDelegate.society_id == society_id,
                ResidentDelegate.delegate_user_id == user_id,
                ResidentDelegate.status == "ACTIVE",
            )
            res = await self.db.execute(stmt)
            delegate = res.scalar_one_or_none()
            if not delegate:
                raise DelegateAccessDeniedError("Active resident delegation record not found")

        # Determine registration status based on capacity
        confirmed_count = await self.registration_repo.count_by_status(
            society_id, event_id, EventRegistrationStatus.CONFIRMED.value
        )
        # also count REGISTERED
        registered_count = await self.registration_repo.count_by_status(
            society_id, event_id, EventRegistrationStatus.REGISTERED.value
        )
        active_count = confirmed_count + registered_count

        reg_status = EventRegistrationStatus.CONFIRMED.value
        waitlist_pos = None

        if event.capacity is not None and event.capacity > 0:
            if active_count >= event.capacity:
                reg_status = EventRegistrationStatus.WAITLISTED.value
                waitlist_count = await self.registration_repo.count_by_status(
                    society_id, event_id, EventRegistrationStatus.WAITLISTED.value
                )
                waitlist_pos = waitlist_count + 1

        reg_number = await self.registration_repo.get_next_registration_number(society_id, event_id)

        registration = EventRegistration(
            society_id=society_id,
            event_id=event_id,
            user_id=user_id,
            registration_number=reg_number,
            status=reg_status,
            waitlist_position=waitlist_pos,
            confirmed_at=datetime.now(UTC) if reg_status == EventRegistrationStatus.CONFIRMED.value else None,
        )
        saved_reg = await self.registration_repo.create(registration)

        # Create Participant record
        participant = EventParticipant(
            society_id=society_id,
            event_id=event_id,
            user_id=user_id,
            participant_type=data.participant_type.value,
            unit_id=data.unit_id,
        )
        await self.participant_repo.create(participant)

        if reg_status == EventRegistrationStatus.CONFIRMED.value:
            await EventDomainHooks.emit_registration_confirmed(society_id, event_id, user_id, reg_number)

        return saved_reg

    async def cancel_registration(
        self, society_id: UUID, event_id: UUID, user_id: UUID, reason: str | None = None
    ) -> EventRegistration:
        await acquire_event_capacity_lock(self.db, event_id)

        reg = await self.registration_repo.get_by_user_event(society_id, event_id, user_id)
        if not reg or reg.status == EventRegistrationStatus.CANCELLED.value:
            raise EventNotFoundError("Active registration not found")

        old_status = reg.status
        reg.status = EventRegistrationStatus.CANCELLED.value
        reg.cancelled_at = datetime.now(UTC)
        reg.cancellation_reason = reason
        await self.db.flush()

        # Promote waitlist if a confirmed registration was cancelled
        if old_status in {EventRegistrationStatus.CONFIRMED.value, EventRegistrationStatus.REGISTERED.value}:
            waitlisted = await self.registration_repo.list_by_event(
                society_id, event_id, status=EventRegistrationStatus.WAITLISTED.value, limit=1
            )
            if waitlisted:
                next_reg = waitlisted[0]
                next_reg.status = EventRegistrationStatus.CONFIRMED.value
                next_reg.confirmed_at = datetime.now(UTC)
                next_reg.waitlist_position = None
                await self.db.flush()
                await EventDomainHooks.emit_registration_confirmed(
                    society_id, event_id, next_reg.user_id, next_reg.registration_number
                )

        await EventDomainHooks.emit_registration_cancelled(society_id, event_id, user_id)
        return reg

    # ---------------------------------------------------------------------------
    # Attendance Tracking
    # ---------------------------------------------------------------------------

    async def record_attendance(
        self,
        society_id: UUID,
        event_id: UUID,
        user_id: UUID,
        recorder_id: UUID,
        status: EventAttendanceStatus,
        notes: str | None = None,
    ) -> EventAttendance:
        event = await self._get_event(society_id, event_id)
        if event.status in {EventStatus.CANCELLED.value, EventStatus.REJECTED.value, EventStatus.DRAFT.value}:
            raise AttendanceNotAllowedError(
                f"Attendance cannot be recorded for event in '{event.status}' state"
            )

        reg = await self.registration_repo.get_by_user_event(society_id, event_id, user_id)
        if not reg:
            raise EventNotFoundError(f"Registration for user {user_id} not found")

        existing_att = await self.attendance_repo.get_by_user_event(society_id, event_id, user_id)
        if existing_att:
            existing_att.status = status.value
            existing_att.notes = notes
            existing_att.check_in_time = (
                datetime.now(UTC)
                if status in {EventAttendanceStatus.CHECKED_IN, EventAttendanceStatus.ATTENDED}
                else existing_att.check_in_time
            )
            await self.db.flush()
            return existing_att

        attendance = EventAttendance(
            society_id=society_id,
            event_id=event_id,
            registration_id=reg.id,
            user_id=user_id,
            status=status.value,
            check_in_time=datetime.now(UTC)
            if status in {EventAttendanceStatus.CHECKED_IN, EventAttendanceStatus.ATTENDED}
            else None,
            recorded_by=recorder_id,
            notes=notes,
        )
        return await self.attendance_repo.create(attendance)

    # ---------------------------------------------------------------------------
    # Attachment Security
    # ---------------------------------------------------------------------------

    async def add_attachment(
        self, society_id: UUID, event_id: UUID, uploader_id: UUID, data: EventAttachmentCreate
    ) -> EventAttachment:
        await self._get_event(society_id, event_id)

        # Path traversal prevention on storage key
        safe_name = data.file_name.replace("..", "").replace("/", "").replace("\\", "")
        storage_key = f"events/{society_id}/{event_id}/{data.file_size}_{safe_name}"

        attachment = EventAttachment(
            society_id=society_id,
            event_id=event_id,
            file_name=safe_name,
            file_size=data.file_size,
            mime_type=data.mime_type,
            storage_object_key=storage_key,
            uploaded_by=uploader_id,
        )
        return await self.attachment_repo.create(attachment)

    # ---------------------------------------------------------------------------
    # Metrics
    # ---------------------------------------------------------------------------

    async def get_event_metrics(self, society_id: UUID, event_id: UUID) -> EventMetricsResponse:
        event = await self._get_event(society_id, event_id)
        confirmed = await self.registration_repo.count_by_status(
            society_id, event_id, EventRegistrationStatus.CONFIRMED.value
        )
        registered = await self.registration_repo.count_by_status(
            society_id, event_id, EventRegistrationStatus.REGISTERED.value
        )
        waitlisted = await self.registration_repo.count_by_status(
            society_id, event_id, EventRegistrationStatus.WAITLISTED.value
        )
        cancelled = await self.registration_repo.count_by_status(
            society_id, event_id, EventRegistrationStatus.CANCELLED.value
        )
        attended = await self.registration_repo.count_by_status(
            society_id, event_id, EventRegistrationStatus.ATTENDED.value
        )
        no_show = await self.registration_repo.count_by_status(
            society_id, event_id, EventRegistrationStatus.NO_SHOW.value
        )

        return EventMetricsResponse(
            total_registered=confirmed + registered + waitlisted + attended + no_show,
            confirmed=confirmed + registered,
            waitlisted=waitlisted,
            cancelled=cancelled,
            attended=attended,
            no_show=no_show,
            capacity=event.capacity,
        )
