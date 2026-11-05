"""Phase 15 Facility Booking Pydantic Schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from apps.api.src.facility_booking.enums import (
    BlackoutStatus,
    BookingApprovalDecision,
    BookingStatus,
    ParticipantRole,
)

# ---------------------------------------------------------------------------
# Booking Config Schemas
# ---------------------------------------------------------------------------


class FacilityBookingConfigCreate(BaseModel):
    is_bookable: bool = True
    requires_approval: bool = False
    max_capacity: int | None = Field(default=None, ge=1)
    min_duration_minutes: int = Field(default=30, ge=15)
    max_duration_minutes: int = Field(default=480, ge=30)
    advance_booking_days: int = Field(default=30, ge=1)
    min_cancellation_notice_hours: int = Field(default=24, ge=0)
    buffer_before_minutes: int = Field(default=0, ge=0)
    buffer_after_minutes: int = Field(default=0, ge=0)
    allow_recurring: bool = False
    allow_delegate_booking: bool = True
    admin_override_enabled: bool = True


class FacilityBookingConfigUpdate(BaseModel):
    is_bookable: bool | None = None
    requires_approval: bool | None = None
    max_capacity: int | None = Field(default=None, ge=1)
    min_duration_minutes: int | None = Field(default=None, ge=15)
    max_duration_minutes: int | None = Field(default=None, ge=30)
    advance_booking_days: int | None = Field(default=None, ge=1)
    min_cancellation_notice_hours: int | None = Field(default=None, ge=0)
    buffer_before_minutes: int | None = Field(default=None, ge=0)
    buffer_after_minutes: int | None = Field(default=None, ge=0)
    allow_recurring: bool | None = None
    allow_delegate_booking: bool | None = None
    admin_override_enabled: bool | None = None


class FacilityBookingConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    facility_id: UUID
    is_bookable: bool
    requires_approval: bool
    max_capacity: int | None = None
    min_duration_minutes: int
    max_duration_minutes: int
    advance_booking_days: int
    min_cancellation_notice_hours: int
    buffer_before_minutes: int
    buffer_after_minutes: int
    allow_recurring: bool
    allow_delegate_booking: bool
    admin_override_enabled: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Availability Window Schemas
# ---------------------------------------------------------------------------


class FacilityAvailabilityWindowCreate(BaseModel):
    day_of_week: int = Field(..., ge=0, le=6)  # 0=Monday ... 6=Sunday
    start_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")  # "06:00"
    end_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")  # "22:00"
    is_active: bool = True


class FacilityAvailabilityWindowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    facility_id: UUID
    day_of_week: int
    start_time: str
    end_time: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Blackout Period Schemas
# ---------------------------------------------------------------------------


class FacilityBlackoutPeriodCreate(BaseModel):
    title: str = Field(..., max_length=200)
    start_at: datetime
    end_at: datetime
    reason: str | None = Field(default=None, max_length=500)


class FacilityBlackoutPeriodResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    facility_id: UUID
    title: str
    start_at: datetime
    end_at: datetime
    reason: str | None = None
    status: BlackoutStatus
    created_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Participant Schemas
# ---------------------------------------------------------------------------


class FacilityBookingParticipantCreate(BaseModel):
    name: str = Field(..., max_length=100)
    contact_phone: str | None = Field(default=None, max_length=50)
    role_or_type: ParticipantRole | None = ParticipantRole.GUEST


class FacilityBookingParticipantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    booking_id: UUID
    name: str
    contact_phone: str | None = None
    role_or_type: ParticipantRole | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Core Booking Schemas
# ---------------------------------------------------------------------------


class FacilityBookingCreate(BaseModel):
    facility_id: UUID
    facility_area_id: UUID | None = None
    title: str = Field(..., max_length=200)
    description: str | None = Field(default=None, max_length=500)
    start_at: datetime
    end_at: datetime
    participant_count: int = Field(default=1, ge=1)
    delegate_user_id: UUID | None = None
    idempotency_key: str | None = Field(default=None, max_length=100)
    participants: list[FacilityBookingParticipantCreate] = Field(default_factory=list)


class FacilityBookingUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    participant_count: int | None = Field(default=None, ge=1)


class FacilityBookingStatusUpdate(BaseModel):
    status: BookingStatus
    reason: str | None = Field(default=None, max_length=500)


class FacilityBookingApprovalRequest(BaseModel):
    decision: BookingApprovalDecision
    reason: str | None = Field(default=None, max_length=500)


class FacilityBookingApprovalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    booking_id: UUID
    approver_user_id: UUID
    decision: BookingApprovalDecision
    reason: str | None = None
    decided_at: datetime


class FacilityBookingCancellationRequest(BaseModel):
    cancellation_reason: str | None = Field(default=None, max_length=500)
    admin_override: bool = False


class FacilityBookingCancellationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    booking_id: UUID
    cancelled_by_user_id: UUID
    cancellation_reason: str | None = None
    is_within_notice_period: bool
    cancelled_at: datetime


class FacilityBookingStatusHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    booking_id: UUID
    old_status: str
    new_status: str
    changed_by_user_id: UUID | None = None
    reason: str | None = None
    changed_at: datetime


class FacilityBookingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    facility_id: UUID
    facility_area_id: UUID | None = None
    booking_code: str
    title: str
    description: str | None = None
    user_id: UUID
    delegate_user_id: UUID | None = None
    start_at: datetime
    end_at: datetime
    status: BookingStatus
    participant_count: int
    idempotency_key: str | None = None
    created_at: datetime
    updated_at: datetime
    participants: list[FacilityBookingParticipantResponse] = Field(default_factory=list)
    approvals: list[FacilityBookingApprovalResponse] = Field(default_factory=list)
    cancellations: list[FacilityBookingCancellationResponse] = Field(default_factory=list)


class FacilityBookingListResponse(BaseModel):
    items: list[FacilityBookingResponse]
    total: int
    page: int
    size: int
