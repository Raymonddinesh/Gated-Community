"""Phase 18 Committee, Meetings & Resolutions Governance Database Models."""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.src.database.base import Base


class Committee(Base):
    """Committee Entity."""

    __tablename__ = "committees"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    committee_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # MANAGING_COMMITTEE, SUB_COMMITTEE, AD_HOC, OTHER
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="DRAFT"
    )  # DRAFT, ACTIVE, SUSPENDED, EXPIRED, ARCHIVED
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
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
    creator = relationship("User", foreign_keys=[created_by])
    members = relationship("CommitteeMember", back_populates="committee", cascade="all, delete-orphan")
    meetings = relationship("Meeting", back_populates="committee")

    __table_args__ = (Index("ix_committees_society_status", "society_id", "status"),)


class CommitteeMember(Base):
    """Committee Member Position Record."""

    __tablename__ = "committee_members"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    committee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("committees.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    position: Mapped[str] = mapped_column(String(50), nullable=False)  # PRESIDENT, SECRETARY, TREASURER, etc.
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="ACTIVE"
    )  # ACTIVE, INACTIVE, RESIGNED
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    appointed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    committee = relationship("Committee", back_populates="members")
    user = relationship("User", foreign_keys=[user_id])
    creator = relationship("User", foreign_keys=[created_by])

    __table_args__ = (
        UniqueConstraint(
            "society_id", "committee_id", "user_id", "effective_from", name="uq_committee_user_active"
        ),
        Index("ix_committee_members_society_user", "society_id", "user_id"),
    )


class Meeting(Base):
    """Meeting Entity."""

    __tablename__ = "meetings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    committee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("committees.id", ondelete="SET NULL"), nullable=True
    )
    meeting_number: Mapped[str] = mapped_column(String(50), nullable=False)
    meeting_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # EC_MEETING, COMMITTEE_MEETING, AGM, EGM, SPECIAL_MEETING, OTHER
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="DRAFT"
    )  # DRAFT, SCHEDULED, NOTICE_PUBLISHED, IN_PROGRESS, COMPLETED, CANCELLED, ADJOURNED
    notice_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    society = relationship("Society")
    committee = relationship("Committee", back_populates="meetings")
    creator = relationship("User")

    agenda_items = relationship("MeetingAgendaItem", back_populates="meeting", cascade="all, delete-orphan")
    attendances = relationship("MeetingAttendance", back_populates="meeting", cascade="all, delete-orphan")
    quorums = relationship("MeetingQuorum", back_populates="meeting", cascade="all, delete-orphan")
    resolutions = relationship("Resolution", back_populates="meeting")
    minutes = relationship("MeetingMinutes", back_populates="meeting", cascade="all, delete-orphan")
    action_items = relationship("MeetingActionItem", back_populates="meeting", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("society_id", "meeting_number", name="uq_meeting_number_society"),
        Index("ix_meetings_society_status", "society_id", "status"),
        Index("ix_meetings_society_scheduled", "society_id", "scheduled_at"),
    )


class MeetingAgendaItem(Base):
    """Meeting Agenda Item Entity."""

    __tablename__ = "meeting_agenda_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="PENDING"
    )  # PENDING, IN_DISCUSSION, RESOLVED, DEFERRED
    discussion_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    meeting = relationship("Meeting", back_populates="agenda_items")
    submitter = relationship("User")

    __table_args__ = (Index("ix_meeting_agenda_society_meeting", "society_id", "meeting_id"),)


class MeetingAttendance(Base):
    """Meeting Attendance Entity."""

    __tablename__ = "meeting_attendances"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="PRESENT"
    )  # PRESENT, ABSENT, EXCUSED, LATE
    check_in: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    check_out: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recorded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    meeting = relationship("Meeting", back_populates="attendances")
    user = relationship("User", foreign_keys=[user_id])
    recorder = relationship("User", foreign_keys=[recorded_by])

    __table_args__ = (
        UniqueConstraint("society_id", "meeting_id", "user_id", name="uq_meeting_attendance_user"),
        Index("ix_meeting_attendances_society_user", "society_id", "user_id"),
    )


class MeetingQuorum(Base):
    """Meeting Quorum Calculation Record."""

    __tablename__ = "meeting_quorums"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False
    )
    required_count: Mapped[int] = mapped_column(Integer, nullable=False)
    present_count: Mapped[int] = mapped_column(Integer, nullable=False)
    quorum_status: Mapped[str] = mapped_column(String(30), nullable=False)  # ACHIEVED, NOT_ACHIEVED
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    calculated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    meeting = relationship("Meeting", back_populates="quorums")
    calculator = relationship("User")

    __table_args__ = (Index("ix_meeting_quorums_society_meeting", "society_id", "meeting_id"),)


class Resolution(Base):
    """Governance Resolution Entity."""

    __tablename__ = "resolutions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    meeting_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True
    )
    agenda_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meeting_agenda_items.id", ondelete="SET NULL"), nullable=True
    )
    resolution_number: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    resolution_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="ORDINARY"
    )  # ORDINARY, SPECIAL, FINANCIAL_APPROVAL, POLICY, OTHER
    voting_rule: Mapped[str] = mapped_column(
        String(50), nullable=False, default="SIMPLE_MAJORITY"
    )  # SIMPLE_MAJORITY, TWO_THIRDS, UNANIMOUS, CUSTOM
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="DRAFT"
    )  # DRAFT, PROPOSED, UNDER_DISCUSSION, VOTING, APPROVED, REJECTED, WITHDRAWN, RECORDED
    proposed_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    seconded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    meeting = relationship("Meeting", back_populates="resolutions")
    agenda_item = relationship("MeetingAgendaItem")
    proposer = relationship("User", foreign_keys=[proposed_by])
    seconder = relationship("User", foreign_keys=[seconded_by])

    votes = relationship("ResolutionVote", back_populates="resolution", cascade="all, delete-orphan")
    status_history = relationship(
        "ResolutionStatusHistory", back_populates="resolution", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("society_id", "resolution_number", name="uq_resolution_number_society"),
        Index("ix_resolutions_society_status", "society_id", "status"),
    )


class ResolutionVote(Base):
    """Resolution Vote Record."""

    __tablename__ = "resolution_votes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    resolution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resolutions.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    vote: Mapped[str] = mapped_column(String(20), nullable=False)  # FOR, AGAINST, ABSTAIN
    voted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    recorded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    resolution = relationship("Resolution", back_populates="votes")
    voter = relationship("User", foreign_keys=[user_id])
    recorder = relationship("User", foreign_keys=[recorded_by])

    __table_args__ = (
        UniqueConstraint("society_id", "resolution_id", "user_id", name="uq_resolution_user_vote"),
        Index("ix_resolution_votes_society_resolution", "society_id", "resolution_id"),
    )


class ResolutionStatusHistory(Base):
    """Resolution Lifecycle Audit History."""

    __tablename__ = "resolution_status_histories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    resolution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resolutions.id", ondelete="CASCADE"), nullable=False
    )
    old_status: Mapped[str] = mapped_column(String(50), nullable=False)
    new_status: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    resolution = relationship("Resolution", back_populates="status_history")

    __table_args__ = (
        Index("ix_resolution_status_histories_society_resolution", "society_id", "resolution_id"),
    )


class MeetingMinutes(Base):
    """Meeting Minutes Entity with Versioning."""

    __tablename__ = "meeting_minutes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="DRAFT"
    )  # DRAFT, PREPARED, SUBMITTED_FOR_APPROVAL, APPROVED, PUBLISHED
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    prepared_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    meeting = relationship("Meeting", back_populates="minutes")
    preparer = relationship("User", foreign_keys=[prepared_by])
    approver = relationship("User", foreign_keys=[approved_by])

    __table_args__ = (
        UniqueConstraint("society_id", "meeting_id", "version", name="uq_meeting_minutes_version"),
        Index("ix_meeting_minutes_society_meeting", "society_id", "meeting_id"),
    )


class MeetingActionItem(Base):
    """Governance Action Item Entity."""

    __tablename__ = "meeting_action_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False
    )
    resolution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resolutions.id", ondelete="SET NULL"), nullable=True
    )
    agenda_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meeting_agenda_items.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_to: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    priority: Mapped[str] = mapped_column(
        String(20), nullable=False, default="NORMAL"
    )  # LOW, NORMAL, HIGH, URGENT
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="OPEN"
    )  # OPEN, IN_PROGRESS, COMPLETED, OVERDUE, CANCELLED
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    meeting = relationship("Meeting", back_populates="action_items")
    assignee = relationship("User")

    __table_args__ = (
        Index("ix_meeting_action_items_society_meeting", "society_id", "meeting_id"),
        Index("ix_meeting_action_items_assigned_to", "society_id", "assigned_to"),
    )


class GovernanceAttachment(Base):
    """Governance Attachment Metadata."""

    __tablename__ = "governance_attachments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("societies.id", ondelete="RESTRICT"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # MEETING, RESOLUTION, MINUTES, ACTION_ITEM
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    storage_object_key: Mapped[str] = mapped_column(String(500), nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    uploader = relationship("User")

    __table_args__ = (
        Index("ix_governance_attachments_society_entity", "society_id", "entity_type", "entity_id"),
    )
