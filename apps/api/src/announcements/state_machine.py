"""Phase 16 Announcement Lifecycle State Machine."""

from apps.api.src.announcements.enums import AnnouncementStatus
from apps.api.src.announcements.exceptions import InvalidAnnouncementStateError

ALLOWED_ANNOUNCEMENT_TRANSITIONS: dict[AnnouncementStatus, set[AnnouncementStatus]] = {
    AnnouncementStatus.DRAFT: {
        AnnouncementStatus.PENDING_REVIEW,
        AnnouncementStatus.APPROVED,
        AnnouncementStatus.SCHEDULED,
        AnnouncementStatus.PUBLISHED,
        AnnouncementStatus.ARCHIVED,
    },
    AnnouncementStatus.PENDING_REVIEW: {
        AnnouncementStatus.APPROVED,
        AnnouncementStatus.REJECTED,
        AnnouncementStatus.DRAFT,
        AnnouncementStatus.ARCHIVED,
    },
    AnnouncementStatus.APPROVED: {
        AnnouncementStatus.SCHEDULED,
        AnnouncementStatus.PUBLISHED,
        AnnouncementStatus.ARCHIVED,
    },
    AnnouncementStatus.SCHEDULED: {
        AnnouncementStatus.PUBLISHED,
        AnnouncementStatus.ARCHIVED,
        AnnouncementStatus.DRAFT,
    },
    AnnouncementStatus.PUBLISHED: {
        AnnouncementStatus.EXPIRED,
        AnnouncementStatus.ARCHIVED,
    },
    AnnouncementStatus.EXPIRED: {
        AnnouncementStatus.ARCHIVED,
    },
    AnnouncementStatus.REJECTED: {
        AnnouncementStatus.DRAFT,
        AnnouncementStatus.ARCHIVED,
    },
    AnnouncementStatus.ARCHIVED: set(),
}

ACTIVE_ANNOUNCEMENT_STATES: set[AnnouncementStatus] = {
    AnnouncementStatus.PUBLISHED,
}


class AnnouncementStateMachine:
    """State Machine validator for announcement status transitions."""

    @staticmethod
    def validate_transition(current: AnnouncementStatus, target: AnnouncementStatus) -> None:
        if current == target:
            return
        allowed = ALLOWED_ANNOUNCEMENT_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise InvalidAnnouncementStateError(
                f"Invalid announcement status transition from '{current.value}' to '{target.value}'."
            )
