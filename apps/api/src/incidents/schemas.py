"""Phase 19 Incident Management Pydantic Schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from apps.api.src.incidents.enums import (
    ActionPriority,
    ActionStatus,
    AttachmentFileType,
    EmergencyContactType,
    IncidentSeverity,
    IncidentStatus,
    ReporterType,
    ResponderType,
)


# ==========================================
# Category Schemas
# ==========================================
class IncidentCategoryCreate(BaseModel):
    name: str = Field(..., max_length=100)
    code: str = Field(..., max_length=50)
    description: str | None = None
    default_severity: IncidentSeverity = IncidentSeverity.MEDIUM
    default_sla_minutes: int | None = 60
    is_active: bool = True


class IncidentCategoryResponse(BaseModel):
    id: UUID
    society_id: UUID | None = None
    name: str
    code: str
    description: str | None = None
    default_severity: str
    default_sla_minutes: int | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# Emergency Contact Schemas
# ==========================================
class EmergencyContactCreate(BaseModel):
    contact_type: EmergencyContactType
    name: str = Field(..., max_length=100)
    phone_number: str = Field(..., max_length=30)
    alt_phone_number: str | None = None
    email: str | None = None
    address: str | None = None
    is_platform_default: bool = False
    is_active: bool = True
    display_order: int = 0
    notes: str | None = None


class EmergencyContactUpdate(BaseModel):
    contact_type: EmergencyContactType | None = None
    name: str | None = None
    phone_number: str | None = None
    alt_phone_number: str | None = None
    email: str | None = None
    address: str | None = None
    is_active: bool | None = None
    display_order: int | None = None
    notes: str | None = None


class EmergencyContactResponse(BaseModel):
    id: UUID
    society_id: UUID | None = None
    contact_type: str
    name: str
    phone_number: str
    alt_phone_number: str | None = None
    email: str | None = None
    address: str | None = None
    is_platform_default: bool
    is_active: bool
    display_order: int
    notes: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# Assignment Schemas
# ==========================================
class IncidentAssignmentCreate(BaseModel):
    responder_type: ResponderType
    assigned_user_id: UUID | None = None
    assigned_staff_id: UUID | None = None
    assigned_vendor_id: UUID | None = None
    assigned_role: str | None = None
    assignment_notes: str | None = None
    is_primary: bool = False


class IncidentAssignmentResponse(BaseModel):
    id: UUID
    society_id: UUID
    incident_id: UUID
    responder_type: str
    assigned_user_id: UUID | None = None
    assigned_staff_id: UUID | None = None
    assigned_vendor_id: UUID | None = None
    assigned_role: str | None = None
    assignment_notes: str | None = None
    is_primary: bool
    assigned_by_id: UUID
    assigned_at: datetime
    unassigned_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# Action Schemas
# ==========================================
class IncidentActionCreate(BaseModel):
    title: str = Field(..., max_length=200)
    description: str | None = None
    priority: ActionPriority = ActionPriority.MEDIUM
    assigned_user_id: UUID | None = None
    due_at: datetime | None = None


class IncidentActionUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: ActionStatus | None = None
    priority: ActionPriority | None = None
    assigned_user_id: UUID | None = None
    due_at: datetime | None = None


class IncidentActionResponse(BaseModel):
    id: UUID
    society_id: UUID
    incident_id: UUID
    title: str
    description: str | None = None
    status: str
    priority: str
    assigned_user_id: UUID | None = None
    due_at: datetime | None = None
    completed_at: datetime | None = None
    completed_by_id: UUID | None = None
    created_by_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# Escalation Schemas
# ==========================================
class IncidentEscalationCreate(BaseModel):
    target_role: str = Field(..., max_length=50)
    reason: str


class IncidentEscalationResponse(BaseModel):
    id: UUID
    society_id: UUID
    incident_id: UUID
    escalation_level: int
    triggered_by_id: UUID
    target_role: str
    reason: str
    sla_minutes_at_escalation: int | None = None
    escalated_at: datetime
    resolved_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# Attachment Schemas
# ==========================================
class PresignedUploadUrlRequest(BaseModel):
    file_name: str = Field(..., max_length=255)
    file_type: AttachmentFileType = AttachmentFileType.DOCUMENT
    file_size_bytes: int = Field(..., gt=0)
    mime_type: str = Field(..., max_length=100)
    duration_seconds: int | None = None  # Validated <= 60 for audio


class PresignedUploadUrlResponse(BaseModel):
    upload_url: str
    storage_path: str
    expires_in_seconds: int = 900


class IncidentAttachmentCreate(BaseModel):
    file_name: str = Field(..., max_length=255)
    file_type: AttachmentFileType = AttachmentFileType.DOCUMENT
    file_size_bytes: int = Field(..., gt=0)
    storage_path: str = Field(..., max_length=500)
    mime_type: str = Field(..., max_length=100)
    duration_seconds: int | None = None


class IncidentAttachmentResponse(BaseModel):
    id: UUID
    society_id: UUID
    incident_id: UUID
    file_name: str
    file_type: str
    file_size_bytes: int
    storage_path: str
    mime_type: str
    duration_seconds: int | None = None
    uploaded_by_id: UUID
    created_at: datetime
    download_url: str | None = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# Timeline & History Schemas
# ==========================================
class IncidentTimelineResponse(BaseModel):
    id: UUID
    society_id: UUID
    incident_id: UUID
    actor_id: UUID
    actor_role: str
    event_type: str
    summary: str
    details: str | None = None
    is_internal_only: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IncidentStatusHistoryResponse(BaseModel):
    id: UUID
    society_id: UUID
    incident_id: UUID
    from_status: str | None = None
    to_status: str
    changed_by_id: UUID
    reason: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IncidentAcknowledgementCreate(BaseModel):
    responder_role: str = Field(..., max_length=50)
    notes: str | None = None


class IncidentAcknowledgementResponse(BaseModel):
    id: UUID
    society_id: UUID
    incident_id: UUID
    acknowledged_by_id: UUID
    responder_role: str
    acknowledged_at: datetime
    notes: str | None = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# Incident Core Schemas
# ==========================================
class IncidentCreate(BaseModel):
    title: str = Field(..., max_length=200)
    description: str
    category_id: UUID
    severity: IncidentSeverity | None = None  # Computed if None
    reporter_type: ReporterType = ReporterType.RESIDENT
    reporter_contact: str | None = None

    block_id: UUID | None = None
    floor_id: UUID | None = None
    unit_id: UUID | None = None
    facility_id: UUID | None = None
    facility_area_id: UUID | None = None
    location_details: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    voice_note_url: str | None = None
    voice_note_duration_seconds: int | None = None  # Max 60s limit


class IncidentTriageRequest(BaseModel):
    severity: IncidentSeverity
    requires_governance_review: bool = False
    requires_work_order: bool = False
    triage_notes: str | None = None


class IncidentOverrideRequest(BaseModel):
    target_status: IncidentStatus
    override_reason: str = Field(..., min_length=5)


class IncidentStatusUpdateRequest(BaseModel):
    target_status: IncidentStatus
    reason: str | None = None


class IncidentResponse(BaseModel):
    id: UUID
    society_id: UUID
    incident_number: str
    title: str
    description: str
    category_id: UUID
    severity: str
    status: str
    reported_by_id: UUID
    reporter_type: str
    reporter_contact: str | None = None

    block_id: UUID | None = None
    floor_id: UUID | None = None
    unit_id: UUID | None = None
    facility_id: UUID | None = None
    facility_area_id: UUID | None = None
    location_details: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    voice_note_url: str | None = None
    voice_note_duration_seconds: int | None = None

    is_hazard_contained: bool
    hazard_contained_at: datetime | None = None
    requires_governance_review: bool
    requires_work_order: bool

    override_applied: bool
    override_reason: str | None = None
    overridden_by_id: UUID | None = None
    overridden_at: datetime | None = None

    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    category: IncidentCategoryResponse | None = None
    assignments: list[IncidentAssignmentResponse] = []
    actions: list[IncidentActionResponse] = []
    escalations: list[IncidentEscalationResponse] = []
    attachments: list[IncidentAttachmentResponse] = []
    acknowledgements: list[IncidentAcknowledgementResponse] = []

    model_config = ConfigDict(from_attributes=True)
