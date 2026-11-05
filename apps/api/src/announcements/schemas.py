"""Phase 16 Announcement Pydantic Schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from apps.api.src.announcements.enums import (
    AnnouncementPriority,
    AnnouncementStatus,
    AudienceType,
    RoleFilter,
    ScheduleStatus,
)

# ---------------------------------------------------------------------------
# Audience Schemas
# ---------------------------------------------------------------------------


class AnnouncementAudienceCreate(BaseModel):
    audience_type: AudienceType
    target_block_id: UUID | None = None
    target_floor_id: UUID | None = None
    target_unit_id: UUID | None = None
    target_user_id: UUID | None = None
    role_filter: RoleFilter | None = RoleFilter.ALL


class AnnouncementAudienceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    announcement_id: UUID
    audience_type: AudienceType
    target_block_id: UUID | None = None
    target_floor_id: UUID | None = None
    target_unit_id: UUID | None = None
    target_user_id: UUID | None = None
    role_filter: RoleFilter | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Attachment Schemas
# ---------------------------------------------------------------------------


class AnnouncementAttachmentCreate(BaseModel):
    file_name: str = Field(..., max_length=255)
    file_size: int = Field(..., ge=1)
    mime_type: str = Field(..., max_length=100)
    storage_object_key: str = Field(..., max_length=500)


class AnnouncementAttachmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    announcement_id: UUID
    file_name: str
    file_size: int
    mime_type: str
    storage_object_key: str
    uploaded_by: UUID
    uploaded_at: datetime


# ---------------------------------------------------------------------------
# Acknowledgement & Read Receipt Schemas
# ---------------------------------------------------------------------------


class AnnouncementAcknowledgementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    announcement_id: UUID
    user_id: UUID
    version_number: int
    acknowledged_at: datetime


class AnnouncementReadReceiptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    announcement_id: UUID
    user_id: UUID
    read_at: datetime


# ---------------------------------------------------------------------------
# Status History & Version Schemas
# ---------------------------------------------------------------------------


class AnnouncementStatusHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    announcement_id: UUID
    old_status: str
    new_status: str
    changed_by_user_id: UUID | None = None
    reason: str | None = None
    changed_at: datetime


class AnnouncementVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    announcement_id: UUID
    version_number: int
    title: str
    summary: str | None = None
    body: str
    priority: AnnouncementPriority
    edited_by_user_id: UUID
    edit_reason: str | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Core Announcement Schemas
# ---------------------------------------------------------------------------


class AnnouncementCreate(BaseModel):
    title: str = Field(..., max_length=200)
    summary: str | None = Field(default=None, max_length=500)
    body: str
    priority: AnnouncementPriority = AnnouncementPriority.NORMAL
    requires_acknowledgement: bool = False
    is_pinned: bool = False
    published_at: datetime | None = None
    expires_at: datetime | None = None
    audiences: list[AnnouncementAudienceCreate] = Field(default_factory=list)
    attachments: list[AnnouncementAttachmentCreate] = Field(default_factory=list)


class AnnouncementUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    summary: str | None = Field(default=None, max_length=500)
    body: str | None = None
    priority: AnnouncementPriority | None = None
    requires_acknowledgement: bool | None = None
    is_pinned: bool | None = None
    expires_at: datetime | None = None
    edit_reason: str | None = Field(default=None, max_length=500)


class AnnouncementScheduleCreate(BaseModel):
    publish_at: datetime
    expires_at: datetime | None = None


class AnnouncementScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    announcement_id: UUID
    publish_at: datetime
    expires_at: datetime | None = None
    status: ScheduleStatus
    created_at: datetime


class AnnouncementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    announcement_number: str
    title: str
    summary: str | None = None
    body: str
    priority: AnnouncementPriority
    status: AnnouncementStatus
    author_id: UUID
    publisher_id: UUID | None = None
    requires_acknowledgement: bool
    is_pinned: bool
    published_at: datetime | None = None
    expires_at: datetime | None = None
    version_number: int
    created_at: datetime
    updated_at: datetime
    is_read: bool = False
    is_acknowledged: bool = False
    audiences: list[AnnouncementAudienceResponse] = Field(default_factory=list)
    attachments: list[AnnouncementAttachmentResponse] = Field(default_factory=list)


class AnnouncementListResponse(BaseModel):
    items: list[AnnouncementResponse]
    total: int
    page: int
    size: int


class AnnouncementMetricsResponse(BaseModel):
    announcement_id: UUID
    society_id: UUID
    total_read_count: int
    total_acknowledged_count: int
    version_number: int
