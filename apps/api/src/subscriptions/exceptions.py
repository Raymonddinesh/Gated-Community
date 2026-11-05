"""Phase 21B — Subscription, Entitlement, and Quota Domain Exceptions."""

from typing import Any
from uuid import UUID

from fastapi import status

from apps.api.src.core.exceptions import AppException


class SubscriptionDomainException(AppException):
    """Base domain exception for subscription and entitlement operations."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code=code, message=message, status_code=status_code, details=details)


class SubscriptionNotFoundException(SubscriptionDomainException):
    """Raised when an active subscription record is not found for the society."""

    def __init__(
        self,
        society_id: UUID | None = None,
        message: str = "No active subscription found for the specified society.",
        details: dict[str, Any] | None = None,
    ) -> None:
        merged_details = details or {}
        if society_id:
            merged_details["society_id"] = str(society_id)
        super().__init__(
            code="SUBSCRIPTION_NOT_FOUND",
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            details=merged_details,
        )


class SubscriptionInactiveException(SubscriptionDomainException):
    """Raised when a subscription is suspended, cancelled, or in an invalid state."""

    def __init__(
        self,
        status_name: str,
        society_id: UUID | None = None,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        msg = message or f"Subscription is inactive with status '{status_name}'."
        merged_details = details or {}
        merged_details["subscription_status"] = status_name
        if society_id:
            merged_details["society_id"] = str(society_id)
        super().__init__(
            code="SUBSCRIPTION_INACTIVE",
            message=msg,
            status_code=status.HTTP_403_FORBIDDEN,
            details=merged_details,
        )


class PlanInactiveException(SubscriptionDomainException):
    """Raised when the plan associated with the subscription is inactive or archived."""

    def __init__(
        self,
        plan_code: str,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        msg = message or f"Subscription plan '{plan_code}' is inactive."
        merged_details = details or {}
        merged_details["plan_code"] = plan_code
        super().__init__(
            code="PLAN_INACTIVE",
            message=msg,
            status_code=status.HTTP_403_FORBIDDEN,
            details=merged_details,
        )


class EntitlementNotFoundException(SubscriptionDomainException):
    """Raised when an explicit entitlement is required but not configured."""

    def __init__(
        self,
        entitlement_key: str,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        msg = message or f"Entitlement '{entitlement_key}' is not configured."
        merged_details = details or {}
        merged_details["entitlement_key"] = entitlement_key
        super().__init__(
            code="ENTITLEMENT_NOT_FOUND",
            message=msg,
            status_code=status.HTTP_404_NOT_FOUND,
            details=merged_details,
        )


class FeatureDisabledException(SubscriptionDomainException):
    """Raised when access to a feature is requested but is disabled by plan or override."""

    def __init__(
        self,
        feature_key: str,
        society_id: UUID | None = None,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        msg = message or f"Feature '{feature_key}' is disabled for this society."
        merged_details = details or {}
        merged_details["feature_key"] = feature_key
        if society_id:
            merged_details["society_id"] = str(society_id)
        super().__init__(
            code="FEATURE_DISABLED",
            message=msg,
            status_code=status.HTTP_403_FORBIDDEN,
            details=merged_details,
        )


class QuotaExceededException(SubscriptionDomainException):
    """Raised when a requested increment would exceed the effective quota limit."""

    def __init__(
        self,
        quota_key: str,
        current_usage: int,
        requested_increment: int,
        max_limit: int,
        society_id: UUID | None = None,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        msg = (
            message
            or f"Quota exceeded for '{quota_key}': current usage {current_usage} + "
            f"requested increment {requested_increment} exceeds maximum limit {max_limit}."
        )
        merged_details = details or {}
        merged_details.update(
            {
                "quota_key": quota_key,
                "current_usage": current_usage,
                "requested_increment": requested_increment,
                "max_limit": max_limit,
            }
        )
        if society_id:
            merged_details["society_id"] = str(society_id)
        super().__init__(
            code="QUOTA_EXCEEDED",
            message=msg,
            status_code=status.HTTP_409_CONFLICT,
            details=merged_details,
        )


class InvalidUsageIncrementException(SubscriptionDomainException):
    """Raised when a negative or invalid usage increment is requested."""

    def __init__(
        self,
        message: str = "Requested usage increment must not be negative.",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code="INVALID_USAGE_INCREMENT",
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details,
        )


class InvalidEntitlementConfigException(SubscriptionDomainException):
    """Raised when persisted entitlement configuration data is corrupt or invalid."""

    def __init__(
        self,
        message: str = "Invalid or contradictory entitlement configuration encountered.",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code="INVALID_ENTITLEMENT_CONFIG",
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details,
        )


class UsageMetricNotFoundException(SubscriptionDomainException):
    """Raised when an expected usage metric record does not exist and cannot be initialized."""

    def __init__(
        self,
        metric_key: str,
        society_id: UUID | None = None,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        msg = message or f"Usage metric '{metric_key}' not found."
        merged_details = details or {}
        merged_details["metric_key"] = metric_key
        if society_id:
            merged_details["society_id"] = str(society_id)
        super().__init__(
            code="USAGE_METRIC_NOT_FOUND",
            message=msg,
            status_code=status.HTTP_404_NOT_FOUND,
            details=merged_details,
        )


class StaleReconciliationException(SubscriptionDomainException):
    """Raised when reconciliation is rejected due to concurrent usage modifications or stale count."""

    def __init__(
        self,
        metric_key: str,
        current_usage: int,
        attempted_count: int,
        society_id: UUID | None = None,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        msg = (
            message
            or f"Stale reconciliation rejected for '{metric_key}': current usage is {current_usage}, "
            f"attempted reconciliation count was {attempted_count}."
        )
        merged_details = details or {}
        merged_details.update(
            {
                "metric_key": metric_key,
                "current_usage": current_usage,
                "attempted_count": attempted_count,
            }
        )
        if society_id:
            merged_details["society_id"] = str(society_id)
        super().__init__(
            code="STALE_RECONCILIATION",
            message=msg,
            status_code=status.HTTP_409_CONFLICT,
            details=merged_details,
        )


class PlanNotFoundException(SubscriptionDomainException):
    """Raised when a specified subscription plan cannot be found in the catalog."""

    def __init__(
        self,
        plan_identifier: str,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        msg = message or f"Subscription plan '{plan_identifier}' was not found in catalog."
        merged_details = details or {}
        merged_details["plan_identifier"] = plan_identifier
        super().__init__(
            code="PLAN_NOT_FOUND",
            message=msg,
            status_code=status.HTTP_404_NOT_FOUND,
            details=merged_details,
        )


class ProvisioningConflictException(SubscriptionDomainException):
    """Raised when provisioning cannot proceed due to an in-progress request or advisory lock conflict."""

    def __init__(
        self,
        message: str = "A provisioning request is currently in progress. Please retry after several seconds.",
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        merged_details = details or {}
        code = merged_details.get("code", "PROVISIONING_IN_PROGRESS")
        if "code" not in merged_details:
            merged_details["code"] = code
        if "retry_after_seconds" not in merged_details:
            merged_details["retry_after_seconds"] = 5
        self.headers = headers or {"Retry-After": "5"}
        super().__init__(
            code=code,
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            details=merged_details,
        )


class IdempotencyPayloadMismatchException(SubscriptionDomainException):
    """Raised when an idempotency key is reused with a different request payload."""

    def __init__(
        self,
        idempotency_key: str,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        msg = message or f"Idempotency key '{idempotency_key}' was previously used with a different request payload."
        merged_details = details or {}
        merged_details["idempotency_key"] = idempotency_key
        merged_details["code"] = "IDEMPOTENCY_PAYLOAD_MISMATCH"
        super().__init__(
            code="IDEMPOTENCY_PAYLOAD_MISMATCH",
            message=msg,
            status_code=422,
            details=merged_details,
        )


class InvalidProvisioningPayloadException(SubscriptionDomainException):
    """Raised when the provisioning request payload fails domain validation."""

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code="INVALID_PROVISIONING_PAYLOAD",
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details,
        )


class ProvisioningEngineException(SubscriptionDomainException):
    """Raised when an unexpected system error occurs during society provisioning."""

    def __init__(
        self,
        message: str = "An unexpected error occurred during society provisioning.",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code="PROVISIONING_ENGINE_ERROR",
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details,
        )


class SocietyAlreadySuspendedException(SubscriptionDomainException):
    """Raised when attempting to suspend a society that is already in SUSPENDED status."""

    def __init__(
        self,
        society_id: UUID | None = None,
        message: str = "Society is already in SUSPENDED status.",
        details: dict[str, Any] | None = None,
    ) -> None:
        merged_details = details or {}
        if society_id:
            merged_details["society_id"] = str(society_id)
        merged_details["code"] = "SOCIETY_ALREADY_SUSPENDED"
        super().__init__(
            code="SOCIETY_ALREADY_SUSPENDED",
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            details=merged_details,
        )


class SocietyAlreadyActiveException(SubscriptionDomainException):
    """Raised when attempting to reactivate a society that is already in ACTIVE status."""

    def __init__(
        self,
        society_id: UUID | None = None,
        message: str = "Society is already in ACTIVE status.",
        details: dict[str, Any] | None = None,
    ) -> None:
        merged_details = details or {}
        if society_id:
            merged_details["society_id"] = str(society_id)
        merged_details["code"] = "SOCIETY_ALREADY_ACTIVE"
        super().__init__(
            code="SOCIETY_ALREADY_ACTIVE",
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            details=merged_details,
        )


class SocietyLifecycleValidationException(SubscriptionDomainException):
    """Raised when a society lifecycle transition fails business rule or reason validation."""

    def __init__(
        self,
        message: str,
        code: str = "INVALID_LIFECYCLE_TRANSITION",
        details: dict[str, Any] | None = None,
    ) -> None:
        merged = details or {}
        merged["code"] = code
        super().__init__(
            code=code,
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=merged,
        )


class ProvisioningRetryIneligibleException(SubscriptionDomainException):
    """Raised when a society provisioning attempt is ineligible for retry (e.g. already COMPLETED)."""

    def __init__(
        self,
        message: str = "Society provisioning has already completed and cannot be retried.",
        code: str = "PROVISIONING_ALREADY_COMPLETED",
        details: dict[str, Any] | None = None,
    ) -> None:
        merged = details or {}
        merged["code"] = code
        super().__init__(
            code=code,
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            details=merged,
        )


class InvalidSubscriptionTransitionException(SubscriptionDomainException):
    """Raised when an illegal subscription state transition is attempted."""

    def __init__(
        self,
        from_status: str,
        to_status: str,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        msg = (
            message
            or f"Subscription transition from '{from_status}' to '{to_status}' is prohibited."
        )
        merged = details or {}
        merged["from_status"] = from_status
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(
            code="INVALID_SUBSCRIPTION_TRANSITION",
            message=msg,
            status_code=status.HTTP_409_CONFLICT,
            details=merged,
        )


class SubscriptionAlreadyCancelledException(SubscriptionDomainException):
    """Raised when attempting to modify or reactivate a CANCELLED subscription."""

    def __init__(
        self,
        society_id: UUID | None = None,
        message: str = "Subscription is CANCELLED and cannot be reactivated or modified.",
        details: dict[str, Any] | None = None,
    ) -> None:
        merged = details or {}
        if society_id:
            merged["society_id"] = str(society_id)
        merged["code"] = "SUBSCRIPTION_ALREADY_CANCELLED"
        super().__init__(
            code="SUBSCRIPTION_ALREADY_CANCELLED",
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            details=merged,
        )


class DowngradeQuotaViolationException(SubscriptionDomainException):
    """Raised when a tenant's current usage exceeds the quota of the target downgrade plan."""

    def __init__(
        self,
        target_plan_code: str,
        violations: list[dict[str, Any]] | dict[str, Any],
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.target_plan_code = target_plan_code
        self.violations = violations
        msg = (
            message
            or f"Cannot downgrade to plan '{target_plan_code}': current usage exceeds target quotas."
        )
        merged = details or {}
        merged["target_plan_code"] = target_plan_code
        merged["violations"] = violations
        merged["code"] = "DOWNGRADE_QUOTA_VIOLATION"
        super().__init__(
            code="DOWNGRADE_QUOTA_VIOLATION",
            message=msg,
            status_code=status.HTTP_409_CONFLICT,
            details=merged,
        )


class DuplicateDowngradeRequestException(SubscriptionDomainException):
    """Raised when a plan downgrade is already scheduled for the subscription."""

    def __init__(
        self,
        scheduled_plan_id: UUID | None = None,
        message: str = "A plan downgrade is already scheduled for this subscription.",
        details: dict[str, Any] | None = None,
    ) -> None:
        merged = details or {}
        if scheduled_plan_id:
            merged["scheduled_plan_id"] = str(scheduled_plan_id)
        merged["code"] = "DUPLICATE_DOWNGRADE_REQUEST"
        super().__init__(
            code="DUPLICATE_DOWNGRADE_REQUEST",
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            details=merged,
        )


class InvalidBillingPeriodException(SubscriptionDomainException):
    """Raised when billing period parameters or calculations are invalid."""

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged = details or {}
        merged["code"] = "INVALID_BILLING_PERIOD"
        super().__init__(
            code="INVALID_BILLING_PERIOD",
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=merged,
        )


class ProrationCalculationException(SubscriptionDomainException):
    """Raised when proration calculation encounters invalid durations or inputs."""

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged = details or {}
        merged["code"] = "PRORATION_CALCULATION_ERROR"
        super().__init__(
            code="PRORATION_CALCULATION_ERROR",
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=merged,
        )



