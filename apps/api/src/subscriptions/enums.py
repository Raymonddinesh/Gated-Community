"""Phase 21B — Subscription, Entitlement, and Quota Domain Enums."""

from enum import StrEnum


class EntitlementType(StrEnum):
    """Supported entitlement representations established by Phase 21A models."""

    BOOLEAN = "BOOLEAN"
    NUMERIC = "NUMERIC"
    UNLIMITED = "UNLIMITED"


class SubscriptionStatus(StrEnum):
    """Society subscription lifecycle statuses."""

    TRIAL = "TRIAL"
    ACTIVE = "ACTIVE"
    PAST_DUE = "PAST_DUE"
    SUSPENDED = "SUSPENDED"
    CANCELLED = "CANCELLED"


class EntitlementSource(StrEnum):
    """Source of resolved entitlement evaluation according to precedence rules."""

    OVERRIDE = "OVERRIDE"
    PLAN = "PLAN"
    SYSTEM_DEFAULT = "SYSTEM_DEFAULT"


class FeatureKey(StrEnum):
    """Well-known platform feature keys."""

    GOVERNANCE = "feature.governance"
    FACILITY_BOOKING = "feature.facility_booking"
    MAINTENANCE_BILLING = "feature.maintenance_billing"
    VISITOR_MANAGEMENT = "feature.visitor_management"
    VEHICLE_TRACKING = "feature.vehicle_tracking"
    ACCOUNTING_ADVANCED = "feature.accounting_advanced"
    EMERGENCY_MANAGEMENT = "feature.emergency_management"
    VENDOR_MANAGEMENT = "feature.vendor_management"


class QuotaKey(StrEnum):
    """Well-known platform quota / metric keys."""

    UNITS_MAX = "quota.units.max"
    RESIDENTS_MAX = "quota.residents.max"
    STAFF_MAX = "quota.staff.max"
    STORAGE_BYTES_MAX = "quota.storage.bytes.max"


class ProvisioningStepKey(StrEnum):
    """Canonical steps executed during the society provisioning lifecycle."""

    VALIDATE_INPUT = "VALIDATE_INPUT"
    CREATE_SOCIETY_ROOT = "CREATE_SOCIETY_ROOT"
    BIND_TENANT_RLS = "BIND_TENANT_RLS"
    ASSIGN_SUBSCRIPTION = "ASSIGN_SUBSCRIPTION"
    INIT_USAGE_METRICS = "INIT_USAGE_METRICS"
    PROVISION_ADMIN_USER = "PROVISION_ADMIN_USER"
    ASSIGN_ADMIN_ROLE = "ASSIGN_ADMIN_ROLE"
    INIT_SPATIAL_BASELINE = "INIT_SPATIAL_BASELINE"
    FINALIZE_ONBOARDING = "FINALIZE_ONBOARDING"


class ProvisioningStatus(StrEnum):
    """Execution status for provisioning steps and attempts."""

    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
