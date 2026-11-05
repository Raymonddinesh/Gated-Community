"""Pydantic schemas for Resident, Ownership, Occupancy, Household, and Self-Service API."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Profile Completeness
# ---------------------------------------------------------------------------
class ProfileCompleteness(BaseModel):
    """Deterministic profile completeness summary."""

    is_complete: bool
    score_percent: int
    missing_required: list[str]
    missing_fields: list[str]


# ---------------------------------------------------------------------------
# Resident Profile Schemas
# ---------------------------------------------------------------------------
class ResidentProfileBase(BaseModel):
    emergency_contact_name: str | None = Field(None, max_length=150)
    emergency_contact_phone: str | None = Field(None, max_length=32)
    alternate_phone: str | None = Field(None, max_length=32)
    preferred_contact_method: str = Field("APP", max_length=32)
    preferred_language: str = Field("en", max_length=10)
    accessibility_preferences: dict[str, Any] = Field(default_factory=dict)
    communication_preferences: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = Field(None, max_length=500)


class ResidentProfileUpdate(BaseModel):
    """Administrative or self-service update of resident preferences."""

    emergency_contact_name: str | None = Field(default=None, max_length=150)
    emergency_contact_phone: str | None = Field(default=None, max_length=32)
    alternate_phone: str | None = Field(default=None, max_length=32)
    preferred_contact_method: str | None = Field(default=None, max_length=32)
    preferred_language: str | None = Field(default=None, max_length=10)
    accessibility_preferences: dict[str, Any] | None = None
    communication_preferences: dict[str, Any] | None = None
    notes: str | None = Field(default=None, max_length=500)


class EmergencyContactUpdate(BaseModel):
    """Targeted update for emergency contact."""

    emergency_contact_name: str = Field(..., min_length=2, max_length=150)
    emergency_contact_phone: str = Field(..., min_length=5, max_length=32)


class ResidentResponse(BaseModel):
    """Complete resident representation with privacy masking applied where appropriate."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    society_id: UUID
    first_name: str
    last_name: str
    display_name: str
    phone: str | None
    alternate_phone: str | None
    email: str | None
    emergency_contact_name: str | None
    emergency_contact_phone: str | None
    preferred_contact_method: str
    preferred_language: str
    accessibility_preferences: dict[str, Any]
    communication_preferences: dict[str, Any]
    status: str
    notes: str | None
    completeness: ProfileCompleteness | None = None
    created_at: datetime
    updated_at: datetime


class ResidentCreateRequest(BaseModel):
    """Associate an existing User as a resident profile in the current society."""

    user_id: UUID
    alternate_phone: str | None = Field(None, max_length=32)
    emergency_contact_name: str | None = Field(None, max_length=150)
    emergency_contact_phone: str | None = Field(None, max_length=32)
    preferred_language: str = Field("en", max_length=10)
    preferred_contact_method: str = Field("APP", max_length=32)
    notes: str | None = Field(None, max_length=500)


# ---------------------------------------------------------------------------
# Occupancy Schemas
# ---------------------------------------------------------------------------
class UnitOccupancyCreate(BaseModel):
    """Move-in / create occupancy request."""

    user_id: UUID
    relationship_type: str = Field("TENANT", max_length=32)  # OWNER, TENANT, etc.
    is_primary_contact: bool = False
    valid_from: date
    valid_to: date | None = None
    notes: str | None = Field(None, max_length=500)


class UnitOccupancyUpdate(BaseModel):
    """Update occupancy details."""

    is_primary_contact: bool | None = None
    valid_to: date | None = None
    status: str | None = None
    notes: str | None = Field(None, max_length=500)


class UnitOccupancyEndRequest(BaseModel):
    """Move-out / end occupancy request."""

    valid_to: date | None = None
    reason: str | None = Field(None, max_length=255)


class UnitOccupancyResponse(BaseModel):
    """Occupancy record response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    unit_id: UUID
    user_id: UUID
    user_name: str
    user_phone: str | None
    user_email: str | None
    relationship_type: str
    is_primary_contact: bool
    valid_from: date | None
    valid_to: date | None
    status: str
    notes: str | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Ownership Schemas
# ---------------------------------------------------------------------------
class UnitOwnershipCreate(BaseModel):
    """Add owner or joint co-owner to a unit."""

    user_id: UUID
    ownership_percentage: Decimal = Field(default=Decimal("100.00"), gt=0, le=100)
    start_date: date
    is_primary: bool = True
    notes: str | None = Field(None, max_length=500)


class UnitOwnershipUpdate(BaseModel):
    """Update existing ownership record."""

    ownership_percentage: Decimal | None = Field(None, gt=0, le=100)
    is_primary: bool | None = None
    notes: str | None = Field(None, max_length=500)


class UnitOwnershipEndRequest(BaseModel):
    """End or transfer ownership."""

    end_date: date | None = None
    reason: str | None = Field(None, max_length=255)


class UnitOwnershipTransferRequest(BaseModel):
    """Schema for transferring full or partial ownership to another user."""

    new_owner_user_id: UUID = Field(..., description="Target user receiving ownership share.")
    transfer_percentage: Decimal = Field(..., gt=0, le=100, description="Percentage share to transfer.")
    transfer_date: date | None = Field(
        default=None, description="Effective transfer date (defaults to today)."
    )
    reason: str | None = Field(default=None, max_length=255, description="Transfer reason or deed reference.")
    is_primary: bool = Field(default=True, description="Designate new owner as primary title contact.")


class UnitOwnershipResponse(BaseModel):
    """Unit ownership record response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    unit_id: UUID
    user_id: UUID
    user_name: str
    user_phone: str | None
    user_email: str | None
    ownership_percentage: Decimal
    start_date: date
    end_date: date | None
    is_primary: bool
    status: str
    notes: str | None
    created_at: datetime
    updated_at: datetime


class UnitOwnershipTransferResponse(BaseModel):
    """Result of atomic ownership transfer operation."""

    source_ownership: UnitOwnershipResponse
    new_ownership: UnitOwnershipResponse


# ---------------------------------------------------------------------------
# Family Member Schemas
# ---------------------------------------------------------------------------
class FamilyMemberCreate(BaseModel):
    """Add a family member to a household."""

    name: str = Field(..., min_length=2, max_length=150)
    relationship: str = Field(..., max_length=50)  # SPOUSE, CHILD, PARENT, etc.
    phone: str | None = Field(None, max_length=32)
    email: str | None = None
    user_id: UUID | None = None
    access_scope: dict[str, Any] = Field(default_factory=dict)


class FamilyMemberUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=150)
    relationship: str | None = Field(None, max_length=50)
    phone: str | None = Field(None, max_length=32)
    email: str | None = None
    access_scope: dict[str, Any] | None = None
    status: str | None = None


class FamilyMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    unit_id: UUID
    primary_resident_user_id: UUID
    user_id: UUID | None
    name: str
    relationship: str
    phone: str | None
    email: str | None
    access_scope: dict[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Delegate Schemas
# ---------------------------------------------------------------------------
class DelegateCreate(BaseModel):
    """Grant delegation to another user for unit actions."""

    unit_id: UUID
    delegate_user_id: UUID
    permissions: list[str] = Field(..., min_length=1)
    valid_from: date
    valid_to: date | None = None
    notes: str | None = Field(default=None, max_length=500)


class DelegateRevokeRequest(BaseModel):
    """Revoke a previously granted delegation."""

    reason: str | None = Field(None, max_length=255)


class DelegateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    unit_id: UUID
    delegator_user_id: UUID
    delegator_name: str
    delegate_user_id: UUID
    delegate_name: str
    delegate_phone: str | None
    delegate_email: str | None
    permissions: list[str]
    valid_from: date
    valid_to: date | None
    status: str
    revoked_at: datetime | None
    revoked_by: UUID | None
    revocation_reason: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Self-Service & My Home Schemas
# ---------------------------------------------------------------------------
class MyHomeUnitSummary(BaseModel):
    unit_id: UUID
    unit_number: str
    block_name: str
    floor_number: int
    unit_type: str
    carpet_area_sqft: float | None
    occupancy_status: str


class MyHomeResponse(BaseModel):
    """Aggregated self-service response for 'My Home' / 'My Household' view."""

    resident: ResidentResponse
    unit: MyHomeUnitSummary | None
    my_occupancy: UnitOccupancyResponse | None
    co_occupants: list[UnitOccupancyResponse]
    owners: list[UnitOwnershipResponse]
    family_members: list[FamilyMemberResponse]
    delegates: list[DelegateResponse]
    easy_mode: bool = False
