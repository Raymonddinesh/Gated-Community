"""Phase 17 Event State Machine."""

from apps.api.src.events.enums import EventStatus
from apps.api.src.events.exceptions import InvalidEventStateError


class EventStateMachine:
    """Validates allowed state transitions for Events."""

    ALLOWED_TRANSITIONS = {
        EventStatus.DRAFT: {
            EventStatus.PENDING_APPROVAL,
            EventStatus.APPROVED,
            EventStatus.PUBLISHED,
            EventStatus.REGISTRATION_OPEN,
            EventStatus.CANCELLED,
        },
        EventStatus.PENDING_APPROVAL: {
            EventStatus.APPROVED,
            EventStatus.REJECTED,
            EventStatus.CANCELLED,
        },
        EventStatus.APPROVED: {
            EventStatus.SCHEDULED,
            EventStatus.PUBLISHED,
            EventStatus.REGISTRATION_OPEN,
            EventStatus.CANCELLED,
        },
        EventStatus.SCHEDULED: {
            EventStatus.PUBLISHED,
            EventStatus.REGISTRATION_OPEN,
            EventStatus.CANCELLED,
        },
        EventStatus.PUBLISHED: {
            EventStatus.REGISTRATION_OPEN,
            EventStatus.IN_PROGRESS,
            EventStatus.COMPLETED,
            EventStatus.CANCELLED,
        },
        EventStatus.REGISTRATION_OPEN: {
            EventStatus.IN_PROGRESS,
            EventStatus.COMPLETED,
            EventStatus.CANCELLED,
        },
        EventStatus.IN_PROGRESS: {
            EventStatus.COMPLETED,
            EventStatus.CANCELLED,
        },
        EventStatus.COMPLETED: set(),
        EventStatus.CANCELLED: set(),
        EventStatus.REJECTED: set(),
    }

    @classmethod
    def validate_transition(cls, current_status: EventStatus | str, new_status: EventStatus | str) -> None:
        curr = EventStatus(current_status)
        new = EventStatus(new_status)

        if curr == new:
            return  # No-op

        allowed = cls.ALLOWED_TRANSITIONS.get(curr, set())
        if new not in allowed:
            raise InvalidEventStateError(
                f"Cannot transition Event state from '{curr.value}' to '{new.value}'."
            )
