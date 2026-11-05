"""Domain Exceptions for Maintenance & Work Order Management."""

from apps.api.src.core.exceptions import AppException


class MaintenanceDomainError(AppException):
    """Base exception for Maintenance domain."""

    def __init__(
        self,
        message: str,
        status_code: int = 400,
        details: dict | None = None,
        code: str = "MAINTENANCE_ERROR",
    ):
        super().__init__(code=code, message=message, status_code=status_code, details=details)


class WorkOrderNotFoundError(MaintenanceDomainError):
    """Work order not found in current society."""

    def __init__(self, work_order_id: str):
        super().__init__(
            code="WORK_ORDER_NOT_FOUND",
            message=f"Work Order with ID '{work_order_id}' was not found.",
            status_code=404,
            details={"work_order_id": work_order_id},
        )


class MaintenanceCategoryNotFoundError(MaintenanceDomainError):
    """Maintenance category not found."""

    def __init__(self, category_id: str):
        super().__init__(
            code="MAINTENANCE_CATEGORY_NOT_FOUND",
            message=f"Maintenance category '{category_id}' was not found.",
            status_code=404,
            details={"category_id": category_id},
        )


class InvalidWorkOrderTransitionError(MaintenanceDomainError):
    """Work order status transition is invalid."""

    def __init__(self, current_status: str, target_status: str):
        super().__init__(
            code="INVALID_WORK_ORDER_TRANSITION",
            message=f"Cannot transition Work Order from status '{current_status}' to '{target_status}'.",
            status_code=400,
            details={"current_status": current_status, "target_status": target_status},
        )


class CrossSocietyWorkOrderError(MaintenanceDomainError):
    """Attempted cross-society entity reference."""

    def __init__(self, message: str = "Referenced entity belongs to a different society."):
        super().__init__(
            code="CROSS_SOCIETY_WORK_ORDER_ERROR",
            message=message,
            status_code=400,
        )


class WorkOrderPermissionDeniedError(MaintenanceDomainError):
    """Action denied for caller."""

    def __init__(self, message: str = "Permission denied for this work order action."):
        super().__init__(
            code="WORK_ORDER_PERMISSION_DENIED",
            message=message,
            status_code=403,
        )


class InvalidScheduleError(MaintenanceDomainError):
    """Invalid schedule timestamps."""

    def __init__(self, message: str = "Scheduled end time cannot be before scheduled start time."):
        super().__init__(
            code="INVALID_SCHEDULE",
            message=message,
            status_code=400,
        )
