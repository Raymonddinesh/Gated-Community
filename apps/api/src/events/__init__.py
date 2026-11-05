"""Phase 17 Events & Community Management Package."""

from apps.api.src.events.enums import (
    EventAttendanceStatus,
    EventRegistrationStatus,
    EventStatus,
    EventType,
    ParticipantType,
)
from apps.api.src.events.event_service import EventService
from apps.api.src.events.exceptions import (
    CapacityExceededError,
    CrossTenantEventError,
    DuplicateRegistrationError,
    EventNotFoundError,
    FacilityBookingConflictError,
    InvalidEventStateError,
)

__all__ = [
    "EventType",
    "EventStatus",
    "EventRegistrationStatus",
    "EventAttendanceStatus",
    "ParticipantType",
    "EventService",
    "EventNotFoundError",
    "InvalidEventStateError",
    "DuplicateRegistrationError",
    "CapacityExceededError",
    "FacilityBookingConflictError",
    "CrossTenantEventError",
]
