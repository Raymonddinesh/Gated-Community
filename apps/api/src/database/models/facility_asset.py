"""Facility & Asset Management Database Models."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.src.database.base import Base


class Facility(Base):
    """Facility model representing physical facilities/amenities in a society."""

    __tablename__ = "facilities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    facility_code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    facility_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default="ACTIVE")
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location_summary: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_bookable_separately: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    areas: Mapped[list["FacilityArea"]] = relationship(
        "FacilityArea", back_populates="facility", cascade="all, delete-orphan"
    )
    documents: Mapped[list["FacilityDocument"]] = relationship(
        "FacilityDocument", back_populates="facility", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("society_id", "facility_code", name="uq_facility_society_code"),
        Index("ix_facility_society_code", "society_id", "facility_code"),
        Index("ix_facility_society_type", "society_id", "facility_type"),
    )


class FacilityArea(Base):
    """Sub-area within a facility (e.g. Badminton Court 1 inside Clubhouse)."""

    __tablename__ = "facility_areas"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False
    )
    area_code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    floor_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    max_occupancy: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    facility: Mapped["Facility"] = relationship("Facility", back_populates="areas")

    __table_args__ = (
        UniqueConstraint("facility_id", "area_code", name="uq_facility_area_facility_code"),
        Index("ix_facility_area_society_facility", "society_id", "facility_id"),
    )


class AssetCategory(Base):
    """Hierarchical category model for society physical assets."""

    __tablename__ = "asset_categories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    category_code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset_categories.id", ondelete="SET NULL"), nullable=True
    )
    is_critical: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        UniqueConstraint("society_id", "category_code", name="uq_asset_category_society_code"),
        Index("ix_asset_category_society_code", "society_id", "category_code"),
    )


class Asset(Base):
    """Core Asset model representing physical equipment, infrastructure, and tools."""

    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    asset_code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asset_categories.id", ondelete="RESTRICT"), nullable=False
    )
    facility_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="SET NULL"), nullable=True
    )
    facility_area_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facility_areas.id", ondelete="SET NULL"), nullable=True
    )
    serial_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String(100), nullable=True)
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendor_profiles.id", ondelete="SET NULL"), nullable=True
    )
    purchase_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    warranty_expiry_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default="IN_SERVICE")
    criticality: Mapped[str] = mapped_column(String(50), nullable=False, server_default="MEDIUM")
    estimated_lifespan_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    category: Mapped["AssetCategory"] = relationship("AssetCategory")
    facility: Mapped["Facility | None"] = relationship("Facility")
    facility_area: Mapped["FacilityArea | None"] = relationship("FacilityArea")
    documents: Mapped[list["AssetDocument"]] = relationship(
        "AssetDocument", back_populates="asset", cascade="all, delete-orphan"
    )
    status_history: Mapped[list["AssetStatusHistory"]] = relationship(
        "AssetStatusHistory", back_populates="asset", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("society_id", "asset_code", name="uq_asset_society_code"),
        Index("ix_asset_society_code", "society_id", "asset_code"),
        Index("ix_asset_society_status", "society_id", "status"),
        Index("ix_asset_society_category", "society_id", "category_id"),
    )


class AssetLocation(Base):
    """Historical tracking of physical locations of assets."""

    __tablename__ = "asset_locations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    facility_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="SET NULL"), nullable=True
    )
    facility_area_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facility_areas.id", ondelete="SET NULL"), nullable=True
    )
    location_details: Mapped[str | None] = mapped_column(String(500), nullable=True)
    moved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    moved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (Index("ix_asset_location_society_asset", "society_id", "asset_id"),)


class AssetStatusHistory(Base):
    """Audit log of status changes for assets."""

    __tablename__ = "asset_status_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    old_status: Mapped[str] = mapped_column(String(50), nullable=False)
    new_status: Mapped[str] = mapped_column(String(50), nullable=False)
    changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    asset: Mapped["Asset"] = relationship("Asset", back_populates="status_history")

    __table_args__ = (Index("ix_asset_status_history_society_asset", "society_id", "asset_id"),)


class AssetAssignmentHistory(Base):
    """Tracking of asset assignment to staff, vendor, department or location."""

    __tablename__ = "asset_assignment_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    assigned_to_type: Mapped[str] = mapped_column(String(50), nullable=False)
    assigned_staff_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_profiles.id", ondelete="SET NULL"), nullable=True
    )
    assigned_vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendor_profiles.id", ondelete="SET NULL"), nullable=True
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    unassigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (Index("ix_asset_assignment_history_society_asset", "society_id", "asset_id"),)


class AssetDocument(Base):
    """Documents attached to an Asset (manual, warranty, invoice, etc.)."""

    __tablename__ = "asset_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    document_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    asset: Mapped["Asset"] = relationship("Asset", back_populates="documents")

    __table_args__ = (Index("ix_asset_documents_society_asset", "society_id", "asset_id"),)


class AssetMaintenanceLink(Base):
    """Links Assets or Facilities to Maintenance Work Orders or Complaints without duplicating lifecycles."""

    __tablename__ = "asset_maintenance_links"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=True
    )
    facility_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="CASCADE"), nullable=True
    )
    work_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("maintenance_work_orders.id", ondelete="SET NULL"), nullable=True
    )
    complaint_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("complaints.id", ondelete="SET NULL"), nullable=True
    )
    link_type: Mapped[str] = mapped_column(String(50), nullable=False, server_default="CORRECTIVE")
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    linked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        Index("ix_asset_maint_link_society_asset", "society_id", "asset_id"),
        Index("ix_asset_maint_link_society_facility", "society_id", "facility_id"),
        Index("ix_asset_maint_link_society_wo", "society_id", "work_order_id"),
    )


class FacilityDocument(Base):
    """Documents attached to a Facility (layout plans, permits, safety certificates)."""

    __tablename__ = "facility_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False
    )
    document_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    facility: Mapped["Facility"] = relationship("Facility", back_populates="documents")

    __table_args__ = (Index("ix_facility_documents_society_facility", "society_id", "facility_id"),)
