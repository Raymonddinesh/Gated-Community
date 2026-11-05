"""SQLAlchemy ORM Models for Complaints & Helpdesk Domain."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.src.database.base import Base

if TYPE_CHECKING:
    from apps.api.src.database.models.identity import User
    from apps.api.src.database.models.society import Unit
    from apps.api.src.database.models.vehicle import Vehicle
    from apps.api.src.database.models.visitor import Visitor


class ComplaintCategory(Base):
    """Configurable complaint category per society (e.g. Plumbing, Electrical)."""

    __tablename__ = "complaint_categories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # Relationships
    subcategories: Mapped[list["ComplaintSubcategory"]] = relationship(
        "ComplaintSubcategory", back_populates="category", cascade="all, delete-orphan"
    )
    complaints: Mapped[list["Complaint"]] = relationship("Complaint", back_populates="category")

    __table_args__ = (
        UniqueConstraint("society_id", "code", name="uq_complaint_category_society_code"),
        Index("ix_complaint_category_society_name", "society_id", "name"),
    )


class ComplaintSubcategory(Base):
    """Configurable complaint subcategory belonging to a category."""

    __tablename__ = "complaint_subcategories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("complaint_categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # Relationships
    category: Mapped["ComplaintCategory"] = relationship("ComplaintCategory", back_populates="subcategories")
    complaints: Mapped[list["Complaint"]] = relationship("Complaint", back_populates="subcategory")

    __table_args__ = (
        UniqueConstraint("society_id", "category_id", "code", name="uq_complaint_subcategory_code"),
    )


class ComplaintSLAPolicy(Base):
    """Configurable SLA Policy mapping category + priority to target hours."""

    __tablename__ = "complaint_sla_policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("complaint_categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    priority: Mapped[str] = mapped_column(String(20), nullable=False)  # LOW, MEDIUM, HIGH, CRITICAL
    acknowledgement_target_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    resolution_target_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=72)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # Relationships
    category: Mapped[Optional["ComplaintCategory"]] = relationship("ComplaintCategory")

    __table_args__ = (
        CheckConstraint(
            "priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_complaint_sla_priority",
        ),
        UniqueConstraint("society_id", "category_id", "priority", name="uq_complaint_sla_society_cat_prio"),
    )


class Complaint(Base):
    """Core Complaint / Service Request entity."""

    __tablename__ = "complaints"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    complaint_number: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("complaint_categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    subcategory_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("complaint_subcategories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    raised_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    raised_for_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("units.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    priority: Mapped[str] = mapped_column(
        String(20), default="MEDIUM", nullable=False
    )  # LOW, MEDIUM, HIGH, CRITICAL
    source: Mapped[str] = mapped_column(
        String(20), default="WEB", nullable=False
    )  # WEB, MOBILE, ADMIN, SECURITY, VOICE, PHOTO, OTHER
    status: Mapped[str] = mapped_column(
        String(32), default="OPEN", nullable=False
    )  # OPEN, ACKNOWLEDGED, ASSIGNED, IN_PROGRESS, WAITING_FOR_RESIDENT, RESOLVED, REOPENED, CLOSED, CANCELLED
    sla_policy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("complaint_sla_policies.id", ondelete="SET NULL"), nullable=True
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    ack_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Optional boundaries
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="SET NULL"), nullable=True
    )
    visitor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visitors.id", ondelete="SET NULL"), nullable=True
    )
    work_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,  # Forward-compatible reference to future Work Orders
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # Relationships
    category: Mapped["ComplaintCategory"] = relationship("ComplaintCategory", back_populates="complaints")
    subcategory: Mapped[Optional["ComplaintSubcategory"]] = relationship(
        "ComplaintSubcategory", back_populates="complaints"
    )
    raised_by: Mapped["User"] = relationship("User", foreign_keys=[raised_by_user_id])
    raised_for_unit: Mapped[Optional["Unit"]] = relationship("Unit")
    sla_policy: Mapped[Optional["ComplaintSLAPolicy"]] = relationship("ComplaintSLAPolicy")
    vehicle: Mapped[Optional["Vehicle"]] = relationship("Vehicle")
    visitor: Mapped[Optional["Visitor"]] = relationship("Visitor")

    assignments: Mapped[list["ComplaintAssignment"]] = relationship(
        "ComplaintAssignment", back_populates="complaint", cascade="all, delete-orphan"
    )
    comments: Mapped[list["ComplaintComment"]] = relationship(
        "ComplaintComment", back_populates="complaint", cascade="all, delete-orphan"
    )
    attachments: Mapped[list["ComplaintAttachment"]] = relationship(
        "ComplaintAttachment", back_populates="complaint", cascade="all, delete-orphan"
    )
    history: Mapped[list["ComplaintStatusHistory"]] = relationship(
        "ComplaintStatusHistory", back_populates="complaint", cascade="all, delete-orphan"
    )
    escalations: Mapped[list["ComplaintEscalation"]] = relationship(
        "ComplaintEscalation", back_populates="complaint", cascade="all, delete-orphan"
    )
    resolution: Mapped[Optional["ComplaintResolution"]] = relationship(
        "ComplaintResolution", back_populates="complaint", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("society_id", "complaint_number", name="uq_complaints_society_number"),
        CheckConstraint(
            "priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_complaints_priority",
        ),
        CheckConstraint(
            "source IN ('WEB', 'MOBILE', 'ADMIN', 'SECURITY', 'VOICE', 'PHOTO', 'OTHER')",
            name="ck_complaints_source",
        ),
        CheckConstraint(
            "status IN ('OPEN', 'ACKNOWLEDGED', 'ASSIGNED', 'IN_PROGRESS', 'WAITING_FOR_RESIDENT', 'RESOLVED', 'REOPENED', 'CLOSED', 'CANCELLED')",
            name="ck_complaints_status",
        ),
        Index("ix_complaints_society_status", "society_id", "status"),
        Index("ix_complaints_society_raised_by", "society_id", "raised_by_user_id"),
        Index("ix_complaints_society_created", "society_id", "created_at"),
    )


class ComplaintAssignment(Base):
    """Tracks current and historical assignment of complaints."""

    __tablename__ = "complaint_assignments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    complaint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assigned_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    target_type: Mapped[str] = mapped_column(
        String(30), default="INTERNAL_USER", nullable=False
    )  # INTERNAL_USER, TEAM, FUTURE_STAFF, FUTURE_VENDOR
    assigned_to_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    assigned_to_role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    assigned_to_team: Mapped[str | None] = mapped_column(String(100), nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # Relationships
    complaint: Mapped["Complaint"] = relationship("Complaint", back_populates="assignments")
    assigned_by: Mapped["User"] = relationship("User", foreign_keys=[assigned_by_user_id])
    assigned_to_user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[assigned_to_user_id])

    __table_args__ = (
        CheckConstraint(
            "target_type IN ('INTERNAL_USER', 'TEAM', 'FUTURE_STAFF', 'FUTURE_VENDOR')",
            name="ck_complaint_assignment_target_type",
        ),
        Index("ix_complaint_assignment_active", "society_id", "complaint_id", "is_current"),
    )


class ComplaintComment(Base):
    """Communication log attached to complaints (PUBLIC vs INTERNAL notes)."""

    __tablename__ = "complaint_comments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    complaint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    comment_type: Mapped[str] = mapped_column(
        String(20), default="PUBLIC", nullable=False
    )  # PUBLIC, INTERNAL
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # Relationships
    complaint: Mapped["Complaint"] = relationship("Complaint", back_populates="comments")
    author: Mapped["User"] = relationship("User")

    __table_args__ = (
        CheckConstraint(
            "comment_type IN ('PUBLIC', 'INTERNAL')",
            name="ck_complaint_comment_type",
        ),
        Index("ix_complaint_comment_complaint", "society_id", "complaint_id", "created_at"),
    )


class ComplaintAttachment(Base):
    """Evidence photos, audio, video, or documents uploaded for a complaint."""

    __tablename__ = "complaint_attachments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    complaint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False, index=True
    )
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    attachment_type: Mapped[str] = mapped_column(
        String(20), default="PHOTO", nullable=False
    )  # PHOTO, VIDEO, AUDIO, DOCUMENT, OTHER
    file_key: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), default="image/jpeg", nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # Relationships
    complaint: Mapped["Complaint"] = relationship("Complaint", back_populates="attachments")
    uploaded_by: Mapped[Optional["User"]] = relationship("User")

    __table_args__ = (
        CheckConstraint(
            "attachment_type IN ('PHOTO', 'VIDEO', 'AUDIO', 'DOCUMENT', 'OTHER')",
            name="ck_complaint_attachment_type",
        ),
        Index("ix_complaint_attachment_complaint", "society_id", "complaint_id"),
    )


class ComplaintStatusHistory(Base):
    """Audit log of status transitions on a complaint."""

    __tablename__ = "complaint_status_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    complaint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # Relationships
    complaint: Mapped["Complaint"] = relationship("Complaint", back_populates="history")
    actor: Mapped["User"] = relationship("User")

    __table_args__ = (
        Index("ix_complaint_status_history_complaint", "society_id", "complaint_id", "created_at"),
    )


class ComplaintEscalation(Base):
    """Tracks SLA breach escalations."""

    __tablename__ = "complaint_escalations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    complaint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False, index=True
    )
    escalation_level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    escalation_reason: Mapped[str] = mapped_column(String(500), nullable=False)
    triggered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    target_role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", nullable=False)  # ACTIVE, RESOLVED
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # Relationships
    complaint: Mapped["Complaint"] = relationship("Complaint", back_populates="escalations")
    triggered_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[triggered_by_user_id])
    target_user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[target_user_id])

    __table_args__ = (Index("ix_complaint_escalation_complaint", "society_id", "complaint_id", "status"),)


class ComplaintResolution(Base):
    """Final or interim resolution records for complaints."""

    __tablename__ = "complaint_resolutions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    complaint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("complaints.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    resolved_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    resolution_summary: Mapped[str] = mapped_column(Text, nullable=False)
    resolution_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # Relationships
    complaint: Mapped["Complaint"] = relationship("Complaint", back_populates="resolution")
    resolved_by: Mapped["User"] = relationship("User")
