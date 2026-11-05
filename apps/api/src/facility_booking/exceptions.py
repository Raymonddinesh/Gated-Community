"""Phase 15 Facility Booking Custom Exceptions."""

from fastapi import HTTPException, status


class FacilityBookingException(HTTPException):
    def __init__(self, detail: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        super().__init__(status_code=status_code, detail=detail)


class BookingNotFoundError(FacilityBookingException):
    def __init__(self, detail: str = "Booking not found."):
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)


class FacilityNotFoundError(FacilityBookingException):
    def __init__(self, detail: str = "Facility not found."):
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)


class FacilityNotBookableError(FacilityBookingException):
    def __init__(self, detail: str = "Facility is not configured for reservations or is disabled."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class BookingConflictError(FacilityBookingException):
    def __init__(self, detail: str = "Requested facility and time slot overlaps with another reservation."):
        super().__init__(detail=detail, status_code=status.HTTP_409_CONFLICT)


class BlackoutConflictError(FacilityBookingException):
    def __init__(
        self, detail: str = "Requested time slot falls within a facility blackout or maintenance window."
    ):
        super().__init__(detail=detail, status_code=status.HTTP_409_CONFLICT)


class OutsideAvailabilityError(FacilityBookingException):
    def __init__(self, detail: str = "Requested booking time is outside facility operating hours."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class BookingDurationInvalidError(FacilityBookingException):
    def __init__(self, detail: str = "Booking duration violates minimum or maximum allowed duration rules."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class CapacityExceededError(FacilityBookingException):
    def __init__(self, detail: str = "Participant count exceeds maximum facility capacity."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class AdvanceBookingLimitExceededError(FacilityBookingException):
    def __init__(self, detail: str = "Booking date exceeds maximum advance booking limit."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class CancellationNotAllowedError(FacilityBookingException):
    def __init__(self, detail: str = "Cancellation is not permitted within the minimum notice period."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class InvalidBookingStateTransitionError(FacilityBookingException):
    def __init__(self, detail: str = "Invalid booking status transition."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class UnauthorizedBookingActionError(FacilityBookingException):
    def __init__(self, detail: str = "User is not authorized to perform this booking action."):
        super().__init__(detail=detail, status_code=status.HTTP_403_FORBIDDEN)


# Aliases for consistent domain service exception imports
BookingSlotConflictError = BookingConflictError
FacilityBlackoutConflictError = BlackoutConflictError
OutsideOperatingHoursError = OutsideAvailabilityError
BookingDurationViolationError = BookingDurationInvalidError
BookingCapacityExceededError = CapacityExceededError
AdvanceBookingWindowExceededError = AdvanceBookingLimitExceededError
CancellationNoticePeriodViolationError = CancellationNotAllowedError
InvalidBookingStatusTransitionError = InvalidBookingStateTransitionError
