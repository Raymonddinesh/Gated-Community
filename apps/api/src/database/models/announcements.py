"""Announcements, Communications & Resident Notification Database Models."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.src.database.base import Base


class Announcement(Base):
    """Core Announcement Entity."""

    __tablename__ = "announcements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    announcement_number: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, server_default="NORMAL")
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="DRAFT")
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    publisher_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    requires_acknowledgement: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Relationships
    audiences = relationship(
        "AnnouncementAudience", back_populates="announcement", cascade="all, delete-orphan"
    )
    attachments = relationship(
        "AnnouncementAttachment", back_populates="announcement", cascade="all, delete-orphan"
    )
    acknowledgements = relationship(
        "AnnouncementAcknowledgement", back_populates="announcement", cascade="all, delete-orphan"
    )
    read_receipts = relationship(
        "AnnouncementReadReceipt", back_populates="announcement", cascade="all, delete-orphan"
    )
    schedules = relationship(
        "AnnouncementSchedule", back_populates="announcement", cascade="all, delete-orphan"
    )
    status_histories = relationship(
        "AnnouncementStatusHistory", back_populates="announcement", cascade="all, delete-orphan"
    )
    versions = relationship(
        "AnnouncementVersion", back_populates="announcement", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("society_id", "announcement_number", name="uq_announcement_number_society"),
        Index("ix_announcements_society_status", "society_id", "status"),
        Index("ix_announcements_society_priority", "society_id", "priority"),
        Index("ix_announcements_published_expires", "published_at", "expires_at"),
    )


class AnnouncementAudience(Base):
    """Targeting rules for announcements (Society, Block, Floor, Unit, User/Resident)."""

    __tablename__ = "announcement_audiences"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    announcement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("announcements.id", ondelete="CASCADE"), nullable=False
    )
    audience_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # SOCIETY, BLOCK, FLOOR, UNIT, RESIDENT
    target_block_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("blocks.id", ondelete="CASCADE"), nullable=True
    )
    target_floor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("floors.id", ondelete="CASCADE"), nullable=True
    )
    target_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("units.id", ondelete="CASCADE"), nullable=True
    )
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    role_filter: Mapped[str | None] = mapped_column(String(30), nullable=True)  # ALL, OWNER_ONLY, TENANT_ONLY
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    announcement = relationship("Announcement", back_populates="audiences")

    __table_args__ = (
        Index("ix_announcement_audiences_society_announcement", "society_id", "announcement_id"),
    )


class AnnouncementAttachment(Base):
    """Attachment file metadata linked to announcements."""

    __tablename__ = "announcement_attachments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    announcement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("announcements.id", ondelete="CASCADE"), nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    storage_object_key: Mapped[str] = mapped_column(String(500), nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    announcement = relationship("Announcement", back_populates="attachments")

    __table_args__ = (
        Index("ix_announcement_attachments_society_announcement", "society_id", "announcement_id"),
    )


class AnnouncementAcknowledgement(Base):
    """Explicit acknowledgement records for mandatory announcements."""

    __tablename__ = "announcement_acknowledgements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    announcement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("announcements.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    acknowledged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    announcement = relationship("Announcement", back_populates="acknowledgements")

    __table_args__ = (
        UniqueConstraint(
            "society_id", "announcement_id", "user_id", "version_number", name="uq_announcement_ack_version"
        ),
        Index("ix_announcement_acks_society_user", "society_id", "user_id"),
    )


class AnnouncementReadReceipt(Base):
    """Read tracking receipts for announcements."""

    __tablename__ = "announcement_read_receipts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    announcement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("announcements.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    announcement = relationship("Announcement", back_populates="read_receipts")

    __table_args__ = (
        UniqueConstraint("society_id", "announcement_id", "user_id", name="uq_announcement_read_user"),
        Index("ix_announcement_reads_society_user", "society_id", "user_id"),
    )


class AnnouncementSchedule(Base):
    """Publishing schedules for deferred announcement release."""

    __tablename__ = "announcement_schedules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    announcement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("announcements.id", ondelete="CASCADE"), nullable=False
    )
    publish_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="PENDING")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    announcement = relationship("Announcement", back_populates="schedules")

    __table_args__ = (
        Index("ix_announcement_schedules_society_publish", "society_id", "publish_at", "status"),
    )


class AnnouncementStatusHistory(Base):
    """Immutable status history log for announcement lifecycle changes."""

    __tablename__ = "announcement_status_histories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    announcement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("announcements.id", ondelete="CASCADE"), nullable=False
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

    announcement = relationship("Announcement", back_populates="status_histories")

    __table_args__ = (
        Index("ix_announcement_status_hist_society_announcement", "society_id", "announcement_id"),
    )


class AnnouncementVersion(Base):
    """Immutable published version snapshots for material announcement changes."""

    __tablename__ = "announcement_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    announcement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("announcements.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False)
    edited_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    edit_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    announcement = relationship("Announcement", back_populates="versions")

    __table_args__ = (
        UniqueConstraint(
            "society_id", "announcement_id", "version_number", name="uq_announcement_version_number"
        ),
        Index("ix_announcement_versions_society_announcement", "society_id", "announcement_id"),
    )
