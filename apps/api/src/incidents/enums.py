"""Phase 19 Incident Management Domain Enums."""

from enum import StrEnum


class IncidentSeverity(StrEnum):
    """Incident severity classification."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class IncidentStatus(StrEnum):
    """Incident lifecycle state machine statuses."""

    REPORTED = "REPORTED"
    TRIAGED = "TRIAGED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESPONSE_STARTED = "RESPONSE_STARTED"
    CONTAINED = "CONTAINED"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    ESCALATED = "ESCALATED"
    CANCELLED = "CANCELLED"


class ReporterType(StrEnum):
    """Reporter identity classification."""

    RESIDENT = "RESIDENT"
    STAFF = "STAFF"
    SECURITY = "SECURITY"
    COMMITTEE = "COMMITTEE"
    VENDOR = "VENDOR"
    ANONYMOUS = "ANONYMOUS"
    SYSTEM = "SYSTEM"


class ResponderType(StrEnum):
    """Responder entity type."""

    STAFF = "STAFF"
    SECURITY = "SECURITY"
    COMMITTEE = "COMMITTEE"
    VENDOR = "VENDOR"
    EMERGENCY_CONTACT = "EMERGENCY_CONTACT"


class ActionStatus(StrEnum):
    """Action item completion status."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class ActionPriority(StrEnum):
    """Action item urgency level."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class AttachmentFileType(StrEnum):
    """Incident attachment file classification."""

    IMAGE = "IMAGE"
    AUDIO = "AUDIO"
    DOCUMENT = "DOCUMENT"
    VIDEO = "VIDEO"


class EmergencyContactType(StrEnum):
    """Emergency contact type classification."""

    POLICE = "POLICE"
    FIRE = "FIRE"
    AMBULANCE = "AMBULANCE"
    HOSPITAL = "HOSPITAL"
    ELECTRICITY = "ELECTRICITY"
    GAS = "GAS"
    SECURITY = "SECURITY"
    MANAGEMENT = "MANAGEMENT"
    OTHER = "OTHER"


class TimelineEventType(StrEnum):
    """Timeline entry classification."""

    REPORTED = "REPORTED"
    STATUS_CHANGED = "STATUS_CHANGED"
    ASSIGNED = "ASSIGNED"
    ACTION_TAKEN = "ACTION_TAKEN"
    ESCALATED = "ESCALATED"
    ATTACHMENT_ADDED = "ATTACHMENT_ADDED"
    OVERRIDE_APPLIED = "OVERRIDE_APPLIED"
    NOTE_ADDED = "NOTE_ADDED"
