"""Phase 19 Incident Management Domain Exceptions."""


class IncidentError(Exception):
    """Base exception for Incident domain."""

    def __init__(self, message: str, code: str = "INCIDENT_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class IncidentNotFoundError(IncidentError):
    def __init__(self, message: str = "Incident entity not found", code: str = "INCIDENT_NOT_FOUND"):
        super().__init__(message, code=code)


class IncidentCategoryNotFoundError(IncidentNotFoundError):
    def __init__(self, message: str = "Incident category not found"):
        super().__init__(message, code="INCIDENT_CATEGORY_NOT_FOUND")


class EmergencyContactNotFoundError(IncidentNotFoundError):
    def __init__(self, message: str = "Emergency contact not found"):
        super().__init__(message, code="EMERGENCY_CONTACT_NOT_FOUND")


class InvalidIncidentStateError(IncidentError):
    def __init__(self, message: str = "Invalid incident state transition"):
        super().__init__(message, code="INVALID_INCIDENT_STATE")


class VoiceDurationExceededError(IncidentError):
    def __init__(
        self, message: str = "Voice note duration exceeds maximum allowed server limit (60 seconds)"
    ):
        super().__init__(message, code="VOICE_DURATION_EXCEEDED")


class IncidentOverridePermissionError(IncidentError):
    def __init__(
        self, message: str = "Emergency override requires incident.override permission and logged reason"
    ):
        super().__init__(message, code="OVERRIDE_PERMISSION_DENIED")


class ResponderAssignmentError(IncidentError):
    def __init__(self, message: str = "Responder assignment failed"):
        super().__init__(message, code="RESPONDER_ASSIGNMENT_FAILED")
