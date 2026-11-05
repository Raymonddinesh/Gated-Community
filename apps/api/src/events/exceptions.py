"""Phase 17 Event Domain Exceptions."""


class EventError(Exception):
    """Base exception for Event domain."""

    def __init__(self, message: str, code: str = "EVENT_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class EventNotFoundError(EventError):
    def __init__(self, message: str = "Event not found"):
        super().__init__(message, code="EVENT_NOT_FOUND")


class InvalidEventStateError(EventError):
    def __init__(self, message: str = "Invalid event state transition"):
        super().__init__(message, code="INVALID_EVENT_STATE")


class InvalidEventTimeError(EventError):
    def __init__(self, message: str = "Invalid event start or end time"):
        super().__init__(message, code="INVALID_EVENT_TIME")


class EventApprovalRequiredError(EventError):
    def __init__(self, message: str = "Event approval is required before publishing"):
        super().__init__(message, code="EVENT_APPROVAL_REQUIRED")


class EventAlreadyPublishedError(EventError):
    def __init__(self, message: str = "Event is already published"):
        super().__init__(message, code="EVENT_ALREADY_PUBLISHED")


class EventCancelledError(EventError):
    def __init__(self, message: str = "Event has been cancelled"):
        super().__init__(message, code="EVENT_CANCELLED")


class RegistrationNotOpenError(EventError):
    def __init__(self, message: str = "Event registration is not open"):
        super().__init__(message, code="REGISTRATION_NOT_OPEN")


class RegistrationClosedError(EventError):
    def __init__(self, message: str = "Event registration is closed"):
        super().__init__(message, code="REGISTRATION_CLOSED")


class RegistrationFullError(EventError):
    def __init__(self, message: str = "Event registration capacity reached"):
        super().__init__(message, code="REGISTRATION_FULL")


class DuplicateRegistrationError(EventError):
    def __init__(self, message: str = "User is already registered for this event"):
        super().__init__(message, code="DUPLICATE_REGISTRATION")


class CapacityExceededError(EventError):
    def __init__(self, message: str = "Event maximum capacity exceeded"):
        super().__init__(message, code="CAPACITY_EXCEEDED")


class WaitlistRequiredError(EventError):
    def __init__(self, message: str = "Registration moved to waitlist due to full capacity"):
        super().__init__(message, code="WAITLIST_REQUIRED")


class FacilityNotFoundError(EventError):
    def __init__(self, message: str = "Associated facility not found"):
        super().__init__(message, code="FACILITY_NOT_FOUND")


class FacilityAccessDeniedError(EventError):
    def __init__(self, message: str = "Facility access denied"):
        super().__init__(message, code="FACILITY_ACCESS_DENIED")


class FacilityBookingConflictError(EventError):
    def __init__(self, message: str = "Facility booking time conflict detected"):
        super().__init__(message, code="FACILITY_BOOKING_CONFLICT")


class InvalidFacilityAssociationError(EventError):
    def __init__(self, message: str = "Invalid facility association for event"):
        super().__init__(message, code="INVALID_FACILITY_ASSOCIATION")


class AttendanceNotAllowedError(EventError):
    def __init__(self, message: str = "Attendance recording not allowed for this event state"):
        super().__init__(message, code="ATTENDANCE_NOT_ALLOWED")


class ParticipantAccessDeniedError(EventError):
    def __init__(self, message: str = "Participant details access denied"):
        super().__init__(message, code="PARTICIPANT_ACCESS_DENIED")


class AttachmentAccessDeniedError(EventError):
    def __init__(self, message: str = "Event attachment access denied"):
        super().__init__(message, code="ATTACHMENT_ACCESS_DENIED")


class DelegateAccessDeniedError(EventError):
    def __init__(self, message: str = "Delegate access denied or delegation expired"):
        super().__init__(message, code="DELEGATE_ACCESS_DENIED")


class CrossTenantEventError(EventError):
    def __init__(self, message: str = "Cross-tenant event access or operation forbidden"):
        super().__init__(message, code="CROSS_TENANT_EVENT_ERROR")
