"""Facility Booking & Common Area Reservation Database Models."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.src.database.base import Base


class FacilityBookingConfig(Base):
    """Configuration rules for bookable facilities."""

    __tablename__ = "facility_booking_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False
    )
    is_bookable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    max_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="30")
    max_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="480")
    advance_booking_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="30")
    min_cancellation_notice_hours: Mapped[int] = mapped_column(Integer, nullable=False, server_default="24")
    buffer_before_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    buffer_after_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    allow_recurring: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    allow_delegate_booking: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    admin_override_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        UniqueConstraint("society_id", "facility_id", name="uq_facility_booking_config_facility"),
        Index("ix_facility_booking_config_society", "society_id", "facility_id"),
    )


class FacilityAvailabilityWindow(Base):
    """Weekly operating/availability windows for facilities."""

    __tablename__ = "facility_availability_windows"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False
    )
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)  # 0=Monday, 6=Sunday
    start_time: Mapped[str] = mapped_column(String(10), nullable=False)  # "06:00"
    end_time: Mapped[str] = mapped_column(String(10), nullable=False)  # "22:00"
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        Index("ix_facility_avail_society_facility", "society_id", "facility_id", "day_of_week"),
    )


class FacilityBlackoutPeriod(Base):
    """Blackout/unavailability windows for facility maintenance or events."""

    __tablename__ = "facility_blackout_periods"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default="ACTIVE")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        Index("ix_facility_blackout_society_facility", "society_id", "facility_id"),
        Index("ix_facility_blackout_time_range", "society_id", "facility_id", "start_at", "end_at"),
    )


class FacilityBooking(Base):
    """Core Facility Reservation / Booking model."""

    __tablename__ = "facility_bookings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="RESTRICT"), nullable=False
    )
    facility_area_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facility_areas.id", ondelete="SET NULL"), nullable=True
    )
    booking_code: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    delegate_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default="PENDING_APPROVAL")
    participant_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    participants: Mapped[list["FacilityBookingParticipant"]] = relationship(
        "FacilityBookingParticipant", back_populates="booking", cascade="all, delete-orphan"
    )
    approvals: Mapped[list["FacilityBookingApproval"]] = relationship(
        "FacilityBookingApproval", back_populates="booking", cascade="all, delete-orphan"
    )
    cancellations: Mapped[list["FacilityBookingCancellation"]] = relationship(
        "FacilityBookingCancellation", back_populates="booking", cascade="all, delete-orphan"
    )
    status_history: Mapped[list["FacilityBookingStatusHistory"]] = relationship(
        "FacilityBookingStatusHistory", back_populates="booking", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("society_id", "booking_code", name="uq_facility_booking_code"),
        Index("ix_facility_booking_society_facility", "society_id", "facility_id"),
        Index("ix_facility_booking_society_user", "society_id", "user_id"),
        Index("ix_facility_booking_society_status", "society_id", "status"),
        Index("ix_facility_booking_time_range", "society_id", "facility_id", "start_at", "end_at"),
        Index("ix_facility_booking_idempotency", "society_id", "idempotency_key"),
    )


class FacilityBookingParticipant(Base):
    """Booking participants info."""

    __tablename__ = "facility_booking_participants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facility_bookings.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    contact_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    role_or_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    booking: Mapped["FacilityBooking"] = relationship("FacilityBooking", back_populates="participants")

    __table_args__ = (Index("ix_facility_booking_part_society_booking", "society_id", "booking_id"),)


class FacilityBookingApproval(Base):
    """Approval or rejection audit trail for booking requests."""

    __tablename__ = "facility_booking_approvals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facility_bookings.id", ondelete="CASCADE"), nullable=False
    )
    approver_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    decision: Mapped[str] = mapped_column(String(50), nullable=False)  # APPROVED, REJECTED
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    booking: Mapped["FacilityBooking"] = relationship("FacilityBooking", back_populates="approvals")

    __table_args__ = (Index("ix_facility_booking_appr_society_booking", "society_id", "booking_id"),)


class FacilityBookingCancellation(Base):
    """Cancellation details and audit log for bookings."""

    __tablename__ = "facility_booking_cancellations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facility_bookings.id", ondelete="CASCADE"), nullable=False
    )
    cancelled_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    cancellation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_within_notice_period: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    cancelled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    booking: Mapped["FacilityBooking"] = relationship("FacilityBooking", back_populates="cancellations")

    __table_args__ = (Index("ix_facility_booking_canc_society_booking", "society_id", "booking_id"),)


class FacilityBookingStatusHistory(Base):
    """Immutable audit trail for booking status state transitions."""

    __tablename__ = "facility_booking_status_histories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facility_bookings.id", ondelete="CASCADE"), nullable=False
    )
    old_status: Mapped[str] = mapped_column(String(50), nullable=False)
    new_status: Mapped[str] = mapped_column(String(50), nullable=False)
    changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    booking: Mapped["FacilityBooking"] = relationship("FacilityBooking", back_populates="status_history")

    __table_args__ = (Index("ix_facility_booking_stat_society_booking", "society_id", "booking_id"),)
