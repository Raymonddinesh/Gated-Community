"""Staff Domain Enumerations."""

from enum import StrEnum


class StaffEngagementType(StrEnum):
    """Operational engagement classification for staff members."""

    FULL_TIME = "FULL_TIME"
    PART_TIME = "PART_TIME"
    CONTRACT = "CONTRACT"
    TEMPORARY = "TEMPORARY"
    VOLUNTEER = "VOLUNTEER"
    OTHER = "OTHER"


class StaffStatus(StrEnum):
    """Staff status lifecycle state."""

    ONBOARDING = "ONBOARDING"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    SUSPENDED = "SUSPENDED"
    OFFBOARDED = "OFFBOARDED"


class StaffDocumentType(StrEnum):
    """Staff document classification type."""

    IDENTITY = "IDENTITY"
    EMPLOYMENT = "EMPLOYMENT"
    CERTIFICATION = "CERTIFICATION"
    TRAINING = "TRAINING"
    OTHER = "OTHER"
