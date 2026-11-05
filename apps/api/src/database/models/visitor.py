"""Visitor & Security Management Foundation Models (Phase 9)."""

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    event,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.src.database.base import ArchiveMixin, Base, TenantScopedMixin, TimestampMixin

if TYPE_CHECKING:
    from apps.api.src.database.models.identity import User
    from apps.api.src.database.models.society import Society, Unit
    from apps.api.src.database.models.vehicle import Vehicle


class Visitor(Base, TenantScopedMixin, TimestampMixin):
    """
    Visitor profile registered within a society.
    Represents an external individual visiting residents or units.
    """

    __tablename__ = "visitors"
    __table_args__ = (
        CheckConstraint(
            "visitor_type IN ('GUEST', 'DELIVERY', 'SERVICE', 'CAB', 'OTHER')",
            name="ck_visitors_visitor_type",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'BLOCKED', 'ARCHIVED')",
            name="ck_visitors_status",
        ),
        Index("ix_visitors_society_phone", "society_id", "phone"),
        Index("ix_visitors_society_type", "society_id", "visitor_type"),
        Index("ix_visitors_society_status", "society_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    phone: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    alternate_phone: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )
    visitor_type: Mapped[str] = mapped_column(
        String(32),
        default="GUEST",
        nullable=False,
    )
    identification_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    identification_number: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    photo_file_key: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="ACTIVE",
        nullable=False,
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
    society: Mapped["Society"] = relationship("Society", backref="visitors")
    invitations: Mapped[list["VisitorInvitation"]] = relationship(
        "VisitorInvitation",
        back_populates="visitor",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    approvals: Mapped[list["VisitorApproval"]] = relationship(
        "VisitorApproval",
        back_populates="visitor",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    access_records: Mapped[list["VisitorAccessRecord"]] = relationship(
        "VisitorAccessRecord",
        back_populates="visitor",
        order_by="VisitorAccessRecord.access_time.desc()",
        lazy="selectin",
    )
    documents: Mapped[list["VisitorDocument"]] = relationship(
        "VisitorDocument",
        back_populates="visitor",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class VisitorInvitation(Base, TenantScopedMixin, TimestampMixin):
    """
    Pre-approved visitor invitation created by a resident.
    Time-bound entry authorization for guests, deliveries, or service personnel.
    """

    __tablename__ = "visitor_invitations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED', 'CANCELLED', 'USED')",
            name="ck_visitor_invitations_status",
        ),
        Index("ix_visitor_invitations_society_unit", "society_id", "unit_id"),
        Index("ix_visitor_invitations_society_host", "society_id", "host_user_id"),
        Index("ix_visitor_invitations_expected_date", "society_id", "expected_date"),
        Index("ix_visitor_invitations_pass_code", "society_id", "pass_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    visitor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("visitors.id", ondelete="CASCADE"),
        nullable=False,
    )
    host_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    unit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("units.id", ondelete="RESTRICT"),
        nullable=False,
    )
    expected_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )
    expected_arrival_window_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expected_arrival_window_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expected_departure: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    purpose: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    pass_code: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )
    access_code_hash: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    delivery_company: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    service_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="PENDING",
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # Relationships
    visitor: Mapped["Visitor"] = relationship("Visitor", back_populates="invitations", lazy="selectin")
    host: Mapped["User"] = relationship("User", lazy="selectin")
    unit: Mapped["Unit"] = relationship("Unit", lazy="selectin")


class VisitorApproval(Base, TenantScopedMixin):
    """
    Approval workflow record capturing resident consent for visitor entry.
    """

    __tablename__ = "visitor_approvals"
    __table_args__ = (
        CheckConstraint(
            "approval_status IN ('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED')",
            name="ck_visitor_approvals_status",
        ),
        Index("ix_visitor_approvals_society_visitor", "society_id", "visitor_id"),
        Index("ix_visitor_approvals_society_unit", "society_id", "unit_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    visitor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("visitors.id", ondelete="CASCADE"),
        nullable=False,
    )
    invitation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("visitor_invitations.id", ondelete="SET NULL"),
        nullable=True,
    )
    unit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("units.id", ondelete="RESTRICT"),
        nullable=False,
    )
    approving_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    approval_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    decision_reason: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    decision_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    visitor: Mapped["Visitor"] = relationship("Visitor", back_populates="approvals", lazy="selectin")
    invitation: Mapped["VisitorInvitation | None"] = relationship("VisitorInvitation", lazy="selectin")
    unit: Mapped["Unit"] = relationship("Unit", lazy="selectin")
    approving_user: Mapped["User"] = relationship("User", lazy="selectin")


class VisitorAccessRecord(Base, TenantScopedMixin):
    """
    Immutable gate access record for visitor entry and exit events.
    Appended upon visitor check-in and updated only for exit timestamp / exit gate.
    """

    __tablename__ = "visitor_access_records"
    __table_args__ = (
        CheckConstraint(
            "access_type IN ('ENTRY', 'EXIT')",
            name="ck_visitor_access_type",
        ),
        CheckConstraint(
            "entry_method IN ('MANUAL', 'QR', 'OTP', 'PRE_APPROVED')",
            name="ck_visitor_entry_method",
        ),
        Index("ix_visitor_access_society_time", "society_id", "access_time"),
        Index("ix_visitor_access_visitor_id", "visitor_id"),
        Index("ix_visitor_access_unit_id", "society_id", "unit_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    visitor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("visitors.id", ondelete="CASCADE"),
        nullable=False,
    )
    invitation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("visitor_invitations.id", ondelete="SET NULL"),
        nullable=True,
    )
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("visitor_approvals.id", ondelete="SET NULL"),
        nullable=True,
    )
    unit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("units.id", ondelete="RESTRICT"),
        nullable=False,
    )
    host_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    security_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("vehicles.id", ondelete="SET NULL"),
        nullable=True,
    )
    visitor_name_snapshot: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    visitor_phone_snapshot: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    visitor_type_snapshot: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    gate_identifier: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    access_type: Mapped[str] = mapped_column(
        String(20),
        default="ENTRY",
        nullable=False,
    )
    access_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )
    entry_method: Mapped[str] = mapped_column(
        String(30),
        default="MANUAL",
        nullable=False,
    )
    exit_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    exit_gate_identifier: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    exit_security_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    exit_method: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )
    delivery_company: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    service_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    emergency_override_reason: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    visitor: Mapped["Visitor"] = relationship("Visitor", back_populates="access_records")
    unit: Mapped["Unit"] = relationship("Unit")
    host: Mapped["User"] = relationship("User", foreign_keys=[host_user_id])
    security_user: Mapped["User | None"] = relationship("User", foreign_keys=[security_user_id])
    vehicle: Mapped["Vehicle | None"] = relationship("Vehicle")


class VisitorDocument(Base, TenantScopedMixin, ArchiveMixin):
    """
    Supporting identification photos or documents for a visitor.
    Supports soft archival without hard-deleting records.
    """

    __tablename__ = "visitor_documents"
    __table_args__ = (
        CheckConstraint(
            "document_type IN ('PHOTO', 'ID_CARD', 'DRIVING_LICENSE', 'PASSPORT', 'OTHER')",
            name="ck_visitor_doc_type",
        ),
        Index("ix_visitor_doc_visitor_id", "visitor_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    visitor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("visitors.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
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
        default="image/jpeg",
        nullable=False,
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
    visitor: Mapped["Visitor"] = relationship("Visitor", back_populates="documents")
    uploader: Mapped["User | None"] = relationship("User")


@event.listens_for(VisitorAccessRecord, "before_delete")
def prevent_visitor_access_record_delete(mapper, connection, target):
    from apps.api.src.visitors.domain.exceptions import VisitorAccessRecordImmutableError

    raise VisitorAccessRecordImmutableError()
