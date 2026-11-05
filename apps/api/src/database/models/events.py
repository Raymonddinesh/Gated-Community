"""Phase 17 Events & Community Management Database Models."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.src.database.base import Base


class Event(Base):
    """Event Core Entity."""

    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    event_number: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)  # EventType enum
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT")  # EventStatus enum
    organizer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    facility_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="SET NULL"), nullable=True
    )
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None or > 0
    registration_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    registration_open_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    registration_close_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="Asia/Kolkata")
    cancellation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )

    # Relationships
    society = relationship("Society")
    organizer = relationship("User", foreign_keys=[organizer_id])
    facility = relationship("Facility")
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])

    participants = relationship("EventParticipant", back_populates="event", cascade="all, delete-orphan")
    registrations = relationship("EventRegistration", back_populates="event", cascade="all, delete-orphan")
    approvals = relationship("EventApproval", back_populates="event", cascade="all, delete-orphan")
    schedules = relationship("EventSchedule", back_populates="event", cascade="all, delete-orphan")
    attendances = relationship("EventAttendance", back_populates="event", cascade="all, delete-orphan")
    attachments = relationship("EventAttachment", back_populates="event", cascade="all, delete-orphan")
    status_history = relationship("EventStatusHistory", back_populates="event", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("society_id", "event_number", name="uq_event_number_society"),
        Index("ix_events_society_status", "society_id", "status"),
        Index("ix_events_society_type", "society_id", "event_type"),
        Index("ix_events_starts_ends", "starts_at", "ends_at"),
    )


class EventParticipant(Base):
    """Event Participant Detail Record."""

    __tablename__ = "event_participants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    participant_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # OWNER, TENANT, RESIDENT, AUTHORIZED_DELEGATE
    unit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("units.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    event = relationship("Event", back_populates="participants")
    user = relationship("User")
    unit = relationship("Unit")

    __table_args__ = (
        Index("ix_event_participants_society_event", "society_id", "event_id"),
        Index("ix_event_participants_society_user", "society_id", "user_id"),
    )


class EventRegistration(Base):
    """Event Registration Record."""

    __tablename__ = "event_registrations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    registration_number: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="REGISTERED"
    )  # EventRegistrationStatus enum
    waitlist_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    event = relationship("Event", back_populates="registrations")
    user = relationship("User")

    __table_args__ = (
        UniqueConstraint("society_id", "event_id", "user_id", name="uq_event_user_registration"),
        Index("ix_event_registrations_society_event", "society_id", "event_id"),
        Index("ix_event_registrations_society_user", "society_id", "user_id"),
        Index("ix_event_registrations_status", "society_id", "event_id", "status"),
    )


class EventApproval(Base):
    """Event Approval Record."""

    __tablename__ = "event_approvals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    approver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(30), nullable=False)  # APPROVED or REJECTED
    comments: Mapped[str | None] = mapped_column(String(500), nullable=True)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    event = relationship("Event", back_populates="approvals")
    approver = relationship("User")

    __table_args__ = (Index("ix_event_approvals_society_event", "society_id", "event_id"),)


class EventSchedule(Base):
    """Event Schedule Record."""

    __tablename__ = "event_schedules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    registration_open_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    registration_close_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    event = relationship("Event", back_populates="schedules")

    __table_args__ = (Index("ix_event_schedules_society_starts", "society_id", "starts_at", "status"),)


class EventAttendance(Base):
    """Event Attendance Record."""

    __tablename__ = "event_attendances"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    registration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event_registrations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="REGISTERED"
    )  # EventAttendanceStatus enum
    check_in_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recorded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    event = relationship("Event", back_populates="attendances")
    registration = relationship("EventRegistration")
    user = relationship("User", foreign_keys=[user_id])
    recorder = relationship("User", foreign_keys=[recorded_by])

    __table_args__ = (
        UniqueConstraint("society_id", "event_id", "user_id", name="uq_event_attendance_user"),
        Index("ix_event_attendances_society_user", "society_id", "user_id"),
    )


class EventAttachment(Base):
    """Event Attachment File Metadata."""

    __tablename__ = "event_attachments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    storage_object_key: Mapped[str] = mapped_column(String(500), nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    event = relationship("Event", back_populates="attachments")
    uploader = relationship("User")

    __table_args__ = (Index("ix_event_attachments_society_event", "society_id", "event_id"),)


class EventStatusHistory(Base):
    """Event Lifecycle Status Audit History."""

    __tablename__ = "event_status_histories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    old_status: Mapped[str] = mapped_column(String(50), nullable=False)
    new_status: Mapped[str] = mapped_column(String(50), nullable=False)
    changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    event = relationship("Event", back_populates="status_history")
    changed_by = relationship("User")

    __table_args__ = (Index("ix_event_status_histories_society_event", "society_id", "event_id"),)
