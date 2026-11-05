"""Phase 20 Notifications & Communication Delivery Pydantic Schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from apps.api.src.notifications.enums import (
    ChannelType,
    DevicePlatform,
    NotificationCategory,
    PriorityLevel,
    RecipientType,
)


# ==========================================
# Notification Schemas
# ==========================================
class NotificationCreate(BaseModel):
    category: NotificationCategory = NotificationCategory.GENERAL
    priority: PriorityLevel = PriorityLevel.NORMAL
    source_domain: str = Field(..., max_length=50)
    source_event_id: str | None = None
    idempotency_key: str | None = Field(None, max_length=128)
    title: str = Field(..., max_length=255)
    content: str
    payload: str | None = None
    recipient_user_ids: list[UUID] = Field(default_factory=list)
    recipient_type: RecipientType = RecipientType.RESIDENT


class NotificationBroadcastCreate(BaseModel):
    category: NotificationCategory = NotificationCategory.ANNOUNCEMENT
    priority: PriorityLevel = PriorityLevel.NORMAL
    source_domain: str = Field("announcements", max_length=50)
    title: str = Field(..., max_length=255)
    content: str
    target_type: RecipientType = RecipientType.ALL_RESIDENTS


class NotificationResponse(BaseModel):
    id: UUID
    society_id: UUID
    category: str
    priority: str
    source_domain: str
    source_event_id: str | None = None
    idempotency_key: str | None = None
    title: str
    content: str
    payload: str | None = None
    sender_id: UUID | None = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# Inbox & Recipient Schemas
# ==========================================
class InboxItemResponse(BaseModel):
    id: UUID
    society_id: UUID
    notification_id: UUID
    title: str
    content: str
    category: str
    priority: str
    source_domain: str
    is_read: bool
    read_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UnreadCountResponse(BaseModel):
    unread_count: int


# ==========================================
# Template Schemas
# ==========================================
class NotificationTemplateCreate(BaseModel):
    code: str = Field(..., max_length=100)
    name: str = Field(..., max_length=150)
    category: NotificationCategory = NotificationCategory.GENERAL
    description: str | None = None
    allowlisted_variables: str | None = None  # Comma-separated variable names


class NotificationTemplateVersionCreate(BaseModel):
    channel: ChannelType
    locale: str = Field("en", max_length=10)
    version: int = Field(1, ge=1)
    subject_template: str | None = Field(None, max_length=255)
    body_template: str
    is_published: bool = True


class NotificationTemplateVersionResponse(BaseModel):
    id: UUID
    society_id: UUID | None = None
    template_id: UUID
    channel: str
    locale: str
    version: int
    subject_template: str | None = None
    body_template: str
    is_published: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationTemplateResponse(BaseModel):
    id: UUID
    society_id: UUID | None = None
    code: str
    name: str
    category: str
    description: str | None = None
    is_active: bool
    allowlisted_variables: str | None = None
    versions: list[NotificationTemplateVersionResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# Preference Schemas
# ==========================================
class NotificationPreferenceUpdate(BaseModel):
    category: NotificationCategory
    is_enabled: bool = True
    quiet_hours_enabled: bool = False
    quiet_hours_start: str | None = None  # e.g., "22:00"
    quiet_hours_end: str | None = None  # e.g., "07:00"


class NotificationPreferenceResponse(BaseModel):
    id: UUID
    society_id: UUID
    user_id: UUID
    category: str
    is_enabled: bool
    quiet_hours_enabled: bool
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ChannelPreferenceUpdate(BaseModel):
    category: NotificationCategory
    channel: ChannelType
    is_enabled: bool = True


class ChannelPreferenceResponse(BaseModel):
    id: UUID
    society_id: UUID
    user_id: UUID
    category: str
    channel: str
    is_enabled: bool

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# Delivery & Attempt Schemas
# ==========================================
class DeliveryAttemptResponse(BaseModel):
    id: UUID
    society_id: UUID
    delivery_id: UUID
    attempt_number: int
    provider_name: str
    provider_request_id: str | None = None
    status: str
    response_code: str | None = None
    error_message: str | None = None
    latency_ms: int | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DeliveryResponse(BaseModel):
    id: UUID
    society_id: UUID
    notification_id: UUID
    recipient_id: UUID
    channel: str
    status: str
    attempt_count: int
    max_attempts: int
    next_retry_at: datetime | None = None
    sent_at: datetime | None = None
    delivered_at: datetime | None = None
    failed_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# Device Token Schemas
# ==========================================
class DeviceTokenCreate(BaseModel):
    device_token: str = Field(..., max_length=255)
    platform: DevicePlatform = DevicePlatform.ANDROID


class DeviceTokenResponse(BaseModel):
    id: UUID
    society_id: UUID
    user_id: UUID
    device_token: str
    platform: str
    is_active: bool
    last_used_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
