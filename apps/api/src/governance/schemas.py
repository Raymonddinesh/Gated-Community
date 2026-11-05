"""Phase 18 Governance Pydantic Schemas."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from apps.api.src.governance.enums import (
    ActionItemStatus,
    CommitteePosition,
    CommitteeRole,
    CommitteeStatus,
    CommitteeType,
    MeetingAttendanceStatus,
    MeetingStatus,
    MeetingType,
    ResolutionStatus,
    ResolutionType,
    VoteChoice,
    VoteValue,
    VotingRule,
    VotingType,
)


# Committee Schemas
class CommitteeCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=200)
    committee_type: CommitteeType = CommitteeType.MANAGING_COMMITTEE
    description: str | None = None
    term_start_date: date | None = None
    term_end_date: date | None = None
    start_date: date | None = None
    end_date: date | None = None


class CommitteeUpdate(BaseModel):
    name: str | None = Field(None, min_length=3, max_length=200)
    committee_type: CommitteeType | None = None
    description: str | None = None
    status: CommitteeStatus | None = None
    term_start_date: date | None = None
    term_end_date: date | None = None
    start_date: date | None = None
    end_date: date | None = None


class CommitteeMemberAdd(BaseModel):
    user_id: UUID
    role: CommitteeRole = CommitteeRole.MEMBER
    position: CommitteePosition = CommitteePosition.MEMBER
    designation: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None


class CommitteeMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    committee_id: UUID
    user_id: UUID
    position: str
    role: str = "MEMBER"
    status: str
    effective_from: date
    effective_to: date | None = None
    appointed_at: datetime | None = None


class CommitteeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    name: str
    committee_type: str
    description: str | None = None
    status: str
    is_active: bool = True
    start_date: date | None = None
    end_date: date | None = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    members: list[CommitteeMemberResponse] = []


# Meeting Schemas
class MeetingCreate(BaseModel):
    committee_id: UUID | None = None
    meeting_type: MeetingType = MeetingType.COMMITTEE_MEETING
    title: str = Field(..., min_length=3, max_length=200)
    description: str | None = None
    scheduled_start_at: datetime | None = None
    scheduled_end_at: datetime | None = None
    scheduled_at: datetime | None = None
    location: str | None = "Society Clubhouse"
    quorum_percentage: float | None = 50.0
    notice_issued_at: datetime | None = None


class MeetingUpdate(BaseModel):
    title: str | None = Field(None, min_length=3, max_length=200)
    description: str | None = None
    scheduled_start_at: datetime | None = None
    scheduled_end_at: datetime | None = None
    scheduled_at: datetime | None = None
    location: str | None = Field(None, min_length=2, max_length=255)


class MeetingStateTransition(BaseModel):
    to_status: MeetingStatus


class MeetingAgendaItemCreate(BaseModel):
    sequence_number: int | None = 1
    item_order: int | None = 1
    title: str = Field(..., min_length=3, max_length=200)
    description: str | None = None
    duration_minutes: int | None = 15


class MeetingAgendaItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    meeting_id: UUID
    sequence_number: int
    item_order: int = 1
    title: str
    description: str | None = None
    submitted_by: UUID
    status: str
    created_at: datetime


class MeetingAttendanceRecord(BaseModel):
    user_id: UUID | None = None
    status: MeetingAttendanceStatus = MeetingAttendanceStatus.PRESENT
    notes: str | None = Field(None, max_length=500)


class MeetingAttendanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    meeting_id: UUID
    user_id: UUID
    status: str
    check_in: datetime | None = None
    recorded_by: UUID
    notes: str | None = None
    created_at: datetime


class MeetingQuorumRecord(BaseModel):
    total_eligible_voters: int = Field(..., ge=1)
    present_in_person: int = Field(..., ge=0)
    present_by_proxy: int = Field(0, ge=0)


class MeetingQuorumCalculateRequest(BaseModel):
    required_count: int = Field(..., ge=1)


class MeetingQuorumResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    meeting_id: UUID
    required_count: int
    present_count: int
    total_present: int = 0
    quorum_status: str
    calculated_at: datetime
    calculated_by: UUID


class MeetingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    committee_id: UUID | None = None
    meeting_number: str
    meeting_type: str
    title: str
    description: str | None = None
    scheduled_at: datetime
    actual_start_at: datetime | None = None
    actual_end_at: datetime | None = None
    location: str
    status: str
    notice_published_at: datetime | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    agenda_items: list[MeetingAgendaItemResponse] = []


# Resolution Schemas
class ResolutionCreate(BaseModel):
    meeting_id: UUID | None = None
    agenda_item_id: UUID | None = None
    title: str = Field(..., min_length=3, max_length=200)
    description: str = Field(..., min_length=5)
    resolution_type: ResolutionType = ResolutionType.ORDINARY
    voting_rule: VotingRule = VotingRule.SIMPLE_MAJORITY
    voting_type: VotingType = VotingType.SIMPLE_MAJORITY
    pass_threshold_percentage: float | None = 50.0
    seconded_by: UUID | None = None


class ResolutionUpdate(BaseModel):
    title: str | None = Field(None, min_length=3, max_length=200)
    description: str | None = None


class ResolutionStateTransition(BaseModel):
    to_status: ResolutionStatus


class ResolutionCastVote(BaseModel):
    choice: VoteChoice = VoteChoice.FOR


class ResolutionVoteRequest(BaseModel):
    vote: VoteValue = VoteValue.FOR


class ResolutionVoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    resolution_id: UUID
    user_id: UUID
    vote: str
    choice: str = "FOR"
    recorded_by: UUID
    created_at: datetime | None = None


class ResolutionTallyResponse(BaseModel):
    resolution_id: UUID
    resolution_number: str
    status: ResolutionStatus
    voting_rule: VotingRule
    votes_for: int = 0
    votes_against: int = 0
    votes_abstain: int = 0
    total_votes: int = 0
    passed: bool = False


class ResolutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    meeting_id: UUID | None = None
    agenda_item_id: UUID | None = None
    resolution_number: str
    title: str
    description: str
    resolution_type: str
    voting_rule: str
    voting_type: str = "SIMPLE_MAJORITY"
    status: str
    proposed_by: UUID
    seconded_by: UUID | None = None
    votes_for: int = 0
    votes_against: int = 0
    votes_abstain: int = 0
    total_votes_cast: int = 0
    approved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    tally: ResolutionTallyResponse | None = None


# Minutes Schemas
class MeetingMinutesCreate(BaseModel):
    summary: str = Field(..., min_length=5)
    key_decisions: str | None = None


class MeetingMinutesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    meeting_id: UUID
    version: int
    status: str
    summary: str
    key_decisions: str | None = None
    prepared_by: UUID
    approved_by: UUID | None = None
    approved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


# Action Item Schemas
class MeetingActionItemCreate(BaseModel):
    meeting_id: UUID | None = None
    resolution_id: UUID | None = None
    agenda_item_id: UUID | None = None
    title: str | None = None
    description: str = Field(..., min_length=3)
    assignee_id: UUID | None = None
    assigned_to: UUID | None = None
    due_date: date | None = None
    priority: str = "NORMAL"


class MeetingActionItemUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: ActionItemStatus | None = None
    due_date: date | None = None
    priority: str | None = None


class MeetingActionItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    meeting_id: UUID
    resolution_id: UUID | None = None
    agenda_item_id: UUID | None = None
    action_number: str = "ACT-2026-000001"
    title: str | None = None
    description: str
    assignee_id: UUID | None = None
    assigned_to: UUID | None = None
    due_date: date | None = None
    priority: str
    status: str
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


# Governance Attachment Schema
class GovernanceAttachmentCreate(BaseModel):
    entity_type: str = Field(..., max_length=50)
    entity_id: UUID
    file_name: str = Field(..., min_length=1, max_length=255)
    file_size: int = Field(..., gt=0, le=10 * 1024 * 1024)
    mime_type: str = Field(..., min_length=3, max_length=100)


class GovernanceAttachmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    entity_type: str
    entity_id: UUID
    file_name: str
    file_size: int
    mime_type: str
    storage_object_key: str
    uploaded_by: UUID
    uploaded_at: datetime
