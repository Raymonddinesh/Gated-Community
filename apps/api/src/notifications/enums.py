"""Phase 20 Notifications & Communication Delivery Enums."""

from enum import StrEnum


class NotificationCategory(StrEnum):
    """Notification Category Hierarchy."""

    ANNOUNCEMENT = "ANNOUNCEMENT"
    BILLING = "BILLING"
    EMERGENCY = "EMERGENCY"
    GOVERNANCE = "GOVERNANCE"
    COMPLAINT = "COMPLAINT"
    EVENT = "EVENT"
    FACILITY = "FACILITY"
    MAINTENANCE = "MAINTENANCE"
    GENERAL = "GENERAL"


class PriorityLevel(StrEnum):
    """Notification Priority Levels."""

    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class NotificationStatus(StrEnum):
    """Notification Lifecycle States."""

    CREATED = "CREATED"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    READ = "READ"
    PARTIALLY_DELIVERED = "PARTIALLY_DELIVERED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class DeliveryStatus(StrEnum):
    """Channel Delivery Execution States."""

    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    EXPIRED = "EXPIRED"
    SUPPRESSED = "SUPPRESSED"
    CANCELLED = "CANCELLED"


class AttemptStatus(StrEnum):
    """Provider Delivery Attempt States."""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    RETRYABLE_FAILURE = "RETRYABLE_FAILURE"


class ChannelType(StrEnum):
    """Supported Communication Channels."""

    IN_APP = "IN_APP"
    EMAIL = "EMAIL"
    SMS = "SMS"
    WHATSAPP = "WHATSAPP"
    PUSH = "PUSH"


class RecipientType(StrEnum):
    """Target Audience Types."""

    RESIDENT = "RESIDENT"
    OWNER = "OWNER"
    TENANT = "TENANT"
    COMMITTEE = "COMMITTEE"
    STAFF = "STAFF"
    ALL_RESIDENTS = "ALL_RESIDENTS"


class DevicePlatform(StrEnum):
    """Mobile Push Platforms."""

    ANDROID = "ANDROID"
    IOS = "IOS"
    WEB = "WEB"
