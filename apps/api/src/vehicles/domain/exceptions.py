"""Vehicle domain specific exceptions inheriting from AppException."""

import uuid
from typing import Any

from apps.api.src.core.exceptions import AppException


class VehicleDomainError(AppException):
    """Base exception for vehicle domain errors."""

    def __init__(
        self,
        message: str,
        code: str = "VEHICLE_DOMAIN_ERROR",
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code=code, message=message, status_code=status_code, details=details)


class VehicleNotFoundError(VehicleDomainError):
    """Vehicle not found."""

    def __init__(self, vehicle_id: uuid.UUID | str) -> None:
        super().__init__(
            message=f"Vehicle with ID '{vehicle_id}' not found",
            code="VEHICLE_NOT_FOUND",
            status_code=404,
        )


class DuplicateVehicleRegistrationError(VehicleDomainError):
    """Active vehicle with the same normalized registration number already exists in this society."""

    def __init__(self, registration_number: str, normalized_registration_number: str) -> None:
        super().__init__(
            message=(
                f"An active vehicle with normalized registration '{normalized_registration_number}' "
                f"(original: '{registration_number}') already exists in this society"
            ),
            code="DUPLICATE_REGISTRATION",
            status_code=409,
            details={
                "registration_number": registration_number,
                "normalized_registration_number": normalized_registration_number,
            },
        )


class VehicleAssociationNotFoundError(VehicleDomainError):
    """Vehicle resident association not found."""

    def __init__(self, association_id: uuid.UUID | str) -> None:
        super().__init__(
            message=f"Vehicle resident association with ID '{association_id}' not found",
            code="ASSOCIATION_NOT_FOUND",
            status_code=404,
        )


class DuplicateVehicleAssociationError(VehicleDomainError):
    """Active association between vehicle, user, and unit already exists."""

    def __init__(self, vehicle_id: uuid.UUID, user_id: uuid.UUID, unit_id: uuid.UUID) -> None:
        super().__init__(
            message=f"An active association already exists for vehicle '{vehicle_id}', user '{user_id}', unit '{unit_id}'",
            code="DUPLICATE_ASSOCIATION",
            status_code=409,
        )


class InvalidVehicleStatusTransitionError(VehicleDomainError):
    """Illegal status transition for vehicle."""

    def __init__(self, current_status: str, target_status: str) -> None:
        super().__init__(
            message=f"Cannot transition vehicle status from '{current_status}' to '{target_status}'",
            code="INVALID_STATUS_TRANSITION",
            status_code=400,
        )


class InvalidVerificationStatusError(VehicleDomainError):
    """Invalid verification transition or status."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message=message,
            code="INVALID_VERIFICATION_STATUS",
            status_code=400,
        )


class VehicleDocumentNotFoundError(VehicleDomainError):
    """Vehicle document not found."""

    def __init__(self, document_id: uuid.UUID | str) -> None:
        super().__init__(
            message=f"Vehicle document with ID '{document_id}' not found",
            code="DOCUMENT_NOT_FOUND",
            status_code=404,
        )


class UnauthorizedVehicleActionError(VehicleDomainError):
    """Action on vehicle not permitted for user."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message=message,
            code="UNAUTHORIZED_VEHICLE_ACTION",
            status_code=403,
        )


class VehicleAccessRecordImmutableError(VehicleDomainError):
    """Vehicle access records are append-only and cannot be modified or deleted."""

    def __init__(self) -> None:
        super().__init__(
            message="Vehicle access records are immutable audit logs and cannot be updated or deleted",
            code="ACCESS_RECORD_IMMUTABLE",
            status_code=400,
        )
