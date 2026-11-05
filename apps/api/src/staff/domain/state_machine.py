"""Staff Status Lifecycle State Machine."""

from apps.api.src.staff.domain.enums import StaffStatus
from apps.api.src.staff.domain.exceptions import InvalidStaffStatusTransitionError


class StaffStatusStateMachine:
    """State Machine governing valid StaffStatus transitions."""

    ALLOWED_TRANSITIONS: dict[StaffStatus, set[StaffStatus]] = {
        StaffStatus.ONBOARDING: {StaffStatus.ACTIVE, StaffStatus.OFFBOARDED},
        StaffStatus.ACTIVE: {StaffStatus.INACTIVE, StaffStatus.SUSPENDED, StaffStatus.OFFBOARDED},
        StaffStatus.INACTIVE: {StaffStatus.ACTIVE, StaffStatus.OFFBOARDED},
        StaffStatus.SUSPENDED: {StaffStatus.ACTIVE, StaffStatus.OFFBOARDED},
        StaffStatus.OFFBOARDED: set(),  # Terminal status
    }

    @classmethod
    def validate_transition(cls, current_status: str, target_status: str) -> None:
        """Validate whether transition from current_status to target_status is allowed.

        Raises InvalidStaffStatusTransitionError if disallowed.
        """
        try:
            curr = StaffStatus(current_status)
            target = StaffStatus(target_status)
        except ValueError:
            raise InvalidStaffStatusTransitionError(current_status, target_status)

        if curr == target:
            return  # No-op status change

        allowed = cls.ALLOWED_TRANSITIONS.get(curr, set())
        if target not in allowed:
            raise InvalidStaffStatusTransitionError(current_status, target_status)
