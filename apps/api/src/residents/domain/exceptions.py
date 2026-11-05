"""Domain exceptions for Resident, Ownership, Occupancy, and Household management."""

from apps.api.src.core.exceptions import AppException


class ResidentDomainException(AppException):
    """Base exception for all resident and occupancy domain errors."""

    def __init__(
        self,
        message: str,
        code: str = "RESIDENT_DOMAIN_ERROR",
        status_code: int = 400,
        details: dict | None = None,
    ) -> None:
        super().__init__(code=code, message=message, status_code=status_code, details=details)


class InvalidOwnershipPercentageError(ResidentDomainException):
    """Raised when ownership percentage is <= 0, > 100, or active total exceeds 100%."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message=message, status_code=400, details=details)


class OccupancyOverlapError(ResidentDomainException):
    """Raised when tenant occupancy dates conflict with an existing active tenancy."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message=message, status_code=409, details=details)


class InvalidDateRangeError(ResidentDomainException):
    """Raised when start date is after end date or dates are invalid."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message=message, status_code=400, details=details)


class UnauthorizedDelegateError(ResidentDomainException):
    """Raised when delegator lacks rights, delegate is invalid, or permissions exceed authority."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message=message, status_code=403, details=details)


class ResidentNotFoundError(ResidentDomainException):
    """Raised when a resident profile or user is not found."""

    def __init__(self, message: str = "Resident profile not found", details: dict | None = None) -> None:
        super().__init__(message=message, status_code=404, details=details)


class OccupancyNotFoundError(ResidentDomainException):
    """Raised when an occupancy record is not found."""

    def __init__(self, message: str = "Unit occupancy record not found", details: dict | None = None) -> None:
        super().__init__(message=message, status_code=404, details=details)


class OwnershipNotFoundError(ResidentDomainException):
    """Raised when an ownership record is not found."""

    def __init__(self, message: str = "Unit ownership record not found", details: dict | None = None) -> None:
        super().__init__(message=message, status_code=404, details=details)


class FamilyMemberNotFoundError(ResidentDomainException):
    """Raised when a family member record is not found."""

    def __init__(self, message: str = "Family member record not found", details: dict | None = None) -> None:
        super().__init__(message=message, status_code=404, details=details)


class DelegateNotFoundError(ResidentDomainException):
    """Raised when a delegate record is not found."""

    def __init__(self, message: str = "Delegate record not found", details: dict | None = None) -> None:
        super().__init__(message=message, status_code=404, details=details)


class CrossSocietyAccessError(ResidentDomainException):
    """Raised when a resident or resource belongs to a different society tenant."""

    def __init__(
        self, message: str = "Access forbidden across society boundaries", details: dict | None = None
    ) -> None:
        super().__init__(message=message, status_code=403, details=details)


class UnitNotFoundError(ResidentDomainException):
    """Raised when a unit is not found within the society."""

    def __init__(self, message: str = "Unit not found within society", details: dict | None = None) -> None:
        super().__init__(message=message, status_code=404, details=details)
