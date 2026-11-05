"""Pydantic Schemas for Staff & Workforce Management."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from apps.api.src.staff.domain.enums import (
    StaffEngagementType,
    StaffStatus,
)


class StaffContactRequest(BaseModel):
    """Staff contact details payload."""

    phone: str = Field(..., min_length=5, max_length=32)
    alternate_phone: str | None = Field(None, max_length=32)
    email: str | None = Field(None, max_length=255)
    emergency_contact_name: str | None = Field(None, max_length=150)
    emergency_contact_relationship: str | None = Field(None, max_length=50)
    emergency_contact_phone: str | None = Field(None, max_length=32)


class StaffContactResponse(BaseModel):
    """Staff contact details response (sensitive PII)."""

    model_config = ConfigDict(from_attributes=True)

    phone: str
    alternate_phone: str | None = None
    email: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_relationship: str | None = None
    emergency_contact_phone: str | None = None


class StaffProfileCreateRequest(BaseModel):
    """Payload to create a new staff profile."""

    user_id: UUID | None = None
    first_name: str = Field(..., min_length=1, max_length=100)
    middle_name: str | None = Field(None, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    preferred_name: str | None = Field(None, max_length=100)
    profile_photo_url: str | None = Field(None, max_length=500)
    date_of_joining: date | None = None
    engagement_type: StaffEngagementType = StaffEngagementType.FULL_TIME
    primary_role_id: UUID | None = None
    contact: StaffContactRequest
    notes: str | None = None


class StaffProfileUpdateRequest(BaseModel):
    """Payload to update an existing staff profile."""

    first_name: str | None = Field(None, min_length=1, max_length=100)
    middle_name: str | None = Field(None, max_length=100)
    last_name: str | None = Field(None, min_length=1, max_length=100)
    preferred_name: str | None = Field(None, max_length=100)
    profile_photo_url: str | None = Field(None, max_length=500)
    engagement_type: StaffEngagementType | None = None
    primary_role_id: UUID | None = None
    notes: str | None = None


class StaffStatusUpdateRequest(BaseModel):
    """Payload to update staff status lifecycle."""

    status: StaffStatus
    reason: str | None = Field(None, max_length=500)


class StaffRoleCreateRequest(BaseModel):
    """Payload to create an operational staff role."""

    name: str = Field(..., min_length=1, max_length=100)
    code: str = Field(..., min_length=1, max_length=50)
    description: str | None = Field(None, max_length=500)
    display_order: int = 0


class StaffRoleResponse(BaseModel):
    """Operational staff role response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    name: str
    code: str
    description: str | None = None
    is_active: bool
    display_order: int
    created_at: datetime


class StaffRoleAssignmentRequest(BaseModel):
    """Payload to assign a role to staff."""

    role_id: UUID
    is_primary: bool = False
    reason: str | None = Field(None, max_length=500)


class StaffRoleAssignmentResponse(BaseModel):
    """Staff role assignment response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    staff_id: UUID
    role_id: UUID
    is_primary: bool
    assigned_at: datetime
    ended_at: datetime | None = None
    reason: str | None = None


class StaffTeamCreateRequest(BaseModel):
    """Payload to create an operational staff team."""

    name: str = Field(..., min_length=1, max_length=100)
    code: str = Field(..., min_length=1, max_length=50)
    description: str | None = Field(None, max_length=500)


class StaffTeamResponse(BaseModel):
    """Staff team response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    name: str
    code: str
    description: str | None = None
    is_active: bool
    created_at: datetime


class StaffTeamMembershipRequest(BaseModel):
    """Payload to add staff to a team."""

    team_id: UUID
    is_primary: bool = False


class StaffTeamMembershipResponse(BaseModel):
    """Staff team membership response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    staff_id: UUID
    team_id: UUID
    is_primary: bool
    joined_at: datetime
    ended_at: datetime | None = None


class StaffDocumentResponse(BaseModel):
    """Staff document metadata response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    staff_id: UUID
    document_type: str
    original_filename: str
    content_type: str
    file_size: int
    created_at: datetime
    archived_at: datetime | None = None


class StaffStatusHistoryResponse(BaseModel):
    """Staff status history response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    staff_id: UUID
    from_status: str | None = None
    to_status: str
    changed_by_user_id: UUID
    reason: str | None = None
    created_at: datetime


class StaffProfileSummaryResponse(BaseModel):
    """Public / operational staff profile summary (no sensitive PII exposed)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    staff_code: str
    display_name: str
    preferred_name: str | None = None
    profile_photo_url: str | None = None
    engagement_type: str
    status: str
    primary_role_id: UUID | None = None
    primary_role_name: str | None = None


class StaffProfileDetailResponse(BaseModel):
    """Detailed staff profile response (contact info included if authorized)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    user_id: UUID | None = None
    staff_code: str
    first_name: str
    middle_name: str | None = None
    last_name: str
    display_name: str
    preferred_name: str | None = None
    profile_photo_url: str | None = None
    date_of_joining: date
    engagement_type: str
    status: str
    primary_role_id: UUID | None = None
    primary_role_name: str | None = None
    notes: str | None = None
    contact: StaffContactResponse | None = None
    created_at: datetime
    updated_at: datetime
