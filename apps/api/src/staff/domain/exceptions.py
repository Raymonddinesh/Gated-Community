"""Staff Domain Custom Exceptions."""

from fastapi import status

from apps.api.src.core.exceptions import (
    AppException,
    ConflictException,
    NotFoundException,
)


class StaffNotFoundError(NotFoundException):
    """Raised when a staff profile is not found."""

    def __init__(self, staff_id_or_code: str):
        super().__init__(
            message=f"Staff profile '{staff_id_or_code}' was not found.",
        )


class StaffRoleNotFoundError(NotFoundException):
    """Raised when a staff role is not found."""

    def __init__(self, role_id_or_code: str):
        super().__init__(
            message=f"Staff role '{role_id_or_code}' was not found.",
        )


class StaffTeamNotFoundError(NotFoundException):
    """Raised when a staff team is not found."""

    def __init__(self, team_id_or_code: str):
        super().__init__(
            message=f"Staff team '{team_id_or_code}' was not found.",
        )


class StaffDocumentNotFoundError(NotFoundException):
    """Raised when a staff document is not found."""

    def __init__(self, document_id: str):
        super().__init__(
            message=f"Staff document '{document_id}' was not found.",
        )


class InvalidStaffStatusTransitionError(AppException):
    """Raised when attempting an invalid staff status lifecycle transition."""

    def __init__(self, from_status: str, to_status: str):
        super().__init__(
            code="INVALID_STAFF_STATUS_TRANSITION",
            message=f"Cannot transition staff status from '{from_status}' to '{to_status}'.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class StaffNotActiveError(AppException):
    """Raised when an operation requires an ACTIVE staff profile."""

    def __init__(self, staff_id: str, status_name: str):
        super().__init__(
            code="STAFF_NOT_ACTIVE",
            message=f"Staff '{staff_id}' is currently '{status_name}' and ineligible for this operation.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class CrossSocietyStaffReferenceError(ConflictException):
    """Raised when a staff entity references a resource from another society."""

    def __init__(self, detail: str):
        super().__init__(
            message=f"Cross-society reference rejected: {detail}",
        )


class StaffCodeGenerationError(AppException):
    """Raised when staff code sequence generation fails."""

    def __init__(self, detail: str):
        super().__init__(
            code="STAFF_CODE_GENERATION_FAILED",
            message=f"Staff code generation failed: {detail}",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
