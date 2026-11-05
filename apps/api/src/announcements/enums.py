"""Phase 16 Announcements & Communications Enums."""

from enum import StrEnum


class AnnouncementPriority(StrEnum):
    NORMAL = "NORMAL"
    IMPORTANT = "IMPORTANT"
    URGENT = "URGENT"


class AnnouncementStatus(StrEnum):
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SCHEDULED = "SCHEDULED"
    PUBLISHED = "PUBLISHED"
    EXPIRED = "EXPIRED"
    ARCHIVED = "ARCHIVED"


class AudienceType(StrEnum):
    SOCIETY = "SOCIETY"
    BLOCK = "BLOCK"
    FLOOR = "FLOOR"
    UNIT = "UNIT"
    RESIDENT = "RESIDENT"


class RoleFilter(StrEnum):
    ALL = "ALL"
    OWNER_ONLY = "OWNER_ONLY"
    TENANT_ONLY = "TENANT_ONLY"


class ScheduleStatus(StrEnum):
    PENDING = "PENDING"
    EXECUTED = "EXECUTED"
    CANCELLED = "CANCELLED"
