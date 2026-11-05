"""Phase 18 Governance State Machines."""

from apps.api.src.governance.enums import MeetingStatus, ResolutionStatus
from apps.api.src.governance.exceptions import InvalidGovernanceStateError


class MeetingStateMachine:
    """Validates allowed state transitions for Meetings."""

    ALLOWED_TRANSITIONS = {
        MeetingStatus.DRAFT: {
            MeetingStatus.SCHEDULED,
            MeetingStatus.NOTICE_PUBLISHED,
            MeetingStatus.CANCELLED,
        },
        MeetingStatus.SCHEDULED: {
            MeetingStatus.NOTICE_PUBLISHED,
            MeetingStatus.IN_PROGRESS,
            MeetingStatus.CANCELLED,
        },
        MeetingStatus.NOTICE_PUBLISHED: {
            MeetingStatus.IN_PROGRESS,
            MeetingStatus.CANCELLED,
            MeetingStatus.ADJOURNED,
        },
        MeetingStatus.IN_PROGRESS: {
            MeetingStatus.COMPLETED,
            MeetingStatus.ADJOURNED,
            MeetingStatus.CANCELLED,
        },
        MeetingStatus.ADJOURNED: {
            MeetingStatus.SCHEDULED,
            MeetingStatus.CANCELLED,
        },
        MeetingStatus.COMPLETED: set(),
        MeetingStatus.CANCELLED: set(),
    }

    @classmethod
    def validate_transition(
        cls, current_status: MeetingStatus | str, new_status: MeetingStatus | str
    ) -> None:
        curr = MeetingStatus(current_status)
        new = MeetingStatus(new_status)

        if curr == new:
            return  # No-op

        allowed = cls.ALLOWED_TRANSITIONS.get(curr, set())
        if new not in allowed:
            raise InvalidGovernanceStateError(
                f"Cannot transition Meeting state from '{curr.value}' to '{new.value}'."
            )


class ResolutionStateMachine:
    """Validates allowed state transitions for Resolutions."""

    ALLOWED_TRANSITIONS = {
        ResolutionStatus.DRAFT: {
            ResolutionStatus.PROPOSED,
            ResolutionStatus.UNDER_DISCUSSION,
            ResolutionStatus.VOTING,
            ResolutionStatus.WITHDRAWN,
        },
        ResolutionStatus.PROPOSED: {
            ResolutionStatus.UNDER_DISCUSSION,
            ResolutionStatus.VOTING,
            ResolutionStatus.WITHDRAWN,
        },
        ResolutionStatus.UNDER_DISCUSSION: {
            ResolutionStatus.VOTING,
            ResolutionStatus.WITHDRAWN,
        },
        ResolutionStatus.VOTING: {
            ResolutionStatus.APPROVED,
            ResolutionStatus.REJECTED,
            ResolutionStatus.WITHDRAWN,
        },
        ResolutionStatus.APPROVED: {
            ResolutionStatus.RECORDED,
        },
        ResolutionStatus.REJECTED: set(),
        ResolutionStatus.WITHDRAWN: set(),
        ResolutionStatus.RECORDED: set(),
    }

    @classmethod
    def validate_transition(
        cls, current_status: ResolutionStatus | str, new_status: ResolutionStatus | str
    ) -> None:
        curr = ResolutionStatus(current_status)
        new = ResolutionStatus(new_status)

        if curr == new:
            return  # No-op

        allowed = cls.ALLOWED_TRANSITIONS.get(curr, set())
        if new not in allowed:
            raise InvalidGovernanceStateError(
                f"Cannot transition Resolution state from '{curr.value}' to '{new.value}'."
            )
