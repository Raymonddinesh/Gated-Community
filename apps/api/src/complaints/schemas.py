"""Pydantic V2 Schemas for Complaints & Helpdesk Domain."""

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class PriorityEnum(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SourceEnum(StrEnum):
    WEB = "WEB"
    MOBILE = "MOBILE"
    ADMIN = "ADMIN"
    SECURITY = "SECURITY"
    VOICE = "VOICE"
    PHOTO = "PHOTO"
    OTHER = "OTHER"


class StatusEnum(StrEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING_FOR_RESIDENT = "WAITING_FOR_RESIDENT"
    RESOLVED = "RESOLVED"
    REOPENED = "REOPENED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class AssignmentTargetTypeEnum(StrEnum):
    INTERNAL_USER = "INTERNAL_USER"
    TEAM = "TEAM"
    FUTURE_STAFF = "FUTURE_STAFF"
    FUTURE_VENDOR = "FUTURE_VENDOR"


class CommentTypeEnum(StrEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"


class AttachmentTypeEnum(StrEnum):
    PHOTO = "PHOTO"
    VIDEO = "VIDEO"
    AUDIO = "AUDIO"
    DOCUMENT = "DOCUMENT"
    OTHER = "OTHER"


class EscalationStatusEnum(StrEnum):
    ACTIVE = "ACTIVE"
    RESOLVED = "RESOLVED"


# --- Category & Subcategory Schemas ---


class ComplaintCategoryCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    code: str = Field(..., min_length=2, max_length=50)
    description: str | None = Field(default=None, max_length=500)
    icon: str | None = Field(default=None, max_length=100)
    is_active: bool = True
    display_order: int = 0


class ComplaintCategoryUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    icon: str | None = Field(default=None, max_length=100)
    is_active: bool | None = None
    display_order: int | None = None


class ComplaintSubcategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    society_id: uuid.UUID
    category_id: uuid.UUID
    name: str
    code: str
    description: str | None = None
    is_active: bool
    display_order: int
    created_at: datetime
    updated_at: datetime


class ComplaintCategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    society_id: uuid.UUID
    name: str
    code: str
    description: str | None = None
    icon: str | None = None
    is_active: bool
    display_order: int
    subcategories: list[ComplaintSubcategoryResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ComplaintSubcategoryCreateRequest(BaseModel):
    category_id: uuid.UUID
    name: str = Field(..., min_length=2, max_length=100)
    code: str = Field(..., min_length=2, max_length=50)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool = True
    display_order: int = 0


class ComplaintSubcategoryUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None
    display_order: int | None = None


# --- SLA Policy Schemas ---


class ComplaintSLAPolicyCreateRequest(BaseModel):
    category_id: uuid.UUID | None = None
    priority: PriorityEnum
    acknowledgement_target_hours: int = Field(default=24, ge=1, le=720)
    resolution_target_hours: int = Field(default=72, ge=1, le=2160)
    is_active: bool = True


class ComplaintSLAPolicyUpdateRequest(BaseModel):
    acknowledgement_target_hours: int | None = Field(default=None, ge=1, le=720)
    resolution_target_hours: int | None = Field(default=None, ge=1, le=2160)
    is_active: bool | None = None


class ComplaintSLAPolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    society_id: uuid.UUID
    category_id: uuid.UUID | None = None
    priority: str
    acknowledgement_target_hours: int
    resolution_target_hours: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


# --- Complaint Schemas ---


class ComplaintCreateRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=200, description="Brief title of the complaint")
    description: str = Field(..., min_length=5, description="Full detailed description")
    category_id: uuid.UUID
    subcategory_id: uuid.UUID | None = None
    unit_id: uuid.UUID | None = None
    priority: PriorityEnum = PriorityEnum.MEDIUM
    source: SourceEnum = SourceEnum.WEB
    vehicle_id: uuid.UUID | None = None
    visitor_id: uuid.UUID | None = None


class ComplaintUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, min_length=5)
    category_id: uuid.UUID | None = None
    subcategory_id: uuid.UUID | None = None
    priority: PriorityEnum | None = None


class ComplaintStatusUpdateRequest(BaseModel):
    status: StatusEnum
    reason: str | None = Field(default=None, max_length=500)


class ComplaintAssignRequest(BaseModel):
    target_type: AssignmentTargetTypeEnum = AssignmentTargetTypeEnum.INTERNAL_USER
    assigned_to_user_id: uuid.UUID | None = None
    assigned_to_role: str | None = Field(default=None, max_length=50)
    assigned_to_team: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=500)


class ComplaintCommentCreateRequest(BaseModel):
    comment_type: CommentTypeEnum = CommentTypeEnum.PUBLIC
    body: str = Field(..., min_length=1, description="Comment text body")


class ComplaintCommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    society_id: uuid.UUID
    complaint_id: uuid.UUID
    author_user_id: uuid.UUID
    comment_type: str
    body: str
    created_at: datetime
    updated_at: datetime


class ComplaintAttachmentCreateRequest(BaseModel):
    attachment_type: AttachmentTypeEnum = AttachmentTypeEnum.PHOTO
    file_key: str = Field(..., min_length=1, max_length=500)
    original_filename: str = Field(..., min_length=1, max_length=255)
    content_type: str = Field(default="image/jpeg", max_length=100)
    file_size_bytes: int | None = Field(default=None, ge=1)
    checksum: str | None = Field(default=None, max_length=64)


class ComplaintAttachmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    society_id: uuid.UUID
    complaint_id: uuid.UUID
    uploaded_by_user_id: uuid.UUID | None = None
    attachment_type: str
    file_key: str
    original_filename: str
    content_type: str
    file_size_bytes: int | None = None
    checksum: str | None = None
    archived_at: datetime | None = None
    created_at: datetime


class ComplaintAssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    society_id: uuid.UUID
    complaint_id: uuid.UUID
    assigned_by_user_id: uuid.UUID
    target_type: str
    assigned_to_user_id: uuid.UUID | None = None
    assigned_to_role: str | None = None
    assigned_to_team: str | None = None
    assigned_at: datetime
    notes: str | None = None
    is_current: bool
    created_at: datetime


class ComplaintStatusHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    society_id: uuid.UUID
    complaint_id: uuid.UUID
    actor_user_id: uuid.UUID
    from_status: str | None = None
    to_status: str
    reason: str | None = None
    created_at: datetime


class ComplaintEscalationCreateRequest(BaseModel):
    escalation_reason: str = Field(..., min_length=5, max_length=500)
    target_user_id: uuid.UUID | None = None
    target_role: str | None = Field(default=None, max_length=50)


class ComplaintEscalationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    society_id: uuid.UUID
    complaint_id: uuid.UUID
    escalation_level: int
    escalation_reason: str
    triggered_by_user_id: uuid.UUID | None = None
    target_user_id: uuid.UUID | None = None
    target_role: str | None = None
    status: str
    triggered_at: datetime
    resolved_at: datetime | None = None
    created_at: datetime


class ComplaintResolutionCreateRequest(BaseModel):
    resolution_summary: str = Field(..., min_length=5, description="Summary of resolution")
    resolution_code: str | None = Field(default=None, max_length=50)


class ComplaintResolutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    society_id: uuid.UUID
    complaint_id: uuid.UUID
    resolved_by_user_id: uuid.UUID
    resolution_summary: str
    resolution_code: str | None = None
    resolved_at: datetime
    created_at: datetime


class ComplaintResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    society_id: uuid.UUID
    complaint_number: str
    title: str
    description: str
    category_id: uuid.UUID
    subcategory_id: uuid.UUID | None = None
    raised_by_user_id: uuid.UUID
    raised_for_unit_id: uuid.UUID | None = None
    priority: str
    source: str
    status: str
    sla_policy_id: uuid.UUID | None = None
    due_at: datetime | None = None
    ack_due_at: datetime | None = None
    acknowledged_at: datetime | None = None
    assigned_at: datetime | None = None
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    reopened_at: datetime | None = None
    cancelled_at: datetime | None = None
    resolution_summary: str | None = None
    vehicle_id: uuid.UUID | None = None
    visitor_id: uuid.UUID | None = None
    work_order_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    category: ComplaintCategoryResponse | None = None
    subcategory: ComplaintSubcategoryResponse | None = None
    current_assignment: ComplaintAssignmentResponse | None = None


class ComplaintPaginatedListResponse(BaseModel):
    items: list[ComplaintResponse]
    total: int
    page: int
    size: int
