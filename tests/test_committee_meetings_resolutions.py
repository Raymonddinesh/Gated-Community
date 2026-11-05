"""Phase 18 Committee, Meetings & Resolutions Governance Unit Test Suite."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.governance.enums import (
    ActionItemStatus,
    CommitteeRole,
    CommitteeStatus,
    CommitteeType,
    MeetingStatus,
    MeetingType,
    QuorumStatus,
    ResolutionStatus,
    VoteChoice,
    VotingType,
)
from apps.api.src.governance.exceptions import (
    DuplicateVoteError,
    MakerCheckerViolationError,
)
from apps.api.src.governance.governance_service import GovernanceService
from apps.api.src.governance.schemas import (
    CommitteeCreate,
    CommitteeMemberAdd,
    MeetingActionItemCreate,
    MeetingActionItemUpdate,
    MeetingAgendaItemCreate,
    MeetingCreate,
    MeetingMinutesCreate,
    MeetingQuorumRecord,
    MeetingStateTransition,
    ResolutionCastVote,
    ResolutionCreate,
    ResolutionStateTransition,
)

UUID_SOCIETY_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
UUID_USER_OWNER_A = uuid.UUID("22222222-2222-2222-2222-22222222222a")
UUID_USER_TENANT_A = uuid.UUID("33333333-3333-3333-3333-33333333333a")
UUID_USER_DELEGATE_A = uuid.UUID("44444444-4444-4444-4444-44444444444a")
UUID_SUPER_ADMIN = uuid.UUID("11111111-1111-1111-1111-11111111111a")


@pytest.mark.asyncio
async def test_committee_creation_and_member_management(seeded_session: AsyncSession):
    service = GovernanceService(seeded_session)
    society_id = UUID_SOCIETY_A
    user1_id = UUID_USER_OWNER_A
    user2_id = UUID_USER_TENANT_A

    committee = await service.create_committee(
        society_id,
        CommitteeCreate(
            name="Executive Managing Committee 2026",
            description="Primary managing committee responsible for society administration.",
            committee_type=CommitteeType.MANAGING_COMMITTEE,
            term_start_date=datetime.now(UTC).date(),
            term_end_date=(datetime.now(UTC) + timedelta(days=365)).date(),
        ),
        creator_id=UUID_SUPER_ADMIN,
    )

    assert committee.id is not None
    assert committee.name == "Executive Managing Committee 2026"
    assert committee.committee_type == CommitteeType.MANAGING_COMMITTEE.value
    assert committee.status == CommitteeStatus.DRAFT.value

    # Add member
    member1 = await service.add_committee_member(
        society_id,
        committee.id,
        CommitteeMemberAdd(
            user_id=user1_id,
            role=CommitteeRole.PRESIDENT,
            designation="President",
        ),
        creator_id=UUID_SUPER_ADMIN,
    )
    assert member1.position == CommitteeRole.PRESIDENT.value
    assert member1.user_id == user1_id

    member2 = await service.add_committee_member(
        society_id,
        committee.id,
        CommitteeMemberAdd(
            user_id=user2_id,
            role=CommitteeRole.SECRETARY,
            designation="Secretary",
        ),
        creator_id=UUID_SUPER_ADMIN,
    )
    assert member2.position == CommitteeRole.SECRETARY.value

    # List members
    members = await service.list_committee_members(society_id, committee.id)
    assert len(members) == 2

    # Remove member
    await service.remove_committee_member(society_id, committee.id, member2.id)
    active_members = await service.list_committee_members(society_id, committee.id, active_only=True)
    assert len(active_members) == 1
    assert active_members[0].user_id == user1_id


@pytest.mark.asyncio
async def test_meeting_creation_and_numbering(seeded_session: AsyncSession):
    service = GovernanceService(seeded_session)
    society_id = UUID_SOCIETY_A
    organizer_id = UUID_USER_OWNER_A

    starts = datetime.now(UTC) + timedelta(days=7)
    ends = starts + timedelta(hours=2)

    meeting = await service.create_meeting(
        society_id,
        organizer_id,
        MeetingCreate(
            title="15th Annual General Body Meeting",
            description="AGM to discuss financial statements, auditor appointment, and major works.",
            meeting_type=MeetingType.ANNUAL_GENERAL_MEETING,
            scheduled_start_at=starts,
            scheduled_end_at=ends,
            location="Society Clubhouse Main Hall",
            quorum_percentage=50.0,
            notice_issued_at=datetime.now(UTC),
        ),
    )

    assert meeting.meeting_number.startswith("MTG-")
    assert meeting.status == MeetingStatus.DRAFT.value
    assert meeting.title == "15th Annual General Body Meeting"

    # Add agenda item
    item = await service.add_agenda_item(
        society_id,
        meeting.id,
        MeetingAgendaItemCreate(
            item_order=1,
            title="Approval of FY 2025-26 Audited Accounts",
            description="Review and pass resolution for audited financial statements.",
            duration_minutes=30,
        ),
        submitter_id=organizer_id,
    )
    assert item.sequence_number == 1
    assert item.title == "Approval of FY 2025-26 Audited Accounts"


@pytest.mark.asyncio
async def test_meeting_lifecycle_transitions(seeded_session: AsyncSession):
    service = GovernanceService(seeded_session)
    society_id = UUID_SOCIETY_A
    user_id = UUID_USER_OWNER_A

    starts = datetime.now(UTC) + timedelta(days=1)
    ends = starts + timedelta(hours=2)

    meeting = await service.create_meeting(
        society_id,
        user_id,
        MeetingCreate(
            title="Monthly Committee Review",
            meeting_type=MeetingType.MANAGING_COMMITTEE,
            scheduled_start_at=starts,
            scheduled_end_at=ends,
        ),
    )

    # Transition to SCHEDULED
    m1 = await service.transition_meeting_status(
        society_id, meeting.id, MeetingStateTransition(to_status=MeetingStatus.SCHEDULED), user_id
    )
    assert m1.status == MeetingStatus.SCHEDULED.value

    # Transition to IN_PROGRESS
    m2 = await service.transition_meeting_status(
        society_id, meeting.id, MeetingStateTransition(to_status=MeetingStatus.IN_PROGRESS), user_id
    )
    assert m2.status == MeetingStatus.IN_PROGRESS.value
    assert m2.started_at is not None

    # Transition to COMPLETED
    m3 = await service.transition_meeting_status(
        society_id, meeting.id, MeetingStateTransition(to_status=MeetingStatus.COMPLETED), user_id
    )
    assert m3.status == MeetingStatus.COMPLETED.value
    assert m3.ended_at is not None


@pytest.mark.asyncio
async def test_quorum_calculation(seeded_session: AsyncSession):
    service = GovernanceService(seeded_session)
    society_id = UUID_SOCIETY_A
    user_id = UUID_USER_OWNER_A

    starts = datetime.now(UTC) + timedelta(hours=1)
    ends = starts + timedelta(hours=2)

    meeting = await service.create_meeting(
        society_id,
        user_id,
        MeetingCreate(
            title="Special General Body Meeting",
            meeting_type=MeetingType.SPECIAL_GENERAL_MEETING,
            scheduled_start_at=starts,
            scheduled_end_at=ends,
            quorum_percentage=33.33,
        ),
    )

    # Record quorum with insufficient attendees (10 present < 50 required)
    q1 = await service.record_quorum(
        society_id,
        meeting.id,
        MeetingQuorumRecord(
            total_eligible_voters=100,
            present_in_person=8,
            present_by_proxy=2,
        ),
        recorded_by=user_id,
    )
    assert q1.quorum_status == QuorumStatus.NOT_ACHIEVED.value
    assert q1.present_count == 10

    # Record quorum with sufficient attendees (40 present >= 33 required)
    q2 = await service.record_quorum(
        society_id,
        meeting.id,
        MeetingQuorumRecord(
            total_eligible_voters=100,
            present_in_person=35,
            present_by_proxy=5,
        ),
        recorded_by=user_id,
    )
    assert q2.quorum_status == QuorumStatus.ACHIEVED.value
    assert q2.present_count == 40


@pytest.mark.asyncio
async def test_resolution_creation_numbering_and_voting(seeded_session: AsyncSession):
    service = GovernanceService(seeded_session)
    society_id = UUID_SOCIETY_A
    proposer_id = UUID_USER_OWNER_A

    starts = datetime.now(UTC) + timedelta(days=1)
    ends = starts + timedelta(hours=2)

    meeting = await service.create_meeting(
        society_id,
        proposer_id,
        MeetingCreate(
            title="General Body Meeting for Capex Approval",
            meeting_type=MeetingType.SPECIAL_GENERAL_MEETING,
            scheduled_start_at=starts,
            scheduled_end_at=ends,
        ),
    )

    resolution = await service.create_resolution(
        society_id,
        proposer_id,
        ResolutionCreate(
            meeting_id=meeting.id,
            title="Solar Rooftop Installation Project",
            description="Authorize committee to contract 100kW rooftop solar grid system for ₹1,500,000.",
            voting_type=VotingType.TWO_THIRDS,
            pass_threshold_percentage=66.67,
        ),
    )

    assert resolution.resolution_number.startswith("RES-")
    assert resolution.status == ResolutionStatus.PROPOSED.value
    assert resolution.voting_rule == VotingType.TWO_THIRDS.value

    # Transition to VOTING_OPEN
    res_open = await service.transition_resolution_status(
        society_id,
        resolution.id,
        ResolutionStateTransition(to_status=ResolutionStatus.VOTING_OPEN),
        proposer_id,
    )
    assert res_open.status == ResolutionStatus.VOTING_OPEN.value

    # Cast votes using seeded user IDs
    v1 = await service.cast_vote(
        society_id, resolution.id, UUID_USER_OWNER_A, ResolutionCastVote(choice=VoteChoice.FOR)
    )
    v2 = await service.cast_vote(
        society_id, resolution.id, UUID_USER_TENANT_A, ResolutionCastVote(choice=VoteChoice.FOR)
    )
    v3 = await service.cast_vote(
        society_id, resolution.id, UUID_USER_DELEGATE_A, ResolutionCastVote(choice=VoteChoice.AGAINST)
    )

    assert v1.vote == VoteChoice.FOR.value
    assert v2.vote == VoteChoice.FOR.value
    assert v3.vote == VoteChoice.AGAINST.value

    votes = await service.list_votes(society_id, resolution.id)
    assert len(votes) == 3

    # Close voting and evaluate
    res_passed = await service.transition_resolution_status(
        society_id, resolution.id, ResolutionStateTransition(to_status=ResolutionStatus.APPROVED), proposer_id
    )
    assert res_passed.status == ResolutionStatus.APPROVED.value


@pytest.mark.asyncio
async def test_duplicate_vote_prevention(seeded_session: AsyncSession):
    service = GovernanceService(seeded_session)
    society_id = UUID_SOCIETY_A
    user_id = UUID_USER_OWNER_A
    voter_id = UUID_USER_TENANT_A

    starts = datetime.now(UTC) + timedelta(days=1)
    ends = starts + timedelta(hours=2)

    meeting = await service.create_meeting(
        society_id,
        user_id,
        MeetingCreate(
            title="Meeting for Voting",
            meeting_type=MeetingType.MANAGING_COMMITTEE,
            scheduled_start_at=starts,
            scheduled_end_at=ends,
        ),
    )

    resolution = await service.create_resolution(
        society_id,
        user_id,
        ResolutionCreate(
            meeting_id=meeting.id,
            title="Rule Modification Resolution",
            description="Modify pet policy.",
            voting_type=VotingType.SIMPLE_MAJORITY,
        ),
    )

    await service.transition_resolution_status(
        society_id, resolution.id, ResolutionStateTransition(to_status=ResolutionStatus.VOTING_OPEN), user_id
    )

    # First vote succeeds
    await service.cast_vote(society_id, resolution.id, voter_id, ResolutionCastVote(choice=VoteChoice.FOR))

    # Second vote by same voter raises DuplicateVoteError
    with pytest.raises(DuplicateVoteError):
        await service.cast_vote(
            society_id, resolution.id, voter_id, ResolutionCastVote(choice=VoteChoice.AGAINST)
        )


@pytest.mark.asyncio
async def test_meeting_minutes_maker_checker_approval(seeded_session: AsyncSession):
    service = GovernanceService(seeded_session)
    society_id = UUID_SOCIETY_A
    author_id = UUID_USER_OWNER_A
    approver_id = UUID_USER_TENANT_A

    starts = datetime.now(UTC) - timedelta(hours=4)
    ends = starts + timedelta(hours=2)

    meeting = await service.create_meeting(
        society_id,
        author_id,
        MeetingCreate(
            title="Completed Committee Meeting",
            meeting_type=MeetingType.MANAGING_COMMITTEE,
            scheduled_start_at=starts,
            scheduled_end_at=ends,
        ),
    )

    # Draft minutes
    minutes = await service.create_meeting_minutes(
        society_id,
        meeting.id,
        author_id,
        MeetingMinutesCreate(
            summary="Meeting reviewed Q3 maintenance budget performance.",
            key_decisions="Approved ₹50,000 for elevator servicing.",
        ),
    )

    assert minutes.status == MeetingStatus.DRAFT.value
    assert minutes.prepared_by == author_id

    # Self-approval by author must fail (maker-checker rule)
    with pytest.raises(MakerCheckerViolationError):
        await service.approve_and_publish_minutes(society_id, meeting.id, approver_id=author_id)

    # Approval by distinct approver succeeds
    published = await service.approve_and_publish_minutes(society_id, meeting.id, approver_id=approver_id)
    assert published.status == ResolutionStatus.PUBLISHED.value
    assert published.approved_by == approver_id


@pytest.mark.asyncio
async def test_action_item_management(seeded_session: AsyncSession):
    service = GovernanceService(seeded_session)
    society_id = UUID_SOCIETY_A
    user_id = UUID_USER_OWNER_A
    assignee_id = UUID_USER_TENANT_A

    starts = datetime.now(UTC) - timedelta(hours=4)
    ends = starts + timedelta(hours=2)

    meeting = await service.create_meeting(
        society_id,
        user_id,
        MeetingCreate(
            title="Meeting for Action Items",
            meeting_type=MeetingType.MANAGING_COMMITTEE,
            scheduled_start_at=starts,
            scheduled_end_at=ends,
        ),
    )

    item = await service.create_action_item(
        society_id,
        MeetingActionItemCreate(
            meeting_id=meeting.id,
            description="Obtain 3 quotes for CCTV overhaul.",
            assignee_id=assignee_id,
            due_date=(datetime.now(UTC) + timedelta(days=14)).date(),
        ),
    )

    assert item.status == ActionItemStatus.PENDING.value
    assert item.assigned_to == assignee_id

    # Update action item to IN_PROGRESS
    updated = await service.update_action_item(
        society_id,
        item.id,
        MeetingActionItemUpdate(status=ActionItemStatus.IN_PROGRESS),
    )
    assert updated.status == ActionItemStatus.IN_PROGRESS.value
