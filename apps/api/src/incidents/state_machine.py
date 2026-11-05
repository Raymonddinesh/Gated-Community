"""Phase 19 Incident Management State Machine."""

from apps.api.src.incidents.enums import IncidentStatus
from apps.api.src.incidents.exceptions import InvalidIncidentStateError


class IncidentStateMachine:
    """Enforces server-authoritative incident lifecycle state transitions."""

    VALID_TRANSITIONS: dict[str, set[str]] = {
        IncidentStatus.REPORTED.value: {
            IncidentStatus.TRIAGED.value,
            IncidentStatus.ACKNOWLEDGED.value,
            IncidentStatus.RESPONSE_STARTED.value,
            IncidentStatus.CANCELLED.value,
        },
        IncidentStatus.TRIAGED.value: {
            IncidentStatus.ACKNOWLEDGED.value,
            IncidentStatus.RESPONSE_STARTED.value,
            IncidentStatus.CONTAINED.value,
            IncidentStatus.ESCALATED.value,
            IncidentStatus.CANCELLED.value,
        },
        IncidentStatus.ACKNOWLEDGED.value: {
            IncidentStatus.RESPONSE_STARTED.value,
            IncidentStatus.CONTAINED.value,
            IncidentStatus.RESOLVED.value,
            IncidentStatus.ESCALATED.value,
            IncidentStatus.CANCELLED.value,
        },
        IncidentStatus.RESPONSE_STARTED.value: {
            IncidentStatus.CONTAINED.value,
            IncidentStatus.RESOLVED.value,
            IncidentStatus.ESCALATED.value,
            IncidentStatus.CANCELLED.value,
        },
        IncidentStatus.CONTAINED.value: {
            IncidentStatus.RESOLVED.value,
            IncidentStatus.CLOSED.value,
            IncidentStatus.ESCALATED.value,
        },
        IncidentStatus.RESOLVED.value: {
            IncidentStatus.CLOSED.value,
        },
        IncidentStatus.ESCALATED.value: {
            IncidentStatus.RESPONSE_STARTED.value,
            IncidentStatus.CONTAINED.value,
            IncidentStatus.RESOLVED.value,
            IncidentStatus.CLOSED.value,
        },
        IncidentStatus.CANCELLED.value: set(),
        IncidentStatus.CLOSED.value: set(),
    }

    @classmethod
    def validate_transition(cls, current_status: str, target_status: str, is_override: bool = False) -> None:
        """Validate state transition.

        If is_override is True, transition is permitted from any state to any state
        (except identical state).
        """
        if current_status == target_status:
            return  # No-op

        if is_override:
            return  # Admin override allowed

        valid_targets = cls.VALID_TRANSITIONS.get(current_status, set())
        if target_status not in valid_targets:
            raise InvalidIncidentStateError(
                f"Cannot transition incident from status '{current_status}' to '{target_status}'. "
                f"Allowed target statuses: {sorted(list(valid_targets)) if valid_targets else 'None (terminal state)'}."
            )
