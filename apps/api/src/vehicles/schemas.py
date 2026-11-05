"""Vehicle domain Pydantic schemas."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class VehicleTypeEnum(StrEnum):
    FOUR_WHEELER = "FOUR_WHEELER"
    THREE_WHEELER = "THREE_WHEELER"
    TWO_WHEELER = "TWO_WHEELER"
    BICYCLE = "BICYCLE"


class FuelTypeEnum(StrEnum):
    PETROL = "PETROL"
    DIESEL = "DIESEL"
    CNG = "CNG"
    ELECTRIC = "ELECTRIC"
    HYBRID = "HYBRID"
    OTHER = "OTHER"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class VehicleStatusEnum(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    SOLD = "SOLD"
    TRANSFERRED = "TRANSFERRED"
    SCRAPPED = "SCRAPPED"


class VerificationStatusEnum(StrEnum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class AssociationTypeEnum(StrEnum):
    OWNER = "OWNER"
    TENANT = "TENANT"
    RESIDENT = "RESIDENT"
    AUTHORIZED_DELEGATE = "AUTHORIZED_DELEGATE"


class AssociationStatusEnum(StrEnum):
    ACTIVE = "ACTIVE"
    ENDED = "ENDED"
    REVOKED = "REVOKED"


class VehicleDocumentTypeEnum(StrEnum):
    RC = "RC"
    INSURANCE = "INSURANCE"
    PUC = "PUC"
    PERMIT = "PERMIT"
    OTHER = "OTHER"


class AccessTypeEnum(StrEnum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"


class DetectionMethodEnum(StrEnum):
    MANUAL = "MANUAL"
    RFID = "RFID"
    ANPR = "ANPR"


# ---------------------------------------------------------------------------
# Association Schemas
# ---------------------------------------------------------------------------


class VehicleAssociationCreateRequest(BaseModel):
    user_id: uuid.UUID
    unit_id: uuid.UUID
    association_type: AssociationTypeEnum = AssociationTypeEnum.RESIDENT
    is_primary: bool = False
    valid_from: date | None = None
    valid_to: date | None = None
    notes: str | None = None


class VehicleAssociationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    society_id: uuid.UUID
    vehicle_id: uuid.UUID
    user_id: uuid.UUID
    unit_id: uuid.UUID
    association_type: str
    is_primary: bool
    valid_from: date
    valid_to: date | None
    status: str
    notes: str | None
    created_at: datetime
    updated_at: datetime
    # Nested minimal details if loaded
    unit_number: str | None = None
    user_display_name: str | None = None


# ---------------------------------------------------------------------------
# Verification Schemas
# ---------------------------------------------------------------------------


class VehicleVerifyRequest(BaseModel):
    verification_status: VerificationStatusEnum
    reason: str | None = None
    supporting_document_ref: str | None = None
    notes: str | None = None


class VehicleVerificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    society_id: uuid.UUID
    vehicle_id: uuid.UUID
    verifier_user_id: uuid.UUID
    verification_status: str
    verification_date: date
    reason: str | None
    supporting_document_ref: str | None
    notes: str | None
    created_at: datetime


# ---------------------------------------------------------------------------
# Document Schemas
# ---------------------------------------------------------------------------


class VehicleDocumentCreateRequest(BaseModel):
    document_type: VehicleDocumentTypeEnum
    document_number: str | None = None
    file_key: str
    file_name: str
    file_size_bytes: int | None = None
    content_type: str = "application/pdf"
    valid_from: date | None = None
    valid_to: date | None = None


class VehicleDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    society_id: uuid.UUID
    vehicle_id: uuid.UUID
    document_type: str
    document_number: str | None
    file_key: str
    file_name: str
    file_size_bytes: int | None
    content_type: str
    valid_from: date | None
    valid_to: date | None
    uploaded_by: uuid.UUID | None
    created_at: datetime


# ---------------------------------------------------------------------------
# Parking Association Schemas
# ---------------------------------------------------------------------------


class VehicleParkingCreateRequest(BaseModel):
    parking_slot_number: str
    valid_from: date | None = None
    valid_to: date | None = None
    notes: str | None = None


class VehicleParkingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    society_id: uuid.UUID
    vehicle_id: uuid.UUID
    parking_slot_number: str
    valid_from: date
    valid_to: date | None
    status: str
    notes: str | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Vehicle Access Schemas
# ---------------------------------------------------------------------------


class VehicleAccessRecordCreateRequest(BaseModel):
    registration_number: str = Field(..., min_length=3, max_length=32)
    access_type: AccessTypeEnum
    gate_identifier: str = Field(..., max_length=50)
    detection_method: DetectionMethodEnum = DetectionMethodEnum.MANUAL
    captured_image_ref: str | None = None
    source_provider: str = "MANUAL"
    confidence_score: Decimal | None = None
    notes: str | None = None


class VehicleAccessRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    society_id: uuid.UUID
    vehicle_id: uuid.UUID | None
    registration_number_snapshot: str
    normalized_registration_number_snapshot: str
    access_type: str
    gate_identifier: str
    access_time: datetime
    detection_method: str
    captured_image_ref: str | None
    operator_user_id: uuid.UUID | None
    source_provider: str
    confidence_score: Decimal | None
    notes: str | None
    created_at: datetime


# ---------------------------------------------------------------------------
# Vehicle Main Schemas
# ---------------------------------------------------------------------------


class VehicleCreateRequest(BaseModel):
    registration_number: str = Field(..., min_length=3, max_length=32)
    vehicle_type: VehicleTypeEnum
    make: str | None = None
    model: str | None = None
    variant: str | None = None
    color: str | None = None
    fuel_type: FuelTypeEnum = FuelTypeEnum.PETROL
    is_ev: bool = False
    battery_capacity_kwh: Decimal | None = None
    charging_required: bool = False
    notes: str | None = None
    # Optional direct association upon creation
    unit_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    association_type: AssociationTypeEnum = AssociationTypeEnum.RESIDENT
    is_primary: bool = False
    parking_slot_number: str | None = None


class VehicleUpdateRequest(BaseModel):
    make: str | None = None
    model: str | None = None
    variant: str | None = None
    color: str | None = None
    fuel_type: FuelTypeEnum | None = None
    is_ev: bool | None = None
    battery_capacity_kwh: Decimal | None = None
    charging_required: bool | None = None
    notes: str | None = None


class VehicleStatusUpdateRequest(BaseModel):
    status: VehicleStatusEnum
    notes: str | None = None


class VehicleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    society_id: uuid.UUID
    registration_number: str
    normalized_registration_number: str
    vehicle_type: str
    make: str | None
    model: str | None
    variant: str | None
    color: str | None
    fuel_type: str
    is_ev: bool
    battery_capacity_kwh: Decimal | None
    charging_required: bool
    status: str
    verification_status: str
    notes: str | None
    created_by: uuid.UUID | None
    updated_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    # Associated sub-entities
    associations: list[VehicleAssociationResponse] = []
    verifications: list[VehicleVerificationResponse] = []
    documents: list[VehicleDocumentResponse] = []
    parking_associations: list[VehicleParkingResponse] = []


class VehicleListResponse(BaseModel):
    items: list[VehicleResponse]
    total: int
    page: int
    size: int
    pages: int
