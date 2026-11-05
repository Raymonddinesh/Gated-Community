"""Pydantic V2 Schemas for Visitor Management & Security Domain."""

import uuid
from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class VisitorTypeEnum(StrEnum):
    GUEST = "GUEST"
    DELIVERY = "DELIVERY"
    SERVICE = "SERVICE"
    CAB = "CAB"
    OTHER = "OTHER"


class VisitorStatusEnum(StrEnum):
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    ARCHIVED = "ARCHIVED"


class InvitationStatusEnum(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    USED = "USED"


class ApprovalStatusEnum(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class AccessTypeEnum(StrEnum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"


class EntryMethodEnum(StrEnum):
    MANUAL = "MANUAL"
    QR = "QR"
    OTP = "OTP"
    PRE_APPROVED = "PRE_APPROVED"


class DocumentTypeEnum(StrEnum):
    PHOTO = "PHOTO"
    ID_CARD = "ID_CARD"
    DRIVING_LICENSE = "DRIVING_LICENSE"
    PASSPORT = "PASSPORT"
    OTHER = "OTHER"


# --- Visitor Schemas ---


class VisitorCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, description="Visitor full name")
    phone: str = Field(..., min_length=8, max_length=20, description="Visitor phone number")
    alternate_phone: str | None = Field(default=None, max_length=20)
    visitor_type: VisitorTypeEnum = VisitorTypeEnum.GUEST
    identification_type: str | None = Field(default=None, max_length=50)
    identification_number: str | None = Field(default=None, max_length=100)
    photo_file_key: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=500)


class VisitorUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=100)
    phone: str | None = Field(None, min_length=8, max_length=20)
    alternate_phone: str | None = Field(None, max_length=20)
    visitor_type: VisitorTypeEnum | None = None
    identification_type: str | None = Field(None, max_length=50)
    identification_number: str | None = Field(None, max_length=100)
    photo_file_key: str | None = Field(None, max_length=500)
    notes: str | None = Field(None, max_length=500)


class VisitorStatusUpdateRequest(BaseModel):
    status: VisitorStatusEnum
    notes: str | None = Field(None, max_length=500)


class VisitorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    society_id: uuid.UUID
    name: str
    phone: str
    alternate_phone: str | None = None
    visitor_type: str
    identification_type: str | None = None
    identification_number: str | None = None
    photo_file_key: str | None = None
    notes: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime


# --- Visitor Invitation Schemas ---


class VisitorInvitationCreateRequest(BaseModel):
    visitor_name: str = Field(..., min_length=2, max_length=100)
    visitor_phone: str = Field(..., min_length=8, max_length=20)
    visitor_type: VisitorTypeEnum = VisitorTypeEnum.GUEST
    unit_id: uuid.UUID
    expected_date: date
    expected_arrival_window_start: datetime | None = None
    expected_arrival_window_end: datetime | None = None
    expected_departure: datetime | None = None
    purpose: str | None = Field(None, max_length=255)
    delivery_company: str | None = Field(None, max_length=100)
    service_type: str | None = Field(None, max_length=100)
    notes: str | None = Field(None, max_length=500)


class VisitorInvitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    society_id: uuid.UUID
    visitor_id: uuid.UUID
    host_user_id: uuid.UUID
    unit_id: uuid.UUID
    expected_date: date
    expected_arrival_window_start: datetime | None = None
    expected_arrival_window_end: datetime | None = None
    expected_departure: datetime | None = None
    purpose: str | None = None
    pass_code: str | None = None
    delivery_company: str | None = None
    service_type: str | None = None
    status: str
    notes: str | None = None
    created_at: datetime
    updated_at: datetime
    visitor: VisitorResponse | None = None


# --- Visitor Approval Schemas ---


class VisitorApprovalDecisionRequest(BaseModel):
    approval_status: ApprovalStatusEnum
    reason: str | None = Field(None, max_length=255)


class VisitorApprovalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    society_id: uuid.UUID
    visitor_id: uuid.UUID
    invitation_id: uuid.UUID | None = None
    unit_id: uuid.UUID
    approving_user_id: uuid.UUID
    approval_status: str
    decision_reason: str | None = None
    decision_time: datetime
    created_at: datetime


# --- Walk-in & Gate Entry / Exit Schemas ---


class WalkInVisitorEntryRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    phone: str = Field(..., min_length=8, max_length=20)
    visitor_type: VisitorTypeEnum = VisitorTypeEnum.GUEST
    unit_id: uuid.UUID
    gate_identifier: str = Field(..., min_length=1, max_length=50)
    vehicle_id: uuid.UUID | None = None
    delivery_company: str | None = Field(None, max_length=100)
    service_type: str | None = Field(None, max_length=100)
    notes: str | None = Field(None, max_length=500)


class VisitorGateEntryRequest(BaseModel):
    visitor_id: uuid.UUID
    unit_id: uuid.UUID
    host_user_id: uuid.UUID
    gate_identifier: str = Field(..., min_length=1, max_length=50)
    entry_method: EntryMethodEnum = EntryMethodEnum.MANUAL
    invitation_id: uuid.UUID | None = None
    pass_code: str | None = Field(None, max_length=16)
    vehicle_id: uuid.UUID | None = None
    delivery_company: str | None = Field(None, max_length=100)
    service_type: str | None = Field(None, max_length=100)
    notes: str | None = Field(None, max_length=500)


class VisitorGateExitRequest(BaseModel):
    gate_identifier: str = Field(..., min_length=1, max_length=50)
    exit_method: EntryMethodEnum = EntryMethodEnum.MANUAL
    notes: str | None = Field(None, max_length=500)


class EmergencyOverrideEntryRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    phone: str = Field(..., min_length=8, max_length=20)
    unit_id: uuid.UUID
    gate_identifier: str = Field(..., min_length=1, max_length=50)
    reason: str = Field(
        ..., min_length=5, max_length=500, description="Mandatory audit reason for emergency override"
    )
    visitor_type: VisitorTypeEnum = VisitorTypeEnum.SERVICE
    vehicle_id: uuid.UUID | None = None
    notes: str | None = Field(None, max_length=500)


class VisitorAccessRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    society_id: uuid.UUID
    visitor_id: uuid.UUID
    invitation_id: uuid.UUID | None = None
    approval_id: uuid.UUID | None = None
    unit_id: uuid.UUID
    host_user_id: uuid.UUID
    security_user_id: uuid.UUID | None = None
    vehicle_id: uuid.UUID | None = None
    visitor_name_snapshot: str
    visitor_phone_snapshot: str
    visitor_type_snapshot: str
    gate_identifier: str
    access_type: str
    access_time: datetime
    entry_method: str
    exit_time: datetime | None = None
    exit_gate_identifier: str | None = None
    exit_security_user_id: uuid.UUID | None = None
    exit_method: str | None = None
    delivery_company: str | None = None
    service_type: str | None = None
    notes: str | None = None
    emergency_override_reason: str | None = None
    created_at: datetime


# --- Document Schemas ---


class VisitorDocumentCreateRequest(BaseModel):
    document_type: DocumentTypeEnum
    file_key: str = Field(..., min_length=1, max_length=500)
    file_name: str = Field(..., min_length=1, max_length=255)
    file_size_bytes: int | None = Field(None, ge=0)
    content_type: str = Field("image/jpeg", max_length=100)


class VisitorDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    society_id: uuid.UUID
    visitor_id: uuid.UUID
    document_type: str
    file_key: str
    file_name: str
    file_size_bytes: int | None = None
    content_type: str
    uploaded_by: uuid.UUID | None = None
    archived_at: datetime | None = None
    created_at: datetime
