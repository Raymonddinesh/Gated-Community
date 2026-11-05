"""Phase 17 Event Pydantic Schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from apps.api.src.events.enums import (
    EventAttendanceStatus,
    EventRegistrationStatus,
    EventStatus,
    EventType,
    ParticipantType,
)


class EventCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: str = Field(..., min_length=5)
    event_type: EventType
    facility_id: UUID | None = None
    capacity: int | None = Field(None, ge=1)
    registration_required: bool = True
    registration_open_at: datetime | None = None
    registration_close_at: datetime | None = None
    starts_at: datetime
    ends_at: datetime
    timezone: str = "Asia/Kolkata"

    @model_validator(mode="after")
    def validate_timestamps(self) -> "EventCreate":
        if self.starts_at >= self.ends_at:
            raise ValueError("starts_at must be strictly before ends_at")

        if self.registration_required:
            if self.registration_open_at and self.registration_close_at:
                if self.registration_open_at >= self.registration_close_at:
                    raise ValueError("registration_open_at must be strictly before registration_close_at")
                if self.registration_close_at > self.starts_at:
                    raise ValueError("registration_close_at must be at or before starts_at")
        return self


class EventUpdate(BaseModel):
    title: str | None = Field(None, min_length=3, max_length=200)
    description: str | None = Field(None, min_length=5)
    event_type: EventType | None = None
    facility_id: UUID | None = None
    capacity: int | None = Field(None, ge=1)
    registration_required: bool | None = None
    registration_open_at: datetime | None = None
    registration_close_at: datetime | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    timezone: str | None = None


class EventApprovalRequest(BaseModel):
    action: str = Field(..., description="APPROVED or REJECTED")
    comments: str | None = Field(None, max_length=500)


class EventCancelRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


class EventRegistrationCreate(BaseModel):
    unit_id: UUID | None = None
    participant_type: ParticipantType = ParticipantType.RESIDENT


class EventAttendanceRecord(BaseModel):
    status: EventAttendanceStatus = EventAttendanceStatus.ATTENDED
    notes: str | None = Field(None, max_length=500)


class EventAttachmentCreate(BaseModel):
    file_name: str = Field(..., min_length=1, max_length=255)
    file_size: int = Field(..., gt=0, le=10 * 1024 * 1024)  # Max 10 MB
    mime_type: str = Field(..., min_length=3, max_length=100)


# Response Schemas


class EventAttachmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    event_id: UUID
    file_name: str
    file_size: int
    mime_type: str
    storage_object_key: str
    uploaded_by: UUID
    uploaded_at: datetime


class EventRegistrationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    event_id: UUID
    user_id: UUID
    registration_number: str
    status: EventRegistrationStatus
    waitlist_position: int | None = None
    registered_at: datetime
    confirmed_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancellation_reason: str | None = None
    is_masked: bool = False


class EventAttendanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    event_id: UUID
    registration_id: UUID
    user_id: UUID
    status: EventAttendanceStatus
    check_in_time: datetime | None = None
    recorded_by: UUID
    notes: str | None = None
    created_at: datetime


class EventStatusHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    event_id: UUID
    old_status: str
    new_status: str
    changed_by_user_id: UUID | None = None
    reason: str | None = None
    changed_at: datetime


class EventMetricsResponse(BaseModel):
    total_registered: int = 0
    confirmed: int = 0
    waitlisted: int = 0
    cancelled: int = 0
    attended: int = 0
    no_show: int = 0
    capacity: int | None = None


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    event_number: str
    title: str
    description: str
    event_type: EventType
    status: EventStatus
    organizer_id: UUID
    facility_id: UUID | None = None
    capacity: int | None = None
    registration_required: bool
    registration_open_at: datetime | None = None
    registration_close_at: datetime | None = None
    starts_at: datetime
    ends_at: datetime
    timezone: str
    cancellation_reason: str | None = None
    published_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    created_by: UUID
    updated_by: UUID | None = None
    metrics: EventMetricsResponse | None = None
    attachments: list[EventAttachmentResponse] = []
