"""Vehicle Management & Vehicle Access Foundation Models (Phase 8)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    event,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.src.database.base import ArchiveMixin, Base, TenantScopedMixin, TimestampMixin

if TYPE_CHECKING:
    from apps.api.src.database.models.identity import User
    from apps.api.src.database.models.society import Society, Unit


class Vehicle(Base, TenantScopedMixin, TimestampMixin):
    """
    Vehicle registered within a society.
    Supports single/joint resident associations, verification status, and EV attributes.
    """

    __tablename__ = "vehicles"
    __table_args__ = (
        CheckConstraint(
            "vehicle_type IN ('FOUR_WHEELER', 'THREE_WHEELER', 'TWO_WHEELER', 'BICYCLE')",
            name="ck_vehicles_vehicle_type",
        ),
        CheckConstraint(
            "fuel_type IN ('PETROL', 'DIESEL', 'CNG', 'ELECTRIC', 'HYBRID', 'OTHER', 'NOT_APPLICABLE')",
            name="ck_vehicles_fuel_type",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'INACTIVE', 'SOLD', 'TRANSFERRED', 'SCRAPPED')",
            name="ck_vehicles_status",
        ),
        CheckConstraint(
            "verification_status IN ('PENDING', 'VERIFIED', 'REJECTED', 'EXPIRED')",
            name="ck_vehicles_verification_status",
        ),
        Index("ix_vehicles_society_status", "society_id", "status"),
        Index("ix_vehicles_society_normalized_reg", "society_id", "normalized_registration_number"),
        Index("ix_vehicles_verification_status", "society_id", "verification_status"),
        Index(
            "uq_vehicles_society_active_normalized_reg",
            "society_id",
            "normalized_registration_number",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
            sqlite_where=text("status = 'ACTIVE'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    registration_number: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    normalized_registration_number: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    vehicle_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    make: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    variant: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    color: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    fuel_type: Mapped[str] = mapped_column(
        String(32),
        default="PETROL",
        nullable=False,
    )
    is_ev: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    battery_capacity_kwh: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 2),
        nullable=True,
    )
    charging_required: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="ACTIVE",
        nullable=False,
    )
    verification_status: Mapped[str] = mapped_column(
        String(32),
        default="PENDING",
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    society: Mapped["Society"] = relationship("Society", backref="vehicles")
    associations: Mapped[list["VehicleResidentAssociation"]] = relationship(
        "VehicleResidentAssociation",
        back_populates="vehicle",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    verifications: Mapped[list["VehicleVerification"]] = relationship(
        "VehicleVerification",
        back_populates="vehicle",
        cascade="all, delete-orphan",
        order_by="VehicleVerification.created_at.desc()",
        lazy="selectin",
    )
    documents: Mapped[list["VehicleDocument"]] = relationship(
        "VehicleDocument",
        back_populates="vehicle",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    parking_associations: Mapped[list["VehicleParkingAssociation"]] = relationship(
        "VehicleParkingAssociation",
        back_populates="vehicle",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    access_records: Mapped[list["VehicleAccessRecord"]] = relationship(
        "VehicleAccessRecord",
        back_populates="vehicle",
        order_by="VehicleAccessRecord.access_time.desc()",
        lazy="selectin",
    )


class VehicleResidentAssociation(Base, TenantScopedMixin, TimestampMixin):
    """
    Association between a vehicle and a resident / unit.
    Decoupled from legal ownership; represents authorization and residency link.
    """

    __tablename__ = "vehicle_resident_associations"
    __table_args__ = (
        CheckConstraint(
            "association_type IN ('OWNER', 'TENANT', 'RESIDENT', 'AUTHORIZED_DELEGATE')",
            name="ck_vehicle_assoc_type",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'ENDED', 'REVOKED')",
            name="ck_vehicle_assoc_status",
        ),
        Index("ix_vehicle_assoc_vehicle_id", "vehicle_id"),
        Index("ix_vehicle_assoc_user_id", "user_id"),
        Index("ix_vehicle_assoc_unit_id", "unit_id"),
        Index("ix_vehicle_assoc_society_status", "society_id", "status"),
        Index(
            "uq_vehicle_assoc_active_primary",
            "society_id",
            "unit_id",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE' AND is_primary = true"),
            sqlite_where=text("status = 'ACTIVE' AND is_primary = 1"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    unit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("units.id", ondelete="RESTRICT"),
        nullable=False,
    )
    association_type: Mapped[str] = mapped_column(
        String(32),
        default="RESIDENT",
        nullable=False,
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    valid_from: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )
    valid_to: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="ACTIVE",
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # Relationships
    vehicle: Mapped["Vehicle"] = relationship("Vehicle", back_populates="associations")
    user: Mapped["User"] = relationship("User")
    unit: Mapped["Unit"] = relationship("Unit")


class VehicleVerification(Base, TenantScopedMixin):
    """
    Verification lifecycle record for a vehicle by society management / security.
    """

    __tablename__ = "vehicle_verifications"
    __table_args__ = (
        CheckConstraint(
            "verification_status IN ('VERIFIED', 'REJECTED', 'EXPIRED')",
            name="ck_vehicle_verif_status",
        ),
        Index("ix_vehicle_verif_vehicle_id", "vehicle_id"),
        Index("ix_vehicle_verif_verifier", "verifier_user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"),
        nullable=False,
    )
    verifier_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    verification_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    verification_date: Mapped[date] = mapped_column(
        Date,
        default=date.today,
        nullable=False,
    )
    reason: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    supporting_document_ref: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    vehicle: Mapped["Vehicle"] = relationship("Vehicle", back_populates="verifications")
    verifier: Mapped["User"] = relationship("User")


class VehicleDocument(Base, TenantScopedMixin, ArchiveMixin):
    """
    Supporting documents for a vehicle (RC, insurance, pollution certificate, permits).
    Supports soft-archival without hard-deleting historical compliance records.
    """

    __tablename__ = "vehicle_documents"
    __table_args__ = (
        CheckConstraint(
            "document_type IN ('RC', 'INSURANCE', 'PUC', 'PERMIT', 'OTHER')",
            name="ck_vehicle_doc_type",
        ),
        Index("ix_vehicle_doc_vehicle_id", "vehicle_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    document_number: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    file_key: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    file_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    file_size_bytes: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    content_type: Mapped[str] = mapped_column(
        String(100),
        default="application/pdf",
        nullable=False,
    )
    valid_from: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    valid_to: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    vehicle: Mapped["Vehicle"] = relationship("Vehicle", back_populates="documents")
    uploader: Mapped["User | None"] = relationship("User")


class VehicleParkingAssociation(Base, TenantScopedMixin, TimestampMixin):
    """
    Clean association boundary between a vehicle and a parking slot.
    Prepares for future full parking slot management.
    """

    __tablename__ = "vehicle_parking_associations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE', 'ENDED')",
            name="ck_vehicle_parking_status",
        ),
        Index("ix_vehicle_parking_vehicle_id", "vehicle_id"),
        Index("ix_vehicle_parking_society_slot", "society_id", "parking_slot_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"),
        nullable=False,
    )
    parking_slot_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    valid_from: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )
    valid_to: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="ACTIVE",
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # Relationships
    vehicle: Mapped["Vehicle"] = relationship("Vehicle", back_populates="parking_associations")


class VehicleAccessRecord(Base, TenantScopedMixin):
    """
    Immutable access log of vehicle gate entry and exit events.
    Supports manual gate operations, future RFID, and future ANPR camera events.
    """

    __tablename__ = "vehicle_access_records"
    __table_args__ = (
        CheckConstraint(
            "access_type IN ('ENTRY', 'EXIT')",
            name="ck_vehicle_access_type",
        ),
        CheckConstraint(
            "detection_method IN ('MANUAL', 'RFID', 'ANPR')",
            name="ck_vehicle_detection_method",
        ),
        Index("ix_vehicle_access_society_time", "society_id", "access_time"),
        Index("ix_vehicle_access_vehicle_id", "vehicle_id"),
        Index("ix_vehicle_access_normalized_reg", "society_id", "normalized_registration_number_snapshot"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("vehicles.id", ondelete="SET NULL"),
        nullable=True,
    )
    registration_number_snapshot: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    normalized_registration_number_snapshot: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    access_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    gate_identifier: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    access_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )
    detection_method: Mapped[str] = mapped_column(
        String(30),
        default="MANUAL",
        nullable=False,
    )
    captured_image_ref: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    operator_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_provider: Mapped[str] = mapped_column(
        String(50),
        default="MANUAL",
        nullable=False,
    )
    confidence_score: Mapped[Decimal | None] = mapped_column(
        Numeric(4, 3),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    vehicle: Mapped["Vehicle | None"] = relationship("Vehicle", back_populates="access_records")
    operator: Mapped["User | None"] = relationship("User")


@event.listens_for(VehicleAccessRecord, "before_update")
def prevent_vehicle_access_record_update(mapper, connection, target):
    from apps.api.src.vehicles.domain.exceptions import VehicleAccessRecordImmutableError

    raise VehicleAccessRecordImmutableError()


@event.listens_for(VehicleAccessRecord, "before_delete")
def prevent_vehicle_access_record_delete(mapper, connection, target):
    from apps.api.src.vehicles.domain.exceptions import VehicleAccessRecordImmutableError

    raise VehicleAccessRecordImmutableError()
