"""Phase 19 Emergency & Incident Management Database Models."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.src.database.base import Base


class IncidentCategory(Base):
    """Incident Category Taxonomy."""

    __tablename__ = "incident_categories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_severity: Mapped[str] = mapped_column(
        String(20), nullable=False, default="MEDIUM"
    )  # LOW, MEDIUM, HIGH, CRITICAL
    default_sla_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True, default=60)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    society = relationship("Society")
    incidents = relationship("Incident", back_populates="category")

    __table_args__ = (Index("ix_incident_categories_society_code", "society_id", "code"),)


class Incident(Base):
    """Master Incident & Emergency Log Entity."""

    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    incident_number: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incident_categories.id", ondelete="RESTRICT"), nullable=False
    )
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False, default="MEDIUM"
    )  # LOW, MEDIUM, HIGH, CRITICAL
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="REPORTED"
    )  # REPORTED, TRIAGED, ACKNOWLEDGED, RESPONSE_STARTED, CONTAINED, RESOLVED, CLOSED, ESCALATED, CANCELLED
    reported_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reporter_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="RESIDENT"
    )  # RESIDENT, STAFF, SECURITY, COMMITTEE, VENDOR, ANONYMOUS, SYSTEM
    reporter_contact: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Location spatial references
    block_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("blocks.id", ondelete="SET NULL"), nullable=True
    )
    floor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("floors.id", ondelete="SET NULL"), nullable=True
    )
    unit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("units.id", ondelete="SET NULL"), nullable=True
    )
    facility_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="SET NULL"), nullable=True
    )
    facility_area_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facility_areas.id", ondelete="SET NULL"), nullable=True
    )
    location_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Audio/Voice Attachment Limit (Max 60 Seconds Server-Enforced)
    voice_note_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    voice_note_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Operational Flags
    is_hazard_contained: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hazard_contained_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    requires_governance_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requires_work_order: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Administrative Override Audit
    override_applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    overridden_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    overridden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    society = relationship("Society")
    category = relationship("IncidentCategory", back_populates="incidents")
    reporter = relationship("User", foreign_keys=[reported_by_id])
    overridden_by = relationship("User", foreign_keys=[overridden_by_id])
    block = relationship("Block")
    floor = relationship("Floor")
    unit = relationship("Unit")
    facility = relationship("Facility")
    facility_area = relationship("FacilityArea")

    assignments = relationship("IncidentAssignment", back_populates="incident", cascade="all, delete-orphan")
    timelines = relationship("IncidentTimeline", back_populates="incident", cascade="all, delete-orphan")
    actions = relationship("IncidentAction", back_populates="incident", cascade="all, delete-orphan")
    escalations = relationship("IncidentEscalation", back_populates="incident", cascade="all, delete-orphan")
    attachments = relationship("IncidentAttachment", back_populates="incident", cascade="all, delete-orphan")
    status_histories = relationship(
        "IncidentStatusHistory", back_populates="incident", cascade="all, delete-orphan"
    )
    acknowledgements = relationship(
        "IncidentAcknowledgement", back_populates="incident", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("society_id", "incident_number", name="uq_incidents_society_number"),
        Index("ix_incidents_society_status", "society_id", "status"),
        Index("ix_incidents_society_severity", "society_id", "severity"),
        Index("ix_incidents_society_created", "society_id", "created_at"),
    )


class IncidentAssignment(Base):
    """Incident Multi-Responder Assignment Record."""

    __tablename__ = "incident_assignments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    responder_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # STAFF, SECURITY, COMMITTEE, VENDOR, EMERGENCY_CONTACT
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assigned_staff_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_profiles.id", ondelete="SET NULL"), nullable=True
    )
    assigned_vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendor_profiles.id", ondelete="SET NULL"), nullable=True
    )
    assigned_role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    assignment_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    assigned_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    unassigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    society = relationship("Society")
    incident = relationship("Incident", back_populates="assignments")
    assigned_user = relationship("User", foreign_keys=[assigned_user_id])
    assigned_staff = relationship("StaffProfile", foreign_keys=[assigned_staff_id])
    assigned_vendor = relationship("VendorProfile", foreign_keys=[assigned_vendor_id])
    assigned_by = relationship("User", foreign_keys=[assigned_by_id])

    __table_args__ = (Index("ix_incident_assignments_society_incident", "society_id", "incident_id"),)


class IncidentTimeline(Base):
    """Append-only Operational Incident Log."""

    __tablename__ = "incident_timelines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    actor_role: Mapped[str] = mapped_column(String(50), nullable=False)
    event_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # REPORTED, STATUS_CHANGED, ASSIGNED, ACTION_TAKEN, ESCALATED, ATTACHMENT_ADDED, OVERRIDE_APPLIED, NOTE_ADDED
    summary: Mapped[str] = mapped_column(String(255), nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_internal_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    society = relationship("Society")
    incident = relationship("Incident", back_populates="timelines")
    actor = relationship("User", foreign_keys=[actor_id])

    __table_args__ = (Index("ix_incident_timelines_society_incident", "society_id", "incident_id"),)


class IncidentAction(Base):
    """Immediate Response Task / Action Item."""

    __tablename__ = "incident_actions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="PENDING"
    )  # PENDING, IN_PROGRESS, COMPLETED, CANCELLED
    priority: Mapped[str] = mapped_column(
        String(20), nullable=False, default="MEDIUM"
    )  # LOW, MEDIUM, HIGH, URGENT
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    society = relationship("Society")
    incident = relationship("Incident", back_populates="actions")
    assigned_user = relationship("User", foreign_keys=[assigned_user_id])
    completed_by = relationship("User", foreign_keys=[completed_by_id])
    created_by = relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (Index("ix_incident_actions_society_incident", "society_id", "incident_id"),)


class IncidentEscalation(Base):
    """Escalation Audit Log."""

    __tablename__ = "incident_escalations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    escalation_level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    triggered_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    target_role: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # COMMITTEE_PRESIDENT, SECURITY_HEAD, FACILITY_MANAGER, EXTERNAL_SERVICE
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    sla_minutes_at_escalation: Mapped[int | None] = mapped_column(Integer, nullable=True)
    escalated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    society = relationship("Society")
    incident = relationship("Incident", back_populates="escalations")
    triggered_by = relationship("User", foreign_keys=[triggered_by_id])

    __table_args__ = (Index("ix_incident_escalations_society_incident", "society_id", "incident_id"),)


class IncidentAttachment(Base):
    """Attachment Metadata for Incident Object Storage."""

    __tablename__ = "incident_attachments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="DOCUMENT"
    )  # IMAGE, AUDIO, DOCUMENT, VIDEO
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    society = relationship("Society")
    incident = relationship("Incident", back_populates="attachments")
    uploaded_by = relationship("User", foreign_keys=[uploaded_by_id])

    __table_args__ = (Index("ix_incident_attachments_society_incident", "society_id", "incident_id"),)


class EmergencyContact(Base):
    """Platform & Society Emergency Contact Directory."""

    __tablename__ = "emergency_contacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="CASCADE"), nullable=True
    )
    contact_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # POLICE, FIRE, AMBULANCE, HOSPITAL, ELECTRICITY, GAS, SECURITY, MANAGEMENT, OTHER
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(30), nullable=False)
    alt_phone_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_platform_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    society = relationship("Society")

    __table_args__ = (Index("ix_emergency_contacts_society_type", "society_id", "contact_type"),)


class IncidentStatusHistory(Base):
    """Incident Lifecycle State Transition Audit History."""

    __tablename__ = "incident_status_histories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    changed_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    society = relationship("Society")
    incident = relationship("Incident", back_populates="status_histories")
    changed_by = relationship("User", foreign_keys=[changed_by_id])

    __table_args__ = (Index("ix_incident_status_histories_society_incident", "society_id", "incident_id"),)


class IncidentAcknowledgement(Base):
    """Responder Operational Triage Receipt."""

    __tablename__ = "incident_acknowledgements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    acknowledged_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    responder_role: Mapped[str] = mapped_column(String(50), nullable=False)
    acknowledged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    society = relationship("Society")
    incident = relationship("Incident", back_populates="acknowledgements")
    acknowledged_by = relationship("User", foreign_keys=[acknowledged_by_id])

    __table_args__ = (Index("ix_incident_acknowledgements_society_incident", "society_id", "incident_id"),)
