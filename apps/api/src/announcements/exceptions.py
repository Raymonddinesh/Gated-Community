"""Phase 16 Announcement Custom Exceptions."""

from fastapi import HTTPException, status


class AnnouncementException(HTTPException):
    def __init__(self, detail: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        super().__init__(status_code=status_code, detail=detail)


class AnnouncementNotFoundError(AnnouncementException):
    def __init__(self, detail: str = "Announcement not found."):
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND)


class AnnouncementAccessDeniedError(AnnouncementException):
    def __init__(self, detail: str = "Access to announcement denied."):
        super().__init__(detail=detail, status_code=status.HTTP_403_FORBIDDEN)


class InvalidAnnouncementStateError(AnnouncementException):
    def __init__(self, detail: str = "Invalid announcement status transition."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class InvalidPublicationTimeError(AnnouncementException):
    def __init__(self, detail: str = "Publish time must be before expiry time and in the future."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class AnnouncementAlreadyPublishedError(AnnouncementException):
    def __init__(self, detail: str = "Announcement is already published."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class AnnouncementExpiredError(AnnouncementException):
    def __init__(self, detail: str = "Announcement has expired."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class AudienceAccessDeniedError(AnnouncementException):
    def __init__(self, detail: str = "Audience target belongs to another tenant or invalid scope."):
        super().__init__(detail=detail, status_code=status.HTTP_403_FORBIDDEN)


class InvalidAudienceError(AnnouncementException):
    def __init__(self, detail: str = "Audience targeting selection is invalid."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class CrossTenantAudienceError(AnnouncementException):
    def __init__(self, detail: str = "Cannot target audience components across tenant boundaries."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class AcknowledgementNotRequiredError(AnnouncementException):
    def __init__(self, detail: str = "Announcement does not require explicit acknowledgement."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class AlreadyAcknowledgedError(AnnouncementException):
    def __init__(self, detail: str = "User has already acknowledged this announcement version."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class AttachmentAccessDeniedError(AnnouncementException):
    def __init__(self, detail: str = "Access to attachment denied."):
        super().__init__(detail=detail, status_code=status.HTTP_403_FORBIDDEN)


class InvalidAttachmentError(AnnouncementException):
    def __init__(self, detail: str = "Attachment file type or size is invalid."):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class PublishPermissionRequiredError(AnnouncementException):
    def __init__(self, detail: str = "User lacks permission to publish official announcements."):
        super().__init__(detail=detail, status_code=status.HTTP_403_FORBIDDEN)


class ApprovalRequiredError(AnnouncementException):
    def __init__(
        self, detail: str = "Announcement requires administrative review and approval before publishing."
    ):
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)
