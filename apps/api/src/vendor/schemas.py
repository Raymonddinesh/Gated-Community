"""Vendor Management Pydantic Schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from apps.api.src.vendor.domain.enums import (
    PreferredContactMethod,
    VendorDocumentType,
    VendorStatus,
    VendorType,
)


# --- Vendor Category Schemas ---
class VendorCategoryBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    code: str = Field(..., min_length=2, max_length=50, pattern=r"^[A-Z0-9_\-]+$")
    description: str | None = Field(None, max_length=500)
    is_active: bool = True
    display_order: int = Field(0, ge=0)


class VendorCategoryCreate(VendorCategoryBase):
    pass


class VendorCategoryUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=100)
    description: str | None = Field(None, max_length=500)
    is_active: bool | None = None
    display_order: int | None = Field(None, ge=0)


class VendorCategoryResponse(VendorCategoryBase):
    id: UUID
    society_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Vendor Contact Schemas ---
class VendorContactBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    designation: str | None = Field(None, max_length=100)
    phone: str = Field(..., min_length=8, max_length=32)
    alternate_phone: str | None = Field(None, max_length=32)
    email: str | None = Field(None, max_length=255)
    preferred_contact_method: PreferredContactMethod = PreferredContactMethod.PHONE
    is_primary: bool = False


class VendorContactCreate(VendorContactBase):
    pass


class VendorContactUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=150)
    designation: str | None = Field(None, max_length=100)
    phone: str | None = Field(None, min_length=8, max_length=32)
    alternate_phone: str | None = Field(None, max_length=32)
    email: str | None = Field(None, max_length=255)
    preferred_contact_method: PreferredContactMethod | None = None
    is_primary: bool | None = None


class VendorContactResponse(VendorContactBase):
    id: UUID
    society_id: UUID
    vendor_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Vendor Address Schemas ---
class VendorAddressBase(BaseModel):
    address_line1: str = Field(..., min_length=3, max_length=255)
    address_line2: str | None = Field(None, max_length=255)
    city: str = Field(..., min_length=2, max_length=100)
    state: str = Field(..., min_length=2, max_length=100)
    postal_code: str = Field(..., min_length=3, max_length=20)
    country: str = Field("IN", min_length=2, max_length=2)
    is_primary: bool = True


class VendorAddressCreate(VendorAddressBase):
    pass


class VendorAddressUpdate(BaseModel):
    address_line1: str | None = Field(None, min_length=3, max_length=255)
    address_line2: str | None = Field(None, max_length=255)
    city: str | None = Field(None, min_length=2, max_length=100)
    state: str | None = Field(None, min_length=2, max_length=100)
    postal_code: str | None = Field(None, min_length=3, max_length=20)
    country: str | None = Field(None, min_length=2, max_length=2)
    is_primary: bool | None = None


class VendorAddressResponse(VendorAddressBase):
    id: UUID
    society_id: UUID
    vendor_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Vendor Service Schemas ---
class VendorServiceBase(BaseModel):
    service_name: str = Field(..., min_length=2, max_length=150)
    description: str | None = None
    category_id: UUID | None = None
    is_active: bool = True


class VendorServiceCreate(VendorServiceBase):
    pass


class VendorServiceUpdate(BaseModel):
    service_name: str | None = Field(None, min_length=2, max_length=150)
    description: str | None = None
    category_id: UUID | None = None
    is_active: bool | None = None


class VendorServiceResponse(VendorServiceBase):
    id: UUID
    society_id: UUID
    vendor_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Vendor Document Schemas ---
class VendorDocumentCreate(BaseModel):
    document_type: VendorDocumentType = VendorDocumentType.REGISTRATION
    original_filename: str = Field(..., min_length=1, max_length=255)
    content_type: str = Field(..., min_length=1, max_length=100)
    file_size: int = Field(..., gt=0)
    checksum: str | None = Field(None, max_length=64)


class VendorDocumentResponse(BaseModel):
    id: UUID
    society_id: UUID
    vendor_id: UUID
    document_type: VendorDocumentType
    storage_key: str
    original_filename: str
    content_type: str
    file_size: int
    checksum: str | None
    uploaded_by_user_id: UUID
    created_at: datetime
    archived_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


# --- Vendor Status Schemas ---
class VendorStatusUpdate(BaseModel):
    target_status: VendorStatus
    reason: str | None = Field(None, max_length=1000)


class VendorStatusHistoryResponse(BaseModel):
    id: UUID
    society_id: UUID
    vendor_id: UUID
    from_status: str | None
    to_status: str
    changed_by_user_id: UUID
    reason: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Vendor Assignment History Schemas ---
class VendorAssignmentHistoryResponse(BaseModel):
    id: UUID
    society_id: UUID
    vendor_id: UUID
    work_order_id: UUID | None
    event_type: str
    notes: str | None
    actor_user_id: UUID | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Vendor Profile Core Schemas ---
class VendorProfileCreate(BaseModel):
    legal_name: str = Field(..., min_length=2, max_length=200)
    display_name: str = Field(..., min_length=2, max_length=200)
    vendor_type: VendorType = VendorType.COMPANY
    description: str | None = None
    primary_category_id: UUID | None = None
    status: VendorStatus = VendorStatus.ONBOARDING

    # Optional embedded sub-resources on creation
    contacts: list[VendorContactCreate] = Field(default_factory=list)
    addresses: list[VendorAddressCreate] = Field(default_factory=list)
    services: list[VendorServiceCreate] = Field(default_factory=list)


class VendorProfileUpdate(BaseModel):
    legal_name: str | None = Field(None, min_length=2, max_length=200)
    display_name: str | None = Field(None, min_length=2, max_length=200)
    vendor_type: VendorType | None = None
    description: str | None = None
    primary_category_id: UUID | None = None


class VendorProfileResponse(BaseModel):
    id: UUID
    society_id: UUID
    vendor_code: str
    legal_name: str
    display_name: str
    vendor_type: VendorType
    description: str | None
    primary_category_id: UUID | None
    status: VendorStatus
    created_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None

    primary_category: VendorCategoryResponse | None = None
    contacts: list[VendorContactResponse] = Field(default_factory=list)
    addresses: list[VendorAddressResponse] = Field(default_factory=list)
    services: list[VendorServiceResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class VendorProfileListResponse(BaseModel):
    items: list[VendorProfileResponse]
    total: int
    page: int
    page_size: int
