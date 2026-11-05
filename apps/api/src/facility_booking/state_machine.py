"""State Machine logic for Facility Bookings."""

from apps.api.src.facility_booking.enums import BookingStatus
from apps.api.src.facility_booking.exceptions import InvalidBookingStateTransitionError

ALLOWED_BOOKING_TRANSITIONS: dict[BookingStatus, set[BookingStatus]] = {
    BookingStatus.DRAFT: {
        BookingStatus.PENDING_APPROVAL,
        BookingStatus.APPROVED,
        BookingStatus.CANCELLED,
    },
    BookingStatus.PENDING_APPROVAL: {
        BookingStatus.APPROVED,
        BookingStatus.REJECTED,
        BookingStatus.CANCELLED,
        BookingStatus.EXPIRED,
    },
    BookingStatus.APPROVED: {
        BookingStatus.CHECKED_IN,
        BookingStatus.CANCELLED,
        BookingStatus.NO_SHOW,
        BookingStatus.COMPLETED,
    },
    BookingStatus.CHECKED_IN: {
        BookingStatus.COMPLETED,
    },
    BookingStatus.REJECTED: set(),
    BookingStatus.CANCELLED: set(),
    BookingStatus.COMPLETED: set(),
    BookingStatus.NO_SHOW: set(),
    BookingStatus.EXPIRED: set(),
}

ACTIVE_RESERVATION_STATES: set[BookingStatus] = {
    BookingStatus.PENDING_APPROVAL,
    BookingStatus.APPROVED,
    BookingStatus.CHECKED_IN,
}


def validate_booking_status_transition(current: BookingStatus, target: BookingStatus) -> None:
    if current == target:
        return
    allowed = ALLOWED_BOOKING_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidBookingStateTransitionError(f"Invalid transition from {current.value} to {target.value}")


class FacilityBookingStateMachine:
    """State Machine class wrapper for facility booking status transitions."""

    @staticmethod
    def validate_transition(current: BookingStatus, target: BookingStatus) -> None:
        validate_booking_status_transition(current, target)
