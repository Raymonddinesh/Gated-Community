"""SQLAlchemy ORM Models for Maintenance & Work Order Management Domain."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.src.database.base import Base

if TYPE_CHECKING:
    from apps.api.src.database.models.complaint import Complaint
    from apps.api.src.database.models.identity import User
    from apps.api.src.database.models.society import Block, Unit
    from apps.api.src.database.models.vehicle import Vehicle
    from apps.api.src.database.models.visitor import Visitor


class MaintenanceCategory(Base):
    """Configurable maintenance category per society (e.g. Plumbing, Electrical, Lift)."""

    __tablename__ = "maintenance_categories"

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
    subcategories: Mapped[list["MaintenanceSubcategory"]] = relationship(
        "MaintenanceSubcategory", back_populates="category", cascade="all, delete-orphan"
    )
    work_orders: Mapped[list["MaintenanceWorkOrder"]] = relationship(
        "MaintenanceWorkOrder", back_populates="category"
    )

    __table_args__ = (
        UniqueConstraint("society_id", "code", name="uq_maintenance_category_society_code"),
        Index("ix_maintenance_category_society_name", "society_id", "name"),
    )


class MaintenanceSubcategory(Base):
    """Configurable maintenance subcategory belonging to a category."""

    __tablename__ = "maintenance_subcategories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("maintenance_categories.id", ondelete="CASCADE"),
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
    category: Mapped["MaintenanceCategory"] = relationship(
        "MaintenanceCategory", back_populates="subcategories"
    )
    work_orders: Mapped[list["MaintenanceWorkOrder"]] = relationship(
        "MaintenanceWorkOrder", back_populates="subcategory"
    )

    __table_args__ = (
        UniqueConstraint("society_id", "category_id", "code", name="uq_maintenance_subcategory_code"),
    )


class MaintenancePriorityPolicy(Base):
    """Configurable priority SLA policy mapping category + priority to target resolution hours."""

    __tablename__ = "maintenance_priority_policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("maintenance_categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    priority: Mapped[str] = mapped_column(String(20), nullable=False)  # LOW, MEDIUM, HIGH, CRITICAL
    target_resolution_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=72)
    escalation_threshold_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=48)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    category: Mapped[Optional["MaintenanceCategory"]] = relationship("MaintenanceCategory")

    __table_args__ = (
        CheckConstraint(
            "priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_maintenance_priority_policy_priority",
        ),
        UniqueConstraint(
            "society_id", "category_id", "priority", name="uq_maintenance_priority_society_cat_prio"
        ),
    )


class MaintenanceWorkOrder(Base):
    """Core Maintenance Work Order entity."""

    __tablename__ = "maintenance_work_orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    work_order_number: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("maintenance_categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    subcategory_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("maintenance_subcategories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source: Mapped[str] = mapped_column(
        String(32), default="ADMIN", nullable=False
    )  # COMPLAINT, SERVICE_REQUEST, ADMIN, INSPECTION, EMERGENCY, PREVENTIVE
    complaint_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("complaints.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    unit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("units.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    block_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("blocks.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    priority: Mapped[str] = mapped_column(
        String(20), default="MEDIUM", nullable=False
    )  # LOW, MEDIUM, HIGH, CRITICAL
    status: Mapped[str] = mapped_column(
        String(32), default="OPEN", nullable=False
    )  # DRAFT, OPEN, ASSIGNED, SCHEDULED, IN_PROGRESS, ON_HOLD, WAITING_FOR_PARTS, WAITING_FOR_RESIDENT, COMPLETED, VERIFIED, CLOSED, REOPENED, CANCELLED
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    requested_for_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("units.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    current_assignment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    estimated_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduled_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduled_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Optional cross-domain reference boundaries
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="SET NULL"), nullable=True
    )
    visitor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visitors.id", ondelete="SET NULL"), nullable=True
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # Relationships
    category: Mapped["MaintenanceCategory"] = relationship(
        "MaintenanceCategory", back_populates="work_orders"
    )
    subcategory: Mapped[Optional["MaintenanceSubcategory"]] = relationship(
        "MaintenanceSubcategory", back_populates="work_orders"
    )
    complaint: Mapped[Optional["Complaint"]] = relationship("Complaint")
    unit: Mapped[Optional["Unit"]] = relationship("Unit", foreign_keys=[unit_id])
    block: Mapped[Optional["Block"]] = relationship("Block", foreign_keys=[block_id])
    requested_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[requested_by_user_id])
    requested_for_unit: Mapped[Optional["Unit"]] = relationship("Unit", foreign_keys=[requested_for_unit_id])
    vehicle: Mapped[Optional["Vehicle"]] = relationship("Vehicle")
    visitor: Mapped[Optional["Visitor"]] = relationship("Visitor")

    assignments: Mapped[list["WorkOrderAssignment"]] = relationship(
        "WorkOrderAssignment", back_populates="work_order", cascade="all, delete-orphan"
    )
    comments: Mapped[list["WorkOrderComment"]] = relationship(
        "WorkOrderComment", back_populates="work_order", cascade="all, delete-orphan"
    )
    attachments: Mapped[list["WorkOrderAttachment"]] = relationship(
        "WorkOrderAttachment", back_populates="work_order", cascade="all, delete-orphan"
    )
    history: Mapped[list["WorkOrderStatusHistory"]] = relationship(
        "WorkOrderStatusHistory", back_populates="work_order", cascade="all, delete-orphan"
    )
    escalations: Mapped[list["WorkOrderEscalation"]] = relationship(
        "WorkOrderEscalation", back_populates="work_order", cascade="all, delete-orphan"
    )
    resolution: Mapped[Optional["WorkOrderResolution"]] = relationship(
        "WorkOrderResolution",
        back_populates="work_order",
        uselist=False,
        cascade="all, delete-orphan",
    )
    materials: Mapped[list["WorkOrderMaterialUsage"]] = relationship(
        "WorkOrderMaterialUsage", back_populates="work_order", cascade="all, delete-orphan"
    )
    activities: Mapped[list["WorkOrderActivity"]] = relationship(
        "WorkOrderActivity", back_populates="work_order", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("society_id", "work_order_number", name="uq_maintenance_work_orders_society_number"),
        CheckConstraint(
            "priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_maintenance_work_orders_priority",
        ),
        CheckConstraint(
            "source IN ('COMPLAINT', 'SERVICE_REQUEST', 'ADMIN', 'INSPECTION', 'EMERGENCY', 'PREVENTIVE')",
            name="ck_maintenance_work_orders_source",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'OPEN', 'ASSIGNED', 'SCHEDULED', 'IN_PROGRESS', 'ON_HOLD', 'WAITING_FOR_PARTS', 'WAITING_FOR_RESIDENT', 'COMPLETED', 'VERIFIED', 'CLOSED', 'REOPENED', 'CANCELLED')",
            name="ck_maintenance_work_orders_status",
        ),
        Index("ix_maintenance_wo_society_status", "society_id", "status"),
        Index("ix_maintenance_wo_society_priority", "society_id", "priority"),
        Index("ix_maintenance_wo_due_at", "society_id", "due_at"),
    )


class WorkOrderAssignment(Base):
    """Preserves full history of work order assignments (INTERNAL_USER, TEAM, STAFF, VENDOR)."""

    __tablename__ = "work_order_assignments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    work_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("maintenance_work_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assignment_type: Mapped[str] = mapped_column(
        String(32), default="INTERNAL_USER", nullable=False
    )  # INTERNAL_USER, TEAM, STAFF, VENDOR
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    target_team_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    assigned_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    unassigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    work_order: Mapped["MaintenanceWorkOrder"] = relationship(
        "MaintenanceWorkOrder", back_populates="assignments"
    )
    target_user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[target_user_id])
    assigned_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[assigned_by_user_id])

    __table_args__ = (
        CheckConstraint(
            "assignment_type IN ('INTERNAL_USER', 'TEAM', 'STAFF', 'VENDOR')",
            name="ck_work_order_assignment_type",
        ),
        Index("ix_wo_assignment_wo_status", "society_id", "work_order_id"),
    )


class WorkOrderComment(Base):
    """Comments attached to a work order (PUBLIC or INTERNAL)."""

    __tablename__ = "work_order_comments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    work_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("maintenance_work_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    comment_text: Mapped[str] = mapped_column(Text, nullable=False)
    comment_type: Mapped[str] = mapped_column(
        String(20), default="PUBLIC", nullable=False
    )  # PUBLIC, INTERNAL
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    work_order: Mapped["MaintenanceWorkOrder"] = relationship(
        "MaintenanceWorkOrder", back_populates="comments"
    )
    user: Mapped["User"] = relationship("User")

    __table_args__ = (
        CheckConstraint(
            "comment_type IN ('PUBLIC', 'INTERNAL')",
            name="ck_work_order_comment_type",
        ),
    )


class WorkOrderAttachment(Base):
    """Media evidence or document attachments for work orders."""

    __tablename__ = "work_order_attachments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    work_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("maintenance_work_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(
        String(20), default="PHOTO", nullable=False
    )  # PHOTO, VIDEO, AUDIO, DOCUMENT, OTHER
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    work_order: Mapped["MaintenanceWorkOrder"] = relationship(
        "MaintenanceWorkOrder", back_populates="attachments"
    )
    uploaded_by: Mapped["User"] = relationship("User")

    __table_args__ = (
        CheckConstraint(
            "file_type IN ('PHOTO', 'VIDEO', 'AUDIO', 'DOCUMENT', 'OTHER')",
            name="ck_work_order_attachment_file_type",
        ),
    )


class WorkOrderStatusHistory(Base):
    """Audit log of work order status transitions."""

    __tablename__ = "work_order_status_histories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    work_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("maintenance_work_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    changed_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    work_order: Mapped["MaintenanceWorkOrder"] = relationship(
        "MaintenanceWorkOrder", back_populates="history"
    )
    changed_by: Mapped["User"] = relationship("User")


class WorkOrderEscalation(Base):
    """SLA breach escalation log for work orders."""

    __tablename__ = "work_order_escalations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    work_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("maintenance_work_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    escalation_level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    triggered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    target_team_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    work_order: Mapped["MaintenanceWorkOrder"] = relationship(
        "MaintenanceWorkOrder", back_populates="escalations"
    )
    triggered_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[triggered_by_user_id])
    target_user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[target_user_id])


class WorkOrderResolution(Base):
    """Resolution details and verification log for work orders."""

    __tablename__ = "work_order_resolutions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    work_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("maintenance_work_orders.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    resolved_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    resolution_summary: Mapped[str] = mapped_column(Text, nullable=False)
    resolution_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resolution_evidence: Mapped[str | None] = mapped_column(String(500), nullable=True)
    verification_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    verified_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default="PENDING_VERIFICATION", nullable=False
    )  # PENDING_VERIFICATION, VERIFIED, REJECTED
    resolved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    work_order: Mapped["MaintenanceWorkOrder"] = relationship(
        "MaintenanceWorkOrder", back_populates="resolution"
    )
    resolved_by: Mapped["User"] = relationship("User", foreign_keys=[resolved_by_user_id])
    verified_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[verified_by_user_id])


class WorkOrderMaterialUsage(Base):
    """Operational material/parts usage record (Non-financial operational tracker)."""

    __tablename__ = "work_order_material_usages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    work_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("maintenance_work_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    material_name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("1.00"))
    unit: Mapped[str] = mapped_column(String(50), nullable=False, default="units")
    estimated_unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    actual_unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    work_order: Mapped["MaintenanceWorkOrder"] = relationship(
        "MaintenanceWorkOrder", back_populates="materials"
    )
    created_by: Mapped["User"] = relationship("User")


class WorkOrderActivity(Base):
    """Unified activity/timeline event log for work orders."""

    __tablename__ = "work_order_activities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    work_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("maintenance_work_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    work_order: Mapped["MaintenanceWorkOrder"] = relationship(
        "MaintenanceWorkOrder", back_populates="activities"
    )
    actor: Mapped[Optional["User"]] = relationship("User")
