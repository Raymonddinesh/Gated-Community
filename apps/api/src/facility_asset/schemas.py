"""Phase 14 Facility & Asset Management Pydantic Schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from apps.api.src.facility_asset.enums import (
    AssetAssignmentType,
    AssetCriticality,
    AssetDocumentType,
    AssetStatus,
    FacilityAreaStatus,
    FacilityDocumentType,
    FacilityStatus,
    FacilityType,
    MaintenanceLinkType,
)

# ---------------------------------------------------------------------------
# Facility & Area Schemas
# ---------------------------------------------------------------------------


class FacilityAreaCreate(BaseModel):
    area_code: str = Field(..., max_length=50)
    name: str = Field(..., max_length=100)
    description: str | None = Field(default=None, max_length=500)
    floor_level: str | None = Field(default=None, max_length=50)
    max_occupancy: int | None = Field(default=None, ge=0)


class FacilityAreaUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    floor_level: str | None = Field(default=None, max_length=50)
    max_occupancy: int | None = Field(default=None, ge=0)
    status: FacilityAreaStatus | None = None


class FacilityAreaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    facility_id: UUID
    area_code: str
    name: str
    description: str | None = None
    floor_level: str | None = None
    max_occupancy: int | None = None
    status: FacilityAreaStatus
    created_at: datetime
    updated_at: datetime


class FacilityCreate(BaseModel):
    name: str = Field(..., max_length=100)
    facility_type: FacilityType
    description: str | None = Field(default=None, max_length=500)
    capacity: int | None = Field(default=None, ge=0)
    location_summary: str | None = Field(default=None, max_length=255)
    is_bookable_separately: bool = False
    areas: list[FacilityAreaCreate] = Field(default_factory=list)


class FacilityUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    facility_type: FacilityType | None = None
    description: str | None = Field(default=None, max_length=500)
    capacity: int | None = Field(default=None, ge=0)
    location_summary: str | None = Field(default=None, max_length=255)
    is_bookable_separately: bool | None = None


class FacilityStatusUpdate(BaseModel):
    status: FacilityStatus
    reason: str | None = Field(default=None, max_length=500)


class FacilityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    facility_code: str
    name: str
    facility_type: FacilityType
    description: str | None = None
    status: FacilityStatus
    capacity: int | None = None
    location_summary: str | None = None
    is_bookable_separately: bool
    created_at: datetime
    updated_at: datetime
    areas: list[FacilityAreaResponse] = Field(default_factory=list)


class FacilityListResponse(BaseModel):
    items: list[FacilityResponse]
    total: int
    page: int
    size: int


# ---------------------------------------------------------------------------
# Asset Category Schemas
# ---------------------------------------------------------------------------


class AssetCategoryCreate(BaseModel):
    category_code: str = Field(..., max_length=50)
    name: str = Field(..., max_length=100)
    description: str | None = Field(default=None, max_length=500)
    parent_id: UUID | None = None
    is_critical: bool = False


class AssetCategoryUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    parent_id: UUID | None = None
    is_critical: bool | None = None


class AssetCategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    category_code: str
    name: str
    description: str | None = None
    parent_id: UUID | None = None
    is_critical: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Asset Schemas
# ---------------------------------------------------------------------------


class AssetCreate(BaseModel):
    name: str = Field(..., max_length=100)
    category_id: UUID
    facility_id: UUID | None = None
    facility_area_id: UUID | None = None
    serial_number: str | None = Field(default=None, max_length=100)
    model_number: str | None = Field(default=None, max_length=100)
    manufacturer: str | None = Field(default=None, max_length=100)
    vendor_id: UUID | None = None
    purchase_date: datetime | None = None
    warranty_expiry_date: datetime | None = None
    criticality: AssetCriticality = AssetCriticality.MEDIUM
    estimated_lifespan_months: int | None = Field(default=None, ge=0)


class AssetUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    category_id: UUID | None = None
    facility_id: UUID | None = None
    facility_area_id: UUID | None = None
    serial_number: str | None = Field(default=None, max_length=100)
    model_number: str | None = Field(default=None, max_length=100)
    manufacturer: str | None = Field(default=None, max_length=100)
    vendor_id: UUID | None = None
    purchase_date: datetime | None = None
    warranty_expiry_date: datetime | None = None
    criticality: AssetCriticality | None = None
    estimated_lifespan_months: int | None = Field(default=None, ge=0)


class AssetStatusUpdate(BaseModel):
    status: AssetStatus
    reason: str | None = Field(None, max_length=500)


class AssetLocationMove(BaseModel):
    facility_id: UUID | None = None
    facility_area_id: UUID | None = None
    location_details: str | None = Field(None, max_length=500)
    reason: str | None = Field(None, max_length=500)


class AssetAssignmentCreate(BaseModel):
    assigned_to_type: AssetAssignmentType
    assigned_staff_id: UUID | None = None
    assigned_vendor_id: UUID | None = None
    notes: str | None = Field(None, max_length=500)


class AssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    asset_code: str
    name: str
    category_id: UUID
    facility_id: UUID | None = None
    facility_area_id: UUID | None = None
    serial_number: str | None = None
    model_number: str | None = None
    manufacturer: str | None = None
    vendor_id: UUID | None = None
    purchase_date: datetime | None = None
    warranty_expiry_date: datetime | None = None
    status: AssetStatus
    criticality: AssetCriticality
    estimated_lifespan_months: int | None = None
    created_at: datetime
    updated_at: datetime


class AssetListResponse(BaseModel):
    items: list[AssetResponse]
    total: int
    page: int
    size: int


class AssetLocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    asset_id: UUID
    facility_id: UUID | None = None
    facility_area_id: UUID | None = None
    location_details: str | None = None
    moved_at: datetime
    moved_by_user_id: UUID | None = None
    reason: str | None = None
    created_at: datetime


class AssetStatusHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    asset_id: UUID
    old_status: str
    new_status: str
    changed_by_user_id: UUID | None = None
    reason: str | None = None
    changed_at: datetime


class AssetAssignmentHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    asset_id: UUID
    assigned_to_type: AssetAssignmentType
    assigned_staff_id: UUID | None = None
    assigned_vendor_id: UUID | None = None
    assigned_at: datetime
    unassigned_at: datetime | None = None
    assigned_by_user_id: UUID | None = None
    notes: str | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Document & Maintenance Link Schemas
# ---------------------------------------------------------------------------


class AssetDocumentCreate(BaseModel):
    document_type: AssetDocumentType
    title: str = Field(..., max_length=255)
    file_path: str = Field(..., max_length=500)
    file_size_bytes: int | None = None
    mime_type: str | None = Field(None, max_length=100)


class AssetDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    asset_id: UUID
    document_type: AssetDocumentType
    title: str
    file_path: str
    file_size_bytes: int | None = None
    mime_type: str | None = None
    uploaded_by_user_id: UUID | None = None
    uploaded_at: datetime


class FacilityDocumentCreate(BaseModel):
    document_type: FacilityDocumentType
    title: str = Field(..., max_length=255)
    file_path: str = Field(..., max_length=500)
    file_size_bytes: int | None = None
    mime_type: str | None = Field(None, max_length=100)


class FacilityDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    facility_id: UUID
    document_type: FacilityDocumentType
    title: str
    file_path: str
    file_size_bytes: int | None = None
    mime_type: str | None = None
    uploaded_by_user_id: UUID | None = None
    uploaded_at: datetime


class AssetMaintenanceLinkCreate(BaseModel):
    asset_id: UUID | None = None
    facility_id: UUID | None = None
    work_order_id: UUID | None = None
    complaint_id: UUID | None = None
    link_type: MaintenanceLinkType = MaintenanceLinkType.CORRECTIVE
    notes: str | None = Field(None, max_length=500)


class AssetMaintenanceLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    asset_id: UUID | None = None
    facility_id: UUID | None = None
    work_order_id: UUID | None = None
    complaint_id: UUID | None = None
    link_type: MaintenanceLinkType
    linked_at: datetime
    linked_by_user_id: UUID | None = None
    notes: str | None = None
    created_at: datetime
