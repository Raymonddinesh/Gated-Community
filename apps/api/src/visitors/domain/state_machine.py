"""State machines for Visitor Invitations, Approvals, and Visit Lifecycles."""

from apps.api.src.visitors.domain.exceptions import InvalidVisitorStatusError

# Valid Invitation status transitions
INVITATION_TRANSITIONS: dict[str, set[str]] = {
    "PENDING": {"APPROVED", "REJECTED", "EXPIRED", "CANCELLED", "USED"},
    "APPROVED": {"USED", "EXPIRED", "CANCELLED"},
    "REJECTED": set(),
    "EXPIRED": set(),
    "CANCELLED": set(),
    "USED": set(),
}

# Valid Approval status transitions
APPROVAL_TRANSITIONS: dict[str, set[str]] = {
    "PENDING": {"APPROVED", "REJECTED", "EXPIRED"},
    "APPROVED": set(),
    "REJECTED": set(),
    "EXPIRED": set(),
}


def validate_invitation_transition(current_status: str, target_status: str) -> None:
    """Validate visitor invitation status transition."""
    if current_status == target_status:
        return
    allowed = INVITATION_TRANSITIONS.get(current_status, set())
    if target_status not in allowed:
        raise InvalidVisitorStatusError(
            f"Cannot transition visitor invitation from '{current_status}' to '{target_status}'"
        )


def validate_approval_transition(current_status: str, target_status: str) -> None:
    """Validate visitor approval status transition."""
    if current_status == target_status:
        return
    allowed = APPROVAL_TRANSITIONS.get(current_status, set())
    if target_status not in allowed:
        raise InvalidVisitorStatusError(
            f"Cannot transition visitor approval from '{current_status}' to '{target_status}'"
        )
