"""Phase 20 Notifications & Communication Delivery Foundation Database Models."""

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
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.src.database.base import Base


class Notification(Base):
    """Master Notification Entity."""

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # ANNOUNCEMENT, BILLING, EMERGENCY, GOVERNANCE, COMPLAINT, EVENT, FACILITY, MAINTENANCE, GENERAL
    priority: Mapped[str] = mapped_column(
        String(20), nullable=False, default="NORMAL"
    )  # LOW, NORMAL, HIGH, CRITICAL
    source_domain: Mapped[str] = mapped_column(String(50), nullable=False)
    source_event_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON metadata string
    sender_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="CREATED"
    )  # CREATED, QUEUED, PROCESSING, SENT, DELIVERED, READ, PARTIALLY_DELIVERED, FAILED, CANCELLED
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    society = relationship("Society")
    sender = relationship("User", foreign_keys=[sender_id])
    recipients = relationship("NotificationRecipient", back_populates="notification", cascade="all, delete-orphan")
    deliveries = relationship("NotificationDelivery", back_populates="notification", cascade="all, delete-orphan")
    batches = relationship("NotificationBatch", back_populates="notification", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_notifications_society_category", "society_id", "category"),
        Index("ix_notifications_society_status", "society_id", "status"),
        UniqueConstraint("society_id", "idempotency_key", name="uq_notifications_society_idempotency"),
    )


class NotificationRecipient(Base):
    """Notification Recipient Inbox Entity."""

    __tablename__ = "notification_recipients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="CASCADE"), nullable=False
    )
    notification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    recipient_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="RESIDENT"
    )  # RESIDENT, OWNER, TENANT, COMMITTEE, STAFF, ALL_RESIDENTS
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    society = relationship("Society")
    notification = relationship("Notification", back_populates="recipients")
    user = relationship("User", foreign_keys=[user_id])
    deliveries = relationship("NotificationDelivery", back_populates="recipient", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_notification_recipients_user_read", "society_id", "user_id", "is_read"),
        Index("ix_notification_recipients_notification", "society_id", "notification_id"),
        UniqueConstraint("notification_id", "user_id", name="uq_notification_recipients_notif_user"),
    )


class NotificationTemplate(Base):
    """Master Notification Template Catalog Entity."""

    __tablename__ = "notification_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="CASCADE"), nullable=True
    )  # NULL for system global templates
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allowlisted_variables: Mapped[str | None] = mapped_column(Text, nullable=True)  # Comma-separated variable names
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    society = relationship("Society")
    versions = relationship("NotificationTemplateVersion", back_populates="template", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_notification_templates_code", "code"),
        UniqueConstraint("society_id", "code", name="uq_notification_templates_society_code"),
    )


class NotificationTemplateVersion(Base):
    """Versioned Notification Template Body Entity."""

    __tablename__ = "notification_template_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="CASCADE"), nullable=True
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notification_templates.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)  # IN_APP, EMAIL, SMS, WHATSAPP, PUSH
    locale: Mapped[str] = mapped_column(String(10), nullable=False, default="en")  # en, ta, etc.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    subject_template: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body_template: Mapped[str] = mapped_column(Text, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    society = relationship("Society")
    template = relationship("NotificationTemplate", back_populates="versions")

    __table_args__ = (
        Index("ix_notification_template_versions_lookup", "template_id", "channel", "locale", "is_published"),
        UniqueConstraint("template_id", "channel", "locale", "version", name="uq_notif_template_version_key"),
    )


class NotificationPreference(Base):
    """User Category Notification Preference Entity."""

    __tablename__ = "notification_preferences"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    quiet_hours_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    quiet_hours_start: Mapped[str | None] = mapped_column(String(10), nullable=True)  # e.g., "22:00"
    quiet_hours_end: Mapped[str | None] = mapped_column(String(10), nullable=True)  # e.g., "07:00"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    society = relationship("Society")
    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        UniqueConstraint("society_id", "user_id", "category", name="uq_notification_preference_user_cat"),
    )


class NotificationChannelPreference(Base):
    """User Channel-Specific Opt-In/Opt-Out Preference Entity."""

    __tablename__ = "notification_channel_preferences"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)  # IN_APP, EMAIL, SMS, WHATSAPP, PUSH
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    society = relationship("Society")
    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        UniqueConstraint("society_id", "user_id", "category", "channel", name="uq_notif_channel_pref_key"),
    )


class NotificationDelivery(Base):
    """Channel Delivery Execution Entity."""

    __tablename__ = "notification_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="CASCADE"), nullable=False
    )
    notification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False
    )
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notification_recipients.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)  # IN_APP, EMAIL, SMS, WHATSAPP, PUSH
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="QUEUED"
    )  # QUEUED, PROCESSING, SENT, DELIVERED, FAILED, RETRYING, EXPIRED, SUPPRESSED, CANCELLED
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    society = relationship("Society")
    notification = relationship("Notification", back_populates="deliveries")
    recipient = relationship("NotificationRecipient", back_populates="deliveries")
    attempts = relationship("NotificationDeliveryAttempt", back_populates="delivery", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_notification_deliveries_status", "society_id", "status"),
        Index("ix_notification_deliveries_recipient", "society_id", "recipient_id"),
        UniqueConstraint("recipient_id", "channel", name="uq_notification_delivery_recipient_channel"),
    )


class NotificationDeliveryAttempt(Base):
    """Provider Delivery Attempt Log Entity."""

    __tablename__ = "notification_delivery_attempts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="CASCADE"), nullable=False
    )
    delivery_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notification_deliveries.id", ondelete="CASCADE"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_name: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_request_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)  # SUCCESS, FAILED, RETRYABLE_FAILURE
    response_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    society = relationship("Society")
    delivery = relationship("NotificationDelivery", back_populates="attempts")

    __table_args__ = (
        Index("ix_notif_delivery_attempts_delivery", "society_id", "delivery_id"),
    )


class NotificationBatch(Base):
    """Mass Broadcast Batch Execution Entity."""

    __tablename__ = "notification_batches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="CASCADE"), nullable=False
    )
    notification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False
    )
    batch_index: Mapped[int] = mapped_column(Integer, nullable=False)
    total_batches: Mapped[int] = mapped_column(Integer, nullable=False)
    recipient_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="QUEUED"
    )  # QUEUED, PROCESSING, COMPLETED, FAILED
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    society = relationship("Society")
    notification = relationship("Notification", back_populates="batches")

    __table_args__ = (
        UniqueConstraint("notification_id", "batch_index", name="uq_notif_batch_index"),
    )


class UserDeviceToken(Base):
    """Mobile Push Device Token Registration Entity."""

    __tablename__ = "user_device_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    device_token: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False, default="ANDROID")  # ANDROID, IOS, WEB
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    society = relationship("Society")
    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        Index("ix_user_device_tokens_user", "society_id", "user_id"),
        UniqueConstraint("society_id", "user_id", "device_token", name="uq_user_device_token"),
    )
