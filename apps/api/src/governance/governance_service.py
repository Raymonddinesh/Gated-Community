"""Phase 18 Governance Domain Service."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.governance import (
    Committee,
    CommitteeMember,
    GovernanceAttachment,
    Meeting,
    MeetingActionItem,
    MeetingAgendaItem,
    MeetingAttendance,
    MeetingMinutes,
    MeetingQuorum,
    Resolution,
    ResolutionStatusHistory,
    ResolutionVote,
)
from apps.api.src.governance.concurrency import (
    acquire_meeting_number_lock,
    acquire_resolution_number_lock,
    acquire_resolution_vote_lock,
)
from apps.api.src.governance.enums import (
    ActionItemStatus,
    CommitteeRole,
    CommitteeStatus,
    MeetingStatus,
    MinutesStatus,
    QuorumStatus,
    ResolutionStatus,
    VoteValue,
    VotingRule,
)
from apps.api.src.governance.event_hooks import GovernanceDomainHooks
from apps.api.src.governance.exceptions import (
    DuplicateVoteError,
    GovernanceNotFoundError,
    MakerCheckerViolationError,
)
from apps.api.src.governance.repositories import (
    CommitteeMemberRepository,
    CommitteeRepository,
    GovernanceAttachmentRepository,
    MeetingActionItemRepository,
    MeetingAgendaItemRepository,
    MeetingAttendanceRepository,
    MeetingMinutesRepository,
    MeetingQuorumRepository,
    MeetingRepository,
    ResolutionRepository,
    ResolutionStatusHistoryRepository,
    ResolutionVoteRepository,
)
from apps.api.src.governance.schemas import (
    CommitteeCreate,
    CommitteeMemberAdd,
    CommitteeUpdate,
    GovernanceAttachmentCreate,
    MeetingActionItemCreate,
    MeetingActionItemUpdate,
    MeetingAgendaItemCreate,
    MeetingAttendanceRecord,
    MeetingCreate,
    MeetingMinutesCreate,
    MeetingUpdate,
    ResolutionCreate,
    ResolutionUpdate,
)
from apps.api.src.governance.state_machine import MeetingStateMachine


class GovernanceService:
    """Core domain service for Committee, Meetings, Quorum, Resolutions, Voting, Minutes, and Governance Action Items."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.committee_repo = CommitteeRepository(db)
        self.member_repo = CommitteeMemberRepository(db)
        self.meeting_repo = MeetingRepository(db)
        self.agenda_repo = MeetingAgendaItemRepository(db)
        self.attendance_repo = MeetingAttendanceRepository(db)
        self.quorum_repo = MeetingQuorumRepository(db)
        self.resolution_repo = ResolutionRepository(db)
        self.vote_repo = ResolutionVoteRepository(db)
        self.res_history_repo = ResolutionStatusHistoryRepository(db)
        self.minutes_repo = MeetingMinutesRepository(db)
        self.action_repo = MeetingActionItemRepository(db)
        self.attachment_repo = GovernanceAttachmentRepository(db)

    # ---------------------------------------------------------------------------
    # Helper Lookups
    # ---------------------------------------------------------------------------
    async def get_committee(self, society_id: UUID, committee_id: UUID) -> Committee:
        c = await self.committee_repo.get_by_id(society_id, committee_id)
        if not c:
            raise GovernanceNotFoundError(f"Committee {committee_id} not found in society {society_id}")
        return c

    async def get_meeting(self, society_id: UUID, meeting_id: UUID) -> Meeting:
        m = await self.meeting_repo.get_by_id(society_id, meeting_id)
        if not m:
            raise GovernanceNotFoundError(f"Meeting {meeting_id} not found in society {society_id}")
        return m

    async def get_resolution(self, society_id: UUID, resolution_id: UUID) -> Resolution:
        r = await self.resolution_repo.get_by_id(society_id, resolution_id)
        if not r:
            raise GovernanceNotFoundError(f"Resolution {resolution_id} not found in society {society_id}")
        return r

    # ---------------------------------------------------------------------------
    # Committee Management
    # ---------------------------------------------------------------------------
    async def create_committee(
        self, society_id: UUID, data: CommitteeCreate, creator_id: UUID | None = None
    ) -> Committee:
        cid = creator_id or UUID("11111111-1111-1111-1111-11111111111a")
        committee_type_val = (
            data.committee_type.value if hasattr(data.committee_type, "value") else str(data.committee_type)
        )
        start_dt = getattr(data, "term_start_date", None) or getattr(data, "start_date", None)
        end_dt = getattr(data, "term_end_date", None) or getattr(data, "end_date", None)

        committee = Committee(
            society_id=society_id,
            name=data.name,
            committee_type=committee_type_val,
            description=data.description,
            status=CommitteeStatus.DRAFT.value,
            start_date=start_dt,
            end_date=end_dt,
            created_by=cid,
        )
        return await self.committee_repo.create(committee)

    async def list_committees(
        self,
        society_id: UUID,
        committee_type: Any = None,
        is_active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Committee]:
        status_filter = CommitteeStatus.ACTIVE.value if is_active is True else None
        return await self.committee_repo.list_committees(
            society_id, status=status_filter, limit=limit, offset=offset
        )

    async def update_committee(
        self, society_id: UUID, committee_id: UUID, data: CommitteeUpdate
    ) -> Committee:
        committee = await self.get_committee(society_id, committee_id)
        if data.name is not None:
            committee.name = data.name
        if data.committee_type is not None:
            committee.committee_type = (
                data.committee_type.value
                if hasattr(data.committee_type, "value")
                else str(data.committee_type)
            )
        if data.description is not None:
            committee.description = data.description
        if data.status is not None:
            committee.status = data.status.value if hasattr(data.status, "value") else str(data.status)
        start_dt = getattr(data, "term_start_date", None) or getattr(data, "start_date", None)
        if start_dt is not None:
            committee.start_date = start_dt
        end_dt = getattr(data, "term_end_date", None) or getattr(data, "end_date", None)
        if end_dt is not None:
            committee.end_date = end_dt
        await self.db.flush()
        return committee

    async def add_committee_member(
        self, society_id: UUID, committee_id: UUID, data: CommitteeMemberAdd, creator_id: UUID | None = None
    ) -> CommitteeMember:
        await self.get_committee(society_id, committee_id)
        cid = creator_id or UUID("11111111-1111-1111-1111-11111111111a")
        raw_role = getattr(data, "role", None) or getattr(data, "position", CommitteeRole.MEMBER)
        role_val = getattr(raw_role, "value", raw_role)
        eff_from = getattr(data, "effective_from", None) or datetime.now(UTC).date()
        eff_to = getattr(data, "effective_to", None)

        member = CommitteeMember(
            society_id=society_id,
            committee_id=committee_id,
            user_id=data.user_id,
            position=str(role_val),
            status="ACTIVE",
            effective_from=eff_from,
            effective_to=eff_to,
            created_by=cid,
        )
        return await self.member_repo.create(member)

    async def list_committee_members(
        self, society_id: UUID, committee_id: UUID, active_only: bool = True
    ) -> list[CommitteeMember]:
        await self.get_committee(society_id, committee_id)
        members = await self.member_repo.list_by_committee(society_id, committee_id)
        if active_only:
            return [m for m in members if m.status == "ACTIVE"]
        return members

    async def remove_committee_member(self, society_id: UUID, committee_id: UUID, member_id: UUID) -> None:
        await self.get_committee(society_id, committee_id)
        stmt = select(CommitteeMember).where(
            CommitteeMember.society_id == society_id,
            CommitteeMember.committee_id == committee_id,
            CommitteeMember.id == member_id,
        )
        res = await self.db.execute(stmt)
        member = res.scalar_one_or_none()
        if not member:
            raise GovernanceNotFoundError(f"Committee member {member_id} not found")
        member.status = "REMOVED"
        member.effective_to = datetime.now(UTC).date()
        await self.db.flush()

    # ---------------------------------------------------------------------------
    # Meeting Lifecycle & Agenda
    # ---------------------------------------------------------------------------
    async def create_meeting(self, society_id: UUID, creator_id: UUID, data: MeetingCreate) -> Meeting:
        await acquire_meeting_number_lock(self.db, society_id)
        if data.committee_id:
            await self.get_committee(society_id, data.committee_id)

        meeting_number = await self.meeting_repo.get_next_meeting_number(society_id)
        m_type = data.meeting_type.value if hasattr(data.meeting_type, "value") else str(data.meeting_type)
        starts = getattr(data, "scheduled_start_at", None) or getattr(data, "scheduled_at", datetime.now(UTC))

        meeting = Meeting(
            society_id=society_id,
            committee_id=data.committee_id,
            meeting_number=meeting_number,
            meeting_type=m_type,
            title=data.title,
            description=data.description,
            scheduled_at=starts,
            location=data.location or "Society Hall",
            status=MeetingStatus.DRAFT.value,
            created_by=creator_id,
        )
        created = await self.meeting_repo.create(meeting)
        await GovernanceDomainHooks.emit_meeting_created(society_id, created.id, meeting_number, data.title)
        return created

    async def list_meetings(
        self,
        society_id: UUID,
        committee_id: UUID | None = None,
        meeting_type: Any = None,
        meeting_status: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Meeting]:
        status_filter: str | None = None
        if meeting_status is not None:
            status_filter = str(getattr(meeting_status, "value", meeting_status))
        return await self.meeting_repo.list_meetings(
            society_id, status=status_filter, limit=limit, offset=offset
        )

    async def update_meeting(self, society_id: UUID, meeting_id: UUID, data: MeetingUpdate) -> Meeting:
        meeting = await self.get_meeting(society_id, meeting_id)
        if data.title is not None:
            meeting.title = data.title
        if data.description is not None:
            meeting.description = data.description
        sched = getattr(data, "scheduled_start_at", None) or getattr(data, "scheduled_at", None)
        if sched is not None:
            meeting.scheduled_at = sched
        if data.location is not None:
            meeting.location = data.location
        await self.db.flush()
        return meeting

    async def transition_meeting_status(
        self, society_id: UUID, meeting_id: UUID, transition: Any, actor_id: UUID
    ) -> Meeting:
        meeting = await self.get_meeting(society_id, meeting_id)
        to_status = transition.to_status if hasattr(transition, "to_status") else transition
        if isinstance(to_status, str):
            to_status = MeetingStatus(to_status)

        MeetingStateMachine.validate_transition(MeetingStatus(meeting.status), to_status)
        meeting.status = to_status.value

        if to_status == MeetingStatus.NOTICE_PUBLISHED:
            meeting.notice_published_at = datetime.now(UTC)
            await GovernanceDomainHooks.emit_meeting_notice_published(
                society_id, meeting.id, meeting.meeting_number
            )
        elif to_status == MeetingStatus.IN_PROGRESS:
            meeting.started_at = datetime.now(UTC)
        elif to_status == MeetingStatus.COMPLETED:
            meeting.ended_at = datetime.now(UTC)

        await self.db.flush()
        return meeting

    async def add_agenda_item(
        self,
        society_id: UUID,
        meeting_id: UUID,
        data: MeetingAgendaItemCreate,
        submitter_id: UUID | None = None,
    ) -> MeetingAgendaItem:
        await self.get_meeting(society_id, meeting_id)
        sid = submitter_id or UUID("11111111-1111-1111-1111-11111111111a")
        seq = getattr(data, "sequence_number", None) or getattr(data, "item_order", 1)

        item = MeetingAgendaItem(
            society_id=society_id,
            meeting_id=meeting_id,
            sequence_number=seq,
            title=data.title,
            description=data.description,
            submitted_by=sid,
        )
        return await self.agenda_repo.create(item)

    async def list_agenda_items(self, society_id: UUID, meeting_id: UUID) -> list[MeetingAgendaItem]:
        await self.get_meeting(society_id, meeting_id)
        stmt = (
            select(MeetingAgendaItem)
            .where(MeetingAgendaItem.society_id == society_id, MeetingAgendaItem.meeting_id == meeting_id)
            .order_by(MeetingAgendaItem.sequence_number.asc())
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    # ---------------------------------------------------------------------------
    # Quorum & Attendance
    # ---------------------------------------------------------------------------
    async def record_quorum(
        self, society_id: UUID, meeting_id: UUID, data: Any, recorded_by: UUID
    ) -> MeetingQuorum:
        await self.get_meeting(society_id, meeting_id)
        total_eligible = getattr(data, "total_eligible_voters", 100)
        present_in_person = getattr(data, "present_in_person", 0)
        present_by_proxy = getattr(data, "present_by_proxy", 0)
        total_present = present_in_person + present_by_proxy

        req_from_data = getattr(data, "required_count", None)
        if req_from_data is not None:
            required_count = req_from_data
        else:
            required_count = int(total_eligible * (33.33 / 100.0))

        status_val = (
            QuorumStatus.ACHIEVED.value
            if total_present >= required_count
            else QuorumStatus.NOT_ACHIEVED.value
        )

        q = MeetingQuorum(
            society_id=society_id,
            meeting_id=meeting_id,
            required_count=required_count,
            present_count=total_present,
            quorum_status=status_val,
            calculated_by=recorded_by,
        )
        saved = await self.quorum_repo.create(q)
        await GovernanceDomainHooks.emit_quorum_result(
            society_id, meeting_id, status_val, total_present, required_count
        )
        return saved

    async def get_quorum(self, society_id: UUID, meeting_id: UUID) -> MeetingQuorum | None:
        await self.get_meeting(society_id, meeting_id)
        stmt = (
            select(MeetingQuorum)
            .where(MeetingQuorum.society_id == society_id, MeetingQuorum.meeting_id == meeting_id)
            .order_by(MeetingQuorum.calculated_at.desc())
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def record_attendance(
        self, society_id: UUID, meeting_id: UUID, data: MeetingAttendanceRecord, recorded_by: UUID
    ) -> MeetingAttendance:
        await self.get_meeting(society_id, meeting_id)
        uid = getattr(data, "user_id", recorded_by)
        status_val = data.status.value if hasattr(data.status, "value") else str(data.status)

        existing = await self.attendance_repo.get_by_user_meeting(society_id, meeting_id, uid)
        if existing:
            existing.status = status_val
            existing.notes = data.notes
            await self.db.flush()
            return existing

        att = MeetingAttendance(
            society_id=society_id,
            meeting_id=meeting_id,
            user_id=uid,
            status=status_val,
            check_in=datetime.now(UTC),
            recorded_by=recorded_by,
            notes=data.notes,
        )
        return await self.attendance_repo.create(att)

    async def list_attendance(self, society_id: UUID, meeting_id: UUID) -> list[MeetingAttendance]:
        await self.get_meeting(society_id, meeting_id)
        stmt = select(MeetingAttendance).where(
            MeetingAttendance.society_id == society_id, MeetingAttendance.meeting_id == meeting_id
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    # ---------------------------------------------------------------------------
    # Resolution & Voting
    # ---------------------------------------------------------------------------
    async def create_resolution(
        self, society_id: UUID, proposer_id: UUID, data: ResolutionCreate
    ) -> Resolution:
        await acquire_resolution_number_lock(self.db, society_id)
        if data.meeting_id:
            await self.get_meeting(society_id, data.meeting_id)

        res_number = await self.resolution_repo.get_next_resolution_number(society_id)
        res_type = (
            getattr(data, "resolution_type", ResolutionStatus.DRAFT).value
            if hasattr(getattr(data, "resolution_type", None), "value")
            else "ORDINARY"
        )

        v_type = getattr(data, "voting_type", None)
        v_rule = getattr(data, "voting_rule", None)
        if v_type is not None:
            chosen_rule = v_type
        elif v_rule is not None:
            chosen_rule = v_rule
        else:
            chosen_rule = VotingRule.SIMPLE_MAJORITY

        v_rule_val = chosen_rule.value if hasattr(chosen_rule, "value") else str(chosen_rule)

        resolution = Resolution(
            society_id=society_id,
            meeting_id=data.meeting_id,
            agenda_item_id=data.agenda_item_id,
            resolution_number=res_number,
            title=data.title,
            description=data.description,
            resolution_type=res_type,
            voting_rule=v_rule_val,
            status=ResolutionStatus.PROPOSED.value,
            proposed_by=proposer_id,
            seconded_by=data.seconded_by,
        )
        created = await self.resolution_repo.create(resolution)
        await GovernanceDomainHooks.emit_resolution_proposed(society_id, created.id, res_number, data.title)
        return created

    async def list_resolutions(
        self,
        society_id: UUID,
        meeting_id: UUID | None = None,
        committee_id: UUID | None = None,
        resolution_status: Any = None,
        voting_type: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Resolution]:
        status_filter: str | None = None
        if resolution_status is not None:
            status_filter = str(getattr(resolution_status, "value", resolution_status))

        stmt = select(Resolution).where(Resolution.society_id == society_id)
        if meeting_id:
            stmt = stmt.where(Resolution.meeting_id == meeting_id)
        if status_filter:
            stmt = stmt.where(Resolution.status == status_filter)
        stmt = stmt.order_by(Resolution.created_at.desc()).offset(offset).limit(limit)
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def update_resolution(
        self, society_id: UUID, resolution_id: UUID, data: ResolutionUpdate
    ) -> Resolution:
        res = await self.get_resolution(society_id, resolution_id)
        if data.title is not None:
            res.title = data.title
        if data.description is not None:
            res.description = data.description
        await self.db.flush()
        return res

    async def transition_resolution_status(
        self, society_id: UUID, resolution_id: UUID, transition: Any, actor_id: UUID
    ) -> Resolution:
        res = await self.get_resolution(society_id, resolution_id)
        to_status = transition.to_status if hasattr(transition, "to_status") else transition
        if isinstance(to_status, str):
            to_status = ResolutionStatus(to_status)

        old_status = res.status
        res.status = to_status.value
        await self.db.flush()

        await self.res_history_repo.create(
            ResolutionStatusHistory(
                society_id=society_id,
                resolution_id=res.id,
                old_status=old_status,
                new_status=to_status.value,
                changed_by_user_id=actor_id,
                reason=f"Status transitioned to {to_status.value}",
            )
        )
        return res

    async def cast_vote(
        self, society_id: UUID, resolution_id: UUID, voter_id: UUID, vote_data: Any
    ) -> ResolutionVote:
        await acquire_resolution_vote_lock(self.db, resolution_id)
        await self.get_resolution(society_id, resolution_id)

        choice_val = getattr(vote_data, "choice", None) or getattr(vote_data, "vote", VoteValue.FOR)
        choice_str = str(getattr(choice_val, "value", choice_val))

        existing = await self.vote_repo.get_by_user_resolution(society_id, resolution_id, voter_id)
        if existing:
            raise DuplicateVoteError(
                f"User {voter_id} has already cast a vote for resolution {resolution_id}."
            )

        vote = ResolutionVote(
            society_id=society_id,
            resolution_id=resolution_id,
            user_id=voter_id,
            vote=choice_str,
            recorded_by=voter_id,
        )
        saved = await self.vote_repo.create(vote)
        return saved

    async def list_votes(self, society_id: UUID, resolution_id: UUID) -> list[ResolutionVote]:
        await self.get_resolution(society_id, resolution_id)
        stmt = select(ResolutionVote).where(
            ResolutionVote.society_id == society_id, ResolutionVote.resolution_id == resolution_id
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    # ---------------------------------------------------------------------------
    # Minutes & Action Items
    # ---------------------------------------------------------------------------
    async def create_meeting_minutes(
        self, society_id: UUID, meeting_id: UUID, prepared_by: UUID, data: MeetingMinutesCreate
    ) -> MeetingMinutes:
        await self.get_meeting(society_id, meeting_id)
        latest = await self.minutes_repo.get_latest_by_meeting(society_id, meeting_id)
        new_version = (latest.version + 1) if latest else 1

        minutes = MeetingMinutes(
            society_id=society_id,
            meeting_id=meeting_id,
            version=new_version,
            status=MinutesStatus.DRAFT.value,
            summary=data.summary,
            prepared_by=prepared_by,
        )
        return await self.minutes_repo.create(minutes)

    async def get_meeting_minutes(self, society_id: UUID, meeting_id: UUID) -> MeetingMinutes | None:
        await self.get_meeting(society_id, meeting_id)
        return await self.minutes_repo.get_latest_by_meeting(society_id, meeting_id)

    async def approve_and_publish_minutes(
        self, society_id: UUID, meeting_id: UUID, approver_id: UUID
    ) -> MeetingMinutes:
        minutes = await self.minutes_repo.get_latest_by_meeting(society_id, meeting_id)
        if not minutes:
            raise GovernanceNotFoundError("No meeting minutes found to approve")

        if minutes.prepared_by == approver_id:
            raise MakerCheckerViolationError("Author cannot approve their own minutes draft")

        minutes.status = ResolutionStatus.PUBLISHED.value
        minutes.approved_by = approver_id
        minutes.approved_at = datetime.now(UTC)
        await self.db.flush()

        await GovernanceDomainHooks.emit_minutes_published(society_id, meeting_id, minutes.version)
        return minutes

    async def create_action_item(self, society_id: UUID, data: MeetingActionItemCreate) -> MeetingActionItem:
        if data.meeting_id:
            await self.get_meeting(society_id, data.meeting_id)

        assignee_id_val: UUID = (
            getattr(data, "assignee_id", None)
            or getattr(data, "assigned_to", None)
            or UUID("11111111-1111-1111-1111-11111111111a")
        )
        title_val: str = getattr(data, "title", None) or (
            data.description[:50] if data.description else "Action Item"
        )

        item = MeetingActionItem(
            society_id=society_id,
            meeting_id=data.meeting_id or UUID("00000000-0000-0000-0000-000000000000"),
            resolution_id=data.resolution_id,
            agenda_item_id=data.agenda_item_id,
            title=title_val,
            description=data.description,
            assigned_to=assignee_id_val,
            due_date=data.due_date,
            priority=getattr(data, "priority", "NORMAL"),
            status=ActionItemStatus.PENDING.value,
        )
        saved = await self.action_repo.create(item)
        await GovernanceDomainHooks.emit_action_item_created(society_id, saved.id, title_val, assignee_id_val)
        return saved

    async def list_action_items(
        self,
        society_id: UUID,
        meeting_id: UUID | None = None,
        assignee_id: UUID | None = None,
        item_status: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MeetingActionItem]:
        status_filter = (
            item_status.value
            if hasattr(item_status, "value")
            else (str(item_status) if item_status else None)
        )
        stmt = select(MeetingActionItem).where(MeetingActionItem.society_id == society_id)
        if meeting_id:
            stmt = stmt.where(MeetingActionItem.meeting_id == meeting_id)
        if assignee_id:
            stmt = stmt.where(MeetingActionItem.assigned_to == assignee_id)
        if status_filter:
            stmt = stmt.where(MeetingActionItem.status == status_filter)
        stmt = stmt.order_by(MeetingActionItem.created_at.desc()).offset(offset).limit(limit)
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def update_action_item(
        self, society_id: UUID, action_item_id: UUID, data: MeetingActionItemUpdate
    ) -> MeetingActionItem:
        stmt = select(MeetingActionItem).where(
            MeetingActionItem.society_id == society_id, MeetingActionItem.id == action_item_id
        )
        res = await self.db.execute(stmt)
        item = res.scalar_one_or_none()
        if not item:
            raise GovernanceNotFoundError(f"Action item {action_item_id} not found")

        if data.status is not None:
            st_val: str = data.status.value if hasattr(data.status, "value") else str(data.status)
            item.status = st_val
        if data.title is not None:
            item.title = data.title
        if data.description is not None:
            item.description = data.description
        await self.db.flush()
        return item

    # ---------------------------------------------------------------------------
    # Governance Attachments
    # ---------------------------------------------------------------------------
    async def create_attachment(
        self, society_id: UUID, uploaded_by: UUID, data: GovernanceAttachmentCreate
    ) -> GovernanceAttachment:
        safe_name = data.file_name.replace("..", "").replace("/", "").replace("\\", "")
        storage_key = f"societies/{society_id}/governance/{data.entity_id}/{data.file_size}_{safe_name}"

        attachment = GovernanceAttachment(
            society_id=society_id,
            entity_type=data.entity_type,
            entity_id=data.entity_id,
            file_name=safe_name,
            file_size=data.file_size,
            mime_type=data.mime_type,
            storage_object_key=storage_key,
            uploaded_by=uploaded_by,
        )
        return await self.attachment_repo.create(attachment)

    async def list_attachments(
        self,
        society_id: UUID,
        meeting_id: UUID | None = None,
        resolution_id: UUID | None = None,
        committee_id: UUID | None = None,
    ) -> list[GovernanceAttachment]:
        stmt = select(GovernanceAttachment).where(GovernanceAttachment.society_id == society_id)
        if meeting_id:
            stmt = stmt.where(GovernanceAttachment.entity_id == meeting_id)
        elif resolution_id:
            stmt = stmt.where(GovernanceAttachment.entity_id == resolution_id)
        elif committee_id:
            stmt = stmt.where(GovernanceAttachment.entity_id == committee_id)
        res = await self.db.execute(stmt)
        return list(res.scalars().all())
