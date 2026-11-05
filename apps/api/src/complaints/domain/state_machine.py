"""State machine transitions and rules for Complaint lifecycle."""

from apps.api.src.complaints.domain.exceptions import InvalidComplaintStatusTransitionError

VALID_COMPLAINT_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "OPEN": {"ACKNOWLEDGED", "ASSIGNED", "IN_PROGRESS", "RESOLVED", "CANCELLED"},
    "ACKNOWLEDGED": {"ASSIGNED", "IN_PROGRESS", "WAITING_FOR_RESIDENT", "RESOLVED", "CANCELLED"},
    "ASSIGNED": {"IN_PROGRESS", "WAITING_FOR_RESIDENT", "CANCELLED", "RESOLVED"},
    "IN_PROGRESS": {"WAITING_FOR_RESIDENT", "RESOLVED", "CANCELLED"},
    "WAITING_FOR_RESIDENT": {"IN_PROGRESS", "RESOLVED", "CANCELLED"},
    "RESOLVED": {"CLOSED", "REOPENED"},
    "REOPENED": {"ASSIGNED", "IN_PROGRESS", "RESOLVED", "CANCELLED"},
    "CLOSED": {"REOPENED"},  # Allowed only under explicit policy / elevated permission
    "CANCELLED": set(),  # Terminal state
}


def validate_status_transition(current_status: str, new_status: str) -> None:
    """
    Validate that transitioning from `current_status` to `new_status` is deterministic and permitted.
    Raises InvalidComplaintStatusTransitionError if transition is forbidden.
    """
    if current_status == new_status:
        return

    allowed = VALID_COMPLAINT_STATUS_TRANSITIONS.get(current_status, set())
    if new_status not in allowed:
        raise InvalidComplaintStatusTransitionError(current_status, new_status)


def validate_complaint_status_transition(current_status: str, new_status: str) -> None:
    """Alias for validate_status_transition."""
    validate_status_transition(current_status, new_status)
